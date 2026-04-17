---
phase: 05-gateway
verified: 2026-04-16T22:00:18Z
status: human_needed
score: 6/7 must-haves verified
overrides_applied: 0
deferred:
  - truth: "Gateway terminates TLS for all customer-facing traffic"
    addressed_in: "Phase 7"
    evidence: "Phase 7 goal: 'TLS termination at the ALB'; Phase 7 SC-2: 'Customer MCP requests over HTTPS to the ALB DNS name are correctly routed'"
human_verification:
  - test: "docker compose up — run full stack and verify all 5 services healthy"
    expected: "All 5 services (db, echo, ping, gateway, admin-api) show healthy status; GET /.well-known/oauth-protected-resource returns JSON with 'resource' key; unauthenticated POST returns 401; authenticated POST returns non-401/non-503"
    why_human: "Cannot start Docker services in CI/automated context; SUMMARY documents this was done but automated re-verification cannot exercise docker compose"
---

# Phase 5: Gateway Verification Report

**Phase Goal:** A customer holding a valid JWT can send MCP requests to `/servers/{server-name}/mcp` and have them transparently proxied to the correct running container, with the complete local topology running under Docker Compose.
**Verified:** 2026-04-16T22:00:18Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | MCP client hitting `/servers/echo/mcp` with valid JWT is proxied; no JWT returns 401 with WWW-Authenticate | VERIFIED | `test_post_proxied` + `test_missing_jwt_returns_401` pass; `require_customer` raises 401 with `WWW-Authenticate: Bearer` header on all invalid token cases |
| 2 | Both POST and GET on `/mcp` are proxied correctly | VERIFIED | `test_post_proxied` and `test_get_sse_proxied` pass; `proxy.py` uses `router.api_route(..., methods=["GET", "POST"])` with `stream=True` |
| 3 | Second request with same `Mcp-Session-Id` routes to same container instance | VERIFIED | `test_session_affinity_routes_to_same_backend` + `test_first_request_records_session` pass; `_session_map + _session_lock` implementation confirmed in `proxy.py` |
| 4 | Authorization header stripped before forwarding to backend containers | VERIFIED | `test_authorization_header_stripped` passes; `proxy.py` line 120: `k.lower() not in ("authorization", "host")` dict comprehension confirmed |
| 5 | GET `/.well-known/oauth-protected-resource` returns valid RFC 9728 document | VERIFIED | `test_oauth_resource_metadata_returns_resource_field` + `test_bearer_methods_supported_field_present` pass; `app.py` implements endpoint returning `{"resource": ..., "bearer_methods_supported": ["header"]}` |
| 6 | Each proxied request produces structured JSON log with trace_id, user identity, server name, HTTP status, timestamp | VERIFIED | All 5 `test_log_*` tests pass; `structlog.contextvars` bind trace_id+http_method in middleware; user_identity+server_name+http_status bound in `proxy_mcp_request` handler |
| 7 | `docker compose up` starts all services with health checks passing | HUMAN NEEDED | 05-03-SUMMARY documents "all 5 services healthy, auth flows confirmed" but automated re-verification cannot run Docker Compose |

**Score:** 6/7 truths verified (1 requires human re-validation)

### Deferred Items

