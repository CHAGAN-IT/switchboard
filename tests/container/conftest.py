"""Shared fixtures for ContainerManager unit tests.

Provides mocked Docker SDK client, server ORM instance, async session,
and repository -- all tests run without a real Docker daemon or database.

Depends on: switchboard.registry.models (ServerStatus enum)
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from switchboard.registry.models import ServerStatus


@pytest.fixture
def mock_docker_client() -> MagicMock:
    """Simulated docker.from_env() client.

    Configured as a context manager so ``with docker.from_env() as client:``
    works in production code. The containers.run() return value mimics a
    Docker Container object with .id and .status attributes.
    """
    client = MagicMock()

    # Make client usable as a context manager
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)

    # Default container returned by containers.run() and containers.get()
    container = MagicMock()
    container.id = "abc123container"
    container.status = "running"
    container.reload = MagicMock()

    client.containers.run.return_value = container
    client.containers.get.return_value = container

    # Network exists by default
    client.networks.get.return_value = MagicMock()

    return client


@pytest.fixture
def mock_server() -> MagicMock:
    """Simulated Server ORM instance in stopped state."""
    server = MagicMock()
    server.id = uuid.uuid4()
    server.name = "echo-server"
    server.container_image = "switchboard/echo:latest"
    server.status = ServerStatus.stopped
    server.container_id = None
    return server


@pytest.fixture
def mock_session() -> AsyncMock:
    """Simulated AsyncSession.

    Provides async no-op stubs for flush, refresh, commit, and get.
    """
    session = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()
    session.get = AsyncMock(return_value=None)
    return session


@pytest.fixture
def mock_repo(mock_server: MagicMock) -> AsyncMock:
    """Simulated ServerRepository.

    update_status and update_container_id return the mock_server after
    updating its attributes to reflect the requested change.
    """
    repo = AsyncMock()

    async def _update_status(session, server_id, status):  # noqa: ANN001, ARG001
        mock_server.status = status
        return mock_server

    async def _update_container_id(session, server_id, container_id):  # noqa: ANN001, ARG001
        mock_server.container_id = container_id
        return mock_server

    repo.update_status = AsyncMock(side_effect=_update_status)
    repo.update_container_id = AsyncMock(side_effect=_update_container_id)

    return repo
