# Roadmap: Switchboard

## Overview

Switchboard is built in seven phases that follow a strict dependency order: the package foundation and database layer must exist before any API surface, the container manager before lifecycle operations, and the gateway — the product's core value delivery — only after reference servers validate the MCP transport. Health monitoring and AWS deployment complete the production-grade system. Each phase delivers a testable, independently verifiable capability.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation** - Python package structure, PostgreSQL schema, and server registry data layer
- [ ] **Phase 2: Admin API** - Operator-facing REST API for server registration, listing, and detail retrieval
- [ ] **Phase 3: Container Manager** - Container lifecycle abstraction with Docker backend for start/stop/restart
- [ ] **Phase 4: Reference Servers** - Echo and ping MCP servers for end-to-end routing validation
- [ ] **Phase 5: Gateway** - JWT-authenticated routing proxy with full local Docker Compose topology
- [ ] **Phase 6: Health Monitor** - Periodic liveness polling and health status tracking
- [ ] **Phase 7: AWS Deployment** - ECS Fargate backend and CDK infrastructure stack

## Phase Details

### Phase 1: Foundation
**Goal**: The project has a working Python package structure, a running PostgreSQL database, and a complete server registry data layer that all subsequent components will depend on.
**Depends on**: Nothing (first phase)
**Requirements**: PLAT-03
**Success Criteria** (what must be TRUE):
  1. `import switchboard` succeeds; the `switchboard/` directory is the top-level Python package, not `src/`
  2. Running `uv run pytest` against the registry module executes integration tests that create, read, list, and delete server records against a real PostgreSQL instance
  3. Alembic migrations apply cleanly on a fresh database and roll back without errors
  4. Server name validation rejects strings that do not match `^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$` at the model level
**Plans:** 3 plans

Plans:
- [x] 01-01-PLAN.md — Project scaffolding: package structure, dependencies, config, Docker Compose
- [x] 01-02-PLAN.md — Data models: Server ORM model, Pydantic schemas, Alembic migration
- [x] 01-03-PLAN.md — Repository and tests: ServerRepository CRUD, test infrastructure, integration tests

### Phase 2: Admin API
**Goal**: An operator can register MCP servers, list all registered servers, and retrieve details for any individual server via a running FastAPI REST API protected by operator JWT validation.
**Depends on**: Phase 1
**Requirements**: SREG-01, SREG-02, SREG-03
**Success Criteria** (what must be TRUE):
  1. `POST /servers` with a valid payload creates a new registry entry and returns 201 with the server record
  2. `GET /servers` returns all registered servers with their current status
  3. `GET /servers/{name}` returns the full record for a specific server, or 404 if the server does not exist
  4. Requests without a valid operator JWT Bearer token return 401 with a `WWW-Authenticate` header
  5. OpenAPI docs at `/docs` accurately reflect all Admin API endpoints
**Plans:** 2 plans

Plans:
- [x] 02-01-PLAN.md — Dependencies, config, and Admin API modules (auth, router, app)
- [x] 02-02-PLAN.md — Admin API test suite (auth unit tests, endpoint integration tests, OpenAPI smoke test)

### Phase 3: Container Manager
**Goal**: An operator can start, stop, and restart registered MCP server containers via the Admin API, using a Docker-backed container manager that wraps all SDK calls safely for async use.
**Depends on**: Phase 2
**Requirements**: CONT-01, CONT-02, CONT-03
**Success Criteria** (what must be TRUE):
  1. `POST /servers/{name}/start` launches a Docker container for the registered server image and updates registry status to `running`
  2. `POST /servers/{name}/stop` stops a running container and updates registry status to `stopped`
  3. `POST /servers/{name}/restart` stops and relaunches the container without requiring manual operator steps
  4. All Docker SDK calls execute inside `asyncio.to_thread()` — no blocking calls in the async event loop
  5. MCP server containers are not reachable on any host-published port; they exist only on the internal Docker network
**Plans:** 2 plans

Plans:
- [x] 03-01-PLAN.md — ContainerManager service: exceptions, Docker SDK wrapper, unit tests (TDD)
- [x] 03-02-PLAN.md — Lifecycle API endpoints: start/stop/restart routes, integration tests (TDD)

