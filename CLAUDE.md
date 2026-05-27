<!-- GSD:project-start source:PROJECT.md -->
## Project

**Switchboard**

Switchboard is a managed MCP (Model Context Protocol) hosting platform that serves as both a deployment target for MCP servers and a centralized access point for customers. Organizations deploy approved MCP servers onto Switchboard; customers connect through a single namespaced URL, authenticated via OAuth/JWT. The platform enforces organizational security by ensuring only approved servers are accessible.

**Core Value:** Organizations can deploy, manage, and govern MCP servers in one place — customers get a single, secure access point without needing to discover or connect to individual servers themselves.

### Constraints

- **Language**: Python 3.12+ — all application code
- **Structure**: Top-level package is `switchboard/`, not `src/`
- **Containerization**: All components must be containerized (Docker)
- **Cloud**: AWS for production; local Docker Compose for development
- **Best practices**: Architecture and code must follow current Python and MCP best practices
- **Auth**: OAuth/JWT — no API-key-only auth
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Recommended Stack
### Core Technologies
| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12+ | Application language | Project constraint; 3.12 brings performance gains and matches ecosystem requirements for mcp/fastmcp |
| FastAPI | 0.135.3 | Admin REST API + HTTP gateway | ASGI-native, async-first, Pydantic v2 integration, OpenAPI docs out of the box; the dominant Python API framework in 2026 |
| Uvicorn | 0.44.0 | ASGI server | Production ASGI server; pairs natively with FastAPI; supports `--workers` flag for multi-process without Gunicorn |
| mcp (official SDK) | 1.27.0 | MCP protocol implementation | Official Anthropic SDK; provides `streamable-http` transport which is the production standard as of 2025; required for building protocol-compliant MCP proxies |
| FastMCP | 3.2.4 | MCP server framework for reference servers | Higher-level Pythonic abstraction on top of the official MCP SDK; use for the echo/ping reference servers; powers ~70% of all MCP servers; not needed in the gateway itself |
| httpx | 0.28.1 | HTTP client for reverse proxy relay | Async-native, streaming-capable; used in the gateway to proxy MCP requests from the namespaced URL to the correct backend container; supports SSE and chunked streaming |
| PostgreSQL | 16+ | Server registry database | The standard relational database for service registries; strong JSON support for arbitrary server metadata; pairs with asyncpg for async access |
| SQLAlchemy | 2.0.49 | ORM (async) | The 2.0 API is the async-native rewrite; standard for FastAPI + PostgreSQL; works with alembic for migrations |
| asyncpg | 0.31.0 | Async PostgreSQL driver | Fastest async Postgres driver for Python; required by SQLAlchemy's async engine (`postgresql+asyncpg://`) |
| Alembic | 1.18.4 | Database migrations | The standard migration tool for SQLAlchemy; generates migration scripts from model changes |
| Pydantic | 2.13.0 | Data validation | FastAPI's validation layer; v2 is required with current FastAPI; defines request/response shapes for Admin API |
| pydantic-settings | 2.13.1 | Configuration management | Reads config from environment variables and `.env` files; the standard way to manage secrets/settings in containerized Python apps since Pydantic v2 split settings into a separate package |
### Authentication Technologies
| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| PyJWT | 2.12.1 | JWT encode/decode | FastAPI docs officially moved away from python-jose (abandoned, has Python 3.12 deprecation warnings); PyJWT is actively maintained, minimal dependencies |
| Authlib | 1.6.10 | OAuth2 server (authorization server flows) | If Switchboard acts as its own OAuth2 authorization server (issues tokens), Authlib provides the full server-side OAuth2 implementation including token introspection and JWKS endpoints |
### AWS Infrastructure
| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| AWS ECS + Fargate | — | Container orchestration | ECS+Fargate is the right choice for this project: no Kubernetes expertise required, simpler task definitions vs. K8s manifests, AWS-native service discovery, lower operational overhead; EKS adds ~$74/month control plane cost and significant complexity without benefit at this scale |
| AWS Application Load Balancer (ALB) | — | Path-based routing | Handles `/servers/{server-name}` routing at the infrastructure layer; each MCP server container can be a separate ECS service registered as an ALB target group; path rules route traffic to the correct service |
| Amazon ECR | — | Container registry | AWS-native, integrates with ECS task definitions and IAM; no separate registry to manage |
| AWS RDS (PostgreSQL) | — | Managed database | Managed PostgreSQL for the server registry; RDS handles backups, failover, and patching; use `db.t4g.small` for dev, scale up for prod |
| AWS Secrets Manager | — | Secret storage | Stores DB credentials, JWT signing keys, OAuth client secrets; integrates with ECS task definitions via environment injection |
| AWS CDK v2 (Python) | 2.x | Infrastructure as Code | Python-native CDK is the IaC recommendation for Python teams targeting AWS; the `aws_ecs_patterns` construct library provides high-level `ApplicationLoadBalancedFargateService` constructs that reduce boilerplate significantly; community is very active (150+ PRs in Jan-Feb 2026 alone) |
### Supporting Libraries
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| docker (Python SDK) | 7.1.0 | Docker Engine API client | Local development only — used by the gateway service to start/stop/inspect MCP server containers via Docker socket; **not** used in production (ECS handles orchestration) |
| httpx-sse | 0.4.0 | SSE streaming via httpx | When proxying SSE streams from backend MCP servers; provides `aiter_sse` for consuming server-sent events from the backend before relaying to the client |
| structlog | 25.x | Structured logging | JSON-formatted logs that integrate with AWS CloudWatch; easier to query than plaintext logs in production |
| tenacity | 9.x | Retry logic | For retrying failed backend container health checks and connection attempts on startup; avoids hand-rolled retry loops |
| pytest | 8.x | Testing framework | Standard Python testing; pair with `pytest-asyncio` for async test support |
| pytest-asyncio | 0.26.x | Async test support | Required for testing FastAPI async endpoints and async SQLAlchemy sessions |
| respx | 0.22.x | Mock httpx in tests | Test the reverse proxy layer by mocking backend container responses without running real MCP servers |
### Development Tools
| Tool | Purpose | Notes |
|------|---------|-------|
| Docker Compose | Local multi-container topology | Runs gateway, reference MCP servers, and PostgreSQL as a unified local stack; mirrors production container topology without ECS complexity |
| uv | Package management and virtual environments | Project requirement; replaces pip/poetry; use `uv add` and `uv sync` |
| ruff | Linting and formatting | Project requirement; replaces flake8/black/isort |
| mypy (strict) or ty | Type checking | Enforce type annotations on all public API surfaces; `--strict` mode |
## Installation
# Core application dependencies
# Database
# Auth
# Config
# Observability
# AWS (production)
# Dev dependencies
## Alternatives Considered
| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| ECS + Fargate | EKS + Fargate | If the org has existing Kubernetes expertise, is running other K8s workloads, or needs multi-cloud portability |
| ECS + Fargate | ECS + EC2 launch type | If workloads need GPUs, custom kernel params, or more predictable compute costs at scale |
| FastAPI | Starlette (raw) | If Admin API overhead is genuinely a concern; FastAPI is built on Starlette and the overhead is negligible in practice |
| FastAPI | Django REST Framework | If the project grows into a full multi-app platform with admin UI, migrations managed by Django ORM, etc. — overkill for v1 |
| PostgreSQL | SQLite | SQLite is appropriate only for local development without Docker; not viable for multi-instance production |
| PyJWT + external IdP | Authlib (full auth server) | If the platform needs to issue its own OAuth2 tokens rather than delegate to AWS Cognito/Auth0/Okta |
| AWS CDK v2 | Terraform | If the broader infrastructure org uses Terraform and cross-team consistency matters more than Python-native IaC |
| httpx (custom proxy) | nginx/traefik as sidecar | If routing logic becomes complex enough to warrant a dedicated reverse proxy binary; for v1, the Python proxy gives more flexibility for auth injection |
## What NOT to Use
| Avoid | Why | Use Instead |
|-------|-----|-------------|
| python-jose | Last release was 3+ years ago; generates deprecation warnings on Python 3.12 with `datetime` functions; effectively abandoned for a security-critical library | PyJWT 2.12.1 |
| SSE transport for MCP | SSE (`/sse`) is the legacy MCP transport; the MCP spec now recommends Streamable HTTP as the production standard; SSE is being deprecated | MCP Streamable HTTP (`/mcp`) transport |
| Requests (sync HTTP) | Blocking I/O in an async FastAPI application will block the event loop and kill concurrency; requests is synchronous only | httpx with AsyncClient |
| psycopg2 (sync) | Same reason as requests — psycopg2 is synchronous and blocks the event loop; SQLAlchemy 2.0 async engine requires an async driver | asyncpg (via `postgresql+asyncpg://`) |
| Docker Swarm | Swarm is in maintenance mode; not the AWS-native path; no clear migration to ECS | AWS ECS with Fargate |
| Gunicorn as process manager in containers | On Kubernetes/ECS, the orchestrator manages process-level availability; Gunicorn adds complexity without benefit in containerized deployments; use `uvicorn --workers N` instead | Uvicorn native workers (`uvicorn app:app --workers 4`) |
| SQLite in production | No concurrent write support for multi-instance deployments; not viable when the gateway scales to multiple ECS tasks | PostgreSQL via RDS |
## Stack Patterns by Variant
- Use `docker` Python SDK to start/stop MCP server containers programmatically
- Use a local PostgreSQL container (not RDS)
- Use Uvicorn in reload mode (`--reload`) for the gateway and admin API
- Mount MCP server images from local builds; use named Docker networks for service discovery
- Use boto3 ECS client (not docker SDK) to register/deregister task definitions and update services
- Use ALB listener rules to route `/servers/{server-name}/*` paths to the correct ECS service target group
- Use ECS Service Connect or AWS Cloud Map for internal service discovery between the gateway and MCP containers
- Use Secrets Manager to inject DB credentials and JWT signing keys as environment variables in task definitions
- PyJWT + JWKS endpoint fetch is sufficient
- Use `httpx.AsyncClient` to fetch the public key from the IdP's JWKS URI at startup and cache it
- Validate token signature, expiry, and audience claims on every request
- Add Authlib with its `AuthorizationServer` class
- Requires a persistent token store (PostgreSQL table)
- Significantly increases scope — defer to post-v1
## Version Compatibility
| Package | Compatible With | Notes |
|---------|-----------------|-------|
| FastAPI 0.135.x | Pydantic 2.13.x | FastAPI 0.100+ requires Pydantic v2; v1 compatibility shim exists but adds overhead |
| SQLAlchemy 2.0.49 | asyncpg 0.31.0 | Use `create_async_engine("postgresql+asyncpg://...")` — not `postgresql://` which silently blocks the event loop |
| mcp 1.27.x | FastAPI 0.135.x | MCP's streamable HTTP transport returns a Starlette app; mount it with `app.mount("/servers/{name}", mcp_app)` |
| FastMCP 3.2.4 | mcp 1.27.x | FastMCP 3.x is built on the official SDK; versions should track closely |
| Alembic 1.18.x | SQLAlchemy 2.0.x | Alembic 1.13+ is required for SQLAlchemy 2.0 full compatibility |
| PyJWT 2.12.x | Python 3.12+ | Active maintenance; no deprecation warnings on 3.12 (unlike python-jose) |
| pydantic-settings 2.13.x | Pydantic 2.13.x | Must match major version of pydantic |
## Sources
- PyPI: `mcp` package — version 1.27.0 verified April 14, 2026; streamable HTTP as production transport
- PyPI: `fastmcp` package — version 3.2.4 verified April 14, 2026
- PyPI: `fastapi` package — version 0.135.3 verified April 14, 2026
- PyPI: `uvicorn` package — version 0.44.0 verified April 14, 2026
- PyPI: `httpx` package — version 0.28.1 verified April 14, 2026
- PyPI: `sqlalchemy` package — version 2.0.49 verified April 14, 2026
- PyPI: `asyncpg` package — version 0.31.0 verified April 14, 2026
- PyPI: `alembic` package — version 1.18.4 verified April 14, 2026
- PyPI: `pydantic` package — version 2.13.0 verified April 14, 2026
- PyPI: `pydantic-settings` package — version 2.13.1 verified April 14, 2026
- PyPI: `PyJWT` package — version 2.12.1 verified April 14, 2026
- PyPI: `Authlib` package — version 1.6.10 verified April 14, 2026
- PyPI: `docker` (Python SDK) — version 7.1.0 verified April 14, 2026
- FastAPI GitHub discussion #9587 — community confirmation that python-jose is abandoned; PyJWT is the replacement (MEDIUM confidence — community source, aligns with PyPI activity data)
- AWS docs: ALB path-based routing with ECS Fargate (HIGH confidence — official AWS docs)
- AWS CDK community update Jan/Feb 2026 — CDK v2 active maintenance confirmed (MEDIUM confidence)
- WebSearch: ECS vs EKS vs Fargate 2025 comparison — ECS+Fargate recommended for teams without Kubernetes expertise (MEDIUM confidence — multiple sources agree)
- MCP spec transports: https://modelcontextprotocol.io/specification/2025-03-26/basic/transports — streamable HTTP is the specified production transport (HIGH confidence)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

