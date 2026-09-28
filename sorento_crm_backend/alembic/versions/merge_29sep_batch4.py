"""Join the heads left on main by the #1342 merge.

#1273 moved main's head to `sales_agent_aliases_r7`; #1342 then landed
`scm_reorder_run_scope_desc` chained on `merge_28sep_batch3`, so main
carried two heads. Schema-free merge point.

Revision ID: merge_29sep_batch4
Revises: sales_agent_aliases_r7, scm_reorder_run_scope_desc
"""
from __future__ import annotations

revision = "merge_29sep_batch4"
down_revision = ("sales_agent_aliases_r7", "scm_reorder_run_scope_desc")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
