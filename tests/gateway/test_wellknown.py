"""Gateway well-known endpoint tests."""

from __future__ import annotations


def test_oauth_resource_metadata_returns_resource_field(gateway_client) -> None:
    """GET /.well-known/oauth-protected-resource returns JSON with 'resource' field."""
    resp = gateway_client.get("/.well-known/oauth-protected-resource")
    assert resp.status_code == 200
    data = resp.json()
    assert "resource" in data


def test_oauth_resource_metadata_content_type_json(gateway_client) -> None:
    """/.well-known/oauth-protected-resource returns Content-Type: application/json."""
    resp = gateway_client.get("/.well-known/oauth-protected-resource")
    assert "application/json" in resp.headers["content-type"]


def test_bearer_methods_supported_field_present(gateway_client) -> None:
    """/.well-known/oauth-protected-resource returns 'bearer_methods_supported'."""
    resp = gateway_client.get("/.well-known/oauth-protected-resource")
    data = resp.json()
    assert "bearer_methods_supported" in data
    assert "header" in data["bearer_methods_supported"]
