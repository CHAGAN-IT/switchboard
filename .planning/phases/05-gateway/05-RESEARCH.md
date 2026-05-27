# Phase 5: Gateway - Research

**Researched:** 2026-04-16
**Domain:** HTTP reverse proxy, MCP Streamable HTTP transport, JWT auth, structured logging, RFC 9728
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Customer JWT Authentication**
- D-01: Gateway uses a separate `CUSTOMER_JWT_SECRET` env var — distinct from `OPERATOR_JWT_SECRET` used by Admin API. Add this field to `Settings` in `switchboard/config.py`.
- D-02: Customer token audience is `switchboard-gateway`. Operator token audience remains `switchboard-admin`. The gateway auth dependency rejects tokens with wrong audience.
- D-03: Required claims: `exp`, `iat`, `sub`. Algorithm: HS256. The `sub` claim value is included in every structured log line as the user identity field (OBSV-01).
- D-04: JWT validation failure returns HTTP 401 with `WWW-Authenticate: Bearer` header — identical pattern to `require_operator` in `switchboard/admin/auth.py`. Create `require_customer` dependency in `switchboard/gateway/auth.py`.

**Gateway App Structure**
- D-05: Standalone FastAPI app in `switchboard/gateway/app.py` — completely separate from Admin API app. Own uvicorn process, own docker-compose service.
- D-06: Gateway docker-compose service exposes host port 8080 (internal container port 8000).
- D-07: Gateway joins the `switchboard-internal` Docker network AND needs a published host port for customer access. Both network entries required.

**Request Routing Strategy**
- D-08: Stateless routing — no database connection in the gateway. Route by server name only: forward to `http://sb-{name}:8000/mcp`. Backend unreachable → HTTP 503 `{"detail": "Server '{name}' is unavailable"}`.
- D-09: Server name validated against pattern `^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$` before forwarding. Invalid names → 404 `{"detail": "Server '{name}' not found"}`.
- D-10: The `Authorization` header is stripped before forwarding. Backend containers never receive the customer's Bearer token.
- D-11: All other headers (including `Mcp-Session-Id`, `Content-Type`, `Accept`) are forwarded unchanged.

**Session Stickiness**
- D-12: Real in-memory session map: `dict[str, str]` mapping `Mcp-Session-Id` → backend container URL. Protected by `asyncio.Lock()`.
- D-13: First request with a new `Mcp-Session-Id`: record target URL before forwarding. Subsequent requests with same ID: use recorded URL regardless of server name in path.
- D-14: Requests without `Mcp-Session-Id`: route normally by server name without map lookup.

**Structured Logging (OBSV-01)**
- D-15: Use `structlog` with JSON output. Each proxied request produces one log line with: `trace_id` (UUID v4), `user_identity` (from JWT `sub`), `server_name`, `http_method`, `http_status`, `timestamp` (ISO 8601). Tool name logged if extractable from request body.
- D-16: Log emission is in middleware or route wrapper — not inside the httpx call — so it captures the final status code.

**RFC 9728 Well-Known Endpoint**
- D-17: `GET /.well-known/oauth-protected-resource` returns a JSON document with `resource` (gateway base URL) and `bearer_methods_supported: ["header"]`. Minimal compliant implementation per RFC 9728 §2.

### Claude's Discretion
- httpx `AsyncClient` lifespan management (startup/shutdown event or `asyncio_client` dependency)
- Whether to use FastAPI middleware or route-level injection for trace ID generation
- Exact structlog processor chain (JSON renderer, timestamp format)
- How to handle SSE stream buffering (whether to set `Transfer-Encoding: chunked` or use `StreamingResponse`)
- Whether to add a docker-compose `healthcheck` for the gateway service (recommended)
- `asyncio.Lock` placement (module-level singleton vs. app state)

### Deferred Ideas (OUT OF SCOPE)
- Multiple MCP container instances per server name (true load balancing)
- Redis-backed session store (for multi-process gateway instances)
- Customer token issuance endpoint (Authlib OAuth2 server, SECU-03 full implementation)
- Rate limiting per server (SECU-04)
- Legacy SSE transport support (GTWY-04)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| GTWY-01 | Customer requests to `/servers/{server-name}` are routed to the corresponding registered container | D-08/D-09: stateless routing to `http://sb-{name}:8000/mcp`; name validation before forwarding |
| GTWY-02 | Gateway proxies MCP Streamable HTTP transport (POST for client→server messages, GET for SSE server→client streams) on the `/mcp` endpoint | MCP spec verified: POST sends JSON-RPC, GET opens SSE stream; both must be proxied transparently |
| GTWY-03 | Gateway tracks `Mcp-Session-Id` headers and routes requests with an existing session ID to the same container instance | D-12/D-13/D-14: in-memory dict + asyncio.Lock; session stickiness by session ID |
| SECU-01 | Gateway validates JWT Bearer token on every customer request; returns `401 Unauthorized` with `WWW-Authenticate` header on failure | D-01 through D-04: `require_customer` dependency mirrors `require_operator` pattern exactly |
| SECU-02 | Gateway terminates TLS for all customer-facing traffic; backend container communication uses the internal network unencrypted | Handled at Docker/nginx layer for local dev; noted for prod. The `Authorization` header strip (D-10) is the code-level concern |
| OBSV-01 | Gateway emits structured JSON logs for each request including trace ID, user identity (from JWT), server name, tool name (if applicable), HTTP status, and timestamp | D-15/D-16: structlog 25.5.0 with JSON renderer; contextvars for per-request binding |
| PLAT-01 | All platform components (gateway, admin API, reference servers, database) run locally via Docker Compose for development | D-05/D-06/D-07: gateway service added to docker-compose.yml; depends_on db, echo, ping |
</phase_requirements>

