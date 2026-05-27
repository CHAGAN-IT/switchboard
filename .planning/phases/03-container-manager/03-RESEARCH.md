# Phase 3: Container Manager - Research

**Researched:** 2026-04-15
**Domain:** Docker container lifecycle management via Python SDK, async wrapping
**Confidence:** HIGH

## Summary

Phase 3 adds container lifecycle operations (start, stop, restart) to the Admin API. The core technical challenge is wrapping the synchronous Docker Python SDK (7.1.0) for safe use inside an async FastAPI application. The Docker SDK's `DockerClient` is explicitly **not thread-safe** (confirmed by maintainers in GitHub issue #3229), which validates the CONTEXT.md decision D-10: instantiate a fresh client inside each `asyncio.to_thread()` call rather than sharing one across the async app.

The Docker SDK provides `containers.run()` for creating and starting containers, `container.stop()` and `container.restart()` for lifecycle management, and the `network` parameter on `run()` for attaching containers to a named Docker network at creation time. Containers started with `detach=True` return a `Container` object immediately but may exit silently if the image has no long-running process -- the implementation must call `container.reload()` after creation and verify `container.status == "running"` before declaring success.

**Primary recommendation:** Build a `ContainerManager` class with three public async methods (`start`, `stop`, `restart`) that each create a short-lived `DockerClient` inside `asyncio.to_thread()`, perform the Docker operation, close the client, and then update the server registry via `ServerRepository.update_status()` and `update_container_id()`. Mock the Docker SDK entirely in unit tests; defer integration tests that require real Docker to a separate marker.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** A named internal Docker network (`switchboard-internal`) is pre-declared in `docker-compose.yml`. `ContainerManager` attaches every MCP server container to this network via the Docker SDK. No host ports are published -- containers are reachable only via the internal network. This is the network the gateway (Phase 5) will also join.
- **D-02:** Container naming uses the `sb-` prefix: a server named `echo` runs as container `sb-echo`. The gateway (Phase 5) routes to `http://sb-{name}:8000/mcp` using this convention. The prefix avoids collisions with other containers on the shared Docker network.
- **D-03:** MCP server containers listen on port **8000** internally (the FastAPI/uvicorn default). This is a constant defined in the container manager module -- not a per-server configuration in Phase 3.
- **D-04:** Container start failure (bad image, OOM, Docker daemon error) -> `ContainerManager` catches the Docker SDK exception, calls `update_status(session, server_id, ServerStatus.error)`, and the API endpoint returns **HTTP 500** with a `{"detail": "<reason>"}` body. Operator can inspect via `GET /servers/{name}`.
- **D-05:** `POST /servers/{name}/stop` when server is already stopped -> **409 Conflict** with `{"detail": "Server 'X' is not running"}`. Consistent with the existing 409 for duplicate registration (Phase 2, D-03).
- **D-06:** `POST /servers/{name}/start` when server is already running -> **409 Conflict** with `{"detail": "Server 'X' is already running"}`. Prevents duplicate container creation.
- **D-07:** All three lifecycle endpoints return **404** if the server name is not found in the registry (same pattern as `GET /servers/{name}` in Phase 2).
- **D-08:** `POST /servers/{name}/start`, `/stop`, and `/restart` all return the full **`ServerRead`** schema on success (HTTP 200). Consistent with Phase 2 endpoints -- callers always receive the current state without a follow-up GET. The returned `ServerRead` reflects the updated `status` and `container_id`.
- **D-09:** A `ContainerManager` class lives in `switchboard/container/manager.py` with async-safe methods: `start(session, server)`, `stop(session, server)`, `restart(session, server)`. Mirrors the `ServerRepository` pattern -- injected as `Depends(get_container_manager)` in API endpoints, reusable by Phase 5 (gateway) and Phase 6 (health monitor) via the same `Depends()` mechanism.
- **D-10:** The Docker client (`docker.from_env()`) is instantiated **inside each `asyncio.to_thread()` call** -- not shared across calls. Thread-safe by construction; avoids event loop blocking during client initialization. Each thread creates and closes its own connection.

