---
status: complete
phase: 01-foundation
source: [01-01-SUMMARY.md, 01-02-SUMMARY.md, 01-03-SUMMARY.md]
started: 2026-04-15T00:00:00Z
updated: 2026-04-15T12:00:00Z
---

## Current Test

<!-- OVERWRITE each test - shows where we are -->

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: Kill any running Docker containers. Run `docker compose up -d` from scratch. PostgreSQL starts, healthcheck passes, and both `switchboard` (port 5432) and `switchboard_test` databases are accessible. No errors in `docker compose logs`.
result: pass

### 2. Package Import
expected: Running `uv run python -c "import switchboard; import switchboard.db; import switchboard.registry; import switchboard.gateway; import switchboard.admin; import switchboard.container; print('OK')"` prints `OK` with no errors.
result: pass

### 3. Settings Configuration
expected: Running `uv run python -c "from switchboard.config import get_settings; s = get_settings(); print(s.database_url)"` prints a DATABASE_URL (or raises a clear validation error if env var is not set). No import errors or crashes.
result: pass

### 4. Server Name Validation — Valid Names Accepted
expected: Running `uv run pytest tests/registry/test_models.py -k "valid" -q` passes. ORM and schemas accept names like `my-server`, `echo-server-01`, `a`.
result: pass

### 5. Server Name Validation — Invalid Names Rejected
expected: Running `uv run pytest tests/registry/test_models.py -k "invalid" -q` passes. ORM raises `ValueError` for names like `UPPER`, `has space`, `has_underscore`, empty string.
result: pass

### 6. Full Unit Test Suite
expected: Running `uv run pytest tests/registry/test_models.py -q` passes all 20 tests with no failures or errors.
result: pass

### 7. Alembic Migration — Upgrade
expected: With PostgreSQL running, `uv run alembic upgrade head` completes without errors and creates the `servers` table with all columns (id, name, image, status, container_id, description, created_at, updated_at).
result: pass

### 8. Alembic Migration — Downgrade
expected: `uv run alembic downgrade base` drops the `servers` table and removes the `serverstatus` enum type without errors.
result: pass

### 9. Repository Integration Tests
expected: Running `uv run pytest tests/registry/test_repository.py -q` passes all 14 tests. CRUD operations (create, get, list, update_status, delete) work against live PostgreSQL. Duplicate name raises `DuplicateServerError`. Non-existent ID returns `None`.
result: pass

### 10. Migration Cycle Test
expected: Running `uv run pytest tests/test_migrations.py -q` passes. Alembic runs upgrade → downgrade → upgrade cycle without errors.
result: pass

### 11. Full Test Suite
expected: Running `uv run pytest -q` passes all 35 tests (20 model + 14 repository + 1 migration) with no failures.
result: pass

## Summary

total: 11
passed: 11
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none yet]
