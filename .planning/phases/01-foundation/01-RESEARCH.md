# Phase 1: Foundation - Research

**Researched:** 2026-04-14
**Domain:** Python package structure, async PostgreSQL data layer, SQLAlchemy 2.0 ORM, Alembic migrations, integration testing
**Confidence:** HIGH

## Summary

Phase 1 establishes the foundational Python package, database schema, async data access layer, and integration test infrastructure that every subsequent phase depends on. The core stack is SQLAlchemy 2.0 (async) + asyncpg + Alembic + pydantic-settings, all locked decisions from prior research. The project starts from a bare `pyproject.toml` with no dependencies and an empty `switchboard/` directory.

The primary technical challenges are: (1) correctly configuring Alembic for async engines (the default template does not work with asyncpg -- you must use the `async` template), (2) implementing per-test transaction rollback with `AsyncSession` and `join_transaction_mode="create_savepoint"`, and (3) handling PostgreSQL enum types in Alembic migrations (autogenerate does not properly create or drop enum types without explicit handling).

**Primary recommendation:** Use SQLAlchemy 2.0 `Mapped`/`mapped_column` declarative style, the Alembic `async` template initialized with `alembic init -t async`, and pytest fixtures with `AsyncSession(bind=connection, join_transaction_mode="create_savepoint")` for test isolation via transaction rollback.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Feature-grouped subpackages -- `switchboard/registry/`, `switchboard/gateway/`, `switchboard/admin/`, `switchboard/container/` -- stubbed as empty packages from day one so the full structure is visible before code fills them.
- **D-02:** Shared database infrastructure lives in `switchboard/db/` subpackage (`engine.py`, `session.py`, `base.py`). All feature subpackages import from here.
- **D-03:** App configuration (DB URL, env vars) managed via `switchboard/config.py` using a `pydantic-settings` `Settings` class. All subpackages import settings from this single module.
- **D-04:** Primary key is UUID v4, generated server-side with Python `uuid.uuid4()`.
- **D-05:** Status is a Python enum with values: `stopped`, `running`, `error`. Default on registration is `stopped`.
- **D-06:** Full column set: `id` (UUID PK), `name` (text, unique, not null), `container_image` (text, not null), `description` (text, nullable), `status` (enum, not null), `container_id` (text, nullable -- populated when container is running), `created_at` (timestamptz, not null), `updated_at` (timestamptz, not null).
- **D-07:** `description` is optional (nullable). Empty string is rejected at the API layer (Phase 2), but the DB column allows NULL.
- **D-08:** Server name must match `^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$` -- validated at the model level, not just the API layer.
- **D-09:** `ServerRepository` class in `switchboard/registry/repository.py` with async methods: `create()`, `get_by_name()`, `get_by_id()`, `list_all()`, `update_status()`, `update_container_id()`, `delete()`. All SQL behind a clean interface.
- **D-10:** Async session management uses `async_sessionmaker` (defined in `switchboard/db/session.py`). Repository methods accept a session argument. FastAPI (Phase 2) injects sessions via `Depends()`; tests pass a test session directly.
- **D-11:** SQLAlchemy ORM model and Pydantic schemas are separate types from day one. ORM model in `switchboard/registry/models.py`; Pydantic schemas in `switchboard/registry/schemas.py`.
- **D-12:** Integration tests require a pre-running PostgreSQL instance (via `docker compose up` before running `uv run pytest`). No testcontainers dependency.
- **D-13:** A pytest session-scoped fixture applies Alembic migrations once per test session. Individual test isolation is via transaction rollback -- each test runs inside a transaction that rolls back after completion.
- **D-14:** Tests use a separate `switchboard_test` database configured via `TEST_DATABASE_URL` environment variable. Dev data is never polluted by tests.

