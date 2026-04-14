# Feature Research

**Domain:** Managed MCP hosting platform (gateway + container orchestration + operator-controlled access)
**Researched:** 2026-04-14
**Confidence:** HIGH — multiple authoritative sources (MCP official spec, Microsoft/AWS/Red Hat implementations, Nordic APIs review of 10 platforms, Maxim and MintMCP enterprise gateway comparisons)

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features operators and customers assume exist. Missing these = platform is unusable or insecure.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Server registration via Admin API** | Operators need to add/remove MCP servers dynamically without redeployment | MEDIUM | CRUD endpoints: register, list, update, deactivate. Replaces config-file approach that breaks hot-reload |
| **Path-based request routing** | Customers expect a single stable URL; platform routes to correct server by path segment | MEDIUM | `/servers/{server-name}` pattern is the industry-standard namespace approach (LiteLLM, Microsoft gateway both use it) |
| **JWT/OAuth 2.1 authentication** | MCP spec (2025-11-25) mandates OAuth 2.1 for HTTP transport; every enterprise platform requires it | HIGH | Must include: Bearer token validation on every request, 401 with WWW-Authenticate on failure, PKCE for interactive flows |
| **Streamable HTTP transport support** | MCP spec deprecated SSE in March 2025 (v1.10.0 TypeScript SDK); all production clients expect Streamable HTTP | MEDIUM | Must maintain backward compat with SSE (older clients exist); Streamable HTTP is the current standard |
| **Container-per-server isolation** | Security boundary between servers; prevents a compromised server from affecting others | MEDIUM | Each server runs in its own container. Docker Compose locally, ECS/EKS in production |
| **Server health monitoring** | Operators cannot manage what they cannot observe; unhealthy containers need detection | MEDIUM | Health check endpoint on each server, periodic polling, status exposed in Admin API |
| **Basic structured logging** | Compliance, debugging, incident response all require request-level audit trails | MEDIUM | JSON structured logs with trace IDs, session IDs, user identity, tool name, timestamp. RFC 5424 severity levels |
| **Server lifecycle management** | Operators need to start, stop, and update individual servers without full platform restart | HIGH | Start/stop/restart per server via Admin API; rolling updates without customer downtime |
| **Tool discovery proxying** | Customers must be able to call `tools/list` and get a response from the correct server | LOW | The platform proxies the standard MCP `tools/list` RPC to the target server; no server-side aggregation required in v1 |
| **Error propagation** | Clients expect standard HTTP status codes and MCP error envelopes, not opaque 502s | LOW | Gateway maps internal errors to correct HTTP status (401, 403, 404, 502, 503) with structured error bodies |
| **HTTPS termination** | All production MCP traffic must be TLS-encrypted (MCP spec requirement) | LOW | TLS at the gateway layer; backend containers communicate over internal network unencrypted |

### Differentiators (Competitive Advantage)

