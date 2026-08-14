"""Collapse the two heads that merging main into the Dealer Kit branch created.

No DDL. This exists solely so `alembic upgrade head` has ONE head to aim at.

Merging `origin/main` brought in `310_form_sla_skip_stage`, whose ancestry runs
through `309_merge_status_engine`. The Dealer Kit chain runs 311 to 318 off a
DIFFERENT 309 (`309_dealer_kit_module`). Neither is an ancestor of the other, so
after the merge the migration graph had two heads:

    310_form_sla_skip_stage     (form SLA skip stage, from main)
    318_dealer_kit_edition      (the Edition graph, this branch)

Two heads is not a warning, it is a broken deploy: `alembic upgrade head` fails
with "Multiple head revisions are present" and the container never starts. The
symptom appears at deploy time, on a branch whose tests were all green, which is
why this repo already carries the lesson - a git merge of two branches that each
added migrations forks the revision graph, and the fork has to be closed
explicitly.

Verified single-head after this file: the graph walk over
`alembic/versions/*.py` reports exactly one head, `319_merge_dealer_kit_form_sla`.

The id is kept under 32 characters on purpose: `scripts/bootstrap_env.py` stamps
the head into a freshly created `alembic_version`, whose `version_num` is
`varchar(32)` until migration `103b` widens it - and that migration never runs on
the stamp path. A longer id fails the bootstrap with StringDataRightTruncation.
"""

revision = "319_merge_dealer_kit_form_sla"
down_revision = ("310_form_sla_skip_stage", "318_dealer_kit_edition")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing to do. A merge revision only joins two lineages."""


def downgrade() -> None:
    """Nothing to undo. Downgrading past this re-forks the graph, which is
    correct: the two lineages genuinely are independent below this point."""
