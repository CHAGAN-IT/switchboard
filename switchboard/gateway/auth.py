"""JWT authentication dependency for customer gateway endpoints.

Validates Bearer tokens using PyJWT with HS256 symmetric key.
The signing secret is loaded from the CUSTOMER_JWT_SECRET environment
variable via pydantic-settings.

Depends on: switchboard.config (get_settings, Settings)
"""

from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from switchboard.config import Settings, get_settings

_bearer_scheme = HTTPBearer(
    scheme_name="CustomerJWT",
    description="Customer JWT token (HS256)",
)


async def require_customer(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    """Validate customer JWT and return decoded payload.

    Uses HS256 symmetric key validation. The customer_jwt_secret
    is loaded from the CUSTOMER_JWT_SECRET environment variable
    via pydantic-settings.

    Args:
        credentials: Bearer token extracted by HTTPBearer.
        settings: Application settings with customer JWT secret.

    Returns:
        Decoded JWT payload as a dictionary.

    Raises:
        HTTPException: 401 with WWW-Authenticate: Bearer header
            if token is invalid, expired, or malformed.
    """
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.customer_jwt_secret,
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "sub"]},
            audience="switchboard-gateway",
            issuer="switchboard",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    return payload
