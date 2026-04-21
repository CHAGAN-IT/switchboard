---
phase: 08-ecs-production-fixes
plan: 01
subsystem: infra
tags: [ecs, healthcheck, cloud-map, fastapi, docker, terraform]

# Dependency graph
requires:
  - phase: 06-health-monitor
    provides: HealthMonitor class with HTTP probe and state machine
  - phase: 07-aws-deployment
    provides: ECS task definitions, Dockerfile targets, docker-compose topology
provides:
  - Unauthenticated GET /health endpoint on admin-api
  - Cloud Map domain suffix support in HealthMonitor._http_probe
  - CLOUD_MAP_DOMAIN env var in admin-api ECS task definition
  - Aligned healthcheck definitions across Dockerfile, docker-compose.yml, and services.tf
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Unauthenticated health endpoints registered directly on FastAPI app, not on authenticated router"
    - "Cloud Map domain suffix passed via constructor param with empty-string default for local dev"

key-files:
  created:
    - tests/admin/test_health_route.py
  modified:
    - switchboard/admin/app.py
    - switchboard/health/monitor.py
    - infra/modules/ecs/services.tf
    - Dockerfile
    - docker-compose.yml

key-decisions:
  - "Health endpoint on app object (not router) to bypass JWT dependency chain"
  - "cloud_map_domain as constructor param rather than reading settings inside _http_probe"

patterns-established:
  - "Health endpoints use include_in_schema=False to stay out of OpenAPI docs"

requirements-completed: [PLAT-02, CONT-04]

# Metrics
duration: 6min
completed: 2026-04-21
---

# Phase 08 Plan 01: ECS Production Fixes Summary

**Unauthenticated /health endpoint for ECS healthcheck + Cloud Map domain suffix in health monitor probe URLs, with aligned healthcheck definitions across Dockerfile, docker-compose.yml, and Terraform**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-21T13:30:16Z
- **Completed:** 2026-04-21T13:36:33Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments

- Added GET /health on admin-api returning `{"status": "ok"}` without JWT auth, fixing the ECS container healthcheck 401 loop
- Added `cloud_map_domain` parameter to HealthMonitor so probe URLs resolve correctly in both ECS (`.switchboard.local` suffix) and local Docker Compose (empty suffix)
- Added `CLOUD_MAP_DOMAIN` environment variable to admin-api ECS task definition (was missing, only gateway had it)
- Fixed Dockerfile admin-api HEALTHCHECK from `/api/v1/servers` (requires JWT) to `/health` (unauthenticated)
- Fixed docker-compose.yml admin-api healthcheck from TCP socket check to HTTP GET `/health`

## Task Commits

Each task was committed atomically:

1. **Task 1: Wave 0 test stubs and /health endpoint (TDD RED then GREEN)** - `7b258b7` (feat)
2. **Task 2: Health monitor Cloud Map fix with TDD + infra alignment** - `f2adbd2` (fix)
3. **Task 3: Full test suite regression check** - `a3ecf5d` (chore)

## Files Created/Modified

- `tests/admin/test_health_route.py` - 3 unit tests for unauthenticated /health endpoint (TestHealthEndpoint)
- `switchboard/admin/app.py` - Added /health route on app object + cloud_map_domain in HealthMonitor constructor call
- `switchboard/health/monitor.py` - Added cloud_map_domain param to __init__ and _http_probe URL construction
- `tests/health/test_monitor.py` - Added 2 tests for cloud_map_domain in _http_probe (ECS + local)
- `infra/modules/ecs/services.tf` - Added CLOUD_MAP_DOMAIN to admin-api task definition environment block
- `Dockerfile` - Changed admin-api HEALTHCHECK from /api/v1/servers to /health
- `docker-compose.yml` - Changed admin-api healthcheck from TCP socket to HTTP /health

## Decisions Made

- Health endpoint registered on `app` (not `router`) to bypass the JWT `dependencies=[Depends(require_operator)]` on the router -- mirrors the gateway's `.well-known` endpoint pattern
- `cloud_map_domain` passed as constructor parameter to HealthMonitor rather than reading `get_settings()` inside `_http_probe` -- keeps the monitor testable and consistent with how the gateway proxy already handles the domain suffix

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed ruff lint and format issues in test_health_route.py**
- **Found during:** Task 3
- **Issue:** Unused `import pytest` (F401) and line-too-long docstring (E501) in the test file created in Task 1
- **Fix:** Removed unused import, shortened docstring, ran ruff format
- **Files modified:** tests/admin/test_health_route.py
- **Verification:** `uv run ruff check` and `uv run ruff format --check` pass
- **Committed in:** a3ecf5d (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug)
**Impact on plan:** Minor lint fix, no scope creep.

## Issues Encountered

- Full test suite cannot run in worktree environment due to pre-existing issues: (1) no PostgreSQL database running (ConnectionRefusedError on port 5432), (2) SOCKS proxy in environment causes `gateway_client` fixture to fail with `ImportError: socksio not installed`. Both are pre-existing infrastructure/environment issues, not caused by this plan's changes. All 105 unit tests that do not require DB or gateway_client pass cleanly.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Admin-api ECS task will now reach healthy state with the `/health` endpoint
- Health monitor will correctly probe MCP servers in ECS via Cloud Map DNS names
- All healthcheck definitions are aligned across Dockerfile, docker-compose.yml, and services.tf

## Self-Check: PASSED

All 8 files verified present. All 3 task commits verified in git log.

---
*Phase: 08-ecs-production-fixes*
*Completed: 2026-04-21*
