# Pitfalls Research

**Domain:** Managed MCP hosting platform (multi-container gateway, OAuth/JWT auth, AWS deployment)
**Researched:** 2026-04-14
**Confidence:** HIGH (MCP spec verified against official docs; AWS pitfalls verified against AWS documentation and community post-mortems; auth pitfalls verified against OAuth 2.1 RFCs and MCP authorization spec)

---

## Critical Pitfalls

### Pitfall 1: Building for SSE-only transport when Streamable HTTP is the current standard

**What goes wrong:**
You design the gateway assuming every MCP server connection is a persistent SSE stream — a separate `/sse` endpoint plus a `/messages` POST endpoint, per the deprecated 2024-11-05 spec. The new 2025-03-26 spec defines a single MCP endpoint accepting both GET and POST, where SSE is optional and response-driven (the server may return `application/json` instead of `text/event-stream` for simple requests). A gateway built for the old transport breaks clients using the new transport and vice versa.

**Why it happens:**
Most early tutorials and SDK examples targeted the HTTP+SSE transport. The deprecation happened in March 2025 but examples lag by months. New builders copy old code.

**How to avoid:**
Target the 2025-03-26 Streamable HTTP spec from day one. The gateway must handle a single endpoint that accepts POST (with `Accept: application/json, text/event-stream`) and optional GET for server-to-client streams. The gateway proxies to the backing container's single MCP endpoint. Support the old SSE transport only if backwards compatibility with old clients is explicitly required — implement it as a separate code path, not a design assumption.

**Warning signs:**
- Proxy routing logic references `/sse` and `/messages` as separate paths
- Gateway code assumes all MCP responses are streams
- Backend containers use the `mcp` Python SDK without pinning spec version

**Phase to address:** Foundation / Gateway routing phase (must be right before any MCP servers are wired up)

---

### Pitfall 2: Session affinity absent from the gateway design

**What goes wrong:**
The MCP Streamable HTTP spec assigns an `Mcp-Session-Id` header during initialization, and all subsequent client requests MUST include it. The backing MCP server holds per-session state in memory. When the gateway load-balances requests round-robin across multiple container replicas, a client's POST with `Mcp-Session-Id` hits a different container than the one that issued the session ID — that container returns 400 Bad Request or silent corruption because it has no state for that session.

**Why it happens:**
Engineers apply standard stateless API load-balancing patterns to MCP without reading the session management section of the spec. The problem only manifests under multiple replicas, so it passes all single-instance tests.

**How to avoid:**
Route requests by `Mcp-Session-Id` header at the gateway layer. Extract the header and consistently route to the same backend container instance for the duration of the session. For v1, since each registered MCP server is a single named container, this is implicit — but as soon as horizontal scaling is added, sticky routing must be explicit. Document this constraint now so future scaling work doesn't break sessions. For stateless MCP servers (tools without session memory), session-ID-based routing still prevents 400 errors from stateful initialization sequences.

**Warning signs:**
- Gateway routing logic uses only URL path for backend selection
- No `Mcp-Session-Id` header extraction in proxy code
- Tests only run against single container replicas

**Phase to address:** Gateway routing phase; re-verify in any scaling phase

---

### Pitfall 3: Treating SSE streams as fire-and-forget through the proxy — buffering breaks streaming

**What goes wrong:**
The Python gateway proxies MCP responses. For tools that return data via SSE stream, the proxy buffers the entire response body before forwarding it to the client (default behavior in most HTTP client libraries and many reverse proxies). The client receives nothing until the stream completes or times out — defeating the purpose of streaming and breaking tools with long-running operations.

**Why it happens:**
`httpx`, `aiohttp`, and `requests` all default to buffered responses. Developers test with small, fast responses and never observe the buffering. Production MCP tools that stream large results (file reads, search results, LLM-generated content) hit this hard.

**How to avoid:**
Use `httpx.AsyncClient` with `stream=True` context manager when proxying to backend MCP containers. Iterate over response chunks and yield them as SSE events to the upstream client. Set `proxy_buffering = off` if Nginx sits in front of the gateway. Verify with a slow-streaming test tool (one that emits events every 500ms for 10 seconds) before marking proxy work complete.

