# Phase 8: ECS Production Fixes - Research

**Researched:** 2026-04-21
**Domain:** ECS healthcheck alignment, Cloud Map service discovery, FastAPI route registration
**Confidence:** HIGH

## Summary

Phase 8 closes two production-blocking gaps identified by the v1.0 milestone audit: (1) the admin-api ECS task never reaches healthy state because it lacks a `GET /health` route, and (2) the health monitor cannot probe MCP server containers in ECS because it constructs hostnames without the Cloud Map domain suffix.

All four tasks are small, surgical fixes to existing code. No new libraries, database migrations, or architectural changes are needed. The primary risk is incomplete alignment -- three separate healthcheck definitions (Dockerfile, docker-compose.yml, services.tf) must agree, and the admin-api ECS task definition must receive the `CLOUD_MAP_DOMAIN` environment variable that it currently lacks.

**Primary recommendation:** Fix all four issues in a single plan with one task per fix, plus a fifth task adding `CLOUD_MAP_DOMAIN` to the admin-api task definition in services.tf (a hidden dependency the audit did not surface).

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PLAT-02 | Production deployment targets AWS ECS Fargate with one task per MCP server container | Tasks 1-3 fix the admin-api healthcheck that prevents ECS healthy state; Task 5 adds CLOUD_MAP_DOMAIN to admin-api task definition |
| CONT-04 | Platform periodically polls each server's health and exposes current health status via Admin API | Task 4 fixes the health monitor probe URL to include Cloud Map domain suffix; Task 5 ensures the env var is available at runtime |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Language:** Python 3.12+ -- all application code [VERIFIED: codebase inspection]
- **Package structure:** Top-level package is `switchboard/`, not `src/` [VERIFIED: codebase inspection]
- **Toolchain:** uv for package management, ruff for linting/formatting, pytest for testing [VERIFIED: CLAUDE.md]
- **Cloud:** AWS for production; local Docker Compose for development [VERIFIED: CLAUDE.md]
- **Auth:** OAuth/JWT -- no API-key-only auth [VERIFIED: CLAUDE.md]
- **TDD required:** Write test first (RED), then implement (GREEN), then refactor [VERIFIED: CLAUDE.md testing rules]
- **Type hints:** Required on all function signatures [VERIFIED: CLAUDE.md]
- **Docstrings:** Google-style on all public modules, classes, methods, functions [VERIFIED: CLAUDE.md]

## Standard Stack

No new dependencies are needed for this phase. All fixes use libraries already in the project.

### Relevant Existing Libraries
| Library | Version | Purpose in This Phase | Already Installed |
|---------|---------|----------------------|-------------------|
| FastAPI | 0.135.3 | Add `GET /health` route to admin-api | Yes [VERIFIED: codebase] |
| httpx | 0.28.1 | Health monitor HTTP probe (already used) | Yes [VERIFIED: codebase] |
| pydantic-settings | 2.13.1 | Read `cloud_map_domain` from Settings | Yes [VERIFIED: codebase] |
| pytest | 8.x | Test health endpoint and monitor fix | Yes [VERIFIED: codebase] |
| pytest-asyncio | 0.26.x | Async test support for monitor tests | Yes [VERIFIED: codebase] |
| respx | 0.22.x | Mock httpx for health monitor probe tests | Yes [VERIFIED: tests/gateway/test_proxy.py] |

## Architecture Patterns

### Current Admin API Structure
```
switchboard/admin/
  app.py        # FastAPI app factory, lifespan (health monitor startup)
  auth.py       # require_operator JWT dependency
  router.py     # /api/v1/* routes (all require JWT via router-level dependency)
```
[VERIFIED: codebase inspection]

### Pattern: Unauthenticated Health Route on the App, Not the Router

The admin router (`router.py`) applies `require_operator` at the router level via `dependencies=[Depends(require_operator)]`. Adding `/health` to this router would require auth -- defeating the purpose for ECS healthchecks.

The correct pattern is to register `/health` directly on the `app` object in `app.py`, outside the authenticated router. This mirrors how the gateway registers `/.well-known/oauth-protected-resource` directly on its app instance (`gateway/app.py` line 103). [VERIFIED: gateway/app.py line 103, admin/router.py line 37]

