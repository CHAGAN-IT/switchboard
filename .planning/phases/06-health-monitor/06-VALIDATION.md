---
phase: 6
slug: health-monitor
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-18
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.26.x |
| **Config file** | `pyproject.toml` (pytest section) |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 6-01-01 | 01 | 1 | CONT-04 | — | N/A | unit | `uv run pytest tests/test_health_monitor.py -x -q` | ❌ W0 | ⬜ pending |
| 6-01-02 | 01 | 1 | CONT-04 | — | N/A | unit | `uv run pytest tests/test_health_monitor.py -x -q` | ❌ W0 | ⬜ pending |
| 6-01-03 | 01 | 1 | CONT-04 | — | N/A | integration | `uv run pytest tests/test_health_integration.py -x -q` | ❌ W0 | ⬜ pending |
| 6-01-04 | 01 | 2 | CONT-04 | — | N/A | unit | `uv run pytest tests/test_health_monitor.py -x -q` | ❌ W0 | ⬜ pending |
| 6-01-05 | 01 | 2 | CONT-04 | — | N/A | integration | `uv run pytest tests/test_admin_health.py -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_health_monitor.py` — unit test stubs for HealthMonitor polling logic
- [ ] `tests/test_health_integration.py` — integration test stubs for full probe cycle
- [ ] `tests/test_admin_health.py` — integration test stubs for `GET /servers/{name}` health_status field
- [ ] `tests/conftest.py` — verify shared fixtures for Docker mock and async session

*Existing pytest + pytest-asyncio infrastructure is already installed. Wave 0 only needs test file stubs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| health_status transitions to `unreachable` within 2 polling intervals after container stop | CONT-04 | Requires real Docker daemon and timing verification | Start a server, stop the container externally, wait 65s, verify `GET /servers/{name}` returns `health_status: unreachable` |
| Background task does not block Admin API request handling | CONT-04 | Concurrency behavior hard to assert in unit tests | During active polling cycle, make rapid Admin API requests and verify response times remain normal |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
