"""Merge the heads left on main by the second 28 Sep migration batch.

#1296 and #1299 each chained on `merge_28sep_batch2`; after both landed
main carried these heads. Schema-free merge point.

Revision ID: merge_28sep_batch3
Revises: aud_0002_audit_trail_gaps, sales_0005_opp_line_price
"""
from __future__ import annotations

revision = "merge_28sep_batch3"
down_revision = ("aud_0002_audit_trail_gaps", "sales_0005_opp_line_price")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
