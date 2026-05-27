---
phase: 02-admin-api
verified: 2026-04-15T04:00:00Z
status: gaps_found
score: 4/5
overrides_applied: 0
gaps:
  - truth: "Requests without a valid operator JWT Bearer token return 401 with WWW-Authenticate header"
    status: partial
    reason: "The JWT auth middleware functions correctly when OPERATOR_JWT_SECRET is set, but the Settings validator allows an empty-string secret (if v and len(v.encode()) < 32 skips the check when v is falsy). PyJWT accepts empty string as a valid HS256 key with only a warning. This means a misconfigured deployment with no OPERATOR_JWT_SECRET set accepts attacker-forged tokens signed with the empty key, making auth bypassable by anyone who knows or guesses the empty-key behavior."
    artifacts:
      - path: "switchboard/config.py"
        issue: "field_validator on operator_jwt_secret uses 'if v and ...' — empty string passes validation. Default value is empty string. Startup succeeds without any secret configured."
      - path: "switchboard/admin/auth.py"
        issue: "jwt.decode() receives settings.operator_jwt_secret which may be ''. PyJWT accepts empty string as a valid HS256 key (confirmed via live test)."
    missing:
      - "Remove the 'if v and ...' guard from validate_jwt_secret_length — enforce non-empty for all values"
      - "Raise ValueError when operator_jwt_secret is empty string: 'OPERATOR_JWT_SECRET environment variable is required and must not be empty'"
      - "Update tests to set OPERATOR_JWT_SECRET before calling Settings() without an explicit override"
human_verification:
  - test: "Run full test suite with PostgreSQL available"
    expected: "All 14 tests in tests/admin/ pass (4 auth + 10 endpoint). Full suite (Phase 1 + Phase 2) shows 68+ tests passing with no regressions."
    why_human: "PostgreSQL is not running in the verification environment. The 3 auth rejection tests (missing/invalid/expired token) pass without DB. The valid-token test and all 10 endpoint tests require a live DB session via the test fixture."
  - test: "Open http://localhost:8000/docs in a browser after running 'uv run uvicorn switchboard.admin.app:app --reload'"
    expected: "OpenAPI UI loads and shows exactly three endpoints: POST /api/v1/servers, GET /api/v1/servers, GET /api/v1/servers/{name}. Each endpoint shows correct request/response schemas and the OperatorJWT security scheme."
    why_human: "Browser rendering of OpenAPI UI is not automatable. The /docs endpoint returns 200 (verified by test), but visual accuracy of schemas requires visual inspection."
---

# Phase 2: Admin API Verification Report

**Phase Goal:** An operator can register MCP servers, list all registered servers, and retrieve details for any individual server via a running FastAPI REST API protected by operator JWT validation.
**Verified:** 2026-04-15T04:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | POST /servers with valid payload creates a new registry entry and returns 201 with server record | VERIFIED | `register_server` in router.py calls `_repo.create()`, calls `await session.commit()`, returns `ServerRead.model_validate(server)` with `status_code=HTTP_201_CREATED`. Test `test_register_server_success` asserts 201, data["name"], data["status"] == "stopped", id and timestamps present. |
| 2 | GET /servers returns all registered servers with their current status | VERIFIED | `list_servers` calls `_repo.list_all(session)`, returns `[ServerRead.model_validate(s) for s in servers]`. Tests `test_list_servers` and `test_list_servers_empty` cover populated and empty cases. |
| 3 | GET /servers/{name} returns the full record for a specific server, or 404 if the server does not exist | VERIFIED | `get_server` calls `_repo.get_by_name(session, name)`, raises `HTTPException(HTTP_404_NOT_FOUND)` when None, returns `ServerRead.model_validate(server)` on success. Tests `test_get_server_by_name` and `test_get_server_not_found_404` cover both paths. |
| 4 | Requests without a valid operator JWT Bearer token return 401 with WWW-Authenticate header | PARTIAL | HTTPBearer + require_operator dependency correctly validates tokens when `operator_jwt_secret` is non-empty. Missing token: 401 confirmed (test passes). Invalid token: 401 confirmed (test passes). Expired token: 401 confirmed (test passes). **BUT:** `operator_jwt_secret` defaults to `""` and the validator allows empty strings. PyJWT accepts `""` as a valid HS256 signing key — confirmed live that a token signed with empty key decodes successfully against empty key. A misconfigured deployment (no OPERATOR_JWT_SECRET set) accepts attacker-forged tokens. |
| 5 | OpenAPI docs at /docs accurately reflect all Admin API endpoints | VERIFIED | App imports confirm 7 routes registered: `/openapi.json`, `/docs`, `/docs/oauth2-redirect`, `/redoc`, `/api/v1/servers` (POST), `/api/v1/servers` (GET), `/api/v1/servers/{name}` (GET). Endpoint smoke test (`test_openapi_docs_accessible`) asserts `/docs` returns 200. Visual accuracy requires human review. |

