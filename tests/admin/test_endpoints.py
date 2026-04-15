"""Endpoint integration tests for Admin API server registration.

Tests all three SREG requirements:
- SREG-01: POST /api/v1/servers (register server)
- SREG-02: GET /api/v1/servers (list servers)
- SREG-03: GET /api/v1/servers/{name} (get server by name)

Plus OpenAPI docs smoke test and validation edge cases.

Threat mitigations:
- T-2-09: All endpoint tests use auth_headers -- verifies endpoints
  are not accidentally accessible without auth.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.asyncio
class TestRegisterServer:
    """Tests for POST /api/v1/servers (SREG-01)."""

    async def test_register_server_success(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Valid payload returns 201 with complete server record."""
        response = await client.post(
            "/api/v1/servers",
            json={
                "name": "echo-server",
                "container_image": "switchboard/echo:latest",
                "description": "Echo MCP server",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "echo-server"
        assert data["container_image"] == "switchboard/echo:latest"
        assert data["description"] == "Echo MCP server"
        assert data["status"] == "stopped"
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    async def test_register_server_duplicate_409(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Duplicate server name returns 409 Conflict (D-03)."""
        payload = {
            "name": "duplicate-test",
            "container_image": "switchboard/test:latest",
        }
        # First registration succeeds
        first = await client.post(
            "/api/v1/servers", json=payload, headers=auth_headers
        )
        assert first.status_code == 201

        # Second registration with same name returns 409
        second = await client.post(
            "/api/v1/servers", json=payload, headers=auth_headers
        )
        assert second.status_code == 409
        assert "already exists" in second.json()["detail"]

    async def test_register_server_invalid_name_422(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Invalid server name returns 422 (name validation from D-08)."""
        response = await client.post(
            "/api/v1/servers",
            json={
                "name": "A",
                "container_image": "switchboard/test:latest",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_register_server_empty_description_422(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Empty description string returns 422 (D-05)."""
        response = await client.post(
            "/api/v1/servers",
            json={
                "name": "empty-desc-test",
                "container_image": "switchboard/test:latest",
                "description": "",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_register_server_null_description_ok(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Null description is accepted (D-05 allows None)."""
        response = await client.post(
            "/api/v1/servers",
            json={
                "name": "null-desc-test",
                "container_image": "switchboard/test:latest",
                "description": None,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        assert response.json()["description"] is None


@pytest.mark.asyncio
class TestListServers:
    """Tests for GET /api/v1/servers (SREG-02)."""

    async def test_list_servers(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Returns all registered servers."""
        # Create 2 servers
        for name in ("list-server-aaa", "list-server-bbb"):
            resp = await client.post(
                "/api/v1/servers",
                json={"name": name, "container_image": f"img/{name}:latest"},
                headers=auth_headers,
            )
            assert resp.status_code == 201

        # List all
        response = await client.get("/api/v1/servers", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        names = {s["name"] for s in data}
        assert "list-server-aaa" in names
        assert "list-server-bbb" in names

    async def test_list_servers_empty(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Returns empty list when no servers registered."""
        response = await client.get("/api/v1/servers", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []


@pytest.mark.asyncio
class TestGetServer:
    """Tests for GET /api/v1/servers/{name} (SREG-03)."""

    async def test_get_server_by_name(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Returns server details for a registered server."""
        # Create server first
        await client.post(
            "/api/v1/servers",
            json={
                "name": "detail-test",
                "container_image": "switchboard/detail:latest",
                "description": "Detail test server",
            },
            headers=auth_headers,
        )

        # Retrieve by name
        response = await client.get(
            "/api/v1/servers/detail-test", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "detail-test"
        assert data["container_image"] == "switchboard/detail:latest"
        assert data["description"] == "Detail test server"

    async def test_get_server_not_found_404(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Returns 404 for nonexistent server name."""
        response = await client.get(
            "/api/v1/servers/nonexistent-server", headers=auth_headers
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


@pytest.mark.asyncio
class TestOpenAPI:
    """Smoke test for OpenAPI documentation."""

    async def test_openapi_docs_accessible(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """OpenAPI docs page at /docs is accessible."""
        response = await client.get("/docs")
        assert response.status_code == 200
