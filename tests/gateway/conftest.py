"""Shared fixtures for Gateway tests.

Provides:
- make_customer_token helper for generating test customer JWTs.
- customer_auth_headers fixture with a valid customer token.

Depends on: PyJWT
"""

from __future__ import annotations

import time

import jwt
import pytest

# Must match CUSTOMER_JWT_SECRET set in tests/conftest.py
CUSTOMER_JWT_SECRET = "pytest-customer-secret-32bytes!!"


def make_customer_token(
    sub: str = "user-123",
    *,
    secret: str = CUSTOMER_JWT_SECRET,
    audience: str = "switchboard-gateway",
    extra_claims: dict | None = None,
) -> str:
    """Generate a signed customer JWT for testing.

    Args:
        sub: Subject claim value (user identifier).
        secret: HMAC signing secret. Defaults to the test secret.
        audience: Token audience claim. Defaults to "switchboard-gateway".
        extra_claims: Additional claims to include in the payload.

    Returns:
        Encoded JWT string.

    Example:
        >>> token = make_customer_token("user-456")
        >>> import jwt
        >>> payload = jwt.decode(token, CUSTOMER_JWT_SECRET, algorithms=["HS256"],
        ...     audience="switchboard-gateway", options={"verify_exp": False})
        >>> payload["sub"]
        'user-456'
    """
    now = time.time()
    payload: dict = {
        "sub": sub,
        "exp": now + 3600,
        "iat": now,
        "aud": audience,
        "iss": "switchboard",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture
def customer_auth_headers() -> dict[str, str]:
    """Authorization headers with a valid customer JWT.

    Returns:
        Dictionary with Authorization header containing a Bearer token.
    """
    return {"Authorization": f"Bearer {make_customer_token()}"}
