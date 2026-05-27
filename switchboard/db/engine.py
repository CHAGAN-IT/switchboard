"""Async SQLAlchemy engine factory."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from switchboard.config import get_settings


def create_engine() -> AsyncEngine:
    """Create the async SQLAlchemy engine.

    Uses postgresql+asyncpg:// driver. Never use plain postgresql://
    which silently uses the sync driver and blocks the event loop.
    """
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=settings.db_echo,
        pool_size=5,
        max_overflow=10,
    )