### Claude's Discretion
- Exact exception type hierarchy for `ContainerManager` errors (e.g., `ContainerStartError`, `ContainerStopError`)
- Whether `restart()` uses Docker's `container.restart()` or a sequential `stop() + start()` approach
- Internal port constant name (`CONTAINER_PORT = 8000`) and location
- `get_container_manager()` factory function structure in `switchboard/container/__init__.py`
- Whether to add a `network_name` setting to `Settings` (in `config.py`) or hard-code `switchboard-internal` as a constant

### Deferred Ideas (OUT OF SCOPE)
- Per-server port configuration (all containers use port 8000 in Phase 3 -- configurable port is a v2 concern)
- Container environment variable injection (CONT-05) -- v2 requirement per REQUIREMENTS.md
- Restart policy (automatic restart on crash) -- Phase 6 (Health Monitor) or v2
- Rolling restart without downtime -- explicitly out of scope per REQUIREMENTS.md
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CONT-01 | Operator can start a registered server container via Admin API | Docker SDK `containers.run(image, detach=True, name=..., network=...)` creates and starts the container; `update_status()` + `update_container_id()` update the registry; new POST endpoint at `/api/v1/servers/{name}/start` |
| CONT-02 | Operator can stop a running server container via Admin API | Docker SDK `containers.get(container_id).stop()` stops the container, then `container.remove()` cleans up; registry updated to `stopped` with `container_id=None`; new POST endpoint at `/api/v1/servers/{name}/stop` |
| CONT-03 | Operator can restart a running server container via Admin API | Sequential `stop()` + `start()` or Docker's `container.restart()` with registry updates; new POST endpoint at `/api/v1/servers/{name}/restart` |
</phase_requirements>

## Standard Stack

### Core (Phase 3 additions)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| docker (Python SDK) | 7.1.0 | Docker Engine API client | Official Python SDK for Docker; provides `DockerClient`, `containers.run()`, `container.stop()`, `container.restart()` -- the only maintained Python Docker library [VERIFIED: pypi.org/project/docker, confirmed 7.1.0 latest as of 2026-04-15] |

### Already Installed (from Phases 1-2)

| Library | Version | Purpose | Phase 3 Usage |
|---------|---------|---------|---------------|
| FastAPI | 0.135.3 | Admin REST API | Three new POST endpoints on existing router |
| SQLAlchemy | 2.0.49 | ORM (async) | `ServerRepository` for status/container_id updates |
| Pydantic | 2.13.0 | Data validation | `ServerRead` schema for response serialization |
| PyJWT | 2.12.1 | JWT auth | Existing `require_operator` dependency protects new endpoints |
| pytest | 8.x | Testing | Test container manager with mocked Docker SDK |
| pytest-asyncio | 0.26.x | Async test support | Async endpoint and manager tests |
| httpx | 0.28.1 | Test HTTP client | `AsyncClient` for endpoint integration tests |

### New Dev Dependency

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest-mock | 0.21.0+ | `mocker` fixture for pytest | Cleaner mocking of Docker SDK calls in unit tests; provides `mocker.patch()` as a fixture instead of `@patch` decorators [ASSUMED -- version needs verification] |

**Installation:**
```bash
# Add docker SDK as a production dependency (used by ContainerManager)
uv add docker

# Add pytest-mock as a dev dependency
uv add --dev pytest-mock
```

**Note:** The `docker` package is currently listed as a dev dependency in `pyproject.toml` (`uv add --dev docker`). For Phase 3, it must be promoted to a **production dependency** because `ContainerManager` runs in the application, not just in tests. [VERIFIED: current pyproject.toml lists docker only in dev deps]

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| docker (sync SDK) + asyncio.to_thread() | aiodocker (async-native Docker client) | aiodocker is async-native but less mature, smaller community, fewer features; docker-py is the official SDK maintained by Docker Inc.; `asyncio.to_thread()` overhead is negligible for the frequency of container lifecycle calls |
| unittest.mock.patch | pytest-mock (mocker fixture) | pytest-mock is a thin wrapper but provides cleaner fixture-based mocking; either works; pytest-mock is optional |

