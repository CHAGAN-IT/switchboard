# Architecture Research

**Domain:** Managed MCP hosting platform (gateway + container orchestration)
**Researched:** 2026-04-14
**Confidence:** HIGH (MCP spec authoritative, AWS patterns well-established)

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CUSTOMER TIER                                  │
│  MCP Client (Claude, Cursor, etc.)                                          │
│  Authorization: Bearer <JWT>                                                │
│  GET/POST /servers/{server-name}/mcp                                        │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ HTTPS
┌────────────────────────────────▼────────────────────────────────────────────┐
│                           GATEWAY (FastAPI/ASGI)                            │
│                                                                             │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌──────────────────┐   │
│  │   Auth Middleware   │  │   Route Resolver    │  │  Proxy Handler   │   │
│  │  JWT validation     │  │  /servers/{name}    │  │  httpx streaming │   │
│  │  Bearer extraction  │  │  → container URL    │  │  SSE passthrough │   │
│  └─────────────────────┘  └─────────────────────┘  └──────────────────┘   │
│                                                                             │
│  OAuth 2.1 Protected Resource Metadata at /.well-known/oauth-protected-    │
│  resource (RFC 9728 compliance) — returns 401 + WWW-Authenticate on miss   │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ internal network
┌────────────────────────────────▼────────────────────────────────────────────┐
│                        SERVER REGISTRY SERVICE                              │
│                                                                             │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌──────────────────┐   │
│  │   Registry DB       │  │  Container Manager  │  │  Health Monitor  │   │
│  │  PostgreSQL         │  │  Docker SDK/ECS API │  │  Liveness probes │   │
│  │  server metadata    │  │  start/stop/status  │  │  status updates  │   │
│  └─────────────────────┘  └─────────────────────┘  └──────────────────┘   │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ container network
┌────────────────────────────────▼────────────────────────────────────────────┐
│                         MCP SERVER TIER                                     │
│                                                                             │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐         │
│  │  echo-server     │  │  weather-server  │  │  custom-server   │   ...   │
│  │  container       │  │  container       │  │  container       │         │
│  │  :8000/mcp       │  │  :8000/mcp       │  │  :8000/mcp       │         │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘         │
│                                                                             │
│  Each container: FastMCP or any MCP-compliant server, streamable HTTP      │
│  transport, single /mcp endpoint, isolated network namespace               │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                            ADMIN API SERVICE                                │
│                                                                             │
│  POST /servers          (register new server)                               │
│  DELETE /servers/{id}   (deregister server)                                 │
│  GET  /servers          (list all servers)                                  │
│  POST /servers/{id}/start                                                   │
│  POST /servers/{id}/stop                                                    │
│  GET  /servers/{id}/status                                                  │
│                                                                             │
│  Auth: operator-scoped JWT (separate scope from customer tokens)           │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| Gateway | Auth enforcement, path-based routing, transparent proxy of MCP protocol | FastAPI + httpx async client, ASGI middleware chain |
| Auth Middleware | JWT validation on every request, return 401/WWW-Authenticate if invalid | PyJWT or python-jose, validate `aud`, `exp`, `iss` claims |
| Route Resolver | Map `/servers/{name}` to internal container URL from registry | In-process call to registry DB or cached lookup |
| Proxy Handler | Forward POST/GET to MCP server, stream SSE response body transparently | httpx `AsyncClient.stream()`, `StreamingResponse` |
| Server Registry | Authoritative store of server metadata: name, image, container ID, status, internal URL | PostgreSQL table, accessed via SQLAlchemy async |
| Container Manager | Start/stop containers for registered servers, return assigned port/hostname | `docker` Python SDK (DooD via socket mount) in dev; ECS API in prod |
| Health Monitor | Periodic liveness checks against each running container's /mcp endpoint | asyncio background task, marks containers UNHEALTHY in registry |
| Admin API | Operator-facing REST API for server CRUD and lifecycle operations | FastAPI, separate service or separate router with operator scope check |
| MCP Server (each) | Expose MCP tools/resources via streamable HTTP on a single `/mcp` endpoint | FastMCP (`mcp.run(transport="streamable-http")`), any MCP-compliant server |

