# Phase 1: Foundation - Context

**Gathered:** 2026-04-14
**Status:** Ready for planning

<domain>
## Phase Boundary

The project has a working Python package structure, a running PostgreSQL database, and a complete server registry data layer (models, migrations, repository) that all subsequent phases depend on. This phase does not include any HTTP API surface, container management, or gateway logic.

</domain>

<decisions>
## Implementation Decisions

### Package structure
- **D-01:** Feature-grouped subpackages — `switchboard/registry/`, `switchboard/gateway/`, `switchboard/admin/`, `switchboard/container/` — stubbed as empty packages from day one so the full structure is visible before code fills them.
- **D-02:** Shared database infrastructure lives in `switchboard/db/` subpackage (`engine.py`, `session.py`, `base.py`). All feature subpackages import from here.
- **D-03:** App configuration (DB URL, env vars) managed via `switchboard/config.py` using a `pydantic-settings` `Settings` class. All subpackages import settings from this single module.

### Server registry schema
- **D-04:** Primary key is UUID v4, generated server-side with Python `uuid.uuid4()`.
- **D-05:** Status is a Python enum with values: `stopped`, `running`, `error`. Default on registration is `stopped`.
- **D-06:** Full column set: `id` (UUID PK), `name` (text, unique, not null), `container_image` (text, not null), `description` (text, nullable), `status` (enum, not null), `container_id` (text, nullable — populated when container is running), `created_at` (timestamptz, not null), `updated_at` (timestamptz, not null).
- **D-07:** `description` is optional (nullable). Empty string is rejected at the API layer (Phase 2), but the DB column allows NULL.
- **D-08:** Server name must match `^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$` — validated at the model level, not just the API layer.

### Database access pattern
- **D-09:** `ServerRepository` class in `switchboard/registry/repository.py` with async methods: `create()`, `get_by_name()`, `get_by_id()`, `list_all()`, `update_status()`, `update_container_id()`, `delete()`. All SQL behind a clean interface.
- **D-10:** Async session management uses `async_sessionmaker` (defined in `switchboard/db/session.py`). Repository methods accept a session argument. FastAPI (Phase 2) injects sessions via `Depends()`; tests pass a test session directly.
- **D-11:** SQLAlchemy ORM model and Pydantic schemas are separate types from day one. ORM model in `switchboard/registry/models.py`; Pydantic schemas in `switchboard/registry/schemas.py`.

### Test database strategy
- **D-12:** Integration tests require a pre-running PostgreSQL instance (via `docker compose up` before running `uv run pytest`). No testcontainers dependency.
- **D-13:** A pytest session-scoped fixture applies Alembic migrations once per test session. Individual test isolation is via transaction rollback — each test runs inside a transaction that rolls back after completion.
- **D-14:** Tests use a separate `switchboard_test` database configured via `TEST_DATABASE_URL` environment variable. Dev data is never polluted by tests.

### Claude's Discretion
- Exact Alembic migration file naming and `env.py` configuration details
- `conftest.py` structure for shared fixtures
- Logging setup in `switchboard/db/` for query debugging
- SQLAlchemy pool configuration (pool size, timeout)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — PLAT-03 (Python package structure constraint), full v1 requirements for traceability

### Project constraints
- `.planning/PROJECT.md` — Language constraint (Python 3.12+), package structure constraint (`switchboard/` not `src/`), containerization requirements

### Technology stack
- `.planning/STACK.md` (in `.planning/research/`) — Confirmed versions: SQLAlchemy 2.0.49, asyncpg 0.31.0, Alembic 1.18.4, pydantic-settings 2.13.1, PyJWT 2.12.1; async driver `postgresql+asyncpg://`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None yet — brand new project. Only `pyproject.toml` exists with no dependencies.

### Established Patterns
- None yet — Phase 1 establishes the patterns that all subsequent phases follow.

### Integration Points
- `switchboard/db/session.py` → imported by Phase 2 (Admin API) for `Depends()` session injection
- `switchboard/config.py` → imported by all phases for database URL and future config values
- `switchboard/registry/repository.py` → imported by Phase 2 (Admin API), Phase 3 (Container Manager), Phase 6 (Health Monitor)

</code_context>

<specifics>
## Specific Ideas

- No specific references beyond the technology stack decisions already captured in REQUIREMENTS.md and the research stack file.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 01-foundation*
*Context gathered: 2026-04-14*
