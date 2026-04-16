"""Gateway structured logging tests — implemented in Plan 02."""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="gateway app not yet created")
def test_structured_log_line_emitted() -> None:
    """Each proxied request emits a structured log line via structlog."""


@pytest.mark.skip(reason="gateway app not yet created")
def test_log_contains_trace_id() -> None:
    """Structured log line contains a trace_id field."""


@pytest.mark.skip(reason="gateway app not yet created")
def test_log_contains_user_identity() -> None:
    """Structured log line contains the customer subject from the JWT."""
