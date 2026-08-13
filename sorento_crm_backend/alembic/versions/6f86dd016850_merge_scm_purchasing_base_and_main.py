"""merge scm purchasing base and main

Revision ID: 6f86dd016850
Revises: 352_scm_product_lifecycle_decision, cac36dbd46ab
Create Date: 2026-08-13 00:21:19.659407

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6f86dd016850'
down_revision = ('352_scm_product_lifecycle_decision', 'cac36dbd46ab')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
