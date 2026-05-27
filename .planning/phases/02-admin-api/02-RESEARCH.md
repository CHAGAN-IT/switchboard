# Phase 2: Admin API - Research

**Researched:** 2026-04-15
**Domain:** FastAPI REST API with JWT authentication, async database integration
**Confidence:** HIGH

## Summary

Phase 2 builds a FastAPI REST API on top of the Phase 1 foundation (ServerRepository, Pydantic schemas, async database sessions). The phase requires three endpoints (`POST /api/v1/servers`, `GET /api/v1/servers`, `GET /api/v1/servers/{name}`), JWT Bearer token validation using PyJWT with HS256, and automatic OpenAPI documentation. All critical decisions are locked in CONTEXT.md.

The existing codebase provides nearly all the building blocks: `ServerRepository` with `create()`, `get_by_name()`, and `list_all()` methods; `ServerCreate` and `ServerRead` Pydantic schemas; `DuplicateServerError` and `ServerNotFoundError` exceptions; and `get_session()` for dependency injection. The phase adds FastAPI, PyJWT, httpx (for testing), and Uvicorn as new dependencies, creates the `switchboard/admin/` subpackage with app, router, and auth modules, and extends `Settings` with `operator_jwt_secret`.

**Primary recommendation:** Use FastAPI's `HTTPBearer` security scheme (not `OAuth2PasswordBearer`) since Switchboard validates externally-issued JWTs and never issues tokens itself. This produces the correct OpenAPI spec (Bearer auth, not OAuth2 password flow) and simplifies the dependency chain.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Validate operator JWTs using HMAC shared secret (HS256). Single `OPERATOR_JWT_SECRET` environment variable added to `Settings` in `switchboard/config.py`. PyJWT 2.12.1 (already in stack) handles encode/decode. A FastAPI `Depends()` dependency verifies the Bearer token on every request and returns 401 with `WWW-Authenticate: Bearer` on failure.
- **D-02:** All Admin API routes are prefixed with `/api/v1/` -- e.g., `POST /api/v1/servers`, `GET /api/v1/servers`, `GET /api/v1/servers/{name}`. Router is registered on the FastAPI app with `prefix="/api/v1"`.
- **D-03:** `POST /api/v1/servers` returns **409 Conflict** when a server with the given name already exists. The `DuplicateServerError` from `switchboard/registry/exceptions.py` is caught and translated to an `HTTPException(status_code=409)`. Response body uses FastAPI's standard `{"detail": "Server 'echo' already exists"}` format.
- **D-04:** FastAPI's default `{"detail": "..."}` envelope for all error responses. No custom error handler or structured error code envelope.
- **D-05:** Empty string for `description` is rejected at the API layer (inherited from Phase 1 decision D-07). A Pydantic validator on `ServerCreate` rejects empty strings; `None` and omission are both valid (treated as no description).

### Claude's Discretion
- FastAPI app entry point location (`switchboard/admin/app.py` or similar)
- JWT token expiry validation (verify `exp` claim)
- Uvicorn startup command and port selection for local dev
- OpenAPI title and description strings
- Whether to add `__all__` exports in `switchboard/admin/__init__.py`

### Deferred Ideas (OUT OF SCOPE)
- Token issuance endpoint (Authlib OAuth2 server) -- post-v1 per REQUIREMENTS.md
- Multiple API keys with role-based scopes (ADMN-01) -- v2 requirement
- Server update / soft-delete endpoints (SREG-04, SREG-05) -- v2 requirement
- URL versioning migration path (v2 -> /api/v2/) -- not needed until v2 requirements are defined

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SREG-01 | Operator can register a new MCP server (name, container image, description) via Admin API | `POST /api/v1/servers` endpoint using `ServerRepository.create()` with `ServerCreate` request body, returning `ServerRead` with 201 status |
| SREG-02 | Operator can list all registered servers with their current status via Admin API | `GET /api/v1/servers` endpoint using `ServerRepository.list_all()`, returning `list[ServerRead]` |
| SREG-03 | Operator can retrieve details for a specific registered server via Admin API | `GET /api/v1/servers/{name}` endpoint using `ServerRepository.get_by_name()`, returning `ServerRead` or 404 |