**Warning signs:**
- Gateway proxy code uses `response.text` or `response.content` (buffered)
- Nginx config lacks `proxy_buffering off`
- No integration test covering a streaming MCP tool response

**Phase to address:** Gateway proxy implementation phase

---

### Pitfall 4: JWT audience claim not validated — tokens accepted for wrong resource

**What goes wrong:**
The gateway validates JWT signature and expiry but skips `aud` (audience) claim validation. A token issued for a different service (e.g., an internal API) passes validation. In multi-tenant scenarios, a token issued for Tenant A's MCP context is accepted for Tenant B's namespace. This enables lateral movement and cross-tenant data access.

**Why it happens:**
PyJWT and python-jose default behavior varies — some only check signature unless you explicitly pass `audience=` to the decode call. Documentation examples often omit audience validation to keep samples short.

**How to avoid:**
Always pass the expected `aud` value when decoding JWTs. The audience should be the Switchboard resource server identifier (e.g., `https://switchboard.example.com`). Verify `iss` (issuer) and `aud` as hard requirements; reject tokens missing either. Write a dedicated test: create a valid JWT with wrong audience, confirm the gateway returns 401.

**Warning signs:**
- `jwt.decode()` calls without `audience=` parameter
- Auth middleware that only checks `exp` and signature
- No test for wrong-audience rejection

**Phase to address:** Auth implementation phase (non-negotiable before any endpoint is callable)

---

### Pitfall 5: Missing `.well-known/oauth-protected-resource` endpoint

**What goes wrong:**
The MCP Authorization spec (June 2025 revision) requires MCP servers acting as OAuth Resource Servers to expose `/.well-known/oauth-protected-resource` per RFC 9728. MCP clients that follow the spec perform discovery before requesting tokens: they call the MCP endpoint without a token, expect a 401 with a `WWW-Authenticate` header pointing to the resource metadata URL, fetch that document, and discover the authorization server. Without this endpoint, spec-compliant MCP clients cannot auto-discover auth and fail to connect.

**Why it happens:**
Most existing MCP hosting examples omit this entirely because the auth spec was added late (March 2025) and SDKs didn't initially implement it. It looks like an optional detail but is required for spec compliance.

**How to avoid:**
Implement `/.well-known/oauth-protected-resource` on the gateway returning a JSON document with `resource`, `authorization_servers`, `bearer_methods_supported`, and `scopes_supported`. Return 401 with `WWW-Authenticate: Bearer realm="...", resource_metadata="..."` on all unauthenticated requests to MCP endpoints. Test with a spec-compliant MCP client (e.g., Claude Desktop) that performs discovery.

**Warning signs:**
- Auth middleware returns 401 with no `WWW-Authenticate` header
- No `/.well-known/` routes defined
- Auth tested only with pre-configured tokens, never with discovery flow

**Phase to address:** Auth implementation phase

---

### Pitfall 6: Token passthrough to backend containers — privilege escalation vector

**What goes wrong:**
The gateway receives a customer's bearer token and forwards it verbatim to the backing MCP container in the `Authorization` header. The MCP server process now holds a token scoped for the gateway resource, not for the MCP server. A compromised or malicious MCP server can replay this token against other services — including the gateway admin API — that accept tokens from the same issuer.

**Why it happens:**
It seems efficient: just pass the header through. The security boundary between "token to authenticate to the platform" and "credentials the MCP server uses for its own operations" gets conflated.

**How to avoid:**
Do not forward customer bearer tokens to backend containers. The gateway authenticates the customer and then makes internal requests to backend containers using service-to-service credentials (IAM roles on ECS, or short-lived internal tokens scoped specifically for that MCP server). The backend container should never receive or need the customer's OAuth token. If a backend needs to act on behalf of a customer (user-delegated access), implement token exchange (RFC 8693) with audience restriction.

**Warning signs:**
- Gateway proxy code copies `Authorization` header from incoming request to outgoing request to backend
- Backend containers have no distinct service identity
- No separation between "platform auth" and "backend service auth" in architecture design

**Phase to address:** Auth implementation phase (architectural decision that affects all subsequent phases)

---

### Pitfall 7: Synchronous blocking code in the async gateway event loop

