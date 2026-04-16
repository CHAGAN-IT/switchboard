"""Gateway session affinity tests — implemented in Plan 02."""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="gateway app not yet created")
def test_session_affinity_routes_to_same_backend() -> None:
    """Requests with the same session ID are routed to the same backend."""


@pytest.mark.skip(reason="gateway app not yet created")
def test_first_request_records_session() -> None:
    """First request creates a session record for the server."""


@pytest.mark.skip(reason="gateway app not yet created")
def test_no_session_id_routes_by_name() -> None:
    """Request without session ID is routed to any healthy backend for the server."""
