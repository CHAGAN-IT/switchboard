"""Server registry repository for async database operations.

Encapsulates all SQL access for the server registry behind a clean
interface. All methods accept an AsyncSession argument so that
transaction boundaries are controlled by the caller (API endpoint
or test fixture).

Repository methods flush() but do not commit() -- this allows tests
to use transaction rollback for isolation and lets API endpoints
batch multiple operations in a single commit.

Depends on: switchboard.registry.models, switchboard.registry.exceptions
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from switchboard.registry.exceptions import DuplicateServerError
from switchboard.registry.models import Server, ServerStatus

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class ServerRepository:
    """Repository for server CRUD operations.

    All methods accept an AsyncSession argument. In production, FastAPI
    injects the session via Depends(). In tests, a test session with
    transaction rollback is passed directly.
    """

    async def create(
        self,
        session: AsyncSession,
        *,
        name: str,
        container_image: str,
        description: str | None = None,
    ) -> Server:
        """Register a new MCP server.

        Args:
            session: Async database session.
            name: Unique server name (validated by model).
            container_image: Docker image reference.
            description: Optional human-readable description.

        Returns:
            The created Server instance with generated UUID.

        Raises:
            DuplicateServerError: If a server with this name already exists.
            ValueError: If name does not match the required pattern.
        """
        server = Server(
            name=name,
            container_image=container_image,
            description=description,
        )
        session.add(server)
        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            raise DuplicateServerError(name) from exc
        await session.refresh(server)
        return server

    async def get_by_id(
        self,
        session: AsyncSession,
        server_id: uuid.UUID,
    ) -> Server | None:
        """Retrieve a server by its UUID.

        Returns:
            The Server instance, or None if not found.
        """
        return await session.get(Server, server_id)

    async def get_by_name(
        self,
        session: AsyncSession,
        name: str,
    ) -> Server | None:
        """Retrieve a server by its unique name.

        Returns:
            The Server instance, or None if not found.
        """
        stmt = select(Server).where(Server.name == name)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(
        self,
        session: AsyncSession,
    ) -> list[Server]:
        """List all registered servers.

        Returns:
            List of all Server instances, ordered by created_at descending.
        """
        stmt = select(Server).order_by(Server.created_at.desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        session: AsyncSession,
        server_id: uuid.UUID,
        status: ServerStatus,
    ) -> Server | None:
        """Update a server's lifecycle status.

        Returns:
            The updated Server instance, or None if not found.
        """
        server = await session.get(Server, server_id)
        if server is None:
            return None
        server.status = status
        await session.flush()
        await session.refresh(server)
        return server

    async def update_container_id(
        self,
        session: AsyncSession,
        server_id: uuid.UUID,
        container_id: str | None,
    ) -> Server | None:
        """Set or clear the Docker container ID for a server.

        Args:
            session: Async database session.
            server_id: UUID of the server to update.
            container_id: Docker container ID, or None to clear.

        Returns:
            The updated Server instance, or None if not found.
        """
        server = await session.get(Server, server_id)
        if server is None:
            return None
        server.container_id = container_id
        await session.flush()
        await session.refresh(server)
        return server

    async def delete(
        self,
        session: AsyncSession,
        server_id: uuid.UUID,
    ) -> bool:
        """Delete a server by ID.

        Returns:
            True if the server was deleted, False if not found.
        """
        server = await session.get(Server, server_id)
        if server is None:
            return False
        await session.delete(server)
        await session.flush()
        return True
