"""merge scm uat main and supplier code sets

Revision ID: 437_merge_uat_main_and_sets
Revises: 429_merge_scm_uat_main, 433_supplier_code_alias_sets
Create Date: 2026-08-27 15:05:50.110921

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '437_merge_uat_main_and_sets'
down_revision = ('429_merge_scm_uat_main', '433_supplier_code_alias_sets')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
