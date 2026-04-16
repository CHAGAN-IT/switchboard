# Phase 5: Gateway - Context

**Gathered:** 2026-04-16
**Status:** Ready for planning

<domain>
## Phase Boundary

A customer holding a valid JWT can send MCP requests to `/servers/{server-name}/mcp` and have them transparently proxied to the correct running container. The gateway validates customer JWTs, strips the `Authorization` header before forwarding, proxies both POST (client→server) and GET (SSE server→client streams) on the `/mcp` endpoint, tracks `Mcp-Session-Id` for session stickiness, serves `GET /.well-known/oauth-protected-resource` per RFC 9728, and emits structured JSON logs. The full local Docker Compose topology (gateway, admin API, PostgreSQL, both reference servers) runs successfully after this phase.

This phase does not include health monitoring (Phase 6) or AWS deployment (Phase 7).

</domain>

<decisions>
## Implementation Decisions

### Customer JWT Authentication
- **D-01:** Gateway uses a separate `CUSTOMER_JWT_SECRET` environment variable — distinct from `OPERATOR_JWT_SECRET` used by the Admin API. Add this field to `Settings` in `switchboard/config.py`.
- **D-02:** Customer token audience is `switchboard-gateway`. Operator token audience remains `switchboard-admin`. The gateway auth dependency rejects tokens with wrong audience.
- **D-03:** Required claims: `exp` (expiry), `iat` (issued-at), `sub` (user identity for structured logs). Algorithm: HS256 (same as operator auth). The `sub` claim value is included in every structured log line as the user identity field (OBSV-01).
- **D-04:** JWT validation failure returns HTTP 401 with `WWW-Authenticate: Bearer` header — identical pattern to `require_operator` in `switchboard/admin/auth.py`. Create `require_customer` dependency in `switchboard/gateway/auth.py`.

### Gateway App Structure
- **D-05:** Standalone FastAPI app in `switchboard/gateway/app.py` — completely separate from the Admin API app. Own uvicorn process, own docker-compose service.
- **D-06:** Gateway docker-compose service exposes host port **8080** (internal container port 8000, consistent with other services). Admin API remains on its existing port.
- **D-07:** Gateway joins the `switchboard-internal` Docker network (to reach backend containers) AND needs a published host port for customer access. Both network entries are required in docker-compose.