```python
# Source: switchboard/gateway/app.py:103 (existing pattern)
@app.get("/.well-known/oauth-protected-resource", include_in_schema=False)
async def oauth_protected_resource(request: Request) -> dict:
    ...
```

### Pattern: Cloud Map Domain Suffix in URL Construction

The gateway proxy already implements this correctly in `resolve_backend()`:

```python
# Source: switchboard/gateway/proxy.py:72 (existing pattern)
settings = get_settings()
domain_suffix = settings.cloud_map_domain
# ...
return f"http://sb-{server_name}{domain_suffix}:8000"
```

The health monitor must mirror this exact pattern in `_http_probe()`. [VERIFIED: gateway/proxy.py lines 71-74]

### Anti-Patterns to Avoid
- **Adding /health to the authenticated router:** Would require JWT, defeating ECS healthcheck purpose. Add to `app` directly. [VERIFIED: router.py line 37 -- router-level Depends(require_operator)]
- **Hardcoding Cloud Map domain in monitor.py:** Must read from `settings.cloud_map_domain` so the same code works in both Docker Compose (empty string) and ECS (`.switchboard.local`). [VERIFIED: config.py line 57]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Health endpoint | Custom middleware or ASGI handler | FastAPI `@app.get("/health")` decorator | FastAPI handles response serialization, status codes, OpenAPI exclusion |
| Settings injection | `os.environ.get("CLOUD_MAP_DOMAIN")` | `get_settings().cloud_map_domain` via pydantic-settings | Already configured, cached, validated -- consistent with rest of codebase |

## Common Pitfalls

### Pitfall 1: Missing CLOUD_MAP_DOMAIN in Admin-API Task Definition
**What goes wrong:** The health monitor fix reads `settings.cloud_map_domain` but the admin-api ECS task definition does not inject `CLOUD_MAP_DOMAIN`. In ECS, `cloud_map_domain` defaults to `""` and probes still fail.
**Why it happens:** The audit identified the code bug (missing suffix in URL) but did not trace through to the infrastructure: `CLOUD_MAP_DOMAIN` is only set in the gateway task definition (services.tf line 43), not in the admin-api task definition (services.tf lines 126-129).
**How to avoid:** Add `{ name = "CLOUD_MAP_DOMAIN", value = ".switchboard.local" }` to the admin-api task definition's `environment` block.
**Warning signs:** Health monitor probes still fail in ECS despite the code fix. [VERIFIED: services.tf lines 43 vs 126-129 -- CLOUD_MAP_DOMAIN present only in gateway]

### Pitfall 2: Dockerfile Healthcheck Still Points to /api/v1/servers
**What goes wrong:** The Dockerfile admin-api target (line 44) currently uses `GET /api/v1/servers` which returns 401. Even after adding `/health` to the app, the Dockerfile healthcheck is not used in ECS (ECS uses its own healthCheck from the task definition), but it IS used in local `docker build` testing and any non-Compose environments.
**Why it happens:** Dockerfile healthcheck was written before the auth middleware was added to the router; it was never updated.
**How to avoid:** Update Dockerfile line 44 to use `GET /health`.
**Warning signs:** `docker run` of the admin-api image shows container as unhealthy. [VERIFIED: Dockerfile line 44]

### Pitfall 3: docker-compose.yml Healthcheck Inconsistency
**What goes wrong:** docker-compose.yml uses TCP socket check for admin-api (line 87), which passes but doesn't validate application health. The other environments use HTTP checks.
**Why it happens:** TCP socket was a workaround because the HTTP healthcheck (`/api/v1/servers`) required auth.
**How to avoid:** Optionally update docker-compose.yml admin-api healthcheck to use `GET /health` for consistency, but this is not strictly required -- TCP check works. The planner should decide whether to include this.
**Warning signs:** docker-compose admin-api appears healthy even when the app crashes after TCP accept. [VERIFIED: docker-compose.yml lines 87-91]