Features not universally expected but valued by operators deploying at scale.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Operator-controlled server approval** | Only whitelisted servers reachable by customers; security teams control the catalog | MEDIUM | Approval state on each registered server (pending/approved/disabled); gateway rejects routing to unapproved servers |
| **Rate limiting per server** | Prevents a single runaway agent or misconfigured client from exhausting one server | MEDIUM | Token bucket per server, configurable limit, returns 429 with Retry-After header |
| **Session affinity (stateful routing)** | Some MCP servers carry session state; routing breaks if different requests hit different instances | HIGH | Mcp-Session-Id header tracking (per MCP spec 2025-11-25); sticky routing to same container instance. Required for stateful servers |
| **Centralized tool namespace collision prevention** | Multiple servers may expose tools with the same name; namespacing prevents ambiguity | LOW | Prefix tool names with server name in aggregated `tools/list` responses (e.g., `filesystem__read_file`) |
| **OpenTelemetry metrics export** | Platform engineers want to feed gateway metrics into Grafana/Datadog/Honeycomb | MEDIUM | Expose Prometheus-compatible `/metrics` endpoint and OTLP traces. Key metrics: `mcp_requests_total`, `mcp_tool_duration_seconds`, `mcp_active_connections` |
| **Per-server environment variable injection** | Each MCP server needs its own secrets (API keys, config) without sharing a global env | MEDIUM | Operator registers per-server env vars via Admin API; injected at container start. Fernet-encrypted at rest |
| **Server version pinning** | Operators need reproducible deployments; "latest" is a footgun in production | MEDIUM | Store image tag or git ref per server registration; Admin API field for version |
| **Rolling restarts without downtime** | Updating a server image should not drop in-flight customer requests | HIGH | Drain connections, start new container, cut over, stop old. Requires careful SSE/Streamable HTTP session handling |
| **Admin API key scoping** | Multiple operators (team leads, CI pipelines, read-only auditors) need different permission levels | MEDIUM | Admin API supports multiple keys with role-based scopes: `admin:read`, `admin:write`, `admin:server:lifecycle` |
| **Reference server validation** | New MCP server images should pass protocol conformance before going live | MEDIUM | Automated ping/echo against registered server before marking it available; catches misconfigured servers early |
| **Request replay protection** | Replayed tokens or duplicate requests should not double-execute tool calls | MEDIUM | Short-lived JWTs + nonce tracking or token expiry enforcement at gateway |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem obviously good but introduce disproportionate complexity in v1.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Per-customer server ACLs** | "Customer A should see servers 1,2,3; Customer B should see 1,4" | Requires a full authorization matrix, a membership/group service, and complicates every routing decision. No confirmed requirement yet | Start with all-or-nothing customer access; add ACLs after access-control requirements are validated |
| **Aggregated `tools/list` across all servers** | "One call returns all tools from all servers" | N+1 fan-out latency on every tool discovery. Partial failures make the aggregate unreliable. Forces tool name namespacing to work correctly | Require clients to list a specific server's tools via namespaced endpoint; aggregation is a v2 feature |
| **Built-in billing / usage metering** | "Track per-customer token usage for billing" | Billing requires its own data pipeline, storage, and reconciliation logic. Adds a hard dependency on a revenue-critical path | Log usage to structured logs; let an external system (Stripe, internal BI) consume log data for billing |
| **Web UI / admin dashboard** | "Operators want a UI to manage servers" | A UI is a separate product that must be kept in sync with the API. v1 operators are technical; API is the right surface | Ship a well-designed Admin REST API with OpenAPI docs; UI can be built later by consumers |
| **Customer self-service server deployment** | "Let customers bring their own servers" | Multi-tenant server execution requires complete container security isolation (namespacing, seccomp, network policies). Massively expands attack surface | v1 is operator-managed only. Customer-deployed servers are a separate product with distinct security requirements |
| **Server-to-server communication** | "Server A should be able to call server B's tools" | Creates hidden dependencies between servers, makes lifecycle management unpredictable, and opens lateral movement vectors | Servers are independent; cross-server orchestration happens at the agent/client layer, not the platform layer |
| **Real-time streaming of all tool outputs** | "Push all tool call results to a webhook or event bus" | Requires an event bus (Kafka/SQS), fanout infrastructure, and delivery guarantees. Most customers don't need this | Tool call responses are returned synchronously via Streamable HTTP; async patterns added only after validated demand |

---

## Feature Dependencies

```
[Server Registration]
    └──requires──> [Admin API]
                       └──requires──> [Admin authentication/authorization]

[Request Routing]
    └──requires──> [Server Registration]
    └──requires──> [Container lifecycle management]

[Customer access]
    └──requires──> [Request Routing]
    └──requires──> [JWT/OAuth 2.1 authentication]
    └──requires──> [HTTPS termination]

[Session affinity]
    └──requires──> [Request Routing]
    └──requires──> [Mcp-Session-Id header tracking]

[Rate limiting]
    └──requires──> [Request Routing]
    └──enhances──> [Health monitoring]

[Health monitoring]
    └──requires──> [Container lifecycle management]
    └──enhances──> [Server lifecycle management]

[OpenTelemetry metrics]
    └──enhances──> [Structured logging]
    └──enhances──> [Health monitoring]

[Operator server approval]
    └──requires──> [Server Registration]
    └──requires──> [Request Routing] (gateway checks approval state before routing)

[Per-server env var injection]
    └──requires──> [Server Registration]
    └──requires──> [Container lifecycle management]

[Tool namespace collision prevention]
    └──requires──> [Tool discovery proxying]
```

### Dependency Notes

- **Request Routing requires Server Registration:** The gateway routing table is built from the server registry. No registry entry = no route.
- **Customer access requires JWT auth AND routing:** Neither works alone. Auth without routing = 404s. Routing without auth = open proxy.
- **Session affinity requires routing:** Sticky routing is a property of the routing layer, not the auth layer. Must be designed into the router from the start; retrofitting is expensive.
- **Operator server approval requires routing AND registration:** The gateway must check approval state on every request. This is a routing-layer concern, not an admin-layer concern.
- **Health monitoring enables lifecycle management:** You cannot confidently restart, drain, or replace a container without knowing its health state.

