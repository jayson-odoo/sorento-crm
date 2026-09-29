"""Join the heads left on main by the #1304 merge.

#1350 landed `eml_0001_layout_columns` -> `eml_0002_seed_layouts` hung off
`merge_29sep_batch6`; #1304 then landed `mem_0001_frames_level` ->
`mem_0002_parser_memory` -> `mem_0003_parser_history`, whose first revision
also hangs off `merge_29sep_batch6`, so main carried two heads. Schema-free
merge point; `527_committed_v_uncapped` (#1145) chains onto it.

Revision ID: merge_29sep_batch7
Revises: eml_0002_seed_layouts, mem_0003_parser_history
"""
from __future__ import annotations

revision = "merge_29sep_batch7"
down_revision = ("eml_0002_seed_layouts", "mem_0003_parser_history")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
