"""Multiple FOC tier combinations per promotion group (JSONB foc_tiers).

Revision ID: 111_promotion_group_foc_tiers
Revises: 110_promotion_groups_bundle
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "111_promotion_group_foc_tiers"
down_revision = "110_promotion_groups_bundle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "promotion_groups",
        sa.Column("foc_tiers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.execute(
        """
        UPDATE promotion_groups
        SET foc_tiers = jsonb_build_array(
            jsonb_build_object(
                'purchase_quantity', purchase_quantity_for_foc,
                'foc_quantity', foc_quantity
            )
        )
        WHERE purchase_quantity_for_foc IS NOT NULL
          AND foc_quantity IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_column("promotion_groups", "foc_tiers")
