---
phase: 04-reference-servers
plan: 01
subsystem: infra
tags: [fastmcp, docker, mcp, streamable-http, uv, reference-servers]

# Dependency graph
requires:
  - phase: 03-container-manager
    provides: "Container naming convention (sb-{name}), CONTAINER_PORT=8000, switchboard-internal network"
provides:
  - "switchboard-echo Docker image: FastMCP server with echo tool (message: str -> str)"
  - "switchboard-ping Docker image: empty FastMCP server (protocol ping automatic)"
  - "Isolated per-server pyproject.toml + uv.lock packages under servers/"
affects: [04-reference-servers, 05-gateway]

# Tech tracking
tech-stack:
  added: [fastmcp 3.2.4, hatchling]
  patterns: [uv-based Dockerfile, per-server isolated package, FastMCP tool decorator]

key-files:
  created:
    - servers/echo/pyproject.toml
    - servers/echo/server.py
    - servers/echo/Dockerfile
    - servers/echo/uv.lock
    - servers/ping/pyproject.toml
    - servers/ping/server.py
    - servers/ping/Dockerfile
    - servers/ping/uv.lock
  modified: []

key-decisions:
  - "Added [tool.hatch.build.targets.wheel] packages=[\".\"] to fix hatchling file discovery for single-file servers"
  - "Used single-stage Dockerfile with uv sync --locked for reproducible builds"

patterns-established:
  - "Per-server package isolation: each server under servers/{name}/ with own pyproject.toml and uv.lock"
  - "uv Dockerfile pattern: COPY --from=ghcr.io/astral-sh/uv:latest, bind-mount for deps layer, COPY source then uv sync"
  - "FastMCP tool definition: @mcp.tool decorator with explicit typed params (no *args/**kwargs)"

requirements-completed: [REFS-01, REFS-02]

# Metrics
duration: 4min
completed: 2026-04-16
---

# Phase 4 Plan 1: Reference Server Packages Summary

**Echo and ping MCP reference servers as independent Docker-containerized FastMCP 3.x microservices with uv-based builds and isolated dependency trees**

## Performance

- **Duration:** 4 min 17s
- **Started:** 2026-04-16T14:21:33Z
- **Completed:** 2026-04-16T14:25:50Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- Echo server package with `@mcp.tool` echo function returning input unchanged (REFS-01)
- Ping server package as empty FastMCP instance relying on protocol-level ping (REFS-02)
- Both Docker images build successfully (`switchboard-echo`, `switchboard-ping`)
- Workspace isolation verified: neither uv.lock contains switchboard platform dependencies (no sqlalchemy, fastapi, etc.)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create echo server package** - `ad1b18c` (feat)
2. **Task 2: Create ping server package** - `c387d95` (feat)

## Files Created/Modified
- `servers/echo/pyproject.toml` - Isolated package manifest with fastmcp dependency
- `servers/echo/server.py` - FastMCP echo tool (message: str -> str) with streamable-http transport
- `servers/echo/Dockerfile` - uv-based single-stage build, EXPOSE 8000
- `servers/echo/uv.lock` - Pinned dependency tree (fastmcp + transitive deps only)
- `servers/ping/pyproject.toml` - Isolated package manifest with fastmcp dependency
- `servers/ping/server.py` - Empty FastMCP instance (protocol ping is automatic)
- `servers/ping/Dockerfile` - uv-based single-stage build, EXPOSE 8000
- `servers/ping/uv.lock` - Pinned dependency tree (fastmcp + transitive deps only)

## Decisions Made
- **Hatchling build target config:** Added `[tool.hatch.build.targets.wheel] packages=["."]` to both pyproject.toml files. Hatchling could not auto-discover files for single-file packages (no `echo/` or `ping/` subdirectory). This tells hatchling to include the root directory contents in the wheel.
- **Single-stage Dockerfile:** Used single-stage build since these are dev/test targets. Multi-stage would add complexity without meaningful image size savings for reference servers.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added hatchling wheel build target configuration**
- **Found during:** Task 1 (echo server Docker build)
- **Issue:** `docker build` failed with `ValueError: Unable to determine which files to ship inside the wheel` because hatchling expects a directory matching the project name (e.g., `echo/`) but the server is a single file (`server.py`).
- **Fix:** Added `[tool.hatch.build.targets.wheel] packages = ["."]` to pyproject.toml, telling hatchling to include files from the current directory.
- **Files modified:** `servers/echo/pyproject.toml` (also applied proactively to `servers/ping/pyproject.toml`)
- **Verification:** Both Docker images build successfully after the fix.
- **Committed in:** ad1b18c (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Essential fix for Docker build to succeed. The plan's pyproject.toml template did not account for hatchling's file discovery behavior with single-file projects. No scope creep.

## Issues Encountered
None beyond the hatchling issue documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Both Docker images ready for docker-compose integration (Plan 04-02)
- Image names: `switchboard-echo`, `switchboard-ping`
- Both expose port 8000 via MCP Streamable HTTP transport at `/mcp` endpoint
- Ready for gateway routing tests in Phase 5 at `http://sb-echo:8000/mcp` and `http://sb-ping:8000/mcp`

## Self-Check: PASSED

All 9 files verified present. Both task commits (ad1b18c, c387d95) verified in git log.

---
*Phase: 04-reference-servers*
*Completed: 2026-04-16*
