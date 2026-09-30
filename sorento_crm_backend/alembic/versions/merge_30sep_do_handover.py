"""Join the two heads main carried after #1383 (`do_pull_0001_perm`, hung off
`lsa_0001_show_all_counts`) merged beside `rs_0001_stock_ask_referred`, so this lane's
own `oihr_0004_wide_line_table` can hang off one head. Schema-free merge point.

Revision ID: merge_30sep_do_handover
Revises: do_pull_0001_perm, rs_0001_stock_ask_referred
Create Date: 2026-09-30
"""
from __future__ import annotations

revision = "merge_30sep_do_handover"
down_revision = ("do_pull_0001_perm", "rs_0001_stock_ask_referred")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