### Claude's Discretion
- Exact Alembic migration file naming and `env.py` configuration details
- `conftest.py` structure for shared fixtures
- Logging setup in `switchboard/db/` for query debugging
- SQLAlchemy pool configuration (pool size, timeout)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PLAT-03 | Top-level Python package is `switchboard/` (not `src/`); Python 3.12+ | Package structure patterns documented in Architecture Patterns section; `pyproject.toml` already has `requires-python = ">=3.12"` |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Language:** Python 3.12+ -- all application code
- **Package management:** `uv` only (never pip, poetry, conda)
- **Linting/formatting:** `ruff` only (never flake8, black, isort)
- **Type checking:** `ty` if available, else `mypy --strict`
- **Testing:** `pytest` with 80%+ coverage target
- **Type hints:** Required on all function signatures; use `from __future__ import annotations`
- **Data modeling:** Pydantic `BaseModel` for validated external data; `dataclasses` for internal structs
- **Paths:** `pathlib.Path` over `os.path`
- **Async:** `asyncio` + `httpx` for I/O-bound work; never mix sync and async without `asyncio.to_thread()`
- **Error handling:** Custom exception hierarchies per module; never catch bare `Exception`
- **Strings:** f-strings only; never `%` or `.format()`
- **Git:** Conventional commits (`feat:`, `fix:`, `refactor:`, etc.)
- **Immutability:** Create new objects, never mutate existing ones
- **File size:** 200-400 lines typical, 800 max
- **Functions:** Max ~50 lines

## Standard Stack

### Core (Phase 1 Dependencies)
| Library | Version | Purpose | Why Standard | Source |
|---------|---------|---------|--------------|--------|
| SQLAlchemy | 2.0.49 | Async ORM | 2.0 API is the async-native rewrite; standard for FastAPI + PostgreSQL | [VERIFIED: PyPI, STACK.md] |
| asyncpg | 0.31.0 | Async PostgreSQL driver | Fastest async Postgres driver; required by SQLAlchemy async engine | [VERIFIED: PyPI, STACK.md] |
| Alembic | 1.18.4 | Database migrations | Standard migration tool for SQLAlchemy; 1.13+ required for SA 2.0 | [VERIFIED: PyPI, STACK.md] |
| Pydantic | 2.13.0 | Data validation / schemas | v2 required with current FastAPI; defines Pydantic schemas separate from ORM models | [VERIFIED: PyPI, STACK.md] |
| pydantic-settings | 2.13.1 | Configuration management | Reads config from env vars / `.env` files; standard for containerized apps | [VERIFIED: PyPI, STACK.md] |

### Dev Dependencies (Phase 1)
| Library | Version | Purpose | Source |
|---------|---------|---------|--------|
| pytest | 8.x | Test framework | [VERIFIED: STACK.md] |
| pytest-asyncio | 0.26.x | Async test support | [VERIFIED: STACK.md] |
| ruff | latest | Linting + formatting | [VERIFIED: CLAUDE.md requirement] |

### Installation

```bash
# Core dependencies
uv add sqlalchemy asyncpg alembic pydantic pydantic-settings

# Dev dependencies
uv add --dev pytest pytest-asyncio ruff
```

## Architecture Patterns

### Recommended Project Structure

```
switchboard/                    # Top-level package (NOT src/)
    __init__.py                 # Package marker; import switchboard succeeds
    config.py                   # pydantic-settings Settings class (D-03)
    db/                         # Shared database infrastructure (D-02)
        __init__.py
        base.py                 # DeclarativeBase for all ORM models
        engine.py               # create_async_engine factory
        session.py              # async_sessionmaker factory
    registry/                   # Server registry domain (Phase 1 implementation)
        __init__.py
        models.py               # SQLAlchemy ORM model: Server (D-06)
        schemas.py              # Pydantic schemas: ServerCreate, ServerRead, etc. (D-11)
        repository.py           # ServerRepository with async CRUD (D-09)
        exceptions.py           # Registry-specific exceptions
    gateway/                    # Stub for Phase 5
        __init__.py
    admin/                      # Stub for Phase 2
        __init__.py
    container/                  # Stub for Phase 3
        __init__.py
alembic/                        # Alembic migrations directory
    env.py                      # Async env.py (from async template)
    versions/                   # Migration scripts
    script.py.mako              # Migration template
alembic.ini                     # Alembic config (reads DB URL from settings)
tests/
    __init__.py
    conftest.py                 # Shared fixtures: engine, session, migrations
    registry/
        __init__.py
        test_models.py          # ORM model validation tests
        test_repository.py      # Integration tests against real PostgreSQL
docker-compose.yml              # PostgreSQL for dev + test databases
pyproject.toml                  # Project config with pytest/ruff settings
```

