# Phase 3: Container Manager - Context

**Gathered:** 2026-04-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Container lifecycle abstraction that lets an operator start, stop, and restart registered MCP server containers via the Admin API. All Docker SDK calls are wrapped inside `asyncio.to_thread()` so the async event loop is never blocked. No gateway routing logic (Phase 5). No health polling (Phase 6). Phase 3 only adds the three lifecycle endpoints and the `ContainerManager` service that backs them.

</domain>

<decisions>
## Implementation Decisions

### Network isolation
- **D-01:** A named internal Docker network (`switchboard-internal`) is pre-declared in `docker-compose.yml`. `ContainerManager` attaches every MCP server container to this network via the Docker SDK. No host ports are published — containers are reachable only via the internal network. This is the network the gateway (Phase 5) will also join.
- **D-02:** Container naming uses the `sb-` prefix: a server named `echo` runs as container `sb-echo`. The gateway (Phase 5) routes to `http://sb-{name}:8000/mcp` using this convention. The prefix avoids collisions with other containers on the shared Docker network.
- **D-03:** MCP server containers listen on port **8000** internally (the FastAPI/uvicorn default). This is a constant defined in the container manager module — not a per-server configuration in Phase 3.

### Error handling & edge cases
- **D-04:** Container start failure (bad image, OOM, Docker daemon error) → `ContainerManager` catches the Docker SDK exception, calls `update_status(session, server_id, ServerStatus.error)`, and the API endpoint returns **HTTP 500** with a `{"detail": "<reason>"}` body. Operator can inspect via `GET /servers/{name}`.
- **D-05:** `POST /servers/{name}/stop` when server is already stopped → **409 Conflict** with `{"detail": "Server 'X' is not running"}`. Consistent with the existing 409 for duplicate registration (Phase 2, D-03).
- **D-06:** `POST /servers/{name}/start` when server is already running → **409 Conflict** with `{"detail": "Server 'X' is already running"}`. Prevents duplicate container creation.
- **D-07:** All three lifecycle endpoints return **404** if the server name is not found in the registry (same pattern as `GET /servers/{name}` in Phase 2).

### API response shape
- **D-08:** `POST /servers/{name}/start`, `/stop`, and `/restart` all return the full **`ServerRead`** schema on success (HTTP 200). Consistent with Phase 2 endpoints — callers always receive the current state without a follow-up GET. The returned `ServerRead` reflects the updated `status` and `container_id`.

### ContainerManager abstraction
- **D-09:** A `ContainerManager` class lives in `switchboard/container/manager.py` with async-safe methods: `start(session, server)`, `stop(session, server)`, `restart(session, server)`. Mirrors the `ServerRepository` pattern — injected as `Depends(get_container_manager)` in API endpoints, reusable by Phase 5 (gateway) and Phase 6 (health monitor) via the same `Depends()` mechanism.
- **D-10:** The Docker client (`docker.from_env()`) is instantiated **inside each `asyncio.to_thread()` call** — not shared across calls. Thread-safe by construction; avoids event loop blocking during client initialization. Each thread creates and closes its own connection.

### Claude's Discretion
- Exact exception type hierarchy for `ContainerManager` errors (e.g., `ContainerStartError`, `ContainerStopError`)
- Whether `restart()` uses Docker's `container.restart()` or a sequential `stop() + start()` approach
- Internal port constant name (`CONTAINER_PORT = 8000`) and location
- `get_container_manager()` factory function structure in `switchboard/container/__init__.py`
- Whether to add a `network_name` setting to `Settings` (in `config.py`) or hard-code `switchboard-internal` as a constant

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — CONT-01 (start), CONT-02 (stop), CONT-03 (restart); also Phase 3 success criteria SC-4 (asyncio.to_thread) and SC-5 (no host-published ports)

### Project constraints
- `.planning/PROJECT.md` — Python 3.12+, `switchboard/` top-level package, Docker-based local dev

### Phase 1 decisions (locked)
- `.planning/phases/01-foundation/01-CONTEXT.md` — D-09 (`ServerRepository` methods including `update_status()`, `update_container_id()`), D-10 (async session injection), D-05 (`ServerStatus` enum: stopped/running/error)

### Phase 2 decisions (locked)
- `.planning/phases/02-admin-api/02-CONTEXT.md` — D-02 (`/api/v1/` prefix), D-03 (409 pattern), D-04 (error response format: `{"detail": "..."}`)

### Technology stack
- `.planning/research/STACK.md` — docker Python SDK 7.1.0; confirmed versions for FastAPI, SQLAlchemy, asyncpg

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `switchboard/registry/repository.py` — `ServerRepository.update_status()` and `update_container_id()` — call these after every successful Docker operation to keep the registry in sync
- `switchboard/registry/models.py` — `ServerStatus` enum (`stopped`, `running`, `error`) — use for all status transitions
- `switchboard/registry/schemas.py` — `ServerRead` — return this from all three lifecycle endpoints (D-08)
- `switchboard/admin/router.py` — Established pattern for `Depends(get_session)` + `Depends(get_repository)` injection — replicate for `Depends(get_container_manager)`
- `switchboard/registry/exceptions.py` — `ServerNotFoundError` already exists — reuse pattern to create `ContainerError` hierarchy in `switchboard/container/`
- `switchboard/container/__init__.py` — Stub package already created in Phase 1 (D-01)

### Established Patterns
- Repository methods accept `session` as first argument; caller commits — same convention applies to `ContainerManager` methods
- `from __future__ import annotations` + `TYPE_CHECKING` block — use in all new files
- `lru_cache` on `get_settings()` — do not instantiate `Settings` directly
- 409 Conflict for invalid-state mutations (Phase 2, D-03) — extended to lifecycle state conflicts (D-05, D-06)

### Integration Points
- `docker-compose.yml` — needs `switchboard-internal` network added; also needs `networks:` key on the `db` service if it needs to communicate with MCP containers (unlikely in Phase 3, but plan for Phase 5)
- `switchboard/admin/router.py` — add three new routes: `POST /api/v1/servers/{name}/start`, `/stop`, `/restart`
- `switchboard/config.py` — may need `DOCKER_NETWORK` setting if not hard-coding the network name constant

</code_context>

<specifics>
## Specific Ideas

- No specific references beyond the technical decisions above
- Gateway (Phase 5) will route to `http://sb-{name}:8000/mcp` — this convention is locked here and Phase 5 must use it

</specifics>

<deferred>
## Deferred Ideas

- Per-server port configuration (all containers use port 8000 in Phase 3 — configurable port is a v2 concern)
- Container environment variable injection (CONT-05) — v2 requirement per REQUIREMENTS.md
- Restart policy (automatic restart on crash) — Phase 6 (Health Monitor) or v2
- Rolling restart without downtime — explicitly out of scope per REQUIREMENTS.md

</deferred>

---

*Phase: 03-container-manager*
*Context gathered: 2026-04-15*