**Score:** 4/5 truths verified (Truth 4 is PARTIAL due to empty-secret bypass)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `switchboard/admin/auth.py` | JWT validation dependency using HTTPBearer + PyJWT HS256 | VERIFIED | Contains `require_operator`, `algorithms=["HS256"]`, `HTTPBearer`, `WWW-Authenticate: Bearer` headers on all 401 responses. `from None` suppresses exception chain (ruff B904 compliant). |
| `switchboard/admin/router.py` | APIRouter with POST/GET /servers endpoints | VERIFIED | Contains `prefix="/api/v1"`, `dependencies=[Depends(require_operator)]`, `@router.post("/servers"`, `@router.get("/servers"`, `@router.get("/servers/{name}"`, `status_code=HTTP_201_CREATED`, `HTTP_409_CONFLICT`, `HTTP_404_NOT_FOUND`, `await session.commit()`. |
| `switchboard/admin/app.py` | FastAPI application instance with router mounted | VERIFIED | Contains `app = FastAPI(...)`, `app.include_router(router)`. Importable at `switchboard.admin.app:app`. |
| `switchboard/config.py` | Settings extended with operator_jwt_secret field | PARTIAL | Contains `operator_jwt_secret: str = ""` and `validate_jwt_secret_length`. Validator skips enforcement when `v` is empty (falsy) — allows startup without secret configured. Existing field and lru_cache preserved. |
| `switchboard/registry/schemas.py` | ServerCreate with empty-string rejection validator | VERIFIED | Contains `field_validator("description", mode="before")`, `reject_empty_description`, `isinstance(v, str) and not v.strip()`. Correctly rejects empty/whitespace-only strings while allowing None. |
| `tests/admin/__init__.py` | Package marker for admin test directory | VERIFIED | File exists (package marker). |
| `tests/admin/conftest.py` | TestClient fixtures with dependency overrides | VERIFIED | Contains `TEST_JWT_SECRET`, `make_operator_token`, `app.dependency_overrides[get_session]`, `app.dependency_overrides[get_settings]`, `app.dependency_overrides.clear()`. Uses `httpx.AsyncClient + ASGITransport` for async tests, sync `TestClient` for auth rejection tests. |
| `tests/admin/test_auth.py` | JWT auth dependency unit tests | VERIFIED | Contains all 4 required test functions: `test_missing_token_401`, `test_invalid_token_401`, `test_expired_token_401`, `test_valid_token_succeeds`. First 3 pass programmatically (no DB needed). |
| `tests/admin/test_endpoints.py` | Endpoint integration tests for all SREG requirements | VERIFIED | Contains all 10 required test functions across `TestRegisterServer`, `TestListServers`, `TestGetServer`, `TestOpenAPI` classes. All use `@pytest.mark.asyncio` and `AsyncClient`. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `switchboard/admin/router.py` | `switchboard/admin/auth.py` | `dependencies=[Depends(require_operator)]` | WIRED | Confirmed at line 29: `dependencies=[Depends(require_operator)]` on the `APIRouter`. All 3 endpoints protected at router level. |
| `switchboard/admin/router.py` | `switchboard/registry/repository.py` | `_repo.create/get_by_name/list_all` | WIRED | `_repo.create()` at line 62, `_repo.list_all()` at line 101, `_repo.get_by_name()` at line 126. |
| `switchboard/admin/router.py` | `switchboard/db/session.py` | `Depends(get_session)` | WIRED | `session: Annotated[AsyncSession, Depends(get_session)]` in all three endpoint signatures. |
| `switchboard/admin/app.py` | `switchboard/admin/router.py` | `app.include_router(router)` | WIRED | Confirmed at line 20: `app.include_router(router)`. 7 routes confirmed importable. |
| `switchboard/admin/auth.py` | `switchboard/config.py` | `Depends(get_settings)` | WIRED | `settings: Annotated[Settings, Depends(get_settings)]` — runtime import (not TYPE_CHECKING), required for FastAPI dependency resolution. |
| `tests/admin/conftest.py` | `switchboard/admin/app.py` | `from switchboard.admin.app import app` | WIRED | Line 27 in conftest. Used for both `dependency_overrides` and `ASGITransport(app=app)`. |
| `tests/admin/conftest.py` | `switchboard/admin/auth.py` | `require_operator` not overridden | WIRED | Conftest explicitly documents that `require_operator` is NOT overridden — real JWT auth runs in both `client` and `unauthenticated_client` fixtures. |
| `tests/admin/conftest.py` | `switchboard/db/session.py` | `dependency_overrides[get_session]` | WIRED | Line 98: `app.dependency_overrides[get_session] = override_session`. |

