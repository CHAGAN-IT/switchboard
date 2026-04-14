---
phase: 01-foundation
plan: 02
subsystem: database
tags: [sqlalchemy, pydantic, alembic, asyncpg, postgresql, orm]

# Dependency graph
requires:
  - phase: 01-foundation-01
    provides: "Base declarative class, Settings with database_url, package structure"
provides:
  - "Server ORM model with all D-06 columns and D-08 name validation"
  - "ServerStatus enum (stopped, running, error)"
  - "ServerCreate and ServerRead Pydantic schemas"
  - "Alembic async migration infrastructure"
  - "Initial migration creating servers table"
affects: [01-foundation-03, 02-admin-api]

# Tech tracking
tech-stack:
  added: []
  patterns: [sqlalchemy-mapped-column, pydantic-orm-separation, alembic-async-template]

key-files:
  created:
    - switchboard/registry/models.py
    - switchboard/registry/schemas.py
    - alembic.ini
    - alembic/env.py
    - alembic/versions/a5578b684627_create_servers_table.py
    - tests/registry/test_models.py
  modified:
    - pyproject.toml

key-decisions:
  - "Manual migration creation due to no PostgreSQL in CI -- migration matches autogenerate output"
  - "Added ruff runtime-evaluated-base-classes config for SQLAlchemy/Pydantic TCH rule compatibility"

patterns-established:
  - "ORM models in switchboard/registry/models.py with @validates for domain constraints"
  - "Pydantic schemas separate from ORM models (D-11) in switchboard/registry/schemas.py"
  - "Alembic env.py reads URL from pydantic-settings, imports all models for metadata registration"
  - "Migration downgrade explicitly drops PostgreSQL enum types"

requirements-completed: [PLAT-03]

# Metrics
duration: 6min
completed: 2026-04-14
---

# Phase 01 Plan 02: Server Model & Migrations Summary

**Server ORM model with UUID PK, name regex validation, ServerStatus enum, Pydantic schemas, and Alembic async migration for the servers table**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-14T13:51:09Z
- **Completed:** 2026-04-14T13:57:00Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- Server ORM model with all 8 columns from D-06, UUID v4 primary key (D-04), ServerStatus enum (D-05), and name validation regex (D-08)
- Separate Pydantic ServerCreate and ServerRead schemas for API serialization (D-11)
- Alembic initialized with async template for asyncpg compatibility, env.py reads URL from pydantic-settings
- Initial migration creates servers table with all columns, indexes, and enum type; downgrade cleans up enum
- 20 unit tests covering name pattern validation, enum membership, ORM @validates, and schema construction

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Server ORM model and Pydantic schemas (TDD)**
   - `6f1f197` (test) - failing tests for Server model and schemas
   - `4bcfca0` (feat) - implement Server ORM model and Pydantic schemas
2. **Task 2: Initialize Alembic with async template and create initial migration** - `02d5a35` (feat)

## Files Created/Modified
- `switchboard/registry/models.py` - Server ORM model, ServerStatus enum, SERVER_NAME_PATTERN regex
- `switchboard/registry/schemas.py` - ServerCreate and ServerRead Pydantic schemas
- `tests/__init__.py` - Test package marker
- `tests/registry/__init__.py` - Registry test package marker
- `tests/registry/test_models.py` - 20 unit tests for models and schemas
- `alembic.ini` - Alembic configuration with empty sqlalchemy.url
- `alembic/env.py` - Async migration environment reading URL from settings
- `alembic/script.py.mako` - Migration file template (generated)
- `alembic/versions/a5578b684627_create_servers_table.py` - Initial migration
- `pyproject.toml` - Added ruff runtime-evaluated-base-classes for TCH rules

## Decisions Made
- **Manual migration creation:** PostgreSQL was not available in the execution environment, so the migration was written manually matching what autogenerate would produce. The migration includes all D-06 columns with correct types.
- **Ruff TCH configuration:** Added `runtime-evaluated-base-classes` for `pydantic.BaseModel`, `sqlalchemy.orm.DeclarativeBase`, and `switchboard.db.base.Base` to prevent false TC003 warnings on imports used at runtime by ORMs.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added ruff runtime-evaluated-base-classes config**
- **Found during:** Task 1 (GREEN phase lint check)
- **Issue:** Ruff TC003 rules flagged `datetime`, `uuid`, and `ServerStatus` imports as type-only, but SQLAlchemy and Pydantic evaluate these at runtime via `Mapped[]` and `BaseModel` annotations
- **Fix:** Added `[tool.ruff.lint.flake8-type-checking]` section to pyproject.toml with runtime-evaluated-base-classes for Pydantic and SQLAlchemy
- **Files modified:** `pyproject.toml`
- **Verification:** `uv run ruff check switchboard/registry/` passes clean
- **Committed in:** `4bcfca0` (Task 1 GREEN commit)

**2. [Rule 3 - Blocking] Manual migration creation (no PostgreSQL available)**
- **Found during:** Task 2 (autogenerate step)
- **Issue:** `alembic revision --autogenerate` requires a running PostgreSQL instance; connection refused on localhost:5432
- **Fix:** Created migration file manually with all D-06 columns, matching autogenerate output format
- **Files modified:** `alembic/versions/a5578b684627_create_servers_table.py`
- **Verification:** Migration file contains create_table with all columns, downgrade drops table and enum
- **Committed in:** `02d5a35` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 blocking)
**Impact on plan:** Both auto-fixes necessary for completing tasks. No scope creep.

## Issues Encountered
None beyond the blocking issues documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Server ORM model and Pydantic schemas ready for repository layer (Plan 03)
- Alembic migration infrastructure ready; migrations can be run once PostgreSQL is available
- All exports (Server, ServerStatus, SERVER_NAME_PATTERN, ServerCreate, ServerRead) available for import

## Self-Check: PASSED

All 10 created files verified present. All 3 task commits (6f1f197, 4bcfca0, 02d5a35) verified in git log.

---
*Phase: 01-foundation*
*Completed: 2026-04-14*
