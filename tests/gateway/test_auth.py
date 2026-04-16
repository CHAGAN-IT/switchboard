"""Unit tests for the require_customer FastAPI dependency.

Uses a minimal FastAPI TestClient with a protected route that depends
on require_customer. Tests run without a real gateway app — only the
authentication dependency is exercised.

Covers SECU-01: Customer JWT validation for gateway endpoints.
"""

from __future__ import annotations

import time

import jwt
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from switchboard.gateway.auth import require_customer

from .conftest import CUSTOMER_JWT_SECRET, make_customer_token

# Minimal test app that depends on require_customer for a single route.
# Constructed at module level so the TestClient is shared across tests
# for performance (auth tests never touch the DB).
_test_app = FastAPI()


@_test_app.get("/protected")
async def _protected(payload: dict = Depends(require_customer)) -> dict:  # noqa: B008
    """Return subject claim from validated token."""
    return {"sub": payload["sub"]}


client = TestClient(_test_app, raise_server_exceptions=False)


def test_missing_jwt_returns_401() -> None:
    """Request without Authorization header → 401 with WWW-Authenticate: Bearer."""
    response = client.get("/protected")
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


def test_wrong_secret_returns_401() -> None:
    """Token signed with incorrect secret returns 401."""
    wrong_secret = "wrong-secret-xxxxxxxxxxxxxxxxxx"
    token = make_customer_token(secret=wrong_secret)
    response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_wrong_audience_returns_401() -> None:
    """Operator-audience token (switchboard-admin) returns 401 at gateway endpoint."""
    token = make_customer_token(audience="switchboard-admin")
    response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_missing_sub_claim_returns_401() -> None:
    """Token missing required 'sub' claim returns 401."""
    now = time.time()
    payload = {
        "exp": now + 3600,
        "iat": now,
        "aud": "switchboard-gateway",
        "iss": "switchboard",
        # 'sub' deliberately omitted
    }
    token = jwt.encode(payload, CUSTOMER_JWT_SECRET, algorithm="HS256")
    response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_valid_token_accepted() -> None:
    """Valid HS256 token with correct audience and required claims returns 200."""
    token = make_customer_token()
    response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {"sub": "user-123"}


def test_expired_token_returns_401() -> None:
    """Token with exp in the past returns 401."""
    now = time.time()
    payload = {
        "sub": "user-123",
        "exp": now - 1,  # Already expired
        "iat": now - 3601,
        "aud": "switchboard-gateway",
        "iss": "switchboard",
    }
    token = jwt.encode(payload, CUSTOMER_JWT_SECRET, algorithm="HS256")
    response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
