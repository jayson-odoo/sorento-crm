"""Drop global unique promo_code to allow uniqueness by code + access level set in service.

Revision ID: 095_promotion_code_access_levels_uniqueness
Revises: 094_contact_access_types
Create Date: 2026-03-19
"""
from alembic import op
import sqlalchemy as sa


revision = "095_promotion_code_access_levels_uniqueness"
down_revision = "094_contact_access_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Drop any unique constraint/index that enforces promo_code-only uniqueness.
    for constraint in inspector.get_unique_constraints("promotions"):
        if set(constraint.get("column_names") or []) == {"promo_code"} and constraint.get("name"):
            op.drop_constraint(constraint["name"], "promotions", type_="unique")

    for index in inspector.get_indexes("promotions"):
        if index.get("unique") and set(index.get("column_names") or []) == {"promo_code"} and index.get("name"):
            op.drop_index(index["name"], table_name="promotions")


def downgrade() -> None:
    bind = op.get_bind()
    duplicate = bind.execute(
        sa.text(
            """
            SELECT promo_code
            FROM promotions
            GROUP BY promo_code
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate:
        raise RuntimeError(
            "Cannot restore promo_code global uniqueness because duplicates exist in promotions."
        )

    op.create_unique_constraint("uq_promotions_promo_code", "promotions", ["promo_code"])
