---
phase: 06-health-monitor
reviewed: 2026-04-18T15:00:00Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - switchboard/health/monitor.py
  - switchboard/admin/app.py
  - switchboard/config.py
  - switchboard/registry/models.py
  - switchboard/registry/schemas.py
  - alembic/versions/b3f1a2c94d85_add_health_status_column.py
  - tests/health/conftest.py
  - tests/health/test_monitor.py
  - tests/health/test_integration.py
  - tests/admin/test_health_endpoint.py
findings:
  critical: 0
  warning: 4
  info: 2
  total: 6
status: issues_found
---

# Phase 6: Code Review Report

**Reviewed:** 2026-04-18T15:00:00Z
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

This phase implements a background `HealthMonitor` that periodically polls running MCP server containers via Docker inspect and HTTP probe, updates `health_status` on the `Server` ORM model, and exposes that field through the Admin API. The implementation covers the full vertical slice: migration, ORM column, Pydantic schema, lifespan wiring, and test suite.

The core implementation is solid. The state machine in `_compute_status` is correct, the lifespan management in `app.py` is clean, and the migration is well-formed. The primary concerns are in the test layer: two findings indicate tests that will silently pass without executing the code they claim to test (missing `@pytest.mark.asyncio` markers and a session-visibility gap in an endpoint test). There is also a warning about the ORM model omitting an explicit SQLAlchemy enum type for `health_status`, which risks DDL drift from the migration.

## Warnings

### WR-01: Async unit test methods missing `@pytest.mark.asyncio` — tests may not execute async code

**File:** `tests/health/test_monitor.py:108`

**Issue:** The classes `TestInspectContainer`, `TestProbeServer`, and `TestPollCycle` contain `async def` test methods without `@pytest.mark.asyncio` decorators, and no class-level `pytestmark` is set. Under `asyncio_mode = "strict"` (or the default in some `pytest-asyncio` versions), async test functions in a plain class are not recognized as coroutines to await — they are collected as synchronous tests that return a coroutine object, which evaluates as truthy and silently passes without executing the async body.

Affected methods:
- `TestInspectContainer.test_inspect_container_running` (line 108)
- `TestInspectContainer.test_inspect_container_not_found` (line 128)
- `TestProbeServer.test_probe_server_healthy` (line 209)
- `TestProbeServer.test_probe_server_unreachable_docker_down` (line 235)
- `TestPollCycle.test_poll_cycle_processes_multiple_servers` (line 269)
- `TestPollCycle.test_poll_cycle_isolates_exceptions` (line 297)
- `TestPollCycle.test_failure_counter_cleanup_for_stopped_servers` (line 335)

**Fix:** Add `@pytest.mark.asyncio` to each async method, or add a class-level `pytestmark` to each affected class:

```python
class TestInspectContainer:
    """Tests for _inspect_container Docker SDK calls."""

    pytestmark = pytest.mark.asyncio

    @patch("switchboard.health.monitor.docker.from_env")
    async def test_inspect_container_running(self, ...):
        ...
```

Or apply per-method:

```python
    @pytest.mark.asyncio
    @patch("switchboard.health.monitor.docker.from_env")
    async def test_inspect_container_running(self, ...):
        ...
```

Note: `TestComputeStatus` and `TestFailureCounterEdgeCases` contain only synchronous test methods and are unaffected.

---

### WR-02: Integration endpoint test — DB write not visible to the API's session

**File:** `tests/admin/test_health_endpoint.py:96`

**Issue:** `test_get_server_returns_health_status_value_when_set` writes `server.health_status = HealthStatus.healthy` to the test `session` fixture and calls `await session.flush()` (line 97), but never calls `session.commit()`. The test session uses `join_transaction_mode="create_savepoint"` and wraps everything in an outer rolled-back transaction (see `tests/conftest.py:113`). A flush writes to the savepoint, but the Admin API's own database session (from `async_session_factory`) is a different connection — it cannot see uncommitted data from another connection's savepoint under PostgreSQL's default Read Committed isolation. The subsequent `GET /api/v1/servers/health-test-03` call will observe `health_status = None` rather than `"healthy"`, so the assertion on line 106 (`assert data["health_status"] == "healthy"`) will fail in a real test run against a database, or pass vacuously if the test runner isn't actually connecting to a database.

**Fix:** The test architecture mixes two approaches (shared session injection vs. real HTTP client hitting the real app). The cleanest fix is to use the monitor's own write path (mock a poll cycle that sets the value) rather than directly mutating the session. Alternatively, commit within the test and use a `finally` block for cleanup, but that breaks rollback isolation.

The most compatible approach within the existing fixture design is to directly manipulate the server via the `client` (if an admin endpoint exists to set status) or mock the ORM layer. For now, explicitly flushing and committing via the test session and relying on the savepoint rollback is not sufficient because the API uses a different connection:

