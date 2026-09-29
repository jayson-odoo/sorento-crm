"""Join the heads left on main by the #833 merge.

#1358 landed `merge_29sep_batch4` (joining `sales_agent_aliases_r7` and
`scm_reorder_run_scope_desc`); #833 then landed a chain ending at
`spk_0002_colour_word_spec` hung off `sales_agent_aliases_r7`, so main
carried two heads. Schema-free merge point.

Revision ID: merge_29sep_batch5
Revises: merge_29sep_batch4, spk_0002_colour_word_spec
"""
from __future__ import annotations

revision = "merge_29sep_batch5"
down_revision = ("merge_29sep_batch4", "spk_0002_colour_word_spec")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
