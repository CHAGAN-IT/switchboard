"""ECS adapter for ContainerManager -- production backend.

Wraps boto3 ECS service API calls. All blocking calls run inside
asyncio.to_thread() following the pattern from _start_blocking
in the Docker adapter.

Depends on: boto3, switchboard.container.exceptions
"""

from __future__ import annotations

import asyncio
import logging
import os

import boto3
from botocore.exceptions import ClientError

from switchboard.container.exceptions import ContainerStartError, ContainerStopError

logger = logging.getLogger(__name__)


def _is_ecs_environment() -> bool:
    """Detect ECS runtime via metadata endpoint env var (D-11).

    AWS ECS Fargate injects ECS_CONTAINER_METADATA_URI into every task
    container. Its presence indicates the application is running inside
    ECS rather than local Docker Compose.
    """
    return "ECS_CONTAINER_METADATA_URI" in os.environ


class ECSAdapter:
    """Manages MCP server ECS services via boto3.

    Each method wraps a synchronous boto3 call in asyncio.to_thread()
    to avoid blocking the event loop, following the established pattern
    from ContainerManager._start_blocking.

    Args:
        cluster_arn: ARN of the ECS cluster.
        region: AWS region name.
    """

    def __init__(self, cluster_arn: str, region: str) -> None:
        self._cluster_arn = cluster_arn
        self._region = region

    async def start_service(self, service_name: str) -> dict:
        """Set desired_count=1 on an ECS service (D-10).

        Args:
            service_name: ECS service name (e.g. "sb-echo").

        Returns:
            Raw boto3 update_service response dict.

        Raises:
            ContainerStartError: If the ECS API call fails.
        """
        try:
            return await asyncio.to_thread(
                self._update_service_blocking, service_name, desired_count=1
            )
        except ClientError as exc:
            raise ContainerStartError(service_name, str(exc)) from exc

    async def stop_service(self, service_name: str) -> dict:
        """Set desired_count=0 on an ECS service (D-10).

        Args:
            service_name: ECS service name (e.g. "sb-echo").

        Returns:
            Raw boto3 update_service response dict.

        Raises:
            ContainerStopError: If the ECS API call fails.
        """
        try:
            return await asyncio.to_thread(
                self._update_service_blocking, service_name, desired_count=0
            )
        except ClientError as exc:
            raise ContainerStopError(service_name, str(exc)) from exc

    async def restart_service(self, service_name: str) -> dict:
        """Force new deployment on an ECS service (D-10).

        Args:
            service_name: ECS service name (e.g. "sb-echo").

        Returns:
            Raw boto3 update_service response dict.

        Raises:
            ContainerStartError: If the ECS API call fails.
        """
        try:
            return await asyncio.to_thread(
                self._force_deploy_blocking, service_name
            )
        except ClientError as exc:
            raise ContainerStartError(service_name, str(exc)) from exc

    def _update_service_blocking(
        self, service_name: str, *, desired_count: int
    ) -> dict:
        """Blocking boto3 call -- runs in thread.

        Creates a fresh boto3 client, calls update_service, and closes
        the client in a finally block to avoid resource leaks (T-7-18).

        Args:
            service_name: ECS service name.
            desired_count: Target task count (1 for start, 0 for stop).

        Returns:
            Raw boto3 update_service response dict.
        """
        client = boto3.client("ecs", region_name=self._region)
        try:
            return client.update_service(
                cluster=self._cluster_arn,
                service=service_name,
                desiredCount=desired_count,
            )
        finally:
            client.close()

    def _force_deploy_blocking(self, service_name: str) -> dict:
        """Blocking boto3 call -- runs in thread.

        Forces a new deployment on the ECS service, which replaces all
        running tasks with new ones from the latest task definition.

        Args:
            service_name: ECS service name.

        Returns:
            Raw boto3 update_service response dict.
        """
        client = boto3.client("ecs", region_name=self._region)
        try:
            return client.update_service(
                cluster=self._cluster_arn,
                service=service_name,
                forceNewDeployment=True,
            )
        finally:
            client.close()
