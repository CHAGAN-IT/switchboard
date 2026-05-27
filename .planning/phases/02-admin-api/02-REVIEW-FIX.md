---
phase: 02-admin-api
fixed_at: 2026-04-15T00:00:00Z
review_path: .planning/phases/02-admin-api/02-REVIEW.md
iteration: 1
fix_scope: critical_warning
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 2: Admin API — Code Review Fix Report

**Fixed at:** 2026-04-15
**Source review:** `.planning/phases/02-admin-api/02-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 3 (1 CRITICAL, 2 HIGH)
- Fixed: 3
- Skipped: 0

---

## Fixed Issues

### CR-01: Empty JWT Secret Bypasses Authentication at Startup

**Files modified:** `switchboard/config.py`, `tests/conftest.py`
**Commits:** `950707c` (config fix), `812c99a` (test support fix)
**Applied fix:** Changed `validate_jwt_secret_length` in `Settings` to reject empty strings unconditionally. The validator previously allowed `""` as a default (only enforcing the 32-byte minimum when a non-empty value was provided), meaning any environment without `OPERATOR_JWT_SECRET` set would boot with an empty HMAC key. The fix adds an explicit `if not v` guard that raises a `ValueError` requiring a non-empty secret at startup.

**Test support fix (followup commit `812c99a`):** The CR-01 validator now causes `get_settings()` to raise at import time in the test environment because `switchboard/db/session.py` calls `create_engine()` at module level, which calls `get_settings()` unconditionally. Fixed by adding `os.environ.setdefault("OPERATOR_JWT_SECRET", "pytest-default-secret-32-bytes-min!")` at the top of `tests/conftest.py`, before any switchboard imports. This ensures the import-time `get_settings()` call succeeds with a valid placeholder value; the actual test JWT secret (`TEST_JWT_SECRET` from `tests/admin/conftest.py`) is used for all authentication via FastAPI `dependency_overrides`.

---

### HR-01: JWT Decoded Without Audience or Issuer Validation

**Files modified:** `switchboard/admin/auth.py`, `tests/admin/conftest.py`
**Commit:** `4c92c5f`
**Applied fix:** Added `options={"require": ["exp", "iat", "sub"]}`, `audience="switchboard-admin"`, and `issuer="switchboard"` to the `jwt.decode()` call in `require_operator`. Tokens not intended for the admin API (wrong `aud`) or from unknown issuers (wrong `iss`) are now rejected, preventing token confusion / privilege escalation if the HS256 secret is ever shared across services.

Updated `make_operator_token()` in `tests/admin/conftest.py` to include `"aud": "switchboard-admin"` and `"iss": "switchboard"` in the test token payload, so all existing tests continue to generate tokens that pass the new validation.

---

### HR-02: Module-Level Repository Instantiation Bypasses Dependency Injection

**Files modified:** `switchboard/admin/router.py`
**Commit:** `ad78992`
**Applied fix:** Removed the module-level `_repo = ServerRepository()` singleton. Replaced it with a `get_repository() -> ServerRepository` FastAPI dependency function. Updated all three endpoint signatures (`register_server`, `list_servers`, `get_server`) to inject `repo: Annotated[ServerRepository, Depends(get_repository)]` and updated all `_repo.` call sites to use the injected `repo` parameter. This aligns repository instantiation with the existing DI pattern (`get_session`, `get_settings`) and enables future test overrides via `app.dependency_overrides[get_repository]`.

---

## Skipped Issues

None — all in-scope findings (CR-01, HR-01, HR-02) were successfully fixed.

---

## Notes

**Test suite verification:** `uv run pytest tests/admin/ -q --tb=short` was executed after all fixes. Test collection succeeded (all tests discovered). Test execution errors were exclusively `ConnectionRefusedError: [Errno 111] Connect call failed ('127.0.0.1', 5432)` — PostgreSQL is not running in the local development environment. This is a pre-existing infrastructure constraint unrelated to any of the applied fixes. The import chain and all module loading completed without error.

**MEDIUM and LOW findings (out of scope):** MD-01, MD-02, MD-03, LW-01, LW-02, LW-03 were reviewed but not fixed per the `fix_scope: critical_warning` configuration. These are documented in the source `02-REVIEW.md` for future attention.

---

_Fixed: 2026-04-15_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
