"""Gateway proxy route tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import respx

if TYPE_CHECKING:
    import pytest


def test_post_proxied(gateway_client, customer_auth_headers) -> None:
    """POST to /servers/echo/mcp with valid JWT is proxied to backend."""
    with respx.mock:
        respx.post("http://sb-echo:8000/mcp").mock(
            return_value=httpx.Response(200, json={"result": "ok"})
        )
        resp = gateway_client.post(
            "/servers/echo/mcp",
            headers=customer_auth_headers,
            json={"method": "ping"},
        )
    assert resp.status_code == 200


def test_get_sse_proxied(gateway_client, customer_auth_headers) -> None:
    """GET /servers/echo/mcp with valid JWT is proxied and returns 200."""
    with respx.mock:
        respx.get("http://sb-echo:8000/mcp").mock(
            return_value=httpx.Response(200, text="data: {}\n\n")
        )
        resp = gateway_client.get("/servers/echo/mcp", headers=customer_auth_headers)
    assert resp.status_code == 200


def test_authorization_header_stripped(gateway_client, customer_auth_headers) -> None:
    """Customer Authorization header is stripped before forwarding to backend."""
    captured: dict = {}

    def capture(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json={})

    with respx.mock:
        respx.post("http://sb-echo:8000/mcp").mock(side_effect=capture)
        gateway_client.post("/servers/echo/mcp", headers=customer_auth_headers, json={})
    assert "authorization" not in captured.get("headers", {})


def test_host_header_stripped(gateway_client, customer_auth_headers) -> None:
    """Client's original host header is not forwarded to the backend.

    The incoming request carries host=testserver (the TestClient default).
    The proxy strips it before forwarding; httpx then sets its own host
    header for the backend URL (sb-echo:8000). We assert the client's
    original host value is not in the forwarded request.
    """
    captured: dict = {}

    def capture(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json={})

    with respx.mock:
        respx.post("http://sb-echo:8000/mcp").mock(side_effect=capture)
        gateway_client.post("/servers/echo/mcp", headers=customer_auth_headers, json={})
    # The original client host (testserver) must not be forwarded.
    # httpx legitimately injects its own host for the backend URL.
    forwarded_host = captured.get("headers", {}).get("host", "")
    assert "testserver" not in forwarded_host


def test_invalid_server_name_returns_404(gateway_client, customer_auth_headers) -> None:
    """Request for a server name with invalid characters returns 404."""
    resp = gateway_client.post(
        "/servers/INVALID_NAME/mcp",
        headers=customer_auth_headers,
        json={},
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


def test_unreachable_backend_returns_503(gateway_client, customer_auth_headers) -> None:
    """Request to unreachable backend container returns 503 with detail."""
    with respx.mock:
        respx.post("http://sb-echo:8000/mcp").mock(
            side_effect=httpx.ConnectError("refused")
        )
        resp = gateway_client.post(
            "/servers/echo/mcp", headers=customer_auth_headers, json={}
        )
    assert resp.status_code == 503
    assert "unavailable" in resp.json()["detail"]


def test_resolve_backend_local_dev_no_domain_suffix(
    gateway_client, customer_auth_headers
) -> None:
    """With empty cloud_map_domain (local dev), URL has no domain suffix."""
    with respx.mock:
        respx.post("http://sb-echo:8000/mcp").mock(
            return_value=httpx.Response(200, json={"result": "ok"})
        )
        resp = gateway_client.post(
            "/servers/echo/mcp",
            headers=customer_auth_headers,
            json={"method": "ping"},
        )
    assert resp.status_code == 200


def test_resolve_backend_ecs_cloud_map_domain(
    monkeypatch: pytest.MonkeyPatch,
    customer_auth_headers,
) -> None:
    """With cloud_map_domain set, backend URL includes domain suffix."""
    monkeypatch.setenv("CUSTOMER_JWT_SECRET", "pytest-customer-secret-32bytes!!")
    monkeypatch.setenv(
        "OPERATOR_JWT_SECRET", "pytest-default-secret-32-bytes-min!"
    )
    monkeypatch.setenv("CLOUD_MAP_DOMAIN", ".switchboard.local")
    from switchboard.config import get_settings

    get_settings.cache_clear()

    from fastapi.testclient import TestClient

    from switchboard.gateway.app import app

    with TestClient(app, raise_server_exceptions=False) as client:
        with respx.mock:
            respx.post("http://sb-echo.switchboard.local:8000/mcp").mock(
                return_value=httpx.Response(200, json={"result": "ok"})
            )
            resp = client.post(
                "/servers/echo/mcp",
                headers=customer_auth_headers,
                json={"method": "ping"},
            )
        assert resp.status_code == 200
    get_settings.cache_clear()
