"""Join the heads left on main by #1353 and #1333.

Both chained onto `cpc4_cost_packaging_method`: #1353 with
`chatbot_picker_domain_1352`, #1333 with `sa2_0004_stock_asks` ->
`sa2_0005_stock_ask_source`, so main carried two heads. Schema-free merge point,
added by #1356 so its own migration has one head to chain onto.

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