## Recommended Project Structure

```
switchboard/
├── __init__.py
├── py.typed
├── gateway/                    # Inbound proxy service
│   ├── __init__.py
│   ├── app.py                  # FastAPI application factory
│   ├── middleware/
│   │   ├── __init__.py
│   │   └── auth.py             # JWT validation middleware
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── mcp_proxy.py        # /servers/{name}/mcp route + proxy handler
│   │   └── well_known.py       # /.well-known/oauth-protected-resource
│   └── proxy.py                # httpx streaming proxy logic
│
├── admin/                      # Admin API service
│   ├── __init__.py
│   ├── app.py                  # FastAPI application factory
│   └── routers/
│       ├── __init__.py
│       └── servers.py          # CRUD + lifecycle endpoints
│
├── registry/                   # Server registry (shared domain layer)
│   ├── __init__.py
│   ├── models.py               # SQLAlchemy ORM models
│   ├── repository.py           # Repository pattern: ServerRepository
│   └── schemas.py              # Pydantic schemas for server metadata
│
├── containers/                 # Container management abstraction
│   ├── __init__.py
│   ├── base.py                 # Abstract ContainerBackend interface
│   ├── docker_backend.py       # Docker SDK implementation (local/dev)
│   └── ecs_backend.py          # AWS ECS implementation (production)
│
├── auth/                       # Auth utilities
│   ├── __init__.py
│   ├── jwt.py                  # Token validation, claim extraction
│   └── config.py               # JWKS URL, issuer, audience config
│
├── health/                     # Health monitoring
│   ├── __init__.py
│   └── monitor.py              # asyncio background health check loop
│
└── config.py                   # Top-level settings (Pydantic Settings)

tests/
├── conftest.py
├── unit/
│   ├── test_auth.py
│   ├── test_registry.py
│   └── test_containers.py
└── integration/
    ├── test_gateway_routing.py
    └── test_admin_api.py

mcp_servers/                    # Reference MCP server implementations
├── echo/
│   ├── Dockerfile
│   └── server.py               # FastMCP echo/ping server
└── ping/
    ├── Dockerfile
    └── server.py

docker-compose.yml              # Local dev topology
pyproject.toml
```

### Structure Rationale

- **gateway/ vs admin/:** Separate FastAPI apps keeps customer-facing and operator-facing surfaces independent. They can be deployed as separate containers with different network exposure (gateway is public-facing; admin API is internal-only or VPN-gated).
- **registry/:** Shared domain layer accessed by both gateway (for route resolution) and admin API (for CRUD). No direct DB access from routers — all through repository.
- **containers/:** Abstract backend interface means the same lifecycle code works in Docker Compose (dev) and ECS (prod). The backend is injected at startup via config.
- **mcp_servers/:** Reference implementations live in the repo to validate routing architecture without external dependencies.

## Architectural Patterns

### Pattern 1: Transparent Streaming Proxy

**What:** The gateway forwards MCP requests to downstream containers without buffering. Both POST (JSON response or SSE stream) and GET (SSE stream) are proxied verbatim, preserving headers including `Mcp-Session-Id`.

**When to use:** Always — this is the core responsibility of the gateway tier.

**Trade-offs:** Requires async httpx with streaming; no response transformation possible mid-stream. Failures in the downstream container surface as 502/504 to the customer. Session stickiness must be handled at the routing layer (same session ID always reaches the same container instance).