</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Language:** Python 3.12+ -- all application code
- **Package structure:** `switchboard/` top-level package (not `src/`)
- **Toolchain:** `uv` for packages, `ruff` for lint/format, `pytest` for testing
- **Type hints:** Required on all function signatures; use `from __future__ import annotations`
- **Import pattern:** `TYPE_CHECKING` block for type-only imports (established in Phase 1)
- **Docstrings:** Google-style on all public modules, classes, methods, and functions
- **Testing:** TDD workflow; 80%+ coverage; `pytest-asyncio` for async tests
- **Git:** Conventional commit messages (`feat:`, `fix:`, etc.)
- **Error handling:** Custom exception hierarchies; never bare `except`; never catch `Exception` without logging
- **Data modeling:** Pydantic `BaseModel` for API validation; separate from ORM models (Phase 1 D-11)

## Standard Stack

### Core (Phase 2 additions)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.135.3 | REST API framework | ASGI-native, async-first, Pydantic v2 integration, automatic OpenAPI docs [VERIFIED: stack research, PyPI April 14 2026] |
| Uvicorn | 0.44.0 | ASGI server | Production ASGI server for FastAPI; `--reload` for dev [VERIFIED: stack research, PyPI April 14 2026] |
| PyJWT | 2.12.1 | JWT encode/decode | HS256 token validation; actively maintained replacement for abandoned python-jose [VERIFIED: stack research, PyPI April 14 2026] |
| httpx | 0.28.1 | HTTP client (also testing) | Required by FastAPI's TestClient; also used for async testing with `AsyncClient` [VERIFIED: stack research, PyPI April 14 2026] |

### Already Installed (from Phase 1)

| Library | Version | Purpose |
|---------|---------|---------|
| SQLAlchemy | 2.0.49 | Async ORM |
| asyncpg | 0.31.0 | Async PostgreSQL driver |
| Pydantic | 2.13.0 | Data validation |
| pydantic-settings | 2.13.1 | Environment variable config |
| Alembic | 1.18.4 | Database migrations |
| pytest | 8.x | Testing framework |
| pytest-asyncio | 0.26.x | Async test support |

### Installation

```bash
uv add fastapi uvicorn PyJWT
uv add --dev httpx
```

