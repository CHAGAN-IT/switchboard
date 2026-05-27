---
phase: 01-foundation
reviewed: 2026-04-14T00:00:00Z
depth: standard
files_reviewed: 29
files_reviewed_list:
  - .env.example
  - .gitignore
  - alembic.ini
  - alembic/README
  - alembic/env.py
  - alembic/script.py.mako
  - alembic/versions/a5578b684627_create_servers_table.py
  - docker-compose.yml
  - pyproject.toml
  - scripts/init-test-db.sql
  - switchboard/__init__.py
  - switchboard/admin/__init__.py
  - switchboard/config.py
  - switchboard/container/__init__.py
  - switchboard/db/__init__.py
  - switchboard/db/base.py
  - switchboard/db/engine.py
  - switchboard/db/session.py
  - switchboard/gateway/__init__.py
  - switchboard/py.typed
  - switchboard/registry/__init__.py
  - switchboard/registry/exceptions.py
  - switchboard/registry/models.py
  - switchboard/registry/repository.py
  - switchboard/registry/schemas.py
  - tests/__init__.py
  - tests/conftest.py
  - tests/registry/__init__.py
  - tests/registry/test_models.py
  - tests/registry/test_repository.py
  - tests/test_migrations.py
findings:
  critical: 0
  warning: 3
  info: 5
  total: 8
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-04-14T00:00:00Z
**Depth:** standard
**Files Reviewed:** 29
**Status:** issues_found

## Summary

This is the Phase 1 foundation: project scaffolding, database layer (SQLAlchemy 2.0 async with asyncpg), Alembic migrations, the server registry ORM model and repository, Pydantic schemas, and integration tests. The overall code quality is high — type hints are present throughout, docstrings follow Google style, the repository pattern is clean, and the transaction-rollback test isolation strategy is well-considered.

Three warnings require attention before this phase is considered complete:

1. The `create()` method in `ServerRepository` calls `session.rollback()` on the caller-provided session after an `IntegrityError`. This violates the stated contract ("repository methods flush() but do not commit()") and breaks transaction batching in non-test callers. The test fixture compensates by using savepoints, but production callers passing a plain session will have their entire in-flight transaction rolled back on any duplicate-name attempt.
2. The module-level engine and session factory in `switchboard/db/session.py` are instantiated at import time, which connects to the settings at import time. If `DATABASE_URL` is not set, or if a test imports the module before overriding the URL, the wrong engine is created and cached for the process lifetime.
3. `psycopg2-binary` appears in dev dependencies with no apparent usage in this codebase. The stack explicitly lists it as something to avoid in favour of `asyncpg`.

No critical (security/crash) issues were found.

## Warnings

### WR-01: `ServerRepository.create()` calls `session.rollback()` — violates caller-controlled transaction contract

**File:** `switchboard/registry/repository.py:70-72`

**Issue:** The module docstring explicitly states "Repository methods flush() but do not commit() — this allows tests to use transaction rollback for isolation and lets API endpoints batch multiple operations in a single commit." However, the `create()` method violates this contract by calling `await session.rollback()` on the injected session when an `IntegrityError` is caught:

```python
except IntegrityError as exc:
    await session.rollback()        # <-- rolls back the caller's session
    raise DuplicateServerError(name) from exc
```

In the test fixture (`conftest.py`), this is partially mitigated because `join_transaction_mode="create_savepoint"` causes `session.rollback()` to roll back only to the most recent savepoint, not the outer connection transaction. The test isolation holds. However, in any production caller that passes a plain `AsyncSession` (e.g., via FastAPI `Depends(get_session)`), this `rollback()` will tear down the entire transaction — discarding any work the caller performed before calling `create()`. This breaks the batching promise entirely and is a latent bug waiting to surface in Phase 2 when the Admin API lands.

**Fix:** Remove `session.rollback()` from the repository. Instead, let the `IntegrityError` propagate out (after being translated to `DuplicateServerError`) and allow the caller to decide whether to rollback or not. For the session to remain usable after an `IntegrityError` without an explicit rollback, use a nested savepoint (`SAVEPOINT`) via SQLAlchemy's `session.begin_nested()`:

```python
async def create(
    self,
    session: AsyncSession,
    *,
    name: str,
    container_image: str,
    description: str | None = None,
) -> Server:
    server = Server(
        name=name,
        container_image=container_image,
        description=description,
    )
    session.add(server)
    try:
        async with session.begin_nested():   # creates a SAVEPOINT
            await session.flush()
    except IntegrityError as exc:
        # The SAVEPOINT is rolled back automatically on exception exit.
        # The outer transaction remains intact.
        raise DuplicateServerError(name) from exc
    await session.refresh(server)
    return server
```

This satisfies both the test savepoint strategy and production callers.

---

### WR-02: Engine and session factory created at module import time in `switchboard/db/session.py`

**File:** `switchboard/db/session.py:16-21`

**Issue:** The module-level statements instantiate the engine and session factory unconditionally at import time:

```python
engine = create_engine()                # reads DATABASE_URL at import
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
```

`create_engine()` calls `get_settings()`, which reads `DATABASE_URL` from the environment or `.env` at the moment the module is first imported. This creates two problems:

1. If any test module imports `switchboard.db.session` before the test environment is configured (e.g., `TEST_DATABASE_URL` is not yet set), the production `DATABASE_URL` is baked into the engine and cached for the process lifetime via `lru_cache` on `get_settings()`.
2. There is no way to swap the engine at runtime — e.g., for tests that need to point at the test database. The current tests work around this by never importing `switchboard.db.session` directly and instead creating their own engines in `conftest.py`, but this is a fragile coupling.

**Fix:** Use lazy initialization. Convert to a module-level accessor that creates the engine on first call:

```python
from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from switchboard.db.engine import create_engine

@lru_cache(maxsize=1)
def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create the session factory once and cache it."""
    engine = create_engine()
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session for dependency injection."""
    async with _get_session_factory()() as session:
        yield session
```

This defers engine creation until the first request, keeps the `lru_cache` on `get_settings()` useful, and allows `get_settings.cache_clear()` to be called in tests before the first import of the session module.

---

### WR-03: `psycopg2-binary` in dev dependencies has no documented usage

**File:** `pyproject.toml:20`

**Issue:** `psycopg2-binary>=2.9.0` is listed as a dev dependency:

```toml
[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.26.0",
    "ruff>=0.11.0",
    "psycopg2-binary>=2.9.0",   # <-- no async usage
]
```

The project stack explicitly calls out psycopg2 as something to avoid: "psycopg2 (sync) — blocking I/O in an async FastAPI application will block the event loop." All database access in this codebase uses `asyncpg` via `postgresql+asyncpg://`. No file in the reviewed set imports or references `psycopg2`. If it is being pulled in for a specific reason (e.g., some Alembic offline mode path or a tool that depends on it), that should be documented with a comment. Otherwise it should be removed.

**Fix:** Remove `psycopg2-binary` from dev dependencies unless a specific usage is identified:

```toml
[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.26.0",
    "ruff>=0.11.0",
    # psycopg2-binary removed: all DB access uses asyncpg (postgresql+asyncpg://)
]
```

If it truly is needed, add a comment explaining why.

---

## Info

### IN-01: Default database credentials hardcoded as fallback in `config.py`

**File:** `switchboard/config.py:23-25`

**Issue:** The `Settings` class specifies default values for `database_url` and `test_database_url` that include plaintext credentials (`postgres:postgres`):

```python
database_url: str = (
    "postgresql+asyncpg://postgres:postgres@localhost:5432/switchboard"
)
test_database_url: str = (
    "postgresql+asyncpg://postgres:postgres@localhost:5432/switchboard_test"
)
```

These are appropriate for local development, but they are committed to source. If `DATABASE_URL` is not set in a production environment, the application silently connects with these defaults rather than failing fast. Additionally, since `get_settings()` is `lru_cache`d, the misconfigured URL will persist for the process lifetime.

**Fix:** Consider requiring `database_url` to be set explicitly (no default), or add a startup validation step that asserts credentials do not match the dev defaults in a production environment indicator is set:

```python
database_url: str  # Required — no default forces explicit configuration
```

