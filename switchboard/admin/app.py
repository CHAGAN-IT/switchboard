"""FastAPI application instance for the Switchboard Admin API.

Entry point for running the Admin API server:
    uvicorn switchboard.admin.app:app --reload

Mounts the server registration router at /api/v1/.
"""

from __future__ import annotations

from fastapi import FastAPI

from switchboard.admin.router import router

app = FastAPI(
    title="Switchboard Admin API",
    description="Operator API for managing MCP server registrations",
    version="0.1.0",
)
app.include_router(router)
