"""Unit tests for HealthMonitor state machine, probing, and polling.

Tests cover the full health monitoring lifecycle:
- State machine transitions (healthy, degraded, unreachable)
- Docker container inspection via mocked SDK
- HTTP probe behavior with various responses and errors
- Poll cycle processing with exception isolation
- Failure counter management and cleanup
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from switchboard.health.monitor import HealthMonitor
from switchboard.registry.models import HealthStatus, ServerStatus


# ---------------------------------------------------------------------------
# State machine: _compute_status
# ---------------------------------------------------------------------------


class TestComputeStatus:
    """Tests for the _compute_status state machine method."""

    def test_compute_status_healthy(
        self, mock_httpx_client: AsyncMock, mock_session_factory: MagicMock
    ) -> None:
        """Docker running + HTTP OK -> healthy, failure counter cleared."""
        monitor = HealthMonitor(mock_session_factory, mock_httpx_client)
        # Seed a previous failure counter
        monitor._failure_counts["test-server"] = 1

        result = monitor._compute_status(
            "test-server", docker_running=True, http_ok=True
        )

        assert result == HealthStatus.healthy
        assert "test-server" not in monitor._failure_counts

    def test_compute_status_degraded(
        self, mock_httpx_client: AsyncMock, mock_session_factory: MagicMock
    ) -> None:
        """Docker running + HTTP fail (first failure) -> degraded, counter=1."""
        monitor = HealthMonitor(mock_session_factory, mock_httpx_client)

        result = monitor._compute_status(
            "test-server", docker_running=True, http_ok=False
        )

        assert result == HealthStatus.degraded
        assert monitor._failure_counts["test-server"] == 1

    def test_compute_status_unreachable_after_two_failures(
        self, mock_httpx_client: AsyncMock, mock_session_factory: MagicMock
    ) -> None:
        """Docker running + HTTP fail (second consecutive) -> unreachable, counter=2."""
        monitor = HealthMonitor(mock_session_factory, mock_httpx_client)
        monitor._failure_counts["test-server"] = 1

        result = monitor._compute_status(
            "test-server", docker_running=True, http_ok=False
        )

        assert result == HealthStatus.unreachable
        assert monitor._failure_counts["test-server"] == 2

    def test_compute_status_unreachable_docker_not_running(
        self, mock_httpx_client: AsyncMock, mock_session_factory: MagicMock
    ) -> None:
        """Docker not running -> unreachable, counter removed."""
        monitor = HealthMonitor(mock_session_factory, mock_httpx_client)
        monitor._failure_counts["test-server"] = 3

        result = monitor._compute_status(
            "test-server", docker_running=False, http_ok=False
        )

        assert result == HealthStatus.unreachable
        assert "test-server" not in monitor._failure_counts

    def test_compute_status_resets_counter_on_success(
        self, mock_httpx_client: AsyncMock, mock_session_factory: MagicMock
    ) -> None:
        """After previous failures, HTTP OK clears the counter."""
        monitor = HealthMonitor(mock_session_factory, mock_httpx_client)
        monitor._failure_counts["test-server"] = 5

        result = monitor._compute_status(
            "test-server", docker_running=True, http_ok=True
        )

        assert result == HealthStatus.healthy
        assert "test-server" not in monitor._failure_counts


# ---------------------------------------------------------------------------
# Docker inspect: _inspect_container
# ---------------------------------------------------------------------------


class TestInspectContainer:
    """Tests for _inspect_container Docker SDK calls."""

    @patch("switchboard.health.monitor.docker.from_env")
    async def test_inspect_container_running(
        self,
        mock_from_env: MagicMock,
        mock_httpx_client: AsyncMock,
        mock_session_factory: MagicMock,
    ) -> None:
        """Mocked docker returns running status."""
        container = MagicMock()
        container.status = "running"
        client = MagicMock()
        client.containers.get.return_value = container
        mock_from_env.return_value = client

        monitor = HealthMonitor(mock_session_factory, mock_httpx_client)
        result = await monitor._inspect_container("sb-test-server")

        assert result == "running"
        client.containers.get.assert_called_once_with("sb-test-server")
        client.close.assert_called_once()

    @patch("switchboard.health.monitor.docker.from_env")
    async def test_inspect_container_not_found(
        self,
        mock_from_env: MagicMock,
        mock_httpx_client: AsyncMock,
        mock_session_factory: MagicMock,
    ) -> None:
        """Mocked docker raises NotFound -> returns None."""
        import docker.errors

        client = MagicMock()
        client.containers.get.side_effect = docker.errors.NotFound("gone")
        mock_from_env.return_value = client

        monitor = HealthMonitor(mock_session_factory, mock_httpx_client)
        result = await monitor._inspect_container("sb-test-server")

        assert result is None
        client.close.assert_called_once()


# ---------------------------------------------------------------------------
# HTTP probe: _http_probe
# ---------------------------------------------------------------------------


class TestHttpProbe:
    """Tests for _http_probe HTTP liveness checks."""

    async def test_http_probe_success_200(
        self, mock_httpx_client: AsyncMock, mock_session_factory: MagicMock
    ) -> None:
        """httpx returns 200 -> True."""
        response = MagicMock()
        response.status_code = 200
        mock_httpx_client.post = AsyncMock(return_value=response)

        monitor = HealthMonitor(mock_session_factory, mock_httpx_client)
        result = await monitor._http_probe("test-server")

        assert result is True
        mock_httpx_client.post.assert_called_once_with(
            "http://sb-test-server:8000/mcp", content=b""
        )

    async def test_http_probe_success_400(
        self, mock_httpx_client: AsyncMock, mock_session_factory: MagicMock
    ) -> None:
        """httpx returns 400 -> True (any HTTP response = alive)."""
        response = MagicMock()
        response.status_code = 400
        mock_httpx_client.post = AsyncMock(return_value=response)

        monitor = HealthMonitor(mock_session_factory, mock_httpx_client)
        result = await monitor._http_probe("test-server")

        assert result is True

    async def test_http_probe_failure_transport_error(
        self, mock_httpx_client: AsyncMock, mock_session_factory: MagicMock
    ) -> None:
        """httpx raises TransportError -> False."""
        mock_httpx_client.post = AsyncMock(
            side_effect=httpx.TransportError("connection refused")
        )

        monitor = HealthMonitor(mock_session_factory, mock_httpx_client)
        result = await monitor._http_probe("test-server")

        assert result is False


# ---------------------------------------------------------------------------
# _probe_server: combines inspect + probe
# ---------------------------------------------------------------------------


class TestProbeServer:
    """Tests for _probe_server combining inspect and HTTP probe."""

    @patch("switchboard.health.monitor.docker.from_env")
    async def test_probe_server_healthy(
        self,
        mock_from_env: MagicMock,
        mock_httpx_client: AsyncMock,
        mock_session_factory: MagicMock,
    ) -> None:
        """Running container + HTTP OK -> healthy."""
        container = MagicMock()
        container.status = "running"
        client = MagicMock()
        client.containers.get.return_value = container
        mock_from_env.return_value = client

        response = MagicMock()
        response.status_code = 200
        mock_httpx_client.post = AsyncMock(return_value=response)

        server = MagicMock()
        server.name = "test-server"
        server.status = ServerStatus.running

        monitor = HealthMonitor(mock_session_factory, mock_httpx_client)
        result = await monitor._probe_server(server)

        assert result == HealthStatus.healthy

    @patch("switchboard.health.monitor.docker.from_env")
    async def test_probe_server_unreachable_docker_down(
        self,
        mock_from_env: MagicMock,
        mock_httpx_client: AsyncMock,
        mock_session_factory: MagicMock,
    ) -> None:
        """Docker not running -> unreachable, no HTTP probe called."""
        import docker.errors

        client = MagicMock()
        client.containers.get.side_effect = docker.errors.NotFound("gone")
        mock_from_env.return_value = client

        server = MagicMock()
        server.name = "test-server"
        server.status = ServerStatus.running

        monitor = HealthMonitor(mock_session_factory, mock_httpx_client)
        result = await monitor._probe_server(server)

        assert result == HealthStatus.unreachable
        # HTTP probe should NOT have been called
        mock_httpx_client.post.assert_not_called()


# ---------------------------------------------------------------------------
# _poll_cycle: full cycle processing
# ---------------------------------------------------------------------------


class TestPollCycle:
    """Tests for _poll_cycle processing multiple servers."""

    async def test_poll_cycle_processes_multiple_servers(
        self, mock_httpx_client: AsyncMock, mock_session_factory: MagicMock
    ) -> None:
        """Two servers, both probed and health updated."""
        server1 = MagicMock()
        server1.name = "server-one"
        server1.status = ServerStatus.running
        server1.health_status = None

        server2 = MagicMock()
        server2.name = "server-two"
        server2.status = ServerStatus.running
        server2.health_status = None

        monitor = HealthMonitor(mock_session_factory, mock_httpx_client)

        # Mock _get_running_servers to return our test servers
        monitor._get_running_servers = AsyncMock(return_value=[server1, server2])
        # Mock _probe_server to return healthy for both
        monitor._probe_server = AsyncMock(return_value=HealthStatus.healthy)
        # Mock _update_health to track calls
        monitor._update_health = AsyncMock()

        await monitor._poll_cycle()

        assert monitor._probe_server.call_count == 2
        assert monitor._update_health.call_count == 2

    async def test_poll_cycle_isolates_exceptions(
        self, mock_httpx_client: AsyncMock, mock_session_factory: MagicMock
    ) -> None:
        """One server probe raises, other still processed."""
        server1 = MagicMock()
        server1.name = "failing-server"
        server1.status = ServerStatus.running

        server2 = MagicMock()
        server2.name = "healthy-server"
        server2.status = ServerStatus.running

        monitor = HealthMonitor(mock_session_factory, mock_httpx_client)

        monitor._get_running_servers = AsyncMock(return_value=[server1, server2])

        # First call raises, second returns healthy
        probe_results = [RuntimeError("Docker exploded"), HealthStatus.healthy]
        call_count = 0

        async def mock_probe(server: MagicMock) -> HealthStatus:
            nonlocal call_count
            idx = call_count
            call_count += 1
            result = probe_results[idx]
            if isinstance(result, Exception):
                raise result
            return result

        monitor._probe_server = mock_probe  # type: ignore[assignment]
        monitor._update_health = AsyncMock()

        # Should not raise despite first server failure
        await monitor._poll_cycle()

        # Second server should still have been processed
        assert monitor._update_health.call_count == 1

    async def test_failure_counter_cleanup_for_stopped_servers(
        self, mock_httpx_client: AsyncMock, mock_session_factory: MagicMock
    ) -> None:
        """Failure counter pruned for servers not in the running set."""
        monitor = HealthMonitor(mock_session_factory, mock_httpx_client)
        # Pre-seed counters for servers that are no longer running
        monitor._failure_counts["old-server"] = 3
        monitor._failure_counts["current-server"] = 1

        current = MagicMock()
        current.name = "current-server"
        current.status = ServerStatus.running

        monitor._get_running_servers = AsyncMock(return_value=[current])
        monitor._probe_server = AsyncMock(return_value=HealthStatus.healthy)
        monitor._update_health = AsyncMock()

        await monitor._poll_cycle()

        # Old server counter should be pruned
        assert "old-server" not in monitor._failure_counts
        # Current server counter gets cleared by compute_status (healthy)
        # but the key behavior here is the pruning of stale entries


# ---------------------------------------------------------------------------
# Failure counter edge cases
# ---------------------------------------------------------------------------


class TestFailureCounterEdgeCases:
    """Additional edge case tests for failure counter behavior."""

    def test_failure_counter_increments_correctly(
        self, mock_httpx_client: AsyncMock, mock_session_factory: MagicMock
    ) -> None:
        """Counter increments from 0 -> 1 -> 2 on consecutive failures."""
        monitor = HealthMonitor(mock_session_factory, mock_httpx_client)

        # First failure: 0 -> 1 = degraded
        r1 = monitor._compute_status("srv", docker_running=True, http_ok=False)
        assert r1 == HealthStatus.degraded
        assert monitor._failure_counts["srv"] == 1

        # Second failure: 1 -> 2 = unreachable
        r2 = monitor._compute_status("srv", docker_running=True, http_ok=False)
        assert r2 == HealthStatus.unreachable
        assert monitor._failure_counts["srv"] == 2

        # Third failure: still unreachable, counter keeps incrementing
        r3 = monitor._compute_status("srv", docker_running=True, http_ok=False)
        assert r3 == HealthStatus.unreachable
        assert monitor._failure_counts["srv"] == 3