**Example:**
```python
import httpx
from fastapi import Request
from fastapi.responses import StreamingResponse

async def proxy_mcp_request(
    request: Request,
    target_url: str,
) -> StreamingResponse:
    """Forward an MCP request to a downstream container, streaming the response."""
    headers = dict(request.headers)
    headers.pop("host", None)  # strip original host header

    async def stream_body() -> AsyncIterator[bytes]:
        async with httpx.AsyncClient() as client:
            async with client.stream(
                method=request.method,
                url=target_url,
                headers=headers,
                content=request.stream(),
            ) as upstream:
                async for chunk in upstream.aiter_raw():
                    yield chunk

    # Preserve Content-Type: text/event-stream if upstream sends SSE
    upstream_headers = {}  # populated from first response chunk in practice
    return StreamingResponse(stream_body(), media_type="text/event-stream")
```

### Pattern 2: Registry-Backed Route Resolution

**What:** Before proxying, the gateway looks up the server name in the registry DB to get the container's internal hostname and port. The result is cached in-process (TTL ~30s) to avoid DB round-trips on every MCP request.

**When to use:** Every inbound request to `/servers/{name}/mcp`.

**Trade-offs:** Cache introduces up to TTL seconds of stale routing after a server is stopped. This is acceptable for v1; invalidation hooks can be added later.

**Example:**
```python
from functools import lru_cache
from switchboard.registry.repository import ServerRepository

async def resolve_target_url(server_name: str, repo: ServerRepository) -> str:
    """Return the internal URL for a running MCP server container."""
    server = await repo.get_by_name(server_name)
    if server is None or server.status != "running":
        raise ServerNotFoundError(server_name)
    return f"http://{server.container_host}:{server.container_port}/mcp"
```

### Pattern 3: Container Backend Abstraction

**What:** A `ContainerBackend` abstract base class defines the lifecycle interface (`start`, `stop`, `status`, `get_url`). `DockerBackend` uses the Docker Python SDK with a mounted socket (DooD). `ECSBackend` uses `boto3` ECS APIs.

**When to use:** Inject the correct backend at startup via `CONTAINER_BACKEND=docker|ecs` env var.

**Trade-offs:** DooD (mounting `/var/run/docker.sock`) gives the management service root-equivalent access to the host Docker daemon. This is acceptable for single-tenant production on a dedicated host or in a dev environment, but should be considered carefully in multi-tenant deployments. ECS backend avoids this entirely.

**Example:**
```python
from abc import ABC, abstractmethod

class ContainerBackend(ABC):
    @abstractmethod
    async def start(self, image: str, name: str, env: dict[str, str]) -> str:
        """Start a container. Returns internal hostname."""
        ...

    @abstractmethod
    async def stop(self, container_id: str) -> None:
        ...

    @abstractmethod
    async def get_url(self, container_id: str) -> str:
        """Return the internal HTTP URL for the container's MCP endpoint."""
        ...
```

## Data Flow

### Customer MCP Request Flow

```
Customer MCP Client
    │
    │  POST /servers/echo/mcp
    │  Authorization: Bearer eyJ...
    │  Mcp-Session-Id: abc123 (if existing session)
    │  Body: { "jsonrpc": "2.0", "method": "tools/list", ... }
    ▼
Gateway Auth Middleware
    │  1. Extract Bearer token from Authorization header
    │  2. Validate JWT: signature, exp, iss, aud
    │  3. Reject with 401 + WWW-Authenticate if invalid
    ▼
Route Resolver
    │  4. Extract server_name = "echo" from URL path
    │  5. Look up "echo" in registry (cache → DB)
    │  6. Reject with 404 if not found or not running
    │  7. Get target = "http://echo-container:8000/mcp"
    ▼
Proxy Handler
    │  8. Forward request to target, strip/rewrite Host header
    │  9. If response is application/json → buffer and return
    │  10. If response is text/event-stream → stream chunks to client
    ▼
MCP Server Container (echo)
    │  11. Process MCP JSON-RPC request
    │  12. Return JSON response or open SSE stream
    ▼
Customer MCP Client
    13. Receives MCP response
```

### Admin Server Registration Flow

