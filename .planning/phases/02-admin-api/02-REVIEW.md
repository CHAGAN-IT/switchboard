---
phase: 02-admin-api
reviewed: 2026-04-15T00:00:00Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - switchboard/admin/auth.py
  - switchboard/admin/router.py
  - switchboard/admin/app.py
  - switchboard/config.py
  - switchboard/registry/schemas.py
  - tests/admin/__init__.py
  - tests/admin/conftest.py
  - tests/admin/test_auth.py
  - tests/admin/test_endpoints.py
findings:
  critical: 1
  high: 2
  medium: 3
  low: 3
  total: 9
status: issues_found
---

# Phase 2: Admin API — Code Review Report

**Reviewed:** 2026-04-15
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH     | 2 |
| MEDIUM   | 3 |
| LOW      | 3 |
| **Total**    | **9** |

The Admin API implementation is structurally sound: JWT auth is wired correctly via FastAPI's dependency injection, the router-level `dependencies=[Depends(require_operator)]` pattern properly protects all routes, and Pydantic schemas cleanly separate from ORM models. The most significant concerns are:

1. **CRITICAL** — The JWT secret defaults to an empty string (`""`), meaning the API will boot and sign/verify tokens with an empty key if `OPERATOR_JWT_SECRET` is not set. This bypasses all meaningful authentication in misconfigured environments.
2. **HIGH** — No audience (`aud`) or issuer (`iss`) claim validation in JWT decoding, making stolen tokens portable across services.
3. **HIGH** — Module-level instantiation of `ServerRepository()` in `router.py` makes the dependency injection pattern inconsistent and harder to mock in tests.

The test suite covers the core happy and error paths well. The fixture isolation approach (dependency overrides cleared in the same fixture that sets them) is correct. Minor gaps exist in token claim coverage and test isolation.

---

## CRITICAL Issues

### CR-01: Empty JWT Secret Bypasses Authentication at Startup

**File:** `switchboard/config.py:33`
**Severity:** CRITICAL

**Issue:** `operator_jwt_secret` defaults to `""` (empty string). The `field_validator` on line 35 explicitly allows empty strings — it only enforces the 32-byte minimum when a value "is explicitly set" (`if v and len(v.encode()) < 32`). This means if `OPERATOR_JWT_SECRET` is not set in the environment, the application starts successfully and PyJWT will sign and verify tokens using `""` as the HMAC key. Any caller who discovers or guesses the empty-key behaviour can forge valid tokens.

PyJWT accepts an empty string as a valid key for HS256:
```python
import jwt
token = jwt.encode({"sub": "attacker"}, "", algorithm="HS256")
payload = jwt.decode(token, "", algorithms=["HS256"])  # succeeds
```

The combination of:
- A permissive default (`""`) in the settings model
- A validator that skips empty values
- Auth code that passes `settings.operator_jwt_secret` directly to `jwt.decode()`

means that in any environment where the secret is not explicitly set, auth is a no-op.

**Fix:** Enforce presence of the secret at startup. Remove the "allow empty string" exception from the validator, or raise on empty:

```python
# switchboard/config.py

@field_validator("operator_jwt_secret")
@classmethod
def validate_jwt_secret(cls, v: str) -> str:
    """Enforce non-empty JWT secret with minimum 32-byte length per RFC 7518 §3.2."""
    if not v:
        raise ValueError(
            "OPERATOR_JWT_SECRET environment variable is required and must not be empty"
        )
    if len(v.encode()) < 32:
        raise ValueError("OPERATOR_JWT_SECRET must be at least 32 bytes")
    return v
```

If an empty default is truly required for local development without configuration, it must be isolated to a dev-only code path (e.g., an `if settings.env == "development"` guard in the startup event), not embedded as a silent validator bypass in the production Settings class.

---

## HIGH Issues

### HR-01: JWT Decoded Without Audience or Issuer Validation

**File:** `switchboard/admin/auth.py:50-54`
**Severity:** HIGH

