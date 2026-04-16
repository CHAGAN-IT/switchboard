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
import urllib.request
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

_MCP_CONTAINER_PORT: str = "8000/tcp"
_HEALTH_CHECK_RETRIES: int = 30
_HEALTH_CHECK_INTERVAL: float = 1.0


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


def _wait_for_healthy(url: str, *, retries: int = _HEALTH_CHECK_RETRIES) -> None:
    """Poll the MCP endpoint until it responds or retries are exhausted.

    The MCP Streamable HTTP endpoint returns 405 Method Not Allowed for
    GET requests (it expects POST), but any HTTP response confirms the
    server is listening. Connection errors mean the server is still starting.

    Args:
        url: Full URL to the MCP endpoint (e.g. http://localhost:12345/mcp).
        retries: Maximum number of attempts before raising.

    Raises:
        RuntimeError: If the endpoint does not respond within the retry limit.
    """
    for attempt in range(retries):
        try:
            urllib.request.urlopen(url, timeout=2)  # noqa: S310
            return
        except urllib.error.HTTPError:
            # Any HTTP response (even 405/406) means the server is up
            return
        except (urllib.error.URLError, OSError) as exc:
            if attempt == retries - 1:
                msg = (
                    f"MCP server at {url} did not become healthy "
                    f"after {retries} attempts"
                )
                raise RuntimeError(msg) from exc
            time.sleep(_HEALTH_CHECK_INTERVAL)


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

        host_port = _get_host_port(container)
        url = f"http://localhost:{host_port}/mcp"
        _wait_for_healthy(url)
        yield url
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

        host_port = _get_host_port(container)
        url = f"http://localhost:{host_port}/mcp"
        _wait_for_healthy(url)
        yield url
    finally:
        if container is not None:
            try:
                container.stop(timeout=5)
                container.remove(force=True)
            except docker.errors.NotFound:
                pass
        client.close()
