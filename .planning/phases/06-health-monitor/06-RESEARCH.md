# Phase 6: Health Monitor - Research

**Researched:** 2026-04-18
**Domain:** asyncio background polling, Docker health inspection, FastAPI lifespan, SQLAlchemy async sessions outside request context
**Confidence:** HIGH

## Summary

Phase 6 adds a background polling loop to the admin API process that periodically inspects Docker container state and probes MCP server HTTP endpoints, persisting the result as a `health_status` column on the existing `Server` model. The health monitor is architecturally isolated in a new `switchboard/health/` module, started via FastAPI's lifespan context manager, and uses the same `asyncio.to_thread()` pattern established in Phase 3's `ContainerManager` for blocking Docker SDK calls.

The technical surface is well-understood: FastAPI lifespan for background task startup/shutdown, `httpx.AsyncClient` for HTTP health probes, `asyncio.to_thread()` for Docker inspect calls, SQLAlchemy `async_sessionmaker` for creating sessions outside request context, and a straightforward Alembic migration to add a nullable PostgreSQL enum column. Every library is already installed in the project. No new dependencies are required.

The primary risk areas are: (1) ensuring the polling loop does not silently die on unhandled exceptions, (2) correct session lifecycle management in the background task (session-per-cycle, not shared across cycles), and (3) the Alembic migration must create the PostgreSQL enum type before adding the column that references it.

**Primary recommendation:** Use `asyncio.create_task()` in the admin API lifespan to start a `while True` polling loop with `asyncio.sleep()`. The loop catches all exceptions per-server (log and continue) and `asyncio.CancelledError` at the top level for graceful shutdown. Create a fresh `AsyncSession` per polling cycle via the existing `async_session_factory`. Use a shared `httpx.AsyncClient` stored on `app.state` for HTTP probes. Track failure counts in an in-memory `dict[str, int]`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Use both Docker inspect and HTTP probe -- inspect first, then HTTP if container is running.
- **D-02:** Docker inspect checks `container.status == "running"`. If the container is not running, classify as `unreachable` immediately -- no HTTP probe needed.
- **D-03:** HTTP probe: `POST /mcp` on the container's internal Docker network address (port 8000, same `switchboard-internal` network). A 2xx or 4xx response means the server is alive (any HTTP response = the process is serving). A connection error or timeout = failure.
- **D-04:** Health state machine: `healthy` = Docker running AND HTTP probe succeeds; `degraded` = Docker running BUT HTTP probe failing (not yet 2 consecutive); `unreachable` = Docker gone/stopped OR HTTP probe failed 2 consecutive times.
- **D-05:** Docker SDK calls in the health monitor MUST use `asyncio.to_thread()` (established pattern from ContainerManager).
- **D-06:** Add `health_status` as a new nullable column on the `Server` ORM model. Type: new `HealthStatus` enum (`healthy`, `degraded`, `unreachable`). Default value: `None` (null) -- means "not yet polled".
- **D-07:** One new Alembic migration to add the column. `ServerRead` Pydantic schema gets a new `health_status: HealthStatus | None` field -- picked up automatically via `from_attributes=True`.
- **D-08:** Null value in API response = server has not been polled yet. No `unknown` enum value needed.
- **D-09:** Polling logic lives in `switchboard/health/` module (e.g., `switchboard/health/monitor.py`).
- **D-10:** Admin API app starts the polling loop in a new lifespan context manager. Gateway does NOT start the poller.
- **D-11:** Polling interval: 30 seconds default, configurable via `HEALTH_POLL_INTERVAL` env var.
- **D-12:** Poller only polls servers with `status == running`. Stopped servers are skipped.

### Claude's Discretion
- Exact httpx client lifecycle for the health monitor (create per-poll or share via app.state)
- Error handling and logging for individual poll failures
- Failure counter storage (in-memory dict keyed by server name is fine)
- Whether to reset `health_status` to `null` when a server is stopped via the Admin API

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CONT-04 | Platform periodically polls each server's health and exposes current health status via Admin API | Full research coverage: background polling loop pattern, Docker inspect + HTTP probe mechanism, health_status column on Server model, ServerRead schema update, Alembic migration, admin API lifespan integration |
</phase_requirements>

## Standard Stack

