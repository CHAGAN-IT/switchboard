---
phase: 8
slug: ecs-production-fixes
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-21
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.26.x |
| **Config file** | `pyproject.toml` [tool.pytest] section |
| **Quick run command** | `uv run pytest tests/admin/test_health_route.py tests/health/test_monitor.py -x -q` |
| **Full suite command** | `uv run pytest -x -q` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/admin/test_health_route.py tests/health/test_monitor.py -x -q`
- **After every plan wave:** Run `uv run pytest -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 8-01-01 | 01 | 1 | PLAT-02 | — | GET /health returns only `{"status": "ok"}`, no sensitive data | unit | `uv run pytest tests/admin/test_health_route.py::TestHealthEndpoint::test_health_returns_200_ok -x` | ❌ W0 | ⬜ pending |
| 8-01-02 | 01 | 1 | PLAT-02 | — | No auth header required | unit | `uv run pytest tests/admin/test_health_route.py::TestHealthEndpoint::test_health_no_auth_required -x` | ❌ W0 | ⬜ pending |
| 8-01-03 | 01 | 1 | CONT-04 | — | _http_probe appends cloud_map_domain to hostname | unit | `uv run pytest tests/health/test_monitor.py::TestHttpProbe::test_http_probe_uses_cloud_map_domain -x` | ❌ W0 | ⬜ pending |
| 8-01-04 | 01 | 1 | CONT-04 | — | _http_probe works with empty domain (local dev) | unit | `uv run pytest tests/health/test_monitor.py::TestHttpProbe::test_http_probe_no_domain_suffix_local -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/admin/test_health_route.py` — stubs for PLAT-02 health endpoint
- [ ] `tests/health/test_monitor.py` — extend existing file with cloud_map_domain probe tests for CONT-04

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| ECS task reaches HEALTHY state in AWS console | PLAT-02 | Requires live ECS deployment | Deploy with `cdk deploy`, check ECS task health in AWS console |
| Cloud Map service discovery routes probe correctly | CONT-04 | Requires live ECS + Cloud Map | Deploy, check health monitor logs in CloudWatch for successful probe URLs |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
