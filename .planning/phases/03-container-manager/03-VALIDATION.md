---
phase: 3
slug: container-manager
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-15
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.26.x |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest tests/container/ tests/admin/ -x -q` |
| **Full suite command** | `uv run pytest -x -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/container/ tests/admin/ -x -q`
- **After every plan wave:** Run `uv run pytest -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 3-W0-01 | 01 | 0 | CONT-01 | — | N/A | unit | `uv run pytest tests/container/test_manager.py -x -q` | ❌ W0 | ⬜ pending |
| 3-W0-02 | 01 | 0 | CONT-02 | — | N/A | unit | `uv run pytest tests/container/test_manager.py -x -q` | ❌ W0 | ⬜ pending |
| 3-W0-03 | 01 | 0 | CONT-03 | — | N/A | unit | `uv run pytest tests/container/test_manager.py -x -q` | ❌ W0 | ⬜ pending |
| 3-01-01 | 01 | 1 | CONT-01 | T-3-01 | No host ports published (D-01) | unit | `uv run pytest tests/container/test_manager.py -k "start" -x -q` | ❌ W0 | ⬜ pending |
| 3-01-02 | 01 | 1 | CONT-01 | T-3-02 | No privileged mode | unit | `uv run pytest tests/container/test_manager.py -k "no_host_port" -x -q` | ❌ W0 | ⬜ pending |
| 3-01-03 | 01 | 1 | CONT-02 | — | N/A | unit | `uv run pytest tests/container/test_manager.py -k "stop" -x -q` | ❌ W0 | ⬜ pending |
| 3-01-04 | 01 | 1 | CONT-03 | — | N/A | unit | `uv run pytest tests/container/test_manager.py -k "restart" -x -q` | ❌ W0 | ⬜ pending |
| 3-02-01 | 02 | 2 | CONT-01 | — | Auth required on endpoint | integration | `uv run pytest tests/admin/test_endpoints.py -k "start" -x -q` | ❌ W0 | ⬜ pending |
| 3-02-02 | 02 | 2 | CONT-02 | — | Auth required on endpoint | integration | `uv run pytest tests/admin/test_endpoints.py -k "stop" -x -q` | ❌ W0 | ⬜ pending |
| 3-02-03 | 02 | 2 | CONT-03 | — | Auth required on endpoint | integration | `uv run pytest tests/admin/test_endpoints.py -k "restart" -x -q` | ❌ W0 | ⬜ pending |
| 3-02-04 | 02 | 2 | CONT-01 | — | 409 when already running | integration | `uv run pytest tests/admin/test_endpoints.py -k "start_already_running" -x -q` | ❌ W0 | ⬜ pending |
| 3-02-05 | 02 | 2 | CONT-02 | — | 409 when already stopped | integration | `uv run pytest tests/admin/test_endpoints.py -k "stop_already_stopped" -x -q` | ❌ W0 | ⬜ pending |
| 3-02-06 | 02 | 2 | CONT-01 | — | 404 for unknown server | integration | `uv run pytest tests/admin/test_endpoints.py -k "not_found" -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/container/__init__.py` — new test package
- [ ] `tests/container/conftest.py` — shared fixtures for ContainerManager mocking (mock `docker.from_env`)
- [ ] `tests/container/test_manager.py` — unit test stubs for CONT-01, CONT-02, CONT-03, SC-4, SC-5
- [ ] Update `tests/admin/conftest.py` — add `get_container_manager` override to existing client fixture
- [ ] Update `tests/admin/test_endpoints.py` — add lifecycle endpoint test stubs (start/stop/restart/409/404)
- [ ] `uv add docker` — promote docker SDK to production dependency

*Wave 0 must be complete before Wave 1 execution begins.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| MCP server container is reachable only on internal network | SC-5 | Requires live Docker Compose environment | `docker inspect sb-{name} --format '{{json .NetworkSettings.Networks}}'` — should show only `switchboard-internal`, no `Ports` entries |
| Container removed after stop (no orphaned containers) | CONT-02 | Requires live Docker | `docker ps -a --filter name=sb-` — should show no containers after stop |
| Docker daemon unavailable returns 500 gracefully | D-04 | Requires killing Docker daemon | Stop Docker, call `POST /start`, verify 500 with `{"detail": "..."}` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