---

## MVP Definition

### Launch With (v1)

Minimum viable product to validate the core value proposition: a managed, secure, single-endpoint access point for operator-approved MCP servers.

- [ ] **Server registration via Admin API** — Without this, operator cannot populate the catalog. Must support create, read, list, update, soft-delete (deactivate).
- [ ] **Path-based request routing** — Core routing behavior: `/servers/{server-name}` maps to the correct container. This is the product.
- [ ] **JWT token validation on all customer requests** — Security is non-negotiable from day one. No open proxies.
- [ ] **Operator-controlled server approval** — Must enforce that only approved servers are reachable. This is the "governance" value prop.
- [ ] **Container-per-server lifecycle management** — Start, stop, and restart individual server containers. Without this, the platform is not manageable.
- [ ] **Server health monitoring** — Basic health check polling; Admin API exposes server status. Operators need to know what is running.
- [ ] **Streamable HTTP transport** — Required by the MCP spec and all current clients. SSE backward compat is a bonus, not MVP.
- [ ] **Structured request logging** — JSON logs with trace IDs, user identity, server name. Minimum audit trail.
- [ ] **HTTPS termination** — MCP spec requirement. No plaintext customer traffic.
- [ ] **Reference MCP servers (echo/ping)** — Needed to validate the routing architecture works end-to-end. Two servers minimum.

### Add After Validation (v1.x)

Features to add once the core routing + auth + lifecycle pipeline is working and used by real operators.

- [ ] **Rate limiting per server** — Add after observing actual traffic patterns. Start with a sensible global default.
- [ ] **Per-server environment variable injection** — Required for any real server beyond echo/ping. Add in v1.x when registering non-trivial servers.
- [ ] **Session affinity** — Add when a stateful MCP server is onboarded. Premature for pure echo/ping servers.
- [ ] **Admin API key scoping** — Add when multiple operators or CI pipelines need different permissions. One shared admin key is acceptable in v1.
- [ ] **OpenTelemetry metrics export** — Add when platform goes to production and needs integration with monitoring stack.
- [ ] **Tool namespace collision prevention** — Add when multiple servers with overlapping tool names are registered.

### Future Consideration (v2+)

Features to defer until product-market fit is established and requirements are confirmed.

- [ ] **Per-customer server ACLs** — Deferred per PROJECT.md. Validate that operators actually need per-customer granularity before building.
- [ ] **Aggregated tools/list** — Deferred; adds N+1 latency risk. Validate demand before building.
- [ ] **Rolling restarts without downtime** — High complexity; only matters at scale. Container replacement in v1 can accept brief downtime.
- [ ] **Web UI / admin dashboard** — Not needed while operator base is technical. API-first until UI ROI is clear.
- [ ] **Billing / usage metering** — Out of scope per PROJECT.md.
- [ ] **Customer self-service server deployment** — Out of scope per PROJECT.md; distinct security model.

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Server registration (Admin API) | HIGH | MEDIUM | P1 |
| Path-based request routing | HIGH | MEDIUM | P1 |
| JWT/OAuth 2.1 auth | HIGH | HIGH | P1 |
| Operator server approval | HIGH | LOW | P1 |
| Container lifecycle management | HIGH | HIGH | P1 |
| Server health monitoring | HIGH | MEDIUM | P1 |
| Streamable HTTP transport | HIGH | MEDIUM | P1 |
| Structured logging | MEDIUM | MEDIUM | P1 |
| HTTPS termination | HIGH | LOW | P1 |
| Reference servers (echo/ping) | HIGH | LOW | P1 |
| Rate limiting per server | MEDIUM | MEDIUM | P2 |
| Per-server env var injection | HIGH | MEDIUM | P2 |
| Session affinity | MEDIUM | HIGH | P2 |
| Admin API key scoping | MEDIUM | MEDIUM | P2 |
| OpenTelemetry metrics | MEDIUM | MEDIUM | P2 |
| Tool namespace collision prevention | LOW | LOW | P2 |
| Rolling restarts without downtime | MEDIUM | HIGH | P3 |
| Per-customer ACLs | MEDIUM | HIGH | P3 |
| Aggregated tools/list | LOW | HIGH | P3 |
| Web UI / admin dashboard | MEDIUM | HIGH | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

