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
        """Enforce minimum 32-byte JWT secret per RFC 7518 Section 3.2.

        Empty string is allowed as a default for development. When a value
        is explicitly set, it must be at least 32 bytes to resist brute-force.
        """
        if v and len(v.encode()) < 32:
            msg = "OPERATOR_JWT_SECRET must be at least 32 bytes"
            raise ValueError(msg)
        return v


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance.

    Uses lru_cache so settings are read once and reused.
    Call get_settings.cache_clear() in tests if needed.
    """
    return Settings()
