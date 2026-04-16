"""Container lifecycle manager wrapping Docker SDK operations.

Provides async-safe start/stop/restart for MCP server containers. All
Docker SDK calls execute inside ``asyncio.to_thread()`` with a fresh
``docker.from_env()`` client per call to avoid event-loop blocking and
connection pool issues.

Containers join the ``switchboard-internal`` bridge network and do NOT
publish host ports (D-01 / T-3-02). The gateway routes traffic to
containers by their internal network address.

Depends on: docker, switchboard.registry.models, switchboard.registry.repository,
            switchboard.container.exceptions
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import docker
import docker.errors

from switchboard.container.exceptions import ContainerStartError, ContainerStopError
from switchboard.registry.models import ServerStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from switchboard.registry.models import Server
    from switchboard.registry.repository import ServerRepository

logger = logging.getLogger(__name__)

CONTAINER_PORT: int = 8000
CONTAINER_NAME_PREFIX: str = "sb-"
DOCKER_NETWORK: str = "switchboard-internal"


class ContainerManager:
    """Async-safe container lifecycle manager.

    Wraps Docker SDK operations for starting, stopping, and restarting
    MCP server containers. Each blocking Docker call runs inside
    ``asyncio.to_thread()`` with a fresh client to avoid blocking the
    event loop.

    All containers join the ``switchboard-internal`` Docker network and
    do not expose host ports. Registry state (server status, container ID)
    is updated after each operation.
    """

    async def start(
        self,
        session: AsyncSession,
        server: Server,
        repo: ServerRepository,
    ) -> Server:
        """Start a container for the given server.

        Creates a Docker container on the internal network, verifies it
        reaches running state, and updates the registry with the new
        container ID and running status.

        Args:
            session: Async database session for registry updates.
            server: Server ORM instance to start.
            repo: Repository for persisting status changes.

        Returns:
            The updated Server instance with running status and container ID.

        Raises:
            ContainerStartError: If the container fails to start for any
                reason (image not found, API error, container not running).
        """
        container_name = f"{CONTAINER_NAME_PREFIX}{server.name}"
        try:
            container_id: str = await asyncio.to_thread(
                self._start_blocking, server.container_image, container_name
            )
        except (
            docker.errors.ImageNotFound,
            docker.errors.APIError,
            RuntimeError,
        ) as exc:
            logger.error("Container start failed for '%s': %s", server.name, exc)
            await repo.update_status(session, server.id, ServerStatus.error)
            raise ContainerStartError(server.name, str(exc)) from exc

        await repo.update_status(session, server.id, ServerStatus.running)
        updated = await repo.update_container_id(session, server.id, container_id)
        return updated if updated is not None else server

    async def stop(
        self,
        session: AsyncSession,
        server: Server,
        repo: ServerRepository,
    ) -> Server:
        """Stop and remove the container for the given server.

        Stops the container with a 10-second timeout, then force-removes
        it. If the container is already gone, the registry is still
        updated to stopped state.

        Args:
            session: Async database session for registry updates.
            server: Server ORM instance to stop.
            repo: Repository for persisting status changes.

        Returns:
            The updated Server instance with stopped status and no container ID.

        Raises:
            ContainerStopError: If the stop operation fails unexpectedly.
        """
        if server.container_id is not None:
            try:
                await asyncio.to_thread(self._stop_blocking, server.container_id)
            except docker.errors.APIError as exc:
                logger.error("Container stop failed for '%s': %s", server.name, exc)
                raise ContainerStopError(server.name, str(exc)) from exc

        await repo.update_status(session, server.id, ServerStatus.stopped)
        updated = await repo.update_container_id(session, server.id, None)
        return updated if updated is not None else server

    async def restart(
        self,
        session: AsyncSession,
        server: Server,
        repo: ServerRepository,
    ) -> Server:
        """Restart the container for the given server.

        Performs a stop followed by a start, producing a new container ID.
        Refreshes the server state from the database between operations.

        Args:
            session: Async database session for registry updates.
            server: Server ORM instance to restart.
            repo: Repository for persisting status changes.

        Returns:
            The updated Server instance with running status and new container ID.

        Raises:
            ContainerStartError: If the new container fails to start.
            ContainerStopError: If the old container fails to stop.
        """
        await self.stop(session, server, repo)

        # Refresh server state after stop to get cleared container_id
        refreshed = await session.get(type(server), server.id)
        if refreshed is None:
            refreshed = server

        return await self.start(session, refreshed, repo)

    def _start_blocking(self, image: str, name: str) -> str:
        """Create and verify a Docker container (blocking, runs in thread).

        Args:
            image: Docker image reference to run.
            name: Container name (prefixed with sb-).

        Returns:
            The Docker container ID string.

        Raises:
            docker.errors.ImageNotFound: If the image does not exist.
            docker.errors.APIError: If the Docker API call fails.
            RuntimeError: If the container does not reach running state.
        """
        client = docker.from_env()
        try:
            self._ensure_network(client)
            self._remove_existing_container(client, name)

            container = client.containers.run(
                image=image,
                name=name,
                detach=True,
                network=DOCKER_NETWORK,
            )

            container.reload()
            if container.status != "running":
                msg = (
                    f"Container '{name}' not in running state "
                    f"after creation: {container.status}"
                )
                raise RuntimeError(msg)

            return container.id
        finally:
            client.close()

    def _stop_blocking(self, container_id: str) -> None:
        """Stop and remove a Docker container (blocking, runs in thread).

        Args:
            container_id: Docker container ID to stop.
        """
        client = docker.from_env()
        try:
            try:
                container = client.containers.get(container_id)
                container.stop(timeout=10)
                container.remove(force=True)
            except docker.errors.NotFound:
                # Container already gone -- no action needed
                pass
        finally:
            client.close()

    def _ensure_network(self, client: docker.DockerClient) -> None:
        """Create the internal Docker network if it does not exist.

        Args:
            client: Active Docker client instance.
        """
        try:
            client.networks.get(DOCKER_NETWORK)
        except docker.errors.NotFound:
            client.networks.create(DOCKER_NETWORK, driver="bridge")

    def _remove_existing_container(
        self, client: docker.DockerClient, name: str
    ) -> None:
        """Remove a pre-existing container with the given name.

        Handles the case where a stopped container from a previous run
        still exists, preventing a new container with the same name.

        Args:
            client: Active Docker client instance.
            name: Container name to check and remove.
        """
        try:
            existing = client.containers.get(name)
            existing.remove(force=True)
        except docker.errors.NotFound:
            pass
