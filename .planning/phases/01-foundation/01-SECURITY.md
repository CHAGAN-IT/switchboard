---
phase: 01
slug: foundation
status: verified
threats_open: 0
asvs_level: 1
created: 2026-04-15
---

# Phase 01 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| User input → ORM model | Server name validated by regex at model level before any DB interaction | Server name string (untrusted) |
| Environment → Alembic config | Database URL read from env vars via pydantic-settings | Database credentials (sensitive) |
| Repository input → SQL | All queries parameterized via SQLAlchemy ORM | Query parameters (untrusted) |
| Test database | Separate `switchboard_test` DB prevents dev data pollution | Test data only |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-02-01 | Tampering | switchboard/registry/models.py | mitigate | `@validates("name")` at `models.py:91-104` enforces `^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$`; all queries via SQLAlchemy ORM (no raw SQL) | closed |
| T-02-02 | Tampering | switchboard/registry/models.py | mitigate | `ServerStatus(enum.Enum)` at `models.py:27-35`; `Mapped[ServerStatus]` at `models.py:73-76` enforces valid values at Python + PostgreSQL enum layers | closed |
| T-02-03 | Information Disclosure | alembic/env.py | mitigate | `get_url()` at `env.py:36-52` reads from env/config/`get_settings()`; `alembic.ini:89` has `sqlalchemy.url =` (empty — no hardcoded credentials) | closed |
| T-02-04 | Elevation of Privilege | alembic migrations | accept | See Accepted Risks Log | closed |
| T-03-01 | Tampering | switchboard/registry/repository.py | mitigate | All queries use `sqlalchemy.select()` and `session.get()` ORM methods (`repository.py:19,98,111`); no raw SQL strings; name validated by model `@validates` before any DB write | closed |
| T-03-02 | Tampering | switchboard/registry/repository.py | mitigate | `IntegrityError` caught at `repository.py:68-72`, session rolled back, wrapped in `DuplicateServerError`; raw DB error never propagated | closed |
| T-03-03 | Information Disclosure | tests/conftest.py | accept | See Accepted Risks Log | closed |
| T-03-04 | Denial of Service | switchboard/registry/repository.py | accept | See Accepted Risks Log | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01 | T-02-04 | Alembic migrations run with full DB privileges during development. Acceptable for v1 local dev; production uses RDS with IAM-scoped credentials (Phase 7 remediation). | architect | 2026-04-15 |
| AR-02 | T-03-03 | Test database uses default dev credentials (`postgres:postgres`). Acceptable for local-only test runs; production uses AWS Secrets Manager (Phase 7 remediation). | architect | 2026-04-15 |
| AR-03 | T-03-04 | `list_all()` has no pagination. Acceptable at v1 scale (< 100 servers); Phase 2 Admin API layer will add pagination if needed. | architect | 2026-04-15 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-04-15 | 8 | 8 | 0 | gsd-security-auditor (ASVS L1) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-04-15
