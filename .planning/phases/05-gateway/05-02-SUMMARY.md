---
phase: 05-gateway
plan: 02
subsystem: gateway
tags: [fastapi, httpx, structlog, respx, streaming-proxy, session-affinity, jwt, rfc-9728]

# Dependency graph
requires:
  - phase: 05-gateway/05-01
    provides: structlog+respx installed, require_customer dependency, customer_auth_headers fixture, stub test files
  - phase: 02-admin-api
    provides: switchboard/registry/models.py SERVER_NAME_PATTERN, switchboard/admin/app.py FastAPI pattern
provides:
  - switchboard/gateway/proxy.py — streaming MCP proxy with server name validation, header stripping, session affinity, 503 handling
  - switchboard/gateway/app.py — FastAPI gateway app with lifespan (httpx.AsyncClient), RequestLogMiddleware, RFC 9728 well-known endpoint
  - Full test coverage for proxy, session, well-known, and structured logging (23 gateway tests passing)
affects:
  - 05-gateway/05-03: gateway app is the integration target for reference MCP servers
  - 07-aws: gateway app is the container entrypoint for ECS/Fargate deployment

# Tech tracking
tech-stack:
  added: []  # All libraries already installed in Plan 01
  patterns:
    - Streaming proxy via httpx.AsyncClient.send(stream=True) + BackgroundTask(aclose) for connection cleanup
    - Server name SSRF prevention via SERVER_NAME_PATTERN regex before any DNS lookup
    - Session stickiness via module-level _session_map dict + asyncio.Lock for concurrent safety
    - Log in route handler (not middleware) to work around Starlette BaseHTTPMiddleware contextvars isolation
    - structlog.testing.capture_logs(processors=[merge_contextvars]) for testing contextvar-enriched log events

key-files:
  created:
    - switchboard/gateway/proxy.py
    - switchboard/gateway/app.py
  modified:
    - tests/gateway/conftest.py (added gateway_client fixture)
    - tests/gateway/test_proxy.py (replaced 5 stubs with 6 real tests)
    - tests/gateway/test_session.py (replaced 3 stubs with 3 real tests)
    - tests/gateway/test_wellknown.py (replaced 2 stubs with 3 real tests)
    - tests/gateway/test_logging.py (replaced 3 stubs with 5 real tests)

key-decisions:
  - "Log proxied_request event in proxy_mcp_request handler (not RequestLogMiddleware.dispatch) because Starlette BaseHTTPMiddleware runs call_next in a new task context — contextvars bound in the route handler are not visible when the middleware resumes after call_next"
  - "Host header stripping test checks that testserver (the TestClient default host) is not forwarded, not that no host header exists — httpx legitimately injects its own host for the backend URL (sb-echo:8000)"
  - "capture_logs(processors=[merge_contextvars]) required for logging tests to capture contextvars set during request handling — default capture_logs() disables all processors including merge_contextvars"

patterns-established:
  - "Pattern 3: Logging in proxy handler — emit the structured log event inside the route handler after the backend responds, not in middleware, to ensure all per-request contextvars are present in the event"
  - "Pattern 4: Starlette BaseHTTPMiddleware contextvars isolation — contextvars set in call_next's task context are not propagated back to the middleware context; bind all contextvars before call_next or log in the handler"

requirements-completed:
  - GTWY-01
  - GTWY-02
  - GTWY-03
  - OBSV-01
  - SECU-02

# Metrics
duration: 35min
completed: 2026-04-16
---

# Phase 5 Plan 02: Gateway Proxy and App Summary

**Streaming MCP proxy (proxy.py) + FastAPI gateway app (app.py) with Authorization header stripping, session affinity, 503 error handling, RFC 9728 well-known endpoint, and structlog JSON logging — all 23 gateway tests passing.**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-04-16T19:10:00Z
- **Completed:** 2026-04-16T19:45:00Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Implemented `switchboard/gateway/proxy.py` with streaming MCP proxy: server name validation via `SERVER_NAME_PATTERN`, Authorization+host header stripping (SECU-02), session stickiness via `_session_map + asyncio.Lock`, 503 on `httpx.ConnectError`, and structured logging via `structlog.contextvars`
- Implemented `switchboard/gateway/app.py` with FastAPI lifespan (shared `httpx.AsyncClient`), `RequestLogMiddleware` (trace_id + http_method binding), router inclusion, and RFC 9728 `/.well-known/oauth-protected-resource` endpoint
- Replaced all 13 stub tests from Plan 01 with 17 real tests across proxy, session, well-known, and logging test files; added `gateway_client` fixture to conftest.py
- All 126 tests pass (23 new gateway + 103 existing); 0 regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement proxy.py** - `7da6d2b` (feat)
2. **Task 2: Implement app.py + replace test stubs** - `7ac19e9` (feat)