## Architecture Patterns

### Recommended Project Structure (Phase 3 additions)

```
switchboard/
├── container/
│   ├── __init__.py          # get_container_manager() factory
│   ├── manager.py           # ContainerManager class
│   └── exceptions.py        # ContainerError hierarchy
├── admin/
│   ├── router.py            # ADD: 3 new lifecycle endpoints
│   └── ...                  # (existing files unchanged)
├── registry/
│   └── ...                  # (existing files unchanged)
└── config.py                # OPTIONAL: add DOCKER_NETWORK setting

tests/
├── container/
│   ├── __init__.py
│   ├── test_manager.py      # Unit tests (mocked Docker SDK)
│   └── conftest.py          # Container test fixtures
├── admin/
│   ├── test_endpoints.py    # ADD: lifecycle endpoint tests
│   └── conftest.py          # ADD: get_container_manager override
└── ...
```

### Pattern 1: asyncio.to_thread() wrapping for sync Docker SDK

**What:** Every Docker SDK call is wrapped in `asyncio.to_thread()` with a fresh `DockerClient` per call, keeping the async event loop unblocked.

**When to use:** Any interaction with the Docker Engine from async code.

**Example:**
```python
# Source: docker-py.readthedocs.io/en/stable/ + Python asyncio docs
import asyncio
import docker
from docker.errors import APIError, ImageNotFound, NotFound

async def _run_container(
    image: str,
    name: str,
    network: str,
) -> str:
    """Start a container in a background thread. Returns container ID."""
    def _blocking() -> str:
        with docker.from_env() as client:
            container = client.containers.run(
                image=image,
                name=name,
                detach=True,
                network=network,
                # No ports= argument -- no host port publishing (D-01)
            )
            # Verify the container actually started
            container.reload()
            if container.status != "running":
                raise RuntimeError(
                    f"Container {name} exited immediately "
                    f"(status: {container.status})"
                )
            return container.id

    return await asyncio.to_thread(_blocking)
```

### Pattern 2: ContainerManager service class with Depends() injection

**What:** A stateless service class injected via FastAPI `Depends()`, mirroring the `ServerRepository` pattern.

**When to use:** Container lifecycle operations from API endpoints.

**Example:**
```python
# Source: Existing switchboard/admin/router.py pattern
from switchboard.container import get_container_manager
from switchboard.container.manager import ContainerManager

# In router.py endpoints:
async def start_server(
    name: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    repo: Annotated[ServerRepository, Depends(get_repository)],
    cm: Annotated[ContainerManager, Depends(get_container_manager)],
) -> ServerRead:
    server = await repo.get_by_name(session, name)
    if server is None:
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found")
    if server.status == ServerStatus.running:
        raise HTTPException(status_code=409, detail=f"Server '{name}' is already running")
    server = await cm.start(session, server)
    await session.commit()
    return ServerRead.model_validate(server)
```

### Pattern 3: Exception hierarchy mirroring registry pattern

**What:** A `ContainerError` base exception with specific subclasses, matching the existing `RegistryError` hierarchy in `switchboard/registry/exceptions.py`.

**When to use:** All error conditions from container operations.

**Example:**
```python
# Source: switchboard/registry/exceptions.py pattern
class ContainerError(Exception):
    """Base exception for container lifecycle operations."""

class ContainerStartError(ContainerError):
    """Container failed to start (bad image, OOM, daemon error)."""
    def __init__(self, server_name: str, reason: str) -> None:
        super().__init__(f"Failed to start container for '{server_name}': {reason}")
        self.server_name = server_name
        self.reason = reason

class ContainerStopError(ContainerError):
    """Container failed to stop."""
    def __init__(self, server_name: str, reason: str) -> None:
        super().__init__(f"Failed to stop container for '{server_name}': {reason}")
        self.server_name = server_name
        self.reason = reason

class ContainerNotRunningError(ContainerError):
    """Attempted to stop a container that is not running."""
    def __init__(self, server_name: str) -> None:
        super().__init__(f"Server '{server_name}' is not running")
        self.server_name = server_name
```

