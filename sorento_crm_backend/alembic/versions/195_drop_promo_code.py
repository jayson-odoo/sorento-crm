"""Drop promotions.promo_code column.

Marketing dropped the human-facing promo code requirement. Promotions are now
identified by UUID + name only. This removes the column, related unique
constraints/indexes, and the entry from the list-query catalog.

Revision ID: 195_drop_promo_code
Revises: 194_contact_impersonation_sessions
Create Date: 2026-05-15
"""
import sqlalchemy as sa
from alembic import op


revision = "195_drop_promo_code"
down_revision = "194_contact_impersonation_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for constraint in inspector.get_unique_constraints("promotions"):
        cols = set(constraint.get("column_names") or [])
        if "promo_code" in cols and constraint.get("name"):
            op.drop_constraint(constraint["name"], "promotions", type_="unique")

    for index in inspector.get_indexes("promotions"):
        cols = set(index.get("column_names") or [])
        if "promo_code" in cols and index.get("name"):
            op.drop_index(index["name"], table_name="promotions")

    with op.batch_alter_table("promotions") as batch:
        batch.drop_column("promo_code")

    op.execute(
        """
        DELETE FROM list_query_fields
        WHERE field_key = 'promo_code'
          AND resource_id IN (SELECT id FROM list_query_resources WHERE resource_key = 'promotions')
        """
    )


def downgrade() -> None:
    op.add_column(
        "promotions",
        sa.Column("promo_code", sa.String(length=50), nullable=True),
    )
