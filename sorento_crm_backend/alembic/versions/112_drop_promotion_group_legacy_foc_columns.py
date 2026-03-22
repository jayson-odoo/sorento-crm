"""Drop legacy purchase_quantity_for_foc / foc_quantity; use foc_tiers JSON only.

Revision ID: 112_drop_promotion_group_legacy_foc_columns
Revises: 111_promotion_group_foc_tiers
"""
from alembic import op
import sqlalchemy as sa


revision = "112_drop_promotion_group_legacy_foc_columns"
down_revision = "111_promotion_group_foc_tiers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "promotion_groups" not in insp.get_table_names():
        return

    columns = {c["name"] for c in insp.get_columns("promotion_groups")}
    has_legacy = "purchase_quantity_for_foc" in columns and "foc_quantity" in columns
    if not has_legacy:
        # Already migrated / schema created without legacy columns; nothing to backfill or drop.
        return

    # Preserve data: rows that still only have legacy columns get foc_tiers backfilled
    op.execute(
        """
        UPDATE promotion_groups
        SET foc_tiers = jsonb_build_array(
            jsonb_build_object(
                'purchase_quantity', purchase_quantity_for_foc,
                'foc_quantity', foc_quantity
            )
        )
        WHERE foc_tiers IS NULL
          AND purchase_quantity_for_foc IS NOT NULL
          AND foc_quantity IS NOT NULL
        """
    )
    op.drop_column("promotion_groups", "purchase_quantity_for_foc")
    op.drop_column("promotion_groups", "foc_quantity")


def downgrade() -> None:
    op.add_column(
        "promotion_groups",
        sa.Column("purchase_quantity_for_foc", sa.Integer(), nullable=True),
    )
    op.add_column(
        "promotion_groups",
        sa.Column("foc_quantity", sa.Integer(), nullable=True),
    )
    op.execute(
        """
        UPDATE promotion_groups
        SET
            purchase_quantity_for_foc = (foc_tiers->0->>'purchase_quantity')::integer,
            foc_quantity = (foc_tiers->0->>'foc_quantity')::integer
        WHERE foc_tiers IS NOT NULL
          AND jsonb_array_length(foc_tiers) > 0
        """
    )