### Pattern 1: SQLAlchemy 2.0 Declarative Base with Type Annotations

**What:** Use the new `Mapped` / `mapped_column` declarative style from SQLAlchemy 2.0.
**When to use:** All ORM model definitions.
**Example:**

```python
# switchboard/db/base.py
# Source: SQLAlchemy 2.0 official docs
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass

class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass
```

```python
# switchboard/registry/models.py
# Source: SQLAlchemy 2.0 docs + CONTEXT.md decisions D-04 through D-08
from __future__ import annotations

import enum
import re
import uuid
from datetime import datetime

from sqlalchemy import String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, validates

from switchboard.db.base import Base

# Server name validation regex (D-08)
SERVER_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")


class ServerStatus(enum.Enum):
    """Server container status (D-05)."""
    stopped = "stopped"
    running = "running"
    error = "error"


class Server(Base):
    """ORM model for registered MCP servers (D-06)."""

    __tablename__ = "servers"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True,
    )
    container_image: Mapped[str] = mapped_column(
        Text, nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )
    status: Mapped[ServerStatus] = mapped_column(
        nullable=False, default=ServerStatus.stopped,
    )
    container_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    @validates("name")
    def validate_name(self, _key: str, value: str) -> str:
        """Validate server name at the model level (D-08)."""
        if not SERVER_NAME_PATTERN.match(value):
            msg = (
                f"Server name '{value}' does not match required pattern: "
                f"lowercase alphanumeric with hyphens, 3-64 chars"
            )
            raise ValueError(msg)
        return value
```

### Pattern 2: Async Engine and Session Factory

**What:** Centralized async engine + session factory in `switchboard/db/`.
**When to use:** All database access throughout the application.
**Example:**

```python
# switchboard/db/engine.py
# Source: SQLAlchemy 2.0 async docs
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from switchboard.config import get_settings


def create_engine() -> AsyncEngine:
    """Create the async SQLAlchemy engine.

    Uses postgresql+asyncpg:// driver. Never use plain postgresql://
    which silently blocks the event loop.
    """
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=settings.db_echo,
        pool_size=5,
        max_overflow=10,
    )
```

```python
# switchboard/db/session.py
# Source: SQLAlchemy 2.0 async docs
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from switchboard.db.engine import create_engine

# Create once at module level; reuse across requests
engine = create_engine()
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncSession:
    """Yield an async session for dependency injection.

    Used by FastAPI Depends() in Phase 2. Tests pass sessions directly.
    """
    async with async_session_factory() as session:
        yield session
```

### Pattern 3: Repository Pattern with Session Injection

**What:** `ServerRepository` encapsulates all SQL; accepts session as argument.
**When to use:** All data access for the server registry.
**Example:**

```python
# switchboard/registry/repository.py
# Source: CONTEXT.md D-09, D-10
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from switchboard.registry.models import Server, ServerStatus


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
        """Register a new MCP server."""
        server = Server(
            name=name,
            container_image=container_image,
            description=description,
        )
        session.add(server)
        await session.flush()
        await session.refresh(server)
        return server

    async def get_by_id(
        self, session: AsyncSession, server_id: uuid.UUID,
    ) -> Server | None:
        """Retrieve a server by its UUID."""
        return await session.get(Server, server_id)

    async def get_by_name(
        self, session: AsyncSession, name: str,
    ) -> Server | None:
        """Retrieve a server by its unique name."""
        stmt = select(Server).where(Server.name == name)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self, session: AsyncSession) -> list[Server]:
        """List all registered servers."""
        stmt = select(Server).order_by(Server.created_at.desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        session: AsyncSession,
        server_id: uuid.UUID,
        status: ServerStatus,
    ) -> Server | None:
        """Update a server's status."""
        server = await session.get(Server, server_id)
        if server is None:
            return None
        server.status = status
        await session.flush()
        await session.refresh(server)
        return server

    async def delete(
        self, session: AsyncSession, server_id: uuid.UUID,
    ) -> bool:
        """Delete a server by ID. Returns True if deleted."""
        server = await session.get(Server, server_id)
        if server is None:
            return False
        await session.delete(server)
        await session.flush()
        return True
```

