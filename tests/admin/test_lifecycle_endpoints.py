"""Integration tests for Admin API container lifecycle endpoints.

Tests all three CONT requirements:
- CONT-01: POST /api/v1/servers/{name}/start (start container)
- CONT-02: POST /api/v1/servers/{name}/stop (stop container)
- CONT-03: POST /api/v1/servers/{name}/restart (restart container)

Threat mitigations:
- T-3-07: All endpoints protected by require_operator JWT dependency.
- T-3-08: Error responses use generic {"detail": "..."} format.
- T-3-09: 409 Conflict prevents double-start and double-stop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from switchboard.container.exceptions import ContainerStartError
from switchboard.registry.models import ServerStatus

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from httpx import AsyncClient

    from switchboard.container.manager import ContainerManager


# Helper: register a server via the API and return the response data.
async def _register_server(
    client: AsyncClient,
    auth_headers: dict[str, str],
    name: str = "test-server",
    image: str = "switchboard/test:latest",
) -> dict:
    """Register a test server and return its API response payload."""
    response = await client.post(
        "/api/v1/servers",
        json={"name": name, "container_image": image},
        headers=auth_headers,
    )
    assert response.status_code == 201, f"Registration failed: {response.text}"
    return response.json()


@pytest.mark.asyncio
class TestStartServer:
    """Tests for POST /api/v1/servers/{name}/start (CONT-01)."""

    async def test_start_server_success(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        mock_container_manager: ContainerManager,
    ) -> None:
        """POST /start returns 200 with running status and container_id."""
        await _register_server(client, auth_headers, name="start-success")

        # Configure mock to simulate Docker start: update DB via repo
        async def mock_start(session, server, repo):  # noqa: ANN001, ARG001
            await repo.update_status(session, server.id, ServerStatus.running)
            await repo.update_container_id(session, server.id, "mock-cid-abc123")
            await session.flush()
            await session.refresh(server)
            return server

        mock_container_manager.start.side_effect = mock_start

        response = await client.post(
            "/api/v1/servers/start-success/start",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["container_id"] == "mock-cid-abc123"
        assert data["name"] == "start-success"

    async def test_start_server_not_found_404(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """POST /start for nonexistent server returns 404."""
        response = await client.post(
            "/api/v1/servers/nonexistent-server/start",
            headers=auth_headers,
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    async def test_start_server_already_running_409(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        mock_container_manager: ContainerManager,
    ) -> None:
        """POST /start when server is already running returns 409."""
        await _register_server(client, auth_headers, name="start-conflict")

        # First start: set to running state in DB
        async def mock_start(session, server, repo):  # noqa: ANN001, ARG001
            await repo.update_status(session, server.id, ServerStatus.running)
            await repo.update_container_id(session, server.id, "mock-cid-running")
            await session.flush()
            await session.refresh(server)
            return server

        mock_container_manager.start.side_effect = mock_start

        first = await client.post(
            "/api/v1/servers/start-conflict/start",
            headers=auth_headers,
        )
        assert first.status_code == 200

        # Second start: should be rejected as already running
        response = await client.post(
            "/api/v1/servers/start-conflict/start",
            headers=auth_headers,
        )
        assert response.status_code == 409
        assert "already running" in response.json()["detail"].lower()

    async def test_start_server_failure_500(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        mock_container_manager: ContainerManager,
    ) -> None:
        """POST /start returns 500 when ContainerManager.start raises."""
        await _register_server(client, auth_headers, name="start-failure")

        mock_container_manager.start.side_effect = ContainerStartError(
            "start-failure", "image not found"
        )

        response = await client.post(
            "/api/v1/servers/start-failure/start",
            headers=auth_headers,
        )
        assert response.status_code == 500
        detail = response.json()["detail"]
        assert "start-failure" in detail
        assert "image not found" in detail

    async def test_start_server_no_auth_401(
        self,
        unauthenticated_client: TestClient,
    ) -> None:
        """POST /start without Bearer token returns 401."""
        response = unauthenticated_client.post(
            "/api/v1/servers/any-server/start",
        )
        assert response.status_code in (401, 403)


@pytest.mark.asyncio
class TestStopServer:
    """Tests for POST /api/v1/servers/{name}/stop (CONT-02)."""

    async def test_stop_server_success(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        mock_container_manager: ContainerManager,
    ) -> None:
        """POST /stop returns 200 with stopped status and null container_id."""
        await _register_server(client, auth_headers, name="stop-success")

        # First start the server so it can be stopped
        async def mock_start(session, server, repo):  # noqa: ANN001, ARG001
            await repo.update_status(session, server.id, ServerStatus.running)
            await repo.update_container_id(session, server.id, "mock-cid-stop")
            await session.flush()
            await session.refresh(server)
            return server

        mock_container_manager.start.side_effect = mock_start

        start_resp = await client.post(
            "/api/v1/servers/stop-success/start",
            headers=auth_headers,
        )
        assert start_resp.status_code == 200

        # Now stop it
        async def mock_stop(session, server, repo):  # noqa: ANN001, ARG001
            await repo.update_status(session, server.id, ServerStatus.stopped)
            await repo.update_container_id(session, server.id, None)
            await session.flush()
            await session.refresh(server)
            return server

        mock_container_manager.stop.side_effect = mock_stop

        response = await client.post(
            "/api/v1/servers/stop-success/stop",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"
        assert data["container_id"] is None
        assert data["name"] == "stop-success"

    async def test_stop_server_not_found_404(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """POST /stop for nonexistent server returns 404."""
        response = await client.post(
            "/api/v1/servers/nonexistent-server/stop",
            headers=auth_headers,
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    async def test_stop_server_already_stopped_409(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """POST /stop when server is already stopped returns 409."""
        # Server starts in "stopped" state after registration
        await _register_server(client, auth_headers, name="stop-conflict")

        response = await client.post(
            "/api/v1/servers/stop-conflict/stop",
            headers=auth_headers,
        )
        assert response.status_code == 409
        assert "not running" in response.json()["detail"].lower()

    async def test_stop_server_no_auth_401(
        self,
        unauthenticated_client: TestClient,
    ) -> None:
        """POST /stop without Bearer token returns 401."""
        response = unauthenticated_client.post(
            "/api/v1/servers/any-server/stop",
        )
        assert response.status_code in (401, 403)


@pytest.mark.asyncio
class TestRestartServer:
    """Tests for POST /api/v1/servers/{name}/restart (CONT-03)."""

    async def test_restart_server_success(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        mock_container_manager: ContainerManager,
    ) -> None:
        """POST /restart returns 200 with running status and container_id."""
        await _register_server(client, auth_headers, name="restart-success")

        # Configure mock restart to simulate stop + start cycle
        async def mock_restart(session, server, repo):  # noqa: ANN001, ARG001
            await repo.update_status(session, server.id, ServerStatus.running)
            await repo.update_container_id(session, server.id, "mock-cid-restarted")
            await session.flush()
            await session.refresh(server)
            return server

        mock_container_manager.restart.side_effect = mock_restart

        response = await client.post(
            "/api/v1/servers/restart-success/restart",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["container_id"] == "mock-cid-restarted"
        assert data["name"] == "restart-success"

    async def test_restart_server_not_found_404(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """POST /restart for nonexistent server returns 404."""
        response = await client.post(
            "/api/v1/servers/nonexistent-server/restart",
            headers=auth_headers,
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    async def test_restart_server_no_auth_401(
        self,
        unauthenticated_client: TestClient,
    ) -> None:
        """POST /restart without Bearer token returns 401."""
        response = unauthenticated_client.post(
            "/api/v1/servers/any-server/restart",
        )
        assert response.status_code in (401, 403)
