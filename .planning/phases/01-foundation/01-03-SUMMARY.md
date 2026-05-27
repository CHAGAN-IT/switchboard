---
phase: 01-foundation
plan: 03
subsystem: database
tags: [sqlalchemy, asyncpg, postgres, repository-pattern, alembic, pytest-asyncio]

# Dependency graph
requires:
  - phase: 01-foundation-02
    provides: Server ORM model, Alembic migrations, Pydantic schemas
provides:
  - ServerRepository with 7 async CRUD methods (create, get_by_id, get_by_name, list_all, update_status, update_container_id, delete)
  - Integration test fixtures with per-test transaction rollback
  - Verified Alembic migration cycle (upgrade/downgrade/re-upgrade)
affects: [02-admin-api, 03-gateway]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Repository pattern: session-injected async CRUD methods with flush-not-commit"
    - "Per-test transaction rollback via SQLAlchemy savepoint join mode"
    - "Subprocess-based Alembic migrations in test fixtures to avoid event loop conflicts"

key-files:
  created:
    - switchboard/registry/repository.py
    - tests/conftest.py
    - tests/registry/test_repository.py
    - tests/test_migrations.py
  modified: []

key-decisions:
  - "Repository methods flush() but never commit() -- transaction boundaries owned by caller"
  - "Engine fixture is per-test (not session-scoped) to avoid asyncpg event loop mismatch with pytest-asyncio 1.3.0"
  - "Alembic subprocess receives async URL directly since env.py uses async_engine_from_config"
  - "DuplicateServerError raised on IntegrityError with session.rollback() to reset savepoint state"

patterns-established:
  - "Repository pattern: all DB access through ServerRepository, never raw queries"
  - "Test isolation: per-test transaction rollback via begin() + create_savepoint join mode"
  - "Migration testing: subprocess-based Alembic commands to avoid event loop conflicts"

requirements-completed: [PLAT-03]

# Metrics
duration: 14min
completed: 2026-04-14
---

# Phase 01 Plan 03: Repository and Integration Tests Summary

**ServerRepository with 7 async CRUD methods verified against PostgreSQL via 14 integration tests with per-test transaction rollback isolation**

## Performance

- **Duration:** 14 min
- **Started:** 2026-04-14T14:59:00Z
- **Completed:** 2026-04-14T15:13:06Z
- **Tasks:** 1 (TDD task with RED/GREEN commits from prior session, plus test fixes in this session)
- **Files modified:** 4

## Accomplishments
- ServerRepository with all 7 async CRUD methods: create, get_by_id, get_by_name, list_all, update_status, update_container_id, delete
- 14 integration tests covering all CRUD operations including edge cases (duplicate names, nonexistent IDs, empty lists)
- Per-test transaction rollback isolation via SQLAlchemy savepoint join mode
- Alembic migration cycle test verifying upgrade/downgrade/re-upgrade without errors
- All 35 tests pass (20 model + 14 repository + 1 migration)

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests for ServerRepository and migrations** - `dde3f98` (test)
2. **Task 1 GREEN: ServerRepository implementation with all CRUD methods** - `9fed0c0` (feat)
3. **Task 1 FIX: Resolve test infrastructure issues for PostgreSQL** - `4f64274` (fix)

## Files Created/Modified
- `switchboard/registry/repository.py` - ServerRepository with 7 async CRUD methods using SQLAlchemy ORM
- `tests/conftest.py` - Shared fixtures: session-scoped Alembic migrations, per-test engine and session with rollback
- `tests/registry/test_repository.py` - 14 integration tests for all repository operations
- `tests/test_migrations.py` - Alembic upgrade/downgrade/re-upgrade cycle verification

## Decisions Made
- **Repository flush-not-commit pattern:** Repository methods call `flush()` but never `commit()`, letting the caller (API endpoint or test fixture) control transaction boundaries. This enables per-test rollback and batched operations.
- **Per-test engine scope:** Changed engine fixture from session-scoped to per-test to avoid `asyncpg` event loop mismatch errors. pytest-asyncio 1.3.0 creates a new event loop per test function, and asyncpg connections are bound to the loop they were created on.
- **Async URL for Alembic subprocess:** `alembic/env.py` uses `async_engine_from_config` internally, so the test subprocess must pass the `postgresql+asyncpg://` URL (not the sync `postgresql://` URL). The prior approach of stripping `+asyncpg` caused `psycopg2` to be loaded, which is incompatible with the async engine.
- **Deterministic ordering assertion:** Changed `test_list_all_returns_servers` to assert `created_at` is non-increasing rather than checking exact name order, since sub-millisecond inserts can produce equal timestamps.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Alembic subprocess URL must be async**
- **Found during:** Task 1 (running integration tests)
- **Issue:** Test fixtures passed sync URL (`postgresql://...`) to Alembic subprocess, but `env.py` uses `async_engine_from_config` which requires `postgresql+asyncpg://...`
- **Fix:** Removed `.replace("+asyncpg", "")` from conftest.py and test_migrations.py; pass async URL directly
- **Files modified:** tests/conftest.py, tests/test_migrations.py
- **Verification:** Alembic upgrade/downgrade succeeds; migration test passes
- **Committed in:** 4f64274

**2. [Rule 1 - Bug] Session-scoped engine causes event loop mismatch**
- **Found during:** Task 1 (running integration tests)
- **Issue:** Session-scoped async engine created asyncpg connections on the first test's event loop; subsequent tests run on different loops, causing `RuntimeError: Task got Future attached to a different loop`
- **Fix:** Changed engine fixture from `scope="session"` to per-test (default scope). Each test gets its own engine on its own event loop.
- **Files modified:** tests/conftest.py
- **Verification:** All 35 tests pass without event loop errors
- **Committed in:** 4f64274

**3. [Rule 1 - Bug] Non-deterministic ordering assertion**
- **Found during:** Task 1 (running integration tests)
- **Issue:** `test_list_all_returns_servers` asserted exact name order (`server-bbb` first), but sub-millisecond inserts produce equal `created_at` timestamps, making order indeterminate
- **Fix:** Changed assertion to verify `created_at` values are non-increasing (descending order invariant) instead of checking specific names
- **Files modified:** tests/registry/test_repository.py
- **Verification:** Test passes reliably across multiple runs
- **Committed in:** 4f64274

---

**Total deviations:** 3 auto-fixed (3 bugs)
**Impact on plan:** All fixes necessary for correct test execution against real PostgreSQL. No scope creep.

## Issues Encountered
- `switchboard_test` database did not exist on PostgreSQL instance. Created via asyncpg direct connection before running tests.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Full data layer complete: models, schemas, migrations, and repository all verified against PostgreSQL
- ServerRepository ready for FastAPI endpoint integration in Phase 2 (Admin API)
- Test infrastructure (fixtures, transaction rollback) ready for future integration tests
- No blockers for Phase 2

## Self-Check: PASSED

- [x] `switchboard/registry/repository.py` exists
- [x] `tests/conftest.py` exists
- [x] `tests/registry/test_repository.py` exists
- [x] `tests/test_migrations.py` exists
- [x] Commit `dde3f98` exists (test RED)
- [x] Commit `9fed0c0` exists (feat GREEN)
- [x] Commit `4f64274` exists (fix)
- [x] `01-03-SUMMARY.md` exists

---
*Phase: 01-foundation*
*Completed: 2026-04-14*