---

## Competitor Feature Analysis

| Feature | Composio | Microsoft MCP Gateway | AWS AgentCore Gateway | Switchboard (target) |
|---------|----------|-----------------------|----------------------|----------------------|
| Server registration | Pre-built catalog only | Kubernetes manifest + API | AWS console + CDK | Admin REST API, dynamic |
| Routing | Path-based, tool-name-based | Session-aware Kubernetes | AWS-managed | Path-based (`/servers/{name}`) |
| Authentication | OAuth 2.1, SSO | Azure Entra ID (RBAC) | AWS IAM + OAuth | JWT/OAuth 2.1, OIDC-compatible |
| Server approval/governance | Curated catalog | Azure role assignment | IAM policy-based | Explicit operator approval state per server |
| Container isolation | Platform-managed | Kubernetes pod-per-server | Managed container runtime | Docker Compose (dev), ECS (prod) |
| Health monitoring | Platform-managed | Kubernetes probes | CloudWatch integration | Periodic health check + Admin API status |
| Rate limiting | Built-in | Azure API Management policies | AWS API Gateway throttling | Per-server token bucket |
| Structured logging | Built-in observability | Azure Monitor + Log Analytics | CloudWatch Logs | JSON structured logs + OTEL |
| Admin API | Limited (tool config) | REST + Kubernetes API | AWS CLI/console/SDK | Purpose-built Admin REST API |
| Dev/local environment | Managed cloud only | Kubernetes-required | AWS-required | Docker Compose full parity |

**Key differentiator for Switchboard:** Python-native, Docker Compose local dev parity, operator-controlled catalog (not vendor curated), simple Admin REST API without Kubernetes or cloud provider lock-in.

---

## Sources

- [Nordic APIs: Review of 10 Managed MCP Platforms](https://nordicapis.com/review-of-10-managed-mcp-platforms/) — feature baseline across platforms (MEDIUM confidence; credible tech publication)
- [Moesif: Comparing MCP Gateways](https://www.moesif.com/blog/monitoring/model-context-protocol/Comparing-MCP-Model-Context-Protocol-Gateways/) — auth patterns and feature comparison
- [Microsoft MCP Gateway (GitHub)](https://github.com/microsoft/mcp-gateway) — session-aware routing, lifecycle management, RBAC (HIGH confidence; official Microsoft open source)
- [Red Hat Developer: Advanced Auth for MCP Gateway](https://developers.redhat.com/articles/2025/12/12/advanced-authentication-authorization-mcp-gateway) — OAuth 2.1, token exchange, Vault integration (HIGH confidence)
- [Maxim: Best MCP Gateways for Enterprises](https://www.getmaxim.ai/articles/best-mcp-gateways-for-enterprises-in-2025/) — enterprise feature requirements, rate limiting, observability (MEDIUM confidence)
- [MintMCP: MCP Gateways Rate Limiting and Access Control](https://www.mintmcp.com/blog/mcp-gateways-rate-limiting-access-control) — rate limiting as table stakes vs differentiator (MEDIUM confidence)
- [DX Heroes: MCP Governance Landscape Early 2026](https://dxheroes.io/insights/mcp-governance-landscape-early-2026) — approval workflows, server catalogs, audit requirements (MEDIUM confidence)
- [MCP Official Authorization Specification (2025-11-25)](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization) — OAuth 2.1 requirements, Streamable HTTP, PKCE (HIGH confidence; official source)
- [Composio: Hosted MCP Platforms](https://composio.dev/content/hosted-mcp-platforms) — platform feature comparison (MEDIUM confidence)
- [Merge.dev: Hosted MCP Platforms](https://www.merge.dev/blog/hosted-mcp-platforms) — observability, governance, DX requirements (MEDIUM confidence)
- [DreamFactory: Designing MCP Servers for Observability](https://blog.dreamfactory.com/designing-mcp-servers-for-observability) — OpenTelemetry, Golden Signals, structured logging patterns (MEDIUM confidence)
- [Zuplo: 6 Must-Have Features of an API Gateway](https://zuplo.com/learning-center/top-api-gateway-features) — API gateway table stakes: caching, rate limiting, circuit breaking, monitoring (HIGH confidence; aligns with all other sources)

---

*Feature research for: Managed MCP hosting platform (Switchboard)*
*Researched: 2026-04-14*
