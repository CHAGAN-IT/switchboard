"""Unit tests for the unauthenticated /health endpoint on the admin API.

Verifies PLAT-02: the admin-api ECS task can reach healthy state by
hitting GET /health without JWT authentication.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.testclient import TestClient


class TestHealthEndpoint:
    """Tests for GET /health (unauthenticated, outside /api/v1 router)."""

    def test_health_returns_200_ok(self, unauthenticated_client: TestClient) -> None:
        """GET /health returns 200 with {"status": "ok"}."""
        response = unauthenticated_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_no_auth_required(self, unauthenticated_client: TestClient) -> None:
        """GET /health succeeds without Authorization header."""
        response = unauthenticated_client.get("/health")
        assert response.status_code == 200
        # Confirm no auth was needed (not 401/403)
        assert "WWW-Authenticate" not in response.headers

    def test_health_response_minimal(self, unauthenticated_client: TestClient) -> None:
        """GET /health returns only status key -- no version/config/debug."""
        response = unauthenticated_client.get("/health")
        data = response.json()
        assert set(data.keys()) == {"status"}
        assert data["status"] == "ok"
