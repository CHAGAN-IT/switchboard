"""Tests for Server ORM model and Pydantic schemas."""

from __future__ import annotations

import pytest

from switchboard.registry.models import SERVER_NAME_PATTERN, Server, ServerStatus
from switchboard.registry.schemas import ServerCreate, ServerRead


@pytest.mark.parametrize(
    "name,valid",
    [
        ("my-server", True),
        ("valid-server-01", True),
        ("abc", True),
        ("a" * 64, True),
        ("a1", False),
        ("a" * 65, False),
        ("-invalid", False),
        ("invalid-", False),
        ("UPPERCASE", False),
        ("has space", False),
        ("has_underscore", False),
        ("a-b", True),
        ("123", True),
    ],
    ids=[
        "valid-hyphenated",
        "valid-with-numbers",
        "valid-min-length-3",
        "valid-max-length-64",
        "invalid-too-short-2",
        "invalid-too-long-65",
        "invalid-starts-hyphen",
        "invalid-ends-hyphen",
        "invalid-uppercase",
        "invalid-space",
        "invalid-underscore",
        "valid-three-char-hyphen",
        "valid-all-digits",
    ],
)
def test_server_name_pattern(name: str, valid: bool) -> None:
    """Verify server name regex matches spec (D-08)."""
    result = SERVER_NAME_PATTERN.match(name)
    if valid:
        assert result is not None, f"Expected '{name}' to be valid"
    else:
        assert result is None, f"Expected '{name}' to be invalid"


def test_server_status_enum_members() -> None:
    """ServerStatus has exactly stopped, running, error (D-05)."""
    members = {m.name for m in ServerStatus}
    assert members == {"stopped", "running", "error"}


def test_server_status_enum_values() -> None:
    """ServerStatus values are lowercase strings matching member names."""
    assert ServerStatus.stopped.value == "stopped"
    assert ServerStatus.running.value == "running"
    assert ServerStatus.error.value == "error"


def test_server_validates_name_rejects_invalid() -> None:
    """Server @validates raises ValueError for invalid name (D-08)."""
    server = Server.__new__(Server)
    with pytest.raises(ValueError, match="does not match"):
        server.validate_name("name", "INVALID-NAME!")


def test_server_validates_name_accepts_valid() -> None:
    """Server @validates passes for valid name (D-08)."""
    server = Server.__new__(Server)
    result = server.validate_name("name", "valid-server")
    assert result == "valid-server"


def test_server_create_schema() -> None:
    """ServerCreate accepts valid fields (D-11)."""
    schema = ServerCreate(name="test-server", container_image="img:latest")
    assert schema.name == "test-server"
    assert schema.container_image == "img:latest"
    assert schema.description is None


def test_server_create_schema_with_description() -> None:
    """ServerCreate accepts optional description."""
    schema = ServerCreate(
        name="test-server",
        container_image="img:latest",
        description="A test server",
    )
    assert schema.description == "A test server"


def test_server_read_schema_from_attributes() -> None:
    """ServerRead has from_attributes=True for ORM compatibility (D-11)."""
    assert ServerRead.model_config.get("from_attributes") is True
