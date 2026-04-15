# Phase 3: Container Manager - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-15
**Phase:** 03-container-manager
**Areas discussed:** Network isolation, Error handling & edge cases, API response shape, ContainerManager abstraction

---

## Network isolation

| Option | Description | Selected |
|--------|-------------|----------|
| Pre-declared in docker-compose.yml | Named network defined in Compose, SDK attaches containers to it | ✓ |
| Container Manager creates it dynamically | ensure_network() creates on first use | |
| Default bridge | No custom network, weaker isolation | |

**User's choice:** Pre-declared in docker-compose.yml (`switchboard-internal`)
**Notes:** —

---

| Option | Description | Selected |
|--------|-------------|----------|
| Container name = server name | `echo` → routes via `http://echo:8000` | |
| Prefixed container name (`sb-echo`) | `sb-` prefix avoids collisions | ✓ |
| Claude's Discretion | — | |

**User's choice:** `sb-{name}` prefix (e.g., `sb-echo`)
**Notes:** —

---

| Option | Description | Selected |
|--------|-------------|----------|
| Port 8000 (FastAPI/uvicorn default) | Consistent across all MCP containers | ✓ |
| Claude's Discretion | Pick a sensible port | |

**User's choice:** Port 8000
**Notes:** —

---

## Error handling & edge cases

| Option | Description | Selected |
|--------|-------------|----------|
| Set status to 'error', return 500 with reason | update_status() + HTTP 500 | ✓ |
| Set status to 'error', return 409 Conflict | Less standard for infra failures | |
| Leave status unchanged, return 500 | Less informative for operators | |

**User's choice:** Set status to `error`, return HTTP 500 with reason
**Notes:** —

---

| Option | Description | Selected |
|--------|-------------|----------|
| 409 Conflict | `{"detail": "Server is not running"}` | ✓ |
| 200 OK (idempotent) | Operator intent satisfied regardless | |
| Claude's Discretion | — | |

**User's choice:** 409 Conflict for stopping an already-stopped server
**Notes:** —

---

| Option | Description | Selected |
|--------|-------------|----------|
| 409 Conflict | `{"detail": "Server is already running"}` | ✓ |
| 200 OK (idempotent) | Return current state | |

**User's choice:** 409 Conflict for starting an already-running server
**Notes:** —

---

## API response shape

| Option | Description | Selected |
|--------|-------------|----------|
| Full ServerRead schema | Consistent with Phase 2; caller gets full current state | ✓ |
| Minimal {status, container_id} | Lighter payload, inconsistent | |
| 204 No Content | Simplest, breaks Phase 2 pattern | |

**User's choice:** Full `ServerRead` schema on success
**Notes:** —

---

## ContainerManager abstraction

| Option | Description | Selected |
|--------|-------------|----------|
| ContainerManager class | Mirrors ServerRepository; injectable via Depends() | ✓ |
| Module-level functions | Simpler, harder to mock | |
| Claude's Discretion | — | |

**User's choice:** `ContainerManager` class in `switchboard/container/manager.py`
**Notes:** —

---

| Option | Description | Selected |
|--------|-------------|----------|
| Inside each asyncio.to_thread() call | Thread-safe, no shared state | ✓ |
| Once at ContainerManager instantiation | Single client, connection pooling concern | |
| Module-level singleton | Simplest, tight coupling | |

**User's choice:** `docker.from_env()` called inside each `asyncio.to_thread()` call
**Notes:** —

---

## Claude's Discretion

- Exception type hierarchy for ContainerManager errors
- Whether restart() uses Docker's container.restart() or stop() + start()
- Internal port constant name and location
- get_container_manager() factory function structure
- Whether network name is a Settings field or a module constant

## Deferred Ideas

- Per-server port configuration
- Container environment variable injection (CONT-05, v2)
- Restart policy (automatic crash recovery)
- Rolling restart without downtime (explicitly out of scope)
