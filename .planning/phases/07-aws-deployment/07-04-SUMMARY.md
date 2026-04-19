---
phase: 07-aws-deployment
plan: 04
subsystem: infra
tags: [boto3, ecs, aws, cloud-map, asyncio, container-manager]

# Dependency graph
requires:
  - phase: 03-container-manager
    provides: ContainerManager with Docker SDK lifecycle operations
  - phase: 05-gateway
    provides: Gateway proxy with resolve_backend DNS routing
provides:
  - ECSAdapter class wrapping boto3 ECS service API calls
  - ECS environment detection via ECS_CONTAINER_METADATA_URI
  - ContainerManager ECS/Docker dispatch based on runtime environment
  - Cloud Map DNS suffix support in gateway proxy resolve_backend
  - Settings fields for aws_region, ecs_cluster_arn, cloud_map_domain
affects: [07-aws-deployment, deployment, container-manager, gateway]

# Tech tracking
tech-stack:
  added: [boto3, botocore]
  patterns: [ECS adapter pattern, environment-based dispatch, asyncio.to_thread for boto3]

key-files:
  created:
    - switchboard/container/ecs_adapter.py
    - tests/container/test_ecs_adapter.py
    - tests/test_config_ecs.py
  modified:
    - switchboard/container/manager.py
    - switchboard/config.py
    - switchboard/gateway/proxy.py
    - tests/container/test_manager.py
    - tests/gateway/test_proxy.py
    - pyproject.toml
    - uv.lock

key-decisions:
  - "ECS adapter creates a fresh boto3 client per call with try/finally close, matching Docker SDK pattern"
  - "ECS environment detection uses ECS_CONTAINER_METADATA_URI presence (injected by Fargate platform)"
  - "ContainerManager accepts optional ecs_adapter constructor parameter for test dependency injection"
  - "Cloud Map domain suffix appended in resolve_backend, empty string for local dev (zero behavior change)"

patterns-established:
  - "ECS adapter pattern: blocking boto3 calls wrapped in asyncio.to_thread with per-call client lifecycle"
  - "Environment dispatch: _is_ecs_environment() check at method entry to route Docker vs ECS paths"

requirements-completed: [PLAT-02]

# Metrics
duration: 7min
completed: 2026-04-19
---

# Phase 07 Plan 04: ECS Adapter Summary

**ECS adapter with boto3 start/stop/restart via update_service, ContainerManager ECS/Docker dispatch, and Cloud Map DNS suffix in gateway proxy**

## Performance

- **Duration:** 7 min
- **Started:** 2026-04-19T15:34:24Z
- **Completed:** 2026-04-19T15:41:40Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments
- Created ECSAdapter class wrapping boto3 ECS update_service for start (desiredCount=1), stop (desiredCount=0), and restart (forceNewDeployment=True)
- Integrated ECS adapter into ContainerManager with environment-based dispatch preserving existing Docker SDK workflow
- Updated gateway proxy resolve_backend to append Cloud Map domain suffix for ECS service discovery
- Added aws_region, ecs_cluster_arn, cloud_map_domain fields to Settings with empty-string defaults
- Full TDD coverage: 22 new tests across 3 test files, all 119 unit tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Add boto3 dependency, create ECS adapter with TDD, update config** - `7076f5a` (feat)
2. **Task 2: Integrate ECS adapter into ContainerManager and update gateway proxy** - `e2e0d07` (feat)

_Both tasks followed TDD: tests written first (RED), implementation to pass (GREEN), then lint cleanup._

## Files Created/Modified
- `switchboard/container/ecs_adapter.py` - ECSAdapter class with start/stop/restart and _is_ecs_environment detection
- `switchboard/container/manager.py` - ContainerManager with ECS/Docker dispatch via _start_ecs/_stop_ecs/_restart_ecs
- `switchboard/config.py` - Settings with aws_region, ecs_cluster_arn, cloud_map_domain fields
- `switchboard/gateway/proxy.py` - resolve_backend appends cloud_map_domain suffix
- `tests/container/test_ecs_adapter.py` - 16 tests for ECS adapter (env detection, CRUD, lifecycle, threading, errors)
- `tests/container/test_manager.py` - 4 new tests for ECS dispatch routing
- `tests/gateway/test_proxy.py` - 2 new tests for Cloud Map domain suffix behavior
- `tests/test_config_ecs.py` - 2 tests for Settings ECS field defaults and values
- `pyproject.toml` - Added boto3 dependency
- `uv.lock` - Updated lockfile with boto3/botocore/s3transfer/jmespath

## Decisions Made
- ECS adapter creates fresh boto3 client per call with try/finally close to avoid resource leaks (T-7-18), matching the Docker SDK pattern in _start_blocking
- ECS environment detection uses ECS_CONTAINER_METADATA_URI (injected by Fargate platform 1.4.0+) rather than a configuration flag, because it is guaranteed present in ECS and absent locally
- ContainerManager constructor accepts optional ecs_adapter parameter for dependency injection in tests, avoiding the need to mock get_settings in dispatch tests
- Cloud Map domain suffix defaults to empty string, so existing Docker Compose URLs (http://sb-echo:8000) are unchanged without any configuration

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Integration tests requiring PostgreSQL (tests/admin/) skip in the worktree environment because no database is available; this is pre-existing and expected. All 119 unit tests pass without regressions.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- ECS adapter is ready for CDK infrastructure integration (07-01, 07-02, 07-03 plans)
- ContainerManager seamlessly switches between Docker and ECS based on runtime environment
- Gateway proxy automatically uses Cloud Map DNS when cloud_map_domain is configured

## Self-Check: PASSED

All created files exist. All commit hashes verified in git log.

---
*Phase: 07-aws-deployment*
*Completed: 2026-04-19*
