# SECURITY.md — Switchboard

**Phase:** 01-foundation (plans 01-02 and 01-03)
**ASVS Level:** 1
**Audit Date:** 2026-04-15
**Auditor:** gsd-security-auditor (claude-sonnet-4-6)

---

## Threat Verification

All five mitigate-disposition threats from the Phase 01 threat register are CLOSED. All three accepted risks are present in the accepted risks log below.

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-02-01 | Tampering | mitigate | CLOSED | `switchboard/registry/models.py:24` — `SERVER_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")`. `models.py:91-104` — `@validates("name")` calls `SERVER_NAME_PATTERN.match(value)` and raises `ValueError` on mismatch. All queries issued through SQLAlchemy ORM; no raw SQL strings present. |
| T-02-02 | Tampering | mitigate | CLOSED | `switchboard/registry/models.py:27-35` — `class ServerStatus(enum.Enum)` with exactly three members (`stopped`, `running`, `error`). `models.py:73-76` — `status: Mapped[ServerStatus]` enforces enum at Python layer; migration creates a PostgreSQL enum type enforcing it at database layer. |
| T-02-03 | Information Disclosure | mitigate | CLOSED | `alembic/env.py:36-52` — `get_url()` reads from `DATABASE_URL` env var, then `config.get_main_option("sqlalchemy.url")`, then `get_settings().database_url`. No credentials hardcoded. `alembic.ini:89` — `sqlalchemy.url =` (empty value confirmed). |
| T-02-04 | Elevation of Privilege | accept | CLOSED | See accepted risks log below. |
| T-03-01 | Tampering | mitigate | CLOSED | `switchboard/registry/repository.py:19,98,111` — all queries use `sqlalchemy.select()` and `session.get()` ORM methods with parameterized bindings; no raw SQL strings found anywhere in repository.py. Server name validated by `@validates("name")` at model layer before any database operation. |
| T-03-02 | Tampering | mitigate | CLOSED | `switchboard/registry/repository.py:68-72` — `except IntegrityError as exc: await session.rollback(); raise DuplicateServerError(name) from exc`. Database-level IntegrityError is caught, session is reset, and a domain exception is raised. Raw database error is never propagated to the caller. |
| T-03-03 | Information Disclosure | accept | CLOSED | See accepted risks log below. |
| T-03-04 | Denial of Service | accept | CLOSED | See accepted risks log below. |

---

## Accepted Risks Log

| Threat ID | Category | Component | Risk Description | Acceptance Rationale | Planned Remediation |
|-----------|----------|-----------|-----------------|----------------------|---------------------|
| T-02-04 | Elevation of Privilege | alembic migrations | Alembic migrations run with full database privileges (DDL + DML). A compromised migration environment could execute arbitrary schema or data changes. | Acceptable for local development. Alembic requires schema-level access by design. | Phase 7: Production uses AWS RDS with IAM-scoped credentials. Migration user will be restricted to schema management only; application user will have DML-only access. |
| T-03-03 | Information Disclosure | tests/conftest.py | Test database URL uses default dev credentials (`postgres:postgres`). These credentials are visible in source and environment. | Acceptable for local development against a containerized test database. Credentials provide access only to the disposable test database (`switchboard_test`). | Phase 7: Production uses AWS Secrets Manager to inject credentials. Test CI environment will use ephemeral per-run credentials. |
| T-03-04 | Denial of Service | switchboard/registry/repository.py | `list_all()` fetches all server records with no pagination limit. A large server registry could cause memory pressure or slow responses. | Acceptable for v1 scale. The platform targets fewer than 100 registered servers in initial deployment. No external attacker can call `list_all()` directly in Phase 1 (no public API yet). | Phase 2: Admin API will expose this method. If operator-controlled data volume remains bounded, pagination is optional. Add cursor-based pagination in Phase 2 if API design warrants it. |

---

## Unregistered Threat Flags

No `## Threat Flags` section was present in either `01-02-SUMMARY.md` or `01-03-SUMMARY.md`. No unregistered flags to report.

---

## Scope

This audit covers Phase 01-foundation plans 02 and 03 only:

- `switchboard/registry/models.py` — Server ORM model, ServerStatus enum, name validation
- `switchboard/registry/schemas.py` — Pydantic request/response schemas (no threats registered)
- `switchboard/registry/repository.py` — ServerRepository async CRUD methods
- `alembic/env.py` — Async migration environment configuration
- `alembic.ini` — Alembic configuration file

Out of scope for this audit: authentication, authorization, Admin API endpoints, gateway proxy, container orchestration. These will be audited in their respective phases.
