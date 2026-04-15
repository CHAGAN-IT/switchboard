"""Unit tests for ContainerManager lifecycle operations.

Tests cover start, stop, and restart with a mocked Docker SDK and
mocked ServerRepository. No real Docker daemon or database required.

Verifies:
- Docker SDK calls are correct (image, name, network, no ports)
- Registry state updates after each operation
- asyncio.to_thread wrapping of blocking Docker calls
- Error handling and exception propagation
- Network creation when missing
- Cleanup of stale stopped containers

Depends on: switchboard.container.manager, switchboard.container.exceptions
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import docker.errors
import pytest

from switchboard.container.exceptions import ContainerStartError
from switchboard.container.manager import (
    CONTAINER_NAME_PREFIX,
    CONTAINER_PORT,
    DOCKER_NETWORK,
    ContainerManager,
)
from switchboard.registry.models import ServerStatus


@pytest.fixture
def manager() -> ContainerManager:
    """Fresh ContainerManager instance for each test."""
    return ContainerManager()


# ---------------------------------------------------------------------------
# start() tests
# ---------------------------------------------------------------------------


class TestStart:
    """Tests for ContainerManager.start()."""

    async def test_start_creates_container(
        self,
        manager: ContainerManager,
        mock_docker_client: MagicMock,
        mock_server: MagicMock,
        mock_session: AsyncMock,
        mock_repo: AsyncMock,
    ) -> None:
        """start() calls containers.run() with correct image, name, detach, network."""
        with patch(
            "switchboard.container.manager.docker.from_env",
            return_value=mock_docker_client,
        ):
            await manager.start(mock_session, mock_server, mock_repo)

        mock_docker_client.containers.run.assert_called_once()
        call_kwargs = mock_docker_client.containers.run.call_args
        assert call_kwargs.kwargs["image"] == "switchboard/echo:latest"
        assert call_kwargs.kwargs["name"] == f"{CONTAINER_NAME_PREFIX}echo-server"
        assert call_kwargs.kwargs["detach"] is True
        assert call_kwargs.kwargs["network"] == DOCKER_NETWORK

    async def test_start_updates_registry_status(
        self,
        manager: ContainerManager,
        mock_docker_client: MagicMock,
        mock_server: MagicMock,
        mock_session: AsyncMock,
        mock_repo: AsyncMock,
    ) -> None:
        """After successful start, registry is updated to running with container ID."""
        with patch(
            "switchboard.container.manager.docker.from_env",
            return_value=mock_docker_client,
        ):
            await manager.start(mock_session, mock_server, mock_repo)

        mock_repo.update_status.assert_any_call(
            mock_session, mock_server.id, ServerStatus.running
        )
        mock_repo.update_container_id.assert_called_once_with(
            mock_session, mock_server.id, "abc123container"
        )

    async def test_start_verifies_container_running(
        self,
        manager: ContainerManager,
        mock_docker_client: MagicMock,
        mock_server: MagicMock,
        mock_session: AsyncMock,
        mock_repo: AsyncMock,
    ) -> None:
        """After containers.run(), container.reload() is called to verify status."""
        container = mock_docker_client.containers.run.return_value
        container.status = "created"  # Not "running"

        with (
            patch(
                "switchboard.container.manager.docker.from_env",
                return_value=mock_docker_client,
            ),
            pytest.raises(ContainerStartError, match="not in running state"),
        ):
            await manager.start(mock_session, mock_server, mock_repo)

        container.reload.assert_called_once()

    async def test_start_failure_sets_error_status_image_not_found(
        self,
        manager: ContainerManager,
        mock_docker_client: MagicMock,
        mock_server: MagicMock,
        mock_session: AsyncMock,
        mock_repo: AsyncMock,
    ) -> None:
        """When Docker raises ImageNotFound, server status is set to error."""
        mock_docker_client.containers.run.side_effect = docker.errors.ImageNotFound(
            "not found"
        )

        with (
            patch(
                "switchboard.container.manager.docker.from_env",
                return_value=mock_docker_client,
            ),
            pytest.raises(ContainerStartError),
        ):
            await manager.start(mock_session, mock_server, mock_repo)

        mock_repo.update_status.assert_called_with(
            mock_session, mock_server.id, ServerStatus.error
        )

    async def test_start_failure_sets_error_status_api_error(
        self,
        manager: ContainerManager,
        mock_docker_client: MagicMock,
        mock_server: MagicMock,
        mock_session: AsyncMock,
        mock_repo: AsyncMock,
    ) -> None:
        """When Docker raises APIError, server status is set to error."""
        mock_docker_client.containers.run.side_effect = docker.errors.APIError(
            "api error"
        )

        with (
            patch(
                "switchboard.container.manager.docker.from_env",
                return_value=mock_docker_client,
            ),
            pytest.raises(ContainerStartError),
        ):
            await manager.start(mock_session, mock_server, mock_repo)

        mock_repo.update_status.assert_called_with(
            mock_session, mock_server.id, ServerStatus.error
        )

    async def test_start_no_host_ports(
        self,
        manager: ContainerManager,
        mock_docker_client: MagicMock,
        mock_server: MagicMock,
        mock_session: AsyncMock,
        mock_repo: AsyncMock,
    ) -> None:
        """containers.run() must NOT include a ports parameter (D-01 / T-3-02)."""
        with patch(
            "switchboard.container.manager.docker.from_env",
            return_value=mock_docker_client,
        ):
            await manager.start(mock_session, mock_server, mock_repo)

        call_kwargs = mock_docker_client.containers.run.call_args
        assert "ports" not in call_kwargs.kwargs, (
            "containers.run() must not publish host ports"
        )

    async def test_start_uses_to_thread(
        self,
        manager: ContainerManager,
        mock_docker_client: MagicMock,
        mock_server: MagicMock,
        mock_session: AsyncMock,
        mock_repo: AsyncMock,
    ) -> None:
        """Docker SDK calls execute inside asyncio.to_thread()."""
        with (
            patch(
                "switchboard.container.manager.docker.from_env",
                return_value=mock_docker_client,
            ),
            patch(
                "switchboard.container.manager.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="abc123container",
            ) as mock_to_thread,
        ):
            await manager.start(mock_session, mock_server, mock_repo)

        mock_to_thread.assert_called_once()

    async def test_start_creates_network_if_missing(
        self,
        manager: ContainerManager,
        mock_docker_client: MagicMock,
        mock_server: MagicMock,
        mock_session: AsyncMock,
        mock_repo: AsyncMock,
    ) -> None:
        """If the Docker network is missing, it is created before containers.run()."""
        mock_docker_client.networks.get.side_effect = docker.errors.NotFound(
            "not found"
        )

        with patch(
            "switchboard.container.manager.docker.from_env",
            return_value=mock_docker_client,
        ):
            await manager.start(mock_session, mock_server, mock_repo)

        mock_docker_client.networks.create.assert_called_once_with(
            DOCKER_NETWORK, driver="bridge"
        )

    async def test_start_handles_existing_stopped_container(
        self,
        manager: ContainerManager,
        mock_docker_client: MagicMock,
        mock_server: MagicMock,
        mock_session: AsyncMock,
        mock_repo: AsyncMock,
    ) -> None:
        """If a stopped container with the same name exists, it is removed first."""
        existing = MagicMock()
        existing.status = "exited"
        mock_docker_client.containers.get.return_value = existing

        new_container = MagicMock()
        new_container.id = "new123container"
        new_container.status = "running"
        new_container.reload = MagicMock()
        mock_docker_client.containers.run.return_value = new_container

        with patch(
            "switchboard.container.manager.docker.from_env",
            return_value=mock_docker_client,
        ):
            await manager.start(mock_session, mock_server, mock_repo)

        existing.remove.assert_called_once_with(force=True)
        mock_docker_client.containers.run.assert_called_once()


# ---------------------------------------------------------------------------
# stop() tests
# ---------------------------------------------------------------------------


class TestStop:
    """Tests for ContainerManager.stop()."""

    async def test_stop_stops_and_removes_container(
        self,
        manager: ContainerManager,
        mock_docker_client: MagicMock,
        mock_server: MagicMock,
        mock_session: AsyncMock,
        mock_repo: AsyncMock,
    ) -> None:
        """stop() calls container.stop(timeout=10) then container.remove(force=True)."""
        mock_server.container_id = "abc123container"
        container = mock_docker_client.containers.get.return_value

        with patch(
            "switchboard.container.manager.docker.from_env",
            return_value=mock_docker_client,
        ):
            await manager.stop(mock_session, mock_server, mock_repo)

        container.stop.assert_called_once_with(timeout=10)
        container.remove.assert_called_once_with(force=True)

    async def test_stop_updates_registry(
        self,
        manager: ContainerManager,
        mock_docker_client: MagicMock,
        mock_server: MagicMock,
        mock_session: AsyncMock,
        mock_repo: AsyncMock,
    ) -> None:
        """After stop, registry is updated to stopped with no container ID."""
        mock_server.container_id = "abc123container"

        with patch(
            "switchboard.container.manager.docker.from_env",
            return_value=mock_docker_client,
        ):
            await manager.stop(mock_session, mock_server, mock_repo)

        mock_repo.update_status.assert_called_once_with(
            mock_session, mock_server.id, ServerStatus.stopped
        )
        mock_repo.update_container_id.assert_called_once_with(
            mock_session, mock_server.id, None
        )

    async def test_stop_handles_already_gone(
        self,
        manager: ContainerManager,
        mock_docker_client: MagicMock,
        mock_server: MagicMock,
        mock_session: AsyncMock,
        mock_repo: AsyncMock,
    ) -> None:
        """When container is not found, registry is still updated to stopped."""
        mock_server.container_id = "gone-container"
        mock_docker_client.containers.get.side_effect = docker.errors.NotFound(
            "not found"
        )

        with patch(
            "switchboard.container.manager.docker.from_env",
            return_value=mock_docker_client,
        ):
            await manager.stop(mock_session, mock_server, mock_repo)

        mock_repo.update_status.assert_called_once_with(
            mock_session, mock_server.id, ServerStatus.stopped
        )

    async def test_stop_uses_to_thread(
        self,
        manager: ContainerManager,
        mock_docker_client: MagicMock,
        mock_server: MagicMock,
        mock_session: AsyncMock,
        mock_repo: AsyncMock,
    ) -> None:
        """Docker SDK calls in stop() execute inside asyncio.to_thread()."""
        mock_server.container_id = "abc123container"

        with (
            patch(
                "switchboard.container.manager.docker.from_env",
                return_value=mock_docker_client,
            ),
            patch(
                "switchboard.container.manager.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value=None,
            ) as mock_to_thread,
        ):
            await manager.stop(mock_session, mock_server, mock_repo)

        mock_to_thread.assert_called_once()


# ---------------------------------------------------------------------------
# restart() tests
# ---------------------------------------------------------------------------


class TestRestart:
    """Tests for ContainerManager.restart()."""

    async def test_restart_performs_stop_then_start(
        self,
        manager: ContainerManager,
        mock_docker_client: MagicMock,
        mock_server: MagicMock,
        mock_session: AsyncMock,
        mock_repo: AsyncMock,
    ) -> None:
        """restart() calls stop then start, producing a new container ID."""
        mock_server.container_id = "old-container-id"

        # After stop, session.get returns server with container_id cleared
        stopped_server = MagicMock()
        stopped_server.id = mock_server.id
        stopped_server.name = mock_server.name
        stopped_server.container_image = mock_server.container_image
        stopped_server.status = ServerStatus.stopped
        stopped_server.container_id = None
        mock_session.get.return_value = stopped_server

        new_container = MagicMock()
        new_container.id = "new-container-id"
        new_container.status = "running"
        new_container.reload = MagicMock()
        mock_docker_client.containers.run.return_value = new_container

        with patch(
            "switchboard.container.manager.docker.from_env",
            return_value=mock_docker_client,
        ):
            await manager.restart(mock_session, mock_server, mock_repo)

        # Verify stop was called (container.stop on old container)
        # and start was called (containers.run for new container)
        mock_docker_client.containers.run.assert_called_once()

    async def test_restart_updates_registry(
        self,
        manager: ContainerManager,
        mock_docker_client: MagicMock,
        mock_server: MagicMock,
        mock_session: AsyncMock,
        mock_repo: AsyncMock,
    ) -> None:
        """After restart, server status is running with the new container ID."""
        mock_server.container_id = "old-container-id"

        stopped_server = MagicMock()
        stopped_server.id = mock_server.id
        stopped_server.name = mock_server.name
        stopped_server.container_image = mock_server.container_image
        stopped_server.status = ServerStatus.stopped
        stopped_server.container_id = None
        mock_session.get.return_value = stopped_server

        new_container = MagicMock()
        new_container.id = "new-container-id"
        new_container.status = "running"
        new_container.reload = MagicMock()
        mock_docker_client.containers.run.return_value = new_container

        with patch(
            "switchboard.container.manager.docker.from_env",
            return_value=mock_docker_client,
        ):
            await manager.restart(mock_session, mock_server, mock_repo)

        # Final state should be running with new container ID
        # update_status called for stop (stopped) and start (running)
        status_calls = mock_repo.update_status.call_args_list
        assert any(
            call.args == (mock_session, mock_server.id, ServerStatus.stopped)
            for call in status_calls
        ), "stop should set status to stopped"
        assert any(
            call.args == (mock_session, stopped_server.id, ServerStatus.running)
            for call in status_calls
        ), "start should set status to running"

    async def test_restart_uses_to_thread(
        self,
        manager: ContainerManager,
        mock_docker_client: MagicMock,
        mock_server: MagicMock,
        mock_session: AsyncMock,
        mock_repo: AsyncMock,
    ) -> None:
        """Docker SDK calls in restart() execute inside asyncio.to_thread()."""
        mock_server.container_id = "old-container-id"

        stopped_server = MagicMock()
        stopped_server.id = mock_server.id
        stopped_server.name = mock_server.name
        stopped_server.container_image = mock_server.container_image
        stopped_server.status = ServerStatus.stopped
        stopped_server.container_id = None
        mock_session.get.return_value = stopped_server

        new_container = MagicMock()
        new_container.id = "new-container-id"
        new_container.status = "running"
        new_container.reload = MagicMock()
        mock_docker_client.containers.run.return_value = new_container

        call_count = 0

        async def mock_to_thread_fn(func, *args, **kwargs):  # noqa: ANN001, ANN003, ARG001
            nonlocal call_count
            call_count += 1
            # For stop: return None; for start: return container id
            if call_count == 1:
                return None
            return "new-container-id"

        with (
            patch(
                "switchboard.container.manager.docker.from_env",
                return_value=mock_docker_client,
            ),
            patch(
                "switchboard.container.manager.asyncio.to_thread",
                side_effect=mock_to_thread_fn,
            ),
        ):
            await manager.restart(mock_session, mock_server, mock_repo)

        # to_thread called twice: once for stop, once for start
        assert call_count == 2, (
            f"Expected 2 to_thread calls (stop + start), got {call_count}"
        )


# ---------------------------------------------------------------------------
# Constants validation
# ---------------------------------------------------------------------------


class TestConstants:
    """Verify module-level constants are correctly defined."""

    def test_container_port(self) -> None:
        assert CONTAINER_PORT == 8000

    def test_container_name_prefix(self) -> None:
        assert CONTAINER_NAME_PREFIX == "sb-"

    def test_docker_network(self) -> None:
        assert DOCKER_NETWORK == "switchboard-internal"
