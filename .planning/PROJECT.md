# Switchboard

## What This Is

Switchboard is a Python application that acts as a central MCP (Model Context Protocol) gateway. It manages the lifecycle of multiple MCP servers and aggregates their tools into a single endpoint, so AI clients and developers connect once to discover and invoke tools from any managed server. It serves clients via both stdio (local/Claude Desktop) and Streamable HTTP (remote clients), with OAuth 2.0 authentication, and exposes an admin API for dynamically registering and removing MCP servers at runtime.

## Core Value

A single connection to Switchboard gives an AI client access to all tools from all managed MCP servers — no per-server configuration, no multiple connections.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] AI client can connect to Switchboard via stdio or Streamable HTTP transport
- [ ] Clients authenticate using OAuth 2.0 before accessing tools
- [ ] Client sees aggregated tool list from all managed MCP servers
- [ ] Client can invoke any tool from any managed MCP server
- [ ] Developer can register an MCP server via admin API
- [ ] Developer can deregister an MCP server via admin API
- [ ] Switchboard manages MCP server process lifecycle (start/stop)
- [ ] Application runs in Docker container
- [ ] Production deployment targets cloud; local dev runs via Docker Compose

### Out of Scope

- Config-file-based server registration — admin API is the registration mechanism
- Web UI for management — API-only for v1
- Multi-tenant isolation — single operator model for v1

## Context

- Python 3.12+, `uv` for package management, `ruff` for linting/formatting
- Top-level package directory is `switchboard/` (not `src/`)
- MCP Python SDK (`mcp`) is the canonical library for MCP protocol implementation
- Transport: Streamable HTTP (current MCP spec) for remote clients; stdio for local clients
- OAuth 2.0 is the MCP-recommended auth mechanism for production deployments
- Containerized via Docker; local dev via Docker Compose
- Cloud deployment target TBD (architecture should be cloud-agnostic)

## Constraints

- **Language**: Python 3.12+ — project requirement
- **Package layout**: `switchboard/` top-level, not `src/` — project requirement
- **Containerization**: Docker required — both dev and prod must run containerized
- **MCP compliance**: Must implement MCP protocol correctly — clients expect spec compliance
- **Auth**: OAuth 2.0 — what the MCP spec recommends for production

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Admin API over config file | Dynamic server registration without restarts | — Pending |
| OAuth 2.0 over API keys | MCP spec recommendation for production | — Pending |
| Both stdio + Streamable HTTP | Support local (Claude Desktop) and remote AI clients | — Pending |
| Switchboard manages server processes | Central lifecycle management, not just proxying | — Pending |

---

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-14 after initialization*
