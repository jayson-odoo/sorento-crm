"""merge promo-expiry and integration-merge heads

Revision ID: cbf3a0044924
Revises: 301_promo_expiry_rule_engine, a6c37a883cc4
Create Date: 2026-07-25 09:27:02.666354

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cbf3a0044924'
down_revision = ('301_promo_expiry_rule_engine', 'a6c37a883cc4')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