### Pattern 4: Docker client cleanup with context manager

**What:** Use `docker.from_env()` as a context manager (`with` statement) to ensure `close()` is always called, preventing socket leaks.

**When to use:** Every Docker SDK interaction.

**Example:**
```python
# Source: github.com/docker/docker-py/issues/2808 (context manager added in PR #2815)
def _blocking_stop(container_id: str) -> None:
    with docker.from_env() as client:
        try:
            container = client.containers.get(container_id)
            container.stop(timeout=10)
            container.remove()
        except docker.errors.NotFound:
            pass  # Container already gone -- no-op
```

### Anti-Patterns to Avoid

- **Shared DockerClient across async calls:** The `DockerClient` is NOT thread-safe (confirmed by maintainers). Creating one at module level and reusing it from `asyncio.to_thread()` calls will cause race conditions. [VERIFIED: github.com/docker/docker-py/issues/3229]
- **Blocking Docker calls in async handlers:** Calling `docker.from_env()` or `container.stop()` directly in an `async def` endpoint blocks the event loop. All Docker SDK calls must go through `asyncio.to_thread()`. [VERIFIED: Python asyncio docs]
- **Not calling container.reload() after run(detach=True):** The returned Container object has cached attributes. Without `reload()`, `container.status` may not reflect reality. A container with a bad CMD exits immediately but `containers.run()` does not raise when `detach=True`. [VERIFIED: docker-py docs]
- **Publishing host ports on MCP server containers:** CONTEXT decision D-01 explicitly forbids host-published ports. Never pass `ports=` to `containers.run()`.
- **Catching bare Exception in Docker operations:** The Docker SDK raises specific exceptions (`ImageNotFound`, `APIError`, `NotFound`). Catch these specifically to provide meaningful error messages.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Docker API communication | Raw HTTP calls to Docker socket | `docker` Python SDK 7.1.0 | Docker API versioning, TLS, auth, response parsing are complex; the SDK handles all of it |
| Sync-to-async wrapping | Custom thread pool executor | `asyncio.to_thread()` (stdlib) | Built into Python 3.9+; handles thread spawning and context propagation correctly |
| Container naming | Manual string concatenation | Constant prefix + f-string (`f"sb-{name}"`) | Centralize in one place to avoid inconsistency with Phase 5 gateway routing |
| Docker client cleanup | Manual try/finally with `close()` | `with docker.from_env() as client:` | Context manager is cleaner and exception-safe; supported since docker-py PR #2815 |

**Key insight:** The Docker SDK handles all the complexity of communicating with the Docker daemon over Unix sockets (or TCP). Hand-rolling HTTP calls to `/var/run/docker.sock` would be error-prone and provide no benefit.

## Common Pitfalls

### Pitfall 1: Container exits immediately after run(detach=True)
**What goes wrong:** `containers.run(image, detach=True)` returns a `Container` object even if the container process exits immediately (bad entrypoint, missing CMD, crash on startup). The registry gets updated to `running` but the container is actually dead.
**Why it happens:** With `detach=True`, Docker starts the container and returns immediately. No exception is raised for exit after start.
**How to avoid:** After `containers.run()`, call `container.reload()` and check `container.status == "running"`. If not running, raise `ContainerStartError` and set registry status to `error`.
**Warning signs:** Tests pass with mock but real Docker shows container in `exited` state.

### Pitfall 2: Stale container_id in registry after external stop
**What goes wrong:** Someone runs `docker stop sb-echo` manually (outside the API). The registry still shows `status=running` and `container_id=<old_id>`. Next `POST /stop` tries to stop a container that no longer exists.
**Why it happens:** Phase 3 has no health monitor (that is Phase 6). The registry is only updated by API calls.
**How to avoid:** In `stop()`, catch `docker.errors.NotFound` when getting the container by ID. If the container is already gone, still update the registry to `stopped` and `container_id=None`. Log a warning but don't fail the stop operation.
**Warning signs:** 500 errors on stop when containers were killed externally.

