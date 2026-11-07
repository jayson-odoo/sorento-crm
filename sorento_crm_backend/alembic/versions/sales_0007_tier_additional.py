"""Sales targets: a tier's % Additional (lane TARGET-TIER-ADDITIONAL, owner 5 Nov 11:10).

`sales.target_commission_tiers.additional_rate` numeric(9,4) NULL, >= 0: paid on top of the
tier's rate when it is the tier reached. Schema only: existing "+ Additional" rows keep paying as
before until `scripts/fold_tier_additionals.py --apply` (owner-approved) moves them onto their
tier. Downgrade drops the column.

Revision ID: sales_0007_tier_additional
Revises: slb_0001_leaderboard_perm
Create Date: 2026-11-05
"""
import sqlalchemy as sa
from alembic import op

from app.models.sales import translated_schema

revision = "sales_0007_tier_additional"
down_revision = "slb_0001_leaderboard_perm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = translated_schema(op.get_bind())
    op.add_column(
        "target_commission_tiers",
        sa.Column("additional_rate", sa.Numeric(9, 4), nullable=True),
        schema=schema,
    )
    op.create_check_constraint(
        "ck_sales_target_commission_tiers_additional_rate",
        "target_commission_tiers",
        "additional_rate IS NULL OR additional_rate >= 0",
        schema=schema,
    )


def downgrade() -> None:
    schema = translated_schema(op.get_bind())
    op.drop_constraint(
        "ck_sales_target_commission_tiers_additional_rate",
        "target_commission_tiers",
        schema=schema,
        type_="check",
    )
    op.drop_column("target_commission_tiers", "additional_rate", schema=schema)
