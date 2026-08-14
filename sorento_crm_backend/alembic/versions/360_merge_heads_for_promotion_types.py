"""Merge the container-status and human-source-boost heads.

Two lanes branched off `322_merge_dealer_kit_customers` and neither rejoined, so
`alembic upgrade head` had two answers. Promotion types build on both, so they
merge here. No schema change of its own.

Revision ID: 360_merge_promo_types
Revises: 323_cs_company_backfill, 356_human_source_boost_seed
Create Date: 2026-08-14
"""

revision = "360_merge_promo_types"
down_revision = ("323_cs_company_backfill", "356_human_source_boost_seed")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