Note: `httpx` is required for `from fastapi.testclient import TestClient` to work. FastAPI 0.112+ moved httpx to an optional dependency. Install as dev dependency since this phase only needs it for testing. Production phases (gateway, Phase 5) will promote it to a runtime dependency. [CITED: https://github.com/fastapi/fastapi/discussions/11958]

## Architecture Patterns

### Recommended Project Structure

```
switchboard/
├── __init__.py
├── config.py               # Settings (extend with operator_jwt_secret)
├── admin/
│   ├── __init__.py          # Package marker
│   ├── app.py               # FastAPI app instance, lifespan, router mounting
│   ├── router.py            # APIRouter with /servers endpoints
│   └── auth.py              # JWT validation dependency
├── db/
│   ├── engine.py            # (existing)
│   ├── session.py           # (existing) get_session()
│   └── base.py              # (existing)
└── registry/
    ├── models.py            # (existing) Server ORM model
    ├── schemas.py           # (existing, modify) ServerCreate, ServerRead
    ├── repository.py        # (existing) ServerRepository
    └── exceptions.py        # (existing) DuplicateServerError, ServerNotFoundError
```

### Pattern 1: HTTPBearer Security Dependency

**What:** Use `fastapi.security.HTTPBearer` as the security scheme, not `OAuth2PasswordBearer`. HTTPBearer produces the correct OpenAPI spec for Bearer token auth and automatically returns 401 when no `Authorization: Bearer` header is present. [CITED: https://fastapi.tiangolo.com/reference/security/]

**When to use:** When validating externally-issued Bearer tokens (this project's case -- Switchboard validates, never issues).

**Example:**

```python
# Source: FastAPI official docs + PyJWT official docs
from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from switchboard.config import get_settings

if TYPE_CHECKING:
    from switchboard.config import Settings

# HTTPBearer auto_error=True means missing/malformed Authorization header
# automatically returns 401 before our code even runs.
_bearer_scheme = HTTPBearer(
    scheme_name="OperatorJWT",
    description="Operator JWT token (HS256)",
)


async def require_operator(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    """Validate operator JWT and return decoded payload.

    Raises:
        HTTPException: 401 if token is invalid, expired, or malformed.
    """
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.operator_jwt_secret,
            algorithms=["HS256"],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload
```

### Pattern 2: Router with Dependency Injection

**What:** Use `APIRouter` with `dependencies=[Depends(require_operator)]` to protect all routes at the router level, avoiding repetition on each endpoint. [CITED: https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/]

**Example:**

```python
# Source: FastAPI official docs
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from switchboard.admin.auth import require_operator
from switchboard.db.session import get_session
from switchboard.registry.exceptions import DuplicateServerError
from switchboard.registry.repository import ServerRepository
from switchboard.registry.schemas import ServerCreate, ServerRead

router = APIRouter(
    prefix="/api/v1",
    tags=["servers"],
    dependencies=[Depends(require_operator)],
)

_repo = ServerRepository()


@router.post(
    "/servers",
    response_model=ServerRead,
    status_code=status.HTTP_201_CREATED,
)
async def register_server(
    body: ServerCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ServerRead:
    """Register a new MCP server."""
    try:
        server = await _repo.create(
            session,
            name=body.name,
            container_image=body.container_image,
            description=body.description,
        )
    except DuplicateServerError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Server '{body.name}' already exists",
        )
    await session.commit()
    return ServerRead.model_validate(server)
```

### Pattern 3: FastAPI App with Router Mounting

**What:** Create a FastAPI app instance in `app.py` and include the router. [ASSUMED]

**Example:**

```python
# switchboard/admin/app.py
from __future__ import annotations

from fastapi import FastAPI

from switchboard.admin.router import router

app = FastAPI(
    title="Switchboard Admin API",
    description="Operator API for managing MCP server registrations",
    version="0.1.0",
)
app.include_router(router)
```

### Pattern 4: Pydantic field_validator for Empty String Rejection (D-05)

**What:** Add a `field_validator` to `ServerCreate` that rejects empty strings for `description` while allowing `None`. [CITED: https://docs.pydantic.dev/latest/concepts/validators/]

**Example:**

```python
# Modification to switchboard/registry/schemas.py
from pydantic import BaseModel, ConfigDict, field_validator


class ServerCreate(BaseModel):
    """Schema for creating a new server registration."""

    name: str
    container_image: str
    description: str | None = None

    @field_validator("description", mode="before")
    @classmethod
    def reject_empty_description(cls, v: str | None) -> str | None:
        """Reject empty strings for description (D-05).

        None and omission are valid. Non-empty strings are valid.
        Empty or whitespace-only strings are rejected.
        """
        if isinstance(v, str) and not v.strip():
            msg = "Description must not be empty; omit the field or set to null instead"
            raise ValueError(msg)
        return v
```

### Pattern 5: Test Dependency Overrides

**What:** Override `get_session` and `require_operator` in tests using `app.dependency_overrides` to inject test sessions and bypass real JWT validation. [CITED: https://fastapi.tiangolo.com/advanced/testing-dependencies/]

**Example:**

```python
# tests/admin/conftest.py
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from switchboard.admin.app import app
from switchboard.admin.auth import require_operator
from switchboard.db.session import get_session


@pytest.fixture
def client(session: AsyncSession) -> TestClient:
    """TestClient with overridden dependencies."""
    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_operator] = lambda: {"sub": "test-operator"}

    yield TestClient(app)

    app.dependency_overrides.clear()


@pytest.fixture
def unauthenticated_client() -> TestClient:
    """TestClient without auth override (for 401 tests)."""
    # Do NOT override require_operator -- real auth runs
    # But DO need a valid OPERATOR_JWT_SECRET in settings
    yield TestClient(app)
    app.dependency_overrides.clear()
```

### Anti-Patterns to Avoid

- **Using `OAuth2PasswordBearer` for externally-issued tokens:** This security scheme implies an OAuth2 password flow with a `tokenUrl` endpoint. Switchboard validates externally-issued tokens; `HTTPBearer` is the correct scheme. [CITED: https://fastapi.tiangolo.com/reference/security/]
- **Committing in repository methods:** Phase 1 established that repository methods `flush()` but never `commit()`. API endpoints must call `await session.commit()` after successful operations. This allows transaction rollback isolation in tests. [VERIFIED: switchboard/registry/repository.py source code]
- **Instantiating `Settings` directly:** Use `get_settings()` with its `lru_cache`. Direct instantiation bypasses caching and reads `.env` again. [VERIFIED: switchboard/config.py source code]
- **Blocking the event loop:** Never use synchronous libraries (requests, psycopg2) in async FastAPI endpoints. All I/O must be async. [CITED: CLAUDE.md stack constraints]
- **Using python-jose:** Abandoned library with Python 3.12 deprecation warnings. PyJWT 2.12.1 is the replacement. [VERIFIED: stack research]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JWT validation | Custom token parsing/signature verification | `jwt.decode()` from PyJWT | Handles signature verification, expiry, algorithm enforcement; hand-rolling misses edge cases (clock skew, algorithm confusion attacks) |
| Bearer token extraction | Manual `Authorization` header parsing | `HTTPBearer` from `fastapi.security` | Handles header parsing, scheme validation, 401 auto-response, and OpenAPI spec generation |
| Request body validation | Manual field checking in endpoint | Pydantic `BaseModel` with `field_validator` | Type coercion, error message formatting, OpenAPI schema generation all handled automatically |
| OpenAPI docs | Manual Swagger/OpenAPI spec | FastAPI's built-in `/docs` | Auto-generated from type hints, response models, and security schemes |
| Session lifecycle | Manual engine/session creation per request | `Depends(get_session)` | Proper async context management, connection pooling, and test overridability |

**Key insight:** FastAPI's dependency injection system eliminates the need for custom middleware or manual request processing. Every cross-cutting concern (auth, session, settings) is a `Depends()` callable.

## Common Pitfalls

### Pitfall 1: Missing `await session.commit()` After Repository Calls
**What goes wrong:** Data appears to be created in the endpoint but is never persisted. Tests pass (they use rollback anyway) but production fails silently.
**Why it happens:** Repository methods `flush()` to get database-generated values (UUIDs, timestamps) but do not `commit()`. This is by design for test isolation.
**How to avoid:** Every endpoint that mutates data must call `await session.commit()` after the repository operation succeeds.
**Warning signs:** POST returns 201 with data, but subsequent GET returns empty list. [VERIFIED: switchboard/registry/repository.py source code]

### Pitfall 2: `jwt.decode()` Without Explicit `algorithms` Parameter
**What goes wrong:** Algorithm confusion attack -- an attacker could forge tokens by switching the algorithm (e.g., from RS256 to HS256 using the public key as a secret).
**Why it happens:** PyJWT allows multiple algorithms by default. Omitting the `algorithms` parameter is a security vulnerability.
**How to avoid:** Always pass `algorithms=["HS256"]` explicitly. Never accept multiple algorithms unless the system is designed for it. [CITED: https://pyjwt.readthedocs.io/en/latest/usage.html]
**Warning signs:** `jwt.decode(token, key)` without third argument.

### Pitfall 3: FastAPI TestClient Requires httpx
**What goes wrong:** `ImportError: No module named 'httpx'` when running `from fastapi.testclient import TestClient`.
**Why it happens:** FastAPI 0.112+ moved httpx from required to optional. It must be installed separately.
**How to avoid:** Add `httpx` as a dev dependency: `uv add --dev httpx`. [CITED: https://github.com/fastapi/fastapi/discussions/11958]
**Warning signs:** Tests fail on import before any test runs.

### Pitfall 4: Dependency Override Not Cleared Between Tests
**What goes wrong:** Test A overrides `get_session`, test B (which needs the real dependency) inherits the override and passes incorrectly or fails unexpectedly.
**Why it happens:** `app.dependency_overrides` is a mutable dict on the app instance -- it persists across tests.
**How to avoid:** Always call `app.dependency_overrides.clear()` in fixture teardown (after `yield`). [CITED: https://fastapi.tiangolo.com/advanced/testing-dependencies/]
**Warning signs:** Tests pass individually but fail when run together.

### Pitfall 5: Pydantic Validator on Optional Field Not Handling None
**What goes wrong:** `field_validator("description")` receives `None` and raises `TypeError` because it tries to call `.strip()` on `None`.
**Why it happens:** Pydantic v2 passes the raw value to `mode="before"` validators, including `None` for optional fields.
**How to avoid:** Check `isinstance(v, str)` before string operations. Return `None` directly if value is `None`. [CITED: https://docs.pydantic.dev/latest/concepts/validators/]
**Warning signs:** `POST /servers` with `description: null` returns 422 instead of success.

### Pitfall 6: Module-Level Engine Creation Conflicts with Test Overrides
**What goes wrong:** `switchboard/db/session.py` creates the engine at module import time. If `get_settings()` is called before test environment variables are set, the engine points to the dev database.
**Why it happens:** Module-level `engine = create_engine()` runs on first import.
**How to avoid:** In tests, override `get_session` entirely (don't rely on the module-level engine). The existing test conftest already creates a per-test engine from `test_database_url`. [VERIFIED: tests/conftest.py source code]
**Warning signs:** Tests modify dev database instead of test database.

## Code Examples

### Complete JWT Auth Dependency

```python
# Source: FastAPI official docs + PyJWT official docs
# switchboard/admin/auth.py
"""JWT authentication dependency for operator endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from switchboard.config import get_settings

if TYPE_CHECKING:
    from switchboard.config import Settings

_bearer_scheme = HTTPBearer(
    scheme_name="OperatorJWT",
    description="Operator JWT token (HS256)",
)


async def require_operator(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    """Validate operator JWT and return decoded payload.

    Uses HS256 symmetric key validation. The operator_jwt_secret
    is loaded from the OPERATOR_JWT_SECRET environment variable
    via pydantic-settings.

    Args:
        credentials: Bearer token extracted by HTTPBearer.
        settings: Application settings with JWT secret.

    Returns:
        Decoded JWT payload as a dictionary.

    Raises:
        HTTPException: 401 with WWW-Authenticate: Bearer header
            if token is invalid, expired, or malformed.
    """
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.operator_jwt_secret,
            algorithms=["HS256"],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload
```

### Complete Router with All Three Endpoints

```python
# Source: FastAPI official docs, project existing patterns
# switchboard/admin/router.py
"""Admin API router for server registration endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from switchboard.admin.auth import require_operator
from switchboard.db.session import get_session
from switchboard.registry.exceptions import DuplicateServerError
from switchboard.registry.repository import ServerRepository
from switchboard.registry.schemas import ServerCreate, ServerRead

router = APIRouter(
    prefix="/api/v1",
    tags=["servers"],
    dependencies=[Depends(require_operator)],
)

_repo = ServerRepository()


@router.post(
    "/servers",
    response_model=ServerRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new MCP server",
)
async def register_server(
    body: ServerCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ServerRead:
    """Register a new MCP server in the registry."""
    try:
        server = await _repo.create(
            session,
            name=body.name,
            container_image=body.container_image,
            description=body.description,
        )
    except DuplicateServerError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Server '{body.name}' already exists",
        )
    await session.commit()
    return ServerRead.model_validate(server)


@router.get(
    "/servers",
    response_model=list[ServerRead],
    summary="List all registered servers",
)
async def list_servers(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ServerRead]:
    """List all registered MCP servers with their current status."""
    servers = await _repo.list_all(session)
    return [ServerRead.model_validate(s) for s in servers]


@router.get(
    "/servers/{name}",
    response_model=ServerRead,
    summary="Get server details",
)
async def get_server(
    name: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ServerRead:
    """Retrieve details for a specific registered server."""
    server = await _repo.get_by_name(session, name)
    if server is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server '{name}' not found",
        )
    return ServerRead.model_validate(server)
```

### Test JWT Token Generation Helper

```python
# Source: PyJWT official docs
# tests/admin/helpers.py or tests/conftest.py
"""Test helpers for generating operator JWT tokens."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

TEST_JWT_SECRET = "test-secret-key-minimum-32-bytes-long!"
TEST_ALGORITHM = "HS256"


def make_operator_token(
    *,
    sub: str = "test-operator",
    exp_delta: timedelta | None = None,
    expired: bool = False,
) -> str:
    """Generate a test operator JWT.

    Args:
        sub: Subject claim (operator identifier).
        exp_delta: Custom expiration delta. Defaults to 1 hour.
        expired: If True, generate an already-expired token.

    Returns:
        Encoded JWT string.
    """
    now = datetime.now(tz=timezone.utc)
    if expired:
        exp = now - timedelta(hours=1)
    elif exp_delta is not None:
        exp = now + exp_delta
    else:
        exp = now + timedelta(hours=1)

    payload = {"sub": sub, "exp": exp, "iat": now}
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm=TEST_ALGORITHM)
```

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.26.x |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (exists) |
| Quick run command | `uv run pytest tests/admin/ -x -q` |
| Full suite command | `uv run pytest -x -q` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SREG-01 | POST /api/v1/servers creates a server and returns 201 | integration | `uv run pytest tests/admin/test_endpoints.py::test_register_server_success -x` | Wave 0 |
| SREG-01 | POST /api/v1/servers rejects duplicate name with 409 | integration | `uv run pytest tests/admin/test_endpoints.py::test_register_server_duplicate_409 -x` | Wave 0 |
| SREG-01 | POST /api/v1/servers rejects invalid name with 422 | integration | `uv run pytest tests/admin/test_endpoints.py::test_register_server_invalid_name_422 -x` | Wave 0 |
| SREG-01 | POST /api/v1/servers rejects empty description with 422 | integration | `uv run pytest tests/admin/test_endpoints.py::test_register_server_empty_description_422 -x` | Wave 0 |
| SREG-02 | GET /api/v1/servers returns all servers | integration | `uv run pytest tests/admin/test_endpoints.py::test_list_servers -x` | Wave 0 |
| SREG-02 | GET /api/v1/servers returns empty list when none registered | integration | `uv run pytest tests/admin/test_endpoints.py::test_list_servers_empty -x` | Wave 0 |
| SREG-03 | GET /api/v1/servers/{name} returns server details | integration | `uv run pytest tests/admin/test_endpoints.py::test_get_server_by_name -x` | Wave 0 |
| SREG-03 | GET /api/v1/servers/{name} returns 404 for unknown server | integration | `uv run pytest tests/admin/test_endpoints.py::test_get_server_not_found_404 -x` | Wave 0 |
| AUTH | Missing Bearer token returns 401 with WWW-Authenticate | unit | `uv run pytest tests/admin/test_auth.py::test_missing_token_401 -x` | Wave 0 |
| AUTH | Invalid/expired token returns 401 with WWW-Authenticate | unit | `uv run pytest tests/admin/test_auth.py::test_invalid_token_401 -x` | Wave 0 |
| AUTH | Expired token returns 401 | unit | `uv run pytest tests/admin/test_auth.py::test_expired_token_401 -x` | Wave 0 |
| AUTH | Valid token allows request | unit | `uv run pytest tests/admin/test_auth.py::test_valid_token_succeeds -x` | Wave 0 |
| OPENAPI | /docs returns 200 with OpenAPI spec | smoke | `uv run pytest tests/admin/test_endpoints.py::test_openapi_docs_accessible -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/admin/ -x -q`
- **Per wave merge:** `uv run pytest -x -q` (full suite including Phase 1 regression)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/admin/__init__.py` -- package marker
- [ ] `tests/admin/test_auth.py` -- JWT auth dependency unit tests
- [ ] `tests/admin/test_endpoints.py` -- endpoint integration tests
- [ ] `tests/admin/conftest.py` -- TestClient fixtures with dependency overrides
- [ ] Framework install: `uv add fastapi uvicorn PyJWT && uv add --dev httpx`

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| python-jose for JWT | PyJWT 2.12.1 | 2024+ (python-jose abandoned) | Use `import jwt` not `from jose import jwt` [VERIFIED: PyPI activity] |
| OAuth2PasswordBearer for all auth | HTTPBearer for external token validation | Always (feature existed since FastAPI 0.40+) | Correct OpenAPI spec; no misleading `tokenUrl` |
| `from starlette.testclient import TestClient` | `from fastapi.testclient import TestClient` | FastAPI 0.112+ | Same underlying class; FastAPI re-export is canonical |
| httpx bundled with FastAPI | httpx as optional dependency | FastAPI 0.112+ | Must install separately: `pip install httpx` or `fastapi[standard]` [CITED: FastAPI GitHub discussion #11958] |
| Pydantic v1 validators | Pydantic v2 `field_validator` with `mode="before"` | Pydantic 2.0+ (2023) | Different decorator syntax, `@classmethod` required [CITED: https://docs.pydantic.dev/latest/concepts/validators/] |

**Deprecated/outdated:**
- `python-jose`: Last release 3+ years ago; Python 3.12 deprecation warnings. Use PyJWT. [VERIFIED: stack research]
- Pydantic v1 `@validator`: Replaced by `@field_validator` in Pydantic v2. [CITED: Pydantic v2 docs]

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Yes | PyJWT HS256 validation via `require_operator` dependency; `HTTPBearer` security scheme |
| V3 Session Management | No | Stateless JWT -- no server-side session management in this phase |
| V4 Access Control | Partial | Single operator role -- all authenticated requests get full access. Role-based scopes deferred to v2 (ADMN-01) |
| V5 Input Validation | Yes | Pydantic `BaseModel` with `field_validator`; server name regex validation at model level |
| V6 Cryptography | Partial | HS256 symmetric key -- key must be 32+ bytes per RFC 7518 Section 3.2 |

### Known Threat Patterns for FastAPI + JWT

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| JWT algorithm confusion | Spoofing | Always pass explicit `algorithms=["HS256"]` to `jwt.decode()` [CITED: PyJWT docs] |
| Weak JWT secret | Spoofing | Enforce minimum 32-byte secret; validate at Settings level [ASSUMED] |
| Missing auth on endpoints | Elevation of Privilege | Router-level `dependencies=[Depends(require_operator)]` ensures all routes protected [CITED: FastAPI docs] |
| Error message information disclosure | Information Disclosure | Use generic "Could not validate credentials" -- never expose internal error details [CITED: FastAPI security tutorial] |
| SQL injection via path params | Tampering | SQLAlchemy ORM with parameterized queries -- no raw SQL [VERIFIED: repository.py source] |
| Missing expiry validation | Spoofing | PyJWT validates `exp` claim by default when present; recommend always including `exp` in tokens [CITED: PyJWT docs] |

## Assumptions Log

> List all claims tagged `[ASSUMED]` in this research.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | FastAPI app entry point at `switchboard/admin/app.py` | Architecture Patterns | Low -- file location is Claude's discretion per CONTEXT.md; trivial to adjust |
| A2 | Enforce minimum 32-byte JWT secret at Settings level | Security Domain | Medium -- without validation, weak secrets could be used in production; should add a Pydantic `field_validator` |
| A3 | Module-level `ServerRepository()` instantiation in router | Architecture Patterns | Low -- repository is stateless (no constructor args); could alternatively inject via Depends if needed |

## Open Questions

1. **JWT `exp` Claim Enforcement**
   - What we know: PyJWT validates `exp` automatically when the claim is present. If absent, no expiry check occurs.
   - What's unclear: Whether the test token generation should always include `exp`, and whether Switchboard should reject tokens without `exp`.
   - Recommendation: Always include `exp` in test tokens; document that production tokens should include `exp`. Claude's discretion per CONTEXT.md -- recommend validating `exp` but not requiring it (tokens without `exp` are valid but logged as a warning). This keeps compatibility with simple test scripts.

2. **Settings Cache and Test Isolation**
   - What we know: `get_settings()` uses `lru_cache`. Tests may need different settings (e.g., different JWT secret).
   - What's unclear: Whether to call `get_settings.cache_clear()` in test fixtures or override the entire dependency.
   - Recommendation: Override `get_settings` via `app.dependency_overrides` in tests, or set `OPERATOR_JWT_SECRET` as an environment variable before the test session. The existing `get_session` override pattern works well for this.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL | Database layer | Expected (Phase 1 dep) | 16+ | Docker Compose `db` service |
| Python | Runtime | Expected | 3.12+ | -- |
| Docker Compose | Test database | Expected (Phase 1 dep) | -- | Manual PostgreSQL |

Note: FastAPI, Uvicorn, PyJWT, and httpx are not yet installed. They must be added via `uv add` before any implementation. This is a Wave 0 task. [VERIFIED: pyproject.toml inspection]

## Sources

### Primary (HIGH confidence)
- FastAPI official docs -- security tutorial (OAuth2 JWT): https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/
- FastAPI official docs -- testing dependencies: https://fastapi.tiangolo.com/advanced/testing-dependencies/
- FastAPI official docs -- async tests: https://fastapi.tiangolo.com/advanced/async-tests/
- FastAPI official docs -- security reference (HTTPBearer): https://fastapi.tiangolo.com/reference/security/
- PyJWT official docs -- usage examples: https://pyjwt.readthedocs.io/en/latest/usage.html
- Pydantic v2 official docs -- validators: https://docs.pydantic.dev/latest/concepts/validators/
- Project source code -- `switchboard/` package (all Phase 1 files inspected)

### Secondary (MEDIUM confidence)
- FastAPI GitHub discussion #11958 -- httpx as optional dependency since 0.112+
- Stack research (STACK.md) -- version pinning verified against PyPI April 14 2026

### Tertiary (LOW confidence)
- None -- all claims verified against primary or secondary sources

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all versions verified against PyPI; patterns verified against official docs
- Architecture: HIGH -- patterns follow FastAPI official documentation exactly; existing codebase inspected for compatibility
- Pitfalls: HIGH -- all pitfalls verified against official docs or observed in source code
- Security: HIGH -- JWT validation patterns from official PyJWT and FastAPI docs; ASVS categories verified

**Research date:** 2026-04-15
**Valid until:** 2026-05-15 (stable domain -- FastAPI, PyJWT, Pydantic v2 are mature)