**What goes wrong:**
The Python gateway uses FastAPI + uvicorn. A route handler calls a blocking function — Docker SDK to provision a container, `subprocess.run` to execute something, or a synchronous database call — without `asyncio.to_thread()`. The uvicorn worker's event loop blocks for the duration of the call. During this time, all other in-flight requests (including SSE streams) stall. Under any real concurrent load, this manifests as cascading timeouts and dropped SSE connections.

**Why it happens:**
Python's async/sync divide is subtle. Many libraries (Docker SDK, some AWS SDK clients, standard `psycopg2`) are synchronous. Developers use them directly in `async def` handlers thinking async def is sufficient.

**How to avoid:**
All blocking I/O in the gateway must be wrapped in `asyncio.to_thread()` or replaced with async equivalents (`aiodocker`, `aioboto3`, `asyncpg`). Use `uvicorn`'s `--workers` only for CPU-bound parallelism, not as a workaround for blocking async code. Set up a simple load test (10 concurrent SSE connections + 10 POST requests) to catch this before deployment.

**Warning signs:**
- `import docker` (synchronous Docker SDK) used in route handlers
- `asyncio.run()` called inside `async def` functions
- Any `time.sleep()` in async code
- No concurrency test in the test suite

**Phase to address:** Gateway implementation phase; verify in load testing phase

---

### Pitfall 8: AWS ECS container cold start breaks first-request routing

**What goes wrong:**
An operator registers a new MCP server. The gateway marks it available and starts accepting routes to it. The first client request arrives before the ECS task has finished starting — image pull takes 5-60 seconds, application bootstrap takes 1-10 seconds. The gateway gets a connection refused or 502 from the container, and the client receives an error with no useful message. The operator thinks the registration failed.

**Why it happens:**
ECS task startup is asynchronous. The ECS `RunTask` API returns a task ARN before the container is ready. Registering the route immediately after the ECS API call succeeds is premature.

**How to avoid:**
Implement a health-check gate: after launching an ECS task, poll the task's health check endpoint (a lightweight `/health` HTTP path on each MCP container) before marking the server route as active. Expose a `status` field on the admin API (`provisioning`, `starting`, `healthy`, `degraded`) so operators know when a server is truly reachable. Use AWS ECS task health check with a `startPeriod` grace window of at least 30 seconds. Optimize cold starts with SOCI (Seekable OCI) image indexing.

**Warning signs:**
- Admin API responds 200 to a register request before container health is confirmed
- No `/health` endpoint on MCP container images
- ECS task state not polled after `RunTask` call

**Phase to address:** Container lifecycle management phase

---

### Pitfall 9: Path-based routing ambiguity — `/servers/{name}` conflicts with MCP protocol paths

**What goes wrong:**
The gateway routes `/servers/{server-name}` to the appropriate backend container. The MCP spec defines its own endpoint at a single path (e.g., `/mcp`). If the gateway strips the prefix correctly but the MCP server uses relative redirects or returns URLs with its internal path, the URLs break when accessed through the gateway. Worse, if the server name contains characters that look like path segments (dashes, underscores, dots), routing regex can misparse them.

**Why it happens:**
Prefix-stripping reverse proxy logic has well-known edge cases. FastAPI's path parameters and HTTPX URL construction don't always compose as expected.

**How to avoid:**
Define a strict URL contract: `/servers/{server-name}` is the gateway namespace prefix; everything after it is forwarded verbatim to the backend container's root. Validate server names at registration time (regex: `^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$`). Write integration tests that exercise path forwarding with names containing hyphens, and that verify SSE `event: endpoint` data returned by the server does not contain internal hostnames. Use an absolute `proxy_pass` directive (not relative) in any Nginx layer.

**Warning signs:**
- Server name validation accepts dots or slashes
- Integration tests only use server name `test` or `server1`
- Proxy code constructs backend URLs by string concatenation instead of URL parsing

**Phase to address:** Gateway routing phase

---

### Pitfall 10: MCP server containers exposing ports to the public internet

**What goes wrong:**
ECS tasks are placed in a VPC but their security groups allow inbound HTTP from `0.0.0.0/0`. Or the Docker Compose development setup binds container ports to `0.0.0.0` and this accidentally carries into production configuration. MCP servers are directly reachable, bypassing gateway authentication and all access controls.

**Why it happens:**
"Open for debugging" settings get committed. Docker Compose port bindings (`ports: "8080:8080"`) are convenient locally and get copied to ECS task definitions without review.