**Issue:** The `jwt.decode()` call validates signature and expiration only. It does not validate `aud` (audience) or `iss` (issuer) claims:

```python
payload = jwt.decode(
    credentials.credentials,
    settings.operator_jwt_secret,
    algorithms=["HS256"],
)
```

A JWT issued by Switchboard for a different purpose (e.g., a future customer-facing service using the same HS256 secret) would be accepted by the admin API, and vice versa. This is a token confusion / privilege escalation risk if the secret is ever shared across services, which is a realistic mistake in HS256-based systems (as opposed to asymmetric RS256/ES256 where each service has its own key pair).

**Fix:** Add audience and issuer validation. Define constants in config or as module-level values:

```python
# switchboard/admin/auth.py

payload = jwt.decode(
    credentials.credentials,
    settings.operator_jwt_secret,
    algorithms=["HS256"],
    options={"require": ["exp", "iat", "sub"]},
    audience="switchboard-admin",        # reject tokens not intended for admin API
    issuer="switchboard",                # reject tokens from unknown issuers
)
```

Corresponding tokens must include `aud="switchboard-admin"` and `iss="switchboard"` claims. The test fixture in `conftest.py` must also include these claims in `make_operator_token()`.

---

### HR-02: Module-Level Repository Instantiation Bypasses Dependency Injection

**File:** `switchboard/admin/router.py:32`
**Severity:** HIGH

**Issue:** `_repo = ServerRepository()` is instantiated at module import time as a module-level singleton:

```python
_repo = ServerRepository()
```

This pattern:

1. Makes `ServerRepository` impossible to override via FastAPI's `dependency_overrides` in tests. The current test suite works around this by testing against a real (overridden) database session, but any future need to mock repository behavior requires monkey-patching the module-level variable, which is fragile.
2. Contradicts the project's dependency injection pattern established by `get_session` and `get_settings`. Repository instantiation should follow the same pattern for consistency and testability.
3. If `ServerRepository.__init__` ever acquires resources (connection pools, config reads), module-level instantiation runs those at import time with no lifecycle control.

**Fix:** Convert `ServerRepository` to a FastAPI dependency:

```python
# switchboard/admin/router.py

from switchboard.registry.repository import ServerRepository

def get_repository() -> ServerRepository:
    """Return a ServerRepository instance for use in endpoint handlers."""
    return ServerRepository()

@router.post("/servers", ...)
async def register_server(
    body: ServerCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    repo: Annotated[ServerRepository, Depends(get_repository)],
) -> ServerRead:
    ...
```

This aligns with the existing DI pattern and enables test overrides via `app.dependency_overrides[get_repository]`.

---

## MEDIUM Issues

### MD-01: Return Type of `require_operator` Is `dict` — No Claim Typing

**File:** `switchboard/admin/auth.py:31`
**Severity:** MEDIUM

