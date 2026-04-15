# Phase 2: Admin API - Context

**Gathered:** 2026-04-15
**Status:** Ready for planning

<domain>
## Phase Boundary

An operator-facing REST API that allows registering MCP servers, listing all registered servers, and retrieving a specific server by name. Protected by operator JWT validation. No container lifecycle operations in this phase (Phase 3). No customer-facing gateway logic (Phase 5).

</domain>

<decisions>
## Implementation Decisions

### JWT Authentication
- **D-01:** Validate operator JWTs using HMAC shared secret (HS256). Single `OPERATOR_JWT_SECRET` environment variable added to `Settings` in `switchboard/config.py`. PyJWT 2.12.1 (already in stack) handles encode/decode. A FastAPI `Depends()` dependency verifies the Bearer token on every request and returns 401 with `WWW-Authenticate: Bearer` on failure.

### API Routes
- **D-02:** All Admin API routes are prefixed with `/api/v1/` — e.g., `POST /api/v1/servers`, `GET /api/v1/servers`, `GET /api/v1/servers/{name}`. Router is registered on the FastAPI app with `prefix="/api/v1"`.

### Duplicate Server Handling
- **D-03:** `POST /api/v1/servers` returns **409 Conflict** when a server with the given name already exists. The `DuplicateServerError` from `switchboard/registry/exceptions.py` is caught and translated to an `HTTPException(status_code=409)`. Response body uses FastAPI's standard `{"detail": "Server 'echo' already exists"}` format.

### Error Response Format
- **D-04:** FastAPI's default `{"detail": "..."}` envelope for all error responses. No custom error handler or structured error code envelope. Consistent with OpenAPI tooling expectations and zero additional code.

### Empty Description
- **D-05:** Empty string for `description` is rejected at the API layer (inherited from Phase 1 decision D-07). A Pydantic validator on `ServerCreate` rejects empty strings; `None` and omission are both valid (treated as no description).

### Claude's Discretion
- FastAPI app entry point location (`switchboard/admin/app.py` or similar)
- JWT token expiry validation (verify `exp` claim)
- Uvicorn startup command and port selection for local dev
- OpenAPI title and description strings
- Whether to add `__all__` exports in `switchboard/admin/__init__.py`

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — SREG-01, SREG-02, SREG-03 (the three server registry requirements this phase fulfills); AUTH constraint (OAuth/JWT, no API-key-only auth)

### Project constraints
- `.planning/PROJECT.md` — Language (Python 3.12+), package structure (`switchboard/` top-level), auth constraint

### Phase 1 decisions (locked — do not re-decide)
- `.planning/phases/01-foundation/01-CONTEXT.md` — D-09 (ServerRepository interface), D-10 (async session injection via Depends), D-11 (ORM/Pydantic separation), D-12/D-13/D-14 (test strategy)

### Technology stack
- `.planning/research/STACK.md` — Confirmed versions: FastAPI 0.135.3, Uvicorn 0.44.0, PyJWT 2.12.1, pydantic-settings 2.13.1

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `switchboard/registry/repository.py` — `ServerRepository` with `create()`, `get_by_name()`, `list_all()` — ready for direct use in API endpoints. Accepts `AsyncSession` argument.
- `switchboard/registry/schemas.py` — `ServerCreate` (request body for POST) and `ServerRead` (response schema) — ready to use as FastAPI request/response models
- `switchboard/registry/exceptions.py` — `DuplicateServerError`, `ServerNotFoundError` — catch and convert to HTTP exceptions in endpoint handlers
- `switchboard/db/session.py` — `get_session()` async generator — use directly as `Depends(get_session)` for session injection
- `switchboard/config.py` — `Settings` class via `get_settings()` — extend with `operator_jwt_secret: str` field

### Established Patterns
- Repository methods flush but never commit — API endpoints must call `await session.commit()` after successful operations
- `from __future__ import annotations` + `TYPE_CHECKING` block for stdlib/SQLAlchemy imports (see all Phase 1 files)
- `lru_cache` on `get_settings()` — do not instantiate `Settings` directly

### Integration Points
- `switchboard/admin/app.py` (to create): FastAPI app instance, router mounting at `/api/v1`
- `switchboard/config.py`: Add `operator_jwt_secret: str` to `Settings`
- `switchboard/admin/` subpackage: Implement router, auth dependency, and endpoint handlers here

</code_context>

<specifics>
## Specific Ideas

- No specific UX references — standard REST API conventions apply
- Operator JWT is assumed to be generated externally (e.g., a CLI script or CI secret); the API only validates, never issues tokens in Phase 2

</specifics>

<deferred>
## Deferred Ideas

- Token issuance endpoint (Authlib OAuth2 server) — post-v1 per REQUIREMENTS.md
- Multiple API keys with role-based scopes (ADMN-01) — v2 requirement
- Server update / soft-delete endpoints (SREG-04, SREG-05) — v2 requirement
- URL versioning migration path (v2 → /api/v2/) — not needed until v2 requirements are defined

</deferred>

---

*Phase: 02-admin-api*
*Context gathered: 2026-04-15*
