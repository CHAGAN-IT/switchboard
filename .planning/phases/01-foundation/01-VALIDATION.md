---
phase: 1
slug: foundation
status: verified
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-14
updated: 2026-04-15
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
| 1-01-01 | 01 | 0 | PLAT-03 | — | N/A | unit | `uv run python -c "import switchboard"` | ✅ | ✅ green |
| 1-01-02 | 01 | 0 | PLAT-03 | — | N/A | unit | `uv run pytest --co -q 2>/dev/null \| grep registry` | ✅ | ✅ green |
| 1-01-03 | 01 | 1 | PLAT-03 | — | N/A | integration | `uv run pytest tests/registry/test_models.py -x -q` | ✅ | ✅ green |
| 1-01-04 | 01 | 1 | PLAT-03 | T-02-01 | Input validation rejects invalid server names | unit | `uv run pytest tests/registry/test_validation.py -x -q` | ✅ | ✅ green |
| 1-01-05 | 01 | 2 | PLAT-03 | — | N/A | integration | `uv run pytest tests/test_migrations.py -x -q` | ✅ | ✅ green |
| 1-01-06 | 01 | 2 | PLAT-03 | — | N/A | integration | `uv run pytest tests/registry/ -x -q` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/__init__.py` — make tests a package
- [x] `tests/conftest.py` — async session fixture with savepoint rollback per test
- [x] `tests/registry/__init__.py` — registry test package
- [x] `tests/registry/test_models.py` — 8 tests covering PLAT-03 (ORM model, schemas)
- [x] `tests/registry/test_validation.py` — 19 tests for server name ORM + Pydantic validation (generated 2026-04-15)
- [x] `tests/test_migrations.py` — Alembic up/down migration cycle test
- [x] `uv add --dev pytest pytest-asyncio` — installed

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Docker WSL2 integration enabled | PLAT-03 | Docker not available in WSL2 by default; requires user to enable Docker Desktop WSL2 backend | In Docker Desktop: Settings → Resources → WSL Integration → enable for your distro |

---

## Validation Audit 2026-04-15

| Metric | Count |
|--------|-------|
| Gaps found | 1 |
| Resolved | 1 |
| Escalated | 0 |

## Validation Sign-Off

- [x] All tasks have automated verify commands
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** verified 2026-04-15