---

## Summary

Phase 5 adds the gateway service — a FastAPI application that authenticates customer JWTs and transparently proxies MCP Streamable HTTP requests to backend containers. The three core technical challenges are: (1) building a correct streaming reverse proxy using httpx that handles both POST (JSON-RPC request/response) and GET (SSE server→client streams) without buffering or losing chunks; (2) implementing in-memory session stickiness that routes subsequent `Mcp-Session-Id` requests to the same container; and (3) emitting per-request structured JSON logs using structlog with contextvars.

The phase is well-constrained by prior decisions. The `require_customer` auth dependency is a near-direct copy of the existing `require_operator` pattern in `switchboard/admin/auth.py` — only the secret and audience differ. The routing logic is stateless (no DB); all container discovery is by DNS name (`sb-{name}`) on the internal Docker network. The RFC 9728 well-known endpoint requires only the `resource` field by spec; the minimal document satisfies compliance.

The main implementation risk is the streaming proxy pattern. httpx's `AsyncClient` must be used in "manual streaming mode" (`send(req, stream=True)`) so that SSE responses flow chunk-by-chunk through FastAPI's `StreamingResponse` without buffering. The `aclose()` cleanup must run even if the client disconnects mid-stream; this requires a `BackgroundTask`. Several headers must be stripped or modified before forwarding (notably `Authorization` and `host`).

**Primary recommendation:** Use FastAPI lifespan to create a single shared `httpx.AsyncClient` stored on `app.state`. Use `send(req, stream=True)` with `StreamingResponse(backend_resp.aiter_raw(), background=BackgroundTask(backend_resp.aclose))` for all proxy routes. Log in an ASGI middleware using `structlog.contextvars.bind_contextvars()` after the response completes.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.135.3 | Gateway ASGI app | Project stack; existing Admin API uses same version [VERIFIED: uv.lock] |
| httpx | 0.28.1 | Async reverse proxy HTTP client | Project stack; async-native, supports streaming via `send(stream=True)` [VERIFIED: uv.lock] |
| PyJWT | 2.12.1 | JWT decode for `require_customer` | Project stack; mirrors `require_operator` [VERIFIED: uv.lock] |
| structlog | 25.5.0 | Structured JSON logging | Project stack recommendation; production-grade; supports contextvars for per-request binding [VERIFIED: pypi.org] |
| uvicorn | 0.44.0 | ASGI server for gateway process | Project stack [VERIFIED: uv.lock] |
| anyio | 4.13.0 | Async primitives (asyncio.Lock) | Transitively installed; use stdlib `asyncio.Lock` directly [VERIFIED: uv.lock] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| httpx-sse | 0.4.3 | SSE consumption via httpx | If parsing individual SSE events from backend is needed (not required for simple passthrough proxy) [VERIFIED: uv.lock] |
| respx | 0.23.1 | Mock httpx in tests | Test the proxy layer without running real containers [VERIFIED: pypi.org Apr 8, 2026] |
| pytest-asyncio | 0.26.x | Async test support | Already in project dev deps [VERIFIED: pyproject.toml] |

### Not Needed for Phase 5
| Excluded | Why |
|----------|-----|
| fastmcp | Used only by reference server containers, not the gateway |
| Authlib | Token issuance deferred to post-v1 |
| docker SDK | Container lifecycle management is Phase 3/6 concern |

**Installation (additions needed):**
```bash
uv add structlog
uv add --dev respx
```

Note: `httpx`, `pyjwt`, `fastapi`, `uvicorn`, `httpx-sse` are already in the lockfile. `structlog` and `respx` are NOT currently in the main project lockfile and must be added.

---

## Architecture Patterns

### Recommended Project Structure
```
switchboard/gateway/
├── __init__.py          # Already exists (stub from Phase 1)
├── app.py               # FastAPI app factory + lifespan
├── auth.py              # require_customer() dependency
└── proxy.py             # proxy_mcp_request() handler + session map

tests/gateway/
├── __init__.py
├── conftest.py          # Gateway test client, make_customer_token helper
├── test_auth.py         # 401 paths, missing token, wrong audience
├── test_proxy.py        # Routing, header stripping, 503 on unreachable backend
├── test_session.py      # Session stickiness map behavior
├── test_wellknown.py    # RFC 9728 endpoint content
└── test_logging.py      # Structured log fields verification
```

### Pattern 1: FastAPI Lifespan for httpx AsyncClient

**What:** Create a single persistent `httpx.AsyncClient` at app startup, store on `app.state`, close at shutdown. This is the FastAPI-recommended approach for connection pooling. [CITED: fastapi.tiangolo.com/advanced/events/]

**When to use:** Any component that needs a shared long-lived external connection.

