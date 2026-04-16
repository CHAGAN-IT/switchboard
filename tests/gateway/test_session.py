"""Gateway session affinity tests."""

from __future__ import annotations

import httpx
import respx

from switchboard.gateway.proxy import _session_map


def test_first_request_records_session(gateway_client, customer_auth_headers) -> None:
    """First request with a session ID records the backend in the session map."""
    _session_map.clear()
    with respx.mock:
        respx.post("http://sb-echo:8000/mcp").mock(
            return_value=httpx.Response(200, json={})
        )
        gateway_client.post(
            "/servers/echo/mcp",
            headers={**customer_auth_headers, "mcp-session-id": "sess-001"},
            json={},
        )
    assert "sess-001" in _session_map
    assert _session_map["sess-001"] == "http://sb-echo:8000"


def test_session_affinity_routes_to_same_backend(
    gateway_client, customer_auth_headers
) -> None:
    """Subsequent requests with the same session ID route to the recorded backend."""
    _session_map.clear()
    # Pre-seed session map with echo backend for sess-002.
    _session_map["sess-002"] = "http://sb-echo:8000"
    captured_urls: list[str] = []

    def capture(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        return httpx.Response(200, json={})

    with respx.mock:
        # The route in the URL says "ping" but session should override to echo.
        respx.post(url__regex=r"http://sb-(echo|ping):8000/mcp").mock(
            side_effect=capture
        )
        gateway_client.post(
            "/servers/ping/mcp",
            headers={**customer_auth_headers, "mcp-session-id": "sess-002"},
            json={},
        )
    assert all("sb-echo:8000" in url for url in captured_urls)


def test_no_session_id_routes_by_name(gateway_client, customer_auth_headers) -> None:
    """Request without session ID is routed by server name."""
    _session_map.clear()
    captured_urls: list[str] = []

    def capture(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        return httpx.Response(200, json={})

    with respx.mock:
        respx.post("http://sb-ping:8000/mcp").mock(side_effect=capture)
        gateway_client.post("/servers/ping/mcp", headers=customer_auth_headers, json={})
    assert any("sb-ping:8000" in url for url in captured_urls)