### Request Routing Strategy
- **D-08:** Stateless routing — no database connection in the gateway. Route by server name only: forward to `http://sb-{name}:8000/mcp`. If the backend is unreachable (container stopped, name doesn't resolve), httpx raises a `ConnectError`; gateway returns HTTP 503 with `{"detail": "Server '{name}' is unavailable"}`.
- **D-09:** Server name from URL path is validated against the name pattern (`^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$`) before forwarding. Invalid names return 404 with `{"detail": "Server '{name}' not found"}` — no connection attempt made.
- **D-10:** The `Authorization` header is stripped from the forwarded request before it reaches the backend container (SC-4). Backend containers never receive the customer's Bearer token.
- **D-11:** All other headers (including `Mcp-Session-Id`, `Content-Type`, `Accept`) are forwarded unchanged.

### Session Stickiness
- **D-12:** Real in-memory session map: a `dict[str, str]` mapping `Mcp-Session-Id` → backend container URL (e.g., `"abc123" → "http://sb-echo:8000"`). Protected by `asyncio.Lock()` for concurrent request safety.
- **D-13:** First request with a new `Mcp-Session-Id`: record the target container URL in the map before forwarding. Subsequent requests with the same session ID: use the recorded URL, regardless of the server name in the path (spec-correct behavior).
- **D-14:** Requests without `Mcp-Session-Id`: route normally by server name without map lookup.

### Structured Logging (OBSV-01)
- **D-15:** Use `structlog` (already in stack) with JSON output. Each proxied request produces one structured log line with fields: `trace_id` (UUID v4 generated per request), `user_identity` (from JWT `sub` claim), `server_name` (from URL path), `http_method`, `http_status`, `timestamp` (ISO 8601). Tool name is logged if extractable from request body.
- **D-16:** Log emission is in a middleware or route wrapper — not inside the httpx call — so it captures the final status code before responding.

### RFC 9728 Well-Known Endpoint
- **D-17:** `GET /.well-known/oauth-protected-resource` returns a JSON document with `resource` (the gateway base URL) and `bearer_tokens_supported: true`. Minimal compliant implementation — no full OAuth authorization server metadata. Claude's discretion on exact field set per RFC 9728 §2.

### Claude's Discretion
- httpx `AsyncClient` lifespan management (startup/shutdown event or `asyncio_client` dependency)
- Whether to use FastAPI middleware or route-level injection for trace ID generation
- Exact structlog processor chain (JSON renderer, timestamp format)
- How to handle SSE stream buffering (whether to set `Transfer-Encoding: chunked` or use `StreamingResponse`)
- Whether to add a docker-compose `healthcheck` for the gateway service (recommended)
- `asyncio.Lock` placement (module-level singleton vs. app state)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — GTWY-01, GTWY-02, GTWY-03, SECU-01, SECU-02, OBSV-01, PLAT-01 (all Phase 5 requirements)

### Project constraints
- `.planning/PROJECT.md` — Python 3.12+, `switchboard/` top-level package, Docker/containerization requirement, OAuth/JWT auth constraint

### Phase decisions (locked — do not re-decide)
- `.planning/phases/01-foundation/01-CONTEXT.md` — D-01 (subpackage structure including `switchboard/gateway/`), D-05 (ServerStatus enum), D-08 (server name pattern `^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$`)
- `.planning/phases/02-admin-api/02-CONTEXT.md` — D-01 (JWT validation pattern: PyJWT HS256, `WWW-Authenticate: Bearer`), D-04 (error response format `{"detail": "..."}`)
- `.planning/phases/03-container-manager/03-CONTEXT.md` — D-01 (`switchboard-internal` network), D-02 (container naming `sb-{name}`), D-03 (container port 8000)

### Technology stack
- `.planning/research/STACK.md` — httpx 0.28.1 (async proxy), httpx-sse 0.4.0 (SSE streaming), structlog 25.x (structured logging), PyJWT 2.12.1, FastAPI 0.135.3, Uvicorn 0.44.0

### MCP specification
- MCP Streamable HTTP transport: https://modelcontextprotocol.io/specification/2025-03-26/basic/transports — POST for client→server, GET for SSE server→client streams; `Mcp-Session-Id` header semantics

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `switchboard/admin/auth.py` — `require_operator()` dependency: exact pattern to replicate as `require_customer()` in `switchboard/gateway/auth.py`. Same PyJWT decode flow, same 401 response shape, different secret and audience.
- `switchboard/admin/app.py` — FastAPI app factory pattern to replicate in `switchboard/gateway/app.py`
- `switchboard/config.py` — `Settings` class + `get_settings()` with `lru_cache` — extend with `customer_jwt_secret: str` field (same validator pattern as `operator_jwt_secret`)
- `switchboard/registry/models.py` — `SERVER_NAME_PATTERN` regex (if extracted) or re-implement the same pattern `^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$` for path validation
- `docker-compose.yml` — `switchboard-internal` network already defined; echo and ping services already present with healthchecks

### Established Patterns
- `from __future__ import annotations` + `TYPE_CHECKING` block in all files
- `lru_cache` on `get_settings()` — never instantiate `Settings` directly
- FastAPI `Depends()` for auth and settings injection
- `{"detail": "..."}` error response envelope — consistent across Admin API and gateway
- Docker services join `switchboard-internal` network with no published ports (exception: gateway publishes 8080)

### Integration Points
- `switchboard/config.py`: Add `customer_jwt_secret: str` field with same 32-byte minimum validator
- `docker-compose.yml`: Add `gateway` service with `build: .`, `ports: ["8080:8000"]`, `networks: [switchboard-internal]`, `depends_on: [db, echo, ping]`
- `switchboard/gateway/__init__.py`: Already stubbed as empty package (Phase 1 D-01)

</code_context>

<specifics>
## Specific Ideas

- The `Authorization` header strip is non-negotiable (success criterion SC-4) — backend containers must never see the customer's token
- The session stickiness map should be initialized at app startup (app lifespan or module-level), not per-request
- For testing Phase 5, a helper script or fixture to generate valid customer JWTs (using `CUSTOMER_JWT_SECRET`) will be needed — no token issuance endpoint exists yet

</specifics>

<deferred>
## Deferred Ideas

- Multiple MCP container instances per server name (true load balancing) — the session stickiness map is designed for this but routing is single-instance in Phase 5
- Redis-backed session store (for multi-process gateway instances) — in-memory is sufficient for v1 single-process deployment
- Customer token issuance endpoint (Authlib OAuth2 server, SECU-03 full implementation) — v2 per REQUIREMENTS.md
- Rate limiting per server (SECU-04) — v2 requirement
- Legacy SSE transport support (GTWY-04) — v2 requirement

</deferred>

---

*Phase: 05-gateway*
*Context gathered: 2026-04-16*