```
Operator
    │
    │  POST /servers
    │  { "name": "weather", "image": "my-org/weather-mcp:latest", "env": {...} }
    │  Authorization: Bearer <operator-scoped JWT>
    ▼
Admin API Auth Check
    │  Validate operator scope in JWT claims
    ▼
Admin Router
    │  Validate request body (Pydantic schema)
    │  Check name uniqueness in registry
    ▼
Registry Repository
    │  INSERT server record (status=registered)
    ▼
Container Manager
    │  Pull image (if needed)
    │  Start container: docker.containers.run(image, detach=True, name=name)
    │  Assign internal hostname/port
    │  UPDATE registry: status=running, container_id=..., host=..., port=...
    ▼
Health Monitor (background)
    │  Begins polling http://weather-container:8000/mcp (GET, expect 200 or 405)
    │  UPDATE status=healthy / unhealthy based on response
    ▼
Admin API Response
    │  201 Created + server metadata
    ▼
Operator
```

### MCP Protocol Session Flow (Streamable HTTP)

```
Client → Gateway → MCP Container

1. POST /servers/{name}/mcp  (InitializeRequest)
   ← 200 OK  Mcp-Session-Id: <uuid>  (InitializeResult)

2. POST /servers/{name}/mcp  (InitializedNotification)
   Mcp-Session-Id: <uuid>
   ← 202 Accepted

3. POST /servers/{name}/mcp  (tools/list request)
   Mcp-Session-Id: <uuid>
   ← 200 OK  Content-Type: application/json  (direct response)
   OR
   ← 200 OK  Content-Type: text/event-stream  (SSE with result events)

4. GET  /servers/{name}/mcp  (open server→client stream)
   Mcp-Session-Id: <uuid>
   ← 200 OK  Content-Type: text/event-stream  (server notifications)

5. DELETE /servers/{name}/mcp  (session termination)
   Mcp-Session-Id: <uuid>
   ← 200 OK
```

**Gateway responsibility in session flow:** The gateway passes `Mcp-Session-Id` headers through verbatim. Session state lives in the MCP server container, not in the gateway. This means the gateway is stateless — any gateway replica can forward any request as long as the session ID reaches the correct container.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1-10 servers | Single gateway instance, Docker Compose locally and on one EC2 host. PostgreSQL on RDS. No caching layer needed. |
| 10-100 servers | Gateway scales horizontally behind ALB. Redis cache for route resolution (avoids DB fan-out). ECS Fargate per MCP server removes server management overhead. |
| 100+ servers | Session affinity becomes critical — ALB sticky sessions or gateway-side session→container routing table in Redis. MCP servers may need horizontal scaling within a server namespace. |

### Scaling Priorities

1. **First bottleneck — route resolution DB reads:** Every MCP request hits the registry to resolve the container URL. Add an in-process TTL cache immediately; add Redis for horizontal gateway scaling.
2. **Second bottleneck — SSE connection fan-out:** Long-lived SSE connections occupy a gateway worker. Ensure Uvicorn workers are tuned to async (not threaded). Gateway instances scale horizontally behind ALB.
3. **Third bottleneck — container startup latency:** On demand starts are slow (5-30s for image pull + process start). Pre-warm containers at registration time; keep them running until explicitly stopped.

## Anti-Patterns

### Anti-Pattern 1: Gateway Holds MCP Session State

**What people do:** Store session metadata (Mcp-Session-Id → server mapping) inside the gateway process.

**Why it's wrong:** Breaks horizontal gateway scaling. When a second gateway replica handles the next request with the same session ID, it has no mapping and returns 404.

**Do this instead:** Keep session state in the MCP server container itself (as the spec intends). The gateway resolves server by name from the URL path, not from the session ID. Each request carries both the server name (in the URL) and the session ID (in the header) — the gateway only needs the name.

### Anti-Pattern 2: One Monolithic Container for All MCP Servers

**What people do:** Run all MCP server logic inside the gateway process, using in-process routing.

