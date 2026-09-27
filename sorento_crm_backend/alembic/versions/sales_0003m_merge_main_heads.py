"""Merge the three heads origin/main carried at d8395cb8 with the sales S1 + S2 chain.

origin/main at d8395cb8 has three heads, each on `sales_0002_team_leader`
(`ideation_confirm_prompts`, `prod_discontinued_at_flt`, `sa2_r9_open_question`); the sales
lane adds a fourth (`sales_0003_opportunities`). No schema change.

Revision ID: sales_0003m_merge_main_heads
Revises: sales_0003_opportunities, ideation_confirm_prompts, prod_discontinued_at_flt, sa2_r9_open_question
Create Date: 2026-09-27
"""

revision = "sales_0003m_merge_main_heads"
down_revision = (
    "sales_0003_opportunities",
    "ideation_confirm_prompts",
    "prod_discontinued_at_flt",
    "sa2_r9_open_question",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
