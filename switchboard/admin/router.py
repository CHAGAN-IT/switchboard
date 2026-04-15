"""Admin API router for server registration endpoints.

Provides CRUD endpoints for MCP server registration under /api/v1/servers.
All routes are protected by JWT validation at the router level via
dependencies=[Depends(require_operator)].

Depends on: switchboard.admin.auth, switchboard.db.session,
            switchboard.registry.repository, switchboard.registry.schemas
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import (
    AsyncSession,  # noqa: TC002 -- FastAPI needs this at runtime for Annotated[AsyncSession, Depends()]
)

from switchboard.admin.auth import require_operator
from switchboard.db.session import get_session
from switchboard.registry.exceptions import DuplicateServerError
from switchboard.registry.repository import ServerRepository
from switchboard.registry.schemas import ServerCreate, ServerRead

router = APIRouter(
    prefix="/api/v1",
    tags=["servers"],
    dependencies=[Depends(require_operator)],
)

_repo = ServerRepository()


@router.post(
    "/servers",
    response_model=ServerRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new MCP server",
)
async def register_server(
    body: ServerCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
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
        server = await _repo.create(
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
    await session.commit()
    return ServerRead.model_validate(server)


@router.get(
    "/servers",
    response_model=list[ServerRead],
    summary="List all registered servers",
)
async def list_servers(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ServerRead]:
    """List all registered MCP servers with their current status.

    Returns all servers ordered by creation date descending.

    Args:
        session: Async database session injected by FastAPI.

    Returns:
        List of all registered server records.
    """
    servers = await _repo.list_all(session)
    return [ServerRead.model_validate(s) for s in servers]


@router.get(
    "/servers/{name}",
    response_model=ServerRead,
    summary="Get server details",
)
async def get_server(
    name: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ServerRead:
    """Retrieve details for a specific registered server.

    Args:
        name: The unique server name.
        session: Async database session injected by FastAPI.

    Returns:
        The server record for the given name.

    Raises:
        HTTPException: 404 if no server with the given name exists.
    """
    server = await _repo.get_by_name(session, name)
    if server is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server '{name}' not found",
        )
    return ServerRead.model_validate(server)
