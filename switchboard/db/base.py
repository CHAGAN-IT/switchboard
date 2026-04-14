"""SQLAlchemy declarative base for all ORM models."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all Switchboard ORM models.

    All model classes inherit from this base. Alembic reads
    Base.metadata to detect schema changes for autogeneration.
    """

    pass
