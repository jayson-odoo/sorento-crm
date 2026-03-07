"""Create user_quick_access table for sidebar quick access pins.

Revision ID: 059_user_quick_access
Revises: 058_spo_number_picking_headers
Create Date: 2026-02-20

"""
from alembic import op
import sqlalchemy as sa


revision = "059_user_quick_access"
down_revision = "058_spo_number_picking_headers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_quick_access",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_user_quick_access_user_id", "user_quick_access", ["user_id"])
    op.create_index(
        "ix_user_quick_access_user_id_path",
        "user_quick_access",
        ["user_id", "path"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_user_quick_access_user_id_path", table_name="user_quick_access")
    op.drop_index("ix_user_quick_access_user_id", table_name="user_quick_access")
    op.drop_table("user_quick_access")