```python
# Instead of directly setting health_status on the session,
# mock _get_running_servers to return the server and force a
# monitor poll cycle that writes via the same session factory.
# OR: verify the field in the DB directly via the test session
# rather than through the HTTP API call.
await session.commit()  # makes data visible cross-connection
# ... make HTTP request ...
# cleanup handled by the outer transaction cannot apply here;
# manually delete the server record after the test.
```

---

### WR-03: ORM `health_status` column has no explicit SQLAlchemy enum type — risks DDL mismatch

**File:** `switchboard/registry/models.py:93`

**Issue:** The `health_status` column is declared as:

```python
health_status: Mapped[HealthStatus | None] = mapped_column(
    nullable=True,
    default=None,
)
```

No explicit `sa.Enum(HealthStatus, name="healthstatus")` is passed to `mapped_column`. SQLAlchemy 2.0 infers the column type from the `Mapped` annotation and will generate its own `Enum` type DDL when `Base.metadata.create_all()` is called. By default, SQLAlchemy names PostgreSQL enum types after the Python class name in lowercase (`healthstatus`), so the name will coincidentally match the migration. However, the inferred type does not carry `create_type=False`, which means if `create_all()` is ever used (e.g., in tests or tooling that bypasses Alembic), it will attempt to create the `healthstatus` enum type again and fail if it already exists. It also means the SQLAlchemy metadata-generated DDL and the Alembic-managed DDL are not explicitly coupled — a future rename of the Python enum class or a change in SQLAlchemy's inference logic could silently diverge.

**Fix:** Explicitly declare the column type to lock it to the migration's enum:

```python
from sqlalchemy import Enum as SAEnum

health_status: Mapped[HealthStatus | None] = mapped_column(
    SAEnum(HealthStatus, name="healthstatus", create_type=False),
    nullable=True,
    default=None,
)
```

The `create_type=False` tells SQLAlchemy to never try to create the PostgreSQL type — Alembic owns that.

---

### WR-04: Integration test calls `session.commit()` inside a `_poll_cycle` call, breaking rollback isolation

**File:** `tests/health/test_integration.py:74`

**Issue:** `test_poll_cycle_updates_health_status_in_db` passes a `mock_factory` that wraps the test's `session` fixture. When `_poll_cycle` runs, it calls `await session.commit()` at line 79 of `monitor.py`. The test `session` fixture is configured with `join_transaction_mode="create_savepoint"` and the outer `transaction.rollback()` in `conftest.py:120` is designed to undo all changes. However, SQLAlchemy's `join_transaction_mode="create_savepoint"` means that `session.commit()` within the session releases the savepoint — it does not commit to the outer transaction. This is actually the correct behavior for isolation (the outer rollback still works), so the test isolation itself is not broken.

However, the test then calls `await session.refresh(server)` on line 77 after `_poll_cycle()`. Because the `session.commit()` inside `_poll_cycle` flushed and released the savepoint, the server's state in the identity map may be expired. `session.refresh(server)` will re-fetch from the database, which should now show the updated `health_status`. This works correctly as written.

The real risk is subtle: if a future developer adds another savepoint-aware operation between `_poll_cycle()` and `session.refresh()`, the expired identity map could cause unexpected lazy-load issues. The test also silently depends on the savepoint commit behavior being transparent, which is implementation-specific to `join_transaction_mode`.

**Fix:** This is a low-severity warning rather than a breaking bug. Document the savepoint behavior in the test to make the dependency explicit:

```python
with patch(...):
    await monitor._poll_cycle()
    # _poll_cycle commits within the savepoint; the outer transaction
    # (from conftest session fixture) still rolls back on test exit.

await session.refresh(server)  # re-fetch after savepoint commit
assert server.health_status == HealthStatus.healthy
```

A comment clarifying the savepoint behavior would prevent future confusion.

---

## Info

### IN-01: `type: ignore[assignment]` comment lacks explanation

**File:** `tests/health/test_monitor.py:326`

**Issue:** The comment `# type: ignore[assignment]` is used without an explanation. Per project conventions from `CLAUDE.md`, `type: ignore` must include a comment explaining why.

**Fix:**

```python
monitor._probe_server = mock_probe  # type: ignore[assignment]  # replacing AsyncMock with hand-rolled async callable for sequenced side effects
```

---

### IN-02: `contextlib` module imported alongside `contextlib.asynccontextmanager` — redundant import alias

**File:** `switchboard/admin/app.py:13-14`

**Issue:** Both `import contextlib` and `from contextlib import asynccontextmanager` are imported. `asynccontextmanager` is used as a decorator on line 30. `contextlib.suppress` is used on line 68. These are correct and both imports are used, but the mix of `import contextlib` (used for `contextlib.suppress`) and `from contextlib import asynccontextmanager` is slightly inconsistent. It is not a bug, but using `from contextlib import asynccontextmanager, suppress` would be more consistent with the project's import style.

**Fix:**

```python
from contextlib import asynccontextmanager, suppress

# Then on line 68:
with suppress(asyncio.CancelledError):
    await task
```

---

_Reviewed: 2026-04-18T15:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
