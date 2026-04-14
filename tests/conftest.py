"""Shared test fixtures for Switchboard integration tests.

Provides:
- Session-scoped async engine connected to the test database.
- Session-scoped migration fixture that applies Alembic migrations once.
- Per-test async session with transaction rollback for isolation.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)

from switchboard.config import get_settings

# Project root for running Alembic commands
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)


@pytest.fixture(scope="session")
def _apply_migrations() -> None:
    """Apply Alembic migrations once per test session.

    Uses subprocess to avoid event loop conflicts between Alembic's
    synchronous runner and pytest-asyncio's event loop. Sets DATABASE_URL
    so alembic/env.py picks up the test database URL.
    """
    settings = get_settings()
    # Convert async URL to sync for Alembic commands
    sync_url = settings.test_database_url.replace("+asyncpg", "")

    env = {**os.environ, "DATABASE_URL": sync_url}

    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        env=env,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"Alembic upgrade failed:\nstdout: {result.stdout}\nstderr: {result.stderr}")

    yield  # type: ignore[misc]

    subprocess.run(
        ["uv", "run", "alembic", "downgrade", "base"],
        env=env,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=False,
    )


@pytest_asyncio.fixture(scope="session")
async def engine(_apply_migrations: None):
    """Create a session-scoped async engine for the test database."""
    settings = get_settings()
    _engine = create_async_engine(
        settings.test_database_url,
        echo=False,
    )
    yield _engine
    await _engine.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Per-test async session with transaction rollback.

    Each test runs inside a transaction that is rolled back after
    completion, providing full isolation without disk writes.

    Uses join_transaction_mode="create_savepoint" so that flush()
    inside repository methods works correctly within the outer
    transaction boundary.
    """
    async with engine.connect() as connection:
        async with connection.begin() as transaction:
            async_session = AsyncSession(
                bind=connection,
                join_transaction_mode="create_savepoint",
                expire_on_commit=False,
            )
            yield async_session
            await transaction.rollback()