### Pattern 4: pydantic-settings Configuration

**What:** Centralized settings via `pydantic-settings` with env var support.
**When to use:** All configuration access.
**Example:**

```python
# switchboard/config.py
# Source: pydantic-settings docs
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/switchboard"
    test_database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/switchboard_test"
    db_echo: bool = False


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
```

### Pattern 5: Alembic Async Configuration

**What:** Initialize Alembic with the `async` template for asyncpg compatibility.
**When to use:** Database migration management.
**Example initialization:**

```bash
# Initialize Alembic with async template -- CRITICAL: not the default template
alembic init -t async alembic
```

Key `env.py` modifications:

```python
# alembic/env.py (key sections)
# Source: Alembic async template + official cookbook
from switchboard.db.base import Base
from switchboard.config import get_settings

# Import all models so Base.metadata knows about them
from switchboard.registry import models  # noqa: F401

target_metadata = Base.metadata

def get_url() -> str:
    """Read DB URL from settings, not alembic.ini."""
    return get_settings().database_url
```

### Pattern 6: Test Fixtures with Transaction Rollback

**What:** Per-test transaction isolation using `join_transaction_mode="create_savepoint"`.
**When to use:** All integration tests that touch the database.
**Example:**

```python
# tests/conftest.py
# Source: SQLAlchemy 2.0 docs "Joining a Session into an External Transaction"
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    create_async_engine,
)

from switchboard.config import get_settings


@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def engine():
    """Create a session-scoped async engine for test database."""
    settings = get_settings()
    _engine = create_async_engine(
        settings.test_database_url,
        echo=False,
    )
    yield _engine
    await _engine.dispose()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def apply_migrations(engine):
    """Apply Alembic migrations once per test session (D-13)."""
    alembic_cfg = Config("alembic.ini")
    # Override the DB URL to point at the test database
    alembic_cfg.set_main_option(
        "sqlalchemy.url",
        get_settings().test_database_url.replace("+asyncpg", ""),
    )
    # Alembic runs migrations synchronously even for async databases
    command.upgrade(alembic_cfg, "head")
    yield
    command.downgrade(alembic_cfg, "base")


@pytest_asyncio.fixture
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Per-test async session with transaction rollback (D-13).

    Each test runs inside a transaction that is rolled back after
    completion, providing full isolation without touching disk.
    """
    async with engine.connect() as connection:
        async with connection.begin() as transaction:
            async_session = AsyncSession(
                bind=connection,
                join_transaction_mode="create_savepoint",
                expire_on_commit=False,
            )
            yield async_session
            await transaction.rollback()
```

### Anti-Patterns to Avoid

- **Using `postgresql://` instead of `postgresql+asyncpg://`:** Silently uses sync driver, blocks the event loop under load. Always use the full async driver URI. [VERIFIED: SQLAlchemy docs]
- **Using the default Alembic template with asyncpg:** The default template uses `engine_from_config()` which does not support async drivers. Use `alembic init -t async`. [VERIFIED: Alembic docs]
- **Creating the engine at import time in production code:** The engine in `session.py` module-level is acceptable for a single-process app, but should use a factory pattern for testability. Consider lazy initialization. [ASSUMED]
- **Committing inside repository methods:** Repository methods should `flush()` (for autoflush to work) but let the caller (API endpoint or test) control `commit()`. This ensures transaction boundaries are controlled at the service layer. [ASSUMED]
- **Mixing ORM models and Pydantic schemas:** Keep them separate (D-11). ORM models are for database persistence; Pydantic schemas are for API validation. Conversion happens at the boundary. [VERIFIED: CONTEXT.md D-11]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Database migrations | Custom SQL scripts | Alembic `alembic init -t async` | Tracks migration state, supports rollback, autogenerate from models |
| Configuration from env vars | Custom env parser | pydantic-settings `BaseSettings` | Validates types, supports `.env` files, nested models, secrets |
| UUID generation | Custom ID scheme | Python `uuid.uuid4()` + SQLAlchemy `Uuid` type | Standard, collision-resistant, database-native support |
| Connection pooling | Manual pool management | SQLAlchemy built-in pool (via `pool_size`/`max_overflow`) | Battle-tested, handles connection recycling and health checks |
| Enum type mapping | String columns + app-level validation | SQLAlchemy `Enum` type + Python `enum.Enum` | Database-level constraint enforcement, type safety |
| Test transaction isolation | Manual DELETE/TRUNCATE after each test | SQLAlchemy `join_transaction_mode="create_savepoint"` | Zero-cost rollback, no race conditions, no orphaned data |

