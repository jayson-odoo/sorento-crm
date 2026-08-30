"""merge close-convo setting and product is_searchable heads

Revision ID: 421_merge_closeconvo_searchable
Revises: 420_close_convo_webhook_setting, 420_product_is_searchable
Create Date: 2026-08-26

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '421_merge_closeconvo_searchable'
down_revision = ('420_close_convo_webhook_setting', '420_product_is_searchable')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
