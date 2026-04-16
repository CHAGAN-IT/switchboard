---
phase: 05-gateway
plan: 01
subsystem: auth
tags: [jwt, pyjwt, structlog, respx, fastapi, pytest, tdd]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: pyproject.toml, uv toolchain, switchboard/ package structure
  - phase: 02-admin-api
    provides: switchboard/admin/auth.py (require_operator pattern to mirror)
    provides: switchboard/config.py (Settings with operator_jwt_secret pattern)
provides:
  - structlog and respx installed as project dependencies
  - Settings.customer_jwt_secret with 32-byte minimum validator
  - switchboard/gateway/auth.py with require_customer FastAPI dependency
  - tests/gateway/ package with conftest, 6 auth unit tests, 13 stub tests
affects:
  - 05-gateway/05-02: gateway app depends on require_customer and CUSTOMER_JWT_SECRET
  - 05-gateway/05-03: logging tests depend on structlog

# Tech tracking
tech-stack:
  added:
    - structlog>=25.0 (structured JSON logging for CloudWatch)
    - respx>=0.22.0 (httpx mock for reverse proxy tests, dev dependency)
  patterns:
    - require_customer mirrors require_operator with customer_jwt_secret and audience=switchboard-gateway
    - minimal FastAPI TestClient pattern for unit-testing auth dependencies without DB
    - pytest.mark.skip stubs for Wave 0 test files ahead of implementation

key-files:
  created:
    - switchboard/gateway/auth.py
    - tests/gateway/__init__.py
    - tests/gateway/conftest.py
    - tests/gateway/test_auth.py
    - tests/gateway/test_proxy.py
    - tests/gateway/test_session.py
    - tests/gateway/test_wellknown.py
    - tests/gateway/test_logging.py
  modified:
    - pyproject.toml (added structlog, respx)
    - uv.lock (updated)
    - switchboard/config.py (added customer_jwt_secret field and validator)
    - tests/conftest.py (added CUSTOMER_JWT_SECRET setdefault)

key-decisions:
  - "Minimal FastAPI TestClient pattern: create a test-only FastAPI app with a single protected route in test_auth.py so auth unit tests run immediately without Plan 02 gateway app"
  - "Wave 0 stub test files use @pytest.mark.skip so pytest collects them cleanly without errors before implementation"
  - "customer_jwt_secret validator identical to operator_jwt_secret: same 32-byte minimum for parity"
  - "wrong_secret test uses 31-byte key intentionally (below minimum) to trigger PyJWT InsecureKeyLengthWarning in test — this is expected behavior"

patterns-established:
  - "Pattern 1: Auth dependency mirroring — require_customer copies require_operator structure exactly, differing only in secret field name and audience claim"
  - "Pattern 2: Wave 0 stubs — test files for not-yet-built routes are created with @pytest.mark.skip upfront so the test suite can be collected and run without errors"

requirements-completed:
  - SECU-01

# Metrics
duration: 25min
completed: 2026-04-16
---

# Phase 5 Plan 01: Gateway Auth Foundation Summary

**Customer JWT auth dependency (require_customer) with HS256/switchboard-gateway audience, structlog+respx installed, and Wave 0 test stubs ready for gateway route implementation in Plan 02.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-04-16T19:08:00Z
- **Completed:** 2026-04-16T19:33:00Z
- **Tasks:** 2
- **Files modified:** 12

## Accomplishments

- Added structlog (25.5.0) and respx (0.23.1) to project dependencies via pyproject.toml + uv sync
- Extended Settings with customer_jwt_secret field and 32-byte minimum validator (mirrors operator_jwt_secret)
- Implemented require_customer FastAPI dependency in switchboard/gateway/auth.py — validates HS256 tokens with audience=switchboard-gateway and mandatory exp/iat/sub claims
- Created tests/gateway/ package with 6 passing auth unit tests and 13 skipped Wave 0 stub tests
- All 103 existing tests pass without regression

## Task Commits

Each task was committed atomically:

1. **Task 1: Add dependencies and extend Settings** - `e9f4cc2` (feat)
2. **Task 2: Implement require_customer and gateway test infrastructure** - `b9d1dcd` (feat)

## Files Created/Modified