## Common Pitfalls

### Pitfall 1: Alembic Autogenerate Does Not Handle PostgreSQL Enum Types Properly

**What goes wrong:** Alembic's `autogenerate` creates the enum type on first `upgrade` but does not drop it on `downgrade`. Running `downgrade` then `upgrade` again fails because the enum type already exists.
**Why it happens:** Alembic lacks built-in support for PostgreSQL enum type lifecycle management. [VERIFIED: Alembic GitHub issue #278]
**How to avoid:** In the initial migration that creates the `servers` table, explicitly add `sa.Enum(ServerStatus, name='serverstatus', create_type=True)` in the `upgrade()` and add `sa.Enum(name='serverstatus').drop(op.get_bind())` (or `op.execute('DROP TYPE IF EXISTS serverstatus')`) in the `downgrade()`. Alternatively, use the `alembic-postgresql-enum` package.
**Warning signs:** Migration runs fine the first time but fails on second `upgrade` after a `downgrade`.

### Pitfall 2: Alembic Needs Sync Driver for Migration Commands

**What goes wrong:** Alembic's CLI commands (`alembic upgrade head`) run synchronously. If `alembic.ini` or `env.py` points at `postgresql+asyncpg://`, the async template handles this correctly -- but the test fixture that calls `command.upgrade()` programmatically may need the sync URL.
**Why it happens:** Alembic's `command.upgrade()` is synchronous. The async template uses `asyncio.run()` internally, but if your test session already has a running event loop, `asyncio.run()` will fail.
**How to avoid:** For test fixtures, use `alembic.command.upgrade()` with a sync-compatible URL (replace `+asyncpg` with `+psycopg2` or use `psycopg` async mode). Alternatively, run migrations via subprocess: `subprocess.run(["alembic", "upgrade", "head"])`.
**Warning signs:** `RuntimeError: asyncio.run() cannot be called when another event loop is running`.

### Pitfall 3: pytest-asyncio Default Mode is "strict"

**What goes wrong:** Async test functions run as regular (sync) functions and silently pass without executing any assertions.
**Why it happens:** Since pytest-asyncio 0.26, the default mode is `strict`, meaning every async test must be explicitly decorated with `@pytest.mark.asyncio`. Without the decorator, pytest sees the coroutine return value as truthy and passes. [VERIFIED: pytest-asyncio docs]
**How to avoid:** Set `asyncio_mode = "auto"` in `pyproject.toml` under `[tool.pytest.ini_options]` so all async test functions are automatically detected. This is the recommended mode for projects that only use asyncio.
**Warning signs:** Tests pass suspiciously fast; async operations are not actually awaited.

### Pitfall 4: Missing Model Imports in Alembic env.py

**What goes wrong:** `alembic revision --autogenerate` produces an empty migration with no table operations.
**Why it happens:** Alembic reads `target_metadata` from `Base.metadata`, but if the ORM model modules are not imported, the metadata has no tables registered.
**How to avoid:** In `alembic/env.py`, explicitly import all model modules before referencing `Base.metadata`: `from switchboard.registry import models  # noqa: F401`.
**Warning signs:** Autogenerated migration file contains only `pass` in both `upgrade()` and `downgrade()`.

### Pitfall 5: SQLAlchemy Enum Type and Python Enum Value Mismatch

**What goes wrong:** Database stores the Python enum member name (e.g., `"STOPPED"`) when you expected the value (e.g., `"stopped"`).
**Why it happens:** SQLAlchemy's `Enum` type uses the enum member `.value` by default when `values_callable` is not specified and the enum inherits from `str`. But behavior depends on whether you define the enum as `class ServerStatus(str, enum.Enum)` vs `class ServerStatus(enum.Enum)`.
**How to avoid:** Use `class ServerStatus(enum.Enum)` (not inheriting from `str`). Define values explicitly: `stopped = "stopped"`. SQLAlchemy will use `.value` for storage. Verify by checking what appears in the database after insertion.
**Warning signs:** Query filters like `.where(Server.status == ServerStatus.stopped)` return no results despite data existing.

### Pitfall 6: `expire_on_commit=False` Required for Async Sessions

**What goes wrong:** Accessing attributes on an ORM object after `commit()` raises `MissingGreenlet` or `DetachedInstanceError`.
**Why it happens:** By default, SQLAlchemy expires all attributes on commit, and lazy loading is not available in async mode. Accessing an expired attribute triggers a synchronous SQL query, which fails in an async context.
**How to avoid:** Set `expire_on_commit=False` on both the `async_sessionmaker` and test `AsyncSession` instances. [VERIFIED: SQLAlchemy 2.0 async docs]
**Warning signs:** `sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called` after a commit.

## Code Examples

### Docker Compose for Development and Test Databases

```yaml
# docker-compose.yml
# Source: docker-patterns skill + CONTEXT.md D-12, D-14
services:
  db:
    image: postgres:16-alpine
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: switchboard
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./scripts/init-test-db.sql:/docker-entrypoint-initdb.d/init-test-db.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  pgdata:
```

```sql
-- scripts/init-test-db.sql
-- Create the test database alongside the dev database
CREATE DATABASE switchboard_test;
```

### Pydantic Schemas (Separate from ORM Models)

```python
# switchboard/registry/schemas.py
# Source: CONTEXT.md D-11
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from switchboard.registry.models import ServerStatus


class ServerCreate(BaseModel):
    """Schema for creating a new server."""
    name: str
    container_image: str
    description: str | None = None


class ServerRead(BaseModel):
    """Schema for reading server data."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    container_image: str
    description: str | None
    status: ServerStatus
    container_id: str | None
    created_at: datetime
    updated_at: datetime
```

### Server Name Validation Test

```python
# tests/registry/test_models.py
from __future__ import annotations

import pytest
from switchboard.registry.models import SERVER_NAME_PATTERN


@pytest.mark.parametrize("name,valid", [
    ("my-server", True),
    ("a1", False),           # Too short (min 3 chars)
    ("abc", True),           # Minimum valid length
    ("a" * 64, True),        # Maximum valid length
    ("a" * 65, False),       # Too long
    ("-invalid", False),     # Starts with hyphen
    ("invalid-", False),     # Ends with hyphen
    ("UPPERCASE", False),    # No uppercase
    ("has space", False),    # No spaces
    ("has_underscore", False),  # No underscores
    ("valid-server-01", True),
])
def test_server_name_validation(name: str, valid: bool) -> None:
    """Verify server name regex matches spec (D-08)."""
    if valid:
        assert SERVER_NAME_PATTERN.match(name)
    else:
        assert not SERVER_NAME_PATTERN.match(name)
```

### pyproject.toml Configuration

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "integration: marks tests requiring a running PostgreSQL instance",
]