**Example:**
```python
# Source: FastAPI lifespan docs (fastapi.tiangolo.com/advanced/events/)
from contextlib import asynccontextmanager
from fastapi import FastAPI
import httpx

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create shared client
    app.state.http_client = httpx.AsyncClient(timeout=30.0)
    yield
    # Shutdown: close cleanly
    await app.state.http_client.aclose()

app = FastAPI(lifespan=lifespan)
```

Access in route handlers via `request.app.state.http_client`.

### Pattern 2: Streaming Reverse Proxy with Manual Stream Mode

**What:** Use `client.send(req, stream=True)` to avoid buffering the backend response. Wrap with `StreamingResponse` and a `BackgroundTask` for cleanup. This is the only correct pattern for proxying SSE — buffering will break SSE streams. [CITED: python-httpx.org/async/]

**When to use:** All `/servers/{name}/mcp` proxy routes (both POST and GET).

**Example:**
```python
# Source: httpx docs (python-httpx.org/async/) + FastAPI proxy discussion #9599
from fastapi import Request
from fastapi.background import BackgroundTask
from starlette.responses import StreamingResponse
import httpx

async def proxy_to_backend(
    request: Request,
    backend_url: str,
    http_client: httpx.AsyncClient,
) -> StreamingResponse:
    # Build forwarded request: strip Authorization, strip host
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("authorization", "host")
    }
    rp_req = http_client.build_request(
        method=request.method,
        url=backend_url,
        headers=headers,
        content=request.stream(),  # streams request body without buffering
    )
    rp_resp = await http_client.send(rp_req, stream=True)
    return StreamingResponse(
        rp_resp.aiter_raw(),
        status_code=rp_resp.status_code,
        headers=dict(rp_resp.headers),
        background=BackgroundTask(rp_resp.aclose),
    )
```

**Critical notes:**
- `request.stream()` is an async generator — use it to avoid buffering the entire POST body in memory (important for large tool calls).
- `rp_resp.aiter_raw()` yields raw bytes without decoding — correct for proxying binary-compatible SSE.
- `BackgroundTask(rp_resp.aclose)` runs after the response is sent, ensuring the httpx response is closed even if the client disconnects.
- The `host` header MUST be removed before forwarding. If sent, httpx will route to the wrong host. [CITED: github.com/fastapi/fastapi/discussions/9599]
- Do NOT copy the `content-length` header from the downstream response if the response is chunked; Starlette handles this.

### Pattern 3: Session Stickiness with asyncio.Lock

**What:** Module-level (or `app.state`) dict + `asyncio.Lock` for concurrent-safe session routing. [VERIFIED: CONTEXT.md D-12/D-13]

**When to use:** Every proxy request that carries `Mcp-Session-Id`.

**Example:**
```python
# Source: CONTEXT.md decisions D-12/D-13/D-14
import asyncio
from typing import ClassVar

_session_map: dict[str, str] = {}
_session_lock: asyncio.Lock = asyncio.Lock()

async def resolve_backend(
    server_name: str,
    session_id: str | None,
) -> str:
    """Return backend URL, using session map if session_id present."""
    if session_id is None:
        return f"http://sb-{server_name}:8000"

    async with _session_lock:
        if session_id in _session_map:
            return _session_map[session_id]
        # First request with this session ID — record and return
        target = f"http://sb-{server_name}:8000"
        _session_map[session_id] = target
        return target
```

**Note on Lock placement:** A module-level `asyncio.Lock()` is created when the module is first imported. Because Python's asyncio event loop starts before modules are re-imported, this is safe in single-process uvicorn. For `app.state` placement, create the lock inside the lifespan function.

### Pattern 4: structlog Per-Request Context via Middleware

**What:** ASGI middleware binds `trace_id`, `user_identity`, `server_name` to structlog's contextvars before the route handler runs. The single log line is emitted after the response completes. [CITED: angelospanag.me/blog/structured-logging-using-structlog-and-fastapi]

**When to use:** Every incoming request through the gateway.

**Example:**
```python
# Source: structlog docs + community FastAPI patterns (2026)
import uuid
import structlog
from starlette.middleware.base import BaseHTTPMiddleware

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.JSONRenderer(),
    ],
)

log = structlog.get_logger()

class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            trace_id=str(uuid.uuid4()),
            http_method=request.method,
        )
        response = await call_next(request)
        # http_status available only after response is built
        log.info(
            "proxied_request",
            http_status=response.status_code,
        )
        return response
```

**Note:** The `user_identity` and `server_name` are extracted in the route handler (after JWT validation) and bound to contextvars there. Middleware handles the trace_id and final log emit.

### Pattern 5: RFC 9728 Well-Known Endpoint

**What:** `GET /.well-known/oauth-protected-resource` returns a minimal JSON metadata document. Only `resource` is required by the spec. [CITED: rfc-editor.org/rfc/rfc9728]

**When to use:** MCP clients auto-discover auth configuration per RFC 9728.

**Example:**
```python
# Source: RFC 9728 §2 (rfc-editor.org/rfc/rfc9728) — minimum compliant document
@app.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource(request: Request) -> dict:
    """RFC 9728 protected resource metadata."""
    base_url = str(request.base_url).rstrip("/")
    return {
        "resource": base_url,
        "bearer_methods_supported": ["header"],
    }
```

