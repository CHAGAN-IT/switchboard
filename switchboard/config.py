"""Application configuration via environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Reads from .env file if present. All values can be overridden
    via environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Database
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/switchboard"
    )
    test_database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/switchboard_test"
    )
    db_echo: bool = False

    # Auth
    operator_jwt_secret: str = ""

    @field_validator("operator_jwt_secret")
    @classmethod
    def validate_jwt_secret_length(cls, v: str) -> str:
        """Enforce non-empty JWT secret with minimum 32-byte length per RFC 7518 §3.2.

        An empty or missing OPERATOR_JWT_SECRET environment variable will
        cause the application to fail at startup rather than boot with an
        insecure empty HMAC key.
        """
        if not v:
            raise ValueError(
                "OPERATOR_JWT_SECRET environment variable is required and must not be empty"
            )
        if len(v.encode()) < 32:
            msg = "OPERATOR_JWT_SECRET must be at least 32 bytes"
            raise ValueError(msg)
        return v

    # Health monitor
    health_poll_interval: int = 30

    @field_validator("health_poll_interval")
    @classmethod
    def validate_poll_interval(cls, v: int) -> int:
        """Enforce minimum 5-second poll interval to prevent resource exhaustion."""
        if v < 5:
            msg = "HEALTH_POLL_INTERVAL must be at least 5 seconds"
            raise ValueError(msg)
        return v

    # Gateway-only: validated at startup in switchboard.gateway.app lifespan
    customer_jwt_secret: str = ""

    @field_validator("customer_jwt_secret")
    @classmethod
    def validate_customer_jwt_secret_length(cls, v: str) -> str:
        """Enforce minimum 32-byte length when a customer JWT secret is provided.

        An empty value is allowed here so the admin-api can start without
        CUSTOMER_JWT_SECRET. The gateway validates non-empty at startup via
        its lifespan function.
        """
        if v and len(v.encode()) < 32:
            msg = "CUSTOMER_JWT_SECRET must be at least 32 bytes when set"
            raise ValueError(msg)
        return v


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance.

    Uses lru_cache so settings are read once and reused.
    Call get_settings.cache_clear() in tests if needed.
    """
    return Settings()
