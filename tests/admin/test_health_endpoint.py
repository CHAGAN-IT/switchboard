"""Integration tests for health_status in Admin API responses.

Verifies that CONT-04 is satisfied: health_status appears in
GET /servers and GET /servers/{name} responses.

Uses the same test fixtures as test_endpoints.py (client, auth_headers,
session from conftest.py).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from switchboard.registry.models import HealthStatus

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
class TestHealthStatusInResponses:
    """Verify health_status field in Admin API responses (CONT-04)."""

    async def test_get_server_returns_null_health_status_for_new_server(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Newly registered server has health_status: null (D-08)."""
        # Register a server
        await client.post(
            "/api/v1/servers",
            json={
                "name": "health-test-01",
                "container_image": "switchboard/echo:latest",
            },
            headers=auth_headers,
        )
        # Get server detail
        response = await client.get(
            "/api/v1/servers/health-test-01",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "health_status" in data
        assert data["health_status"] is None

    async def test_list_servers_includes_health_status(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """GET /servers list includes health_status for each server."""
        await client.post(
            "/api/v1/servers",
            json={
                "name": "health-test-02",
                "container_image": "switchboard/echo:latest",
            },
            headers=auth_headers,
        )
        response = await client.get(
            "/api/v1/servers",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
        for server in data:
            assert "health_status" in server

    async def test_get_server_returns_health_status_value_when_set(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        session: AsyncSession,
    ) -> None:
        """After health_status is set on ORM, API returns the string value."""
        from sqlalchemy import select

        from switchboard.registry.models import Server

        # Register a server
        await client.post(
            "/api/v1/servers",
            json={
                "name": "health-test-03",
                "container_image": "switchboard/echo:latest",
            },
            headers=auth_headers,
        )
        # Directly set health_status on the ORM object (simulating a poll)
        stmt = select(Server).where(Server.name == "health-test-03")
        result = await session.execute(stmt)
        server = result.scalar_one()
        server.health_status = HealthStatus.healthy
        await session.flush()

        # Verify API returns the value
        response = await client.get(
            "/api/v1/servers/health-test-03",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["health_status"] == "healthy"
