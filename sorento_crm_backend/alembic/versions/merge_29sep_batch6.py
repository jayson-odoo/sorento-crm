"""Join the heads left on main by the #1333 merge.

#1353 landed `chatbot_picker_domain_1352` hung off
`cpc4_cost_packaging_method`; #1333 then landed a chain ending at
`sa2_0005_stock_ask_source` whose first revision (`sa2_0004_stock_asks`)
also hangs off `cpc4_cost_packaging_method`, so main carried two heads.
Schema-free merge point.

Revision ID: merge_29sep_batch6
Revises: chatbot_picker_domain_1352, sa2_0005_stock_ask_source
"""
from __future__ import annotations

revision = "merge_29sep_batch6"
down_revision = ("chatbot_picker_domain_1352", "sa2_0005_stock_ask_source")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
