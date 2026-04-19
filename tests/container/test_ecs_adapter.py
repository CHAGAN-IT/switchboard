"""Unit tests for ECS adapter and environment detection.

Tests cover the ECSAdapter class (start/stop/restart via boto3) and the
_is_ecs_environment() detection function. All boto3 calls are mocked --
no real AWS credentials or API calls required.

Verifies:
- ECS environment detection via ECS_CONTAINER_METADATA_URI
- start_service calls update_service with desiredCount=1
- stop_service calls update_service with desiredCount=0
- restart_service calls update_service with forceNewDeployment=True
- All adapter methods use asyncio.to_thread for blocking calls
- boto3 client created with correct region_name and closed after each call
- ClientError from boto3 propagates as ContainerStartError/ContainerStopError

Depends on: switchboard.container.ecs_adapter, switchboard.container.exceptions
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from switchboard.container.ecs_adapter import ECSAdapter, _is_ecs_environment
from switchboard.container.exceptions import ContainerStartError, ContainerStopError

CLUSTER_ARN = "arn:aws:ecs:us-east-1:123456789012:cluster/switchboard-dev"
REGION = "us-east-1"


# ---------------------------------------------------------------------------
# Environment detection
# ---------------------------------------------------------------------------


class TestEnvDetection:
    """Tests for _is_ecs_environment() function."""

    def test_returns_true_when_metadata_uri_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_is_ecs_environment() returns True when ECS_CONTAINER_METADATA_URI is set."""
        monkeypatch.setenv(
            "ECS_CONTAINER_METADATA_URI", "http://169.254.170.2/v4/abc123"
        )
        assert _is_ecs_environment() is True

    def test_returns_false_when_metadata_uri_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns False when ECS_CONTAINER_METADATA_URI is not set."""
        monkeypatch.delenv("ECS_CONTAINER_METADATA_URI", raising=False)
        assert _is_ecs_environment() is False


# ---------------------------------------------------------------------------
# start_service
# ---------------------------------------------------------------------------


class TestStart:
    """Tests for ECSAdapter.start_service()."""

    async def test_start_calls_update_service_with_desired_count_1(self) -> None:
        """start_service calls update_service with desiredCount=1."""
        mock_client = MagicMock()
        mock_client.update_service.return_value = {"service": {"status": "ACTIVE"}}

        with patch(
            "switchboard.container.ecs_adapter.boto3.client", return_value=mock_client
        ):
            adapter = ECSAdapter(cluster_arn=CLUSTER_ARN, region=REGION)
            await adapter.start_service("sb-echo")

        mock_client.update_service.assert_called_once_with(
            cluster=CLUSTER_ARN,
            service="sb-echo",
            desiredCount=1,
        )

    async def test_start_error_raises_container_start_error(self) -> None:
        """ClientError from boto3 is re-raised as ContainerStartError."""
        mock_client = MagicMock()
        mock_client.update_service.side_effect = ClientError(
            error_response={
                "Error": {"Code": "ServiceNotFoundException", "Message": "not found"}
            },
            operation_name="UpdateService",
        )

        with (
            patch(
                "switchboard.container.ecs_adapter.boto3.client",
                return_value=mock_client,
            ),
            pytest.raises(ContainerStartError, match="sb-echo"),
        ):
            adapter = ECSAdapter(cluster_arn=CLUSTER_ARN, region=REGION)
            await adapter.start_service("sb-echo")


# ---------------------------------------------------------------------------
# stop_service
# ---------------------------------------------------------------------------


class TestStop:
    """Tests for ECSAdapter.stop_service()."""

    async def test_stop_calls_update_service_with_desired_count_0(self) -> None:
        """stop_service calls update_service with desiredCount=0."""
        mock_client = MagicMock()
        mock_client.update_service.return_value = {"service": {"status": "ACTIVE"}}

        with patch(
            "switchboard.container.ecs_adapter.boto3.client", return_value=mock_client
        ):
            adapter = ECSAdapter(cluster_arn=CLUSTER_ARN, region=REGION)
            await adapter.stop_service("sb-echo")

        mock_client.update_service.assert_called_once_with(
            cluster=CLUSTER_ARN,
            service="sb-echo",
            desiredCount=0,
        )

    async def test_stop_error_raises_container_stop_error(self) -> None:
        """ClientError from boto3 is re-raised as ContainerStopError."""
        mock_client = MagicMock()
        mock_client.update_service.side_effect = ClientError(
            error_response={
                "Error": {"Code": "ServiceNotFoundException", "Message": "not found"}
            },
            operation_name="UpdateService",
        )

        with (
            patch(
                "switchboard.container.ecs_adapter.boto3.client",
                return_value=mock_client,
            ),
            pytest.raises(ContainerStopError, match="sb-echo"),
        ):
            adapter = ECSAdapter(cluster_arn=CLUSTER_ARN, region=REGION)
            await adapter.stop_service("sb-echo")


# ---------------------------------------------------------------------------
# restart_service
# ---------------------------------------------------------------------------


class TestRestart:
    """Tests for ECSAdapter.restart_service()."""

    async def test_restart_calls_update_service_with_force_new_deployment(self) -> None:
        """restart_service calls update_service with forceNewDeployment=True."""
        mock_client = MagicMock()
        mock_client.update_service.return_value = {"service": {"status": "ACTIVE"}}

        with patch(
            "switchboard.container.ecs_adapter.boto3.client", return_value=mock_client
        ):
            adapter = ECSAdapter(cluster_arn=CLUSTER_ARN, region=REGION)
            await adapter.restart_service("sb-echo")

        mock_client.update_service.assert_called_once_with(
            cluster=CLUSTER_ARN,
            service="sb-echo",
            forceNewDeployment=True,
        )

    async def test_restart_error_raises_container_start_error(self) -> None:
        """ClientError from boto3 restart is re-raised as ContainerStartError."""
        mock_client = MagicMock()
        mock_client.update_service.side_effect = ClientError(
            error_response={
                "Error": {"Code": "ClusterNotFoundException", "Message": "not found"}
            },
            operation_name="UpdateService",
        )

        with (
            patch(
                "switchboard.container.ecs_adapter.boto3.client",
                return_value=mock_client,
            ),
            pytest.raises(ContainerStartError, match="sb-echo"),
        ):
            adapter = ECSAdapter(cluster_arn=CLUSTER_ARN, region=REGION)
            await adapter.restart_service("sb-echo")


# ---------------------------------------------------------------------------
# Client lifecycle
# ---------------------------------------------------------------------------


class TestClientLifecycle:
    """Tests for boto3 client creation and cleanup."""

    async def test_client_created_with_correct_region(self) -> None:
        """boto3.client('ecs', region_name=...) is called with the adapter's region."""
        mock_client = MagicMock()
        mock_client.update_service.return_value = {}

        with patch(
            "switchboard.container.ecs_adapter.boto3.client", return_value=mock_client
        ) as mock_boto3:
            adapter = ECSAdapter(cluster_arn=CLUSTER_ARN, region=REGION)
            await adapter.start_service("sb-echo")

        mock_boto3.assert_called_with("ecs", region_name=REGION)

    async def test_client_closed_after_success(self) -> None:
        """boto3 client.close() is called after successful operation."""
        mock_client = MagicMock()
        mock_client.update_service.return_value = {}

        with patch(
            "switchboard.container.ecs_adapter.boto3.client", return_value=mock_client
        ):
            adapter = ECSAdapter(cluster_arn=CLUSTER_ARN, region=REGION)
            await adapter.start_service("sb-echo")

        mock_client.close.assert_called_once()

    async def test_client_closed_after_error(self) -> None:
        """boto3 client.close() is called even when update_service raises."""
        mock_client = MagicMock()
        mock_client.update_service.side_effect = ClientError(
            error_response={
                "Error": {"Code": "ServiceNotFoundException", "Message": "fail"}
            },
            operation_name="UpdateService",
        )

        with (
            patch(
                "switchboard.container.ecs_adapter.boto3.client",
                return_value=mock_client,
            ),
            pytest.raises(ContainerStartError),
        ):
            adapter = ECSAdapter(cluster_arn=CLUSTER_ARN, region=REGION)
            await adapter.start_service("sb-echo")

        mock_client.close.assert_called_once()


