"""Join the conversation-intervention-tickets lane with main's SCM head.

No DDL. A merge revision only joins lineages so `alembic upgrade head` has ONE
head to aim at.

Two heads exist after merging main into this branch:

    358_scm_po_spo_history_aliases (main: SCM purchase-history aliases lane)
    330_conversations_inbox        (this branch: conversations inbox + perms,
                                    tail of the 321..330 intervention-ticket lane)

The two lanes are independent below this point: the intervention-ticket chain
hangs off `320_dealer_kit_tile_template` era work and grew while main advanced
through the dealer-kit, container-status, GRN and SCM lanes. Neither is an
ancestor of the other, so the git merge leaves the alembic graph forked even
though the Python merged cleanly.

Two heads is not a warning, it is a broken deploy: CI's `bootstrap_env` job
stamps a single head and `alembic upgrade head` refuses to guess. That is
exactly how this surfaced - the PR merge commit failed CI on
"Multiple heads are present; please specify a single target revision".

The id is 22 characters: `scripts/bootstrap_env.py` stamps the head into an
`alembic_version` table created with `version_num varchar(32)` (see 322's
docstring), so any head id must stay <= 32.
"""

revision = "359_merge_tickets_main"
down_revision = (
    "358_scm_po_spo_history_aliases",
    "330_conversations_inbox",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""


def downgrade() -> None:
    """Nothing to undo. Downgrading past this re-forks the graph, which is
    correct: the two lineages genuinely are independent below this point."""
