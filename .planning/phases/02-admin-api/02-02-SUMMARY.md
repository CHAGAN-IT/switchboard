---
phase: 02-admin-api
plan: 02
subsystem: testing
tags: [pytest, jwt, fastapi, httpx, asyncio, pydantic]

# Dependency graph
requires:
  - phase: 02-admin-api/01
    provides: "Admin API production code (app, auth, router, schemas)"
  - phase: 01-foundation
    provides: "DB models, migrations, conftest fixtures (session, engine)"
provides:
  - "14 passing tests covering JWT auth and all SREG endpoints"
  - "Test infrastructure (conftest.py) with async client fixtures"
  - "make_operator_token helper for generating test JWTs"
affects: [03-container-lifecycle, 05-gateway]

# Tech tracking
tech-stack:
  added: [httpx ASGITransport]
  patterns: [httpx.AsyncClient for async endpoint tests, sync TestClient for auth-rejection tests]

key-files:
  created:
    - tests/admin/__init__.py
    - tests/admin/conftest.py
    - tests/admin/test_auth.py
    - tests/admin/test_endpoints.py
  modified:
    - switchboard/admin/auth.py
    - switchboard/admin/router.py

key-decisions:
  - "Used httpx.AsyncClient + ASGITransport instead of sync TestClient for DB-dependent tests to avoid event loop mismatch"
  - "Separated unauthenticated_client (sync, no DB) from client (async, with DB) for clean fixture responsibility"
  - "Fixed runtime type resolution bug: Settings and AsyncSession must be runtime imports when used with FastAPI Depends()"

patterns-established:
  - "Async test client pattern: httpx.AsyncClient + ASGITransport for tests needing async DB sessions"
  - "Auth test helper: make_operator_token() for generating JWTs with configurable expiration"
  - "Dependency override pattern: override get_session + get_settings, never override require_operator"

requirements-completed: [SREG-01, SREG-02, SREG-03]

# Metrics
duration: 9min
completed: 2026-04-15
---

# Phase 02 Plan 02: Admin API Test Suite Summary

**14 passing tests for JWT auth (missing/invalid/expired/valid tokens) and all SREG endpoints (register/list/get with success and error paths), plus OpenAPI docs smoke test**

## Performance

- **Duration:** 9 min
- **Started:** 2026-04-15T02:40:43Z
- **Completed:** 2026-04-15T02:49:21Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- 4 JWT auth unit tests verifying 401 on missing/invalid/expired tokens and 200 on valid tokens
- 10 endpoint integration tests covering SREG-01 (register with 201/409/422), SREG-02 (list with empty/populated), SREG-03 (get with 200/404), plus OpenAPI docs accessibility
- Fixed critical runtime bug: FastAPI Depends() type annotations under TYPE_CHECKING block caused 422 instead of proper dependency injection
- Full test suite (68 tests: Phase 1 + Phase 2) passes without regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Create test infrastructure and JWT auth unit tests** - `35b8a81` (test)
2. **Task 2: Create endpoint integration tests and OpenAPI smoke test** - `ae15b1a` (test)

## Files Created/Modified
- `tests/admin/__init__.py` - Package marker for admin test directory
- `tests/admin/conftest.py` - Test fixtures: async client, auth headers, token helper, dependency overrides
- `tests/admin/test_auth.py` - 4 JWT auth dependency unit tests (missing/invalid/expired/valid tokens)
- `tests/admin/test_endpoints.py` - 10 endpoint integration tests (register, list, get, OpenAPI docs)
- `switchboard/admin/auth.py` - Fixed Settings import from TYPE_CHECKING to runtime (FastAPI needs it for Depends)
- `switchboard/admin/router.py` - Fixed AsyncSession import from TYPE_CHECKING to runtime; added ValueError handling for ORM name validation

## Decisions Made
- Used httpx.AsyncClient + ASGITransport instead of sync TestClient for DB-dependent tests. Sync TestClient creates a separate blocking portal/event loop that conflicts with pytest-asyncio's async session fixtures, causing "attached to a different loop" errors.
- Kept sync TestClient for auth-rejection tests (unauthenticated_client) since those tests never reach the DB layer and don't need async session fixtures.
- Fixed production code bugs inline (Rule 1 deviations) rather than deferring, since the tests would not pass without the fixes.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed TYPE_CHECKING import causing FastAPI dependency resolution failure**
- **Found during:** Task 1 (JWT auth unit tests)
- **Issue:** In `auth.py`, `Settings` was imported under `TYPE_CHECKING` but used in `Annotated[Settings, Depends(get_settings)]`. With `from __future__ import annotations`, the type becomes a string at runtime. FastAPI's `get_type_hints()` failed to resolve `Settings` (not in module globals), causing it to treat `settings` as a query parameter instead of a dependency. Result: 422 instead of 401 for invalid tokens.
- **Fix:** Moved `Settings` import from `TYPE_CHECKING` block to runtime import in `auth.py`. Applied same fix to `AsyncSession` in `router.py`.
- **Files modified:** `switchboard/admin/auth.py`, `switchboard/admin/router.py`
- **Verification:** All 4 auth tests pass with correct 401 responses
- **Committed in:** 35b8a81 (Task 1 commit)

**2. [Rule 1 - Bug] Fixed unhandled ValueError from ORM name validation**
- **Found during:** Task 2 (endpoint tests)
- **Issue:** Server name "A" passed Pydantic ServerCreate validation (no name validator) but failed ORM-level `@validates("name")` with a `ValueError`. The router's `register_server` only caught `DuplicateServerError`, so the ValueError propagated as a 500.
- **Fix:** Added `except ValueError` handler in `register_server` that returns 422 with the validation error message.
- **Files modified:** `switchboard/admin/router.py`
- **Verification:** `test_register_server_invalid_name_422` passes with 422 response
- **Committed in:** ae15b1a (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both auto-fixes necessary for correctness. No scope creep. The TYPE_CHECKING bug would have prevented any authenticated API usage from working correctly.

## Issues Encountered
- Event loop mismatch between sync TestClient and pytest-asyncio async sessions -- resolved by switching to httpx.AsyncClient + ASGITransport for DB-dependent tests.
- Deprecation warning for `HTTP_422_UNPROCESSABLE_ENTITY` -- replaced with `HTTP_422_UNPROCESSABLE_CONTENT`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All SREG requirements tested and verified
- Test infrastructure (conftest.py, helpers) ready for Phase 3+ extension
- 68 total tests passing across Phase 1 and Phase 2

## Self-Check: PASSED

All created files verified present. All commit hashes verified in git log.

---
*Phase: 02-admin-api*
*Completed: 2026-04-15*
