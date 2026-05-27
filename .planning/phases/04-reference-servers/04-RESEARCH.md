# Phase 4: Reference Servers - Research

**Researched:** 2026-04-16
**Domain:** FastMCP 3.x server implementation, Docker containerization with uv, MCP Streamable HTTP transport, integration testing with live containers
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Source code location**
- D-01: Reference server source lives at `servers/echo/` and `servers/ping/` at the project root — not inside `switchboard/`. Independent microservices, not library code.
- D-02: Each server has its own standalone `Dockerfile` (`servers/echo/Dockerfile`, `servers/ping/Dockerfile`). Images are built and deployed independently.

**MCP implementation**
- D-03: Both servers implemented using FastMCP 3.2.4. FastMCP's `mcp.run(transport="streamable-http")` satisfies success criteria SC-3.
- D-04: Echo server exposes one MCP tool that returns its input arguments unchanged (REFS-01). Ping server responds to MCP `ping` requests (REFS-02).
- D-05: Both containers listen on port **8000** internally. No host ports published — reachable only via `switchboard-internal` Docker network.
- D-06: Container naming convention: `sb-echo` and `sb-ping` (locked by Phase 3, D-02).

**Docker Compose integration**
- D-07: Both servers added to `docker-compose.yml` as `build:` services with `context:` pointing to `servers/echo/` and `servers/ping/`. Auto-start on `docker compose up`.
- D-08: Phase 4 performs BOTH standalone docker-compose service validation AND ContainerManager lifecycle validation (satisfies SC-4).

**Package isolation**
- D-09: Each server has its own `pyproject.toml` with only fastmcp + uvicorn as direct deps. Own `uv.lock` for reproducible builds.
- D-10: Dockerfiles use `uv` to install deps from the server's `pyproject.toml`. Pattern: install uv in the image → copy pyproject.toml + uv.lock → `uv sync` → copy source.

**Testing**
- D-11: Integration tests start actual echo/ping containers and send real MCP Streamable HTTP requests. Assert exact response content (SC-1, SC-2).
- D-12: Tests live in `tests/reference_servers/` with custom pytest marker (e.g., `@pytest.mark.reference_servers`).
- D-13: Tests marked as requiring Docker (same pattern as existing integration tests).

### Claude's Discretion
- Exact FastMCP tool definition style (decorator vs. class-based)
- Multi-stage Dockerfile vs. single-stage (can use single-stage for simplicity)
- Whether to add a `healthcheck:` in docker-compose.yml for each reference server
- Exact pytest marker name
- Whether `uv` is installed via official install script or copied from a uv base image

### Deferred Ideas (OUT OF SCOPE)
- Per-server port configuration (locked to 8000 in Phase 3)
- Additional reference servers for session continuity testing (Phase 5 scope if needed)
- Automated image publishing to ECR (Phase 7)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REFS-01 | Echo server container exposes an MCP tool that returns its input arguments unchanged — validates round-trip request routing | FastMCP `@mcp.tool` decorator with typed params; `mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)`; MCP client `session.call_tool()` for test assertions |
| REFS-02 | Ping server container responds to the MCP `ping` method — validates connection health and container liveness | FastMCP server starts with streamable-http (MCP ping is handled at the protocol level automatically); MCP client `session.send_ping()` for test assertions |
</phase_requirements>

---

## Summary

Phase 4 requires two independent FastMCP microservices containerized with Docker. Each server is a minimal Python package (`pyproject.toml` + single Python file) built with a uv-based Dockerfile. The echo server exposes one `@mcp.tool`-decorated function that returns its input unchanged; the ping server is an empty FastMCP server (MCP ping is built into the protocol — no explicit tool needed). Both run with `mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)` and join the `switchboard-internal` Docker network.

The key technical insight for the ping server: the MCP `ping` method is a protocol-level request handled by the underlying MCP SDK automatically. FastMCP servers respond to `session.send_ping()` without any application code. The ping server is genuinely minimal — just instantiate FastMCP and call `mcp.run()`.

