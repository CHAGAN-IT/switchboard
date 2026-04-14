"""Pydantic schemas for server registry API serialization.

These schemas are separate from the ORM model (D-11). ORM models
handle database persistence; Pydantic schemas handle API validation
and serialization. Conversion happens at the boundary.

Depends on: switchboard.registry.models (ServerStatus enum)
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from switchboard.registry.models import ServerStatus


class ServerCreate(BaseModel):
    """Schema for creating a new server registration."""

    name: str
    container_image: str
    description: str | None = None


class ServerRead(BaseModel):
    """Schema for reading server data from the API.

    Uses from_attributes=True so it can be constructed directly
    from a Server ORM instance: ServerRead.model_validate(server_orm).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    container_image: str
    description: str | None
    status: ServerStatus
    container_id: str | None
    created_at: datetime
    updated_at: datetime
