# Project Research Summary

**Project:** Switchboard — Managed MCP Hosting Platform
**Domain:** MCP gateway + container orchestration + operator-controlled access
**Researched:** 2026-04-14
**Confidence:** HIGH

## Executive Summary

Switchboard is a managed MCP (Model Context Protocol) hosting platform that acts as a secure, operator-governed gateway to a fleet of containerized MCP servers. Experts in this space build it as a three-tier system: a stateless proxy gateway that enforces authentication and routes by URL path, an admin API that manages server registration and container lifecycle, and isolated per-server containers running the MCP protocol. This architecture matches how production-grade MCP gateways are built at Microsoft, Composio, and AWS AgentCore — all of which converge on path-based routing with OAuth 2.1 enforcement and container-per-server isolation as the baseline design.

The recommended approach is a Python-native stack (FastAPI, asyncpg, mcp SDK 1.27+) deployed locally via Docker Compose and in production via ECS Fargate behind an ALB. The gateway is a transparent streaming proxy that adds auth enforcement and registry-backed route resolution without touching MCP protocol semantics. A PostgreSQL registry is the single source of truth for server state, shared (read-only) by the gateway and (read-write) by the admin API. The container management layer is abstracted behind an interface so the same code works with the Docker SDK in development and the ECS API in production.

The most consequential risks are architectural rather than implementation: building for the deprecated SSE transport instead of Streamable HTTP will require a full proxy redesign; forwarding customer bearer tokens to backend containers is a privilege escalation vector that is expensive to fix retroactively; and omitting the `/.well-known/oauth-protected-resource` discovery endpoint breaks spec-compliant clients entirely. All three must be addressed at design time, not patched later. The remaining risks — session affinity, stream buffering, async blocking code — are implementation-time concerns with clear mitigations.

## Key Findings

### Recommended Stack

The stack is well-defined and version-locked. FastAPI 0.135.3 with Uvicorn 0.44.0 handles both the gateway and admin API as separate ASGI apps. The official `mcp` SDK (1.27.0) provides Streamable HTTP transport compliance; FastMCP 3.2.4 is used for reference server implementations only. PostgreSQL 16+ via SQLAlchemy 2.0 async + asyncpg 0.31.0 stores the server registry. All versions were verified against PyPI on the research date.

A critical version decision: use PyJWT 2.12.1 — not python-jose, which is abandoned and generates Python 3.12 deprecation warnings in a security-critical role. For v1, Switchboard should operate as an OAuth 2.1 resource server only (validating tokens from an external IdP), not as its own authorization server — this keeps v1 scope manageable. AWS CDK v2 (Python) is the IaC recommendation; ECS + Fargate beats EKS for this project given the absence of Kubernetes expertise requirements.

**Core technologies:**
- FastAPI 0.135.3: Admin REST API and HTTP gateway — ASGI-native, async-first, Pydantic v2 integration, OpenAPI docs
- mcp SDK 1.27.0: Protocol compliance — Streamable HTTP transport is the production standard; SSE is deprecated
- httpx 0.28.1: Reverse proxy relay — async-native, streaming-capable, required for transparent SSE/chunked proxy
- PostgreSQL 16+ / SQLAlchemy 2.0 / asyncpg 0.31.0: Server registry — async-native, standard for FastAPI deployments
- PyJWT 2.12.1: JWT validation — actively maintained, no Python 3.12 warnings (unlike abandoned python-jose)
- ECS Fargate + ALB: Container orchestration — no Kubernetes overhead, AWS-native service discovery
- AWS CDK v2 (Python): Infrastructure as code — Python-native, active maintenance, high-level ECS constructs
- pydantic-settings 2.13.1: Configuration — environment-variable and .env-file config, standard for containerized apps

### Expected Features

Research across 12+ sources confirms the MCP gateway feature landscape. The MCP spec (2025-11-25) mandates OAuth 2.1 and Streamable HTTP as non-negotiable baselines. Enterprise platforms universally implement operator approval workflows, structured logging with audit trails, and per-server rate limiting. Switchboard's key competitive differentiator is being Python-native with Docker Compose local dev parity and an explicit operator-controlled catalog — competitors require Kubernetes (Microsoft) or cloud-provider lock-in (AWS AgentCore).

