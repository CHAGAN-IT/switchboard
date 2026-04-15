"""Container lifecycle management -- Phase 3."""

from __future__ import annotations

from switchboard.container.manager import ContainerManager


def get_container_manager() -> ContainerManager:
    """Return a ContainerManager instance for use in endpoint handlers.

    Injected via FastAPI Depends(get_container_manager). Stateless -- a new
    instance per request is fine since all state lives in the Docker daemon
    and the server registry database.
    """
    return ContainerManager()