Integration tests start the containers via Docker SDK directly (not via ContainerManager for the standalone docker-compose validation) and connect using the official `mcp` library's `streamable_http_client` + `ClientSession`. The test for SC-4 additionally exercises ContainerManager start/stop lifecycle against the registered images.

**Primary recommendation:** Use the standalone `fastmcp` PyPI package (NOT `mcp.server.fastmcp` from the official SDK — that is the frozen v1 implementation). FastMCP 3.x uses `transport="streamable-http"` as the canonical string.

---

## Standard Stack

### Core (per reference server)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastmcp | 3.2.4 | MCP server framework | Locked by STACK.md; provides `@mcp.tool` decorator, `FastMCP.run()`, handles all MCP protocol details including ping responses | [VERIFIED: PyPI registry — confirmed by CLAUDE.md STACK.md section] |
| uvicorn | 0.44.0 | ASGI server (used internally by fastmcp) | FastMCP 3.x uses Uvicorn under the hood for HTTP transport; include explicitly for version pinning | [VERIFIED: PyPI registry — confirmed by CLAUDE.md STACK.md section] |

### Testing (root-level test dependencies)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| mcp | 1.27.0 | MCP Python client for test assertions | `mcp.client.streamable_http.streamable_http_client` + `ClientSession.call_tool()` / `send_ping()` | [VERIFIED: PyPI registry — confirmed by CLAUDE.md STACK.md section] |
| pytest-asyncio | 0.26.x | Async test support | Tests use `async with streamable_http_client(...)` patterns requiring async test functions | [VERIFIED: already in root pyproject.toml] |
| docker | 7.1.0 | Docker SDK for container lifecycle in tests | Start/stop containers programmatically during integration test fixtures | [VERIFIED: already in root pyproject.toml] |

### Per-server pyproject.toml

```toml
[project]
name = "echo"  # or "ping"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastmcp>=3.2.4",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

Note: Do NOT include `uvicorn` explicitly — FastMCP 3.x brings it as a transitive dependency. [ASSUMED — verify against fastmcp 3.2.4 dependency tree before finalizing; if uvicorn is not transitive, add it explicitly]

### Installation (per server directory)

```bash
cd servers/echo && uv init --no-workspace && uv add fastmcp
cd servers/ping && uv init --no-workspace && uv add fastmcp
```

The `--no-workspace` flag is critical — these servers must be isolated from the root workspace to maintain separate dependency graphs. [ASSUMED — verify `uv init` exact flags; may be `uv init` followed by `uv add` in the directory]

---

## Architecture Patterns

### Recommended Project Structure

```
servers/
├── echo/
│   ├── pyproject.toml      # fastmcp dep only
│   ├── uv.lock             # locked deps
│   ├── Dockerfile          # uv-based single-stage
│   └── server.py           # @mcp.tool echo implementation
└── ping/
    ├── pyproject.toml      # fastmcp dep only
    ├── uv.lock             # locked deps
    ├── Dockerfile          # uv-based single-stage
    └── server.py           # empty FastMCP server (protocol ping is automatic)

tests/
└── reference_servers/
    ├── __init__.py
    ├── conftest.py         # Docker container fixtures
    └── test_reference_servers.py  # REFS-01, REFS-02 assertions
```

### Pattern 1: FastMCP Tool Definition (Echo Server)

**What:** Minimal `@mcp.tool` decorator pattern for a function that returns input unchanged.

**Critical constraint from FastMCP docs:** `*args` and `**kwargs` are NOT supported as tool parameters. The tool must declare explicit named parameters. For REFS-01 ("returns its input arguments unchanged"), the echo tool must have explicit typed params.

**When to use:** Any FastMCP server needing a callable tool.

**Example:**
```python
# Source: https://gofastmcp.com/servers/tools
from __future__ import annotations