**Must have (table stakes):**
- Server registration via Admin API — dynamic CRUD without redeployment
- Path-based routing (`/servers/{server-name}`) — industry-standard namespace pattern
- JWT/OAuth 2.1 token validation — MCP spec requirement; non-negotiable from day one
- Operator-controlled server approval — the core governance value proposition
- Container-per-server lifecycle management — security isolation; start/stop/restart per server
- Server health monitoring — liveness polling + status exposed via Admin API
- Streamable HTTP transport — current MCP spec standard; SSE is deprecated
- Structured JSON logging — compliance, audit trails, incident response
- HTTPS termination at the gateway — MCP spec requirement
- Reference MCP servers (echo/ping) — needed to validate routing architecture end-to-end

**Should have (competitive):**
- Rate limiting per server — prevents runaway clients from exhausting a server
- Per-server environment variable injection — required for non-trivial servers beyond echo/ping
- Session affinity (Mcp-Session-Id routing) — required when stateful MCP servers are onboarded
- Admin API key scoping (role-based) — multiple operators with different permission levels
- OpenTelemetry metrics export — integration with Grafana/Datadog/Honeycomb
- Tool namespace collision prevention — prefix tool names with server name in aggregated responses
- Operator server approval workflow — pending/approved/disabled approval states

**Defer (v2+):**
- Per-customer server ACLs — requires authorization matrix and membership service; unvalidated requirement
- Aggregated `tools/list` across all servers — N+1 fan-out latency risk; validate demand first
- Rolling restarts without downtime — high complexity; v1 can accept brief restart downtime
- Web UI / admin dashboard — API-first; UI ROI unclear until operator base is established
- Customer self-service server deployment — distinct security model; out of scope

### Architecture Approach

The system is a three-tier design: a public-facing gateway (stateless proxy with auth enforcement), a server registry service (PostgreSQL + container manager + health monitor), and isolated MCP server containers. The gateway and admin API are separate FastAPI apps that can be deployed as separate containers with different network exposure — the gateway is public-facing, the admin API is internal-only. Both read the same PostgreSQL registry, but only the admin API writes to it. The container management layer is abstracted behind a `ContainerBackend` interface with Docker (dev) and ECS (prod) implementations injected via environment configuration.

**Major components:**
1. Gateway (FastAPI + httpx) — JWT validation middleware, registry-backed route resolver, transparent streaming proxy
2. Admin API (FastAPI) — operator-facing CRUD and container lifecycle operations, operator-scoped auth
3. Server Registry (PostgreSQL + SQLAlchemy async) — authoritative server metadata store, accessed via repository pattern
4. Container Manager (abstracted) — Docker SDK backend for local dev, ECS API backend for production
5. Health Monitor (asyncio background task) — periodic liveness polling, updates registry status
6. MCP Server Containers (FastMCP) — isolated per-server containers exposing single `/mcp` Streamable HTTP endpoint

### Critical Pitfalls

Ten pitfalls were identified; five are critical-severity architectural decisions that must be made correctly before implementation begins:

1. **Building for deprecated SSE transport** — Target Streamable HTTP (2025-03-26 spec) from day one. The gateway proxies a single `/mcp` endpoint accepting POST and GET. Do not assume all responses are streams. Recovery cost: HIGH (proxy redesign required).

2. **Forwarding customer bearer tokens to backend containers** — Strip the `Authorization` header before forwarding to MCP containers. Backend containers are trusted by network policy, not by token. This is a confused deputy vulnerability that requires an architectural change to fix retroactively. Recovery cost: HIGH.

3. **Missing `/.well-known/oauth-protected-resource` endpoint** — Spec-compliant MCP clients (including Claude Desktop) perform discovery before requesting tokens. Without this endpoint, they cannot connect. Return 401 with `WWW-Authenticate` header pointing to the resource metadata URL. Recovery cost: LOW once known, but breaks all spec-compliant clients until implemented.

