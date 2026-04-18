"""Integration test for HealthMonitor poll cycle against real database.

Verifies the full flow: HealthMonitor reads running servers from DB,
probes them (with mocked Docker/HTTP), and writes health_status back.

Uses the shared session fixture from tests/conftest.py for DB access
with transaction rollback isolation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from switchboard.registry.models import HealthStatus, Server, ServerStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
class TestHealthMonitorIntegration:
    """Integration tests for HealthMonitor._poll_cycle with real DB."""

    async def test_poll_cycle_updates_health_status_in_db(
        self, session: AsyncSession
    ) -> None:
        """poll_cycle writes computed health_status to the database."""
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from switchboard.health.monitor import HealthMonitor

        # Create a running server in the DB
        server = Server(
            name="integration-test-01",
            container_image="switchboard/echo:latest",
            status=ServerStatus.running,
            container_id="abc123",
        )
        session.add(server)
        await session.flush()
        await session.refresh(server)

        # Create a session factory that returns our test session
        mock_factory = MagicMock(spec=async_sessionmaker)
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        # Mock Docker inspect: container is running
        mock_docker_client = MagicMock()
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_docker_client.containers.get.return_value = mock_container

        # Mock HTTP probe: returns 200 (healthy)
        mock_httpx = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_httpx.post = AsyncMock(return_value=mock_response)

        monitor = HealthMonitor(
            session_factory=mock_factory,
            http_client=mock_httpx,
            poll_interval=30,
        )

        with patch(
            "switchboard.health.monitor.docker.from_env",
            return_value=mock_docker_client,
        ):
            await monitor._poll_cycle()

        # Verify health_status was updated in the DB
        await session.refresh(server)
        assert server.health_status == HealthStatus.healthy

    async def test_poll_cycle_skips_stopped_servers(
        self, session: AsyncSession
    ) -> None:
        """Stopped servers are not polled (D-12)."""
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from switchboard.health.monitor import HealthMonitor

        # Create a stopped server
        server = Server(
            name="integration-test-02",
            container_image="switchboard/echo:latest",
            status=ServerStatus.stopped,
        )
        session.add(server)
        await session.flush()

        mock_factory = MagicMock(spec=async_sessionmaker)
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_httpx = AsyncMock(spec=httpx.AsyncClient)

        monitor = HealthMonitor(
            session_factory=mock_factory,
            http_client=mock_httpx,
            poll_interval=30,
        )

        with patch(
            "switchboard.health.monitor.docker.from_env",
        ) as mock_docker_env:
            await monitor._poll_cycle()
            # Docker inspect should NOT have been called for stopped servers
            mock_docker_env.assert_not_called()

        # health_status should remain None (not polled)
        await session.refresh(server)
        assert server.health_status is None
