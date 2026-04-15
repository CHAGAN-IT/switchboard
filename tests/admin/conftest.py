"""Shared fixtures for Admin API tests.

Provides:
- make_operator_token helper for generating test JWTs.
- auth_headers fixture with a valid operator token.
- client fixture (async) with dependency overrides for session and settings.
- unauthenticated_client fixture for testing auth rejection paths.

Uses httpx.AsyncClient + ASGITransport for async tests that need
DB access, and sync TestClient for auth-rejection tests that never
reach the DB layer.

Depends on: switchboard.admin.app, switchboard.config, switchboard.db.session
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import jwt
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from switchboard.admin.app import app
from switchboard.config import Settings, get_settings
from switchboard.db.session import get_session

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator

    from sqlalchemy.ext.asyncio import AsyncSession

TEST_JWT_SECRET = "test-secret-key-minimum-32-bytes-long!"
TEST_ALGORITHM = "HS256"


def make_operator_token(
    *,
    sub: str = "test-operator",
    exp_delta: timedelta | None = None,
    expired: bool = False,
) -> str:
    """Generate a signed operator JWT for testing.

    Args:
        sub: Subject claim value.
        exp_delta: Custom expiration delta from now.
        expired: If True, set expiration 1 hour in the past.

    Returns:
        Encoded JWT string.
    """
    now = datetime.now(tz=UTC)
    if expired:
        exp = now - timedelta(hours=1)
    elif exp_delta is not None:
        exp = now + exp_delta
    else:
        exp = now + timedelta(hours=1)
    payload = {"sub": sub, "exp": exp, "iat": now}
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm=TEST_ALGORITHM)


def _override_settings() -> Settings:
    """Return Settings with known test JWT secret."""
    return Settings(
        operator_jwt_secret=TEST_JWT_SECRET,
        database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/switchboard",
        test_database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/switchboard_test",
    )


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Authorization headers with a valid operator JWT."""
    token = make_operator_token()
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client with DB session and settings overrides.

    Uses httpx.AsyncClient + ASGITransport so that the test session
    (created by pytest-asyncio) runs in the same event loop as the
    ASGI app. This avoids the 'attached to a different loop' error
    that occurs with sync TestClient + async DB sessions.

    Real JWT auth runs (require_operator is NOT overridden).
    """

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = _override_settings

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def unauthenticated_client() -> Generator[TestClient, None, None]:
    """Sync TestClient for testing auth rejection paths.

    Overrides get_settings so JWT secret is known for valid-token tests,
    but does NOT override get_session (auth-rejection responses never
    reach the DB layer). Does NOT bypass require_operator.
    """
    app.dependency_overrides[get_settings] = _override_settings

    yield TestClient(app, raise_server_exceptions=False)

    app.dependency_overrides.clear()
