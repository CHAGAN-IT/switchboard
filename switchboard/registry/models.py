"""SQLAlchemy ORM model for registered MCP servers.

Defines the Server table and ServerStatus enum used by the registry
domain. The Server model enforces name validation at the ORM level
via ``@validates``, complementing database-level constraints.

Depends on: switchboard.db.base (Base declarative class)
"""

from __future__ import annotations

import enum
import re
import uuid
from datetime import datetime

from sqlalchemy import String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, validates

from switchboard.db.base import Base

# Server name validation regex (D-08):
# Lowercase alphanumeric, may contain hyphens (not at start/end), 3-64 chars total.
SERVER_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")


class ServerStatus(enum.Enum):
    """Server container lifecycle status (D-05).

    Values: stopped (default on registration), running, error.
    """

    stopped = "stopped"
    running = "running"
    error = "error"


class Server(Base):
    """ORM model for a registered MCP server (D-06).

    Columns:
        id: UUID v4 primary key, generated server-side (D-04).
        name: Unique server name, validated by regex (D-08).
        container_image: Docker image reference (required).
        description: Optional human-readable description (D-07).
        status: Current lifecycle status (D-05).
        container_id: Docker container ID when running.
        created_at: Row creation timestamp (server-generated).
        updated_at: Last modification timestamp (server-generated).
    """

    __tablename__ = "servers"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    container_image: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    status: Mapped[ServerStatus] = mapped_column(
        nullable=False,
        default=ServerStatus.stopped,
    )
    container_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    @validates("name")
    def validate_name(self, _key: str, value: str) -> str:
        """Validate server name at the model level (D-08).

        Raises:
            ValueError: If name does not match the required pattern.
        """
        if not SERVER_NAME_PATTERN.match(value):
            msg = (
                f"Server name '{value}' does not match required pattern: "
                f"lowercase alphanumeric with hyphens, 3-64 chars"
            )
            raise ValueError(msg)
        return value
