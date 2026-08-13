"""merge spec-search and sla-undo heads

Revision ID: cac36dbd46ab
Revises: 311n_product_findability, 312c_seed_undo_template_defaults
Create Date: 2026-08-11 21:59:47.541481

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cac36dbd46ab'
down_revision = ('311n_product_findability', '312c_seed_undo_template_defaults')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
