"""Background health monitor for MCP server containers.

Periodically polls running servers via Docker inspect and HTTP probe,
updating the health_status column on each Server record. Started as
an asyncio background task from the admin API lifespan.

Depends on: switchboard.registry.models, switchboard.db.session, docker, httpx
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import docker
import docker.errors
import httpx
import structlog

from switchboard.container.manager import CONTAINER_NAME_PREFIX
from switchboard.registry.models import HealthStatus, Server, ServerStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = structlog.get_logger()


class HealthMonitor:
    """Polls running MCP servers and updates their health_status.

    Uses Docker inspect to check container state, then HTTP POST /mcp
    to probe liveness. Tracks consecutive HTTP failures in memory to
    implement the healthy -> degraded -> unreachable state machine.

    Args:
        session_factory: Async session factory for DB access (session-per-cycle).
        http_client: Shared httpx.AsyncClient for HTTP probes.
        poll_interval: Seconds between polling cycles (default 30).
        cloud_map_domain: DNS suffix for Cloud Map service discovery.
            ".switchboard.local" in ECS, "" (empty) in local Docker Compose.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        http_client: httpx.AsyncClient,
        poll_interval: int = 30,
        cloud_map_domain: str = "",
    ) -> None:
        self._session_factory = session_factory
        self._client = http_client
        self._interval = poll_interval
        self._cloud_map_domain = cloud_map_domain
        self._failure_counts: dict[str, int] = {}

    async def run(self) -> None:
        """Main polling loop -- runs until cancelled."""
        try:
            while True:
                await self._poll_cycle()
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            logger.info("health_monitor_shutdown")
            raise

    async def _poll_cycle(self) -> None:
        """Poll all running servers. Never raises (exceptions isolated per server)."""
        async with self._session_factory() as session:
            servers = await self._get_running_servers(session)
            current_names = {s.name for s in servers}
            # Prune failure counters for servers no longer running
            stale = set(self._failure_counts.keys()) - current_names
            for name in stale:
                del self._failure_counts[name]

            for server in servers:
                try:
                    new_status = await self._probe_server(server)
                    await self._update_health(session, server, new_status)
                except Exception:
                    logger.exception("health_probe_error", server_name=server.name)
            await session.commit()

    async def _get_running_servers(self, session: AsyncSession) -> list[Server]:
        """Fetch all servers with status == running (D-12)."""
        from sqlalchemy import select

        stmt = select(Server).where(Server.status == ServerStatus.running)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _probe_server(self, server: Server) -> HealthStatus:
        """Run Docker inspect + HTTP probe and return computed status."""
        container_name = f"{CONTAINER_NAME_PREFIX}{server.name}"
        docker_status = await self._inspect_container(container_name)
        docker_running = docker_status == "running"

        if not docker_running:
            return self._compute_status(
                server.name, docker_running=False, http_ok=False
            )

        http_ok = await self._http_probe(server.name)
        return self._compute_status(server.name, docker_running=True, http_ok=http_ok)

    async def _inspect_container(self, container_name: str) -> str | None:
        """Return container status string or None if not found (D-01, D-02)."""
        return await asyncio.to_thread(self._inspect_blocking, container_name)

    def _inspect_blocking(self, container_name: str) -> str | None:
        """Blocking Docker inspect -- runs in thread (D-05).

        Creates a fresh Docker client per call and closes it in a finally
        block, matching the pattern established in ContainerManager.

        Args:
            container_name: Full container name (e.g. sb-my-server).

        Returns:
            Container status string (e.g. "running") or None if not found.
        """
        client = docker.from_env()
        try:
            container = client.containers.get(container_name)
            return container.status
        except docker.errors.NotFound:
            return None
        finally:
            client.close()

    async def _http_probe(self, server_name: str) -> bool:
        """Probe the MCP server's /mcp endpoint (D-03).

        Returns True if any HTTP response received (2xx, 4xx, 5xx = alive).
        Returns False on connection error or timeout.

        Args:
            server_name: Server name (without container prefix).

        Returns:
            True if any HTTP response was received, False on transport error.
        """
        url = f"http://{CONTAINER_NAME_PREFIX}{server_name}{self._cloud_map_domain}:8000/mcp"
        try:
            await self._client.post(url, content=b"")
            return True
        except httpx.TransportError:
            return False

    def _compute_status(
        self,
        server_name: str,
        *,
        docker_running: bool,
        http_ok: bool,
    ) -> HealthStatus:
        """Apply health state machine (D-04).

        State machine:
        - healthy: Docker running AND HTTP probe succeeds
        - degraded: Docker running BUT HTTP failing (< 2 consecutive)
        - unreachable: Docker not running OR HTTP failed >= 2 consecutive

        Args:
            server_name: Server name for failure counter lookup.
            docker_running: Whether Docker reports container as running.
            http_ok: Whether the HTTP probe received any response.

        Returns:
            Computed HealthStatus value.
        """
        if not docker_running:
            self._failure_counts.pop(server_name, None)
            return HealthStatus.unreachable

        if http_ok:
            self._failure_counts.pop(server_name, None)
            return HealthStatus.healthy

        count = self._failure_counts.get(server_name, 0) + 1
        self._failure_counts[server_name] = count
        if count >= 2:
            return HealthStatus.unreachable
        return HealthStatus.degraded

    async def _update_health(
        self,
        session: AsyncSession,
        server: Server,
        status: HealthStatus,
    ) -> None:
        """Persist the computed health status to the database.

        Args:
            session: Active async database session.
            server: Server ORM instance to update.
            status: New health status to persist.
        """
        server.health_status = status
        session.add(server)
        await session.flush()
        logger.debug(
            "health_status_updated",
            server_name=server.name,
            health_status=status.value,
        )
