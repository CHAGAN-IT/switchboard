---
phase: 05-gateway
reviewed: 2026-04-16T00:00:00Z
depth: standard
files_reviewed: 16
files_reviewed_list:
  - .env.example
  - Dockerfile
  - docker-compose.yml
  - pyproject.toml
  - switchboard/config.py
  - switchboard/gateway/app.py
  - switchboard/gateway/auth.py
  - switchboard/gateway/proxy.py
  - tests/conftest.py
  - tests/gateway/__init__.py
  - tests/gateway/conftest.py
  - tests/gateway/test_auth.py
  - tests/gateway/test_logging.py
  - tests/gateway/test_proxy.py
  - tests/gateway/test_session.py
  - tests/gateway/test_wellknown.py
findings:
  critical: 0
  warning: 4
  info: 4
  total: 8
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-04-16T00:00:00Z
**Depth:** standard
**Files Reviewed:** 16
**Status:** issues_found

## Summary

Reviewed the Phase 5 gateway implementation: `switchboard/gateway/` (app, auth, proxy), shared
configuration, Dockerfile, docker-compose, and the full gateway test suite. The implementation is
well-structured overall — JWT validation is correct and strict, SSRF mitigation via
`SERVER_NAME_PATTERN` is in place, the `Authorization` and `host` header stripping is verified by
tests, session affinity is lock-protected, and structured logging is wired correctly.

Four warnings and four info items were found. No critical (security-breaking) issues were
identified. The most impactful warning is the unbounded `_session_map` that grows without eviction,
which is a reliability/DoS risk in production. The second-most impactful is incomplete error
handling in the proxy: only `httpx.ConnectError` is caught, leaving other transport failures as
unhandled 500s. The remaining findings are a missing type annotation, a Docker image pinning issue,
an unused dev dependency, and minor quality items.

## Warnings

### WR-01: Unbounded session map grows indefinitely — DoS and memory exhaustion risk

**File:** `switchboard/gateway/proxy.py:30`
**Issue:** `_session_map: dict[str, str] = {}` is a module-level dictionary that is written to
every time a request arrives with a previously unseen `Mcp-Session-Id`. There is no eviction,
expiry, or maximum-size guard. In production, clients (or an attacker) can generate unlimited
unique session IDs, causing the gateway process to consume unbounded memory until it is killed by
the OS or OOM killer. This is a correctness/reliability issue, not a pure performance concern —
the process will eventually crash under sustained load.

**Fix:** Apply a maximum-size cap using `collections.OrderedDict` with LRU eviction, or use a
bounded TTL structure. A minimal safe pattern:

```python
import time
from collections import OrderedDict

_SESSION_MAP_MAX = 100_000
_SESSION_TTL_SECONDS = 3600

# (session_id) -> (backend_url, inserted_at)
_session_map: OrderedDict[str, tuple[str, float]] = OrderedDict()
_session_lock = asyncio.Lock()

async def resolve_backend(server_name: str, session_id: str | None) -> str:
    if session_id is None:
        return f"http://sb-{server_name}:8000"
    async with _session_lock:
        now = time.monotonic()
        if session_id in _session_map:
            url, _ = _session_map[session_id]
            # Refresh insertion order for LRU
            _session_map.move_to_end(session_id)
            return url
        target = f"http://sb-{server_name}:8000"
        _session_map[session_id] = (target, now)
        # Evict oldest entry if over cap
        if len(_session_map) > _SESSION_MAP_MAX:
            _session_map.popitem(last=False)
        return target
```

---

### WR-02: Only `httpx.ConnectError` caught — other transport errors surface as 500

**File:** `switchboard/gateway/proxy.py:131-137`
**Issue:** The `try/except` block around `http_client.send(rp_req, stream=True)` only handles
`httpx.ConnectError`. Other common transport failures — `httpx.TimeoutException` (backend took
too long to respond), `httpx.ReadError` (connection dropped mid-response), and
`httpx.RemoteProtocolError` (malformed HTTP from backend) — are not caught and will propagate as
unhandled exceptions, resulting in a 500 Internal Server Error to the customer with no
`WWW-Authenticate` header and potentially exposing internal stack detail through FastAPI's default
error handler.

**Fix:** Broaden the except clause to cover all `httpx.TransportError` subclasses, which is the
base class for all network-layer failures:

```python
try:
    rp_resp = await http_client.send(rp_req, stream=True)
except httpx.TransportError as exc:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Server '{server_name}' is unavailable",
    ) from None
```

`httpx.ConnectError` is a subclass of `httpx.TransportError`, so this is a strict superset of the
current behavior with no regression risk.

---

### WR-03: Missing type annotations on `RequestLogMiddleware.dispatch`

**File:** `switchboard/gateway/app.py:52`
**Issue:** The `dispatch` method signature is missing type annotations on `call_next` and on the
return type. The project CLAUDE.md requires type hints on all function signatures. With strict
mypy, this would produce `error: Function is missing a type annotation for one or more arguments`.

