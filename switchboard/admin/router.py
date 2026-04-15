"""Admin API router for server registration and lifecycle endpoints.

Provides CRUD endpoints for MCP server registration and container
lifecycle management (start/stop/restart) under /api/v1/servers.
All routes are protected by JWT validation at the router level via
dependencies=[Depends(require_operator)].

Depends on: switchboard.admin.auth, switchboard.db.session,
            switchboard.registry.repository, switchboard.registry.schemas,
            switchboard.container
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import (
    AsyncSession,  # noqa: TC002 -- FastAPI needs this at runtime for Annotated[AsyncSession, Depends()]
)

from switchboard.admin.auth import require_operator
from switchboard.container import get_container_manager
from switchboard.container.exceptions import ContainerStartError, ContainerStopError
from switchboard.container.manager import (
    ContainerManager,  # noqa: TC001 -- FastAPI needs this at runtime for Annotated[ContainerManager, Depends()]
)
from switchboard.db.session import get_session
from switchboard.registry.exceptions import DuplicateServerError
from switchboard.registry.models import ServerStatus
from switchboard.registry.repository import ServerRepository
from switchboard.registry.schemas import ServerCreate, ServerRead

router = APIRouter(
    prefix="/api/v1",
    tags=["servers"],
    dependencies=[Depends(require_operator)],
)


def get_repository() -> ServerRepository:
    """Return a ServerRepository instance for use in endpoint handlers."""
    return ServerRepository()


@router.post(
    "/servers",
    response_model=ServerRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new MCP server",
)
async def register_server(
    body: ServerCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    repo: Annotated[ServerRepository, Depends(get_repository)],
) -> ServerRead:
    """Register a new MCP server in the registry.

    Creates a new server entry with the given name, container image,
    and optional description. Returns the complete server record
    including generated UUID and timestamps.

    Args:
        body: Server registration payload (name, container_image, description).
        session: Async database session injected by FastAPI.

    Returns:
        The created server record.

    Raises:
        HTTPException: 409 if server name already exists (D-03).
    """
    try:
        server = await repo.create(
            session,
            name=body.name,
            container_image=body.container_image,
            description=body.description,
        )
    except DuplicateServerError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Server '{body.name}' already exists",
        ) from None
    except ValueError as exc:
        # ORM-level validation (e.g. name pattern) caught here
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from None
    await session.commit()
    return ServerRead.model_validate(server)


@router.get(
    "/servers",
    response_model=list[ServerRead],
    summary="List all registered servers",
)
async def list_servers(
    session: Annotated[AsyncSession, Depends(get_session)],
    repo: Annotated[ServerRepository, Depends(get_repository)],
) -> list[ServerRead]:
    """List all registered MCP servers with their current status.

    Returns all servers ordered by creation date descending.

    Args:
        session: Async database session injected by FastAPI.
        repo: Server repository injected by FastAPI.

    Returns:
        List of all registered server records.
    """
    servers = await repo.list_all(session)
    return [ServerRead.model_validate(s) for s in servers]


@router.get(
    "/servers/{name}",
    response_model=ServerRead,
    summary="Get server details",
)
async def get_server(
    name: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    repo: Annotated[ServerRepository, Depends(get_repository)],
) -> ServerRead:
    """Retrieve details for a specific registered server.

    Args:
        name: The unique server name.
        session: Async database session injected by FastAPI.
        repo: Server repository injected by FastAPI.

    Returns:
        The server record for the given name.

    Raises:
        HTTPException: 404 if no server with the given name exists.
    """
    server = await repo.get_by_name(session, name)
    if server is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server '{name}' not found",
        )
    return ServerRead.model_validate(server)


@router.post(
    "/servers/{name}/start",
    response_model=ServerRead,
    summary="Start a server container",
)
async def start_server(
    name: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    repo: Annotated[ServerRepository, Depends(get_repository)],
    cm: Annotated[ContainerManager, Depends(get_container_manager)],
) -> ServerRead:
    """Start the Docker container for a registered server.

    Launches a new container on the internal network and updates the
    registry with running status and container ID.

    Args:
        name: The unique server name.
        session: Async database session injected by FastAPI.
        repo: Server repository injected by FastAPI.
        cm: Container manager injected by FastAPI.

    Returns:
        The updated server record with running status.

    Raises:
        HTTPException: 404 if server not found, 409 if already running,
            500 if container start fails.
    """
    server = await repo.get_by_name(session, name)
    if server is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server '{name}' not found",
        )
    if server.status == ServerStatus.running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Server '{name}' is already running",
        )
    try:
        server = await cm.start(session, server, repo)
    except ContainerStartError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from None
    await session.commit()
    return ServerRead.model_validate(server)


@router.post(
    "/servers/{name}/stop",
    response_model=ServerRead,
    summary="Stop a server container",
)
async def stop_server(
    name: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    repo: Annotated[ServerRepository, Depends(get_repository)],
    cm: Annotated[ContainerManager, Depends(get_container_manager)],
) -> ServerRead:
    """Stop and remove the Docker container for a registered server.

    Stops the running container and updates the registry with stopped
    status and cleared container ID.

    Args:
        name: The unique server name.
        session: Async database session injected by FastAPI.
        repo: Server repository injected by FastAPI.
        cm: Container manager injected by FastAPI.

    Returns:
        The updated server record with stopped status.

    Raises:
        HTTPException: 404 if server not found, 409 if not running,
            500 if container stop fails.
    """
    server = await repo.get_by_name(session, name)
    if server is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server '{name}' not found",
        )
    if server.status != ServerStatus.running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Server '{name}' is not running",
        )
    try:
        server = await cm.stop(session, server, repo)
    except ContainerStopError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from None
    await session.commit()
    return ServerRead.model_validate(server)


@router.post(
    "/servers/{name}/restart",
    response_model=ServerRead,
    summary="Restart a server container",
)
async def restart_server(
    name: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    repo: Annotated[ServerRepository, Depends(get_repository)],
    cm: Annotated[ContainerManager, Depends(get_container_manager)],
) -> ServerRead:
    """Restart the Docker container for a registered server.

    Performs a stop followed by a start, producing a fresh container.
    Works regardless of current server state (stopped servers get started).

    Args:
        name: The unique server name.
        session: Async database session injected by FastAPI.
        repo: Server repository injected by FastAPI.
        cm: Container manager injected by FastAPI.

    Returns:
        The updated server record with running status and new container ID.

    Raises:
        HTTPException: 404 if server not found, 500 if restart fails.
    """
    server = await repo.get_by_name(session, name)
    if server is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server '{name}' not found",
        )
    try:
        server = await cm.restart(session, server, repo)
    except (ContainerStartError, ContainerStopError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from None
    await session.commit()
    return ServerRead.model_validate(server)
