# Phase 1: Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-14
**Phase:** 01-foundation
**Areas discussed:** Package structure, Server registry schema, Database access pattern, Test database strategy

---

## Package structure

| Option | Description | Selected |
|--------|-------------|----------|
| Flat | All modules at top level (models.py, db.py, registry.py) | |
| Domain-layered subpackages | switchboard/db/, switchboard/registry/ etc. | |
| Feature-grouped subpackages | switchboard/registry/, switchboard/gateway/, switchboard/admin/, switchboard/container/ | ✓ |

**User's choice:** Feature-grouped subpackages

---

| Option | Description | Selected |
|--------|-------------|----------|
| Stub them all now | Create all subpackages as empty packages with __init__.py | ✓ |
| Only registry/ for now | Create only registry/ in Phase 1 | |
| registry/ plus shared db/ | registry/ + db/ for database config | |

**User's choice:** Stub them all now — all subpackages visible from day one

---

| Option | Description | Selected |
|--------|-------------|----------|
| switchboard/db/ subpackage | engine.py, session.py, base.py | ✓ |
| switchboard/core/ subpackage | Cross-cutting infrastructure | |
| Top-level switchboard/db.py | Single module at top level | |

**User's choice:** switchboard/db/ subpackage

---

| Option | Description | Selected |
|--------|-------------|----------|
| switchboard/config.py with pydantic-settings | Settings class, reads from env vars / .env | ✓ |
| switchboard/db/ includes settings | DB config inside db/ | |
| Environment variables directly | os.environ reads inline | |

**User's choice:** switchboard/config.py with pydantic-settings

---

## Server registry schema

| Option | Description | Selected |
|--------|-------------|----------|
| UUID | UUID v4 generated server-side | ✓ |
| Auto-increment integer | SERIAL or BIGSERIAL | |
| Server name as primary key | Name field as PK | |

**User's choice:** UUID

---

| Option | Description | Selected |
|--------|-------------|----------|
| stopped / running / error | Three states covering the lifecycle | ✓ |
| pending / stopped / running / error | Adds transitional pending state | |
| Full lifecycle (6 states) | registered / starting / running / stopping / stopped / error | |

**User's choice:** stopped / running / error

---

| Option | Description | Selected |
|--------|-------------|----------|
| created_at + updated_at timestamps only | Standard audit columns | |
| Timestamps + container_id column | Also store running container's Docker ID | ✓ |
| Timestamps + container_id + port + network_name | Full container runtime context | |

**User's choice:** Timestamps + container_id

---

| Option | Description | Selected |
|--------|-------------|----------|
| Optional (nullable) | Allow registering without a description | ✓ |
| Required (non-nullable) | Force documentation at registration time | |

**User's choice:** Optional (nullable)

---

## Database access pattern

| Option | Description | Selected |
|--------|-------------|----------|
| Repository class | ServerRepository with async methods | ✓ |
| Direct ORM in service layer | Business logic calls SQLAlchemy directly | |
| Thin CRUD functions | Module-level async functions, no class | |

**User's choice:** Repository class

---

| Option | Description | Selected |
|--------|-------------|----------|
| AsyncSession factory via dependency injection | async_sessionmaker; repository accepts session arg | ✓ |
| Repository owns its session | Repository creates/manages its own session | |
| Context manager sessions | async with get_session() per operation | |

**User's choice:** AsyncSession factory via dependency injection

---

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, separate from day one | ORM models in models.py, Pydantic in schemas.py | ✓ |
| Single Pydantic model with SQLAlchemy | SQLModel merged approach | |
| Start merged, split later | Dataclass/dict initially, refactor in Phase 2 | |

**User's choice:** Yes, separate from day one

---

## Test database strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Require docker compose up before tests | Pre-running Postgres, pytest fixture applies migrations | ✓ |
| testcontainers-python fixture | Auto-spin PostgreSQL container per test session | |
| SQLite for unit tests, real PG for integration | Mixed dialect approach | |

**User's choice:** Require docker compose up before tests

---

| Option | Description | Selected |
|--------|-------------|----------|
| Transaction rollback per test | Each test runs inside a rolled-back transaction | ✓ |
| Truncate tables between tests | Fixture truncates all tables after each test | |
| Fresh schema per test module | Drop/recreate schema between modules | |

**User's choice:** Transaction rollback per test

---

| Option | Description | Selected |
|--------|-------------|----------|
| Separate test database | switchboard_test via TEST_DATABASE_URL | ✓ |
| Same database with schema isolation | Dev DB but separate schema | |
| Same database, rely on rollback | Dev DB, no separate database | |

**User's choice:** Separate test database (switchboard_test)

---

## Claude's Discretion

- Alembic migration file naming and env.py configuration
- conftest.py fixture structure
- Logging setup in switchboard/db/
- SQLAlchemy pool configuration

## Deferred Ideas

None.
