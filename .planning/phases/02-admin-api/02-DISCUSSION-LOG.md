# Phase 2: Admin API - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-15
**Phase:** 02-admin-api
**Areas discussed:** JWT signing key strategy, Duplicate server response, URL structure, Error response format

---

## JWT Signing Key Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| HMAC shared secret (HS256) | Single OPERATOR_JWT_SECRET env var; simplest setup | ✓ |
| RSA static public key (RS256) | PEM public key env var; supports key rotation | |
| JWKS endpoint (RS256) | Fetches keys from JWKS_URI at startup; most flexible | |

**User's choice:** HMAC shared secret (HS256)
**Notes:** Sufficient for an operator-only API where the platform controls both sides.

---

## Duplicate Server Response

| Option | Description | Selected |
|--------|-------------|----------|
| 409 Conflict | Standard HTTP convention for uniqueness conflicts | ✓ |
| 422 Unprocessable Entity | FastAPI default for validation errors; less precise | |
| 200 OK with existing record | Idempotent upsert; hides duplicates silently | |

**User's choice:** 409 Conflict
**Notes:** `DuplicateServerError` from repository maps cleanly to 409.

---

## URL Structure

| Option | Description | Selected |
|--------|-------------|----------|
| /servers (flat) | Matches roadmap success criteria exactly | |
| /api/v1/servers | Versioned prefix; forward-compatible | ✓ |
| /admin/servers | Namespaced prefix; explicit admin scope | |

**User's choice:** /api/v1/servers
**Notes:** Version prefix provides forward compatibility for future breaking changes.

---

## Error Response Format

| Option | Description | Selected |
|--------|-------------|----------|
| FastAPI default {"detail": "..."} | Zero custom code; consistent with OpenAPI tooling | ✓ |
| Custom {"error": "code", "message": "..."} | Structured for programmatic parsing; requires custom handler | |
| RFC 7807 Problem Details | Standard {type, title, status, detail}; most setup | |

**User's choice:** FastAPI default `{"detail": "..."}`
**Notes:** Simplest approach; appropriate for an operator-internal API.

---

## Claude's Discretion

- FastAPI app entry point location
- JWT token expiry validation details
- Uvicorn startup command and port
- OpenAPI metadata strings

## Deferred Ideas

- Token issuance endpoint — post-v1
- Multiple API keys with RBAC (ADMN-01) — v2
- Server update/soft-delete endpoints (SREG-04, SREG-05) — v2
