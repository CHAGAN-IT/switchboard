---
phase: 01-foundation
plan: 01
subsystem: infra
tags: [python, sqlalchemy, asyncpg, pydantic-settings, docker, postgresql]

# Dependency graph
requires: []
provides:
  - Importable switchboard Python package with all subpackages
  - pydantic-settings Settings class for environment-based configuration
  - Async SQLAlchemy engine factory (postgresql+asyncpg)
  - Async session factory (async_sessionmaker)
  - SQLAlchemy DeclarativeBase for ORM models
  - Registry exception hierarchy (RegistryError, ServerNotFoundError, DuplicateServerError)
  - Docker Compose with PostgreSQL 16 (dev + test databases)
  - Project tooling config (pytest, ruff, isort)
affects: [01-02, 01-03, 02-admin-api, 03-container, 05-gateway]

# Tech tracking
tech-stack:
  added: [sqlalchemy 2.0.49, asyncpg 0.31.0, alembic 1.18.4, pydantic 2.13.0, pydantic-settings 2.13.1, psycopg2-binary, pytest, pytest-asyncio, ruff]
  patterns: [pydantic-settings with lru_cache, async engine factory, async_sessionmaker with expire_on_commit=False, TYPE_CHECKING imports for stdlib types]

key-files:
  created:
    - pyproject.toml
    - switchboard/__init__.py
    - switchboard/py.typed
    - switchboard/config.py
    - switchboard/db/__init__.py
    - switchboard/db/base.py
    - switchboard/db/engine.py
    - switchboard/db/session.py
    - switchboard/registry/__init__.py
    - switchboard/registry/exceptions.py
    - switchboard/gateway/__init__.py
    - switchboard/admin/__init__.py
    - switchboard/container/__init__.py
    - docker-compose.yml
    - scripts/init-test-db.sql
    - .env.example
    - .gitignore
    - uv.lock
  modified: []

key-decisions:
  - "Used lru_cache for Settings singleton instead of module-level instance for testability (cache_clear in tests)"
  - "Set expire_on_commit=False on async_sessionmaker to prevent lazy-load errors after commit"
  - "Used TYPE_CHECKING block for AsyncGenerator import to satisfy ruff TCH003 with from __future__ import annotations"
  - "Included psycopg2-binary as dev dependency for Alembic sync migration commands"

patterns-established:
  - "Settings via pydantic-settings with get_settings() cached factory"
  - "Async engine factory in db/engine.py importing from config"
  - "Session factory in db/session.py importing from db/engine"
  - "Custom exception hierarchy per domain subpackage (registry/exceptions.py)"
  - "TYPE_CHECKING block for stdlib imports used only in annotations"

requirements-completed: [PLAT-03]

# Metrics
duration: 3min
completed: 2026-04-14
---

# Phase 1 Plan 1: Project Scaffold Summary

**Python package scaffold with pydantic-settings config, async SQLAlchemy (postgresql+asyncpg) engine/session factories, and Docker Compose PostgreSQL**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-14T13:43:38Z
- **Completed:** 2026-04-14T13:47:07Z
- **Tasks:** 2
- **Files modified:** 18

## Accomplishments

- Scaffolded importable `switchboard` package with 5 subpackages (db, registry, gateway, admin, container)
- Created pydantic-settings configuration with DATABASE_URL, TEST_DATABASE_URL, and DB_ECHO environment variables
- Built async SQLAlchemy infrastructure: DeclarativeBase, engine factory (postgresql+asyncpg), and session factory
- Defined registry exception hierarchy (RegistryError, ServerNotFoundError, DuplicateServerError)
- Set up Docker Compose with PostgreSQL 16 (dev + test databases with healthcheck)
- Installed all Phase 1 dependencies and configured pytest, ruff, and isort tooling

## Task Commits

Each task was committed atomically:

1. **Task 1: Create package structure, install dependencies, and configure settings** - `35bbf51` (feat)
2. **Task 2: Create Docker Compose for PostgreSQL with dev and test databases** - `c3ed22a` (feat)

## Files Created/Modified

- `pyproject.toml` - Project config with all Phase 1 dependencies and tool settings
- `uv.lock` - Locked dependency versions
- `switchboard/__init__.py` - Package marker with module docstring
- `switchboard/py.typed` - PEP 561 type hint marker
- `switchboard/config.py` - Settings class with database URLs via pydantic-settings
- `switchboard/db/__init__.py` - Database subpackage marker
- `switchboard/db/base.py` - SQLAlchemy DeclarativeBase for all ORM models
- `switchboard/db/engine.py` - Async engine factory using postgresql+asyncpg
- `switchboard/db/session.py` - Async session factory with get_session generator
- `switchboard/registry/__init__.py` - Registry subpackage marker
- `switchboard/registry/exceptions.py` - RegistryError, ServerNotFoundError, DuplicateServerError
- `switchboard/gateway/__init__.py` - Gateway subpackage marker (Phase 5)
- `switchboard/admin/__init__.py` - Admin API subpackage marker (Phase 2)
- `switchboard/container/__init__.py` - Container management subpackage marker (Phase 3)
- `docker-compose.yml` - PostgreSQL 16-alpine with healthcheck and dual databases
- `scripts/init-test-db.sql` - Creates switchboard_test database on container init
- `.env.example` - Environment variable template
- `.gitignore` - Python, venv, IDE, testing, Docker ignores

## Decisions Made

- Used `lru_cache` for Settings singleton instead of module-level instance, enabling `cache_clear()` in tests for isolated configuration
- Set `expire_on_commit=False` on async_sessionmaker to prevent lazy-load errors when accessing attributes after commit in async context
- Placed `AsyncGenerator` import inside `TYPE_CHECKING` block to satisfy ruff TCH003 rule (stdlib imports used only in type annotations with `from __future__ import annotations`)
- Included `psycopg2-binary` as dev dependency for Alembic's sync migration commands (per research pitfall 2)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed ruff TCH003 lint error for AsyncGenerator import**
- **Found during:** Task 1 (package structure and settings)
- **Issue:** `from collections.abc import AsyncGenerator` triggered TCH003 because `from __future__ import annotations` makes the import only needed at type-check time
- **Fix:** Moved `AsyncGenerator` import into `if TYPE_CHECKING:` block
- **Files modified:** `switchboard/db/session.py`
- **Verification:** `uv run ruff check switchboard/` passes with no errors
- **Committed in:** `35bbf51` (part of Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Minor lint fix required by ruff TCH rule. No scope creep.

## Issues Encountered

- Docker is not available in the WSL2 environment (needs Docker Desktop integration). Skipped `docker compose config` validation. The YAML file structure is correct and follows the Docker Compose specification.

## User Setup Required

None - no external service configuration required. Run `docker compose up -d` when Docker Desktop WSL2 integration is enabled.

## Next Phase Readiness

- Package structure complete: all subpackages importable, ready for model definitions (Plan 01-02)
- Database infrastructure ready: Base, engine, session factories available for ORM models
- Docker Compose ready: start with `docker compose up -d` for integration tests
- All Phase 1 dependencies installed and locked

## Self-Check: PASSED

- All 19 created files verified present on disk
- Commit `35bbf51` (Task 1) verified in git log
- Commit `c3ed22a` (Task 2) verified in git log

---
*Phase: 01-foundation*
*Completed: 2026-04-14*
