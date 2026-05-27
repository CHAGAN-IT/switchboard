---
phase: 03-container-manager
reviewed: 2026-04-15T23:10:00Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - switchboard/container/manager.py
  - switchboard/container/exceptions.py
  - switchboard/container/__init__.py
  - tests/container/conftest.py
  - tests/container/test_manager.py
  - docker-compose.yml
  - switchboard/admin/router.py
  - tests/admin/test_lifecycle_endpoints.py
  - tests/admin/conftest.py
findings:
  critical: 0
  warning: 4
  info: 3
  total: 7
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-04-15T23:10:00Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Phase 3 delivers container lifecycle management (`ContainerManager`) with three async operations (start/stop/restart), a custom exception hierarchy, FastAPI lifecycle endpoints wired to those operations, and a comprehensive unit and integration test suite.

The implementation is well-structured: Docker SDK calls are correctly offloaded via `asyncio.to_thread()`, containers are isolated on the internal network without host-port publishing (satisfying D-01/T-3-02), and the exception hierarchy cleanly separates container failure modes. Code quality is high overall — type hints are present throughout, docstrings follow Google style, and the test coverage is strong.

Four warnings require attention before merging:

1. **Error status not persisted on start failure** — `ContainerManager.start()` calls `repo.update_status(..., ServerStatus.error)` then raises `ContainerStartError`, but the router catches the exception and re-raises an `HTTPException` *before* reaching `session.commit()`. Because the repository uses `flush()` not `commit()`, the `error` status is never written to the database. A failed start leaves the server stuck in its pre-start state with no observable error status.

2. **Container start race window** — Between `update_status(running)` (line 92) and `update_container_id(container_id)` (line 93) in `ContainerManager.start()`, the DB briefly shows `status=running` with `container_id=None`. A concurrent read (e.g. gateway polling) during this window would see an inconsistent state.

3. **`CONTAINER_PORT` constant is unused** — Declared at module level in `manager.py` and imported by `test_manager.py`, but never passed to `client.containers.run()`. If port-mapping were intended for internal routing, this silently omits it; if not intended, the constant is dead code.

4. **`docker-compose.yml` has no gateway or app service** — The `switchboard-internal` network is declared and used by `ContainerManager` at runtime, but the compose file only defines `db`. This means local development has no compose-managed gateway service to route traffic to the containers that `ContainerManager` starts, and the compose definition doesn't model the full local topology documented in the architecture.

Three informational items are also noted.

---

## Warnings

### WR-01: Error status from ContainerManager.start() is never committed

**File:** `switchboard/container/manager.py:88-90` and `switchboard/admin/router.py:193-197`

**Issue:** When a Docker error occurs in `_start_blocking`, the exception handler calls `repo.update_status(session, server.id, ServerStatus.error)` and then raises `ContainerStartError`. The repository's `update_status` method calls `session.flush()` — it does not commit. Back in `start_server` (router.py line 193-197), the `ContainerStartError` is caught and re-raised as `HTTPException` without ever reaching `session.commit()` on line 198. FastAPI will close the session after the exception, rolling back the unflushed state. The server's status in the database remains whatever it was before the start attempt (typically `stopped`), not `error`. An operator has no persistent signal that the start failed.

**Fix:** Add `await session.commit()` in the manager's error handler before raising, or move the error-state persistence to the router's exception handler. The cleanest router-side fix:

```python
# switchboard/admin/router.py  -- start_server handler
try:
    server = await cm.start(session, server, repo)
except ContainerStartError as exc:
    # Persist the error status that manager.start() flushed.
    await session.commit()
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=str(exc),
    ) from None
await session.commit()
return ServerRead.model_validate(server)
```

Alternatively, remove the `update_status(error)` call from `manager.start()` entirely and let the router set it:

```python
# switchboard/admin/router.py  -- start_server handler
try:
    server = await cm.start(session, server, repo)
except ContainerStartError as exc:
    await repo.update_status(session, server.id, ServerStatus.error)
    await session.commit()
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=str(exc),
    ) from None
```

The same analysis applies to `ContainerStopError` in `stop_server`, though that path doesn't set an error status today and is therefore not broken.

---

### WR-02: Inconsistent DB state window during start() — status set running before container_id is written

**File:** `switchboard/container/manager.py:92-93`

**Issue:** `start()` calls `repo.update_status(..., ServerStatus.running)` on line 92 before calling `repo.update_container_id(..., container_id)` on line 93. Each call flushes independently. Between the two flushes, the database row has `status=running` but `container_id=NULL`. Any concurrent read (e.g. a gateway health poll or a list-servers response mid-request) in that window returns an inconsistent record: running but no container to route to. Both fields should be set atomically.

**Fix:** Either batch both changes into a single flush, or update both fields on the ORM object before flushing once:

```python
# switchboard/container/manager.py -- start()
# After container_id is obtained, set both fields before any flush:
updated = await repo.update_status_and_container_id(
    session, server.id, ServerStatus.running, container_id
)
return updated if updated is not None else server
```

If adding a combined repository method is undesirable, directly mutate the ORM object and flush once:

