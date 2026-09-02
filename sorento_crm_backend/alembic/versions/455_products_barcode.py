"""products.barcode: CRM-owned barcode field, printed by the tag designer

Revision ID: 455_products_barcode
Revises: 454_tag_template_versions
Create Date: 2026-09-02 00:00:00.000000

Nullable and indexed, never unique: not every product carries a barcode yet,
and two products sharing a placeholder value (or none at all) must not block
each other's ingest or manual entry. CRM owns this column (PLAN D14 -
`price-tag-feedback-r2`): AutoCount's `bar_code` overwrites it only when the
incoming value is non-empty, so a value typed on the product master survives
a sync that carries no barcode for that item. See
`app/services/master_ingest_service._product_columns` for the overwrite rule.

MERGE ORDER: chains onto `454_tag_template_versions` (PR #486, unmerged at
authoring time) rather than `453_shared_brand_attach`, to avoid a dual head on
`main`. See that PR's plan slice (S5) for the reason.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '455_products_barcode'
down_revision = '454_tag_template_versions'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('products', sa.Column('barcode', sa.String(length=100), nullable=True))
    op.create_index('ix_products_barcode', 'products', ['barcode'])


def downgrade() -> None:
    op.drop_index('ix_products_barcode', table_name='products')
    op.drop_column('products', 'barcode')
