# Phase 4: Reference Servers - Context

**Gathered:** 2026-04-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Two containerized MCP servers (echo and ping) exist as Docker images that respond correctly to Streamable HTTP transport requests, providing validated test targets for gateway integration. This phase does not include any gateway routing logic (Phase 5). The reference servers are independent microservices separate from the `switchboard/` platform package.

</domain>

<decisions>
## Implementation Decisions

### Source code location
- **D-01:** Reference server source lives at `servers/echo/` and `servers/ping/` at the project root — not inside `switchboard/`. These are independent microservices, not library code.
- **D-02:** Each server has its own standalone `Dockerfile` (`servers/echo/Dockerfile`, `servers/ping/Dockerfile`). Images are built and deployed independently.

### MCP implementation
- **D-03:** Both servers are implemented using FastMCP 3.2.4 (per STACK.md recommendation: "use for the echo/ping reference servers"). FastMCP's `mcp.run(transport="streamable-http")` satisfies success criteria SC-3.
- **D-04:** Echo server exposes one MCP tool that returns its input arguments unchanged (REFS-01). Ping server responds to MCP `ping` requests (REFS-02).
- **D-05:** Both containers listen on port **8000** internally (locked by Phase 3, D-03). No host ports are published — containers are reachable only via the `switchboard-internal` Docker network.
- **D-06:** Container naming follows Phase 3 convention: `sb-echo` and `sb-ping` (locked by Phase 3, D-02).

### Docker Compose integration
- **D-07:** Both servers are added to `docker-compose.yml` as `build:` services with `context:` pointing to `servers/echo/` and `servers/ping/`. They auto-start on `docker compose up` alongside the database — making Phase 5 gateway testing seamless without manual image builds.
- **D-08:** The reference servers are also registered via the Admin API and verified that ContainerManager can start/stop them (satisfies SC-4: "Both images can be registered via the Admin API and started by the container manager"). Phase 4 performs both: standalone docker-compose service validation AND ContainerManager lifecycle validation.

### Package isolation
- **D-09:** Each server has its own `pyproject.toml` with only the server's direct dependencies (fastmcp + uvicorn). Own `uv.lock` for reproducible builds. Keeps Docker images lean and isolated from the platform's dependency graph.
- **D-10:** Dockerfiles use `uv` to install deps from the server's `pyproject.toml` (consistent with project toolchain). Pattern: install uv in the image → copy pyproject.toml + uv.lock → `uv sync` → copy source.

### Testing
- **D-11:** Phase 4 includes integration tests that actually start the echo/ping containers and send real MCP Streamable HTTP requests using the MCP Python client. Asserts exact response content (SC-1: echo returns input unchanged; SC-2: ping returns valid response).
- **D-12:** Tests live in `tests/reference_servers/` (or `tests/test_reference_servers.py`) inside the root tests directory — co-located with all other platform tests. Marked with a custom pytest marker (e.g., `@pytest.mark.reference_servers`) for selective execution.
- **D-13:** Tests mark integration (require Docker running) — same pattern as existing integration tests that require PostgreSQL.

### Claude's Discretion
- Exact FastMCP tool definition style (decorator vs. class-based)
- Multi-stage Dockerfile vs. single-stage (can use single-stage for simplicity since these are dev targets)
- Whether to add a `healthcheck:` in docker-compose.yml for each reference server (recommended for Phase 5 startup ordering)
- Exact pytest marker name (`reference_servers` vs `integration_server` etc.)
- Whether `uv` is installed in the Docker image via official install script or copied from a uv base image

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — REFS-01 (echo server: returns input arguments unchanged), REFS-02 (ping server: responds to MCP ping method)

### Technology stack
- `.planning/research/STACK.md` — FastMCP 3.2.4 (confirmed for reference servers), mcp 1.27.0 (underlying SDK), uvicorn 0.44.0; MCP Streamable HTTP transport as production standard; SSE transport deprecated and must NOT be used

### Phase 1 decisions (locked — do not re-decide)
- `.planning/phases/01-foundation/01-CONTEXT.md` — D-12/D-13/D-14 (test strategy: require running Docker, pytest markers, test database separation pattern to adapt for containers)

### Phase 3 decisions (locked — do not re-decide)
- `.planning/phases/03-container-manager/03-CONTEXT.md` — D-01 (`switchboard-internal` network), D-02 (container naming: `sb-{name}`, gateway routes to `http://sb-{name}:8000/mcp`), D-03 (port 8000 internal)

### MCP specification
- MCP Streamable HTTP transport: https://modelcontextprotocol.io/specification/2025-03-26/basic/transports — use streamable-http, not SSE (per STACK.md)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `switchboard/admin/router.py` — Admin API endpoints for server registration (`POST /api/v1/servers`) — Phase 4 tests use this to register echo and ping servers
- `switchboard/container/manager.py` — `ContainerManager` with `start()`, `stop()` — used in Phase 4 integration test for SC-4 validation
- `docker-compose.yml` — Already has `switchboard-internal` network defined; just needs the echo and ping service entries added with `build:` and `networks:` keys

### Established Patterns
- `from __future__ import annotations` in all Python files
- `uv` for package management — replicate in each server's Dockerfile
- Pytest markers for test categorization — add a new marker for reference server tests
- Docker services join `switchboard-internal` network — reference server services must also join this network in docker-compose.yml

### Integration Points
- `docker-compose.yml` — Add `echo` and `ping` services with `build:`, `networks: [switchboard-internal]`, and no published ports
- `pyproject.toml` (root) — Add `reference_servers` to `tool.pytest.ini_options.markers` list
- Phase 5 (Gateway) — Will route to `http://sb-echo:8000/mcp` and `http://sb-ping:8000/mcp` via the ContainerManager's naming convention

</code_context>

<specifics>
## Specific Ideas

- No specific UI/UX references — these are backend MCP servers
- Gateway (Phase 5) routing convention is locked: `http://sb-{name}:8000/mcp` — reference server images must be compatible with this URL pattern

</specifics>

<deferred>
## Deferred Ideas

- Per-server port configuration — v2 (Phase 3 locked all containers to port 8000)
- Additional reference servers (e.g., a stateful tool that tests session continuity) — useful for Phase 5 testing but belongs in Phase 5 scope if needed
- Automated image publishing to ECR — Phase 7 (AWS Deployment)

</deferred>

---

*Phase: 04-reference-servers*
*Context gathered: 2026-04-16*