Or retain the default but add a validator that warns loudly when the default is in use and `ENV != "development"`.

---

### IN-02: `_apply_migrations` fixture downgrade teardown silently ignores failure

**File:** `tests/conftest.py:61-68`

**Issue:** The teardown downgrade in `_apply_migrations` uses `check=False`, meaning a failed downgrade is silently ignored:

```python
subprocess.run(
    ["uv", "run", "alembic", "downgrade", "base"],
    env=env,
    capture_output=True,
    text=True,
    cwd=PROJECT_ROOT,
    check=False,    # failure is silently swallowed
)
```

If the downgrade fails (e.g., due to a broken migration), the test database is left in a partially-migrated state. Subsequent test runs may fail with confusing errors because the schema is in an unexpected state. The setup path (`_apply_migrations` before `yield`) correctly calls `pytest.fail()` on upgrade failure, but the teardown does not provide equivalent protection.

**Fix:** Log a warning or use a `warn()` on teardown failure so the developer knows the database state may be dirty:

```python
result = subprocess.run(
    ["uv", "run", "alembic", "downgrade", "base"],
    env=env,
    capture_output=True,
    text=True,
    cwd=PROJECT_ROOT,
    check=False,
)
if result.returncode != 0:
    import warnings
    warnings.warn(
        f"Alembic downgrade teardown failed — test DB may be dirty:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}",
        stacklevel=1,
    )
```

---

### IN-03: `updated_at` uses ORM-side `onupdate` rather than a server-side trigger

**File:** `switchboard/registry/models.py:85-88`

**Issue:** The `updated_at` column is configured with `onupdate=func.now()`:

```python
updated_at: Mapped[datetime] = mapped_column(
    nullable=False,
    server_default=func.now(),
    onupdate=func.now(),
)
```

SQLAlchemy's `onupdate` is an ORM-level hook — it fires when the ORM emits an `UPDATE` statement for a row it is tracking. This means `updated_at` will NOT be refreshed when:
- The row is updated via raw SQL (e.g., direct `session.execute(update(Server).where(...)`)
- The row is updated outside the ORM (e.g., a migration, an admin tool, a second process)

For a platform that may eventually have background processes or direct SQL admin operations, this is a consistency gap. The `created_at` and `updated_at` defaults in the migration correctly use `server_default=sa.text("now()")` for creation, but there is no `ON UPDATE` trigger in the migration for `updated_at`.

**Fix:** Add a PostgreSQL trigger in a migration to enforce `updated_at` at the database level, independent of the ORM:

```sql
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER servers_updated_at
BEFORE UPDATE ON servers
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

The ORM-level `onupdate` can remain as a belt-and-suspenders fallback.

---

### IN-04: `type: ignore[misc]` on `yield` in `_apply_migrations` has no explanation

**File:** `tests/conftest.py:59`

**Issue:** The `_apply_migrations` fixture uses `# type: ignore[misc]` without an explanation:

```python
yield  # type: ignore[misc]
```

Per project conventions (from `CLAUDE.md`): "No `# type: ignore` without a comment explaining why." The suppression is needed because `mypy` objects to a `None`-returning generator fixture with `scope="session"` — the return type inference differs from `pytest_asyncio` conventions. The ignore is valid but needs documentation.

**Fix:**

```python
yield  # type: ignore[misc]  # mypy: session-scoped pytest fixture yields None; return type is inferred as Generator, not None
```

---

### IN-05: `--strict-markers` not enabled in pytest configuration

**File:** `pyproject.toml:27-32`

**Issue:** The `pyproject.toml` defines an `integration` marker but does not enable `--strict-markers`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "integration: marks tests requiring a running PostgreSQL instance",
]
```

Without `--strict-markers`, a test file using an undefined marker (e.g., a typo like `@pytest.mark.integratoin`) will silently pass rather than raising an error. This makes it easy for integration tests to be accidentally marked with a non-existent marker and then run in environments where they should be skipped.

**Fix:**

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = ["--strict-markers"]
markers = [
    "integration: marks tests requiring a running PostgreSQL instance",
]
```

---

_Reviewed: 2026-04-14T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