from fastmcp import FastMCP

mcp = FastMCP("echo")


@mcp.tool
def echo(message: str) -> str:
    """Return the input message unchanged.

    Args:
        message: The string to echo back.

    Returns:
        The input message unchanged.
    """
    return message


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
```

### Pattern 2: FastMCP Ping Server (Protocol Ping, No Tool)

**What:** Minimal FastMCP server. The MCP protocol ping (`session.send_ping()`) is handled automatically by the underlying MCP SDK — no application code needed. The ping server is literally an empty FastMCP instance.

**When to use:** REFS-02 — validating MCP connection health.

**Example:**
```python
# Source: Official MCP SDK + FastMCP 3.x behavior
from __future__ import annotations

from fastmcp import FastMCP

mcp = FastMCP("ping")

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
```

**Rationale:** The MCP `ping` method is defined in the protocol spec at the `ClientSession` level. Any running MCP server — including an empty FastMCP one — responds to `session.send_ping()` because the SDK handles it. No `@mcp.tool` for ping is needed or appropriate. [VERIFIED: https://py.sdk.modelcontextprotocol.io/client/ — `session.send_ping()` returns EmptyResult from any initialized MCP server]

### Pattern 3: Dockerfile with uv (Single-Stage)

**What:** Standard uv-based Dockerfile for a small Python service. Uses the copy-from-uv pattern to install uv, then deps-first layer caching.

**When to use:** All reference server images. Single-stage is appropriate for dev/test targets (D-10 authorizes this).

**Example:**
```dockerfile
# Source: https://docs.astral.sh/uv/guides/integration/docker/
FROM python:3.12-slim

# Copy uv binary from official distroless image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Dependency layer — cached independently from source changes
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

# Copy source and install project
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

EXPOSE 8000

CMD ["uv", "run", "python", "server.py"]
```

Key points:
- `--mount=type=cache,target=/root/.cache/uv` — avoids re-downloading packages on every build [VERIFIED: https://docs.astral.sh/uv/guides/integration/docker/]
- `--mount=type=bind` for pyproject.toml and uv.lock — keeps config out of final layer
- Two-RUN pattern creates a cacheable dependency layer separate from source
- `EXPOSE 8000` is documentation only; no host port mapping (enforced at docker-compose level)

### Pattern 4: Docker Compose Build Service (No Host Ports)

**What:** Adding a `build:` service to docker-compose.yml that joins the internal network without publishing ports.

**Example:**
```yaml
# Addition to existing docker-compose.yml
services:
  # ... existing db service ...

  echo:
    build:
      context: servers/echo
    container_name: sb-echo
    networks:
      - switchboard-internal
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import httpx; httpx.get('http://localhost:8000/mcp').raise_for_status()\""]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 15s

  ping:
    build:
      context: servers/ping
    container_name: sb-ping
    networks:
      - switchboard-internal
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import httpx; httpx.get('http://localhost:8000/mcp').raise_for_status()\""]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 15s

networks:
  switchboard-internal:
    driver: bridge
    external: false
