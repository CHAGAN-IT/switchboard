"""create servers table

Revision ID: a5578b684627
Revises:
Create Date: 2026-04-14 13:51:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a5578b684627"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "servers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("container_image", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("stopped", "running", "error", name="serverstatus"),
            nullable=False,
        ),
        sa.Column("container_id", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_servers_name"), "servers", ["name"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_servers_name"), table_name="servers")
    op.drop_table("servers")
    # Alembic autogenerate does not drop enum types on downgrade.
    # Without this, running downgrade then upgrade again fails because
    # the enum type already exists.
    op.execute("DROP TYPE IF EXISTS serverstatus")
