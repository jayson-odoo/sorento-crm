"""Add `access_levels` JSONB column + GIN index to `brands`.

Brands now carry the same access-level vocabulary as promotions / attachments
(`contact_access_types.code`). Used by the resolver's promotion-domain product
fallback: when a promotion isn't found for the active contact's access levels,
the fallback product search scopes to products whose brand.access_levels
intersect the supplied codes — keeps the agent from surfacing products the
contact isn't supposed to see.

Default `["dealer","end_user"]` mirrors the existing Attachment + Promotion
default so legacy brands stay broadly visible.

Revision ID: 222_brands_access_levels
Revises: 221_resync_customer_pairs
Create Date: 2026-06-02
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision = "222_brands_access_levels"
down_revision = "221_resync_customer_pairs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "brands",
        sa.Column(
            "access_levels",
            JSONB(),
            nullable=False,
            server_default=sa.text("""'["dealer","end_user"]'::jsonb"""),
        ),
    )
    op.create_index(
        "ix_brands_access_levels",
        "brands",
        ["access_levels"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_brands_access_levels", table_name="brands")
    op.drop_column("brands", "access_levels")
