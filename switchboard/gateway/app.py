"""FastAPI application instance for the Switchboard Gateway.

Entry point for running the gateway server:
    uvicorn switchboard.gateway.app:app

Mounts the MCP proxy router at the root. Customer JWT validation
is applied per-route via require_customer dependency in proxy.py.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import httpx
import structlog
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

from switchboard.gateway.proxy import router

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(0),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

log = structlog.get_logger()


class RequestLogMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that binds trace_id and http_method per request.

    Clears structlog contextvars and binds a fresh trace_id and http_method
    before calling the route handler. The "proxied_request" log event is
    emitted from proxy_mcp_request (not here) because Starlette's
    BaseHTTPMiddleware runs call_next in a new task context — contextvars
    set in the route handler (user_identity, server_name) are not visible
    in the middleware's context after call_next returns.
    """

    async def dispatch(self, request: Request, call_next):
        """Bind per-request contextvars and delegate to the route handler.

        Args:
            request: Incoming Starlette request.
            call_next: Next middleware or route handler.

        Returns:
            Response from the downstream handler.
        """
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            trace_id=str(uuid.uuid4()),
            http_method=request.method,
        )
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create shared httpx.AsyncClient at startup; close at shutdown.

    The client is stored on app.state so proxy handlers can access it
    via request.app.state.http_client.
    """
    app.state.http_client = httpx.AsyncClient(timeout=30.0)
    yield
    await app.state.http_client.aclose()


app = FastAPI(
    title="Switchboard Gateway",
    description="Customer-facing MCP proxy gateway",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(RequestLogMiddleware)
app.include_router(router)


@app.get("/.well-known/oauth-protected-resource", include_in_schema=False)
async def oauth_protected_resource(request: Request) -> dict:
    """RFC 9728 §2 protected resource metadata endpoint.

    Returns a minimal compliant document. The 'resource' field is
    required; 'bearer_methods_supported' indicates Bearer token delivery
    via Authorization header.

    Args:
        request: Incoming request used to derive the base URL.

    Returns:
        Dictionary with 'resource' and 'bearer_methods_supported' keys.
    """
    base_url = str(request.base_url).rstrip("/")
    return {"resource": base_url, "bearer_methods_supported": ["header"]}