## Files Created/Modified

- `switchboard/gateway/proxy.py` - New: streaming MCP proxy handler, resolve_backend, session map, header stripping
- `switchboard/gateway/app.py` - New: FastAPI gateway app with lifespan, middleware, well-known endpoint
- `tests/gateway/conftest.py` - Added `gateway_client` TestClient fixture
- `tests/gateway/test_proxy.py` - Replaced 5 stubs with 6 real proxy tests (POST, GET, auth strip, host strip, 404, 503)
- `tests/gateway/test_session.py` - Replaced 3 stubs with 3 session affinity tests
- `tests/gateway/test_wellknown.py` - Replaced 2 stubs with 3 well-known endpoint tests (resource field, content-type, bearer_methods)
- `tests/gateway/test_logging.py` - Replaced 3 stubs with 5 structured logging tests (trace_id, user_identity, server_name, http_status)

## Decisions Made

- **Log in route handler, not middleware:** Starlette's `BaseHTTPMiddleware` calls `call_next` by creating a new asyncio task (a copy of the current context). Contextvars bound in `proxy_mcp_request` (user_identity, server_name) are in the task's context copy and never propagate back to the middleware's context. Moving `log.info("proxied_request", ...)` to the end of the route handler — after `http_client.send()` returns and before returning the `StreamingResponse` — ensures all contextvar fields are present in the event.
- **Host header test checks testserver not absence of host:** `httpx.build_request` always injects a `host` header for the target URL (sb-echo:8000). The security requirement is that the client's original host (testserver) is not forwarded, not that no host header exists. The test was updated to assert `"testserver" not in forwarded_host`.
- **`capture_logs(processors=[merge_contextvars])`:** The default `capture_logs()` replaces all processors with `LogCapture`, skipping `merge_contextvars`. Passing `merge_contextvars` as a processor ensures contextvars are merged into captured events, enabling assertions on `trace_id`, `user_identity`, and `server_name`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed BackgroundTask import path**
- **Found during:** Task 1 (proxy.py import verification)
- **Issue:** Plan specified `from fastapi.background import BackgroundTask` but `BackgroundTask` is not exported from `fastapi.background` (only `BackgroundTasks` is). `BackgroundTask` lives in `starlette.background`.
- **Fix:** Changed import to `from starlette.background import BackgroundTask`
- **Files modified:** switchboard/gateway/proxy.py
- **Verification:** `uv run python -c "from switchboard.gateway.proxy import router, resolve_backend"` exits 0
- **Committed in:** 7da6d2b (Task 1 commit)

**2. [Rule 1 - Bug] Removed empty TYPE_CHECKING block**
- **Found during:** Task 1 (ruff check)
- **Issue:** Plan's import template included an empty `if TYPE_CHECKING: pass` block; ruff flags this as TC005
- **Fix:** Removed the `TYPE_CHECKING` import and the empty block
- **Files modified:** switchboard/gateway/proxy.py
- **Verification:** `ruff check switchboard/gateway/proxy.py` exits 0
- **Committed in:** 7da6d2b (Task 1 commit)

**3. [Rule 1 - Bug] Fixed structlog contextvar propagation (log in handler not middleware)**
- **Found during:** Task 2 (test_logging tests failing for user_identity and server_name)
- **Issue:** `structlog.contextvars.bind_contextvars(user_identity=..., server_name=...)` was called in `proxy_mcp_request` but the `log.info("proxied_request", ...)` was emitted in `RequestLogMiddleware.dispatch` after `call_next`. Starlette's `BaseHTTPMiddleware` runs the route handler in a new task context (contextvar copy); mutations from the route handler don't propagate back to the middleware context.
- **Fix:** Moved `log.info("proxied_request", http_status=rp_resp.status_code)` into `proxy_mcp_request` (after `http_client.send()`, before returning `StreamingResponse`). Updated `RequestLogMiddleware.dispatch` to only bind trace_id and http_method without emitting a log event.
- **Files modified:** switchboard/gateway/proxy.py, switchboard/gateway/app.py
- **Verification:** `uv run pytest tests/gateway/test_logging.py` — all 5 tests pass
- **Committed in:** 7ac19e9 (Task 2 commit)

