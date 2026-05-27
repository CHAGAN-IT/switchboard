---
phase: 4
slug: reference-servers
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-16
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.26.x |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `uv run pytest tests/reference_servers/ -m reference_servers -x -q` |
| **Full suite command** | `uv run pytest -m reference_servers` |
| **Estimated runtime** | ~30 seconds (Docker startup time dominates) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/reference_servers/ -m reference_servers -x -q`
- **After every plan wave:** Run `uv run pytest -m reference_servers`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

**Pre-requisite for running tests:**
```bash
docker compose build echo ping   # build images first
docker compose up -d             # start all services
```

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 4-01-01 | 01 | 0 | REFS-01 | — | N/A | integration | `uv run pytest tests/reference_servers/test_reference_servers.py::test_echo_returns_input_unchanged -x` | ❌ W0 | ⬜ pending |
| 4-01-02 | 01 | 0 | REFS-02 | — | N/A | integration | `uv run pytest tests/reference_servers/test_reference_servers.py::test_ping_responds_to_mcp_ping -x` | ❌ W0 | ⬜ pending |
| 4-01-03 | 01 | 1 | REFS-01/SC-4 | — | No host ports published; internal network only | integration | `uv run pytest tests/reference_servers/test_reference_servers.py::test_container_manager_lifecycle -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/reference_servers/__init__.py` — package marker
- [ ] `tests/reference_servers/conftest.py` — container fixtures (`echo_container`, `ping_container`, `echo_server_url`, `ping_server_url`)
- [ ] `tests/reference_servers/test_reference_servers.py` — REFS-01, REFS-02, SC-4 test stubs
- [ ] Root `pyproject.toml` update: add `reference_servers` to `markers` list
- [ ] Root `pyproject.toml` update: add `mcp` to dev dependencies (`uv add --dev mcp`)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Both images can be built cleanly with `docker compose build` | D-02, D-10 | Requires Docker build environment; not automatable in CI without Docker-in-Docker | Run `docker compose build echo ping` and verify both succeed with exit code 0 |
| Containers join `switchboard-internal` network (no host ports) | D-05 | Network topology verification requires `docker inspect` | Run `docker compose up -d echo ping && docker inspect sb-echo | grep -A5 NetworkSettings` — verify no host port binding |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