- `pyproject.toml` - Added structlog>=25.0 and respx>=0.22.0
- `uv.lock` - Updated with new packages (structlog 25.5.0, respx 0.23.1)
- `switchboard/config.py` - Added customer_jwt_secret field and validate_customer_jwt_secret_length validator
- `tests/conftest.py` - Added CUSTOMER_JWT_SECRET setdefault before switchboard imports
- `switchboard/gateway/auth.py` - New: require_customer dependency (CustomerJWT Bearer scheme, audience=switchboard-gateway)
- `tests/gateway/__init__.py` - New: empty package marker
- `tests/gateway/conftest.py` - New: make_customer_token helper and customer_auth_headers fixture
- `tests/gateway/test_auth.py` - New: 6 unit tests (missing header, wrong secret, wrong audience, missing sub, valid, expired)
- `tests/gateway/test_proxy.py` - New: 5 skipped proxy route stubs
- `tests/gateway/test_session.py` - New: 3 skipped session affinity stubs
- `tests/gateway/test_wellknown.py` - New: 2 skipped well-known endpoint stubs
- `tests/gateway/test_logging.py` - New: 3 skipped structured logging stubs

## Decisions Made

- **Minimal TestClient pattern for auth tests:** Created a test-only FastAPI app with a single `/protected` route in `test_auth.py` so all 6 auth unit tests run immediately without needing the gateway app from Plan 02. This keeps the RED-GREEN cycle tight.
- **Wave 0 stubs with `@pytest.mark.skip`:** Stub files for proxy, session, wellknown, and logging routes are created now so `pytest tests/gateway/` can be run without collection errors. Stubs will be filled in Plan 02.
- **customer_jwt_secret validator identical to operator_jwt_secret:** Same 32-byte minimum, same startup failure behavior. Consistent security posture across all JWT secrets in the system.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed unused `pytest` import from test_auth.py**
- **Found during:** Task 2 (ruff check tests/gateway/)
- **Issue:** `import pytest` was unused after test structure was finalized (tests use no pytest decorators or fixtures directly in that file)
- **Fix:** Removed the unused import
- **Files modified:** tests/gateway/test_auth.py
- **Verification:** `ruff check tests/gateway/` exits 0
- **Committed in:** b9d1dcd (Task 2 commit)

**2. [Rule 1 - Bug] Fixed docstring line lengths exceeding 88 chars**
- **Found during:** Task 2 (ruff format --check)
- **Issue:** Two docstrings in test_auth.py and test_wellknown.py exceeded the 88-char line limit
- **Fix:** Shortened docstring text to fit within 88 characters
- **Files modified:** tests/gateway/test_auth.py, tests/gateway/test_wellknown.py
- **Verification:** `ruff check && ruff format --check` exits 0
- **Committed in:** b9d1dcd (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 - style/lint corrections)
**Impact on plan:** Minor fixes during ruff check pass. No scope changes.

## Issues Encountered

- The `uv add structlog` and `uv add --dev respx` commands ran silently without error in sandbox mode but didn't modify pyproject.toml (sandbox restricted uv cache writes). Resolved by editing pyproject.toml directly and running `uv sync` with sandbox disabled — identical end result.

## User Setup Required

None - no external service configuration required. CUSTOMER_JWT_SECRET is set via environment variable. Tests use a default test value.

## Next Phase Readiness

- require_customer dependency is ready for use in Plan 02 gateway app routes
- customer_auth_headers fixture available in tests/gateway/conftest.py
- 13 stub tests (proxy, session, wellknown, logging) waiting to be implemented in Plan 02
- structlog available for structured logging implementation in Plan 02
- respx available for mocking backend containers in Plan 02 proxy tests

---
*Phase: 05-gateway*
*Completed: 2026-04-16*

## Self-Check: PASSED

All files verified:
- switchboard/gateway/auth.py — FOUND
- tests/gateway/__init__.py — FOUND
- tests/gateway/conftest.py — FOUND
- tests/gateway/test_auth.py — FOUND
- tests/gateway/test_proxy.py — FOUND
- tests/gateway/test_session.py — FOUND
- tests/gateway/test_wellknown.py — FOUND
- tests/gateway/test_logging.py — FOUND
- .planning/phases/05-gateway/05-01-SUMMARY.md — FOUND

Commits verified:
- e9f4cc2 — FOUND (feat(05-01): add structlog+respx deps and customer_jwt_secret to Settings)
- b9d1dcd — FOUND (feat(05-01): implement require_customer and gateway test infrastructure)