**How to avoid:**
MCP container tasks MUST be in a private subnet with no inbound security group rules from outside the VPC. The only allowed ingress to MCP containers is from the gateway's security group. Enforce this in infrastructure-as-code (no public IPs on MCP task definitions, security group rules reference gateway SG by ID not CIDR). In Docker Compose, do not publish MCP container ports — use a shared Docker network instead. Write a deployment checklist item: "verify no MCP container has a public IP or public-facing port."

**Warning signs:**
- ECS task definition has `assignPublicIp: ENABLED`
- Docker Compose MCP service has `ports:` section
- Security group audit shows `0.0.0.0/0` on port 8000/8080

**Phase to address:** Infrastructure / AWS deployment phase

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Storing session state in-memory in MCP container | Simplest implementation, no external dependency | Session lost on container restart/redeploy; prevents horizontal scaling | v1 only if containers are never restarted during a session |
| Using a single wildcard IAM role for all MCP containers | One role to manage | Compromised MCP server gets access to all other resources in the account | Never — use per-server IAM task roles |
| Skipping `.well-known` discovery endpoint | Saves one route to implement | Spec-compliant clients cannot connect; discovered when integrating real clients | Never |
| Synchronous Docker SDK calls in gateway | Docker SDK is well-documented | Blocks event loop, stalls all concurrent requests | Never in async gateway code |
| Using `localhost` / `127.0.0.1` for inter-container communication | Works in single-container dev | Breaks in Docker networks and ECS; containers have separate network namespaces | Never in any multi-container setup |
| Hard-coding MCP container base URL in gateway config | Simpler than service discovery | Requires gateway redeployment to register new servers | v1 only if registration volume is low |
| Skipping Origin header validation in MCP containers | Less code | Enables DNS rebinding attacks against locally-running servers | Never — it's one header check |

---

## Integration Gotchas

Common mistakes when connecting to external services.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| AWS ECS RunTask API | Treating task ARN response as "container ready" | Poll `DescribeTasks` until task health check passes before marking route active |
| AWS ECS service discovery / Cloud Map | Relying on DNS TTL for near-instant updates | DNS TTL for Cloud Map can be 30-60s; use direct IP from task metadata or ALB target group for routing |
| OAuth Authorization Server (JWKS) | Fetching JWKS on every token validation request | Cache JWKS with a TTL of ~1 hour; rotate cache on key ID miss |
| OAuth Authorization Server | Trusting `kid` header without JWKS lookup | Always fetch the public key from JWKS by `kid`; never trust unsigned key material |
| Docker Compose networking | Using `localhost` from one service to reach another | Use Docker service names as hostnames (e.g., `http://mcp-echo:8000`) within a shared network |
| MCP Python SDK | Assuming latest SDK version targets latest spec | Pin SDK version to spec; verify which spec version the SDK implements before use |
| AWS ALB | Using ALB timeout defaults (60s) for SSE connections | Set ALB idle timeout to 3600s for paths serving SSE; SSE connections idle between events |

---

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| One ECS task per MCP server always running | Acceptable at 5 servers; costly at 50 | Design container lifecycle management from the start; support scale-to-zero for idle servers | ~20 servers (cost), ~100 servers (ECS task limits per cluster) |
| Polling ECS `DescribeTasks` in a tight loop for health | Works for 1-2 servers; hits ECS API rate limits at scale | Use exponential backoff; consider event-driven health via ECS EventBridge events | ~10 concurrent registrations |
| JWKS fetch on every request (no caching) | 20-50ms added to every JWT validation | Cache JWKS document with in-memory LRU cache, TTL 1h | ~100 req/s gateway throughput |
| Synchronous Docker/ECS SDK calls in async gateway | Single blocking call stalls all connections | Wrap all blocking SDK calls in `asyncio.to_thread()` | First concurrent user |
| No connection pool for gateway-to-backend HTTP | Fine with 1-2 servers; socket exhaustion at scale | Use `httpx.AsyncClient` with a per-backend connection pool, reuse across requests | ~50 concurrent MCP sessions |
| Logging full request/response bodies for debugging | Harmless in dev; PII leak and disk exhaustion in prod | Log request IDs and metadata only; use structured logging with redaction from day one | First production deployment |

