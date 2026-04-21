"""FastAPI application instance for the Switchboard Admin API.

Entry point for running the Admin API server:
    uvicorn switchboard.admin.app:app --reload

Mounts the server registration router at /api/v1/.
Starts the health monitor background task in the lifespan.
"""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import httpx
import structlog
from fastapi import FastAPI

from switchboard.admin.router import router

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage health monitor lifecycle.

    Startup:
    - Create a shared httpx.AsyncClient for health probes (D-03)
    - Start the HealthMonitor polling loop as a background task (D-10)

    Shutdown:
    - Cancel the polling task
    - Close the httpx client
    """
    from switchboard.config import get_settings
    from switchboard.db.session import async_session_factory
    from switchboard.health.monitor import HealthMonitor

    settings = get_settings()

    # Shared HTTP client for health probes -- 5s read, 3s connect (T-6-06)
    app.state.health_client = httpx.AsyncClient(
        timeout=httpx.Timeout(5.0, connect=3.0),
    )

    # Start health monitor background task (D-10, D-11)
    monitor = HealthMonitor(
        session_factory=async_session_factory,
        http_client=app.state.health_client,
        poll_interval=settings.health_poll_interval,
        cloud_map_domain=settings.cloud_map_domain,
    )
    task = asyncio.create_task(monitor.run())
    logger.info(
        "health_monitor_started",
        poll_interval=settings.health_poll_interval,
    )

    yield

    # Shutdown: cancel task, close client
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    await app.state.health_client.aclose()
    logger.info("health_monitor_stopped")


app = FastAPI(
    title="Switchboard Admin API",
    description="Operator API for managing MCP server registrations",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    """Unauthenticated health endpoint for ECS/Docker healthchecks.

    Returns a minimal response with no sensitive data (version, config,
    debug info). Registered directly on the app -- not on the authenticated
    router -- so ECS container healthchecks can reach it without JWT.

    Returns:
        Dictionary with single key "status" set to "ok".
    """
    return {"status": "ok"}