```python
# Retrieve server, set both fields, flush once
server_obj = await session.get(type(server), server.id)
if server_obj is not None:
    server_obj.status = ServerStatus.running
    server_obj.container_id = container_id
    await session.flush()
    await session.refresh(server_obj)
    return server_obj
return server
```

---

### WR-03: CONTAINER_PORT constant is declared but never used

**File:** `switchboard/container/manager.py:36`

**Issue:** `CONTAINER_PORT: int = 8000` is defined and exported, but it is never passed to `client.containers.run()`. The `containers.run()` call has no `ports` argument (intentional per D-01/T-3-02 — no host-port publishing), but `CONTAINER_PORT` is also not used for internal network addressing or health checks. Its presence implies either (a) it was intended for internal routing and was accidentally omitted, or (b) it is dead code. `test_manager.py` imports it for `TestConstants.test_container_port()`, but testing a constant's value in isolation has no value unless the constant is actually used in logic.

**Fix:** If `CONTAINER_PORT` represents the port MCP servers listen on inside their containers (for gateway routing), document its purpose clearly and use it where routing addresses are constructed. If it has no current use and no planned use in this phase, remove it and the corresponding test to avoid creating misleading dead code:

```python
# Remove from manager.py:
# CONTAINER_PORT: int = 8000  <-- delete this

# Remove from test_manager.py:
# def test_container_port(self) -> None:
#     assert CONTAINER_PORT == 8000  <-- delete this
```

---

### WR-04: docker-compose.yml defines the internal network but no gateway/app service

**File:** `docker-compose.yml:19-21`

**Issue:** The `switchboard-internal` bridge network is declared in `docker-compose.yml`, mirroring what `ContainerManager._ensure_network()` creates at runtime. However, no gateway service or admin-api service is defined in the compose file — only `db`. This means there is no compose-managed service that joins `switchboard-internal`, so the network exists in compose for documentation purposes only. Locally, when `ContainerManager` starts MCP server containers on this network, nothing else in the compose topology can route to them. This is not a runtime bug (the gateway would be started separately), but it means the `docker-compose.yml` does not represent a runnable local development stack.

**Fix:** Add gateway and admin-api service stubs to `docker-compose.yml` so the compose file reflects the full local topology and developers can `docker compose up` to get a working environment. At minimum, ensure both services declare `networks: - switchboard-internal` so they can reach containers that `ContainerManager` starts.

---

## Info

### IN-01: stop() does not set error status on ContainerStopError

**File:** `switchboard/container/manager.py:119-128`

**Issue:** When `_stop_blocking` raises `docker.errors.APIError`, `stop()` raises `ContainerStopError` without updating the server's status to `error`. The server's status (e.g. `running`) remains unchanged in the database even though the stop operation failed. This is a design choice that may be intentional (the container may still be running), but it is inconsistent with `start()`, which does set `error` status on failure, and it makes operator visibility harder since the status in the registry doesn't indicate that a stop attempt failed.

**Fix:** Either document explicitly in the docstring that stop failures leave the status unchanged, or add an `error` status update before re-raising:

```python
except docker.errors.APIError as exc:
    logger.error("Container stop failed for '%s': %s", server.name, exc)
    await repo.update_status(session, server.id, ServerStatus.error)
    raise ContainerStopError(server.name, str(exc)) from exc
```

---

### IN-02: docker-compose.yml exposes database port to host with hardcoded credentials

**File:** `docker-compose.yml:4-9`

**Issue:** The `db` service publishes `5432:5432` to the host and uses `POSTGRES_PASSWORD: postgres` inline. While this is a common local-development pattern, the hardcoded password in a committed file and the open host port are worth flagging. If a developer's `.env` file is misconfigured to point at `localhost:5432`, local tests could accidentally hit this container with the hardcoded credentials. There is also a risk that this pattern is copy-pasted to a staging compose file.

**Fix:** Move credentials to an `.env` file (which is already in `.gitignore` per project conventions) and reference them via `${POSTGRES_PASSWORD:-postgres}`:

```yaml
environment:
  POSTGRES_USER: ${POSTGRES_USER:-postgres}
  POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
  POSTGRES_DB: ${POSTGRES_DB:-switchboard}
```

---

### IN-03: Test for to_thread in restart() uses fragile call-count tracking

**File:** `tests/container/test_manager.py:479-503`

**Issue:** `test_restart_uses_to_thread` tracks `asyncio.to_thread` calls via a closure counter (`call_count`) and returns different values on the first vs. second call. This is a working approach, but it is fragile: if the internal ordering of `stop()` / `start()` changes (e.g., restart is refactored to call them in a single `to_thread` invocation), the test will fail with a misleading `AssertionError` about call count rather than a meaningful behavioral assertion. The test also implicitly assumes `to_thread` will be called exactly twice, but does not verify *which* functions are passed to it.

**Fix:** Use `mock_to_thread.call_args_list` to assert on the actual functions passed, rather than positional call order:

```python
# Verify _stop_blocking was called first, _start_blocking second
calls = mock_to_thread.call_args_list
assert len(calls) == 2
assert calls[0].args[0].__name__ == "_stop_blocking"
assert calls[1].args[0].__name__ == "_start_blocking"
```

---

_Reviewed: 2026-04-15T23:10:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
