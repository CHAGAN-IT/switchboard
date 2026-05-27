"""MCP proxy handler — routes customer requests to backend containers.

Handles request forwarding, Authorization header stripping, server name
validation, and session-sticky routing. All routing is stateless from
the database perspective: backends are reached by DNS name sb-{name}:8000
on the switchboard-internal Docker network.

Depends on: switchboard.registry.models (SERVER_NAME_PATTERN),
            switchboard.gateway.auth (require_customer)
"""

from __future__ import annotations

import asyncio
from typing import Annotated

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

from switchboard.config import get_settings
from switchboard.gateway.auth import require_customer
from switchboard.registry.models import SERVER_NAME_PATTERN

log = structlog.get_logger()

# Hop-by-hop headers must not be forwarded through an ASGI proxy layer.
# Forwarding Transfer-Encoding or Connection causes content decoding errors
# and connection management issues in Starlette's StreamingResponse.
HOP_BY_HOP_HEADERS: frozenset[str] = frozenset({
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
})

# Session stickiness map: Mcp-Session-Id → backend base URL
# Protected by _session_lock for concurrent request safety (D-12).
_session_map: dict[str, str] = {}
_session_lock = asyncio.Lock()

router = APIRouter()


async def resolve_backend(server_name: str, session_id: str | None) -> str:
    """Resolve the backend base URL for a given server and session.

    If session_id is None, returns a fresh URL by server name.
    If session_id is known, returns the previously recorded URL for
    session affinity. If session_id is new, records and returns the
    server-name-derived URL.

    In ECS, the Cloud Map domain suffix (e.g. ``.switchboard.local``)
    is appended to produce DNS names that resolve via AWS Cloud Map
    service discovery (D-07). In local Docker Compose, the suffix is
    empty and the plain ``sb-{name}`` hostname resolves via Docker DNS.

    Args:
        server_name: The MCP server name used for DNS-based routing.
        session_id: The Mcp-Session-Id header value, or None if absent.

    Returns:
        Backend base URL of the form ``http://sb-{name}{suffix}:8000``.
    """
    settings = get_settings()
    domain_suffix = settings.cloud_map_domain
    if session_id is None:
        return f"http://sb-{server_name}{domain_suffix}:8000"
    async with _session_lock:
        if session_id in _session_map:
            return _session_map[session_id]
        target = f"http://sb-{server_name}{domain_suffix}:8000"
        _session_map[session_id] = target
        return target


@router.api_route(
    "/servers/{server_name}/mcp",
    methods=["GET", "POST"],
    include_in_schema=False,
)
async def proxy_mcp_request(
    server_name: str,
    request: Request,
    payload: Annotated[dict, Depends(require_customer)],
) -> StreamingResponse:
    """Proxy a customer MCP request to the appropriate backend container.

    Validates the server name, strips security-sensitive headers,
    resolves the backend URL (with session affinity), and streams
    the backend response back to the customer.

    Authorization and host headers are stripped before forwarding
    to prevent JWT leakage to backend containers (SECU-02 clause 2).

    Args:
        server_name: Server name extracted from the URL path.
        request: Incoming Starlette request object.
        payload: Decoded JWT payload from require_customer dependency.

    Returns:
        StreamingResponse relaying the backend's response body.

    Raises:
        HTTPException: 404 if server_name does not match the required
            pattern (T-5-05, T-5-07 — prevents SSRF via path injection).
        HTTPException: 503 if the backend container is unreachable
            (T-5-08 — connection leak also prevented via BackgroundTask).
    """
    # Validate server name against strict pattern before any DNS lookup
    # (T-5-05, T-5-07: prevents routing to unexpected hosts via SSRF).
    if not SERVER_NAME_PATTERN.match(server_name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server '{server_name}' not found",
        )

    # Starlette normalizes all header names to lowercase.
    session_id = request.headers.get("mcp-session-id")

    # Bind user identity and server name so the middleware log event
    # captures them via structlog.contextvars.merge_contextvars.
    structlog.contextvars.bind_contextvars(
        user_identity=payload["sub"],
        server_name=server_name,
    )

    backend_base = await resolve_backend(server_name, session_id)
    backend_url = f"{backend_base}/mcp"

    # Strip Authorization and host headers before forwarding (T-5-06).
    # Authorization must never reach backend containers (SECU-02 clause 2).
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in ("authorization", "host")
    }

    http_client: httpx.AsyncClient = request.app.state.http_client
    rp_req = http_client.build_request(
        method=request.method,
        url=backend_url,
        headers=headers,
        content=request.stream(),  # Streaming body — no buffering
    )

    try:
        rp_resp = await http_client.send(rp_req, stream=True)
    except httpx.ConnectError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Server '{server_name}' is unavailable",
        ) from None

    # Log here (not in middleware) because BaseHTTPMiddleware runs call_next
    # in a new asyncio task — contextvars bound in the route (user_identity,
    # server_name) are not visible in the middleware context after call_next.
    log.info("proxied_request", http_status=rp_resp.status_code)

    # Register aclose as a BackgroundTask so the connection is released
    # even if the client disconnects mid-stream (T-5-08).
    # Hop-by-hop headers are stripped to prevent content decoding errors
    # and connection management issues in the ASGI layer.
    return StreamingResponse(
        rp_resp.aiter_raw(),
        status_code=rp_resp.status_code,
        headers={
            k: v
            for k, v in rp_resp.headers.items()
            if k.lower() not in HOP_BY_HOP_HEADERS
        },
        background=BackgroundTask(rp_resp.aclose),
    )