**Why it's wrong:** Eliminates isolation. A bug or crash in one server takes down the entire platform. Prevents independent scaling and deployment of individual servers. Makes the security boundary meaningless.

**Do this instead:** One container per MCP server, as specified in the project requirements. The gateway is a dumb proxy; each server runs in its own isolated container.

### Anti-Pattern 3: Docker-in-Docker (DinD) for Container Management

**What people do:** Run a Docker daemon inside the management container (`--privileged` + DinD image) to start child containers.

**Why it's wrong:** DinD requires `--privileged` mode which gives the container root-equivalent host access and is harder to secure than socket mounting. DinD also has I/O performance overhead and lifecycle complexity.

**Do this instead:** Docker-out-of-Docker (DooD) — mount `/var/run/docker.sock` into the management container. The Docker SDK then communicates with the host daemon directly. Containers started this way are siblings of the management container, not children. In production, replace with ECS API calls entirely (no socket needed).

### Anti-Pattern 4: Passing Customer JWT to MCP Server Containers

**What people do:** Forward the customer's `Authorization: Bearer` header through to the upstream MCP container.

**Why it's wrong:** The MCP spec (2025-11-25) explicitly prohibits token passthrough. MCP servers must validate that tokens were issued specifically for them as audience. A customer token issued to the gateway is not a valid token for the downstream MCP container. This is also a confused deputy vulnerability.

**Do this instead:** The gateway validates the customer token and strips the `Authorization` header before forwarding to the MCP container. MCP containers on the internal network are trusted by network policy, not by token. If downstream auth is needed in the future, issue a separate service-to-service token.

### Anti-Pattern 5: Using the Deprecated HTTP+SSE Transport

**What people do:** Build MCP servers using the old (2024-11-05) HTTP+SSE transport with separate `/sse` and `/messages` endpoints.

**Why it's wrong:** The SSE transport was deprecated in the March 2025 spec update. It requires persistent long-lived connections and is harder to proxy than the new streamable HTTP transport.

**Do this instead:** Use Streamable HTTP transport. Single `/mcp` endpoint supporting both POST and GET. FastMCP's `mcp.run(transport="streamable-http")` uses this by default in current versions.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| OAuth 2.1 Authorization Server (external) | Gateway validates JWTs using JWKS endpoint from issuer; no direct call on hot path once keys are cached | Use `python-jose` or `PyJWT`; cache JWKS with TTL; validate `iss`, `aud`, `exp` claims |
| PostgreSQL (RDS in prod) | SQLAlchemy async (`asyncpg` driver); accessed via Repository pattern | Single DB instance for v1; schema: `servers` table with name, image, status, container_id, host, port |
| Docker Engine (dev only) | Docker SDK for Python via mounted socket (`/var/run/docker.sock`) | DooD pattern; management container needs socket mount |
| AWS ECS (prod only) | `boto3` ECS client; `register_task_definition`, `run_task`, `stop_task` | Fargate launch type eliminates EC2 management; tasks per MCP server |
| AWS ECR | Image registry for MCP server images | Images pulled by ECS at task start; use ECR lifecycle policies |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Gateway ↔ Registry DB | Direct async DB query (SQLAlchemy) with in-process cache | Gateway must not write to registry; read-only access |
| Admin API ↔ Registry DB | Full read/write via Repository | Admin API owns lifecycle mutations |
| Admin API ↔ Container Manager | In-process function calls (same service) | Container Manager is a module, not a separate service in v1 |
| Gateway ↔ MCP Containers | HTTP (internal network, no TLS) | Containers are on isolated internal network; gateway is the only ingress |
| Admin API ↔ MCP Containers | HTTP health checks only | Admin API does not send MCP protocol messages |

## Suggested Build Order

Dependencies drive build order: each phase unlocks the next.

