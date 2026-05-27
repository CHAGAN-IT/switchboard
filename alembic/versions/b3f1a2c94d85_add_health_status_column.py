"""add health_status column

Revision ID: b3f1a2c94d85
Revises: a5578b684627
Create Date: 2026-04-18 14:42:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3f1a2c94d85"
down_revision: str | None = "a5578b684627"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # add_column() does NOT auto-create PostgreSQL enum types (unlike
    # create_table()). Must explicitly create the type first.
    healthstatus = sa.Enum("healthy", "degraded", "unreachable", name="healthstatus")
    healthstatus.create(op.get_bind())
    op.add_column(
        "servers",
        sa.Column(
            "health_status",
            sa.Enum(
                "healthy",
                "degraded",
                "unreachable",
                name="healthstatus",
                create_type=False,
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("servers", "health_status")
    op.execute("DROP TYPE IF EXISTS healthstatus")
