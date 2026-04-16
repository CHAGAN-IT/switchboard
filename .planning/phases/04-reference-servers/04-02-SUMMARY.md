---
phase: 04-reference-servers
plan: 02
subsystem: testing
tags: [docker-compose, mcp, integration-tests, pytest, reference-servers, streamable-http]

# Dependency graph
requires:
  - phase: 04-reference-servers/01
    provides: echo and ping MCP server packages (servers/echo, servers/ping) with Dockerfiles
  - phase: 03-container-manager
    provides: ContainerManager class for start/stop/restart lifecycle
provides:
  - docker-compose.yml with echo and ping build services on switchboard-internal network
  - integration test suite validating REFS-01 (echo), REFS-02 (ping), SC-4 (ContainerManager lifecycle)
  - pytest reference_servers marker for selective test execution
  - mcp SDK dev dependency for MCP client-based testing
affects: [05-gateway, phase-transition]

# Tech tracking
tech-stack:
  added: [mcp 1.27.0 (dev dependency for test client)]
  patterns: [retry-based container health check with stdlib urllib, session-scoped Docker container fixtures with ephemeral host ports, MCP streamable HTTP client test pattern]

key-files:
  created:
    - tests/reference_servers/__init__.py
    - tests/reference_servers/conftest.py
    - tests/reference_servers/test_reference_servers.py
  modified:
    - docker-compose.yml
    - pyproject.toml
    - uv.lock

key-decisions:
  - "Replaced static sleep with retry-based health check using stdlib urllib.request for container readiness"
  - "Used test-specific container names (sb-echo-test, sb-ping-test) to avoid collision with docker-compose production containers"
  - "Suppressed SIM117 lint rule for dependent async context managers (streamable_http_client yields values consumed by ClientSession)"

patterns-established:
  - "MCP client test pattern: streamable_http_client(url) -> ClientSession -> call_tool/send_ping for integration testing"
  - "Docker container fixture pattern: session-scoped, ephemeral host port, retry-based health check, cleanup on teardown"
  - "Reference server image convention: build with docker compose -p switchboard build; test container names use -test suffix"

requirements-completed: [REFS-01, REFS-02]

# Metrics
duration: 7min
completed: 2026-04-16
---

# Phase 04 Plan 02: Docker Compose Integration and Reference Server Tests Summary

**Echo and ping MCP servers wired into Docker Compose with 4 passing integration tests validating REFS-01, REFS-02, and SC-4 via real MCP Streamable HTTP client connections**

## Performance

- **Duration:** 7 min
- **Started:** 2026-04-16T14:30:06Z
- **Completed:** 2026-04-16T14:37:48Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Added echo and ping build services to docker-compose.yml with no host ports, container names sb-echo/sb-ping, stdlib urllib healthchecks, and switchboard-internal network
- Created integration test suite with session-scoped Docker container fixtures using ephemeral host ports and retry-based health checks
- All 4 tests pass: REFS-01 (echo returns input unchanged), REFS-01 edge case, REFS-02 (ping responds to MCP ping), SC-4 (ContainerManager lifecycle)
- Added mcp>=1.27.0 dev dependency and reference_servers pytest marker

## Task Commits

Each task was committed atomically:

1. **Task 1: Add echo/ping services to docker-compose.yml and root pyproject.toml** - `c401ed9` (feat)
2. **Task 2 RED: Write reference server integration tests** - `fbf4983` (test)
3. **Task 2 GREEN: Tests pass with health check improvements** - `4ca166b` (feat)
4. **Lockfile update for mcp dependency** - `3d62c48` (chore)

_Note: TDD task had RED/GREEN commits as expected._

## Files Created/Modified
- `docker-compose.yml` - Added echo and ping build services with no host ports, container names sb-echo/sb-ping, stdlib urllib healthchecks, switchboard-internal network
- `pyproject.toml` - Added mcp>=1.27.0 to dev dependencies, reference_servers pytest marker
- `uv.lock` - Updated lockfile with mcp dependency tree (313 new lines)
- `tests/reference_servers/__init__.py` - Package marker (empty)
- `tests/reference_servers/conftest.py` - Session-scoped Docker container fixtures (echo_server_url, ping_server_url) with ephemeral host ports and retry-based health checks
- `tests/reference_servers/test_reference_servers.py` - REFS-01 echo test, REFS-01 edge case, REFS-02 ping test, SC-4 ContainerManager lifecycle test

## Decisions Made
- **Retry-based health check:** Replaced the plan's static 3-second sleep with a `_wait_for_healthy()` function that polls the MCP endpoint via stdlib urllib.request. The container runs `uv sync` on startup which can take 5+ seconds on cold start. Retries up to 30 times at 1-second intervals.
- **SIM117 suppression:** The ruff SIM117 rule (combine nested with statements) was suppressed on MCP client test code because `ClientSession(read, write)` depends on values yielded by the outer `streamable_http_client()` context manager -- they cannot be combined.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Replaced static sleep with retry-based health check**
- **Found during:** Task 2 (GREEN phase -- tests failing with httpx.ReadError)
- **Issue:** The plan specified `_STARTUP_WAIT_SECONDS: int = 3` but containers running `uv sync` on startup need 5-8 seconds to become healthy
- **Fix:** Added `_wait_for_healthy()` function using stdlib urllib.request to poll the MCP endpoint with retries (30 attempts, 1s interval)
- **Files modified:** tests/reference_servers/conftest.py
- **Verification:** All 4 tests pass consistently (20s total including container startup)
- **Committed in:** 4ca166b (GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Auto-fix was necessary for test reliability. The plan's static sleep was insufficient for container startup time. No scope creep.

## Issues Encountered
- Docker Compose image naming in worktrees uses directory name as prefix (e.g., `agent-a02e497f-echo` instead of `switchboard-echo`). Resolved by building with `-p switchboard` project name flag: `docker compose -p switchboard build echo ping`

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 4 (Reference Servers) is complete: both echo and ping servers are packaged, containerized, wired into Docker Compose, and validated with integration tests
- Ready for Phase 5 (Gateway): validated MCP test targets are available for routing tests via `docker compose -p switchboard build echo ping && uv run pytest tests/reference_servers/ -m reference_servers`
- Gateway can reach echo/ping containers via switchboard-internal network (container names sb-echo, sb-ping, port 8000)

## Self-Check: PASSED

All 7 files verified present. All 4 commit hashes verified in git log.

---
*Phase: 04-reference-servers*
*Completed: 2026-04-16*