```
Phase 1: Registry + DB schema
    └── Unblocks everything else; all components need server metadata

Phase 2: Container Manager (Docker backend)
    └── Depends on: Registry (needs server records to manage containers)
    └── Unblocks: Admin API (needs container ops), local dev topology

Phase 3: Admin API
    └── Depends on: Registry + Container Manager
    └── Unblocks: Ability to register and start test servers

Phase 4: Reference MCP Servers (echo/ping)
    └── Depends on: nothing (standalone containers)
    └── Unblocks: Gateway integration testing

Phase 5: Gateway (Auth + Routing + Proxy)
    └── Depends on: Registry (route lookup), Auth config, running MCP servers
    └── This is the integration milestone; all pieces must exist

Phase 6: Health Monitor
    └── Depends on: Registry + running containers
    └── Can be added after gateway works; improves reliability

Phase 7: ECS Backend
    └── Depends on: Container Manager abstraction (Phase 2)
    └── Swap in for Docker backend in production deployment
```

## AWS Deployment Topology (Production)

```
Internet
    │
    ▼
ALB (Application Load Balancer)
    │  HTTPS termination, SSL cert via ACM
    │  Routes: /* → Gateway ECS Service
    │          /admin/* → Admin API ECS Service (IP allowlist or VPN only)
    ▼
┌─────────────────────────────────────────────────────┐
│  VPC Private Subnets                                │
│                                                     │
│  Gateway Service (ECS Fargate)                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ task     │ │ task     │ │ task     │  (scales)  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘            │
│       └────────────┴────────────┘                   │
│                    │                                │
│  Admin API Service (ECS Fargate)                    │
│  ┌──────────┐                                       │
│  │ task     │                                       │
│  └────┬─────┘                                       │
│       │                                             │
│  RDS PostgreSQL (registry DB)                       │
│                                                     │
│  MCP Server Tasks (ECS Fargate, one task def each)  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ echo     │ │ weather  │ │ custom   │            │
│  │ task     │ │ task     │ │ task     │            │
│  └──────────┘ └──────────┘ └──────────┘            │
│  Service Discovery: AWS Cloud Map (private DNS)     │
│  echo.mcp.local:8000, weather.mcp.local:8000       │
└─────────────────────────────────────────────────────┘
```

**ECS vs EKS decision:** Use ECS Fargate for v1. Lower operational overhead than EKS (no control plane to manage). Container-per-server maps naturally to one Fargate task per registered server. AWS Cloud Map provides private DNS for service discovery (the gateway resolves `{name}.mcp.local` instead of a stored IP). Switch to EKS if Kubernetes-native tooling or RBAC becomes a requirement in later versions.

## Sources

- [MCP Transports Specification (2025-03-26)](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) — HIGH confidence, official spec
- [MCP Authorization Specification (2025-11-25)](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization) — HIGH confidence, official spec
- [MCP Python SDK (GitHub)](https://github.com/modelcontextprotocol/python-sdk) — HIGH confidence, official SDK
- [Microsoft MCP Gateway (GitHub)](https://github.com/microsoft/mcp-gateway) — MEDIUM confidence, reference implementation for gateway patterns
- [Docker SDK for Python](https://docker-py.readthedocs.io/en/stable/containers.html) — HIGH confidence, official docs
- [AWS ECS Fargate Architecture](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html) — HIGH confidence, official AWS docs
- [FastAPI Behind a Proxy](https://fastapi.tiangolo.com/advanced/behind-a-proxy/) — HIGH confidence, official FastAPI docs
- [MCP Gateways Overview 2025 (Maxim)](https://www.getmaxim.ai/articles/top-5-mcp-gateways-in-2025-the-complete-guide-to-enterprise-ready-ai-agent-infrastructure/) — MEDIUM confidence, third-party analysis
- [Why MCP Deprecated SSE (fka.dev)](https://blog.fka.dev/blog/2025-06-06-why-mcp-deprecated-sse-and-go-with-streamable-http/) — MEDIUM confidence, community analysis verified against spec

---
*Architecture research for: Switchboard — managed MCP hosting platform*
*Researched: 2026-04-14*
