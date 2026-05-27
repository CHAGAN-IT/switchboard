---
phase: 08-ecs-production-fixes
reviewed: 2026-04-21T00:00:00Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - tests/admin/test_health_route.py
  - switchboard/admin/app.py
  - switchboard/health/monitor.py
  - infra/modules/ecs/services.tf
  - Dockerfile
  - docker-compose.yml
  - tests/health/test_monitor.py
findings:
  critical: 0
  warning: 2
  info: 4
  total: 6
status: issues_found
---

# Phase 08: Code Review Report

**Reviewed:** 2026-04-21T00:00:00Z
**Depth:** standard
**Files Reviewed:** 7
**Status:** issues_found

## Summary

This phase introduces ECS production fixes: an unauthenticated `/health` endpoint on the admin API (PLAT-02), a `HealthMonitor` background task polling running servers, ECS task definitions with health checks, a multi-target Dockerfile, and a Docker Compose local stack.

The changes are well-structured and the core logic is sound. The health endpoint, state machine, and shutdown sequence are all correctly implemented. Two warnings require attention before production deployment: a missing Docker SDK error handler that leaves health data stale in ECS (where no Docker socket exists), and missing ECS health checks on the echo/ping task definitions that could cause premature Cloud Map registration.

## Warnings

### WR-01: `_inspect_blocking` does not handle `DockerException` — stale health data in ECS

**File:** `switchboard/health/monitor.py:111-130`
**Issue:** `_inspect_blocking` only catches `docker.errors.NotFound`. In an ECS Fargate environment there is no Docker socket, so `docker.from_env()` raises `docker.errors.DockerException` (or the underlying `requests.exceptions.ConnectionError`). This exception propagates through `_probe_server` to the broad `except Exception` handler at line 81, which logs it but skips the `_update_health` call for that server. The server's `health_status` in the database is never updated — stale data persists indefinitely for every server in production.

The `cloud_map_domain` setting already distinguishes ECS from local Docker Compose. The `_inspect_blocking` method should also be aware of this distinction, or at minimum handle `DockerException` explicitly so the monitor can fall back to HTTP-only probing in ECS.

**Fix:** Add a `DockerException` handler in `_inspect_blocking` that returns a sentinel value (e.g., `None` with logging), and update `_probe_server` to skip Docker inspection entirely when `cloud_map_domain` is non-empty (i.e., in ECS where Cloud Map DNS-based discovery is used instead of Docker socket):

```python
def _inspect_blocking(self, container_name: str) -> str | None:
    """Blocking Docker inspect -- runs in thread (D-05).

    Returns None if the container is not found OR if the Docker
    daemon is unreachable (e.g., in ECS where no socket exists).
    """
    try:
        client = docker.from_env()
    except docker.errors.DockerException:
        logger.debug("docker_unavailable_skipping_inspect", container=container_name)
        return None
    try:
        container = client.containers.get(container_name)
        return container.status
    except docker.errors.NotFound:
        return None
    finally:
        client.close()
```

And in `_probe_server`, skip Docker inspection in ECS:

```python
async def _probe_server(self, server: Server) -> HealthStatus:
    """Run Docker inspect + HTTP probe and return computed status."""
    # In ECS (cloud_map_domain set), Docker socket unavailable -- HTTP only.
    if self._cloud_map_domain:
        http_ok = await self._http_probe(server.name)
        return self._compute_status(server.name, docker_running=True, http_ok=http_ok)

    container_name = f"{CONTAINER_NAME_PREFIX}{server.name}"
    docker_status = await self._inspect_container(container_name)
    docker_running = docker_status == "running"

    if not docker_running:
        return self._compute_status(server.name, docker_running=False, http_ok=False)

    http_ok = await self._http_probe(server.name)
    return self._compute_status(server.name, docker_running=True, http_ok=http_ok)
```

---

### WR-02: Echo and ping ECS task definitions missing `healthCheck` block