# ---------------------------------------------------------------------------
# asyncio.to_thread usage
# ---------------------------------------------------------------------------


class TestAsyncThreading:
    """Verify all adapter methods use asyncio.to_thread for blocking calls."""

    async def test_start_uses_to_thread(self) -> None:
        """start_service runs blocking call via asyncio.to_thread."""
        mock_client = MagicMock()
        mock_client.update_service.return_value = {}

        with (
            patch(
                "switchboard.container.ecs_adapter.boto3.client",
                return_value=mock_client,
            ),
            patch(
                "switchboard.container.ecs_adapter.asyncio.to_thread"
            ) as mock_to_thread,
        ):
            mock_to_thread.return_value = {}
            adapter = ECSAdapter(cluster_arn=CLUSTER_ARN, region=REGION)
            await adapter.start_service("sb-echo")

        mock_to_thread.assert_called_once()

    async def test_stop_uses_to_thread(self) -> None:
        """stop_service runs blocking call via asyncio.to_thread."""
        mock_client = MagicMock()
        mock_client.update_service.return_value = {}

        with (
            patch(
                "switchboard.container.ecs_adapter.boto3.client",
                return_value=mock_client,
            ),
            patch(
                "switchboard.container.ecs_adapter.asyncio.to_thread"
            ) as mock_to_thread,
        ):
            mock_to_thread.return_value = {}
            adapter = ECSAdapter(cluster_arn=CLUSTER_ARN, region=REGION)
            await adapter.stop_service("sb-echo")

        mock_to_thread.assert_called_once()

    async def test_restart_uses_to_thread(self) -> None:
        """restart_service runs blocking call via asyncio.to_thread."""
        mock_client = MagicMock()
        mock_client.update_service.return_value = {}

        with (
            patch(
                "switchboard.container.ecs_adapter.boto3.client",
                return_value=mock_client,
            ),
            patch(
                "switchboard.container.ecs_adapter.asyncio.to_thread"
            ) as mock_to_thread,
        ):
            mock_to_thread.return_value = {}
            adapter = ECSAdapter(cluster_arn=CLUSTER_ARN, region=REGION)
            await adapter.restart_service("sb-echo")

        mock_to_thread.assert_called_once()
