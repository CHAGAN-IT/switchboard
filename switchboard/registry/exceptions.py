"""Registry-specific exception hierarchy."""

from __future__ import annotations


class RegistryError(Exception):
    """Base exception for server registry operations."""

    pass


class ServerNotFoundError(RegistryError):
    """Raised when a requested server does not exist."""

    def __init__(self, identifier: str) -> None:
        super().__init__(f"Server not found: {identifier}")
        self.identifier = identifier


class DuplicateServerError(RegistryError):
    """Raised when a server name already exists."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Server already exists: {name}")
        self.name = name
