---
phase: 04-reference-servers
reviewed: 2026-04-16T00:00:00Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - docker-compose.yml
  - pyproject.toml
  - servers/echo/Dockerfile
  - servers/echo/pyproject.toml
  - servers/echo/server.py
  - servers/ping/Dockerfile
  - servers/ping/pyproject.toml
  - servers/ping/server.py
  - tests/reference_servers/conftest.py
  - tests/reference_servers/test_reference_servers.py
findings:
  critical: 0
  warning: 4
  info: 5
  total: 9
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-04-16T00:00:00Z
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

This phase delivers two FastMCP reference servers (echo, ping), Docker Compose integration,
and integration tests. The server implementations themselves are clean, minimal, and
well-documented. The test fixtures demonstrate correct patterns for ephemeral-port container
management with proper cleanup via `finally` blocks.

However, there are four warnings that require attention before this phase can be considered
complete:

1. The Docker healthchecks for echo and ping will always report containers as unhealthy
   when they are in fact healthy — this is a functional bug that will cause issues in
   `docker compose` workflows and CI.
2. Both Dockerfiles run as root, which contradicts the project's docker-patterns skill
   and is a container security concern.
3. Unguarded index access on `result.content[0]` in two tests will produce unhelpful
   `IndexError` crashes instead of clear assertion failures if the MCP server returns
   empty content.
4. The lifecycle test (`test_container_manager_lifecycle_echo`) leaks a Docker container
   if the test fails after `start()` but before `stop()`.

The info items are lower-priority but should be addressed before production hardening.

## Warnings

### WR-01: Docker Healthcheck Fails for Healthy Containers

**File:** `docker-compose.yml:26-29` (echo), `docker-compose.yml:39-42` (ping)

**Issue:** The healthcheck command is:
```
python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/mcp')"
```
The MCP Streamable HTTP transport returns HTTP `405 Method Not Allowed` for `GET /mcp`
requests (it expects `POST`). `urllib.request.urlopen` raises `urllib.error.HTTPError`
(a subclass of `URLError`) for all non-2xx responses. Because the exception is not caught,
Python exits with code `1`, which Docker interprets as an unhealthy container.

Result: both `sb-echo` and `sb-ping` will perpetually report `unhealthy` even when
fully operational, breaking any service that depends on `condition: service_healthy`.

**Fix:** Catch `HTTPError` in the one-liner, or use a tool that treats 4xx as success.
The `_wait_for_healthy` function in `conftest.py` already demonstrates the correct logic:

```yaml
# Option A: Handle HTTPError inline (matches conftest.py logic)
healthcheck:
  test:
    - "CMD-SHELL"
    - >
      python -c "
      import urllib.request, urllib.error;
      try:
          urllib.request.urlopen('http://localhost:8000/mcp', timeout=2)
      except urllib.error.HTTPError:
          pass
      "

# Option B: Use curl (available in python:3.12-slim via apt, or add to Dockerfile)
healthcheck:
  test: ["CMD-SHELL", "curl -sf -o /dev/null -w '%{http_code}' http://localhost:8000/mcp | grep -qE '(200|405|406)'"]
```

---

### WR-02: Dockerfiles Run as Root

**File:** `servers/echo/Dockerfile:1-25`, `servers/ping/Dockerfile:1-25`

**Issue:** Neither Dockerfile creates a non-root user or sets a `USER` instruction.
The MCP server process runs as `root` inside the container. Per the project's
`docker-patterns` skill, containers should always run as non-root. Running as root
means that if the container is compromised, the attacker has root access to the
container filesystem and, depending on Docker daemon configuration, potentially the host.

**Fix:** Add a non-root user after the dependency install step:

```dockerfile
# After the second uv sync and before CMD:
RUN addgroup --system --gid 1001 appgroup \
    && adduser --system --uid 1001 --ingroup appgroup appuser

USER appuser

CMD ["uv", "run", "python", "server.py"]
```

Note: if the `uv` cache or venv path requires write access, adjust `--mount` permissions
or chown the `/app` directory to `appuser` before switching.

---

### WR-03: Unguarded Index Access on MCP Tool Result Content

**File:** `tests/reference_servers/test_reference_servers.py:46`, `test_reference_servers.py:62`

**Issue:** Both echo tests access `result.content[0].text` without checking that
`result.content` is non-empty:

```python
# Line 46
assert result.content[0].text == "hello world"

# Line 62
assert result.content[0].text == test_message
```

If the MCP tool call returns an empty `content` list (e.g., due to an SDK version
mismatch, serialization issue, or server-side error), both tests raise `IndexError`
instead of a meaningful assertion failure. This makes debugging significantly harder.

**Fix:** Assert the length before indexing, or use a more descriptive check:

```python
assert result.content, "Expected non-empty content from echo tool"
assert result.content[0].text == "hello world"
```

Or use `pytest`'s assertion rewriting to get a clear diff on failure:

```python
assert len(result.content) >= 1, f"Expected content, got: {result.content!r}"
assert result.content[0].text == "hello world"
```

---

### WR-04: Docker Container Leak on Test Failure in Lifecycle Test

**File:** `tests/reference_servers/test_reference_servers.py:88-142`

**Issue:** `test_container_manager_lifecycle_echo` starts a real Docker container via
`manager.start()` (line 136) and stops it via `manager.stop()` (line 141). There is no
`try/finally` block to guarantee cleanup. If:
- the assertion at line 137 fails (container started but status is wrong), or
- `manager.stop()` raises an exception,

