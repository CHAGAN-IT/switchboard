---
status: partial
phase: 02-admin-api
source: [02-01-SUMMARY.md, 02-02-SUMMARY.md]
started: 2026-04-15T05:00:00Z
updated: 2026-04-15T05:10:00Z
---

## Current Test

## Current Test

[testing complete — 2 tests blocked pending PostgreSQL/Docker Compose setup]

## Tests

### 1. Startup rejected without OPERATOR_JWT_SECRET
expected: Run `uv run python -c "from switchboard.admin.app import app"` without OPERATOR_JWT_SECRET in env. Expect a Pydantic ValidationError: "OPERATOR_JWT_SECRET environment variable is required and must not be empty". App does not start silently.
result: pass

### 2. App boots with valid secret
expected: Run `OPERATOR_JWT_SECRET=switchboard-dev-secret-at-least-32bytes uv run uvicorn switchboard.admin.app:app --port 8000`. Server starts without errors, logs show "Application startup complete." and listens on port 8000. Note: DB connection errors are expected if PostgreSQL is not running — that's a separate concern from the secret validator.
result: pass

### 3. Unauthenticated request returns 401
expected: `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/servers` returns 403 (FastAPI HTTPBearer returns 403 for missing header) OR 401. Response headers include `WWW-Authenticate: Bearer`.
result: pass

### 4. OpenAPI docs accessible
expected: `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/docs` returns 200. Opening http://localhost:8000/docs in a browser shows Swagger UI with exactly three endpoints: POST /api/v1/servers, GET /api/v1/servers, GET /api/v1/servers/{name}.
result: pass

### 5. Server registration returns 201
expected: |
  With a valid JWT (requires running app + PostgreSQL):
  `curl -X POST http://localhost:8000/api/v1/servers \
    -H "Authorization: Bearer <valid_jwt>" \
    -H "Content-Type: application/json" \
    -d '{"name":"my-mcp-server","container_image":"myimage:latest"}'`
  Returns HTTP 201 with JSON body containing id, name, container_image, status: "stopped", created_at, updated_at.
result: blocked
blocked_by: server
reason: "ConnectionRefusedError: Connect call failed ('127.0.0.1', 5432) — PostgreSQL not running"

### 6. List and get-by-name endpoints work
expected: |
  GET /api/v1/servers with valid JWT returns HTTP 200 with JSON array (empty [] or containing registered servers).
  GET /api/v1/servers/my-mcp-server with valid JWT returns HTTP 200 with the full server record.
  GET /api/v1/servers/nonexistent with valid JWT returns HTTP 404 with {"detail":"Server 'nonexistent' not found"}.
result: blocked
blocked_by: server
reason: "No PostgreSQL available — docker compose has no postgres service (Docker Compose not yet configured, Phase 3 work)"

## Summary

total: 6
passed: 4
issues: 0
pending: 0
skipped: 0
blocked: 2
skipped: 0
blocked: 0

## Gaps

[none yet]
