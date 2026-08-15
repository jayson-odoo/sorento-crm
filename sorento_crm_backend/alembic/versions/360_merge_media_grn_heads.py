"""Join the chatbot-media head with the GRN/main merge head.

No DDL. A merge revision only joins lineages so `alembic upgrade head` has ONE
head to aim at.

Two independent lanes are live at this point:

    357_merge_grn_spo_fm_heads (main: GRN forward-matching merged with main's
                                container-status and spec-search lanes)
    359_media_voice_degraded   (this branch: chatbot media endpoint chain,
                                356 -> 357_chatbot_media_permissions -> 358 -> 359,
                                hanging off 885010d94677)

Neither is an ancestor of the other - the media chain forked before the GRN
lane landed on main - so CI's `bootstrap_env` `command.stamp(cfg, "head")` and
`alembic upgrade head` both fail with "Multiple heads are present" until they
are joined.

The id is 25 characters: `scripts/bootstrap_env.py` stamps the head into an
`alembic_version` table created with `version_num varchar(32)`, so any head id
must stay <= 32 (see 322's docstring).
"""

revision = "360_merge_media_grn_heads"
down_revision = (
    "357_merge_grn_spo_fm_heads",
    "359_media_voice_degraded",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""


def downgrade() -> None:
    """Nothing to undo. Downgrading past this re-forks the graph, which is
    correct: the two lineages genuinely are independent below this point."""