### Pitfall 3: Docker network does not exist at container start time
**What goes wrong:** `containers.run(network="switchboard-internal")` fails with `docker.errors.NotFound` if the network hasn't been created yet (e.g., first run without `docker compose up`).
**Why it happens:** The `switchboard-internal` network is declared in `docker-compose.yml` but only created when `docker compose up` runs. If the admin API runs standalone (outside compose), the network doesn't exist.
**How to avoid:** In the `start()` method, create the network if it doesn't exist using `client.networks.create("switchboard-internal", driver="bridge")`. Wrap in try/except to handle race conditions. Or: document that `docker compose up` is a prerequisite.
**Warning signs:** `NotFound` errors when starting containers outside Docker Compose.

### Pitfall 4: Orphaned containers after failed stop
**What goes wrong:** `container.stop()` succeeds but `container.remove()` fails (e.g., volume in use). The container is stopped but not removed. Next `start()` call fails because container name `sb-echo` is already taken.
**Why it happens:** Docker container names are unique. A stopped-but-not-removed container still holds the name.
**How to avoid:** In `start()`, check for existing container with the same name first. If found and stopped, remove it. Use `force=True` on `container.remove()` as a safety net. In `stop()`, always call `remove(force=True)` after `stop()`.
**Warning signs:** `409 Conflict` from Docker daemon ("container name already in use").

### Pitfall 5: asyncio.to_thread() context variable propagation
**What goes wrong:** If the application uses `contextvars` (e.g., for request ID tracking), those are NOT automatically propagated to the thread spawned by `asyncio.to_thread()`.
**Why it happens:** `asyncio.to_thread()` copies the current context by default in Python 3.12+, but third-party middleware may use thread-local storage instead of contextvars.
**How to avoid:** For Phase 3 this is unlikely to be an issue since Docker calls don't need request context. But be aware for Phase 5 when logging/tracing might be involved.
**Warning signs:** Missing trace IDs in logs from Docker operations.

### Pitfall 6: Test fixture interference from dependency_overrides
**What goes wrong:** Tests that override `get_container_manager` via `app.dependency_overrides` conflict with other tests that don't override it, causing the real Docker SDK to be called in test.
**Why it happens:** `app.dependency_overrides` is global state. If not cleared after each test, overrides leak.
**How to avoid:** Follow the existing pattern in `tests/admin/conftest.py`: clear overrides in the fixture teardown (`app.dependency_overrides.clear()`). Add the `get_container_manager` override alongside existing `get_session` and `get_settings` overrides.
**Warning signs:** Tests that pass in isolation but fail when run together.

## Code Examples

### Docker SDK: Create and start a container on a named network
```python
# Source: docker-py.readthedocs.io/en/stable/containers.html
import docker

with docker.from_env() as client:
    container = client.containers.run(
        image="switchboard/echo:latest",
        name="sb-echo",
        detach=True,
        network="switchboard-internal",
        # hostname="sb-echo",  # optional: sets container hostname
        # No ports= -- containers only accessible on internal network
    )
    container.reload()
    print(f"Container ID: {container.id}")
    print(f"Status: {container.status}")  # "running" or "exited"
```

### Docker SDK: Stop and remove a container
```python
# Source: docker-py.readthedocs.io/en/stable/containers.html
import docker

with docker.from_env() as client:
    try:
        container = client.containers.get("sb-echo")
        container.stop(timeout=10)  # SIGTERM, then SIGKILL after 10s
        container.remove()
    except docker.errors.NotFound:
        pass  # Container already gone
```

### Docker SDK: Exception types for error handling
```python
# Source: docker-py.readthedocs.io/en/stable/containers.html
import docker.errors

# docker.errors.ImageNotFound  -- image does not exist locally or in registry
# docker.errors.APIError       -- general Docker API error (daemon error, OOM, etc.)
# docker.errors.NotFound       -- container/network/volume not found
# docker.errors.ContainerError -- container ran and exited with non-zero code (only when detach=False)
```