Items not yet met but explicitly addressed in later milestone phases.

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | TLS termination for customer-facing gateway traffic (SECU-02 clause 1) | Phase 7 | Phase 7 goal: "TLS termination at the ALB"; SC-2: "Customer MCP requests over HTTPS to the ALB DNS name are correctly routed" |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `switchboard/gateway/auth.py` | `require_customer` FastAPI dependency | VERIFIED | 68 lines; substantive HS256 JWT validation with audience="switchboard-gateway", mandatory exp/iat/sub claims, 401+WWW-Authenticate on failure |
| `switchboard/config.py` | Settings with `customer_jwt_secret` field | VERIFIED | `customer_jwt_secret: str = ""` at line 54; `validate_customer_jwt_secret_length` validator at line 56; optional (validates length if set; gateway does startup check) |
| `switchboard/gateway/proxy.py` | Streaming MCP proxy handler | VERIFIED | 151 lines; `proxy_mcp_request` + `resolve_backend` + `_session_map/_session_lock`; streaming via `send(stream=True)` + `BackgroundTask(aclose)` |
| `switchboard/gateway/app.py` | FastAPI gateway app with lifespan/middleware/routes | VERIFIED | 118 lines; `lifespan` (httpx.AsyncClient), `RequestLogMiddleware`, `include_router(router)`, `oauth_protected_resource` endpoint |
| `tests/gateway/conftest.py` | `make_customer_token` helper + `gateway_client` fixture | VERIFIED | Both present; `gateway_client` uses monkeypatch to set secrets and clears settings cache |
| `tests/gateway/test_auth.py` | 6 auth unit tests (401 paths + acceptance) | VERIFIED | 6 tests present and passing via minimal FastAPI TestClient pattern |
| `Dockerfile` | Multi-target Dockerfile with gateway + admin-api targets | VERIFIED | `FROM base AS gateway` and `FROM base AS admin-api` targets; CMD runs `switchboard.gateway.app:app` and `switchboard.admin.app:app` respectively |
| `docker-compose.yml` | Gateway service on 8080:8000 with switchboard-internal network | VERIFIED | gateway service present, port 8080:8000, `switchboard-internal` network, `CUSTOMER_JWT_SECRET` env var, depends_on db+echo+ping healthy |
| `.env.example` | Documents CUSTOMER_JWT_SECRET | VERIFIED | Contains `CUSTOMER_JWT_SECRET=change-me-customer-secret-min-32bytes` with generation instructions |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `gateway/auth.py` | `switchboard/config.py` | `Depends(get_settings)` + `settings.customer_jwt_secret` | VERIFIED | `customer_jwt_secret` used in `jwt.decode()` call at line 50 |
| `tests/conftest.py` | `switchboard/config.py` | `os.environ.setdefault("CUSTOMER_JWT_SECRET", ...)` | VERIFIED | Line 25 in `tests/conftest.py` sets default test value |
| `gateway/app.py` | `gateway/proxy.py` | `app.include_router(router)` | VERIFIED | `from switchboard.gateway.proxy import router` + `app.include_router(router)` at line 100 |
| `gateway/app.py` | `gateway/auth.py` | `Depends(require_customer)` in proxy route | VERIFIED | `proxy_mcp_request` takes `Annotated[dict, Depends(require_customer)]` parameter |
| `gateway/proxy.py` | `httpx.AsyncClient` | `request.app.state.http_client` | VERIFIED | `http_client: httpx.AsyncClient = request.app.state.http_client` at line 123 |
| `gateway/app.py` | `structlog` | `RequestLogMiddleware` + `structlog.contextvars` | VERIFIED | Middleware clears+binds trace_id/http_method; proxy handler binds user_identity/server_name and emits `proxied_request` event |
| `docker-compose.yml gateway service` | `switchboard-internal network` | `networks: [switchboard-internal]` | VERIFIED | Gateway service joins `switchboard-internal`; echo/ping also on same network; 5 occurrences of `switchboard-internal` in file |
| `docker-compose.yml gateway service` | `Dockerfile` | `build: context: . target: gateway` | VERIFIED | `target: gateway` in gateway service build config |

### Data-Flow Trace (Level 4)