### Core (All Already Installed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.135.3 | Admin API lifespan for background task | Already used; lifespan context manager is the documented pattern for background tasks [VERIFIED: codebase] |
| httpx | 0.28.1 | HTTP health probe to MCP server `/mcp` endpoint | Already installed (dev dep); async-native, fine-grained timeout control via `httpx.Timeout` [VERIFIED: pyproject.toml] |
| docker (Python SDK) | 7.1.0 | Docker inspect via `client.containers.get()` | Already used in ContainerManager; `asyncio.to_thread()` pattern established [VERIFIED: codebase] |
| SQLAlchemy | 2.0.49 | Async ORM for health_status column reads/writes | Already used; `async_sessionmaker` provides session-per-task pattern [VERIFIED: codebase] |
| asyncpg | 0.31.0 | Async PostgreSQL driver | Already used as SQLAlchemy async backend [VERIFIED: codebase] |
| Alembic | 1.18.4 | Database migration for new column | Already configured with async env.py [VERIFIED: codebase] |
| structlog | 25.x | Structured logging for health monitor events | Already configured in gateway; import and reuse [VERIFIED: codebase] |

### No New Dependencies Required

Every library needed for Phase 6 is already in `pyproject.toml`. The health monitor httpx client is a dev dependency (`httpx>=0.28.1` in dev group), but since the admin API process needs it at runtime, **httpx should be moved from `[dependency-groups] dev` to `[project] dependencies`**. [VERIFIED: pyproject.toml shows httpx only in dev group]

**Installation:** No new packages needed.

**Action required:** Move `httpx>=0.28.1` from dev dependencies to main dependencies in `pyproject.toml`. The health monitor's HTTP probe runs in production, not just in tests.

## Architecture Patterns

### Recommended Module Structure

```
switchboard/
├── health/
│   ├── __init__.py          # Empty or exports start_health_monitor
│   ├── monitor.py           # HealthMonitor class with polling loop
│   └── prober.py            # (optional) Probe logic if monitor.py grows
├── registry/
│   └── models.py            # HealthStatus enum added here (alongside ServerStatus)
└── admin/
    └── app.py               # Lifespan updated to start health monitor
```

[VERIFIED: codebase structure follows this module-per-domain pattern -- see `switchboard/container/`, `switchboard/registry/`, `switchboard/gateway/`]

### Pattern 1: FastAPI Lifespan Background Task

**What:** Start a long-running `asyncio.Task` before yield, cancel it after yield.
**When to use:** Any background polling loop that must run alongside the ASGI server.
**Why this pattern:** FastAPI's lifespan is the documented way to manage resource lifecycles. The task runs in the same event loop as the ASGI server, so it can share `app.state` resources like httpx clients. [CITED: https://fastapi.tiangolo.com/advanced/events/]

```python
# Source: FastAPI official docs + codebase gateway pattern
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import httpx
from fastapi import FastAPI

from switchboard.health.monitor import HealthMonitor

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup: create shared resources
    app.state.health_client = httpx.AsyncClient(
        timeout=httpx.Timeout(5.0, connect=3.0),
    )
    monitor = HealthMonitor(app.state.health_client)
    task = asyncio.create_task(monitor.run())

    yield

    # Shutdown: cancel task, close client
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    await app.state.health_client.aclose()
```

### Pattern 2: Resilient Polling Loop with Exception Isolation