**File:** `infra/modules/ecs/services.tf:184-219` and `250-285`
**Issue:** The echo and ping task definitions have no `healthCheck` block. Without a container health check, ECS marks the container as `HEALTHY` immediately on first start (it uses the `UNKNOWN` → `HEALTHY` transition with no verification). Both services are registered with Cloud Map (`service_registries` block at lines 233-236 and 299-302), and Cloud Map receives `HEALTHY` registrations even if the MCP server is still initializing. This can cause the gateway to receive Cloud Map DNS responses for containers that are not yet ready to serve traffic.

**Fix:** Add a `healthCheck` block to both echo and ping task definitions, consistent with the pattern already used for gateway and admin-api. A TCP socket check (as used in docker-compose.yml) is appropriate since these containers do not have an HTTP health endpoint:

```hcl
# In aws_ecs_task_definition.echo and aws_ecs_task_definition.ping
# container_definitions block:

healthCheck = {
  command     = ["CMD-SHELL", "python -c \"import socket; s=socket.create_connection(('localhost',8000),timeout=3); s.close()\""]
  interval    = 10
  timeout     = 5
  retries     = 3
  startPeriod = 15
}
```

---

## Info

### IN-01: Unpinned `uv` version in Dockerfile base layer

**File:** `Dockerfile:12`
**Issue:** `COPY --from=ghcr.io/astral-sh/uv:latest` uses the `:latest` tag. A future release of `uv` could introduce breaking changes to CLI flags or behavior (e.g., changes to `uv sync --locked`) that silently break image builds. Pinning to a specific version ensures reproducibility.

**Fix:** Pin to a specific `uv` release:

```dockerfile
COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /uvx /bin/
```

---

### IN-02: Unguarded JWT secret environment variable interpolation in docker-compose.yml

**File:** `docker-compose.yml:55-56`
**Issue:** `CUSTOMER_JWT_SECRET=${CUSTOMER_JWT_SECRET}` and `OPERATOR_JWT_SECRET=${OPERATOR_JWT_SECRET}` use Docker Compose variable interpolation without a default or required marker. If these variables are absent from the host environment, Docker Compose silently injects empty strings, causing the gateway container to start with an empty JWT secret and accept or reject all tokens unpredictably.

**Fix:** Use required variable syntax (Docker Compose 2.x+) to fail fast if secrets are not set, or add a `.env.example` file:

```yaml
environment:
  - CUSTOMER_JWT_SECRET=${CUSTOMER_JWT_SECRET:?CUSTOMER_JWT_SECRET is required}
  - OPERATOR_JWT_SECRET=${OPERATOR_JWT_SECRET:?OPERATOR_JWT_SECRET is required}
```

---

### IN-03: Broad `except Exception` swallows per-server health probe errors

**File:** `switchboard/health/monitor.py:81-82`
**Issue:** The polling loop catches all exceptions per server and logs them without re-raising. While this isolation is intentional (one failing probe must not stop others), catching `Exception` broadly is flagged by the project's global CLAUDE.md convention: "Never catch `Exception` at a boundary without logging and re-raising or returning a typed error." The logging is present, but the swallowing is complete. This is a convention deviation rather than a functional bug.

**Fix:** If the design intent is to always isolate per-server failures, document this explicitly at the call site with a `# WORKAROUND:` comment, or narrow the catch to expected exception types:

```python
except (docker.errors.DockerException, httpx.HTTPError, OSError) as exc:
    logger.exception("health_probe_error", server_name=server.name)
    # Intentionally swallowed: one server failure must not stop others.
    _ = exc
```

---

### IN-04: `mock_probe` assignment suppressed with `# type: ignore[assignment]` without explanation

**File:** `tests/health/test_monitor.py:366`
**Issue:** `monitor._probe_server = mock_probe  # type: ignore[assignment]` uses `# type: ignore` without explaining why type checking fails here. Per project convention, every `# type: ignore` must include a comment explaining why.

**Fix:**

```python
# _probe_server is a bound method; assigning a plain async function requires ignore.
monitor._probe_server = mock_probe  # type: ignore[method-assign]
```

---

_Reviewed: 2026-04-21T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
