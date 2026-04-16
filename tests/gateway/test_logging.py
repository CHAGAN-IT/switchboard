"""Gateway structured logging tests."""

from __future__ import annotations

import httpx
import respx
import structlog.contextvars
import structlog.testing


def _capture_with_context() -> structlog.testing.capture_logs:
    """Return a capture_logs context manager that merges contextvars.

    structlog.testing.capture_logs() disables all configured processors by
    default. Passing merge_contextvars as a processor ensures that
    contextvars bound during request handling (trace_id, http_method,
    user_identity, server_name) are included in the captured log events.

    Returns:
        Context manager yielding a list of captured log event dicts.
    """
    return structlog.testing.capture_logs(
        processors=[structlog.contextvars.merge_contextvars]
    )


def test_structured_log_line_emitted(gateway_client, customer_auth_headers) -> None:
    """Each proxied request emits at least one structured log event."""
    with _capture_with_context() as captured, respx.mock:
        respx.post("http://sb-echo:8000/mcp").mock(
            return_value=httpx.Response(200, json={})
        )
        gateway_client.post("/servers/echo/mcp", headers=customer_auth_headers, json={})
    assert len(captured) >= 1


def test_log_contains_trace_id(gateway_client, customer_auth_headers) -> None:
    """Structured log line for a proxied request contains a trace_id field."""
    with _capture_with_context() as captured, respx.mock:
        respx.post("http://sb-echo:8000/mcp").mock(
            return_value=httpx.Response(200, json={})
        )
        gateway_client.post("/servers/echo/mcp", headers=customer_auth_headers, json={})
    log_events = [e for e in captured if e.get("event") == "proxied_request"]
    assert log_events, "No 'proxied_request' log event captured"
    assert "trace_id" in log_events[0]


def test_log_contains_user_identity(gateway_client, customer_auth_headers) -> None:
    """Structured log line contains the customer subject from the JWT."""
    with _capture_with_context() as captured, respx.mock:
        respx.post("http://sb-echo:8000/mcp").mock(
            return_value=httpx.Response(200, json={})
        )
        gateway_client.post("/servers/echo/mcp", headers=customer_auth_headers, json={})
    log_events = [e for e in captured if e.get("event") == "proxied_request"]
    assert log_events, "No 'proxied_request' log event captured"
    assert "user_identity" in log_events[0]
    assert log_events[0]["user_identity"] == "user-123"


def test_log_contains_server_name(gateway_client, customer_auth_headers) -> None:
    """Structured log line contains the server_name from the URL path."""
    with _capture_with_context() as captured, respx.mock:
        respx.post("http://sb-echo:8000/mcp").mock(
            return_value=httpx.Response(200, json={})
        )
        gateway_client.post("/servers/echo/mcp", headers=customer_auth_headers, json={})
    log_events = [e for e in captured if e.get("event") == "proxied_request"]
    assert log_events, "No 'proxied_request' log event captured"
    assert "server_name" in log_events[0]
    assert log_events[0]["server_name"] == "echo"


def test_log_contains_http_status(gateway_client, customer_auth_headers) -> None:
    """Structured log line contains the http_status from the proxied response."""
    with _capture_with_context() as captured, respx.mock:
        respx.post("http://sb-echo:8000/mcp").mock(
            return_value=httpx.Response(200, json={})
        )
        gateway_client.post("/servers/echo/mcp", headers=customer_auth_headers, json={})
    log_events = [e for e in captured if e.get("event") == "proxied_request"]
    assert log_events, "No 'proxied_request' log event captured"
    assert "http_status" in log_events[0]
    assert log_events[0]["http_status"] == 200
