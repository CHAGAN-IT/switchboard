"""JWT authentication dependency unit tests.

Verifies that the require_operator dependency correctly rejects
missing, invalid, and expired tokens (401) and passes valid tokens.

Threat mitigations:
- T-2-07: Missing/invalid/expired tokens return 401.
- T-2-08: Error messages are generic, not leaking JWT internals.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.admin.conftest import make_operator_token

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from httpx import AsyncClient


def test_missing_token_401(unauthenticated_client: TestClient) -> None:
    """Request without Authorization header returns 401 with WWW-Authenticate."""
    response = unauthenticated_client.get("/api/v1/servers")
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_invalid_token_401(unauthenticated_client: TestClient) -> None:
    """Request with invalid Bearer token returns 401."""
    response = unauthenticated_client.get(
        "/api/v1/servers",
        headers={"Authorization": "Bearer invalid-garbage-token"},
    )
    assert response.status_code == 401
    assert "Could not validate credentials" in response.json()["detail"]


def test_expired_token_401(unauthenticated_client: TestClient) -> None:
    """Request with expired JWT returns 401 with expiration detail."""
    token = make_operator_token(expired=True)
    response = unauthenticated_client.get(
        "/api/v1/servers",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_valid_token_succeeds(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Request with valid JWT passes authentication and returns 200."""
    response = await client.get("/api/v1/servers", headers=auth_headers)
    # 200 means auth passed (returns empty server list)
    assert response.status_code == 200
