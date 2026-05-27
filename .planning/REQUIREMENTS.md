# Requirements: Switchboard

**Defined:** 2026-04-14
**Core Value:** Organizations can deploy, manage, and govern MCP servers in one place — customers get a single, secure access point without needing to discover or connect to individual servers themselves.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Server Registry

- [ ] **SREG-01**: Operator can register a new MCP server (name, container image, description) via Admin API
- [ ] **SREG-02**: Operator can list all registered servers with their current status via Admin API
- [ ] **SREG-03**: Operator can retrieve details for a specific registered server via Admin API

### Container Lifecycle

- [ ] **CONT-01**: Operator can start a registered server container via Admin API
- [ ] **CONT-02**: Operator can stop a running server container via Admin API
- [ ] **CONT-03**: Operator can restart a running server container via Admin API
- [ ] **CONT-04**: Platform periodically polls each server's health and exposes current health status via Admin API

### Gateway

- [ ] **GTWY-01**: Customer requests to `/servers/{server-name}` are routed to the corresponding registered container
- [ ] **GTWY-02**: Gateway proxies MCP Streamable HTTP transport (POST for client→server messages, GET for SSE server→client streams) on the `/mcp` endpoint
- [ ] **GTWY-03**: Gateway tracks `Mcp-Session-Id` headers and routes requests with an existing session ID to the same container instance

### Security

- [ ] **SECU-01**: Gateway validates JWT Bearer token on every customer request; returns `401 Unauthorized` with `WWW-Authenticate` header on failure
- [ ] **SECU-02**: Gateway terminates TLS for all customer-facing traffic; backend container communication uses the internal network unencrypted

### Observability

- [ ] **OBSV-01**: Gateway emits structured JSON logs for each request including trace ID, user identity (from JWT), server name, tool name (if applicable), HTTP status, and timestamp

### Reference Servers

- [ ] **REFS-01**: Echo server container exposes an MCP tool that returns its input arguments unchanged — validates round-trip request routing
- [ ] **REFS-02**: Ping server container responds to the MCP `ping` method — validates connection health and container liveness

### Platform Infrastructure

- [ ] **PLAT-01**: All platform components (gateway, admin API, reference servers, database) run locally via Docker Compose for development
- [ ] **PLAT-02**: Production deployment targets AWS ECS Fargate with one task per MCP server container
- [ ] **PLAT-03**: Top-level Python package is `switchboard/` (not `src/`); Python 3.12+

## v2 Requirements

Deferred to after v1 validation. Tracked but not in current roadmap.

### Server Registry

- **SREG-04**: Operator can update server registration metadata (image tag, description) via Admin API
- **SREG-05**: Operator can deactivate (soft-delete) a server — gateway stops routing to it but record is retained
- **SREG-06**: Operator sets server approval state (pending → approved → disabled); gateway rejects routing to non-approved servers

### Security

- **SECU-03**: Gateway exposes `/.well-known/oauth-protected-resource` per RFC 9728 so spec-compliant MCP clients auto-discover auth configuration
- **SECU-04**: Rate limiting per server (token bucket algorithm); returns `429 Too Many Requests` with `Retry-After` header on excess traffic

### Container Lifecycle

- **CONT-05**: Per-server environment variable injection — operator registers per-server secrets via Admin API; injected into container at start time (encrypted at rest)

### Gateway

- **GTWY-04**: Gateway supports legacy SSE transport (deprecated MCP spec) for backward compatibility with older clients

### Observability

- **OBSV-02**: Platform exposes OpenTelemetry-compatible metrics (`mcp_requests_total`, `mcp_tool_duration_seconds`, `mcp_active_connections`) at a Prometheus-compatible `/metrics` endpoint

### Admin Access

- **ADMN-01**: Admin API supports multiple API keys with role-based scopes (`admin:read`, `admin:write`, `admin:server:lifecycle`) for CI pipelines and read-only auditors

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Per-customer server ACLs | No confirmed requirement — all customers see the same approved catalog. Add only after access-control requirements are validated. |
| Aggregated `tools/list` across all servers | N+1 fan-out latency, partial-failure semantics, forces tool name namespacing. Client should call each server's tools endpoint directly. |
| Billing / usage metering | Separate data pipeline concern. Usage can be derived from structured logs by an external system. |
| Web UI / admin dashboard | v1 operators are technical; API-first until UI ROI is established. |
| Customer self-service server deployment | Distinct security model (multi-tenant execution, container isolation). v1 is operator-managed only. |
| Server-to-server communication | Creates hidden dependencies and lateral movement vectors. Cross-server orchestration belongs at the agent/client layer. |
| Real-time webhook / event bus for tool outputs | Requires event bus infrastructure (SQS/Kafka). No validated demand. |
| Rolling restarts without downtime | High complexity. v1 can accept brief downtime during container replacement. |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PLAT-03 | Phase 1 | Pending |
| SREG-01 | Phase 2 | Pending |
| SREG-02 | Phase 2 | Pending |
| SREG-03 | Phase 2 | Pending |
| CONT-01 | Phase 3 | Pending |
| CONT-02 | Phase 3 | Pending |
| CONT-03 | Phase 3 | Pending |
| REFS-01 | Phase 4 | Pending |
| REFS-02 | Phase 4 | Pending |
| GTWY-01 | Phase 5 | Pending |
| GTWY-02 | Phase 5 | Pending |
| GTWY-03 | Phase 5 | Pending |
| SECU-01 | Phase 5 | Pending |
| SECU-02 | Phase 5 | Pending |
| OBSV-01 | Phase 5 | Pending |
| PLAT-01 | Phase 5 | Pending |
| CONT-04 | Phase 8 (gap closure) | Pending |
| PLAT-02 | Phase 8 (gap closure) | Pending |

**Coverage:**
- v1 requirements: 18 total
- Mapped to phases: 18
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-14*
*Last updated: 2026-04-14 after roadmap creation*
