# Phase 4: Reference Servers - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-16
**Phase:** 04-reference-servers
**Areas discussed:** Source code location, Docker Compose integration, Testing scope, Package isolation

---

## Source code location

| Option | Description | Selected |
|--------|-------------|----------|
| servers/echo/ and servers/ping/ at root | Top-level servers/ directory. Clear separation: services, not library code. Easy to extend. | ✓ |
| reference-servers/echo/ and reference-servers/ping/ | More descriptive name, same structure | |
| Inside switchboard/ package | e.g., switchboard/reference_servers/. Mixes platform and test targets | |

**User's choice:** `servers/echo/` and `servers/ping/` at project root

| Option | Description | Selected |
|--------|-------------|----------|
| Own Dockerfile per server | servers/echo/Dockerfile and servers/ping/Dockerfile. Standard for multi-container. | ✓ |
| Shared base Dockerfile, server-specific layers | Base Python+FastMCP image, server adds tools. Reduces duplication. | |
| Single Dockerfile with build arg | BUILD_TARGET=echo or ping. CI pipelines harder. | |

**User's choice:** Each server has its own standalone Dockerfile

---

## Docker Compose integration

| Option | Description | Selected |
|--------|-------------|----------|
| Build services with auto-start | Add as build: services, auto-start on docker compose up. Seamless local dev. | ✓ |
| Pre-built images, started via ContainerManager only | More realistic to production but more friction locally | |
| docker-compose profiles | Optional services under a compose profile | |

**User's choice:** Build services with auto-start in docker-compose.yml

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — register via Admin API and ContainerManager | Satisfies SC-4 directly in Phase 4 | ✓ |
| No — just build images, Phase 5 handles registration | Lighter Phase 4 scope | |
| Claude's discretion | Planner decides | |

**User's choice:** Yes — register via Admin API and verify ContainerManager can start them in Phase 4

---

## Testing scope

| Option | Description | Selected |
|--------|-------------|----------|
| Integration tests: run container + actual MCP tool call | Start containers, send real MCP HTTP request, assert response. Fully satisfies SC-1/SC-2. | ✓ |
| Build smoke test only | Verify images build and start without crash. Phase 5 validates protocol behavior. | |
| Unit tests for server logic + E2E deferred | Unit test tool functions, Phase 5 handles protocol validation. | |

**User's choice:** Integration tests — run container and send actual MCP tool call

| Option | Description | Selected |
|--------|-------------|----------|
| tests/test_reference_servers.py or tests/reference_servers/ | Co-located with platform tests, custom pytest marker | ✓ |
| Test files inside servers/echo/ and servers/ping/ | Isolated per server, splits test suite | |

**User's choice:** `tests/reference_servers/` inside root tests directory

---

## Package isolation

| Option | Description | Selected |
|--------|-------------|----------|
| Own pyproject.toml per server | Lean, isolated Docker images. Standard for containerized microservices. | ✓ |
| Shared root pyproject.toml | Simpler but mixes platform and server concerns | |
| requirements.txt per server | Simplest, no uv toolchain, loses locked builds | |

**User's choice:** Own pyproject.toml per server with own uv.lock

| Option | Description | Selected |
|--------|-------------|----------|
| uv + pyproject.toml with uv sync | Consistent with project toolchain, reproducible builds | ✓ |
| pip install fastmcp in Dockerfile | Simpler but inconsistent with project standards | |
| Claude's discretion | Planner picks | |

**User's choice:** uv + pyproject.toml with uv sync in Dockerfile

---

## Claude's Discretion

- FastMCP tool definition style (decorator vs. class-based)
- Multi-stage vs. single-stage Dockerfile
- Whether to add healthcheck: in docker-compose.yml for each reference server
- Exact pytest marker name
- How uv is installed inside the Docker image