4. **JWT audience claim not validated** — Always pass `audience=` to PyJWT decode. A token issued for a different service passes signature validation and is accepted. Write a test: valid JWT with wrong audience must return 401. Recovery cost: LOW but a security regression until fixed.

5. **Session affinity absent from routing** — Extract `Mcp-Session-Id` header and route consistently to the same container for the session duration. This is implicit with single-instance containers but must be explicit before any horizontal scaling. Recovery cost: MEDIUM (routing table change without backend changes).

Additional implementation-time pitfalls: SSE stream buffering (use `httpx.AsyncClient` with `stream=True`), synchronous blocking code in async gateway (wrap Docker/ECS SDK calls in `asyncio.to_thread()`), ECS cold start 502s (implement health-check gate before marking routes active), path routing ambiguity (validate server names to `^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$`), and MCP containers exposed publicly (private subnets only, security group rules restrict ingress to gateway SG).

## Implications for Roadmap

The architecture research provides an explicit build order driven by dependencies. Every phase unlocks the next. The 7-phase sequence from ARCHITECTURE.md maps directly to feature groups from FEATURES.md and pitfall prevention from PITFALLS.md.

### Phase 1: Registry and Database Foundation

**Rationale:** Every other component reads server metadata from the registry. The gateway needs it for route resolution, the admin API needs it for CRUD, and the container manager needs it for lifecycle state. This is the dependency root.

**Delivers:** PostgreSQL schema, SQLAlchemy async models, Alembic migrations, ServerRepository with full CRUD, Pydantic schemas for server metadata.

**Addresses:** Server registration (table stakes), server status tracking for lifecycle management.

**Avoids:** Pitfall 9 (path routing ambiguity) — server name validation regex enforced at the model level from the start.

**Research flag:** Standard patterns — SQLAlchemy 2.0 async + asyncpg + Alembic is well-documented. No additional research needed.

### Phase 2: Container Manager Abstraction

**Rationale:** The admin API and gateway both depend on the ability to start/stop containers and retrieve internal URLs. The abstraction must exist before admin API routes can be implemented. Building the Docker backend first enables all local development.

**Delivers:** `ContainerBackend` abstract interface, `DockerBackend` implementation (Docker SDK via DooD socket mount), Docker Compose topology for local development.

**Addresses:** Container-per-server isolation (table stakes), server lifecycle management (table stakes).

**Avoids:** Pitfall 7 (blocking Docker SDK in async gateway) — wrap all Docker SDK calls in `asyncio.to_thread()` from the start. Pitfall 10 (containers exposed publicly) — Docker Compose must not publish MCP container ports; use shared named network instead.

**Research flag:** Standard Docker SDK patterns. The DooD vs DinD decision is well-documented; use DooD. No additional research needed.

### Phase 3: Admin API

**Rationale:** Requires the registry (Phase 1) and container manager (Phase 2). Enables operators to populate the server catalog, which is required before gateway routing can be tested end-to-end.

**Delivers:** FastAPI Admin API app, server CRUD endpoints, container lifecycle endpoints (start/stop/restart/status), operator JWT validation with admin scope.

**Addresses:** Server registration via Admin API (P1), server lifecycle management (P1), operator server approval (P1).

**Avoids:** Pitfall 4 (JWT audience not validated) — admin tokens must validate `aud`, `iss`, `exp` from day one. Pitfall 8 (ECS cold start 502s) — implement health-check gate; admin API returns `status: provisioning` immediately, transitions to `status: healthy` only after liveness confirmation.

**Research flag:** FastAPI + JWT auth is well-documented. The health-check gate state machine (provisioning → starting → healthy → degraded) benefits from deeper research into ECS task health check patterns.

### Phase 4: Reference MCP Servers

**Rationale:** Standalone containers with no dependencies on the platform. Building them in parallel with or immediately after the admin API provides the test targets needed for gateway integration testing. Without real MCP servers, gateway work cannot be validated.

**Delivers:** Two FastMCP servers (echo and ping) as Docker images, each exposing `/mcp` via Streamable HTTP transport.

