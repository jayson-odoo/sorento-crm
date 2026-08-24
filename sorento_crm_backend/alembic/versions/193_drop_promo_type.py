"""Drop promotions.promo_type column.

The DB carries a legacy CHECK constraint ``promotions_promo_type_check`` whose
allowed value list is no longer aligned with the API contract - n8n payloads
sending ``promo_type='discount'`` 500'd on CheckViolation. The column itself is
not load-bearing on any business logic (no flag-driven branching in services),
so we remove it entirely rather than maintain a moving allowed list.

Also clears the ``promo_type`` field from the list-query catalog so the
DataGrid filter UI stops offering it.

Revision ID: 193_drop_promo_type
Revises: 192_promotion_dates_nullable
Create Date: 2026-05-14
"""
import sqlalchemy as sa
from alembic import op


revision = "193_drop_promo_type"
down_revision = "192_promotion_dates_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE promotions DROP CONSTRAINT IF EXISTS promotions_promo_type_check")
    op.execute("DROP INDEX IF EXISTS ix_promotions_promo_type")
    with op.batch_alter_table("promotions") as batch:
        batch.drop_column("promo_type")

    op.execute(
        """
        DELETE FROM list_query_fields
        WHERE field_key = 'promo_type'
          AND resource_id IN (SELECT id FROM list_query_resources WHERE resource_key = 'promotions')
        """
    )


def downgrade() -> None:
    op.add_column(
        "promotions",
        sa.Column("promo_type", sa.String(length=50), nullable=True),
    )
    op.create_index("ix_promotions_promo_type", "promotions", ["promo_type"])
