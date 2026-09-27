"""Collapse main's three heads so the chatbot memory lane's migrations have ONE parent.

No DDL. This exists solely so `alembic upgrade head` has ONE head to aim at.

When the memory lane merged main (d8395cb8, 27 Sep 2026), main itself carried three
heads, each branched off `sales_0002_team_leader` by a separate PR:

    ideation_confirm_prompts  (#1279, over ideation_reply_fmt_prompts)
    sa2_r9_open_question      (#1247)
    prod_discontinued_at_flt  (#1292)

None of them is edited here (they are main's). The lane's own chain,
`mem_0001_frames_level` -> `mem_0002_parser_memory`, hangs off this revision instead.

The id stays <= 32 characters: `scripts/bootstrap_env.py` stamps the head into an
`alembic_version.version_num varchar(32)` column (see `321_merge_dealer_kit_main`).

Revision ID: mem_0000_merge_main
Revises: ideation_confirm_prompts, prod_discontinued_at_flt, sa2_r9_open_question
"""

revision = "mem_0000_merge_main"
down_revision = ("ideation_confirm_prompts", "prod_discontinued_at_flt", "sa2_r9_open_question")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""


def downgrade() -> None:
    """Nothing to undo. Downgrading past this re-forks the graph, which is correct:
    the three lineages genuinely are independent below this point."""