**Addresses:** Reference server requirement (table stakes), end-to-end routing validation.

**Avoids:** Pitfall 1 (SSE-only transport) — reference servers must use `mcp.run(transport="streamable-http")`, establishing the Streamable HTTP pattern before the gateway is built.

**Research flag:** FastMCP is well-documented. No additional research needed.

### Phase 5: Gateway — Auth, Routing, and Proxy

**Rationale:** The integration milestone. Depends on the registry (Phase 1), running MCP servers (Phase 4), and auth configuration. This is the product — all prior phases exist to make this work.

**Delivers:** FastAPI Gateway app, JWT validation middleware, registry-backed route resolver with in-process TTL cache, transparent streaming proxy via httpx, `/.well-known/oauth-protected-resource` endpoint, 401 with `WWW-Authenticate` on unauthenticated requests.

**Addresses:** Path-based routing (P1), JWT/OAuth 2.1 auth (P1), Streamable HTTP transport (P1), HTTPS termination (P1), error propagation (P1), tool discovery proxying (P1).

**Avoids:** Pitfall 1 (SSE transport) — proxy handles single `/mcp` endpoint with both POST and GET. Pitfall 2 (session affinity) — extract and preserve `Mcp-Session-Id` header; document sticky routing requirement for future scaling. Pitfall 3 (stream buffering) — `httpx.AsyncClient.stream()` with `aiter_raw()` chunk iteration. Pitfall 4 (JWT audience) — `jwt.decode(token, key, audience="https://switchboard.example.com")`. Pitfall 5 (missing `.well-known`) — implement discovery endpoint. Pitfall 6 (token passthrough) — strip `Authorization` header before forwarding to containers. Pitfall 7 (blocking async) — no synchronous SDK calls in route handlers.

**Research flag:** HIGH priority for deeper research. Transparent streaming proxy with SSE passthrough has subtle edge cases. The `Mcp-Session-Id` sticky routing contract needs verification against the spec. The `/.well-known/oauth-protected-resource` RFC 9728 document format needs exact verification.

### Phase 6: Health Monitor

**Rationale:** Can be added after gateway works; improves reliability without changing the core routing architecture. Health state enables lifecycle decisions (auto-restart degraded containers, drain before updates).

**Delivers:** asyncio background task polling each running container's MCP endpoint, status updates written to registry, Admin API exposes per-server health status.

**Addresses:** Server health monitoring (P1), foundation for future rate limiting and lifecycle automation.

**Avoids:** Pitfall 8 (cold start 502s) — health monitor confirms `healthy` state before gateway routes traffic; ties into the Phase 3 registration health-check gate.

**Research flag:** Standard asyncio background task pattern. ECS EventBridge integration for event-driven health (vs. polling) is worth researching if poll volume becomes a concern.

### Phase 7: AWS Deployment (ECS Backend + CDK)

**Rationale:** Production deployment. Depends on the container abstraction from Phase 2 — the ECS backend implements the same `ContainerBackend` interface as the Docker backend. CDK constructs deploy gateway, admin API, and MCP server tasks as separate ECS Fargate services.

**Delivers:** `ECSBackend` implementation (boto3 ECS client), AWS CDK v2 Python stack (VPC, ALB, ECS services, RDS, Secrets Manager, ECR), private networking with Cloud Map service discovery, production security group rules.

**Addresses:** Production deployment, HTTPS termination via ALB + ACM, Secrets Manager for JWT keys and DB credentials.

**Avoids:** Pitfall 8 (cold start) — SOCI image indexing, 30s ECS startPeriod grace window. Pitfall 10 (containers exposed publicly) — private subnets, security groups restrict MCP container ingress to gateway SG only.

**Research flag:** ECS Cloud Map DNS TTL behavior (30-60s) needs verification for route resolution latency. SOCI image indexing setup is worth researching for cold start optimization. CDK `ApplicationLoadBalancedFargateService` construct patterns are well-documented.

### Phase Ordering Rationale

