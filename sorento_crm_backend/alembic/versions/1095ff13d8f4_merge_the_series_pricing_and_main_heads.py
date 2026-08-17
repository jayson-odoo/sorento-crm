"""merge the series-pricing and main heads

Revision ID: 1095ff13d8f4
Revises: 333_series_product_pricing, cac36dbd46ab
Create Date: 2026-08-12 14:19:57.479599

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1095ff13d8f4'
down_revision = ('333_series_product_pricing', 'cac36dbd46ab')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
