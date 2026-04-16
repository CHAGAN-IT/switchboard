"""Gateway proxy route tests — implemented in Plan 02."""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="gateway app not yet created")
def test_post_proxied() -> None:
    """POST to /servers/{name}/mcp is proxied to backend container."""


@pytest.mark.skip(reason="gateway app not yet created")
def test_get_sse_proxied() -> None:
    """GET /servers/{name}/sse is proxied with SSE streaming."""


@pytest.mark.skip(reason="gateway app not yet created")
def test_authorization_header_stripped() -> None:
    """Customer Authorization header is stripped before forwarding to backend."""


@pytest.mark.skip(reason="gateway app not yet created")
def test_invalid_server_name_returns_404() -> None:
    """Request for unregistered server name returns 404."""


@pytest.mark.skip(reason="gateway app not yet created")
def test_unreachable_backend_returns_503() -> None:
    """Request to unreachable backend container returns 503."""