```python
# Current (line 52):
async def dispatch(self, request: Request, call_next):
```

**Fix:**

```python
from collections.abc import Awaitable, Callable
from starlette.responses import Response

async def dispatch(
    self,
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
```

The `Callable[[Request], Awaitable[Response]]` signature matches Starlette's `BaseHTTPMiddleware`
contract. Move the import to the `TYPE_CHECKING` block if linters complain about the runtime cost.

---

### WR-04: `uv:latest` tag in Dockerfile — reproducibility risk

**File:** `Dockerfile:12`
**Issue:** The base `uv` binary is copied from `ghcr.io/astral-sh/uv:latest`. Using `latest`
means any breaking change in a future `uv` release (e.g., changed CLI flags, removed
`--no-install-project`, altered lock-file behavior) will silently affect the build without any
change to the Dockerfile. This is a reliability issue — CI builds on the same commit can produce
different results over time.

**Fix:** Pin to the exact `uv` version currently used in the project (check with `uv --version`
in the dev environment) and update it deliberately:

```dockerfile
# Pin to specific version; update deliberately
COPY --from=ghcr.io/astral-sh/uv:0.6.12 /uv /uvx /bin/
```

---

## Info

### IN-01: `psycopg2-binary` in dev dependencies is unused

**File:** `pyproject.toml:25`
**Issue:** `psycopg2-binary>=2.9.0` is listed in the `dev` dependency group, but it is never
imported anywhere in the codebase. The stack documentation explicitly calls out `psycopg2` as
"NEVER use — blocks the event loop; use asyncpg instead." Alembic migrations use
`async_engine_from_config` with the `asyncpg` driver. The presence of `psycopg2-binary` adds
unnecessary installation weight and creates confusion about which driver is authoritative.

**Fix:** Remove the entry from `pyproject.toml` and run `uv lock` to regenerate the lockfile:

```toml
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.26.0",
    "ruff>=0.11.0",
    # psycopg2-binary removed — asyncpg used everywhere
    "httpx>=0.28.1",
    "mcp>=1.27.0",
    "respx>=0.22.0",
]
```

---

### IN-02: `structlog.configure()` called at module import time as a side effect

**File:** `switchboard/gateway/app.py:26-36`
**Issue:** `structlog.configure(...)` is called unconditionally at module import level. Any module
that imports `from switchboard.gateway.app import app` (including test files) will reconfigure the
global structlog. This makes the structlog configuration order-dependent: if another module
configures structlog first, this call will silently override it. The `test_logging.py` tests work
around this using `structlog.testing.capture_logs`, but the side-effect import pattern is
fragile.

**Fix:** Move `structlog.configure()` into the `lifespan` function or into a dedicated
`configure_logging()` function called explicitly from `lifespan`:

```python
def _configure_logging() -> None:
    """Configure structlog once at application startup."""
    structlog.configure(
        processors=[...],
        ...
    )

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _configure_logging()
    settings = get_settings()
    ...
```

---

### IN-03: Forward proxy leaks all backend response headers to clients verbatim

**File:** `switchboard/gateway/proxy.py:149`
**Issue:** `headers=dict(rp_resp.headers)` passes all backend response headers — including any
`X-Internal-*`, `Server`, `X-Powered-By`, `Set-Cookie`, or debug headers that backend containers
might emit — directly to the customer. While the backends are trusted internal services, this
creates an information disclosure channel if a backend is ever misconfigured. There is no test
verifying which response headers are forwarded or filtered.

**Fix:** Consider an explicit allowlist of response headers to forward, or at minimum strip
`server`, `x-powered-by`, and any internal headers. For a streaming proxy, a pragmatic approach
is to strip known-sensitive headers while forwarding the rest:

```python
_STRIP_RESPONSE_HEADERS = frozenset({"server", "x-powered-by", "x-internal-trace"})

headers = {
    k: v
    for k, v in rp_resp.headers.items()
    if k.lower() not in _STRIP_RESPONSE_HEADERS
}
```

---

### IN-04: Test session affinity tests mutate shared module-level state without cleanup guarantee

**File:** `tests/gateway/test_session.py:13,31,55`
**Issue:** All three session affinity tests call `_session_map.clear()` to reset state before the
test, but they rely on previous tests having left the map in an unknown state. If a test raises
before the `clear()` call in the next test, the state carries over. Additionally, direct access to
`_session_map` from tests couples the test suite tightly to an implementation detail.

**Fix:** Use a pytest fixture with `autouse=False` that clears the map before and after each
session test:

```python
# In conftest.py or test_session.py
import pytest
from switchboard.gateway.proxy import _session_map

@pytest.fixture(autouse=True)
def clear_session_map():
    _session_map.clear()
    yield
    _session_map.clear()
```

This guarantees cleanup even if the test fails or raises mid-execution.

---

_Reviewed: 2026-04-16T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
