# Phase 6: Health Monitor - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-18
**Phase:** 06-health-monitor
**Areas discussed:** Probe mechanism, Health status storage, Background task placement

---

## Probe mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| HTTP probe only | POST /mcp inside internal network; no Docker SDK | |
| Docker inspect only | container.status check via SDK; degraded hard to express | |
| Both: inspect first, then HTTP if running | Most accurate three-state model | ✓ |

**User's choice:** Both probes — inspect first, HTTP if container is running

**HTTP endpoint sub-question:**

| Option | Description | Selected |
|--------|-------------|----------|
| POST /mcp | MCP Streamable HTTP endpoint; any response = alive | ✓ |
| GET /mcp | SSE stream endpoint | |
| Simple GET to lightweight path | Fastest, no MCP protocol knowledge | |

**User's choice:** POST /mcp

**Failure threshold sub-question:**

| Option | Description | Selected |
|--------|-------------|----------|
| 1 failure = unreachable immediately | Fast but noisy | |
| 2 consecutive failures | Aligns with "two polling intervals" success criterion | ✓ |
| 3 consecutive failures | More tolerant, slower detection | |

**User's choice:** 2 consecutive failures

---

## Health status storage

| Option | Description | Selected |
|--------|-------------|----------|
| New column on Server ORM + Alembic migration | Persistent, from_attributes picks it up automatically | ✓ |
| In-memory dict | No migration, lost on restart | |
| Separate HealthRecord table | History, but overkill for v1 | |

**User's choice:** New column on Server ORM

**Initial value sub-question:**

| Option | Description | Selected |
|--------|-------------|----------|
| null / None | Honest: not polled yet | |
| unknown enum value | Explicit not-yet-polled state | |
| Only poll running servers; no field for stopped | health_status only when running | |

**User's choice:** Claude's discretion → null (None) before first poll

---

## Background task placement

| Option | Description | Selected |
|--------|-------------|----------|
| Admin API lifespan | Most natural; health is admin concern | |
| New standalone health module (switchboard/health/) started by both apps | Module isolated; admin app imports it | ✓ |
| Gateway lifespan | Mixes concerns; gateway is customer-facing | |

**User's choice:** Standalone module (switchboard/health/), imported and started by admin API lifespan only

**Which process runs it sub-question:**

| Option | Description | Selected |
|--------|-------------|----------|
| Admin API process only | One loop, one writer | ✓ |
| Dedicated third process/container | Most isolated, new container | |
| Both processes (duplicate polling) | Redundant, idempotent writes | |

**User's choice:** Admin API process only

**Polling interval sub-question:**

| Option | Description | Selected |
|--------|-------------|----------|
| 10 seconds | Faster detection, more API calls | |
| 30 seconds | Standard; configurable via env var | ✓ |
| 60 seconds | Low overhead; 2-min worst case | |

**User's choice:** 30 seconds (HEALTH_POLL_INTERVAL env var)

---

## Claude's Discretion

- httpx client lifecycle in health monitor
- Error handling and logging per failed poll
- In-memory failure counter structure
- Whether to reset health_status when server is explicitly stopped

## Deferred Ideas

None.