[tool.ruff]
target-version = "py312"
line-length = 88

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "SIM", "TCH"]

[tool.ruff.lint.isort]
known-first-party = ["switchboard"]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `Column()` + `relationship()` | `Mapped[T]` + `mapped_column()` | SQLAlchemy 2.0 (Jan 2023) | Type-safe ORM, better IDE support, catches errors at type-check time |
| `engine_from_config()` for Alembic | `async_engine_from_config()` + async template | Alembic 1.12+ | Required for asyncpg; default template does not work with async drivers |
| `sessionmaker(class_=AsyncSession)` | `async_sessionmaker(expire_on_commit=False)` | SQLAlchemy 2.0 | Dedicated async factory; `expire_on_commit=False` is required for async |
| Manual savepoint management | `join_transaction_mode="create_savepoint"` | SQLAlchemy 2.0 | Cleaner test isolation; no need for manual `begin_nested()` calls |
| `pydantic.BaseSettings` | `pydantic_settings.BaseSettings` | Pydantic v2 (Jun 2023) | Settings split into separate `pydantic-settings` package |
| pytest-asyncio `strict` as opt-in | pytest-asyncio `strict` as default | 0.26.0 (Mar 2025) | Must explicitly set `asyncio_mode = "auto"` or decorate every async test |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Engine should use lazy initialization / factory pattern for testability rather than module-level creation | Anti-Patterns | LOW -- module-level is common in simple apps; factory pattern is a best practice but not strictly required |
| A2 | Repository methods should flush() but not commit(), leaving transaction control to the caller | Anti-Patterns | MEDIUM -- if the planner expects commit-per-method, test fixtures would need different isolation |
| A3 | Using subprocess or sync URL for Alembic commands in test fixtures avoids event loop conflicts | Pitfall 2 | MEDIUM -- the actual behavior depends on pytest-asyncio's event loop policy; may need experimentation |

