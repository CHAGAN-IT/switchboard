---
phase: 2
slug: admin-api
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-15
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.26.x |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/admin/ -x -q` |
| **Full suite command** | `uv run pytest -x -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/admin/ -x -q`
- **After every plan wave:** Run `uv run pytest -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 2-01-01 | 01 | 0 | SREG-01 | — | N/A | unit | `uv run pytest tests/admin/ -x -q` | ❌ W0 | ⬜ pending |
| 2-01-02 | 01 | 1 | SREG-01 | T-2-01 | 401 + WWW-Authenticate on missing token | integration | `uv run pytest tests/admin/test_endpoints.py::test_register_server_success -x` | ❌ W0 | ⬜ pending |
| 2-01-03 | 01 | 1 | SREG-01 | T-2-01 | 409 on duplicate name | integration | `uv run pytest tests/admin/test_endpoints.py::test_register_server_duplicate_409 -x` | ❌ W0 | ⬜ pending |
| 2-01-04 | 01 | 1 | SREG-01 | — | 422 on invalid input | integration | `uv run pytest tests/admin/test_endpoints.py::test_register_server_invalid_name_422 -x` | ❌ W0 | ⬜ pending |
| 2-02-01 | 02 | 1 | SREG-02 | — | N/A | integration | `uv run pytest tests/admin/test_endpoints.py::test_list_servers -x` | ❌ W0 | ⬜ pending |
| 2-02-02 | 02 | 1 | SREG-02 | — | N/A | integration | `uv run pytest tests/admin/test_endpoints.py::test_list_servers_empty -x` | ❌ W0 | ⬜ pending |
| 2-03-01 | 03 | 1 | SREG-03 | — | N/A | integration | `uv run pytest tests/admin/test_endpoints.py::test_get_server_by_name -x` | ❌ W0 | ⬜ pending |
| 2-03-02 | 03 | 1 | SREG-03 | — | 404 for unknown server | integration | `uv run pytest tests/admin/test_endpoints.py::test_get_server_not_found_404 -x` | ❌ W0 | ⬜ pending |
| 2-04-01 | 04 | 1 | AUTH | T-2-02 | 401 + WWW-Authenticate on missing token | unit | `uv run pytest tests/admin/test_auth.py::test_missing_token_401 -x` | ❌ W0 | ⬜ pending |
| 2-04-02 | 04 | 1 | AUTH | T-2-02 | 401 on invalid/expired token | unit | `uv run pytest tests/admin/test_auth.py::test_invalid_token_401 -x` | ❌ W0 | ⬜ pending |
| 2-04-03 | 04 | 1 | AUTH | T-2-03 | 401 on expired token | unit | `uv run pytest tests/admin/test_auth.py::test_expired_token_401 -x` | ❌ W0 | ⬜ pending |
| 2-04-04 | 04 | 1 | AUTH | T-2-04 | Valid token allows request through | unit | `uv run pytest tests/admin/test_auth.py::test_valid_token_succeeds -x` | ❌ W0 | ⬜ pending |
| 2-05-01 | 05 | 2 | OPENAPI | — | N/A | smoke | `uv run pytest tests/admin/test_endpoints.py::test_openapi_docs_accessible -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/admin/__init__.py` — package marker
- [ ] `tests/admin/conftest.py` — TestClient fixtures with dependency overrides (`get_session`, `require_operator`)
- [ ] `tests/admin/test_auth.py` — JWT auth dependency unit tests (stubs for AUTH requirements)
- [ ] `tests/admin/test_endpoints.py` — endpoint integration tests (stubs for SREG-01, SREG-02, SREG-03)
- [ ] Framework install: `uv add fastapi uvicorn PyJWT && uv add --dev httpx`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| OpenAPI UI at `/docs` renders correctly in browser | SREG-01/02/03 | Browser rendering not automatable | Start `uv run uvicorn switchboard.admin.app:app --reload`, open `http://localhost:8000/docs`, verify all 3 endpoints listed with correct schemas |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
