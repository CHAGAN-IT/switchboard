---
phase: 5
slug: gateway
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-16
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -q` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 5-W0-01 | 01 | 0 | GTWY-01 | — | N/A | unit stub | `uv run pytest tests/test_gateway_router.py -x -q` | ❌ W0 | ⬜ pending |
| 5-W0-02 | 01 | 0 | SECU-01 | T-5-01 | JWT-less request returns 401 | unit stub | `uv run pytest tests/test_gateway_auth.py -x -q` | ❌ W0 | ⬜ pending |
| 5-W0-03 | 01 | 0 | OBSV-01 | — | N/A | unit stub | `uv run pytest tests/test_gateway_logging.py -x -q` | ❌ W0 | ⬜ pending |
| 5-01-01 | 01 | 1 | GTWY-01 | — | N/A | unit | `uv run pytest tests/test_gateway_router.py -x -q` | ❌ W0 | ⬜ pending |
| 5-01-02 | 01 | 1 | SECU-01 | T-5-01 | Invalid JWT returns 401 + WWW-Authenticate header | unit | `uv run pytest tests/test_gateway_auth.py::test_missing_jwt_returns_401 -x -q` | ❌ W0 | ⬜ pending |
| 5-01-03 | 01 | 1 | SECU-02 | T-5-02 | Authorization header stripped before forwarding | unit | `uv run pytest tests/test_gateway_router.py::test_authorization_header_stripped -x -q` | ❌ W0 | ⬜ pending |
| 5-01-04 | 01 | 1 | GTWY-02 | — | POST proxied correctly | unit | `uv run pytest tests/test_gateway_router.py::test_post_proxied -x -q` | ❌ W0 | ⬜ pending |
| 5-01-05 | 01 | 1 | GTWY-02 | — | GET (SSE) proxied as streaming response | unit | `uv run pytest tests/test_gateway_router.py::test_get_sse_proxied -x -q` | ❌ W0 | ⬜ pending |
| 5-01-06 | 01 | 1 | GTWY-03 | — | Same Mcp-Session-Id routes to same container | unit | `uv run pytest tests/test_gateway_router.py::test_session_affinity -x -q` | ❌ W0 | ⬜ pending |
| 5-01-07 | 01 | 1 | SECU-02 | T-5-03 | /.well-known/oauth-protected-resource returns RFC 9728 doc | unit | `uv run pytest tests/test_gateway_meta.py::test_oauth_resource_metadata -x -q` | ❌ W0 | ⬜ pending |
| 5-01-08 | 01 | 1 | OBSV-01 | — | Structured JSON log line emitted per request | unit | `uv run pytest tests/test_gateway_logging.py::test_structured_log_line -x -q` | ❌ W0 | ⬜ pending |
| 5-01-09 | 01 | 2 | PLAT-01 | — | docker compose up passes health checks | integration | `docker compose up -d && docker compose ps` (manual check) | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_gateway_router.py` — stubs for GTWY-01, GTWY-02, GTWY-03, SECU-02
- [ ] `tests/test_gateway_auth.py` — stubs for SECU-01
- [ ] `tests/test_gateway_logging.py` — stubs for OBSV-01
- [ ] `tests/test_gateway_meta.py` — stubs for SECU-02 (RFC 9728 endpoint)
- [ ] `tests/conftest.py` — add `os.environ.setdefault("CUSTOMER_JWT_SECRET", "test-customer-secret")` fixture
- [ ] `uv add structlog` — missing from lockfile (required for structured logging)
- [ ] `uv add --dev respx` — missing from lockfile (required for mocking httpx in tests)

*Wave 0 must complete before any Wave 1 tasks begin.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `docker compose up` starts all services | PLAT-01 | Requires Docker daemon + real container images | Run `docker compose up -d`, verify `docker compose ps` shows all services healthy |
| End-to-end MCP request through gateway | GTWY-01 | Requires full running stack | Use `mcp` CLI or httpx script to send a real MCP request to `/servers/echo/mcp` with a valid JWT |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
