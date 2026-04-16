"""Fixtures for reference server integration tests.

Starts echo and ping containers with ephemeral host ports so tests running
on the host machine can reach the MCP endpoints. Uses test-specific
container names (sb-echo-test, sb-ping-test) to avoid colliding with
docker-compose production containers.

Requires: Docker daemon running, switchboard-echo and switchboard-ping
images built (``docker compose build echo ping``).

Note on networking: The switchboard-internal network is internal-only.
Tests run on the host and cannot reach containers via that network.
Fixtures publish an ephemeral host port and discover the assigned port
via container.ports. This matches the existing pattern for PostgreSQL
(port 5432 published in docker-compose.yml for test access).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import docker
import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

ECHO_IMAGE: str = "switchboard-echo"
PING_IMAGE: str = "switchboard-ping"

# Test container names -- distinct from production names (sb-echo, sb-ping)
# to prevent conflicts when docker-compose services are also running.
ECHO_TEST_NAME: str = "sb-echo-test"
PING_TEST_NAME: str = "sb-ping-test"

_STARTUP_WAIT_SECONDS: int = 3
_MCP_CONTAINER_PORT: str = "8000/tcp"


def _get_host_port(container: docker.models.containers.Container) -> int:
    """Return the ephemeral host port mapped to container port 8000.

    Args:
        container: Running Docker container with an ephemeral port mapping.

    Returns:
        Host port number as integer.

    Raises:
        RuntimeError: If no port mapping is found for port 8000.
    """
    container.reload()
    ports = container.ports.get(_MCP_CONTAINER_PORT)
    if not ports:
        msg = (
            f"No port mapping found for {_MCP_CONTAINER_PORT} "
            f"on container {container.name}"
        )
        raise RuntimeError(msg)
    return int(ports[0]["HostPort"])


@pytest.fixture(scope="session")
def echo_server_url() -> Generator[str, None, None]:
    """Start echo container and yield its MCP endpoint URL.

    Publishes an ephemeral host port so tests can reach the server from
    outside the Docker network. Container is removed after the test session.
    """
    client = docker.from_env()
    container = None
    try:
        # Remove any leftover test container from a previous interrupted run
        try:
            old = client.containers.get(ECHO_TEST_NAME)
            old.remove(force=True)
        except docker.errors.NotFound:
            pass

        container = client.containers.run(
            image=ECHO_IMAGE,
            name=ECHO_TEST_NAME,
            detach=True,
            ports={_MCP_CONTAINER_PORT: None},  # None = ephemeral host port
        )
        time.sleep(_STARTUP_WAIT_SECONDS)

        host_port = _get_host_port(container)
        yield f"http://localhost:{host_port}/mcp"
    finally:
        if container is not None:
            try:
                container.stop(timeout=5)
                container.remove(force=True)
            except docker.errors.NotFound:
                pass
        client.close()


@pytest.fixture(scope="session")
def ping_server_url() -> Generator[str, None, None]:
    """Start ping container and yield its MCP endpoint URL.

    Publishes an ephemeral host port so tests can reach the server from
    outside the Docker network. Container is removed after the test session.
    """
    client = docker.from_env()
    container = None
    try:
        try:
            old = client.containers.get(PING_TEST_NAME)
            old.remove(force=True)
        except docker.errors.NotFound:
            pass

        container = client.containers.run(
            image=PING_IMAGE,
            name=PING_TEST_NAME,
            detach=True,
            ports={_MCP_CONTAINER_PORT: None},
        )
        time.sleep(_STARTUP_WAIT_SECONDS)

        host_port = _get_host_port(container)
        yield f"http://localhost:{host_port}/mcp"
    finally:
        if container is not None:
            try:
                container.stop(timeout=5)
                container.remove(force=True)
            except docker.errors.NotFound:
                pass
        client.close()