- Phases 1-2 are pure infrastructure with no external dependencies; they can be developed in parallel.
- Phase 3 (Admin API) strictly depends on Phases 1 and 2 being complete.
- Phase 4 (Reference Servers) has no platform dependencies; it can run concurrently with Phase 3.
- Phase 5 (Gateway) is the integration point; all prior phases must be complete.
- Phase 6 (Health Monitor) enhances Phase 5 without blocking it; ship Phase 5 first.
- Phase 7 (AWS) is the production deployment layer; all application phases must be solid before infrastructure work.

This ordering ensures every phase produces a testable, shippable increment: Phase 1 has integration tests for the registry, Phase 2 has working container start/stop, Phase 3 has a usable admin API, Phase 5 is the first end-to-end MCP client connection.

### Research Flags

Phases needing deeper research during planning:

- **Phase 5 (Gateway):** Transparent streaming proxy edge cases for MCP Streamable HTTP; `Mcp-Session-Id` sticky routing contract; `/.well-known/oauth-protected-resource` RFC 9728 exact document format; ALB idle timeout configuration for SSE connections (must be set to 3600s, not the default 60s).
- **Phase 7 (AWS Deployment):** ECS Cloud Map DNS TTL behavior for route resolution; SOCI image indexing for cold start reduction; per-server IAM task roles (not a single wildcard role — identified as a critical technical debt pattern in PITFALLS.md).

Phases with well-established patterns (skip additional research):

- **Phase 1 (Registry):** SQLAlchemy 2.0 async + asyncpg + Alembic is thoroughly documented; all versions verified.
- **Phase 2 (Container Manager):** Docker SDK DooD pattern is well-documented; AWS ECS Fargate documentation is authoritative.
- **Phase 4 (Reference Servers):** FastMCP is well-documented; Streamable HTTP transport is the default in current versions.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified against PyPI on 2026-04-14; official documentation confirmed; no speculative choices |
| Features | HIGH | Multiple authoritative sources (MCP official spec, Microsoft/AWS/Red Hat implementations, 10+ platform comparisons); feature landscape well-established |
| Architecture | HIGH | MCP spec is authoritative for transport and auth patterns; AWS ECS/ALB patterns are official documentation; build order is dependency-driven with no ambiguity |
| Pitfalls | HIGH | MCP spec verified; AWS pitfalls from official docs and post-mortems; OAuth/JWT pitfalls from OAuth 2.1 RFCs and Red Hat developer documentation |

**Overall confidence:** HIGH

### Gaps to Address

- **Auth server choice:** Research assumes external IdP (PyJWT + JWKS validation). If Switchboard needs to issue its own OAuth tokens, Authlib and a token store must be added — this significantly expands scope and should be validated with product requirements before Phase 3 begins.
- **Session affinity at scale:** For v1 with single-instance containers, session affinity is implicit (each server name maps to one container). When horizontal scaling is introduced (multiple replicas per server), the routing layer must implement consistent hashing or ALB sticky sessions. This is documented as a future requirement but needs design work before any scaling phase.
- **Per-server IAM task roles:** PITFALLS.md identifies a wildcard IAM role for all containers as a critical security mistake that should never be acceptable. The CDK phase (Phase 7) must implement per-server task roles, which requires the server registry to carry IAM role ARN per server. This gap should be addressed in Phase 1 schema design even if the ECS backend isn't implemented until Phase 7.
- **Backward compatibility with SSE transport:** The research recommends Streamable HTTP as the primary transport. If older clients using the deprecated SSE transport must be supported, a separate code path is required. The scope of backward compat support should be confirmed before Phase 5 gateway design is finalized.
- **JWKS caching strategy:** Gateway must cache the JWKS document from the external IdP to avoid 20-50ms round-trip on every token validation request. The cache TTL and rotation-on-key-ID-miss logic needs implementation design before Phase 5.

## Sources

### Primary (HIGH confidence)

