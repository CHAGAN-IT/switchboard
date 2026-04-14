"""Integration tests for ServerRepository against real PostgreSQL.

All tests use the session fixture from conftest.py which provides
per-test transaction rollback isolation.

Prerequisites: PostgreSQL must be running (docker compose up).
"""

from __future__ import annotations

import uuid

import pytest

from switchboard.registry.exceptions import DuplicateServerError
from switchboard.registry.models import ServerStatus
from switchboard.registry.repository import ServerRepository


@pytest.fixture
def repo() -> ServerRepository:
    """Provide a ServerRepository instance."""
    return ServerRepository()


@pytest.mark.integration
async def test_create_server(session, repo: ServerRepository) -> None:
    """create() inserts a server with UUID and status=stopped."""
    server = await repo.create(
        session,
        name="test-server",
        container_image="nginx:latest",
        description="A test server",
    )
    assert server.id is not None
    assert isinstance(server.id, uuid.UUID)
    assert server.name == "test-server"
    assert server.container_image == "nginx:latest"
    assert server.description == "A test server"
    assert server.status == ServerStatus.stopped
    assert server.container_id is None
    assert server.created_at is not None
    assert server.updated_at is not None


@pytest.mark.integration
async def test_create_server_duplicate_name(
    session, repo: ServerRepository
) -> None:
    """create() raises DuplicateServerError for duplicate name."""
    await repo.create(
        session, name="dupe-server", container_image="img:v1"
    )
    with pytest.raises(DuplicateServerError, match="dupe-server"):
        await repo.create(
            session, name="dupe-server", container_image="img:v2"
        )


@pytest.mark.integration
async def test_get_by_name_existing(
    session, repo: ServerRepository
) -> None:
    """get_by_name() returns the correct server."""
    created = await repo.create(
        session, name="find-me", container_image="img:latest"
    )
    found = await repo.get_by_name(session, "find-me")
    assert found is not None
    assert found.id == created.id
    assert found.name == "find-me"


@pytest.mark.integration
async def test_get_by_name_nonexistent(
    session, repo: ServerRepository
) -> None:
    """get_by_name() returns None for nonexistent name."""
    result = await repo.get_by_name(session, "no-such-server")
    assert result is None


@pytest.mark.integration
async def test_get_by_id_existing(
    session, repo: ServerRepository
) -> None:
    """get_by_id() returns the correct server."""
    created = await repo.create(
        session, name="id-lookup", container_image="img:latest"
    )
    found = await repo.get_by_id(session, created.id)
    assert found is not None
    assert found.name == "id-lookup"


@pytest.mark.integration
async def test_get_by_id_nonexistent(
    session, repo: ServerRepository
) -> None:
    """get_by_id() returns None for nonexistent UUID."""
    result = await repo.get_by_id(session, uuid.uuid4())
    assert result is None


@pytest.mark.integration
async def test_list_all_returns_servers(
    session, repo: ServerRepository
) -> None:
    """list_all() returns all servers in descending created_at order."""
    await repo.create(
        session, name="server-aaa", container_image="img:v1"
    )
    await repo.create(
        session, name="server-bbb", container_image="img:v2"
    )
    servers = await repo.list_all(session)
    assert len(servers) >= 2
    names = [s.name for s in servers]
    assert "server-aaa" in names
    assert "server-bbb" in names
    # Verify ordering: most recent first
    if len(servers) == 2:
        assert servers[0].name == "server-bbb"
        assert servers[1].name == "server-aaa"


@pytest.mark.integration
async def test_list_all_empty(
    session, repo: ServerRepository
) -> None:
    """list_all() returns empty list when no servers exist."""
    servers = await repo.list_all(session)
    assert isinstance(servers, list)
    assert len(servers) == 0


@pytest.mark.integration
async def test_update_status(
    session, repo: ServerRepository
) -> None:
    """update_status() changes the server status."""
    created = await repo.create(
        session, name="status-test", container_image="img:latest"
    )
    assert created.status == ServerStatus.stopped

    updated = await repo.update_status(
        session, created.id, ServerStatus.running
    )
    assert updated is not None
    assert updated.status == ServerStatus.running


@pytest.mark.integration
async def test_update_status_nonexistent(
    session, repo: ServerRepository
) -> None:
    """update_status() returns None for nonexistent server."""
    result = await repo.update_status(
        session, uuid.uuid4(), ServerStatus.running
    )
    assert result is None


@pytest.mark.integration
async def test_update_container_id_set(
    session, repo: ServerRepository
) -> None:
    """update_container_id() sets the container_id field."""
    created = await repo.create(
        session, name="container-test", container_image="img:latest"
    )
    updated = await repo.update_container_id(
        session, created.id, "abc123def456"
    )
    assert updated is not None
    assert updated.container_id == "abc123def456"


@pytest.mark.integration
async def test_update_container_id_clear(
    session, repo: ServerRepository
) -> None:
    """update_container_id() clears container_id when passed None."""
    created = await repo.create(
        session, name="clear-container", container_image="img:latest"
    )
    await repo.update_container_id(session, created.id, "some-id")
    cleared = await repo.update_container_id(session, created.id, None)
    assert cleared is not None
    assert cleared.container_id is None


@pytest.mark.integration
async def test_delete_existing(
    session, repo: ServerRepository
) -> None:
    """delete() removes a server and returns True."""
    created = await repo.create(
        session, name="delete-me", container_image="img:latest"
    )
    result = await repo.delete(session, created.id)
    assert result is True

    found = await repo.get_by_id(session, created.id)
    assert found is None


@pytest.mark.integration
async def test_delete_nonexistent(
    session, repo: ServerRepository
) -> None:
    """delete() returns False for nonexistent server."""
    result = await repo.delete(session, uuid.uuid4())
    assert result is False
