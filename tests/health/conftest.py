"""Shared fixtures for health monitor unit tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_docker_client() -> MagicMock:
    """Mocked Docker SDK client for inspect calls."""
    client = MagicMock()
    container = MagicMock()
    container.status = "running"
    client.containers.get.return_value = container
    return client


@pytest.fixture
def mock_httpx_client() -> AsyncMock:
    """Mocked httpx.AsyncClient for HTTP probes."""
    client = AsyncMock()
    response = MagicMock()
    response.status_code = 200
    client.post = AsyncMock(return_value=response)
    return client


@pytest.fixture
def mock_session_factory() -> MagicMock:
    """Mocked async_session_factory that returns a context-managed session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)

    return factory
