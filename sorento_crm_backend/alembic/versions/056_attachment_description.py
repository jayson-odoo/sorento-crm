"""Add description to attachments for AI/search.

Revision ID: 056_attachment_description
Revises: 055_inbound_shipment_line_unique
Create Date: 2026-02-19

"""
from alembic import op
import sqlalchemy as sa


revision = "056_attachment_description"
down_revision = "055_inbound_shipment_line_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("attachments")]
    if "description" not in columns:
        op.add_column(
            "attachments",
            sa.Column("description", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("attachments")]
    if "description" in columns:
        op.drop_column("attachments", "description")