**4. [Rule 1 - Bug] Fixed test_host_header_stripped assertion**
- **Found during:** Task 2 (test_host_header_stripped failing)
- **Issue:** Test asserted `"host" not in captured.get("headers", {})` but `httpx.build_request` always injects a `host` header for the target URL (sb-echo:8000). The requirement is that the client's original `host` (testserver) is not forwarded.
- **Fix:** Changed assertion to check `"testserver" not in forwarded_host` instead of absence of host header
- **Files modified:** tests/gateway/test_proxy.py
- **Verification:** `uv run pytest tests/gateway/test_proxy.py::test_host_header_stripped` passes
- **Committed in:** 7ac19e9 (Task 2 commit)

**5. [Rule 1 - Bug] Fixed capture_logs for contextvar-enriched events**
- **Found during:** Task 2 (test_log_contains_trace_id failing in first attempt)
- **Issue:** `structlog.testing.capture_logs()` replaces all configured processors with `LogCapture`, skipping `merge_contextvars`. Contextvar-bound fields (trace_id, http_method) were absent from captured events.
- **Fix:** Used `capture_logs(processors=[structlog.contextvars.merge_contextvars])` to preserve contextvar merging during test capture (requires structlog 25.5.0 which is installed)
- **Files modified:** tests/gateway/test_logging.py
- **Verification:** All 5 logging tests pass
- **Committed in:** 7ac19e9 (Task 2 commit)

**6. [Rule 1 - Bug] Fixed ruff lint issues in test files**
- **Found during:** Task 2 (ruff check tests/gateway/)
- **Issue:** Unused `import pytest` in test_proxy.py, E501 line too long in docstring, SIM117 nested with statements in test_logging.py
- **Fix:** Removed unused import, shortened docstring, combined nested `with` statements into single `with x, y:` form
- **Files modified:** tests/gateway/test_proxy.py, tests/gateway/test_logging.py
- **Verification:** `ruff check tests/gateway/` exits 0
- **Committed in:** 7ac19e9 (Task 2 commit)

---

**Total deviations:** 6 auto-fixed (all Rule 1 — bugs/correctness)
**Impact on plan:** All fixes necessary for correctness. The Starlette contextvars isolation issue (fix 3) required a minor architecture adjustment (logging location moved from middleware to handler) that preserves all plan requirements while working correctly. No scope creep.

## Issues Encountered

- Starlette's `BaseHTTPMiddleware` creates a new asyncio task context for `call_next`, isolating the route handler's contextvar mutations from the middleware. This is a known Starlette limitation. The fix (log in handler) is clean and maintains all security and observability requirements.

## User Setup Required

None - no external service configuration required. All environment variables use test defaults.

## Next Phase Readiness

- Gateway app (`switchboard/gateway/app:app`) is ready for uvicorn invocation
- All proxy security properties verified: Authorization header stripped, host stripped, server name validated
- structlog JSON logging working with trace_id, user_identity, server_name, http_method, http_status per request
- RFC 9728 well-known endpoint implemented
- Plan 03 (reference MCP servers + Docker Compose wiring) can proceed immediately

---
*Phase: 05-gateway*
*Completed: 2026-04-16*

## Self-Check: PASSED

All files verified:
- switchboard/gateway/proxy.py — FOUND
- switchboard/gateway/app.py — FOUND
- tests/gateway/conftest.py — FOUND
- tests/gateway/test_proxy.py — FOUND
- tests/gateway/test_session.py — FOUND
- tests/gateway/test_wellknown.py — FOUND
- tests/gateway/test_logging.py — FOUND
- .planning/phases/05-gateway/05-02-SUMMARY.md — FOUND

Commits verified:
- 7da6d2b — FOUND (feat(05-02): implement MCP proxy handler)
- 7ac19e9 — FOUND (feat(05-02): implement gateway app + replace test stubs)
