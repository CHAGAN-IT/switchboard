"""Async session factory for database access."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from switchboard.db.engine import create_engine

# Module-level engine and session factory.
# Created once; reused across all requests.
engine = create_engine()
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session for dependency injection.

    Used by FastAPI Depends() in Phase 2. Tests pass sessions directly
    via the transaction-rollback fixture.
    """
    async with async_session_factory() as session:
        yield session
