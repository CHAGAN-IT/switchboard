"""Gateway well-known endpoint tests — implemented in Plan 02."""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="gateway app not yet created")
def test_oauth_resource_metadata_returns_resource_field() -> None:
    """GET /.well-known/oauth-protected-resource returns JSON with 'resource' field."""


@pytest.mark.skip(reason="gateway app not yet created")
def test_oauth_resource_metadata_content_type_json() -> None:
    """/.well-known/oauth-protected-resource returns Content-Type: application/json."""
