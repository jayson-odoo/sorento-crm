"""Merge the three heads left on main by the 27 Sep merges (#1279, #1247, #1292).

All three branch from `sales_0002_team_leader`. Schema-free merge point.

Revision ID: merge_27sep_three_heads
Revises: ideation_confirm_prompts, sa2_r9_open_question, prod_discontinued_at_flt
"""
from __future__ import annotations

revision = "merge_27sep_three_heads"
down_revision = ("ideation_confirm_prompts", "sa2_r9_open_question", "prod_discontinued_at_flt")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
