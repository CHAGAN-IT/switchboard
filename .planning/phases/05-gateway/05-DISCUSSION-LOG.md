# Phase 5: Gateway - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-16
**Phase:** 05-gateway
**Areas discussed:** Customer JWT configuration, Gateway app structure, Request routing strategy, Session stickiness scope

---

## Customer JWT configuration

| Option | Description | Selected |
|--------|-------------|----------|
| Separate CUSTOMER_JWT_SECRET | Separate env var, distinct from OPERATOR_JWT_SECRET. Full isolation: independent secrets per auth domain. | ✓ |
| Same secret, different audience | One OPERATOR_JWT_SECRET, two audiences. Simpler config but weaker isolation. | |
| You decide | Claude picks based on security best practices. | |

**User's choice:** Separate CUSTOMER_JWT_SECRET

| Claims option | Description | Selected |
|--------|-------------|----------|
| Standard claims: exp, iat, sub | Require expiry, issued-at, user identity. sub becomes user_identity in logs. | ✓ |
| Standard + custom scope claim | Add scope/access claim for future ACL use — logged but not enforced. | |
| Minimal: exp only | Just validate signature and expiry. Logs show anonymous user. | |

**User's choice:** Standard claims only (exp, iat, sub)

---

## Gateway app structure

| Option | Description | Selected |
|--------|-------------|----------|
| Standalone FastAPI app + own docker-compose service | switchboard/gateway/app.py, separate process, own port. Clear security boundary. | ✓ |
| Sub-app mounted on admin API | app.mount() on existing admin app. Single process, simpler compose. Weaker isolation. | |

**User's choice:** Standalone — separate FastAPI app

| Port option | Description | Selected |
|--------|-------------|----------|
| 8080 | Gateway on localhost:8080, Admin API stays on 8000. Common convention. | ✓ |
| 9000 | Larger gap from admin port. | |
| You decide | Claude picks non-conflicting port. | |

**User's choice:** Port 8080

---

## Request routing strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Stateless: route by name, 503 on connection failure | No DB connection. httpx ConnectError → 503. Fast path, minimal dependencies. | ✓ |
| Stateful: DB lookup first, 404/503 based on registry status | DB round-trip per request. Better error messages. Gateway depends on PostgreSQL. | |
| Hybrid: DB lookup for 404 only | Check registration (404 if unknown), skip status check, return 503 on connect failure. | |

**User's choice:** Stateless routing

| 404 option | Description | Selected |
|--------|-------------|----------|
| 404 with detail message | Return {"detail": "Server 'name' not found"} — consistent with Admin API format. | ✓ |
| 404 with empty body | Less revealing but harder to debug. | |
| You decide | Claude handles error format based on Admin API consistency. | |

**User's choice:** 404 with detail message (applied via name pattern validation before connection attempt)

**Notes:** Stateless routing means true 404 vs 503 cannot be distinguished after connection attempt. Server name pattern validation (`^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$`) provides a 404 path for syntactically invalid names without a DB round-trip.

---

## Session stickiness scope

| Option | Description | Selected |
|--------|-------------|----------|
| Real in-memory map: session_id → container address | dict mapping Mcp-Session-Id to backend URL. asyncio.Lock for safety. GTWY-03 compliant. Future-proof. | ✓ |
| No-op: forward to sb-{name}, pass session header through | No routing map. Trivially satisfied in Phase 5 (one container per server). Revisit in Phase 7. | |

**User's choice:** Real in-memory map

---

## Claude's Discretion

- httpx AsyncClient lifespan management
- Middleware vs. route-level trace ID generation
- structlog processor chain details
- SSE stream buffering approach
- docker-compose healthcheck for gateway service
- asyncio.Lock placement

## Deferred Ideas

- Redis-backed session store (for multi-process deployments)
- Customer token issuance endpoint — v2
- Rate limiting — v2
- Legacy SSE transport — v2