### Pitfall 4: Settings Cache in Tests
**What goes wrong:** Tests that modify `CLOUD_MAP_DOMAIN` via monkeypatch must call `get_settings.cache_clear()` before AND after the test. If cleanup runs only at the end and the test fails mid-execution, the cache retains the test value.
**Why it happens:** `get_settings()` uses `@lru_cache`. The Phase 7 code review (07-REVIEW.md line 322) already flagged this pattern.
**How to avoid:** Use `monkeypatch` environment setup combined with settings cache clear in a try/finally or fixture teardown. The existing test in `test_proxy.py:115-144` shows the pattern. [VERIFIED: 07-REVIEW.md line 322, test_proxy.py lines 115-144]

### Pitfall 5: HealthMonitor Constructor Does Not Accept Settings
**What goes wrong:** The HealthMonitor `__init__` signature takes `session_factory`, `http_client`, and `poll_interval`. It does not take a `cloud_map_domain` parameter. The fix must either pass it via constructor or read settings inside `_http_probe`.
**Why it happens:** HealthMonitor was designed for Docker Compose where no domain suffix was needed.
**How to avoid:** Two options: (a) add `cloud_map_domain` to the constructor and pass from the lifespan, or (b) call `get_settings()` inside `_http_probe`. Option (a) is cleaner for testability -- allows tests to inject the value without monkeypatching environment variables. [VERIFIED: monitor.py lines 42-51]

## Code Examples

### Example 1: Health Endpoint (mirroring gateway's well-known endpoint pattern)
```python
# Source: switchboard/gateway/app.py:103 (existing pattern to mirror)
# Register on app directly, not on the authenticated router
@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}
```
[VERIFIED: gateway/app.py lines 103-118]

### Example 2: Cloud Map Domain in Health Monitor (mirroring proxy.py pattern)
```python
# Source: switchboard/gateway/proxy.py:71-74 (pattern to mirror)
# Current monitor.py line 140 (broken):
# url = f"http://{CONTAINER_NAME_PREFIX}{server_name}:8000/mcp"
#
# Fixed (mirrors proxy.py:72):
# url = f"http://{CONTAINER_NAME_PREFIX}{server_name}{self._cloud_map_domain}:8000/mcp"
```
[VERIFIED: proxy.py lines 71-74, monitor.py line 140]

### Example 3: Dockerfile Healthcheck Fix
```dockerfile
# Current (broken -- 401 from authenticated endpoint):
# HEALTHCHECK ... CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/servers')"
#
# Fixed:
HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=15s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
```
[VERIFIED: Dockerfile lines 43-44]

### Example 4: ECS Task Definition Healthcheck (already correct in services.tf)
```hcl
# Source: infra/modules/ecs/services.tf:140-148 (already points to /health)
healthCheck = {
  command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/health')\""]
  interval    = 10
  timeout     = 5
  retries     = 3
  startPeriod = 15
}
```
[VERIFIED: services.tf lines 140-148 -- already correct, needs the route to exist]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| TCP socket healthcheck | HTTP endpoint healthcheck | Phase 8 | Validates application health, not just port availability |
| Hardcoded Docker hostnames in monitor | Settings-driven hostname with Cloud Map suffix | Phase 8 | Health probes work in both Docker Compose and ECS |
| /api/v1/servers as healthcheck | /health unauthenticated endpoint | Phase 8 | Healthcheck not blocked by JWT auth |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | docker-compose.yml admin-api healthcheck should also be updated to use /health for consistency | Pitfall 3 | LOW -- TCP check works; only affects local consistency. Planner can decide. |
| A2 | Passing cloud_map_domain via HealthMonitor constructor is preferred over calling get_settings() inside _http_probe | Pitfall 5 | LOW -- either approach works. Constructor injection is more testable. |

## Open Questions

1. **Should docker-compose.yml admin-api healthcheck be updated?**
   - What we know: TCP socket check works. All three other definitions (gateway Dockerfile, gateway docker-compose, gateway services.tf) use HTTP. Admin-api docker-compose uses TCP.
   - What's unclear: Whether consistency matters enough to change a working check.
   - Recommendation: Update for consistency. The /health endpoint will exist; use it everywhere. [ASSUMED]

