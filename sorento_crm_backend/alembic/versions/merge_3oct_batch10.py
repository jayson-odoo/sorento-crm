"""Join the heads left on main by the #1441 and #1439 merges.

#1441 landed `cust_group_0001` hung off `picker_no_cap_0001`; #1439 then landed
`rpl_0001_regions`, whose down_revision is the same `picker_no_cap_0001`, so main
carried two heads. Schema-free merge point.

Revision ID: merge_3oct_batch10
Revises: cust_group_0001, rpl_0001_regions
"""
from __future__ import annotations

revision = "merge_3oct_batch10"
down_revision = ("cust_group_0001", "rpl_0001_regions")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
