"""merge plan row price supplier (#337) with uat main and sets (#347)

Revision ID: 438_merge_price_supplier_sets
Revises: 430_plan_row_price_supplier, 437_merge_uat_main_and_sets
Create Date: 2026-08-27

#347 merged 429_merge_scm_uat_main + 433_supplier_code_alias_sets but landed
after #337 had already added 430_plan_row_price_supplier on top of 429, so main
carried two heads and the CI head gate failed.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "438_merge_price_supplier_sets"
down_revision = ("430_plan_row_price_supplier", "437_merge_uat_main_and_sets")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