2. **Should HealthMonitor accept cloud_map_domain via constructor or read from settings?**
   - What we know: Constructor injection is more testable. The lifespan function in `admin/app.py` already reads settings and passes values to the HealthMonitor constructor.
   - What's unclear: Whether the team prefers minimal constructor changes.
   - Recommendation: Add `cloud_map_domain` parameter to constructor, pass from lifespan. Matches existing pattern of explicit dependency injection in this class. [ASSUMED]

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.26.x |
| Config file | `pyproject.toml` [tool.pytest] section |
| Quick run command | `uv run pytest tests/admin/test_health_route.py tests/health/test_monitor.py -x -q` |
| Full suite command | `uv run pytest -x -q` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PLAT-02-a | GET /health returns 200 with {"status": "ok"} unauthenticated | unit | `uv run pytest tests/admin/test_health_route.py::TestHealthEndpoint::test_health_returns_200_ok -x` | No -- Wave 0 |
| PLAT-02-b | GET /health returns 200 without Authorization header | unit | `uv run pytest tests/admin/test_health_route.py::TestHealthEndpoint::test_health_no_auth_required -x` | No -- Wave 0 |
| CONT-04-a | _http_probe uses cloud_map_domain suffix in URL | unit | `uv run pytest tests/health/test_monitor.py::TestHttpProbe::test_http_probe_uses_cloud_map_domain -x` | No -- Wave 0 |
| CONT-04-b | _http_probe works with empty cloud_map_domain (local dev) | unit | `uv run pytest tests/health/test_monitor.py::TestHttpProbe::test_http_probe_no_domain_suffix_local -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/admin/test_health_route.py tests/health/test_monitor.py -x -q`
- **Per wave merge:** `uv run pytest -x -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/admin/test_health_route.py` -- covers PLAT-02 health endpoint
- [ ] `tests/health/test_monitor.py` -- extends existing file with cloud_map_domain probe tests for CONT-04

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Yes | /health endpoint is intentionally unauthenticated -- must NOT leak sensitive data |
| V3 Session Management | No | N/A |
| V4 Access Control | Yes | /health must be registered outside the authenticated router to bypass JWT |
| V5 Input Validation | No | /health takes no input |
| V6 Cryptography | No | N/A |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Health endpoint information disclosure | Information Disclosure | Return only `{"status": "ok"}` -- no version, config, or debug info |
| Health endpoint as DDoS amplifier | Denial of Service | Minimal response body; no database queries; ECS ALB rate-limits at infrastructure level |
| Health endpoint accessible externally | Information Disclosure | Admin-api is internal-only (not registered with ALB per services.tf line 157); security groups restrict access [VERIFIED: services.tf lines 157-177] |

## Environment Availability

> Step 2.6: No new external dependencies identified. All fixes target existing code and Terraform config. No new tools, runtimes, or services required.

## Sources

### Primary (HIGH confidence)
- Codebase inspection: `switchboard/admin/app.py`, `switchboard/admin/router.py`, `switchboard/health/monitor.py`, `switchboard/gateway/proxy.py`, `switchboard/config.py` -- all source files read and analyzed
- Codebase inspection: `Dockerfile`, `docker-compose.yml`, `infra/modules/ecs/services.tf` -- all infrastructure files read and analyzed
- Codebase inspection: `tests/health/test_monitor.py`, `tests/admin/test_health_endpoint.py`, `tests/admin/conftest.py`, `tests/health/conftest.py` -- all relevant test files read
- `.planning/v1.0-MILESTONE-AUDIT.md` -- source of gap identification with specific line references

### Secondary (MEDIUM confidence)
- `.planning/phases/07-aws-deployment/07-REVIEW.md` -- settings cache cleanup concern (line 322)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries; all existing code verified
- Architecture: HIGH -- patterns directly observed in codebase (gateway/app.py, gateway/proxy.py)
- Pitfalls: HIGH -- every pitfall verified against specific file and line references
- Hidden dependency (CLOUD_MAP_DOMAIN in admin-api task): HIGH -- verified by grep showing it exists only in gateway task definition

**Research date:** 2026-04-21
**Valid until:** 2026-05-21 (stable -- fixes to existing, well-understood codebase)
