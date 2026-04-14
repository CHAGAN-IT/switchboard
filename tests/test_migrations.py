"""Test Alembic migration cycle (upgrade + downgrade).

Verifies that migrations apply cleanly on a fresh database
and roll back without errors. This test runs independently
of the conftest migration fixture.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from switchboard.config import get_settings

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)


@pytest.mark.integration
def test_migrations_upgrade_downgrade() -> None:
    """Alembic upgrade to head then downgrade to base succeeds.

    Uses subprocess to avoid event loop conflicts.
    Tests against the test database.
    """
    settings = get_settings()
    sync_url = settings.test_database_url.replace("+asyncpg", "")

    env = {**os.environ, "DATABASE_URL": sync_url}

    # Downgrade first to ensure clean state
    subprocess.run(
        ["uv", "run", "alembic", "downgrade", "base"],
        env=env,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=False,
    )

    # Upgrade to head
    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        env=env,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=False,
    )
    assert result.returncode == 0, (
        f"Upgrade failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )

    # Downgrade to base
    result = subprocess.run(
        ["uv", "run", "alembic", "downgrade", "base"],
        env=env,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=False,
    )
    assert result.returncode == 0, (
        f"Downgrade failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )

    # Upgrade again to verify clean round-trip (catches enum type leak)
    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        env=env,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=False,
    )
    assert result.returncode == 0, (
        f"Re-upgrade failed (enum type not cleaned up on downgrade?):\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