### Docker SDK: Create network if not exists
```python
# Source: docker-py.readthedocs.io/en/stable/networks.html
import docker

with docker.from_env() as client:
    try:
        network = client.networks.get("switchboard-internal")
    except docker.errors.NotFound:
        network = client.networks.create(
            "switchboard-internal",
            driver="bridge",
        )
```

### Mocking Docker SDK in tests
```python
# Source: project pattern (tests/admin/conftest.py) + unittest.mock
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from switchboard.container.manager import ContainerManager


@pytest.fixture
def mock_container_manager():
    """ContainerManager with mocked Docker SDK calls."""
    manager = ContainerManager()
    # The actual Docker calls happen inside asyncio.to_thread(),
    # so we mock at the ContainerManager method level for endpoint tests
    return manager


# For unit-testing ContainerManager itself, mock docker.from_env():
@patch("switchboard.container.manager.docker.from_env")
def test_start_container(mock_from_env):
    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_container.id = "abc123def456"
    mock_container.status = "running"
    mock_client.containers.run.return_value = mock_container
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_from_env.return_value = mock_client

    # Now call the synchronous _blocking function directly
    # (test the inner function, not the async wrapper)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `docker-py` package name | `docker` package name | 2017 (v2.0+) | Import `import docker`, not `import docker_py` |
| Shared DockerClient instance | Per-thread client creation | Always (confirmed 2025 via issue #3229) | Must create new client in each `asyncio.to_thread()` call |
| Manual `close()` on DockerClient | Context manager `with docker.from_env() as client:` | 2021 (PR #2815) | Safer resource cleanup |
| SSE transport for MCP servers | Streamable HTTP transport | 2025 (MCP spec update) | MCP containers use `/mcp` endpoint, port 8000 |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `pytest-mock` version 0.21.0+ is current and compatible | Standard Stack | LOW -- `unittest.mock` (stdlib) is the fallback; `pytest-mock` is a convenience, not a requirement |
| A2 | `docker.from_env()` supports context manager in 7.1.0 | Architecture Patterns | LOW -- if not, use `contextlib.closing()` wrapper or manual try/finally with `client.close()` |
| A3 | `container.reload()` correctly refreshes `status` attribute after `run(detach=True)` | Pitfalls | MEDIUM -- if `reload()` is unreliable, need a short sleep + retry pattern to check status |
| A4 | Creating network with `client.networks.create()` is idempotent when caught with try/except | Pitfalls | LOW -- the try/except pattern handles the `APIError` if network already exists |

## Open Questions

1. **restart() implementation strategy**
   - What we know: Docker SDK provides `container.restart()` which stops then starts the same container. Alternatively, we can do `stop()` + `start()` (destroy old container, create new one).
   - What's unclear: Which approach is better for MCP servers? `container.restart()` preserves the container (same ID, same filesystem). `stop()` + `start()` creates a fresh container (new ID, clean filesystem).
   - Recommendation: Use `stop()` + `start()` (sequential) because: (a) MCP servers should be stateless, (b) fresh container avoids stale filesystem state, (c) matches the mental model of "restart = stop then start", (d) the registry `container_id` gets updated to the new ID. Docker's `restart()` keeps the old container ID which could confuse operators.

2. **Network creation responsibility**
   - What we know: CONTEXT D-01 says the network is "pre-declared in docker-compose.yml". Docker Compose creates networks automatically on `docker compose up`.
   - What's unclear: Should `ContainerManager.start()` create the network if it doesn't exist, or should it fail and tell the operator to run `docker compose up`?
   - Recommendation: Defensively create the network if missing. This costs one extra Docker API call (to check) but prevents confusing errors when running the admin API outside Docker Compose. The network creation is idempotent.

3. **Container removal on stop**
   - What we know: Docker keeps stopped containers around (visible via `docker ps -a`). Container names are unique -- a stopped `sb-echo` blocks creating a new `sb-echo`.
   - What's unclear: Should `stop()` also remove the container, or leave it for debugging?
   - Recommendation: Remove the container after stop. Leftover stopped containers cause name conflicts on next `start()` and provide minimal debugging value (logs are accessible via Docker even after removal in recent versions).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker daemon | ContainerManager (all operations) | Yes | 29.4.0 | None -- Docker is required |
| Docker CLI | Developer workflow / compose | Yes | 29.4.0 | -- |
| PostgreSQL | Server registry (existing) | Yes (container) | 16-alpine | -- |
| docker Python SDK | ContainerManager | Not installed yet | 7.1.0 (to install) | -- |
| `switchboard-internal` network | Container networking | Not created yet | -- | ContainerManager creates if missing |

**Missing dependencies with no fallback:**
- `docker` Python SDK must be added to production dependencies (`uv add docker`)

**Missing dependencies with fallback:**
- `switchboard-internal` Docker network: created by `docker compose up` or defensively by `ContainerManager.start()`

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.26.x |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/container/ -x -q` |
| Full suite command | `uv run pytest -x -q` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CONT-01 | POST /servers/{name}/start creates Docker container, updates status to running | unit + integration | `uv run pytest tests/container/test_manager.py tests/admin/test_endpoints.py -k "start" -x` | Wave 0 |
| CONT-02 | POST /servers/{name}/stop stops Docker container, updates status to stopped | unit + integration | `uv run pytest tests/container/test_manager.py tests/admin/test_endpoints.py -k "stop" -x` | Wave 0 |
| CONT-03 | POST /servers/{name}/restart stops and relaunches container | unit + integration | `uv run pytest tests/container/test_manager.py tests/admin/test_endpoints.py -k "restart" -x` | Wave 0 |
| SC-4 | All Docker SDK calls inside asyncio.to_thread() | unit | `uv run pytest tests/container/test_manager.py -k "to_thread" -x` | Wave 0 |
| SC-5 | No host-published ports on MCP containers | unit | `uv run pytest tests/container/test_manager.py -k "no_host_port" -x` | Wave 0 |
| D-04 | Start failure sets status to error, returns 500 | unit + integration | `uv run pytest tests/container/test_manager.py tests/admin/test_endpoints.py -k "start_failure" -x` | Wave 0 |
| D-05 | Stop already-stopped returns 409 | integration | `uv run pytest tests/admin/test_endpoints.py -k "stop_already_stopped" -x` | Wave 0 |
| D-06 | Start already-running returns 409 | integration | `uv run pytest tests/admin/test_endpoints.py -k "start_already_running" -x` | Wave 0 |
| D-07 | Lifecycle endpoints return 404 for unknown server | integration | `uv run pytest tests/admin/test_endpoints.py -k "not_found" -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/container/ tests/admin/ -x -q`
- **Per wave merge:** `uv run pytest -x -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/container/__init__.py` -- new test package
- [ ] `tests/container/conftest.py` -- shared fixtures for ContainerManager mocking
- [ ] `tests/container/test_manager.py` -- unit tests for ContainerManager methods
- [ ] Update `tests/admin/conftest.py` -- add `get_container_manager` override to existing client fixture
- [ ] Update `tests/admin/test_endpoints.py` -- add lifecycle endpoint tests (or create `test_lifecycle_endpoints.py`)
- [ ] `uv add docker` -- production dependency (currently dev-only or not installed)
- [ ] `uv add --dev pytest-mock` -- optional but recommended for cleaner mocking

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Yes (inherited) | Existing `require_operator` JWT dependency protects all new endpoints |
| V3 Session Management | No | No session state in Phase 3 |
| V4 Access Control | Yes | All lifecycle endpoints behind operator JWT; no customer access |
| V5 Input Validation | Yes | Server `name` path parameter validated via existing model-level regex; no additional user input (start/stop/restart are parameterless actions) |
| V6 Cryptography | No | No crypto operations in Phase 3 |

