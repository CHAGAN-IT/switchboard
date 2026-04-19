# Switchboard

## What This Is

Switchboard is a managed MCP (Model Context Protocol) hosting platform that serves as both a deployment target for MCP servers and a centralized access point for customers. Organizations deploy approved MCP servers onto Switchboard; customers connect through a single namespaced URL, authenticated via OAuth/JWT. The platform enforces organizational security by ensuring only approved servers are accessible.

## Core Value

Organizations can deploy, manage, and govern MCP servers in one place — customers get a single, secure access point without needing to discover or connect to individual servers themselves.

## Requirements

### Validated

- [x] Codebase is Python with `switchboard/` as the top-level package directory — Validated in Phase 01: foundation
- [x] Platform runs locally via Docker Compose for development — Validated in Phase 01: foundation (PostgreSQL 16, dev + test databases)

### Active

- [x] Operator can register and manage MCP servers via an Admin REST API — Validated in Phase 02: admin-api
- [x] Each MCP server runs in its own container, managed by Switchboard — Validated in Phase 03: container-manager
- [x] Customers access MCP servers through a single namespaced URL (e.g., `/servers/{server-name}`) — Validated in Phase 05: gateway
- [x] Customers authenticate via OAuth/JWT before accessing any MCP server — Validated in Phase 05: gateway
- [x] Registered MCP servers are health-monitored; health_status surfaced via Admin API — Validated in Phase 06: health-monitor
- [ ] Only operator-approved MCP servers are accessible to customers
- [ ] Platform runs on AWS in production; runs locally via Docker Compose for development
- [ ] Codebase is Python with `switchboard/` as the top-level package directory
- [ ] 1-2 reference MCP servers (echo/ping) included to validate the routing architecture

### Out of Scope

- Per-customer ACLs (access control per server per customer) — deferred, no requirement confirmed yet
- Customer-deployed servers — v1 is operator-managed only
- UI/dashboard — admin interaction is API-only in v1
- Billing / usage metering — not part of v1

## Context

- MCP (Model Context Protocol) is Anthropic's open standard for connecting AI models to tools and data sources. Servers expose tools/resources over HTTP (SSE or streamable HTTP transport).
- The MCP ecosystem currently lacks managed hosting and centralized governance — organizations run servers ad-hoc, creating security and discoverability problems.
- Each MCP server is a containerized process; Switchboard's gateway routes inbound requests to the correct container based on the URL path segment.
- Development environment uses Docker Compose to replicate the multi-container topology locally.
- Production targets AWS (likely ECS or EKS for container orchestration).

## Constraints

- **Language**: Python 3.12+ — all application code
- **Structure**: Top-level package is `switchboard/`, not `src/`
- **Containerization**: All components must be containerized (Docker)
- **Cloud**: AWS for production; local Docker Compose for development
- **Best practices**: Architecture and code must follow current Python and MCP best practices
- **Auth**: OAuth/JWT — no API-key-only auth

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Separate container per MCP server | Isolation, independent scaling, security boundaries | — Pending |
| Single namespaced URL for customer access | Simpler client configuration; one endpoint to manage | — Pending |
| OAuth/JWT for auth | Organizational standard; supports token scoping for future ACLs | — Pending |
| Admin REST API (not config file) for server management | Supports dynamic registration without redeployment | — Pending |
| AWS as cloud target | Common enterprise choice; ECS/EKS fits container-per-server model | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-19 after Phase 06: health-monitor complete*