| Skill | Description | Path |
|-------|-------------|------|
| coding-standards | Universal coding standards, best practices, and patterns for TypeScript, JavaScript, React, and Node.js development. | `.claude/skills/coding-standards/SKILL.md` |
| continuous-learning-v2 | Instinct-based learning system that observes sessions via hooks, creates atomic instincts with confidence scoring, and evolves them into skills/commands/agents. | `.claude/skills/continuous-learning-v2/SKILL.md` |
| docker-patterns | Docker and Docker Compose patterns for local development, container security, networking, volume strategies, and multi-service orchestration. | `.claude/skills/docker-patterns/SKILL.md` |
| python-patterns | Pythonic idioms, PEP 8 standards, type hints, and best practices for building robust, efficient, and maintainable Python applications. | `.claude/skills/python-patterns/SKILL.md` |
| python-testing | Python testing strategies using pytest, TDD methodology, fixtures, mocking, parametrization, and coverage requirements. | `.claude/skills/python-testing/SKILL.md` |
| security-review | Use this skill when adding authentication, handling user input, working with secrets, creating API endpoints, or implementing payment/sensitive features. Provides comprehensive security checklist and patterns. | `.claude/skills/security-review/SKILL.md` |
| security-scan | Scan your Claude Code configuration (.claude/ directory) for security vulnerabilities, misconfigurations, and injection risks using AgentShield. Checks CLAUDE.md, settings.json, MCP servers, hooks, and agent definitions. | `.claude/skills/security-scan/SKILL.md` |
| strategic-compact | Suggests manual context compaction at logical intervals to preserve context through task phases rather than arbitrary auto-compaction. | `.claude/skills/strategic-compact/SKILL.md` |
| tdd-workflow | Use this skill when writing new features, fixing bugs, or refactoring code. Enforces test-driven development with 80%+ coverage including unit, integration, and E2E tests. | `.claude/skills/tdd-workflow/SKILL.md` |
| verification-loop | "A comprehensive verification system for Claude Code sessions." | `.claude/skills/verification-loop/SKILL.md` |
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
