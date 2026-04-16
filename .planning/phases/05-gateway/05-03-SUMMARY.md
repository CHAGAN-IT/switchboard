---
phase: 05-gateway
plan: 03
subsystem: docker
tags: [docker, docker-compose, dockerfile, gateway, admin-api, plat-01]

# Dependency graph
requires:
  - phase: 05-gateway/05-02
    provides: switchboard/gateway/app.py (gateway uvicorn entrypoint), switchboard/admin/app.py (admin-api entrypoint)
  - phase: 01-foundation
    provides: pyproject.toml, uv.lock, servers/echo/Dockerfile pattern
provides:
  - Dockerfile with gateway and admin-api multi-stage build targets
  - docker-compose.yml gateway service on port 8080:8000 with healthchecks
  - docker-compose.yml admin-api service on port 8090:8000 with healthchecks
  - .env.example with CUSTOMER_JWT_SECRET and OPERATOR_JWT_SECRET documentation
affects:
  - 07-aws: Dockerfile pattern is the ECS container image source

# Tech tracking
tech-stack:
  added: []  # No new Python dependencies — this plan is infrastructure-only
  patterns:
    - Multi-stage Dockerfile: shared base layer with --no-dev uv sync, then per-service FROM base AS <target>
    - docker-compose gateway depends_on with condition: service_healthy for ordered startup
    - Secret injection via ${ENV_VAR} expansion (not hardcoded in docker-compose.yml)

key-files:
  created:
    - Dockerfile
  modified:
    - docker-compose.yml (added gateway and admin-api services)
    - .env.example (added CUSTOMER_JWT_SECRET entry)

key-decisions:
  - "Gateway service does not include DATABASE_URL — gateway is stateless per CONTEXT.md D-08; only CUSTOMER_JWT_SECRET and OPERATOR_JWT_SECRET are required"
  - "TLS termination for customer-facing gateway traffic deferred to Phase 7 (AWS ALB); port 8080 is plain HTTP for local dev"
  - "echo and ping services have no ports: mapping — only accessible on switchboard-internal; only gateway (8080) and admin-api (8090) are host-accessible (mitigates T-5-14)"

patterns-established:
  - "Pattern 5: Multi-target root Dockerfile — single Dockerfile, multiple FROM base AS <target> stages; docker-compose.yml references target: gateway or target: admin-api"

requirements-completed:
  - GTWY-01
  - GTWY-02
  - GTWY-03
  - SECU-01
  - PLAT-01

# Metrics
duration: 15min
completed: 2026-04-16
---

# Phase 5 Plan 03: Docker Compose Topology Summary

**Root Dockerfile with gateway/admin-api multi-stage build targets, docker-compose.yml extended with gateway (8080) and admin-api (8090) services, and .env.example updated — awaiting human verification of full stack startup.**

## Performance

- **Duration:** ~15 min (Task 1 complete; Task 2 pending human verification)
- **Started:** 2026-04-16T19:16:00Z
- **Completed:** 2026-04-16T19:31:00Z (Task 1); Task 2 pending
- **Tasks:** 1 of 2 complete
- **Files modified:** 3

## Accomplishments

- Created `/home/chagan/development/switchboard/Dockerfile` with shared `base` layer and two named build targets: `gateway` (runs `uvicorn switchboard.gateway.app:app`) and `admin-api` (runs `uvicorn switchboard.admin.app:app`)
- Extended `docker-compose.yml` with `gateway` service (port 8080:8000, depends on db+echo+ping healthy, secrets injected from host environment)
- Extended `docker-compose.yml` with `admin-api` service (port 8090:8000, depends on db healthy, DATABASE_URL and OPERATOR_JWT_SECRET from environment)
- Updated `.env.example` with `CUSTOMER_JWT_SECRET` and generation instructions
- Threat mitigations T-5-12 through T-5-15 applied: no hardcoded secrets, `.env` in `.gitignore`, backend containers have no host ports, gateway fails-fast on missing CUSTOMER_JWT_SECRET

## Task Commits

Each task was committed atomically:

1. **Task 1: Dockerfile + docker-compose.yml + .env.example** - `7f252b1` (feat)
2. **Task 2: Human verification** - PENDING CHECKPOINT

## Files Created/Modified

- `Dockerfile` - New: multi-stage Dockerfile with `base`, `gateway`, and `admin-api` build targets
- `docker-compose.yml` - Added gateway service (8080:8000) and admin-api service (8090:8000)
- `.env.example` - Added CUSTOMER_JWT_SECRET with placeholder value and generation instructions

## Decisions Made

- **Gateway is stateless (no DATABASE_URL):** Per CONTEXT.md D-08, the gateway does not interact with the database directly. Only CUSTOMER_JWT_SECRET (required) and OPERATOR_JWT_SECRET (passed through but not used by gateway) are provided. This keeps the gateway container minimal.
- **TLS deferred to Phase 7:** Port 8080 is plain HTTP for local development. The AWS ALB in Phase 7 handles TLS termination at the edge. This is the correct and expected behavior for local dev.
- **Backend containers not exposed:** echo and ping have no `ports:` mapping — they are only reachable on `switchboard-internal` network. This mitigates T-5-14 (elevation of privilege via exposed backend ports).

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None — all files are complete infrastructure configuration. No placeholder values in the gateway or admin-api service definitions (secrets come from environment).

## Threat Flags

No new security surface introduced beyond what is documented in the plan's threat model. All mitigations applied:

| Threat ID | Mitigation |
|-----------|------------|
| T-5-12 | Secrets injected via `${ENV_VAR}` expansion — not hardcoded in docker-compose.yml |
| T-5-13 | `.env` confirmed in `.gitignore` (line 13); `.env.example` is placeholder-only |
| T-5-14 | echo and ping have no `ports:` mapping — only accessible on switchboard-internal |
| T-5-15 | Settings.customer_jwt_secret validator raises ValueError at import — container fails fast on missing secret |

## Deferred Issues

Pre-existing test failures (not caused by this plan's changes):
- `tests/gateway/test_logging.py` — 5 tests fail on base branch due to structlog capture issue. These failures existed before Plan 03 and are unrelated to docker-compose/Dockerfile changes.

Pre-existing ruff lint issues (not in files modified by this plan):
- `switchboard/config.py` — E501 on lines 46, 58, 66 (line too long in docstrings)
- `tests/registry/test_validation.py` — I001 unsorted imports

---
*Phase: 05-gateway*
*Completed: 2026-04-16 (Task 1 of 2; checkpoint pending)*

## Self-Check: PASSED

Files verified:
- Dockerfile — FOUND
- docker-compose.yml — FOUND (modified)
- .env.example — FOUND (modified)
- .planning/phases/05-gateway/05-03-SUMMARY.md — FOUND

Commits verified:
- 7f252b1 — Task 1 commit (feat(05-03): add Dockerfile and extend docker-compose with gateway+admin-api)