### Known Threat Patterns for Docker Container Management

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Container escape via privileged mode | Elevation of Privilege | Never set `privileged=True`; never add capabilities beyond defaults; document in SECURITY.md |
| Host port exposure leaking internal services | Information Disclosure | D-01: No `ports=` parameter on `containers.run()`; containers only on internal network |
| Arbitrary image execution | Tampering / Elevation | Container image comes from registered `container_image` field (operator-controlled via authenticated API); no user-supplied image names at runtime |
| Docker socket access = root equivalent | Elevation of Privilege | The admin API process needs Docker socket access; in production (Phase 7), ECS replaces Docker SDK entirely; for local dev, document this trust boundary |
| Denial of service via many container starts | Denial of Service | Rate limiting deferred to v2 (SECU-04); for now, operator JWT limits access to trusted operators |
| Container name collision | Tampering | `sb-` prefix + unique server name prevents collisions; `start()` checks for existing container before creating |

## Project Constraints (from CLAUDE.md)

Directives extracted from CLAUDE.md and global rules that constrain Phase 3 implementation:

- **Python 3.12+** -- all code must use 3.12+ features; `asyncio.to_thread()` is available (added in 3.9)
- **Top-level package is `switchboard/`** -- new code goes in `switchboard/container/`
- **`uv` for package management** -- `uv add docker`, not `pip install docker`
- **`ruff` for linting/formatting** -- run before commit
- **`from __future__ import annotations`** + `TYPE_CHECKING` block -- required in all new files
- **Type hints on all function signatures** -- required per global CLAUDE.md
- **Google-style docstrings** -- required on all public modules, classes, methods
- **Paths: `pathlib.Path`** over `os.path` -- though not directly relevant for Phase 3
- **Custom exception hierarchies per module** -- `ContainerError` base in `switchboard/container/exceptions.py`
- **Never catch bare `Exception`** -- catch specific Docker SDK exceptions
- **Functions max ~50 lines** -- decompose if longer
- **Repository pattern** -- `ContainerManager` follows the same `Depends()` injection pattern as `ServerRepository`
- **Tests required for every change** -- pytest with `pytest-asyncio`
- **Mock external services** -- Docker SDK must be mocked in unit tests

