# Phase 6: Health Monitor - Context

**Gathered:** 2026-04-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Continuously poll running MCP server containers and expose the most recent liveness result via the existing `GET /servers/{name}` Admin API endpoint as a new `health_status` field. Starting, stopping, and restarting containers is Phase 3 (ContainerManager). AWS CloudMap / ECS health checks are Phase 7. This phase only observes and reports.

</domain>

<decisions>
## Implementation Decisions

### Probe mechanism
- **D-01:** Use both Docker inspect and HTTP probe — inspect first, then HTTP if container is running.
- **D-02:** Docker inspect checks `container.status == "running"`. If the container is not running, classify as `unreachable` immediately — no HTTP probe needed.
- **D-03:** HTTP probe: `POST /mcp` on the container's internal Docker network address (port 8000, same `switchboard-internal` network). A 2xx or 4xx response means the server is alive (any HTTP response = the process is serving). A connection error or timeout = failure.
- **D-04:** Health state machine:
  - `healthy` = Docker inspect running AND HTTP probe succeeds
  - `degraded` = Docker inspect running BUT HTTP probe has been failing (not yet 2 consecutive failures)
  - `unreachable` = Docker inspect shows container gone/stopped OR HTTP probe has failed 2 consecutive times
- **D-05:** Docker SDK calls in the health monitor MUST use `asyncio.to_thread()` (established pattern from ContainerManager).

### Health status storage
- **D-06:** Add `health_status` as a new nullable column on the `Server` ORM model. Type: new `HealthStatus` enum (`healthy`, `degraded`, `unreachable`). Default value: `None` (null) — means "not yet polled".
- **D-07:** One new Alembic migration to add the column. `ServerRead` Pydantic schema gets a new `health_status: HealthStatus | None` field — it's picked up automatically via `from_attributes=True`.
- **D-08:** Null value in API response = server has not been polled yet (e.g., newly registered, or still stopped). No `unknown` enum value needed — null is sufficient.

### Background task placement
- **D-09:** Polling logic lives in a new `switchboard/health/` module (e.g., `switchboard/health/monitor.py`). This keeps the concern isolated and independently testable.
- **D-10:** The admin API app (`switchboard/admin/app.py`) starts the polling loop in a new `lifespan` context manager. The gateway does NOT start the poller — it reads `health_status` through normal DB queries like any other server field.
- **D-11:** Polling interval: 30 seconds by default, configurable via `HEALTH_POLL_INTERVAL` environment variable (add to pydantic-settings `Settings` class). The 30-second default means "within two polling intervals" = 60 seconds worst case, satisfying the success criterion.
- **D-12:** The poller only polls servers with `status == running`. Stopped servers are skipped each cycle; their `health_status` is not updated (retains last known value or null).

### Claude's Discretion
- Exact httpx client lifecycle for the health monitor (create per-poll or share via app.state)
- Error handling and logging for individual poll failures (log the error, continue next cycle — don't crash the loop)
- Failure counter storage (in-memory dict keyed by server name is fine — poller is single-process)
- Whether to reset `health_status` to `null` when a server is stopped via the Admin API

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` §CONT-04 — "Platform periodically polls each server's health and exposes current health status via Admin API"

### Phase 6 roadmap entry
- `.planning/ROADMAP.md` §Phase 6 — Goal, success criteria, and dependency on Phase 5

### Existing code (integration points)
- `switchboard/registry/models.py` — Server ORM model; HealthStatus enum goes here or in a new `switchboard/health/` module; `health_status` column added here
- `switchboard/registry/schemas.py` — ServerRead schema; add `health_status: HealthStatus | None`
- `switchboard/admin/app.py` — Gets a new lifespan that starts the health monitor background task
- `switchboard/container/manager.py` — asyncio.to_thread() pattern for Docker SDK calls; replicate for inspect calls in health monitor
- `switchboard/config.py` — pydantic-settings Settings class; add HEALTH_POLL_INTERVAL

No external specs — requirements fully captured in decisions above.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `asyncio.to_thread()` pattern from `switchboard/container/manager.py` — use identically for Docker inspect calls in the health monitor
- `docker.from_env()` with `client.close()` in `finally` — same pattern for inspect in health monitor
- `switchboard/db/session.py` session factory — the health monitor will create its own DB sessions for polling cycles
- `structlog` logging already configured in gateway — import and reuse in health module

### Established Patterns
- SQLAlchemy async session via `AsyncSession` + `asyncio.to_thread()` for blocking Docker calls
- Pydantic-settings env var config: new `HEALTH_POLL_INTERVAL: int = 30` field
- `ServerRepository` for reading server records — health monitor reads all `status == running` servers via existing repo methods

### Integration Points
- `Server` ORM model: add `health_status` column (nullable `HealthStatus` enum)
- `ServerRead` schema: add `health_status: HealthStatus | None` field
- `admin/app.py`: add `lifespan` context manager that `asyncio.create_task()`s the polling loop
- Alembic migrations: one new migration for the `health_status` column
- `CONTAINER_NAME_PREFIX` + server name = container name; use with Docker SDK to inspect by name

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches for background task structure and failure counter implementation.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 06-health-monitor*
*Context gathered: 2026-04-18*