---

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Forwarding customer bearer token to backend containers | Token replay; compromised MCP server accesses other services | Authenticate customer at gateway; use service-to-service credentials for backend calls |
| Accepting tokens with any audience | Cross-service token misuse | Validate `aud` claim matches Switchboard's resource identifier on every token validation |
| MCP tool descriptions not sanitized | Tool poisoning: malicious tool descriptions can inject instructions into the AI model's context | Sanitize tool name/description fields at registration time; flag unusual Unicode or instruction-like content |
| No rate limiting on MCP tool calls | A single client can exhaust backend container resources | Implement per-client rate limiting at the gateway before any MCP container proxying |
| Admin API accessible on same port/path as customer API | Operator credentials protect less than they appear to | Separate admin API and customer-facing endpoints at network level (different port or separate service) |
| Session IDs that are predictable or short | Session hijacking | Session IDs must be cryptographically random UUIDs (128-bit entropy minimum) per MCP spec |
| Origin header validation skipped on MCP containers | DNS rebinding attacks against local/development servers | MCP containers MUST validate `Origin` header on all incoming connections per the spec's security warning |

---

## UX Pitfalls

Common developer experience mistakes for platform operators.

| Pitfall | Operator Impact | Better Approach |
|---------|----------------|-----------------|
| No server provisioning status in admin API | Operator registers server, gets 200 OK, but first client request fails with 502 because ECS task isn't ready | Return `status: provisioning` immediately; poll to `status: healthy`; surface status on GET /servers/{name} |
| Error responses from gateway don't distinguish client auth failure from backend container failure | Operators cannot diagnose whether the problem is the JWT, the routing, or the MCP server itself | Use distinct HTTP status codes: 401 for auth failure, 502 for backend unavailable, 503 for server not registered |
| No way to test a registered MCP server before exposing to customers | Bad server images discovered by customers | Admin API should include a `POST /servers/{name}/test` endpoint that runs the MCP initialization handshake and returns result |
| Container startup logs not surfaced | Operators register a server that silently fails to start | Pipe ECS container logs to CloudWatch; expose recent logs via admin API on server detail endpoint |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **JWT Validation:** Token signature verified but audience, issuer, and expiry all checked — verify with a test that constructs a token with correct signature but wrong `aud` and confirms 401
- [ ] **SSE Proxy:** Gateway forwards SSE events — verify with a tool that streams events over 10+ seconds and confirm client receives each event as it is emitted (not buffered until stream ends)
- [ ] **Session Routing:** Requests with `Mcp-Session-Id` reach the correct backend — verify with a multi-replica setup (or mock) that routes by session header
- [ ] **Container Isolation:** MCP containers not reachable except through gateway — verify by attempting direct HTTP call to container IP; confirm connection refused or security group block
- [ ] **OAuth Discovery:** `/.well-known/oauth-protected-resource` returns valid RFC 9728 document — verify by running an MCP client that performs discovery flow, not just pre-configured token
- [ ] **Health Gate:** Gateway does not route to a server until its ECS task health check passes — verify by registering a server and immediately requesting it; confirm 503 until healthy
- [ ] **Origin Validation:** MCP containers reject requests with disallowed Origin headers — verify by sending a request with `Origin: https://evil.example.com` and confirming rejection
- [ ] **Backwards Compat:** If old SSE transport is supported, verify the upgrade path — old client connects via legacy SSE endpoint and new client connects via Streamable HTTP to same server

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Gateway built for old SSE transport only | HIGH | Redesign proxy layer to handle Streamable HTTP; old SSE support becomes an opt-in backward-compat layer |
| Session routing absent, discovered at scale | MEDIUM | Add `Mcp-Session-Id` extraction and consistent hashing in gateway without changing backend; requires routing table persistence |
| JWT audience not validated | LOW | Add `audience=` parameter to decode call and add test; deploy hotfix |
| Token passthrough to backends | HIGH | Requires architectural change: add internal service credential layer; affects all backend container integrations |
| MCP container directly accessible | LOW-MEDIUM | Update ECS security group rules and task definition to remove public IP; verify with network scan |
| Blocking code in async gateway | MEDIUM | Profile with `asyncio` debug mode to identify blockers; wrap in `asyncio.to_thread()` or replace with async library |
| Cold start 502 errors on first request | MEDIUM | Implement health-check gate in registration flow; may require state machine in server registry |