**Important field name correction:** The correct field is `bearer_methods_supported` (not `bearer_tokens_supported`). Values are `["header", "body", "query"]` for the bearer token delivery methods supported. [CITED: rfc-editor.org/rfc/rfc9728 §2]

### Anti-Patterns to Avoid

- **Buffering the proxy response:** Using `await client.get(url)` (non-streaming) will buffer the entire backend response before sending to the client. This breaks SSE streams and causes memory issues with large responses.
- **Creating AsyncClient per-request:** `async with httpx.AsyncClient() as client:` inside a route handler creates a new connection pool per request. Use the lifespan-managed client on `app.state`.
- **Forwarding the `host` header:** This causes httpx to route to the wrong backend. Always remove `host` from forwarded headers.
- **Forwarding `Authorization` to backend:** Non-negotiable strip (D-10). Backend containers must never receive the customer JWT.
- **Emitting log lines inside `aiter_raw()`:** The status code is unknown until after the response is constructed. Log in middleware after `call_next()` returns.
- **Not calling `rp_resp.aclose()`:** Without `BackgroundTask(rp_resp.aclose)`, the httpx response is never closed, leaking connections.
- **Creating `asyncio.Lock()` at class attribute level:** Locks must be created in the event loop. Create at module level (safe for single-process) or in the lifespan function.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP proxying with streaming | Custom chunk iterator with `asyncio.StreamReader` | `httpx.AsyncClient.send(stream=True)` + `StreamingResponse(aiter_raw())` | httpx handles connection pooling, retries, timeouts, chunked encoding, and HTTP/2 |
| Structured JSON logging | Custom JSON log formatter | `structlog` with `JSONRenderer()` processor | structlog handles contextvars, processor chain, timestamp formatting, and CloudWatch-compatible output |
| JWT validation | Custom HMAC-SHA256 implementation | `PyJWT` with `jwt.decode()` — copy `require_operator` pattern | PyJWT handles all RFC 7519 claim validation (exp, iat, aud) and algorithm enforcement |
| SSE passthrough detection | Content-type sniffing to decide streaming vs buffered | Always use streaming proxy — both POST and GET responses may be SSE | The MCP spec says POST responses MAY be SSE; detect at runtime is complex and fragile |
| Per-request UUID generation | Custom counter or timestamp-based ID | `uuid.uuid4()` | Cryptographically random, globally unique, no coordination needed |

**Key insight:** The most dangerous hand-roll in this phase is the streaming proxy. httpx's streaming API handles HTTP/1.1 chunked transfer encoding, HTTP/2 flow control, and response body cleanup automatically. Custom implementations almost always break on edge cases like empty SSE frames, premature client disconnect, or large binary payloads.

---

## Common Pitfalls

### Pitfall 1: Buffered Proxy Breaks SSE Streams

**What goes wrong:** Using `await client.get()` or `await client.post()` buffers the entire backend response before returning. MCP GET requests expect a persistent SSE stream; a buffered client will hang until the backend closes the connection.

**Why it happens:** httpx's non-streaming API is the default and simpler API.

**How to avoid:** Always use `await client.send(req, stream=True)` for proxy routes. Wrap in `StreamingResponse(rp_resp.aiter_raw(), background=BackgroundTask(rp_resp.aclose))`.

**Warning signs:** Integration test with echo server hangs indefinitely; SSE GET requests never return.

### Pitfall 2: asyncio.Lock Created Outside Event Loop

**What goes wrong:** `asyncio.Lock()` raises `DeprecationWarning: There is no current event loop` in Python 3.10+ if created at import time without a running loop. In Python 3.12+ this is an error.

**Why it happens:** Module-level lock creation runs at import time, which may precede the event loop.

**How to avoid:** In Python 3.12+, `asyncio.Lock()` can be created at module level safely (no longer requires a running loop). Verify this is the case in testing. Alternatively, create the lock inside the lifespan function and store on `app.state`.

**Warning signs:** `DeprecationWarning: There is no current event loop` during pytest collection.

### Pitfall 3: `host` Header Causes Backend Connection Failure

**What goes wrong:** Forwarding the original `host` header (e.g., `localhost:8080`) causes httpx to route the internal request to `localhost:8080` instead of `sb-echo:8000`. The container lookup fails.

**Why it happens:** httpx respects the `host` header for routing.

**How to avoid:** Always strip `host` from headers before building the forwarded request. Strip `authorization` at the same step.

**Warning signs:** Backend returns 404 or connection refused even when container is healthy; `sb-echo:8000` resolves correctly but request fails.

### Pitfall 4: `structlog` Not in Project Dependencies

**What goes wrong:** `import structlog` raises `ModuleNotFoundError` at runtime.

**Why it happens:** `structlog` is in the project's recommended stack but NOT currently in `pyproject.toml` or the lockfile.

**How to avoid:** Add `uv add structlog` as part of Wave 0 setup. This also requires updating the Dockerfile if it uses a locked install.

**Warning signs:** Gateway fails to start with `ModuleNotFoundError: No module named 'structlog'`.

### Pitfall 5: JWT `issuer` Claim Mismatch

**What goes wrong:** Customer tokens issued without `iss: "switchboard"` fail validation if the `require_customer` dependency enforces the `issuer` parameter (as `require_operator` does).

