"""Add created_at to attachments (mirrors uploaded_at).

Revision ID: 141_attachments_created_at
Revises: 140_promotions_start_end_as_date
Create Date: 2026-04-14

"""
from alembic import op
import sqlalchemy as sa


revision = "141_attachments_created_at"
down_revision = "140_promotions_start_end_as_date"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attachments",
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.execute(sa.text("UPDATE attachments SET created_at = uploaded_at WHERE created_at IS NULL"))
    op.alter_column(
        "attachments",
        "created_at",
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )


def downgrade() -> None:
    op.drop_column("attachments", "created_at")