- [MCP Transports Specification (2025-03-26)](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) — Streamable HTTP transport, session management, SSE deprecation
- [MCP Authorization Specification (2025-11-25)](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization) — OAuth 2.1 requirements, PKCE, Protected Resource Metadata
- [MCP Authorization Specification (2025-06-18)](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization) — `.well-known/oauth-protected-resource` RFC 9728 requirements
- [MCP Python SDK (GitHub)](https://github.com/modelcontextprotocol/python-sdk) — SDK implementation details
- [Microsoft MCP Gateway (GitHub)](https://github.com/microsoft/mcp-gateway) — reference implementation for session-aware routing, RBAC patterns
- [AWS ECS Fargate documentation](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html) — ECS task lifecycle, health checks, Fargate constraints
- [FastAPI documentation](https://fastapi.tiangolo.com/advanced/behind-a-proxy/) — reverse proxy configuration, ASGI patterns
- [Docker SDK for Python](https://docker-py.readthedocs.io/en/stable/containers.html) — DooD socket pattern, container management API
- PyPI verified versions: fastapi 0.135.3, uvicorn 0.44.0, mcp 1.27.0, fastmcp 3.2.4, httpx 0.28.1, sqlalchemy 2.0.49, asyncpg 0.31.0, alembic 1.18.4, pydantic 2.13.0, pydantic-settings 2.13.1, PyJWT 2.12.1, Authlib 1.6.10, docker SDK 7.1.0

### Secondary (MEDIUM confidence)

- [Nordic APIs: Review of 10 Managed MCP Platforms](https://nordicapis.com/review-of-10-managed-mcp-platforms/) — feature baseline across platforms
- [Red Hat Developer: Advanced Auth for MCP Gateway](https://developers.redhat.com/articles/2025/12/12/advanced-authentication-authorization-mcp-gateway) — token passthrough, audience validation, privilege escalation patterns
- [Maxim: Best MCP Gateways for Enterprises](https://www.getmaxim.ai/articles/best-mcp-gateways-for-enterprises-in-2025/) — enterprise feature requirements
- [MintMCP: MCP Gateways Rate Limiting and Access Control](https://www.mintmcp.com/blog/mcp-gateways-rate-limiting-access-control) — rate limiting as table stakes
- [DX Heroes: MCP Governance Landscape Early 2026](https://dxheroes.io/insights/mcp-governance-landscape-early-2026) — approval workflows, governance requirements
- [MCP Session Affinity with NGINX Plus (F5 DevCentral)](https://community.f5.com/kb/technicalarticles/mcp-session-affinity-with-f5-nginx-plus/341961) — sticky routing requirement verification
- [Taming Cold Starts on AWS Fargate](https://aws.plainenglish.io/taming-cold-starts-on-aws-fargate-the-architecture-behind-sub-5-second-task-launches-622ebd73b051) — ECS cold start patterns and SOCI
- [Why MCP Deprecated SSE (fka.dev)](https://blog.fka.dev/blog/2025-06-06-why-mcp-deprecated-sse-and-go-with-streamable-http/) — deprecation rationale, verified against spec
- [AWS CDK v2 community (Jan-Feb 2026)](https://github.com/aws/aws-cdk) — active maintenance confirmation
- [Aaron Parecki: Let's Fix OAuth in MCP](https://aaronparecki.com/2025/04/03/15/oauth-for-model-context-protocol) — OAuth design, `.well-known` requirements

### Tertiary (MEDIUM-LOW confidence)

- [Moesif: Comparing MCP Gateways](https://www.moesif.com/blog/monitoring/model-context-protocol/Comparing-MCP-Model-Context-Protocol-Gateways/) — auth patterns and feature comparison
- [MCP Security Vulnerabilities (Practical DevSecOps)](https://www.practical-devsecops.com/mcp-security-vulnerabilities/) — tool poisoning, prompt injection via MCP
- [Nearform: Implementing MCP Tips Tricks and Pitfalls](https://nearform.com/digital-community/implementing-model-context-protocol-mcp-tips-tricks-and-pitfalls/) — global state leaks, tool confusion
- [ECS Fargate Pitfalls (Business Compass)](https://knowledge.businesscompassllc.com/avoiding-ecs-fargate-pitfalls-a-practical-troubleshooting-handbook/) — provisioning limits, DNS resolution failures

---
*Research completed: 2026-04-14*
*Ready for roadmap: yes*
