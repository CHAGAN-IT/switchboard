"""Container lifecycle exception hierarchy.

Mirrors the pattern from switchboard.registry.exceptions. Each exception
carries structured attributes (server_name, reason) for logging and
error-response construction.

Depends on: nothing (leaf module)
"""

from __future__ import annotations


class ContainerError(Exception):
    """Base exception for container lifecycle operations."""


class ContainerStartError(ContainerError):
    """Raised when a container fails to start.

    Attributes:
        server_name: Name of the server whose container failed.
        reason: Human-readable failure reason.
    """

    def __init__(self, server_name: str, reason: str) -> None:
        super().__init__(f"Failed to start container for '{server_name}': {reason}")
        self.server_name = server_name
        self.reason = reason


class ContainerStopError(ContainerError):
    """Raised when a container fails to stop.

    Attributes:
        server_name: Name of the server whose container failed.
        reason: Human-readable failure reason.
    """

    def __init__(self, server_name: str, reason: str) -> None:
        super().__init__(f"Failed to stop container for '{server_name}': {reason}")
        self.server_name = server_name
        self.reason = reason


class ContainerNotRunningError(ContainerError):
    """Raised when an operation requires a running container but none is found.

    Attributes:
        server_name: Name of the server that is not running.
    """

    def __init__(self, server_name: str) -> None:
        super().__init__(f"Server '{server_name}' is not running")
        self.server_name = server_name