## Open Questions

1. **Docker availability in WSL2**
   - What we know: Docker CLI is not available in this WSL2 environment (`docker` command fails with "could not be found in this WSL 2 distro"). Docker Desktop is installed on Windows but WSL integration is not enabled.
   - What's unclear: Whether the user intends to enable WSL2 Docker integration before starting Phase 1.
   - Recommendation: The user must enable Docker Desktop WSL2 integration (Settings > Resources > WSL Integration) before running `docker compose up` for PostgreSQL. Alternatively, install a standalone PostgreSQL instance in WSL2. The planner should include a prerequisite step that verifies Docker/PostgreSQL availability.

2. **Alembic migration runner in test fixtures**
   - What we know: `alembic.command.upgrade()` is synchronous. pytest-asyncio tests run in an async event loop. The Alembic async template uses `asyncio.run()` internally.
   - What's unclear: Whether calling `command.upgrade()` from within a `session`-scoped async fixture causes event loop conflicts in pytest-asyncio 0.26.x.
   - Recommendation: Use a session-scoped *synchronous* fixture (not `async`) for migrations, with a sync Alembic URL (replace `+asyncpg` with `+psycopg2`). This avoids the nested event loop issue entirely. Add `psycopg2-binary` as a dev dependency for this purpose.

3. **`ruff` not in venv**
   - What we know: `uv run ruff` fails currently because no dependencies are installed yet.
   - What's unclear: Nothing -- this is expected for a new project.
   - Recommendation: `uv add --dev ruff` as part of initial project setup.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | All code | Yes | 3.12.1 (pyenv) | -- |
| uv | Package management | Yes | 0.10.8 | -- |
| Docker / Docker Compose | PostgreSQL for dev/test (D-12) | No (WSL2 integration disabled) | -- | Enable WSL2 integration or install PostgreSQL natively |
| PostgreSQL | Server registry database | No (depends on Docker) | -- | `apt install postgresql` in WSL2 |
| ruff | Linting/formatting | No (not installed yet) | -- | `uv add --dev ruff` |

**Missing dependencies with no fallback:**
- Docker (or PostgreSQL) is REQUIRED for integration tests (D-12). The planner must address this as a prerequisite.