the Docker container `sb-echo-lifecycle-test` will remain running and must be cleaned up
manually. On repeated test runs this causes conflicts (`container already exists` errors).

**Fix:** Wrap the start/stop sequence in a `try/finally`:

```python
# Start the container
updated = await manager.start(mock_session, mock_server, mock_repo)
try:
    assert updated.status == ServerStatus.running
    assert updated.container_id is not None

    # Stop the container
    await manager.stop(mock_session, updated, mock_repo)
    assert mock_server.status == ServerStatus.stopped
finally:
    # Ensure cleanup even if assertions fail
    if mock_server.container_id is not None:
        import docker as _docker
        try:
            _client = _docker.from_env()
            _container = _client.containers.get(f"sb-{mock_server.name}")
            _container.stop(timeout=5)
            _container.remove(force=True)
            _client.close()
        except Exception:
            pass  # Best-effort cleanup
```

Alternatively, refactor into a session-scoped fixture similar to `echo_server_url`.

---

## Info

### IN-01: Floating `uv:latest` Tag in Dockerfiles

**File:** `servers/echo/Dockerfile:6`, `servers/ping/Dockerfile:6`

**Issue:** Both Dockerfiles use `COPY --from=ghcr.io/astral-sh/uv:latest`, which
pins to the latest release at build time but is not reproducible across builds.
The `docker-patterns` skill notes that `:latest` tags should be avoided in favor of
pinned versions.

**Fix:** Pin to a specific uv version:
```dockerfile
COPY --from=ghcr.io/astral-sh/uv:0.6.0 /uv /uvx /bin/
```
Check the latest stable release at https://github.com/astral-sh/uv/releases.

---

### IN-02: Duplicated Container Fixture Code in conftest.py

**File:** `tests/reference_servers/conftest.py:97-169`

**Issue:** `echo_server_url` (lines 97-132) and `ping_server_url` (lines 135-169)
are nearly identical — the only differences are the image name, container name, and
yield value. This is ~70 lines of duplicated fixture logic that will drift if one
is updated without the other.

**Fix:** Extract a generic `_server_fixture` helper and compose the specific fixtures
from it:

```python
from contextlib import contextmanager

def _run_server_container(
    image: str,
    name: str,
) -> Generator[str, None, None]:
    """Start a server container and yield its MCP endpoint URL."""
    client = docker.from_env()
    container = None
    try:
        try:
            old = client.containers.get(name)
            old.remove(force=True)
        except docker.errors.NotFound:
            pass

        container = client.containers.run(
            image=image,
            name=name,
            detach=True,
            ports={_MCP_CONTAINER_PORT: None},
        )
        host_port = _get_host_port(container)
        url = f"http://localhost:{host_port}/mcp"
        _wait_for_healthy(url)
        yield url
    finally:
        if container is not None:
            try:
                container.stop(timeout=5)
                container.remove(force=True)
            except docker.errors.NotFound:
                pass
        client.close()


@pytest.fixture(scope="session")
def echo_server_url() -> Generator[str, None, None]:
    yield from _run_server_container(ECHO_IMAGE, ECHO_TEST_NAME)


@pytest.fixture(scope="session")
def ping_server_url() -> Generator[str, None, None]:
    yield from _run_server_container(PING_IMAGE, PING_TEST_NAME)
```

---

### IN-03: Missing `--strict-markers` in pytest Configuration

**File:** `pyproject.toml:33-39`

**Issue:** The `[tool.pytest.ini_options]` section registers `reference_servers` and
`integration` markers but does not set `addopts = ["--strict-markers"]`. Without this
flag, a misspelled marker (e.g., `@pytest.mark.reference_server` instead of
`@pytest.mark.reference_servers`) silently creates a new marker instead of raising an
error. This can cause tests to not be excluded when running with `-m reference_servers`.

**Fix:**
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = ["--strict-markers"]
markers = [
    "integration: marks tests requiring a running PostgreSQL instance",
    "reference_servers: marks tests requiring Docker images switchboard-echo and switchboard-ping to be built",
]
```

---

### IN-04: Missing Return Type Annotation on `_wait_for_healthy`

**File:** `tests/reference_servers/conftest.py:66`

**Issue:** `_wait_for_healthy` is missing a `-> None` return type annotation on the
function signature, which is inconsistent with the project's type annotation requirements
(all function signatures must have type hints per CLAUDE.md).

**Fix:**
```python
def _wait_for_healthy(url: str, *, retries: int = _HEALTH_CHECK_RETRIES) -> None:
```

---

### IN-05: No `.dockerignore` Files for Reference Servers

**File:** `servers/echo/`, `servers/ping/`

**Issue:** Neither server directory has a `.dockerignore` file. The Docker build context
for each server is its full directory (`servers/echo` and `servers/ping`). Without
`.dockerignore`, files such as `__pycache__`, `.pytest_cache`, and any local dev
artifacts are sent to the Docker daemon, slightly increasing build context size and
potentially including stale bytecode in the image.

**Fix:** Add a `.dockerignore` to each server directory:
```
__pycache__
*.pyc
*.pyo
.pytest_cache
.ruff_cache
.mypy_cache
```

---

_Reviewed: 2026-04-16T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
