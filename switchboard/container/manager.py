"""Container lifecycle manager wrapping Docker SDK and ECS operations.

Provides async-safe start/stop/restart for MCP server containers. In local
development (Docker Compose), operations use the Docker SDK. In ECS (detected
via ECS_CONTAINER_METADATA_URI), operations route to the ECS adapter.

All blocking calls execute inside ``asyncio.to_thread()`` to avoid
event-loop blocking.

Containers join the ``switchboard-internal`` bridge network and do NOT
publish host ports (D-01 / T-3-02). The gateway routes traffic to
containers by their internal network address.

Depends on: docker, switchboard.registry.models, switchboard.registry.repository,
            switchboard.container.exceptions, switchboard.container.ecs_adapter
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import docker
import docker.errors

from switchboard.container.ecs_adapter import ECSAdapter, _is_ecs_environment
from switchboard.container.exceptions import (
    ContainerStartError,
    ContainerStopError,
)
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

    Dispatches operations to Docker SDK (local dev) or ECS adapter
    (production) based on the ECS_CONTAINER_METADATA_URI environment
    variable (D-11).

    Wraps Docker SDK operations for starting, stopping, and restarting
    MCP server containers. Each blocking Docker call runs inside
    ``asyncio.to_thread()`` with a fresh client to avoid blocking the
    event loop.

    All containers join the ``switchboard-internal`` Docker network and
    do not expose host ports. Registry state (server status, container ID)
    is updated after each operation.

    Args:
        ecs_adapter: Optional pre-configured ECS adapter for dependency
            injection in tests. If None and running in ECS, an adapter
            is created from Settings.
    """

    def __init__(
        self, ecs_adapter: ECSAdapter | None = None
    ) -> None:
        self._ecs_adapter = ecs_adapter

    async def start(
        self,
        session: AsyncSession,
        server: Server,
        repo: ServerRepository,
    ) -> Server:
        """Start a container for the given server.

        In ECS, calls the ECS adapter to set desiredCount=1.
        In Docker, creates a container on the internal network.

        Args:
            session: Async database session for registry updates.
            server: Server ORM instance to start.
            repo: Repository for persisting status changes.

        Returns:
            The updated Server instance with running status.

        Raises:
            ContainerStartError: If the container fails to start.
        """
        if _is_ecs_environment():
            return await self._start_ecs(session, server, repo)
        return await self._start_docker(session, server, repo)

    async def stop(
        self,
        session: AsyncSession,
        server: Server,
        repo: ServerRepository,
    ) -> Server:
        """Stop the container for the given server.

        In ECS, calls the ECS adapter to set desiredCount=0.
        In Docker, stops and removes the container.

        Args:
            session: Async database session for registry updates.
            server: Server ORM instance to stop.
            repo: Repository for persisting status changes.

        Returns:
            The updated Server instance with stopped status.

        Raises:
            ContainerStopError: If the stop operation fails.
        """
        if _is_ecs_environment():
            return await self._stop_ecs(session, server, repo)
        return await self._stop_docker(session, server, repo)

    async def restart(
        self,
        session: AsyncSession,
        server: Server,
        repo: ServerRepository,
    ) -> Server:
        """Restart the container for the given server.

        In ECS, forces a new deployment. In Docker, performs
        stop-then-start to get a new container ID.

        Args:
            session: Async database session for registry updates.
            server: Server ORM instance to restart.
            repo: Repository for persisting status changes.

        Returns:
            The updated Server instance with running status.

        Raises:
            ContainerStartError: If the new container fails to start.
            ContainerStopError: If the old container fails to stop.
        """
        if _is_ecs_environment():
            return await self._restart_ecs(session, server, repo)
        return await self._restart_docker(session, server, repo)

    # ------------------------------------------------------------------
    # ECS dispatch methods (D-09 / D-10 / D-11)
    # ------------------------------------------------------------------

    def _get_ecs_adapter(self) -> ECSAdapter:
        """Return the ECS adapter, creating one from Settings if needed."""
        if self._ecs_adapter is not None:
            return self._ecs_adapter
        from switchboard.config import get_settings

        settings = get_settings()
        return ECSAdapter(
            cluster_arn=settings.ecs_cluster_arn,
            region=settings.aws_region,
        )

    async def _start_ecs(
        self,
        session: AsyncSession,
        server: Server,
        repo: ServerRepository,
    ) -> Server:
        """Start server via ECS service update (D-10: desiredCount=1)."""
        service_name = f"{CONTAINER_NAME_PREFIX}{server.name}"
        adapter = self._get_ecs_adapter()
        try:
            await adapter.start_service(service_name)
        except ContainerStartError:
            await repo.update_status(
                session, server.id, ServerStatus.error
            )
            raise
        await repo.update_status(
            session, server.id, ServerStatus.running
        )
        refreshed = await session.get(type(server), server.id)
        return refreshed if refreshed is not None else server

    async def _stop_ecs(
        self,
        session: AsyncSession,
        server: Server,
        repo: ServerRepository,
    ) -> Server:
        """Stop server via ECS service update (D-10: desiredCount=0)."""
        service_name = f"{CONTAINER_NAME_PREFIX}{server.name}"
        adapter = self._get_ecs_adapter()
        try:
            await adapter.stop_service(service_name)
        except ContainerStopError:
            await repo.update_status(
                session, server.id, ServerStatus.error
            )
            raise
        await repo.update_status(
            session, server.id, ServerStatus.stopped
        )
        refreshed = await session.get(type(server), server.id)
        return refreshed if refreshed is not None else server

    async def _restart_ecs(
        self,
        session: AsyncSession,
        server: Server,
        repo: ServerRepository,
    ) -> Server:
        """Restart server via ECS force new deployment (D-10)."""
        service_name = f"{CONTAINER_NAME_PREFIX}{server.name}"
        adapter = self._get_ecs_adapter()
        try:
            await adapter.restart_service(service_name)
        except ContainerStartError:
            await repo.update_status(
                session, server.id, ServerStatus.error
            )
            raise
        await repo.update_status(
            session, server.id, ServerStatus.running
        )
        refreshed = await session.get(type(server), server.id)
        return refreshed if refreshed is not None else server

    # ------------------------------------------------------------------
    # Docker dispatch methods (local development)
    # ------------------------------------------------------------------

    async def _start_docker(
        self,
        session: AsyncSession,
        server: Server,
        repo: ServerRepository,
    ) -> Server:
        """Start a Docker container for the given server."""
        container_name = f"{CONTAINER_NAME_PREFIX}{server.name}"
        try:
            container_id: str = await asyncio.to_thread(
                self._start_blocking,
                server.container_image,
                container_name,
            )
        except (
            docker.errors.ImageNotFound,
            docker.errors.APIError,
            RuntimeError,
        ) as exc:
            logger.error(
                "Container start failed for '%s': %s",
                server.name,
                exc,
            )
            await repo.update_status(
                session, server.id, ServerStatus.error
            )
            raise ContainerStartError(server.name, str(exc)) from exc

        await repo.update_status(
            session, server.id, ServerStatus.running
        )
        updated = await repo.update_container_id(
            session, server.id, container_id
        )
        return updated if updated is not None else server

    async def _stop_docker(
        self,
        session: AsyncSession,
        server: Server,
        repo: ServerRepository,
    ) -> Server:
        """Stop and remove the Docker container for the given server."""
        if server.container_id is not None:
            try:
                await asyncio.to_thread(
                    self._stop_blocking, server.container_id
                )
            except docker.errors.APIError as exc:
                logger.error(
                    "Container stop failed for '%s': %s",
                    server.name,
                    exc,
                )
                raise ContainerStopError(
                    server.name, str(exc)
                ) from exc

        await repo.update_status(
            session, server.id, ServerStatus.stopped
        )
        updated = await repo.update_container_id(
            session, server.id, None
        )
        return updated if updated is not None else server

    async def _restart_docker(
        self,
        session: AsyncSession,
        server: Server,
        repo: ServerRepository,
    ) -> Server:
        """Restart by stopping then starting a new Docker container."""
        await self._stop_docker(session, server, repo)

        # Refresh server state after stop to get cleared container_id
        refreshed = await session.get(type(server), server.id)
        if refreshed is None:
            refreshed = server

        return await self._start_docker(session, refreshed, repo)

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