---

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| SSE-only transport design | Gateway routing phase (first MCP work) | Integration test: Streamable HTTP client connects successfully |
| Session affinity absent | Gateway routing phase | Test: two requests with same session ID reach same backend |
| SSE stream buffering | Gateway proxy implementation | Test: streaming tool emits events client receives incrementally |
| JWT audience not validated | Auth implementation phase | Test: wrong-audience token returns 401 |
| Missing `.well-known` discovery | Auth implementation phase | Test: discovery flow with spec-compliant client succeeds |
| Token passthrough to backends | Auth implementation phase | Architecture review: no `Authorization` header forwarded to containers |
| Blocking code in async gateway | Gateway implementation + load test phase | Load test: 50 concurrent SSE connections show no stalling |
| ECS cold start 502s | Container lifecycle management phase | Test: register server, immediately request, verify 503 until healthy |
| Path routing ambiguity | Gateway routing phase | Integration test: server names with hyphens route correctly |
| MCP containers exposed publicly | Infrastructure / AWS deployment phase | Security scan: direct container IP returns no response |

---

## Sources

- [MCP Transports Specification (2025-03-26)](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) — Session management, Streamable HTTP requirements, backwards compatibility
- [MCP Authorization Specification (2025-06-18)](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization) — OAuth 2.1 Protected Resource Metadata, `.well-known` requirements
- [Why MCP Deprecated SSE — fka.dev](https://blog.fka.dev/blog/2025-06-06-why-mcp-deprecated-sse-and-go-with-streamable-http/) — SSE deprecation rationale
- [MCP Transport Future — MCP Blog](https://blog.modelcontextprotocol.io/posts/2025-12-19-mcp-transport-future/) — Session confusion, stateful routing bottlenecks
- [Why MCP's Move Away from SSE Simplifies Security — Auth0](https://auth0.com/blog/mcp-streamable-http/) — SSE security pitfalls
- [Implementing MCP: Tips, Tricks and Pitfalls — Nearform](https://nearform.com/digital-community/implementing-model-context-protocol-mcp-tips-tricks-and-pitfalls/) — Global state leaks, STDIO logging, tool confusion
- [Advanced Auth and Authorization for MCP Gateway — Red Hat Developer](https://developers.redhat.com/articles/2025/12/12/advanced-authentication-authorization-mcp-gateway) — Token passthrough, audience validation, privilege escalation
- [MCP Session Affinity with NGINX Plus — F5 DevCentral](https://community.f5.com/kb/technicalarticles/mcp-session-affinity-with-f5-nginx-plus/341961) — Sticky routing requirement
- [Taming Cold Starts on AWS Fargate — AWS in Plain English](https://aws.plainenglish.io/taming-cold-starts-on-aws-fargate-the-architecture-behind-sub-5-second-task-launches-622ebd73b051) — ECS Fargate cold start latency
- [Surviving SSE Behind Nginx Proxy Manager — Medium](https://medium.com/@dsherwin/surviving-sse-behind-nginx-proxy-manager-npm-a-real-world-deep-dive-69c5a6e8b8e5) — Proxy buffering and timeout configuration
- [Let's Fix OAuth in MCP — Aaron Parecki](https://aaronparecki.com/2025/04/03/15/oauth-for-model-context-protocol) — OAuth design critiques and `.well-known` requirements
- [MCP Security Vulnerabilities — Practical DevSecOps](https://www.practical-devsecops.com/mcp-security-vulnerabilities/) — Tool poisoning, prompt injection via MCP
- [Remote MCP in the Real World — Medium](https://medium.com/@yagmur.sahin/remote-mcp-in-the-real-world-oauth-2-1-9d149de6e475) — Protected Resource Metadata practical implementation
- [Avoiding ECS Fargate Pitfalls — Business Compass](https://knowledge.businesscompassllc.com/avoiding-ecs-fargate-pitfalls-a-practical-troubleshooting-handbook/) — ECS provisioning limits, DNS resolution failures

---
*Pitfalls research for: Managed MCP hosting platform (Switchboard)*
*Researched: 2026-04-14*
