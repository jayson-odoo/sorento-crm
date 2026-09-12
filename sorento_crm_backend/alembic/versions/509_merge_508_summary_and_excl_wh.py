"""merge order summary suggest docs (#798) with stock visibility excl wh (#799)

Revision ID: 509_merge_508_summary_exclwh
Revises: 508_order_summary_suggest_docs, 508_stock_visibility_excl_wh
Create Date: 2026-09-10

#798 and #799 both branched off 507_pi_link_packing_row and merged minutes
apart, so main carried two 508_ heads and the CI head gate failed.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "509_merge_508_summary_exclwh"
down_revision = ("508_order_summary_suggest_docs", "508_stock_visibility_excl_wh")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
