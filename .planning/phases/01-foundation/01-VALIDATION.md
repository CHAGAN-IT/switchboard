---
phase: 1
slug: foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-14
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.26.x |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `uv run pytest tests/registry/ -x -q --tb=short` |
| **Full suite command** | `uv run pytest -x -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/registry/ -x -q --tb=short`
- **After every plan wave:** Run `uv run pytest -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 0 | PLAT-03 | — | N/A | unit | `uv run python -c "import switchboard"` | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 0 | PLAT-03 | — | N/A | unit | `uv run pytest --co -q 2>/dev/null | grep registry` | ❌ W0 | ⬜ pending |
| 1-01-03 | 01 | 1 | PLAT-03 | — | N/A | integration | `uv run pytest tests/registry/test_models.py -x -q` | ❌ W0 | ⬜ pending |
| 1-01-04 | 01 | 1 | PLAT-03 | — | Input validation rejects invalid server names | unit | `uv run pytest tests/registry/test_validation.py -x -q` | ❌ W0 | ⬜ pending |
| 1-01-05 | 01 | 2 | PLAT-03 | — | N/A | integration | `uv run pytest tests/registry/test_migrations.py -x -q` | ❌ W0 | ⬜ pending |
| 1-01-06 | 01 | 2 | PLAT-03 | — | N/A | integration | `uv run pytest tests/registry/ -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/__init__.py` — make tests a package
- [ ] `tests/conftest.py` — async session fixture with savepoint rollback per test
- [ ] `tests/registry/__init__.py` — registry test package
- [ ] `tests/registry/test_models.py` — stubs for PLAT-03 (CRUD operations)
- [ ] `tests/registry/test_validation.py` — stubs for server name regex validation
- [ ] `tests/registry/test_migrations.py` — stubs for Alembic up/down migration
- [ ] `uv add --dev pytest pytest-asyncio` — if not already installed

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Docker WSL2 integration enabled | PLAT-03 | Docker not available in WSL2 by default; requires user to enable Docker Desktop WSL2 backend | In Docker Desktop: Settings → Resources → WSL Integration → enable for your distro |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