The gateway is a proxy — it does not render stored data but forwards live HTTP streams. Data flow is request → JWT decode → backend forward → stream response. No static/empty data patterns found.

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `proxy.py` `proxy_mcp_request` | `rp_resp` (streaming backend response) | `http_client.send(rp_req, stream=True)` | Yes — live HTTP response from backend | FLOWING |
| `proxy.py` `resolve_backend` | `_session_map[session_id]` | Module-level dict, populated on first request | Yes — real URL computed from server_name | FLOWING |
| `auth.py` `require_customer` | JWT `payload` dict | `jwt.decode()` from Bearer token | Yes — decoded from actual token | FLOWING |
| `app.py` `oauth_protected_resource` | `base_url` | `str(request.base_url)` | Yes — derived from live request | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Gateway proxy module imports | `uv run python -c "from switchboard.gateway.proxy import router, resolve_backend"` | exit 0, "proxy imports ok" | PASS |
| App instance has correct title | `uv run python -c "from switchboard.gateway.app import app; print(app.title)"` | "Switchboard Gateway" | PASS |
| Dependencies importable | `uv run python -c "import structlog, respx; print(structlog.__version__)"` | "structlog 25.5.0 respx 0.23.1" | PASS |
| All 23 gateway tests pass | `uv run pytest tests/gateway/ -q` | "23 passed, 1 warning in 0.60s" | PASS |
| Ruff lint + format clean | `uv run ruff check switchboard/gateway/ && uv run ruff format --check switchboard/gateway/` | "All checks passed! 4 files already formatted" | PASS |
| Docker Compose full stack | `docker compose up --build -d` (requires Docker) | Cannot test in CI — documented as human-verified in 05-03-SUMMARY | SKIP (human) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| GTWY-01 | 05-02, 05-03 | Customer requests to `/servers/{server-name}` routed to backend container | SATISFIED | `proxy_mcp_request` routes via `http://sb-{name}:8000`; `test_post_proxied` verifies; docker-compose wires gateway→echo/ping |
| GTWY-02 | 05-02 | POST + GET on `/mcp` endpoint proxied | SATISFIED | `router.api_route("/servers/{server_name}/mcp", methods=["GET", "POST"])`; `test_post_proxied` + `test_get_sse_proxied` pass |
| GTWY-03 | 05-02 | Session-ID-based sticky routing | SATISFIED | `_session_map + _session_lock` in `proxy.py`; `test_session_affinity_routes_to_same_backend` passes |
| SECU-01 | 05-01 | JWT Bearer validation; 401+WWW-Authenticate on failure | SATISFIED | `require_customer` in `auth.py`; 6 auth tests pass; 401+`WWW-Authenticate: Bearer` on all failure paths |
| SECU-02 | 05-02 | TLS termination + internal network unencrypted | PARTIAL | Clause 2 (auth header strip, internal HTTP) satisfied — `test_authorization_header_stripped` passes, header strip confirmed in code; Clause 1 (TLS termination) deferred to Phase 7 (AWS ALB) |
| OBSV-01 | 05-02 | Structured JSON logs per request with trace_id, user identity, server name, HTTP status, timestamp | SATISFIED | `structlog.configure` with `JSONRenderer`, `TimeStamper`; `log.info("proxied_request", ...)` with all required fields; 5 logging tests pass |
| PLAT-01 | 05-03 | All components run locally via Docker Compose | SATISFIED (human-verified) | `Dockerfile` with gateway/admin-api targets; `docker-compose.yml` with 5 services; SUMMARY documents "all 5 services healthy" |

**Requirement note — SECU-02:** The requirement is mapped to Phase 5 in REQUIREMENTS.md. Clause 2 (backend communication unencrypted on internal network) is fully delivered. Clause 1 (TLS termination) is an infrastructure concern deferred to Phase 7's AWS ALB. The plan frontmatter for 05-02 explicitly annotates `SECU-02 # Partial: clause 2 delivered here; clause 1 deferred to Phase 7`. Phase 7 success criterion 2 explicitly covers HTTPS at the ALB.

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| None found | — | — | — |

Scanned `switchboard/gateway/auth.py`, `proxy.py`, `app.py` for TODO/FIXME, empty returns, hardcoded empty data, placeholder text. No anti-patterns found. All functions contain substantive implementations. No stubs remain in test files (all 13 Wave 0 stubs replaced with passing tests in Plan 02).

### Human Verification Required

#### 1. Docker Compose Full Stack Test

**Test:** Run `docker compose up --build -d` with OPERATOR_JWT_SECRET and CUSTOMER_JWT_SECRET set, then verify:
- `docker compose ps` shows all 5 services (db, echo, ping, gateway, admin-api) healthy
- `curl -s http://localhost:8080/.well-known/oauth-protected-resource` returns JSON with "resource" key
- Unauthenticated `curl http://localhost:8080/servers/echo/mcp` returns 401
- Authenticated POST with valid customer JWT returns non-401/non-503 from echo server

**Expected:** Full stack healthy; auth flows work end-to-end; gateway proxies to echo container

**Why human:** Cannot start Docker services in automated verification context. The 05-03-SUMMARY documents human verification was performed ("all 5 services healthy, auth flows confirmed" with commit `7b9edb2`), but automated re-verification of docker compose requires human execution.

### Gaps Summary

No automated gaps. All 23 gateway tests pass. All core artifacts exist, are substantive, and are properly wired. The only outstanding item is the docker compose human re-verification, which is procedural (the code and configuration are correct and were previously verified by the developer).

The SECU-02 TLS clause is a documented, intentional deferral to Phase 7 infrastructure work — not a gap in Phase 5.

---

_Verified: 2026-04-16T22:00:18Z_
_Verifier: Claude (gsd-verifier)_
