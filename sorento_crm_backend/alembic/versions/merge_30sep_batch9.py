"""Join the heads left on main by the #1383 and #1386 merges.

#1386 landed `rs_0001_stock_ask_referred` hung off `lsa_0001_show_all_counts`
(#1382); #1383 then landed `do_pull_0001_perm`, whose down_revision is the same
`lsa_0001_show_all_counts`, so main carried two heads. Schema-free merge point.

Revision ID: merge_30sep_batch9
Revises: do_pull_0001_perm, rs_0001_stock_ask_referred
"""
from __future__ import annotations

revision = "merge_30sep_batch9"
down_revision = ("do_pull_0001_perm", "rs_0001_stock_ask_referred")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