**Issue:** The `require_operator` dependency declares `-> dict` as its return type. This is a bare, untyped dict. Any endpoint that injects the decoded payload (e.g., for `sub` or custom claims) would receive `dict` with no IDE assistance or static analysis validation. The GLOBAL CLAUDE.md rules require type hints on all function signatures; `dict` alone violates the intent of that rule (it's typed in form but not in semantics).

Additionally, none of the three endpoint handlers in `router.py` actually inject the `require_operator` payload — they use it only for auth gating. If the payload is never consumed, the return type annotation is misleading.

**Fix (option A — tighten the return type):** Define a typed payload model:

```python
# switchboard/admin/auth.py

from pydantic import BaseModel

class OperatorTokenPayload(BaseModel):
    """Decoded JWT claims for a verified operator token."""
    sub: str
    exp: int
    iat: int

async def require_operator(...) -> OperatorTokenPayload:
    ...
    return OperatorTokenPayload.model_validate(payload)
```

**Fix (option B — if payload is never used, document intent):** If endpoints only gate on auth and never read claims, change the return type to `None` and drop the return value:

```python
async def require_operator(...) -> None:
    ...
    # Raises HTTPException on invalid token; returns None on success.
    # Callers use this as a guard only, not to read token claims.
```

Option A is preferred — it makes future claim-reading endpoints safe to write without introducing untyped dict access.

---

### MD-02: `_override_settings()` in conftest.py Hardcodes Database URLs

**File:** `tests/admin/conftest.py:67-73`
**Severity:** MEDIUM

**Issue:** The `_override_settings()` helper constructs a `Settings` instance with hardcoded database URLs:

```python
def _override_settings() -> Settings:
    return Settings(
        operator_jwt_secret=TEST_JWT_SECRET,
        database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/switchboard",
        test_database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/switchboard_test",
    )
```

These duplicate the defaults already baked into `Settings` field definitions in `config.py`. If the defaults change (e.g., for CI/CD, Docker Compose hostnames), this fixture silently diverges and tests pass locally but fail in CI. The fixture's intent is to override `operator_jwt_secret` only — it should not be re-specifying database URLs.

**Fix:** Only override what the fixture intends to override. Let `Settings` resolve everything else from defaults and environment:

```python
def _override_settings() -> Settings:
    """Return Settings with known test JWT secret. All other values from env/defaults."""
    return Settings(operator_jwt_secret=TEST_JWT_SECRET)
```

If `Settings()` cannot be constructed without a valid `OPERATOR_JWT_SECRET` after fixing CR-01 above, the test suite's `_override_settings` is the correct place to provide it for tests — which is what this fixture already does.

---

### MD-03: `test_register_server_invalid_name_422` Does Not Validate Error Body

**File:** `tests/admin/test_endpoints.py:73-85`
**Severity:** MEDIUM

**Issue:** The test verifies the status code is 422 but does not assert the error body content:

```python
async def test_register_server_invalid_name_422(
    self, client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.post(...)
    assert response.status_code == 422
    # No assertion on response.json()
```

This means the test would pass if the 422 were returned for any reason — a database error, a bug in validation logic, or an unrelated Pydantic schema mismatch. The test name implies it's testing name pattern validation (from D-08), but nothing in the assertion verifies that interpretation.

**Fix:** Assert the error body targets the `name` field:

```python
assert response.status_code == 422
errors = response.json()["detail"]
# Find the validation error for the 'name' field
name_errors = [e for e in errors if "name" in e.get("loc", [])]
assert name_errors, f"Expected validation error for 'name' field, got: {errors}"
```

Apply the same pattern to `test_register_server_empty_description_422` for the `description` field.

---

## LOW Issues

### LW-01: No Rate Limiting on Admin Endpoints

**File:** `switchboard/admin/app.py`
**Severity:** LOW

**Issue:** The Admin API has no rate limiting middleware. The project's security guidelines (`.claude/skills/security-review/SKILL.md`) list rate limiting as mandatory on all API endpoints. While enforcement via a reverse proxy or ALB is acceptable in production, there is no application-level protection for local dev or misconfigured deployments. An attacker who obtains a JWT secret or can forge tokens at scale faces no throttling on the registration endpoint.

**Fix:** Add SlowAPI or a simple dependency-based rate limiter for the admin router. At minimum, add a TODO with a tracking reference so the gap is documented:

```python
# switchboard/admin/app.py
# TODO(security): Add rate limiting to admin endpoints before production deployment.
# See: https://github.com/laurentS/slowapi for ASGI-compatible rate limiting.
```

---

### LW-02: `conftest.py` `client` Fixture Leaks `dependency_overrides` on Exception

**File:** `tests/admin/conftest.py:95-105`
**Severity:** LOW

**Issue:** The `client` fixture clears `app.dependency_overrides` in a line after `yield`, not in a `finally` block:

```python
async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
    yield ac

app.dependency_overrides.clear()  # Only runs if no exception during yield
```

If a test raises an unhandled exception that propagates through the `async with` block, `app.dependency_overrides.clear()` may not run. This can cause subsequent tests to run with stale overrides from a failed test, producing misleading failures.

**Fix:** The `async with` context manager does handle normal teardown, but since `yield` sits inside the `async with`, a test exception propagates and the `async with` exit runs — so `clear()` would typically still execute. However, the safer and more explicit pattern is:

```python
app.dependency_overrides[get_session] = override_session
app.dependency_overrides[get_settings] = _override_settings

try:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
finally:
    app.dependency_overrides.clear()
```

This is already the correct pattern for the `unauthenticated_client` fixture (which uses a separate `yield` outside the `with`), but apply it here for defensive consistency.

---

### LW-03: `test_get_server_by_name` Does Not Assert Status of Create Step

**File:** `tests/admin/test_endpoints.py:158-181`
**Severity:** LOW

**Issue:** The `test_get_server_by_name` test creates a server in a setup step but does not assert the creation succeeded:

```python
# Create server first
await client.post(
    "/api/v1/servers",
    json={...},
    headers=auth_headers,
)
# No assert here — if create fails silently, get returns 404 and test fails
# with a misleading error about the GET, not the POST
```

If the POST fails for any reason (transient DB issue, validation regression), the test will fail at the GET assertion with `404 Not Found`, which misattributes the failure to the retrieval path rather than the setup path.

**Fix:**

```python
create_response = await client.post(
    "/api/v1/servers",
    json={...},
    headers=auth_headers,
)
assert create_response.status_code == 201, (
    f"Setup failed: could not create server. Response: {create_response.json()}"
)
```

---

## PASS Items

The following areas were reviewed and found to have no issues:

- **JWT algorithm restriction** (`auth.py:53`): `algorithms=["HS256"]` is a list, correctly preventing algorithm confusion attacks (e.g., `"none"` or RS256 key-confusion).
- **Error message information leakage** (`auth.py:55-66`): Expired tokens return "Token has expired"; all other JWT errors return the generic "Could not validate credentials". Internal PyJWT error messages are not surfaced. `from None` suppresses chained exception context.
- **WWW-Authenticate header** (`auth.py:59, 65`): Present on all 401 responses per RFC 6750.
- **Router-level auth gating** (`router.py:26-30`): `dependencies=[Depends(require_operator)]` applied at the router level correctly protects all routes without requiring per-endpoint repetition.
- **Async patterns** (`router.py`): All endpoint functions are `async def`, all database calls are `await`ed. No sync blocking in the async path.
- **Pydantic v2 ORM mode** (`schemas.py:48`): `ConfigDict(from_attributes=True)` is the correct Pydantic v2 pattern; `orm_mode=True` (v1) is not used.
- **`field_validator` mode** (`schemas.py:27`): `mode="before"` is correct for the empty-string rejection validator — it runs before type coercion, catching `""` before Pydantic might coerce it.
- **`from __future__ import annotations`**: Present in all production modules. Correct for Python 3.12 with forward references.
- **`lru_cache` on `get_settings`** (`config.py:49`): Settings read once and cached. Tests clear the cache via dependency overrides (not via `cache_clear()`), which is the appropriate FastAPI pattern.
- **`HTTPBearer` auto_error default** (`auth.py:20-23`): Default `auto_error=True` means missing Authorization header returns 403 from the scheme itself before `require_operator` runs. Tests confirm 401 — this 403 vs 401 edge case should be verified: FastAPI's `HTTPBearer` with `auto_error=True` actually raises a 403, not 401, for missing credentials. If the test at `test_auth.py:27` passes with 401, the `unauthenticated_client` fixture may be masking this. **This is worth a manual check** but not classified as a finding without confirmed reproduction.
- **`ServerCreate` description validator**: Correctly uses `v.strip()` to reject whitespace-only strings, not just empty strings.
- **Import structure**: All modules follow stdlib → third-party → local ordering. No wildcard imports.

---

_Reviewed: 2026-04-15_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