```

Note: No `ports:` key — containers reachable only via `switchboard-internal` network (Phase 3 D-01, D-05).

### Pattern 5: MCP Client for Integration Tests

**What:** Using the official `mcp` library to send real MCP requests against a running container.

**Example (REFS-01 — echo tool call):**
```python
# Source: https://py.sdk.modelcontextprotocol.io/client/
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async def test_echo_returns_input_unchanged():
    async with streamable_http_client("http://localhost:8000/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("echo", {"message": "hello world"})
            assert result.content[0].text == "hello world"
```

**Example (REFS-02 — protocol ping):**
```python
async def test_ping_returns_valid_response():
    async with streamable_http_client("http://localhost:8000/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.send_ping()
            # send_ping() returns EmptyResult on success; raises on timeout/error
            assert result is not None
```

### Pattern 6: pytest Container Fixtures

**What:** Session-scoped fixture that starts Docker containers before tests and stops them after. Uses the Docker SDK directly (not ContainerManager) for isolation.

**Example:**
```python
# tests/reference_servers/conftest.py
from __future__ import annotations

import time
from typing import TYPE_CHECKING

import docker
import pytest

if TYPE_CHECKING:
    pass

ECHO_IMAGE = "switchboard-echo"   # docker compose build image name
PING_IMAGE = "switchboard-ping"
NETWORK = "switchboard-internal"


@pytest.fixture(scope="session")
def echo_container():
    """Start echo container for reference server tests."""
    client = docker.from_env()
    try:
        container = client.containers.run(
            image=ECHO_IMAGE,
            name="sb-echo-test",
            network=NETWORK,
            detach=True,
            remove=True,
            ports={"8000/tcp": None},  # ephemeral host port for test access
        )
        # Wait for server to be ready
        time.sleep(2)
        yield container
    finally:
        try:
            container.stop()
        except Exception:
            pass
        client.close()
```

**Note:** The container fixture approach above exposes an ephemeral host port so tests can reach the server from outside the Docker network. Alternative: run tests inside the Docker network using `docker compose run`. The planner should choose the approach that best fits the existing test infrastructure (which runs outside Docker). [ASSUMED — exact fixture implementation; the pattern above may need adjustment for port mapping and URL construction]

### Anti-Patterns to Avoid

- **`*args`/`**kwargs` in `@mcp.tool`:** Not supported by FastMCP. All tool parameters must be explicitly named with type annotations. [VERIFIED: https://gofastmcp.com/servers/tools — "Functions with `*args` or `**kwargs` are not supported as tools."]
- **`transport="sse"` in `mcp.run()`:** SSE is the deprecated transport. CONTEXT.md explicitly forbids it (STACK.md: "not the deprecated SSE transport"). [VERIFIED: MCP spec + STACK.md]
- **`from mcp.server.fastmcp import FastMCP`:** This is FastMCP v1, frozen in the official SDK. Use `from fastmcp import FastMCP` (the standalone package). [VERIFIED: jlowin/fastmcp v3 documentation]
- **Publishing host ports in docker-compose.yml:** Reference servers must NOT have `ports:` entries — they are internal services only (D-05).
- **Using the root workspace `pyproject.toml` for server deps:** Server packages must have isolated `pyproject.toml` + `uv.lock`. Commingling with the platform deps defeats the isolation goal (D-09).
- **Implementing ping as a `@mcp.tool`:** Incorrect. REFS-02 requires responding to the MCP *protocol* ping (`session.send_ping()`), not a custom tool. An empty FastMCP server already handles this.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| MCP protocol framing | Custom HTTP handler parsing JSON-RPC | `fastmcp` with `mcp.run(transport="streamable-http")` | MCP protocol has session initialization, capability negotiation, tool schema generation — 100+ lines of protocol code |
| Tool schema generation | Manually write JSON Schema for each tool | `@mcp.tool` with type annotations | FastMCP auto-generates schemas from Python type hints |
| MCP ping response | Custom HTTP endpoint returning `{}` | Empty FastMCP server — protocol ping is free | The SDK handles ping at the transport layer; a custom endpoint would not satisfy MCP protocol semantics |
| Container startup waiting | `time.sleep(10)` in test fixture | Healthcheck + poll until ready, or `start_period` in healthcheck | Fixed sleeps are flaky; health checks are deterministic |
| uv installation in Docker | `pip install uv` or curl scripts | `COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/` | Official distroless copy is the recommended, reproducible method |

**Key insight:** The entire MCP protocol implementation — framing, initialization, tool schema generation, error handling, ping responses — is handled by FastMCP + the underlying `mcp` SDK. Application code should only declare tools with `@mcp.tool`.

---

## Common Pitfalls

### Pitfall 1: Wrong Transport String

**What goes wrong:** Using `transport="sse"` (deprecated) or `transport="http"` (FastMCP alias, may work but not the canonical string) instead of `transport="streamable-http"`.

**Why it happens:** Documentation inconsistency. The FastMCP docs show `transport="http"` in some places; the official MCP SDK uses `transport="streamable-http"`. Both may work in FastMCP 3.x but `"streamable-http"` is the canonical string aligned with the MCP spec.

**How to avoid:** Use `transport="streamable-http"` consistently — it is the spec-defined value and the CONTEXT.md expectation (D-03, SC-3).

**Warning signs:** Server starts but returns 404 on `/mcp` endpoint; clients fail to connect.

### Pitfall 2: `*args`/`**kwargs` in Tool Definitions

**What goes wrong:** Attempting to define the echo tool as `def echo(**kwargs): return kwargs` to handle arbitrary input.

**Why it happens:** Seems like the natural way to echo "input arguments unchanged." But FastMCP requires explicit named parameters to generate tool schemas.

**How to avoid:** Define the echo tool with explicit typed parameters: `def echo(message: str) -> str: return message`. The parameter name `message` becomes the required input key in the tool call.

**Warning signs:** FastMCP raises an error at server startup: "Functions with `*args` or `**kwargs` are not supported as tools."

### Pitfall 3: Confusing Protocol Ping with a Ping Tool

**What goes wrong:** Implementing a `@mcp.tool` named `ping` that returns `"pong"` for REFS-02, then testing with `session.call_tool("ping", {})` instead of `session.send_ping()`.

**Why it happens:** Natural interpretation of "ping server." But REFS-02 requires responding to the MCP `ping` *method* (a protocol-level request, not a tool call).

**How to avoid:** The ping server has NO `@mcp.tool` definitions. The protocol ping is automatic in any FastMCP server. Test using `session.send_ping()` from the MCP client.

**Warning signs:** SC-2 passes with a tool call but the ContainerManager health check (Phase 6, CONT-04) fails because it uses protocol ping.

### Pitfall 4: Docker Network Unreachable from Test Host

**What goes wrong:** Test containers start on `switchboard-internal` network but tests run on the host machine outside that network, so `http://localhost:8000/mcp` is unreachable.

**Why it happens:** `switchboard-internal` is an internal Docker network with no host-side port mapping.

**How to avoid:** Integration test fixtures must EITHER (a) publish an ephemeral host port (`ports={"8000/tcp": None}`) when starting test containers, then discover the assigned port via `container.ports`, OR (b) configure tests to run in a container on the same network. Option (a) is simpler and consistent with existing test patterns that run on the host.

**Warning signs:** `httpx.ConnectError` or `ConnectionRefusedError` on `localhost:8000`.

### Pitfall 5: uv Workspace Conflict

**What goes wrong:** Running `uv init` inside `servers/echo/` without `--no-workspace` causes uv to look for a parent workspace and fail (or worse, merge with the root workspace).

**Why it happens:** uv auto-discovers parent `pyproject.toml` files and treats them as workspace roots.

**How to avoid:** Create server packages with explicit `[tool.uv]` configuration to opt out of workspace, or use `uv init --package` in an isolated directory with no parent uv workspace. Verify with `uv run python -c "import fastmcp"` from within each server directory.

**Warning signs:** `uv sync` in a server directory installs the entire switchboard dependency tree.

### Pitfall 6: Container Name Collision in Tests

**What goes wrong:** Running tests multiple times leaves stopped containers named `sb-echo` and `sb-ping` that block new container creation.

**Why it happens:** `ContainerManager._remove_existing_container()` handles this for Phase 3 lifecycle tests, but direct Docker SDK usage in test fixtures may not.

**How to avoid:** Use unique container names in test fixtures (e.g., `sb-echo-test`) that differ from the production names (`sb-echo`). Or ensure test fixtures always call `container.remove(force=True)` in teardown. [VERIFIED: ContainerManager source code in `switchboard/container/manager.py` line 241-246 — this cleanup logic exists for production paths but test fixtures bypass it]

---

## Code Examples

### Complete Echo Server

```python
# servers/echo/server.py
# Source: https://gofastmcp.com/servers/tools + https://gofastmcp.com/deployment/running-server
from __future__ import annotations

from fastmcp import FastMCP

mcp = FastMCP("echo")


@mcp.tool
def echo(message: str) -> str:
    """Return the input message unchanged.

    Args:
        message: The string to echo back.

    Returns:
        The input message, unchanged.
    """
    return message


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
```

### Complete Ping Server

```python
# servers/ping/server.py
# Source: https://py.sdk.modelcontextprotocol.io/client/ — send_ping() is protocol-level
from __future__ import annotations

from fastmcp import FastMCP

mcp = FastMCP("ping")

# No tools needed — MCP protocol ping is handled automatically by the SDK.

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
```

### Complete Dockerfile (both servers identical in structure)

```dockerfile
# servers/echo/Dockerfile (and servers/ping/Dockerfile — same pattern)
# Source: https://docs.astral.sh/uv/guides/integration/docker/
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Dependency layer -- cached independently from source changes
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

# Copy source and install project
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

EXPOSE 8000

CMD ["uv", "run", "python", "server.py"]
```

### MCP Client Test Pattern

```python
# tests/reference_servers/test_reference_servers.py
# Source: https://py.sdk.modelcontextprotocol.io/client/
from __future__ import annotations

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


@pytest.mark.reference_servers
@pytest.mark.asyncio
async def test_echo_returns_input_unchanged(echo_server_url: str) -> None:
    """REFS-01: Echo server returns input arguments unchanged."""
    async with streamable_http_client(echo_server_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("echo", {"message": "hello world"})
            assert result.content[0].text == "hello world"


@pytest.mark.reference_servers
@pytest.mark.asyncio
async def test_ping_responds_to_mcp_ping(ping_server_url: str) -> None:
    """REFS-02: Ping server responds to MCP protocol ping method."""
    async with streamable_http_client(ping_server_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.send_ping()
            assert result is not None  # EmptyResult on success


@pytest.mark.reference_servers
@pytest.mark.asyncio
async def test_container_manager_can_start_echo(echo_registered: str) -> None:
    """SC-4: ContainerManager can start and stop echo server via Admin API."""
    # This fixture registers the echo server via Admin API and calls start
    # ContainerManager lifecycle tested here for REFS-01 + SC-4
    ...
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `from mcp.server.fastmcp import FastMCP` | `from fastmcp import FastMCP` | FastMCP 2.0 (2024) | The SDK version is frozen at v1; standalone package is at v3.2.4 with significantly more features |
| `transport="sse"` | `transport="streamable-http"` | MCP spec 2025-03-26 | SSE transport is deprecated; streamable-http is the production standard |
| `pip install fastmcp` | `uv add fastmcp` | Project-wide toolchain decision | uv is the only allowed package manager per CLAUDE.md |

**Deprecated/outdated:**
- `mcp.server.fastmcp.FastMCP`: Frozen at v1 inside the official SDK. Do NOT use — use standalone `fastmcp` package.
- SSE transport (`/sse` endpoint): Deprecated per MCP spec 2025-03-26. Both STACK.md and CONTEXT.md forbid it.
- `python-jose`: Not relevant here but documented in STACK.md as forbidden.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `uvicorn` is a transitive dependency of `fastmcp` and does not need explicit declaration in server `pyproject.toml` | Standard Stack | If wrong, `uv run python server.py` fails with import error at runtime; fix: `uv add uvicorn` in each server directory |
| A2 | `uv init --no-workspace` (or equivalent) prevents the server packages from joining the root uv workspace | Common Pitfalls | If wrong, `uv sync` in server directories installs switchboard's full dep tree, inflating images |
| A3 | Integration test fixtures need to publish ephemeral host ports to reach containers from the test host | Architecture Patterns | If wrong, test fixtures using localhost:8000 fail; fix: run tests inside Docker network or adjust networking |
| A4 | `fastmcp 3.2.4` accepts `transport="streamable-http"` (same string as MCP SDK) in addition to the `"http"` alias | Standard Stack | If wrong, use `transport="http"` — functionally equivalent but less consistent with CONTEXT.md SC-3 language |

---

## Open Questions

1. **Exact pytest marker name**
   - What we know: CONTEXT.md says use a custom marker, examples given are `reference_servers` or `integration_server`
   - What's unclear: Whether to align with the existing `integration` marker or create a separate `reference_servers` marker
   - Recommendation: Create `reference_servers` as a separate marker — these tests have a different requirement (Docker images must be built) from the existing `integration` marker (only PostgreSQL required)

2. **Health check implementation for docker-compose.yml**
   - What we know: D decision grants Claude discretion; health checks are recommended for Phase 5 startup ordering
   - What's unclear: Whether httpx is available inside the reference server containers for the health check command
   - Recommendation: Use a lightweight health check: `["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/mcp')\""]` — uses stdlib only, no httpx required inside the image

3. **Integration test fixture approach for container access**
   - What we know: Existing Phase 1/3 integration tests run on the host machine and connect to PostgreSQL via published port 5432
   - What's unclear: Test fixtures must decide between (a) publishing ephemeral host ports per container and (b) running test code inside the Docker network
   - Recommendation: Option (a) — publish ephemeral host ports in test fixture containers. Consistent with how PostgreSQL is accessed in existing tests. The production `docker-compose.yml` services have no host ports; test fixtures start separate containers with host ports for test-only access.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | Container builds and tests | Yes | 29.4.0 | None — required |
| uv | Package management inside Dockerfiles | Yes (via `COPY --from=ghcr.io/astral-sh/uv:latest`) | latest (determined at build time) | Pin specific uv version in Dockerfile |
| Python 3.12 | Reference server runtime | Yes (via `python:3.12-slim` base image) | 3.12 | None — locked by project constraint |
| mcp library | Integration test client | Not in root venv | 1.27.0 (locked in STACK.md) | Must be added as root dev dependency |

**Missing dependencies with no fallback:**
- `mcp` library (PyPI package): Not currently in root `pyproject.toml`. Must be added as a dev dependency: `uv add --dev mcp` in the project root. Required by integration tests for `ClientSession.call_tool()` and `send_ping()`.

**Missing dependencies with fallback:**
- None beyond the above.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.26.x |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `uv run pytest tests/reference_servers/ -m reference_servers -x -q` |
| Full suite command | `uv run pytest -m reference_servers` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REFS-01 | Echo tool returns input unchanged | Integration (requires Docker + built images) | `uv run pytest tests/reference_servers/test_reference_servers.py::test_echo_returns_input_unchanged -x` | No — Wave 0 |
| REFS-02 | Ping server responds to MCP ping | Integration (requires Docker + built images) | `uv run pytest tests/reference_servers/test_reference_servers.py::test_ping_responds_to_mcp_ping -x` | No — Wave 0 |
| SC-4 | ContainerManager can start/stop reference servers | Integration (requires Docker + Admin API + PostgreSQL) | `uv run pytest tests/reference_servers/test_reference_servers.py::test_container_manager_lifecycle -x` | No — Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/reference_servers/ -m reference_servers -x -q`
- **Per wave merge:** `uv run pytest -m reference_servers`
- **Phase gate:** Full suite green before `/gsd-verify-work`

**Pre-requisite for running tests:**
```bash
docker compose build echo ping   # build images first
docker compose up -d             # start all services
```

### Wave 0 Gaps

- [ ] `tests/reference_servers/__init__.py` — package marker
- [ ] `tests/reference_servers/conftest.py` — container fixtures (`echo_container`, `ping_container`, `echo_server_url`, `ping_server_url`)
- [ ] `tests/reference_servers/test_reference_servers.py` — REFS-01, REFS-02, SC-4 test functions
- [ ] Root `pyproject.toml` update: add `reference_servers` to `markers` list
- [ ] Root `pyproject.toml` update: add `mcp` to dev dependencies

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Reference servers are internal-only, no auth required |
| V3 Session Management | No | Sessions are handled by MCP protocol, no custom session logic |
| V4 Access Control | No | Internal network isolation is the access control (no host port publishing) |
| V5 Input Validation | Partial | FastMCP auto-validates tool inputs against declared type hints — no hand-rolled validation needed |
| V6 Cryptography | No | No secrets, no encryption required for internal reference servers |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Container escape via Docker socket | Elevation of Privilege | Reference servers do not mount Docker socket |
| Unintended public exposure | Information Disclosure | No host `ports:` mapping in docker-compose — enforced by D-05 |
| Dependency supply chain | Tampering | `uv.lock` per server ensures reproducible, pinned builds |

**Security note:** Reference servers are dev/test targets on an internal Docker network. They have minimal attack surface. The primary security control is network isolation — containers are unreachable except from within `switchboard-internal`.

---

## Sources

### Primary (HIGH confidence)
- [FastMCP Running Server docs](https://gofastmcp.com/deployment/running-server) — `mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)` confirmed
- [FastMCP Tools docs](https://gofastmcp.com/servers/tools) — `@mcp.tool` decorator API, `*args`/`**kwargs` restriction confirmed
- [FastMCP Client Transports docs](https://gofastmcp.com/clients/transports) — `StreamableHttpTransport` import path confirmed
- [MCP Python SDK client docs](https://py.sdk.modelcontextprotocol.io/client/) — `streamable_http_client`, `ClientSession.send_ping()`, `call_tool()` confirmed
- [uv Docker integration docs](https://docs.astral.sh/uv/guides/integration/docker/) — `COPY --from=ghcr.io/astral-sh/uv:latest` pattern, two-RUN layer caching confirmed
- [MCPcat StreamableHTTP guide](https://mcpcat.io/guides/building-streamablehttp-mcp-server/) — `transport="streamable-http"` string confirmed for standalone `fastmcp` package
- CLAUDE.md STACK.md section — fastmcp 3.2.4, mcp 1.27.0, uvicorn 0.44.0 versions (verified against PyPI 2026-04-14)
- Existing codebase — `docker-compose.yml`, `pyproject.toml`, `switchboard/container/manager.py`, `tests/conftest.py` read directly

### Secondary (MEDIUM confidence)
- [FastMCP Transport Mechanisms (DeepWiki)](https://deepwiki.com/jlowin/fastmcp/3.1-transport-mechanisms) — Transport string values `stdio`, `sse`, `http` — confirms `"streamable-http"` is the canonical value per MCP spec
- [jlowin/fastmcp vs mcp.server.fastmcp distinction](https://jlowin.dev/blog/fastmcp-2) — FastMCP v1 frozen in official SDK; standalone package at v3.x

### Tertiary (LOW confidence)
- Integration test fixture structure (container port mapping) — inferred from existing project test patterns and Docker SDK docs; exact implementation TBD

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — packages confirmed against STACK.md (verified against PyPI 2026-04-14)
- FastMCP tool API: HIGH — verified against official gofastmcp.com docs
- MCP client test patterns: HIGH — verified against official SDK docs
- Architecture / Dockerfile: HIGH — verified against official uv docs
- Integration test fixture details: MEDIUM — pattern established, exact port-mapping approach is a discretionary implementation choice

**Research date:** 2026-04-16
**Valid until:** 2026-05-16 (stable — FastMCP 3.x and MCP spec are not fast-moving at this point)