**What:** A `while True` loop that catches exceptions per-server so one failing server never kills the loop.
**When to use:** Any background monitor polling multiple targets.
**Why this pattern:** An unhandled exception in the polling loop would silently kill the background task. The event loop does not restart cancelled/crashed tasks. [CITED: https://roguelynn.com/words/asyncio-graceful-shutdowns/]

```python
async def run(self) -> None:
    """Main polling loop -- runs until cancelled."""
    try:
        while True:
            await self._poll_cycle()
            await asyncio.sleep(self._interval)
    except asyncio.CancelledError:
        logger.info("health_monitor_shutdown")
        raise  # Re-raise so the lifespan await completes

async def _poll_cycle(self) -> None:
    """Poll all running servers. Never raises."""
    async with self._session_factory() as session:
        servers = await self._get_running_servers(session)
        for server in servers:
            try:
                new_status = await self._probe_server(server)
                await self._update_health(session, server, new_status)
            except Exception:
                logger.exception("health_probe_error", server_name=server.name)
        await session.commit()
```

### Pattern 3: Session-Per-Cycle (Not Per-Request)

**What:** Create a new `AsyncSession` via `async_session_factory()` for each polling cycle, not a long-lived session.
**When to use:** Background tasks that perform database operations outside the FastAPI request lifecycle.
**Why this pattern:** Sessions must not be shared across concurrent tasks or held open indefinitely. The `async_session_factory` (already defined in `switchboard/db/session.py`) creates properly scoped sessions. Each polling cycle gets its own session, reads running servers, updates health statuses, commits, and closes. [CITED: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html]

```python
# Source: SQLAlchemy 2.0 async docs + switchboard/db/session.py
from switchboard.db.session import async_session_factory

async def _poll_cycle(self) -> None:
    async with async_session_factory() as session:
        # Read servers, probe, update health_status
        await session.commit()
    # Session auto-closed by context manager
```

### Pattern 4: Docker Inspect via asyncio.to_thread()

**What:** Wrap blocking Docker SDK calls in `asyncio.to_thread()` with a fresh client per call.
**When to use:** Any Docker SDK operation in an async context.
**Why this pattern:** Exact replication of the established ContainerManager pattern. Fresh `docker.from_env()` per call avoids connection pool issues. [VERIFIED: switchboard/container/manager.py lines 162-199]

```python
# Source: switchboard/container/manager.py (established pattern)
async def _inspect_container(self, container_name: str) -> str | None:
    """Return container status or None if not found."""
    return await asyncio.to_thread(self._inspect_blocking, container_name)

def _inspect_blocking(self, container_name: str) -> str | None:
    """Blocking Docker inspect (runs in thread)."""
    client = docker.from_env()
    try:
        container = client.containers.get(container_name)
        return container.status  # "running", "exited", "dead", etc.
    except docker.errors.NotFound:
        return None
    finally:
        client.close()
```

### Pattern 5: In-Memory Failure Counter + DB Persistence

**What:** Track consecutive HTTP probe failures in a `dict[str, int]` in memory. Write the derived `HealthStatus` to the database.
**When to use:** When the state machine depends on counting consecutive failures but the count itself is transient.
**Why this pattern:** The failure count is an implementation detail of the state machine, not something the API exposes. In-memory is simpler, avoids an extra DB column, and is safe because the poller is single-process. The DB only stores the final computed `HealthStatus` enum value. [ASSUMED]

```python
# Failure counters -- in-memory, reset on success
_failure_counts: dict[str, int] = {}

def _compute_status(
    self, server_name: str, docker_running: bool, http_ok: bool
) -> HealthStatus:
    if not docker_running:
        self._failure_counts.pop(server_name, None)
        return HealthStatus.unreachable

    if http_ok:
        self._failure_counts.pop(server_name, None)
        return HealthStatus.healthy

    # HTTP failed while Docker is running
    count = self._failure_counts.get(server_name, 0) + 1
    self._failure_counts[server_name] = count
    if count >= 2:
        return HealthStatus.unreachable
    return HealthStatus.degraded
```

### Anti-Patterns to Avoid

- **Sharing a single AsyncSession across polling cycles:** Sessions are not thread-safe and must not be reused across async task boundaries. Create a new one per cycle. [CITED: SQLAlchemy async docs]
- **Not catching exceptions inside the polling loop:** An unhandled exception kills the `asyncio.Task` silently. No automatic restart. The monitor must catch `Exception` per-server and `CancelledError` at the top level.
- **Using `asyncio.to_thread()` for async-safe operations:** Only Docker SDK calls need `to_thread()`. The HTTP probe via httpx is already async-native and runs directly in the event loop.
- **Creating a new httpx.AsyncClient per probe:** Client creation is expensive (connection pool setup). Share one client across all probes in a cycle. Recreating per-probe wastes TCP connections and adds latency.
- **Forgetting to cancel the background task on shutdown:** If the lifespan does not cancel the task, the process hangs on SIGTERM because `asyncio.sleep()` blocks indefinitely.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP health probes | Raw `asyncio.open_connection()` / `urllib` | `httpx.AsyncClient.post()` with `httpx.Timeout` | httpx handles connection pooling, timeouts, error classification; raw sockets miss HTTP protocol negotiation |
| Background task scheduling | Custom thread pool or APScheduler | `asyncio.create_task()` + `asyncio.sleep()` in lifespan | The polling loop is simple enough that a scheduler adds unnecessary complexity; APScheduler's async support is fragile |
| Docker container inspection | Subprocess `docker inspect` CLI | Docker Python SDK `client.containers.get()` | SDK parses JSON output, handles API versioning, and is already used throughout the codebase |
| Retry logic for probes | Hand-rolled retry with counters | Simple failure counter dict (not tenacity) | The state machine IS the retry logic -- `degraded` is the "retry in progress" state. Adding tenacity would double-count retries. |
| Session management in background tasks | Manual engine.connect() / raw SQL | `async_session_factory()` context manager | Existing factory handles connection pooling, session scoping, and cleanup automatically |

**Key insight:** This phase does not need any new libraries. The existing stack (httpx, docker SDK, SQLAlchemy async, structlog) provides everything. The complexity is in the orchestration pattern, not in missing capabilities.

## Common Pitfalls

### Pitfall 1: Background Task Dies Silently

**What goes wrong:** An unhandled exception in the `asyncio.create_task()` coroutine kills the task. No error is logged, no restart happens. The health monitor stops running but the API continues serving stale health data.
**Why it happens:** `asyncio.create_task()` does not propagate exceptions to the caller unless the task is awaited. Exceptions are only reported when the task object is garbage collected (and even then, only as a warning).
**How to avoid:** Catch `Exception` broadly at the per-server level (log and continue to next server). Only let `asyncio.CancelledError` propagate (re-raise it) to support graceful shutdown.
**Warning signs:** `health_status` values stop changing even though containers are being started/stopped.

### Pitfall 2: Alembic Enum Type Creation Order

**What goes wrong:** The migration adds a column with a PostgreSQL enum type, but the enum type does not exist yet. The migration fails with `ProgrammingError: type "healthstatus" does not exist`.
**Why it happens:** PostgreSQL enums are separate database objects. They must be created with `CREATE TYPE` before a column can reference them. Alembic's autogenerate sometimes handles this correctly, sometimes not.
**How to avoid:** In the migration, explicitly create the enum type first using `sa.Enum('healthy', 'degraded', 'unreachable', name='healthstatus').create(op.get_bind())` before `op.add_column()`. In the downgrade, drop the column first, then drop the type. The existing migration for `serverstatus` (in `a5578b684627`) uses inline `sa.Enum()` in `create_table()` which auto-creates the type -- but `add_column()` does NOT auto-create it. [VERIFIED: existing migration pattern in `alembic/versions/a5578b684627_create_servers_table.py`]
**Warning signs:** Migration works in tests (fresh DB) but fails in environments with existing schema.

### Pitfall 3: Session Reuse Across Polling Cycles

**What goes wrong:** The health monitor creates one `AsyncSession` at startup and reuses it for all polling cycles. Over time, the session's identity map grows unbounded, stale objects accumulate, and eventually a `DetachedInstanceError` or stale-data bug occurs.
**Why it happens:** Sessions are designed for short-lived units of work. Long-lived sessions accumulate ORM identity map entries and hold database connections from the pool.
**How to avoid:** Use `async with async_session_factory() as session:` per polling cycle. The context manager closes the session and returns the connection to the pool.
**Warning signs:** Memory growth in the admin API process over time; stale `health_status` values that don't match Docker state.

### Pitfall 4: httpx.ConnectError vs ConnectTimeout Confusion

**What goes wrong:** The health probe catches `httpx.ConnectError` but not `httpx.TimeoutException`. A slow-but-alive server is classified as `unreachable` because the timeout exception propagates uncaught.
**Why it happens:** httpx has a detailed exception hierarchy. `ConnectError` and `ConnectTimeout` are siblings under `TransportError`, not parent-child. Catching one misses the other.
**How to avoid:** Catch `httpx.TransportError` which covers all network-level failures (connection errors, timeouts, protocol errors). Or catch `httpx.HTTPError` for the broadest coverage including HTTP status errors (though for health probes, any HTTP response = alive per D-03). [VERIFIED: https://www.python-httpx.org/exceptions/]
**Warning signs:** Health probes log unhandled exceptions for servers that respond slowly.

### Pitfall 5: Not Cleaning Up Failure Counters for Removed/Stopped Servers

**What goes wrong:** A server is stopped, its failure counter remains in the in-memory dict. When the server is restarted, the old counter causes it to immediately transition to `degraded` or `unreachable` on the first probe failure.
**Why it happens:** The failure counter dict is not pruned when servers are stopped or removed.
**How to avoid:** Reset (delete) the failure counter when: (1) a probe succeeds (counter no longer needed), (2) Docker inspect shows container not running (counter irrelevant), or (3) at the start of each poll cycle, prune keys for servers not in the current running set.
**Warning signs:** Newly restarted servers show `degraded` status on first probe failure instead of remaining `healthy`.

### Pitfall 6: Admin API Currently Has No Lifespan

**What goes wrong:** The admin API app (`switchboard/admin/app.py`) currently has no `lifespan` parameter. Adding a lifespan requires modifying the `FastAPI()` constructor call.
**Why it happens:** The admin API was created in Phase 2 as a simple CRUD API with no background tasks.
**How to avoid:** This is expected. Add a new `lifespan` async context manager to `switchboard/admin/app.py` and pass it to `FastAPI(lifespan=lifespan)`. The gateway already demonstrates this pattern in `switchboard/gateway/app.py`. [VERIFIED: admin/app.py has no lifespan; gateway/app.py has a working lifespan]
**Warning signs:** None -- this is a straightforward integration.

## Code Examples

### Health Probe HTTP Call
```python
# Source: httpx official docs (https://www.python-httpx.org/advanced/timeouts/)
# + decision D-03 from CONTEXT.md
async def _http_probe(self, server_name: str) -> bool:
    """Probe the MCP server's /mcp endpoint. Returns True if alive."""
    url = f"http://sb-{server_name}:8000/mcp"
    try:
        response = await self._client.post(url, content=b"")
        # Any HTTP response (2xx, 4xx, 5xx) = server is alive (D-03)
        return True
    except httpx.TransportError:
        # Connection error, timeout, protocol error = failure
        return False
```

### HealthStatus Enum Definition
```python
# Source: codebase pattern from ServerStatus enum in switchboard/registry/models.py
class HealthStatus(enum.Enum):
    """Health poll result for a running MCP server container.

    Values: healthy, degraded, unreachable.
    Null in the database means "not yet polled" (D-08).
    """
    healthy = "healthy"
    degraded = "degraded"
    unreachable = "unreachable"
```

### Alembic Migration for Nullable Enum Column
```python
# Source: Alembic docs (https://alembic.sqlalchemy.org/en/latest/ops.html)
# + existing migration pattern from a5578b684627_create_servers_table.py
import sqlalchemy as sa
from alembic import op

def upgrade() -> None:
    # Create the PostgreSQL enum type first (add_column does NOT auto-create)
    healthstatus = sa.Enum("healthy", "degraded", "unreachable", name="healthstatus")
    healthstatus.create(op.get_bind())

    op.add_column(
        "servers",
        sa.Column(
            "health_status",
            sa.Enum("healthy", "degraded", "unreachable", name="healthstatus",
                    create_type=False),
            nullable=True,
        ),
    )

def downgrade() -> None:
    op.drop_column("servers", "health_status")
    op.execute("DROP TYPE IF EXISTS healthstatus")
```

### httpx.AsyncClient Configuration for Health Probes
```python
# Source: httpx docs (https://www.python-httpx.org/advanced/timeouts/)
import httpx

# Short timeouts appropriate for health checks:
# - 3s connect: if the container isn't reachable in 3s, it's down
# - 5s read: if the MCP server doesn't respond in 5s, it's degraded
health_client = httpx.AsyncClient(
    timeout=httpx.Timeout(5.0, connect=3.0),
)
```

### Reading Running Servers for Polling
```python
# Source: codebase pattern from switchboard/registry/repository.py
from sqlalchemy import select
from switchboard.registry.models import Server, ServerStatus

async def _get_running_servers(self, session: AsyncSession) -> list[Server]:
    """Fetch all servers with status == running (D-12)."""
    stmt = select(Server).where(Server.status == ServerStatus.running)
    result = await session.execute(stmt)
    return list(result.scalars().all())
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@app.on_event("startup")` | `lifespan` context manager | FastAPI 0.93+ (2023) | Old approach deprecated; lifespan is the only recommended pattern for startup/shutdown [CITED: FastAPI docs] |
| Shared long-lived AsyncSession | Session-per-task via async_sessionmaker | SQLAlchemy 2.0 (2023) | Long-lived sessions cause memory leaks and stale data in async contexts [CITED: SQLAlchemy 2.0 async docs] |
| `python-jose` for JWT | `PyJWT` | 2024 | python-jose abandoned; not relevant to this phase but noting for consistency [VERIFIED: codebase uses PyJWT] |

**Deprecated/outdated:**
- `BackgroundTasks` (FastAPI): Designed for fire-and-forget per-request jobs, NOT for long-running polling loops. Using it for a health monitor would tie the loop lifecycle to a single request.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | In-memory failure counter dict is sufficient (poller is single-process) | Architecture Patterns / Pattern 5 | LOW -- if admin API runs multiple workers, each has independent counters. Mitigation: document single-worker requirement for admin API or move counters to DB. |
| A2 | The `POST /mcp` probe with empty body will elicit a response from MCP servers | Code Examples / Health Probe | LOW -- MCP servers should respond with an error (4xx) to malformed requests, which still confirms liveness per D-03. Verified by gateway proxy pattern which uses same endpoint. |
| A3 | httpx should be moved to main dependencies (not just dev) | Standard Stack | MEDIUM -- if httpx stays in dev only, production Docker images built without dev dependencies will fail to import it in the health monitor. |

## Open Questions

1. **Should `health_status` be reset to `null` when a server is stopped via Admin API?**
   - What we know: D-12 says "stopped servers are skipped each cycle; their health_status retains last known value or null." CONTEXT.md lists this as Claude's Discretion.
   - What's unclear: Whether operators expect `health_status` to show `unreachable` (last known) or `null` (not applicable since stopped) for stopped servers.
   - Recommendation: Reset to `null` on stop. Rationale: a stopped server's last health status is stale and potentially misleading. `null` clearly communicates "not being monitored." The `ContainerManager.stop()` method already updates `status` and `container_id`; adding a `health_status = None` update is trivial.

2. **httpx client lifecycle: shared vs. per-poll-cycle?**
   - What we know: CONTEXT.md lists this as Claude's Discretion. Gateway uses a shared client on `app.state`.
   - What's unclear: Whether the health monitor should share the gateway's client pattern or create its own.
   - Recommendation: Create a dedicated `httpx.AsyncClient` in the admin API lifespan, stored on `app.state.health_client`. Share it across all polls (reuses TCP connections). Close it in the lifespan shutdown. This mirrors the gateway pattern exactly. Do NOT create a client per-poll -- that wastes connection setup.

3. **Single worker requirement for in-memory failure counters?**
   - What we know: The admin API currently runs with Uvicorn (`uvicorn switchboard.admin.app:app`). No `--workers` flag is specified.
   - What's unclear: Whether production will use multiple Uvicorn workers.
   - Recommendation: Document that the health monitor assumes single-worker. If multi-worker is needed later, failure counters would need to move to the database or a shared cache. For v1, single-worker is fine.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| httpx | HTTP health probes | Partially (dev only) | 0.28.1 | Move to main deps |
| docker SDK | Container inspect | Yes | 7.1.0 | -- |
| PostgreSQL | Health status storage | Yes (Docker Compose) | 16+ | -- |
| asyncpg | Async DB driver | Yes | 0.31.0 | -- |
| Alembic | Migration | Yes | 1.18.4 | -- |

**Missing dependencies with no fallback:**
- None.

**Missing dependencies with fallback:**
- httpx is currently in dev-only dependencies. Must be moved to main dependencies for production health probes.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.26.x |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/health/ -x -q` |
| Full suite command | `uv run pytest -x -q` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CONT-04a | health_status field appears in GET /servers/{name} response | integration | `uv run pytest tests/admin/test_endpoints.py -x -q -k health` | No -- Wave 0 |
| CONT-04b | Stopping container causes health_status -> unreachable within 2 intervals | unit | `uv run pytest tests/health/test_monitor.py -x -q -k unreachable` | No -- Wave 0 |
| CONT-04c | Health monitor runs as asyncio background task, does not block requests | unit | `uv run pytest tests/health/test_monitor.py -x -q -k background` | No -- Wave 0 |
| CONT-04d | HealthStatus enum has correct values (healthy, degraded, unreachable) | unit | `uv run pytest tests/health/test_monitor.py -x -q -k enum` | No -- Wave 0 |
| CONT-04e | Docker inspect + HTTP probe produces correct state machine transitions | unit | `uv run pytest tests/health/test_monitor.py -x -q -k state_machine` | No -- Wave 0 |
| CONT-04f | Alembic migration adds health_status column successfully | integration | `uv run pytest tests/test_migrations.py -x -q` | Yes (exists but needs update) |
| CONT-04g | Failure counter resets on success, increments on failure | unit | `uv run pytest tests/health/test_monitor.py -x -q -k failure_counter` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/health/ -x -q`
- **Per wave merge:** `uv run pytest -x -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/health/__init__.py` -- package init
- [ ] `tests/health/conftest.py` -- shared fixtures (mock Docker client, mock httpx client, mock session factory)
- [ ] `tests/health/test_monitor.py` -- covers CONT-04b through CONT-04g
- [ ] Update `tests/admin/test_endpoints.py` or add `tests/admin/test_health_endpoint.py` -- covers CONT-04a

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Health monitor is internal; no user-facing auth surface |
| V3 Session Management | No | No sessions introduced |
| V4 Access Control | No | Health data exposed through existing authenticated Admin API |
| V5 Input Validation | Yes | Validate HEALTH_POLL_INTERVAL is a positive integer via pydantic-settings |
| V6 Cryptography | No | No crypto operations |

### Known Threat Patterns for Health Monitor

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SSRF via server name in probe URL | Tampering | Server names come from DB (already validated by SERVER_NAME_PATTERN regex); never from user input at probe time |
| Health probe to non-Switchboard containers | Tampering | Probe URL is constructed from `CONTAINER_NAME_PREFIX + server.name` (deterministic, validated at registration) |
| DoS via very short poll interval | Denial of Service | Pydantic validator on HEALTH_POLL_INTERVAL enforces minimum (recommend >= 5 seconds) |
| Information disclosure via health_status | Information Disclosure | Health status is only exposed via authenticated Admin API (existing JWT auth on all /api/v1/ routes) |

## Sources

### Primary (HIGH confidence)
- Codebase: `switchboard/container/manager.py` -- Docker SDK + asyncio.to_thread() pattern (lines 80-82, 162-199)
- Codebase: `switchboard/gateway/app.py` -- FastAPI lifespan context manager pattern (lines 70-90)
- Codebase: `switchboard/db/session.py` -- async_session_factory pattern (lines 17-21)
- Codebase: `switchboard/registry/models.py` -- ServerStatus enum pattern, Server model structure
- Codebase: `switchboard/registry/schemas.py` -- ServerRead with from_attributes=True pattern
- Codebase: `alembic/versions/a5578b684627_create_servers_table.py` -- existing migration with enum type
- [FastAPI Lifespan Events](https://fastapi.tiangolo.com/advanced/events/) -- official docs for lifespan pattern
- [SQLAlchemy 2.0 Async I/O](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) -- session-per-task pattern
- [httpx Timeouts](https://www.python-httpx.org/advanced/timeouts/) -- Timeout class configuration
- [httpx Exceptions](https://www.python-httpx.org/exceptions/) -- exception hierarchy

### Secondary (MEDIUM confidence)
- [Alembic Operation Reference](https://alembic.sqlalchemy.org/en/latest/ops.html) -- add_column with enum type
- [Docker SDK Containers](https://docker-py.readthedocs.io/en/stable/containers.html) -- container.status, containers.get()
- [Graceful asyncio Shutdowns](https://roguelynn.com/words/asyncio-graceful-shutdowns/) -- CancelledError handling pattern

### Tertiary (LOW confidence)
- None. All findings verified against codebase or official documentation.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already installed and used in the codebase; no new dependencies needed
- Architecture: HIGH -- patterns directly replicate existing codebase patterns (ContainerManager, gateway lifespan, session factory)
- Pitfalls: HIGH -- verified against official docs and codebase inspection; Alembic enum pitfall verified against existing migration
- Migration: HIGH -- straightforward nullable column addition; pattern established in existing migration

**Research date:** 2026-04-18
**Valid until:** 2026-05-18 (stable domain; no fast-moving libraries)
