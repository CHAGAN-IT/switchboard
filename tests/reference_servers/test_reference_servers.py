"""Integration tests for reference MCP servers.

Tests require:
- Docker daemon running
- switchboard-echo and switchboard-ping images built:
    docker compose build echo ping

Run selectively:
    uv run pytest tests/reference_servers/ -m reference_servers -x -q

REFS-01: Echo server returns input unchanged (D-04, SC-1)
REFS-02: Ping server responds to MCP protocol ping (D-04, SC-2)
SC-4:    ContainerManager can start/stop reference server images (SC-4)
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from switchboard.container.manager import ContainerManager
from switchboard.registry.models import ServerStatus


@pytest.mark.reference_servers
@pytest.mark.asyncio
async def test_echo_returns_input_unchanged(echo_server_url: str) -> None:
    """REFS-01: Echo tool returns the message argument unchanged.

    Sends a real MCP tool call to the running echo container via
    Streamable HTTP transport and asserts the response content matches
    the input exactly.
    """
    async with streamable_http_client(echo_server_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("echo", {"message": "hello world"})
            assert result.content[0].text == "hello world"


@pytest.mark.reference_servers
@pytest.mark.asyncio
async def test_echo_handles_different_messages(echo_server_url: str) -> None:
    """REFS-01 edge case: Echo returns arbitrary strings unchanged."""
    test_message = "switchboard-phase-4-validation-123"
    async with streamable_http_client(echo_server_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("echo", {"message": test_message})
            assert result.content[0].text == test_message


@pytest.mark.reference_servers
@pytest.mark.asyncio
async def test_ping_responds_to_mcp_ping(ping_server_url: str) -> None:
    """REFS-02: Ping server responds to the MCP protocol ping method.

    Sends session.send_ping() to the running ping container and asserts
    a valid EmptyResult is returned. The protocol ping is handled by the
    FastMCP/mcp SDK layer -- no application tool code is involved.
    """
    async with streamable_http_client(ping_server_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.send_ping()
            # send_ping() returns EmptyResult on success; raises on timeout/error.
            assert result is not None


@pytest.mark.reference_servers
@pytest.mark.asyncio
async def test_container_manager_lifecycle_echo() -> None:
    """SC-4: ContainerManager.start() and stop() work with the echo image.

    Verifies that the ContainerManager can start and stop the echo server
    using its standard lifecycle operations. Uses a mocked database session
    and repository -- only the Docker interaction is real.

    Requires: switchboard-echo image built and Docker daemon running.
    """
    manager = ContainerManager()

    # Build a minimal Server-like object that ContainerManager expects
    server_id = uuid.uuid4()
    mock_server = MagicMock()
    mock_server.id = server_id
    mock_server.container_image = "switchboard-echo"
    mock_server.status = ServerStatus.stopped
    mock_server.container_id = None

    # Use test-specific server name to avoid collision with sb-echo (docker-compose)
    # ContainerManager builds name as f"sb-{server.name}" = "sb-echo-lifecycle-test"
    mock_server.name = "echo-lifecycle-test"

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=mock_server)

    mock_repo = AsyncMock()

    async def _update_status(
        session: object,  # noqa: ARG001
        server_id: object,  # noqa: ARG001
        status: ServerStatus,
    ) -> MagicMock:
        mock_server.status = status
        return mock_server

    async def _update_container_id(
        session: object,  # noqa: ARG001
        server_id: object,  # noqa: ARG001
        container_id: str | None,
    ) -> MagicMock:
        mock_server.container_id = container_id
        return mock_server

    mock_repo.update_status = AsyncMock(side_effect=_update_status)
    mock_repo.update_container_id = AsyncMock(side_effect=_update_container_id)

    # Start the container
    updated = await manager.start(mock_session, mock_server, mock_repo)
    assert updated.status == ServerStatus.running
    assert updated.container_id is not None

    # Stop the container
    await manager.stop(mock_session, updated, mock_repo)
    assert mock_server.status == ServerStatus.stopped
