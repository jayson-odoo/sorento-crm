"""join order inquiry number and product sets

Revision ID: 418_merge_oi_product_sets
Revises: 415_merge_pset_pushidea, 417_order_inquiry_number
Create Date: 2026-08-25 18:30:52.124438

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '418_merge_oi_product_sets'
down_revision = ('415_merge_pset_pushidea', '417_order_inquiry_number')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