### Data-Flow Trace (Level 4)

Not applicable. Admin API serves dynamic data from PostgreSQL via ServerRepository. Data flow is verified by integration tests against a live DB (human verification required for this environment).

The static structure is sound: `router.py` calls `_repo.list_all(session)` and returns `[ServerRead.model_validate(s) for s in servers]` — result is not discarded. No hardcoded empty returns in the actual response path.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| App is importable with correct routes | `uv run python -c "from switchboard.admin.app import app; print([r.path for r in app.routes if hasattr(r, 'path')])"` | `['/openapi.json', '/docs', '/docs/oauth2-redirect', '/redoc', '/api/v1/servers', '/api/v1/servers', '/api/v1/servers/{name}']` | PASS |
| Missing token returns 401 | `uv run pytest tests/admin/test_auth.py::test_missing_token_401 -q` | 1 passed | PASS |
| Invalid token returns 401 | `uv run pytest tests/admin/test_auth.py::test_invalid_token_401 -q` | 1 passed | PASS |
| Expired token returns 401 | `uv run pytest tests/admin/test_auth.py::test_expired_token_401 -q` | 1 passed | PASS |
| Empty-key JWT bypass | `jwt.decode(jwt.encode({"sub":"x"}, "", algorithm="HS256"), "", algorithms=["HS256"])` | Succeeds with InsecureKeyLengthWarning — bypass confirmed | FAIL |
| Full endpoint suite | `uv run pytest tests/admin/ -x -q` | 3 passed, 1 error (PostgreSQL not available) | SKIP (needs DB) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| SREG-01 | 02-01-PLAN.md, 02-02-PLAN.md | Operator can register a new MCP server (name, container image, description) via Admin API | SATISFIED | `POST /api/v1/servers` endpoint with `ServerCreate` body, `ServerRepository.create()`, returns `ServerRead` with 201. Tests: `test_register_server_success`, `test_register_server_duplicate_409`, `test_register_server_invalid_name_422`, `test_register_server_empty_description_422`, `test_register_server_null_description_ok`. |
| SREG-02 | 02-01-PLAN.md, 02-02-PLAN.md | Operator can list all registered servers with their current status via Admin API | SATISFIED | `GET /api/v1/servers` endpoint with `ServerRepository.list_all()`, returns `list[ServerRead]` including status field. Tests: `test_list_servers`, `test_list_servers_empty`. |
| SREG-03 | 02-01-PLAN.md, 02-02-PLAN.md | Operator can retrieve details for a specific registered server via Admin API | SATISFIED | `GET /api/v1/servers/{name}` endpoint with `ServerRepository.get_by_name()`, returns `ServerRead` or 404. Tests: `test_get_server_by_name`, `test_get_server_not_found_404`. |

