"""Tests for ECS-related Settings fields.

Verifies that the Settings class accepts aws_region, ecs_cluster_arn, and
cloud_map_domain fields with empty-string defaults for local development.

Depends on: switchboard.config.Settings
"""

from __future__ import annotations

from switchboard.config import Settings


class TestSettingsECSFields:
    """Validate ECS configuration fields on Settings."""

    def test_settings_ecs_defaults(self) -> None:
        """New ECS fields default to empty strings for local dev."""
        s = Settings(operator_jwt_secret="x" * 32, _env_file=None)
        assert s.aws_region == ""
        assert s.ecs_cluster_arn == ""
        assert s.cloud_map_domain == ""

    def test_settings_ecs_values(self) -> None:
        """ECS fields accept explicit values."""
        s = Settings(
            operator_jwt_secret="x" * 32,
            aws_region="us-east-1",
            ecs_cluster_arn="arn:aws:ecs:us-east-1:123456789012:cluster/switchboard-dev",
            cloud_map_domain=".switchboard.local",
            _env_file=None,
        )
        assert s.aws_region == "us-east-1"
        assert (
            s.ecs_cluster_arn
            == "arn:aws:ecs:us-east-1:123456789012:cluster/switchboard-dev"
        )
        assert s.cloud_map_domain == ".switchboard.local"