## Sources

### Primary (HIGH confidence)
- [Docker SDK for Python 7.1.0 - Containers API](https://docker-py.readthedocs.io/en/stable/containers.html) -- `containers.run()`, `container.stop()`, `container.restart()`, `container.remove()` API reference
- [Docker SDK for Python 7.1.0 - Networks API](https://docker-py.readthedocs.io/en/stable/networks.html) -- `networks.create()`, `network.connect()` parameters
- [Docker SDK for Python 7.1.0 - Client API](https://docker-py.readthedocs.io/en/stable/client.html) -- `DockerClient`, `from_env()`, `close()`
- [Docker SDK thread safety (issue #3229)](https://github.com/docker/docker-py/issues/3229) -- confirmed DockerClient is NOT thread-safe; create per-thread
- [Docker SDK context manager (issue #2808 / PR #2815)](https://github.com/docker/docker-py/issues/2808) -- context manager support added for `DockerClient`
- [PyPI: docker 7.1.0](https://pypi.org/project/docker/) -- version confirmed latest as of April 2026
- Codebase: `switchboard/registry/repository.py` -- established patterns for session handling, Depends() injection
- Codebase: `switchboard/admin/router.py` -- established patterns for endpoint structure, error handling
- Codebase: `switchboard/registry/exceptions.py` -- established patterns for exception hierarchy

### Secondary (MEDIUM confidence)
- [Python asyncio.to_thread() discussion](https://discuss.python.org/t/is-asyncio-to-thread-always-threadsafe/49145) -- thread safety nuances with context variables
- [Docker detach issue #3052](https://github.com/docker/docker-py/issues/3052) -- container exits immediately with `detach=True`, need `reload()` to check status

### Tertiary (LOW confidence)
- None -- all critical claims verified against official docs or codebase

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- Docker SDK 7.1.0 is confirmed; all other libraries already installed and verified in Phases 1-2
- Architecture: HIGH -- patterns directly extend existing codebase; Docker SDK API verified against official docs
- Pitfalls: HIGH -- Docker SDK thread safety confirmed by maintainers; detach behavior confirmed by docs and issues

**Research date:** 2026-04-15
**Valid until:** 2026-05-15 (30 days -- Docker SDK is stable, no breaking changes expected)