No orphaned requirements: REQUIREMENTS.md maps only SREG-01, SREG-02, SREG-03 to Phase 2, and both plans claim exactly these three IDs.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `switchboard/config.py` | 43 | `if v and len(v.encode()) < 32:` — validator skips enforcement when `v` is falsy (empty string) | Blocker | Default `operator_jwt_secret = ""` + this validator allows the API to start without any secret configured. PyJWT accepts empty string as HS256 key. Token forgery possible in misconfigured deployments. |
| `switchboard/admin/auth.py` | — | `jwt.decode()` called without audience/issuer validation | Warning | No `aud` or `iss` claim enforcement. Tokens intended for other services (if any share this HS256 secret) would be accepted. Non-blocking for Phase 2 single-service scope but a known security gap per REVIEW.md CR-01. |
| `switchboard/admin/router.py` | 32 | `_repo = ServerRepository()` module-level singleton | Warning | Bypasses FastAPI DI for the repository. Current tests work around it via real DB session override, but future mocking requires monkey-patching. Documented as HR-02 in REVIEW.md. |

No TODO/FIXME/placeholder markers found in any production or test files.

### Human Verification Required

#### 1. Full Test Suite with Database

**Test:** Start PostgreSQL (e.g., via Docker Compose) and run `uv run pytest -x -q` from the project root.
**Expected:** All 14 tests in `tests/admin/` pass (4 auth + 10 endpoint). Total suite shows 68+ tests passing including Phase 1 regression tests. No failures.
**Why human:** PostgreSQL database is required for `test_valid_token_succeeds` and all 10 endpoint integration tests. The verification environment has no running database.

#### 2. OpenAPI UI Visual Accuracy

**Test:** Run `uv run uvicorn switchboard.admin.app:app --reload` and open `http://localhost:8000/docs` in a browser.
**Expected:** Three endpoints visible: `POST /api/v1/servers`, `GET /api/v1/servers`, `GET /api/v1/servers/{name}`. Each shows correct request/response schemas (ServerCreate/ServerRead), the `OperatorJWT` Bearer security scheme, and accurate status codes (201, 409, 422 for POST; 200 for GET; 200/404 for GET-by-name).
**Why human:** Browser-rendered OpenAPI UI accuracy requires visual inspection. The `/docs` 200 status is confirmed programmatically, but schema correctness and visual rendering require a browser.

### Gaps Summary

**One gap blocks full goal achievement:**

**Truth 4 (JWT protection) is PARTIAL.** The JWT auth dependency (`require_operator`) correctly validates tokens when `OPERATOR_JWT_SECRET` is configured. The auth tests for missing/invalid/expired tokens all pass. However, the `Settings` validator allows `operator_jwt_secret` to be an empty string (the default), and PyJWT accepts `""` as a valid HS256 signing key. This means:

- A deployment that fails to set `OPERATOR_JWT_SECRET` starts successfully without error
- An attacker who signs a JWT with an empty key and sends it receives a valid authenticated response
- This was confirmed live: `jwt.encode({"sub":"x"}, "", algorithm="HS256")` + `jwt.decode(...)` succeeds

The phase goal states the API is "protected by operator JWT validation." With the current empty-secret bypass, that protection is conditional on correct configuration with no enforcement at startup. The REVIEW.md (CR-01) documented this issue. The fix is a one-line validator change: remove the `if v and ...` guard and enforce non-empty always.

This gap is in `switchboard/config.py` line 43 and requires changing `if v and len(v.encode()) < 32:` to `if not v: raise ValueError(...)` plus the existing minimum-length check.

---

_Verified: 2026-04-15T04:00:00Z_
_Verifier: Claude (gsd-verifier)_