### Phase 4: Reference Servers
**Goal**: Two containerized MCP servers (echo and ping) exist as Docker images that respond correctly to Streamable HTTP transport requests, providing validated test targets for gateway integration.
**Depends on**: Phase 1
**Requirements**: REFS-01, REFS-02
**Success Criteria** (what must be TRUE):
  1. Running the echo image and sending an MCP tool call returns the exact input arguments unchanged
  2. Running the ping image and sending an MCP `ping` request returns a valid response
  3. Both servers use `mcp.run(transport="streamable-http")` — not the deprecated SSE transport
  4. Both images can be registered via the Admin API and started by the container manager
**Plans:** 2 plans

Plans:
- [x] 04-01-PLAN.md — Echo and ping server packages: FastMCP implementation, uv-based Dockerfiles, isolated pyproject.toml
- [x] 04-02-PLAN.md — Docker Compose integration, root pyproject.toml updates, and reference server integration tests

### Phase 5: Gateway
**Goal**: A customer holding a valid JWT can send MCP requests to `/servers/{server-name}/mcp` and have them transparently proxied to the correct running container, with the complete local topology running under Docker Compose.
**Depends on**: Phase 3, Phase 4
**Requirements**: GTWY-01, GTWY-02, GTWY-03, SECU-01, SECU-02, OBSV-01, PLAT-01
**Success Criteria** (what must be TRUE):
  1. An MCP client hitting `/servers/echo/mcp` with a valid JWT receives the correct response from the echo container; the same path with no JWT returns 401 with a `WWW-Authenticate` header
  2. Both POST (client-to-server messages) and GET (SSE server-to-client streams) on the `/mcp` endpoint are proxied correctly for a registered server
  3. A second request carrying the same `Mcp-Session-Id` header is routed to the same container instance that handled the first request
  4. The `Authorization` header is stripped before forwarding to backend MCP containers — backend containers never receive the customer's Bearer token
  5. `GET /.well-known/oauth-protected-resource` returns a valid RFC 9728 resource metadata document
  6. Each proxied request produces a structured JSON log line containing trace ID, user identity, server name, HTTP status, and timestamp
  7. `docker compose up` starts gateway, admin API, PostgreSQL, and both reference servers with all service health checks passing
**Plans:** 3 plans

Plans:
- [x] 05-01-PLAN.md — Dependencies, config, require_customer auth dependency, Wave 0 test stubs
- [x] 05-02-PLAN.md — Gateway proxy module, app factory, well-known endpoint, full test suite
- [x] 05-03-PLAN.md — Root Dockerfile, docker-compose gateway service, human-verified docker compose up

### Phase 6: Health Monitor
**Goal**: The platform continuously polls running MCP server containers and exposes current health status via the Admin API so operators know when servers are degraded without manual inspection.
**Depends on**: Phase 5
**Requirements**: CONT-04
**Success Criteria** (what must be TRUE):
  1. `GET /servers/{name}` returns a `health_status` field reflecting the most recent liveness poll result (`healthy`, `degraded`, or `unreachable`)
  2. Stopping a container externally causes the health status to transition to `unreachable` within two polling intervals
  3. The health monitor runs as an asyncio background task and does not block gateway or admin API request handling
**Plans**: TBD

### Phase 7: AWS Deployment
**Goal**: The complete Switchboard platform runs in production on AWS ECS Fargate with TLS termination at the ALB, private networking for MCP containers, and all secrets stored in Secrets Manager.
**Depends on**: Phase 6
**Requirements**: PLAT-02
**Success Criteria** (what must be TRUE):
  1. `cdk deploy` provisions a working stack — gateway, admin API, PostgreSQL (RDS), and reference server tasks — with all ECS services healthy
  2. Customer MCP requests over HTTPS to the ALB DNS name are correctly routed to the matching ECS task
  3. MCP server containers are in private subnets with security groups that restrict ingress to the gateway security group only — no public port exposure
  4. An ECS task that fails its health check does not receive traffic until it passes again
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7

Note: Phase 4 depends only on Phase 1 and can be worked concurrently with Phases 2-3.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 0/3 | Planning complete | - |
| 2. Admin API | 0/2 | Planning complete | - |
| 3. Container Manager | 0/2 | Planning complete | - |
| 4. Reference Servers | 0/2 | Planning complete | - |
| 5. Gateway | 0/3 | Planning complete | - |
| 6. Health Monitor | 0/? | Not started | - |
| 7. AWS Deployment | 0/? | Not started | - |
