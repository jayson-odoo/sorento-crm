"""Join the heads left on main by the #1353 and #1333 merges.

#1353 landed `chatbot_picker_domain_1352` and #1333 landed a chain ending at
`sa2_0005_stock_ask_source` (via `sa2_0004_stock_asks`); both hang off
`cpc4_cost_packaging_method`, so main carried two heads. Schema-free merge
point.

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
