"""Add generic entity_attachment_links and backfill complaint links.

Revision ID: 076_entity_attachment_links
Revises: 075_backfill_email_verified_at
Create Date: 2026-03-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "076_entity_attachment_links"
down_revision = "075_backfill_email_verified_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entity_attachment_links",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column("attachment_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.ForeignKeyConstraint(["attachment_id"], ["attachments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_entity_attachment_links_entity",
        "entity_attachment_links",
        ["entity_type", "entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_entity_attachment_links_attachment_id",
        "entity_attachment_links",
        ["attachment_id"],
        unique=False,
    )
    op.create_index(
        "uq_entity_attachment_links_unique",
        "entity_attachment_links",
        ["entity_type", "entity_id", "attachment_id"],
        unique=True,
    )

    # Backfill existing complaint attachment links into the generic table.
    op.execute(
        """
        INSERT INTO entity_attachment_links
            (id, entity_type, entity_id, attachment_id, is_primary, sort_order, created_at, created_by)
        SELECT
            ca.id,
            'complaint' AS entity_type,
            ca.complaint_id::text AS entity_id,
            ca.attachment_id,
            ca.is_primary,
            ca.sort_order,
            ca.created_at,
            ca.created_by
        FROM complaint_attachments ca
        ON CONFLICT (entity_type, entity_id, attachment_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("uq_entity_attachment_links_unique", table_name="entity_attachment_links")
    op.drop_index("ix_entity_attachment_links_attachment_id", table_name="entity_attachment_links")
    op.drop_index("ix_entity_attachment_links_entity", table_name="entity_attachment_links")
    op.drop_table("entity_attachment_links")