**Why it happens:** The existing `require_operator` validates `issuer="switchboard"`. If `require_customer` copies this exactly but test helper tokens omit `iss`, tests fail with `InvalidIssuerError`.

**How to avoid:** The CONTEXT.md decisions (D-03) specify `exp`, `iat`, `sub` as required claims but do not mention `iss`. Verify whether `iss` validation is included in `require_customer`. If yes, the test `make_customer_token` helper must include `iss: "switchboard"`.

**Warning signs:** `jwt.InvalidIssuerError` in test logs when using `make_customer_token` without `iss` claim.

### Pitfall 6: `respx` Not Mocking Streaming Responses Correctly

**What goes wrong:** `respx` mocks return buffered responses by default. Tests that check `StreamingResponse` behavior may not exercise the actual streaming code path.

**Why it happens:** `respx` simulates httpx responses as in-memory objects.

**How to avoid:** For streaming proxy unit tests, test the route with a real (or AsyncMock) httpx response that returns bytes. Use `respx` for testing 503 error paths and header stripping (where streaming behavior doesn't matter).

**Warning signs:** Unit tests pass but integration tests fail because `aiter_raw()` is never exercised.

### Pitfall 7: `CUSTOMER_JWT_SECRET` Not in conftest.py `os.environ.setdefault`

**What goes wrong:** The top-level `tests/conftest.py` sets `OPERATOR_JWT_SECRET` via `os.environ.setdefault` to satisfy `get_settings()` at import time. If `CUSTOMER_JWT_SECRET` is added to `Settings` with a mandatory validator, all tests (including admin tests) fail at import time with a validation error.

**Why it happens:** `Settings` is loaded once via `lru_cache` and both secrets are validated at instantiation.

**How to avoid:** When adding `customer_jwt_secret` to `Settings`, add a corresponding `os.environ.setdefault("CUSTOMER_JWT_SECRET", "pytest-customer-secret-32bytes!")` to the top-level `tests/conftest.py`.

**Warning signs:** All existing admin tests break with `ValueError: CUSTOMER_JWT_SECRET environment variable is required...` after adding the new field.

---

## Code Examples

Verified patterns from official sources:

### require_customer (mirrors require_operator exactly)
```python
# Source: switchboard/admin/auth.py (existing pattern to replicate)
_bearer_scheme = HTTPBearer(
    scheme_name="CustomerJWT",
    description="Customer JWT token (HS256)",
)

async def require_customer(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    """Validate customer JWT and return decoded payload."""
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.customer_jwt_secret,
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "sub"]},
            audience="switchboard-gateway",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    return payload
```

### Server name validation (reuse existing regex)
```python
# Source: switchboard/registry/models.py (SERVER_NAME_PATTERN already defined)
import re
from switchboard.registry.models import SERVER_NAME_PATTERN

def validate_server_name(name: str) -> bool:
    """Return True if name matches the server name pattern."""
    return bool(SERVER_NAME_PATTERN.match(name))
```

### Gateway docker-compose service addition
```yaml
# Source: CONTEXT.md D-05/D-06/D-07
  gateway:
    build:
      context: .
    command: uvicorn switchboard.gateway.app:app --host 0.0.0.0 --port 8000
    ports:
      - "8080:8000"
    networks:
      - switchboard-internal
    environment:
      CUSTOMER_JWT_SECRET: ${CUSTOMER_JWT_SECRET}
      OPERATOR_JWT_SECRET: ${OPERATOR_JWT_SECRET}
      DATABASE_URL: ${DATABASE_URL}
    depends_on:
      db:
        condition: service_healthy
      echo:
        condition: service_healthy
      ping:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/.well-known/oauth-protected-resource')\""]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
```

### structlog configuration (JSON mode)
```python
# Source: structlog docs + community FastAPI patterns (angelospanag.me/blog, 2026)
import structlog

def configure_logging() -> None:
    """Configure structlog for JSON output in production."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
    )
```

Call `configure_logging()` at the top of `switchboard/gateway/app.py` before app instantiation.

### MCP proxy route skeleton (POST + GET on same path)
```python
# Source: MCP spec (modelcontextprotocol.io) + httpx docs (python-httpx.org/async/)
@app.api_route(
    "/servers/{server_name}/mcp",
    methods=["GET", "POST", "DELETE"],
)
async def proxy_mcp(
    server_name: str,
    request: Request,
    payload: Annotated[dict, Depends(require_customer)],
) -> StreamingResponse:
    """Proxy MCP Streamable HTTP requests to the backend container."""
    # 1. Validate server name pattern
    if not SERVER_NAME_PATTERN.match(server_name):
        raise HTTPException(status_code=404, detail=f"Server '{server_name}' not found")

    # 2. Resolve backend URL (session stickiness)
    session_id = request.headers.get("Mcp-Session-Id")
    backend_base = await resolve_backend(server_name, session_id)

    # 3. Forward request
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("authorization", "host")
    }
    rp_req = request.app.state.http_client.build_request(
        method=request.method,
        url=f"{backend_base}/mcp",
        headers=headers,
        content=request.stream(),
    )
    try:
        rp_resp = await request.app.state.http_client.send(rp_req, stream=True)
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"Server '{server_name}' is unavailable",
        ) from None

    # 4. Bind structlog context for log line emission (in middleware)
    structlog.contextvars.bind_contextvars(
        server_name=server_name,
        user_identity=payload["sub"],
    )

    return StreamingResponse(
        rp_resp.aiter_raw(),
        status_code=rp_resp.status_code,
        headers=dict(rp_resp.headers),
        background=BackgroundTask(rp_resp.aclose),
    )
```

---

## MCP Streamable HTTP Transport Summary

[CITED: modelcontextprotocol.io/specification/2025-03-26/basic/transports]

Key facts verified from the official spec:

| Property | Value |
|----------|-------|
| MCP endpoint path | Single path supporting both GET and POST (e.g. `/mcp`) |
| POST (client→server) | Sends JSON-RPC request/notification/response; may return `application/json` OR `text/event-stream` |
| GET (server→client) | Opens SSE stream for server-initiated messages; returns `text/event-stream` or 405 |
| DELETE (session termination) | Client sends DELETE to terminate session; server may return 405 |
| `Mcp-Session-Id` assignment | Server sets this in the `InitializeResult` HTTP response header |
| `Mcp-Session-Id` forwarding | Clients MUST include on all subsequent requests; gateway forwards it unchanged (D-11) |
| Client disconnection | Should NOT be interpreted as cancellation; spec-correct to keep session alive |
| `Accept` header | Client MUST include both `application/json` and `text/event-stream` |

**Proxy-specific note:** The gateway does not need to interpret MCP JSON-RPC — it proxies opaque bytes. The gateway only needs to: (1) route by server name/session, (2) strip `Authorization`, (3) handle SSE by using streaming response, and (4) handle `ConnectError` → 503.

---

## RFC 9728 Well-Known Endpoint Details

[CITED: rfc-editor.org/rfc/rfc9728]

| Property | Value |
|----------|-------|
| Endpoint path | `/.well-known/oauth-protected-resource` |
| Required fields | `resource` (the protected resource's identifier URI) |
| Optional field in scope | `bearer_methods_supported` — JSON array of `"header"`, `"body"`, `"query"` |
| Minimum compliant document | `{"resource": "https://gateway.example.com"}` |
| Field name correction | `bearer_methods_supported` NOT `bearer_tokens_supported` |
| Resource field constraint | Must match the URL prefix used to retrieve the metadata |

The CONTEXT.md D-17 mentions `bearer_tokens_supported: true` — this is **incorrect**. The RFC 9728 field is `bearer_methods_supported` (an array). The implementation should use `"bearer_methods_supported": ["header"]` to indicate that Bearer tokens must be sent in the `Authorization` header.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SSE transport (`/sse` endpoint) | Streamable HTTP (`/mcp` endpoint, POST+GET) | MCP spec 2025-03-26 | Legacy SSE is deprecated; Streamable HTTP is the production standard |
| `@app.on_event("startup")` | `@asynccontextmanager` lifespan | FastAPI 0.93+ | Old event handlers still work but are deprecated |
| `python-jose` for JWT | `PyJWT` | ~2023 | python-jose is abandoned, has Python 3.12 deprecation warnings |
| Gunicorn + uvicorn workers | `uvicorn --workers N` in containers | 2022+ | Gunicorn adds complexity in orchestrated environments |

**Deprecated/outdated:**
- `text/event-stream` SSE transport for MCP: The `2024-11-05` spec version used SSE+POST separate endpoints. The `2025-03-26` spec replaced this with Streamable HTTP. The reference servers (echo, ping) already use `streamable-http` transport as confirmed in `servers/echo/server.py`.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `asyncio.Lock()` created at module level is safe in Python 3.12+ without a running event loop | Architecture Patterns (Pattern 3) | If wrong, lock must be created in lifespan function and accessed via `app.state`; low risk as the alternative is simple |
| A2 | The `require_customer` dependency omits `issuer` validation (unlike `require_operator` which validates `issuer="switchboard"`) | Code Examples | If issuer validation is added, `make_customer_token` helper must include `iss` claim |
| A3 | `structlog.processors.JSONRenderer()` is the correct class name (not `structlog.processors.JSONRenderer` vs `structlog.dev.JSONRenderer`) | Code Examples | Wrong class means startup error; easily fixed but a gotcha during implementation |
| A4 | `request.stream()` in FastAPI returns an async iterable compatible with `httpx.build_request(content=...)` | Code Examples | If incompatible, use `await request.body()` instead (buffers full body — acceptable for non-streaming POST) |

**Lowest-risk assumptions:** A1 and A3 are easily verified during Wave 0 by running the app. A2 is a deliberate design choice to document. A4 is the most consequential — if `request.stream()` doesn't work as httpx `content`, fall back to `await request.body()`.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | Container build + compose | Yes | 29.4.0 | None — required for integration tests |
| Python 3.12 | Application | Yes (`.python-version` file exists) | 3.12 | None — project constraint |
| httpx | Proxy client | Yes (in lockfile) | 0.28.1 | None — required |
| structlog | Structured logging | No (NOT in lockfile) | N/A — must add | None — required; add via `uv add structlog` |
| respx | Test mock for httpx | No (NOT in lockfile) | N/A — must add | pytest-mock manual mock (more verbose) |
| PostgreSQL | Admin API / db service | Yes (via Docker Compose) | 16-alpine | None |
| echo container | Gateway integration tests | Yes (Dockerfile exists) | Phase 4 output | None |
| ping container | Gateway integration tests | Yes (Dockerfile exists) | Phase 4 output | None |

**Missing dependencies with no fallback:**
- `structlog` — must be added to `pyproject.toml` before any gateway code is written

**Missing dependencies with fallback:**
- `respx` — `pytest-mock` can mock `httpx.AsyncClient` methods manually, but `respx` is cleaner for HTTP-level mocking

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.26.x |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (exists, `asyncio_mode = "auto"`) |
| Quick run command | `uv run pytest tests/gateway/ -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GTWY-01 | POST to `/servers/echo/mcp` routes to `sb-echo:8000/mcp` | unit (respx mock) | `uv run pytest tests/gateway/test_proxy.py -x -q` | No — Wave 0 |
| GTWY-01 | Invalid server name returns 404 | unit | `uv run pytest tests/gateway/test_proxy.py::test_invalid_server_name_404 -x` | No — Wave 0 |
| GTWY-01 | Unreachable backend returns 503 | unit (respx mock ConnectError) | `uv run pytest tests/gateway/test_proxy.py::test_backend_unavailable_503 -x` | No — Wave 0 |
| GTWY-02 | GET to `/servers/echo/mcp` returns SSE stream (streaming response) | unit | `uv run pytest tests/gateway/test_proxy.py::test_get_sse_stream -x` | No — Wave 0 |
| GTWY-02 | POST to `/servers/echo/mcp` proxies request body | unit | `uv run pytest tests/gateway/test_proxy.py::test_post_proxies_body -x` | No — Wave 0 |
| GTWY-03 | Second request with same `Mcp-Session-Id` routes to same backend URL | unit | `uv run pytest tests/gateway/test_session.py -x -q` | No — Wave 0 |
| GTWY-03 | Request without `Mcp-Session-Id` routes by server name | unit | `uv run pytest tests/gateway/test_session.py::test_no_session_id_routes_by_name -x` | No — Wave 0 |
| SECU-01 | Missing token returns 401 with `WWW-Authenticate: Bearer` | unit | `uv run pytest tests/gateway/test_auth.py::test_missing_token_401 -x` | No — Wave 0 |
| SECU-01 | Invalid token returns 401 | unit | `uv run pytest tests/gateway/test_auth.py::test_invalid_token_401 -x` | No — Wave 0 |
| SECU-01 | Expired token returns 401 | unit | `uv run pytest tests/gateway/test_auth.py::test_expired_token_401 -x` | No — Wave 0 |
| SECU-01 | Valid token with wrong audience returns 401 | unit | `uv run pytest tests/gateway/test_auth.py::test_wrong_audience_401 -x` | No — Wave 0 |
| SECU-01 | `Authorization` header stripped before forwarding | unit | `uv run pytest tests/gateway/test_proxy.py::test_authorization_stripped -x` | No — Wave 0 |
| SECU-02 | TLS termination | manual — handled at Docker/infra layer | N/A — verify in docker-compose.yml healthcheck | N/A |
| OBSV-01 | Each proxied request emits JSON log with required fields | unit (caplog/capsys) | `uv run pytest tests/gateway/test_logging.py -x -q` | No — Wave 0 |
| PLAT-01 | `docker compose up` starts all 5 services with healthchecks passing | integration (manual smoke) | `docker compose up -d && docker compose ps` | N/A |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/gateway/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/gateway/__init__.py` — package marker
- [ ] `tests/gateway/conftest.py` — `make_customer_token` helper, gateway `AsyncClient` fixture with `ASGITransport`, settings override with `CUSTOMER_JWT_SECRET`
- [ ] `tests/gateway/test_auth.py` — covers SECU-01 auth rejection paths
- [ ] `tests/gateway/test_proxy.py` — covers GTWY-01, GTWY-02, SECU-01 (header strip)
- [ ] `tests/gateway/test_session.py` — covers GTWY-03
- [ ] `tests/gateway/test_wellknown.py` — covers RFC 9728 endpoint
- [ ] `tests/gateway/test_logging.py` — covers OBSV-01
- [ ] Add `structlog` to `pyproject.toml` dependencies: `uv add structlog`
- [ ] Add `respx` to dev dependencies: `uv add --dev respx`
- [ ] Add `CUSTOMER_JWT_SECRET` default to `tests/conftest.py` `os.environ.setdefault`

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Yes | PyJWT HS256, `require_customer` dependency, audience validation |
| V3 Session Management | Partial | `Mcp-Session-Id` is a backend-assigned opaque token; gateway stores but does not generate sessions |
| V4 Access Control | Yes | Every route protected by `require_customer`; no unauthenticated routes except `/.well-known/oauth-protected-resource` |
| V5 Input Validation | Yes | Server name pattern validated (`SERVER_NAME_PATTERN`) before any network call |
| V6 Cryptography | N/A | Gateway verifies signatures only — PyJWT, never hand-roll |

### Known Threat Patterns for MCP Proxy Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| JWT replay after expiry | Spoofing | `options={"require": ["exp", "iat"]}` in `jwt.decode()` |
| Customer token leaking to backend | Information Disclosure | Strip `Authorization` header (D-10) — non-negotiable |
| Server name path traversal (`/servers/../etc`) | Tampering | `SERVER_NAME_PATTERN` regex rejects any non-alphanumeric chars including `/` and `.` |
| DNS rebinding against backend containers | Tampering | Backend containers on `switchboard-internal` network with no published ports; gateway is the only ingress |
| Timing oracle on JWT validation | Information Disclosure | Use generic error messages (`"Could not validate credentials"`) — mirror existing pattern |
| Missing `WWW-Authenticate` header | Spoofing | Enforced in `require_customer` via `headers={"WWW-Authenticate": "Bearer"}` on 401 responses |
| Token with wrong audience accepted | Spoofing | `audience="switchboard-gateway"` parameter in `jwt.decode()` |

---

## Project Constraints (from CLAUDE.md)

| Constraint | Source | Impact on Phase 5 |
|------------|--------|-------------------|
| Python 3.12+ | CLAUDE.md + project constraints | Use `from __future__ import annotations`, modern `asyncio.Lock()` semantics |
| `switchboard/` top-level package | CLAUDE.md | Gateway lives at `switchboard/gateway/`, not `src/gateway/` |
| `uv` for package management only | CLAUDE.md | `uv add structlog`, `uv add --dev respx` — no pip |
| `ruff` for linting/formatting | CLAUDE.md | Existing ruff config in `pyproject.toml` applies |
| Type hints on all function signatures | CLAUDE.md | `require_customer`, `proxy_mcp`, `resolve_backend` all need full type annotations |
| `from __future__ import annotations` + `TYPE_CHECKING` | Established project pattern | Required in all new files |
| `lru_cache` on `get_settings()` | Established project pattern | Do not instantiate `Settings` directly in gateway code |
| `{"detail": "..."}` error envelope | Established project pattern | All HTTPException messages use this shape |
| Docker Compose for local dev | CLAUDE.md + project constraints | Gateway must be a compose service with healthcheck |
| `Depends()` for auth and settings injection | Established project pattern | `require_customer` and `get_settings` are FastAPI dependencies |
| TDD: write tests first | CLAUDE.md / testing rules | Wave 0 test files must be created before Wave 1 implementation |
| 80%+ test coverage | CLAUDE.md / testing rules | Critical paths (auth rejection, header strip, 503 routing) require 100% |

---

## Sources

### Primary (HIGH confidence)
- [VERIFIED: modelcontextprotocol.io/specification/2025-03-26/basic/transports] — MCP Streamable HTTP transport: POST/GET semantics, `Mcp-Session-Id` header behavior, SSE stream requirements
- [VERIFIED: rfc-editor.org/rfc/rfc9728] — RFC 9728 §2: required fields, `bearer_methods_supported` field name, minimum compliant document
- [VERIFIED: python-httpx.org/async/] — httpx streaming mode: `send(stream=True)`, `aiter_raw()`, manual streaming mode + `aclose()` requirement
- [VERIFIED: fastapi.tiangolo.com/advanced/events/] — FastAPI lifespan: `@asynccontextmanager`, `app.state` resource storage pattern
- [VERIFIED: uv.lock] — package versions: httpx 0.28.1, httpx-sse 0.4.3, mcp 1.27.0, fastapi 0.135.3, pyjwt 2.12.1, uvicorn 0.44.0
- [VERIFIED: pyproject.toml] — project dependencies; `structlog` and `respx` NOT present; `pytest-asyncio` `asyncio_mode = "auto"` confirmed
- [VERIFIED: switchboard/admin/auth.py] — `require_operator` pattern: exact code to replicate for `require_customer`
- [VERIFIED: switchboard/registry/models.py] — `SERVER_NAME_PATTERN` regex available for import
- [VERIFIED: servers/echo/server.py] — echo server uses `fastmcp.run(transport="streamable-http")` — confirms Streamable HTTP transport is already in use
- [VERIFIED: docker-compose.yml] — `switchboard-internal` network defined; echo and ping services present with healthchecks; db service healthy

### Secondary (MEDIUM confidence)
- [CITED: pypi.org/project/structlog/] — structlog 25.5.0, released Oct 27 2025
- [CITED: pypi.org/project/respx/] — respx 0.23.1, released Apr 8 2026
- [CITED: github.com/fastapi/fastapi/discussions/9599] — proxy pattern: strip `host` header, `StreamingResponse(aiter_raw())` approach (community-verified, aligns with httpx docs)
- [CITED: angelospanag.me/blog/structured-logging-using-structlog-and-fastapi] — structlog `contextvars.bind_contextvars()` per-request binding pattern, processor chain example

### Tertiary (LOW confidence)
- None. All critical claims verified against official sources or codebase inspection.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions verified in uv.lock or pypi.org
- Architecture patterns: HIGH — verified against FastAPI docs, httpx docs, MCP spec, and RFC 9728
- Common pitfalls: HIGH — derived from codebase inspection (existing patterns) + official docs
- RFC 9728 field names: HIGH — verified from rfc-editor.org directly (`bearer_methods_supported`, not `bearer_tokens_supported`)
- Test infrastructure: HIGH — existing test patterns inspected directly

**Research date:** 2026-04-16
**Valid until:** 2026-05-16 (stable libraries; MCP spec may have minor updates)