**Missing dependencies with fallback:**
- ruff -- installed via `uv add --dev ruff` as part of setup.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.26.x |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (Wave 0) |
| Quick run command | `uv run pytest tests/registry/ -x -q` |
| Full suite command | `uv run pytest --tb=short` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PLAT-03 | `import switchboard` succeeds | unit | `uv run python -c "import switchboard"` | No -- Wave 0 |
| SC-01 | Create server record in PostgreSQL | integration | `uv run pytest tests/registry/test_repository.py::test_create_server -x` | No -- Wave 0 |
| SC-02 | Read server by ID and by name | integration | `uv run pytest tests/registry/test_repository.py::test_get_server -x` | No -- Wave 0 |
| SC-03 | List all servers | integration | `uv run pytest tests/registry/test_repository.py::test_list_servers -x` | No -- Wave 0 |
| SC-04 | Delete server record | integration | `uv run pytest tests/registry/test_repository.py::test_delete_server -x` | No -- Wave 0 |
| SC-05 | Alembic upgrade + downgrade clean | integration | `uv run pytest tests/test_migrations.py -x` | No -- Wave 0 |
| SC-06 | Name validation rejects invalid patterns | unit | `uv run pytest tests/registry/test_models.py -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/registry/ -x -q`
- **Per wave merge:** `uv run pytest --tb=short`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/conftest.py` -- shared async engine, session, migration fixtures
- [ ] `tests/registry/__init__.py` -- test package marker
- [ ] `tests/registry/test_models.py` -- model validation tests (name regex, enum)
- [ ] `tests/registry/test_repository.py` -- CRUD integration tests
- [ ] `pyproject.toml` `[tool.pytest.ini_options]` section with `asyncio_mode = "auto"`
- [ ] Framework install: `uv add --dev pytest pytest-asyncio`

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Phase 5 concern |
| V3 Session Management | No | Phase 5 concern |
| V4 Access Control | No | No API surface in Phase 1 |
| V5 Input Validation | Yes | SQLAlchemy `@validates` for server name pattern; Pydantic schemas for data shapes |
| V6 Cryptography | No | No crypto in Phase 1 |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via server name | Tampering | SQLAlchemy ORM parameterizes all queries; `@validates` rejects malformed input |
| Database credential exposure | Information Disclosure | pydantic-settings reads from env vars; `.env` file in `.gitignore`; never hardcode |
| Enum bypass (invalid status value) | Tampering | PostgreSQL enum type + Python enum class enforces valid values at both layers |

## Sources

### Primary (HIGH confidence)
- [SQLAlchemy 2.0 Async I/O Documentation](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) -- async engine, session, mapped_column patterns
- [SQLAlchemy 2.0 Type Basics](https://docs.sqlalchemy.org/en/20/core/type_basics.html) -- `Uuid` generic type
- [Alembic 1.18.4 Cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html) -- async template, autogenerate
- [Alembic Async Template (GitHub)](https://github.com/sqlalchemy/alembic/blob/main/alembic/templates/async/env.py) -- reference env.py for async migrations
- [pytest-asyncio Configuration Docs](https://pytest-asyncio.readthedocs.io/en/latest/reference/configuration.html) -- asyncio_mode, loop_scope
- [pydantic-settings Documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) -- BaseSettings, env_prefix, SettingsConfigDict
- [SQLAlchemy "Joining a Session into an External Transaction"](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html) -- `join_transaction_mode="create_savepoint"` for test isolation

### Secondary (MEDIUM confidence)
- [Alembic PostgreSQL Enum Issue #278](https://github.com/sqlalchemy/alembic/issues/278) -- enum type autogenerate limitation confirmed
- [alembic-postgresql-enum PyPI](https://pypi.org/project/alembic-postgresql-enum/) -- third-party fix for enum migrations
- [SQLAlchemy Discussion #12792](https://github.com/sqlalchemy/sqlalchemy/discussions/12792) -- correct UUID usage with 2.0 ORM
- [SQLAlchemy Discussion #10857](https://github.com/sqlalchemy/sqlalchemy/discussions/10857) -- async external transaction pattern for tests
- [CORE27: Transactional Unit Tests with Async SQLAlchemy](https://www.core27.co/post/transactional-unit-tests-with-pytest-and-async-sqlalchemy) -- async test fixture patterns

### Tertiary (LOW confidence)
- None -- all critical claims verified with official documentation.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all library versions verified in prior STACK.md research (PyPI confirmed 2026-04-14)
- Architecture: HIGH -- patterns sourced from official SQLAlchemy 2.0 and Alembic docs, locked by CONTEXT.md decisions
- Pitfalls: HIGH -- each pitfall traced to official docs, GitHub issues, or confirmed community patterns
- Test strategy: MEDIUM -- async test fixture pattern (`join_transaction_mode`) is well-documented but the exact interaction with pytest-asyncio 0.26.x session-scoped fixtures needs validation (Open Question #2)

**Research date:** 2026-04-14
**Valid until:** 2026-05-14 (stable libraries, no major releases expected)
