"""Drop promotions.name column.

Marketing dropped the name field as well. Promotion identity = UUID + description.
Removes the column and any related index plus the list-query field entry.

Revision ID: 196_drop_promotion_name
Revises: 195_drop_promo_code
Create Date: 2026-05-15
"""
import sqlalchemy as sa
from alembic import op


revision = "196_drop_promotion_name"
down_revision = "195_drop_promo_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for index in inspector.get_indexes("promotions"):
        cols = set(index.get("column_names") or [])
        if "name" in cols and index.get("name"):
            op.drop_index(index["name"], table_name="promotions")

    with op.batch_alter_table("promotions") as batch:
        batch.drop_column("name")

    op.execute(
        """
        DELETE FROM list_query_fields
        WHERE field_key = 'name'
          AND resource_id IN (SELECT id FROM list_query_resources WHERE resource_key = 'promotions')
        """
    )


def downgrade() -> None:
    op.add_column(
        "promotions",
        sa.Column("name", sa.String(length=255), nullable=True),
    )
