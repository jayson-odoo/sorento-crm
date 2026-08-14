"""Join the Container Status lineage with the spec-authoring lineage.

No DDL. A merge revision only joins two lineages so `alembic upgrade head` has ONE
head to aim at.

**What happened.** `322_merge_dealer_kit_customers` was the single head when both
branches were cut, and both chained onto it correctly:

    322_merge_dealer_kit_customers
      |-- 323_cs_company_backfill        (#145, container status per-company)
      `-- 356_human_source_boost_seed    (#144, authored spec writes)

Neither revision is wrong, and neither review could have caught it: each branch had
exactly one head while it was open. The fork exists only in the merged result, and it
appeared the moment the second PR landed - #145 merged at 8bfa434b, #144 at abb0c7c1
about an hour later, on a base whose head had moved underneath it.

**Why it is a broken deploy rather than a warning.** CI's `bootstrap_env` job and
`alembic upgrade head` both abort with "Multiple heads are present", which took out
`Backend test suite (Postgres)` and `Dealer Kit PDF render (real browser)` on run
31804888999 before a single test ran. Nothing about either feature is at fault, so
neither log names anything you could go and read.

Fixed forward with a merge revision rather than by editing either landed revision:
both have run on deployed databases, and rewriting a revision that is already in
somebody's `alembic_version` is how you get two environments that disagree about what
has been applied.

**The id is 31 characters, and that is a constraint rather than a preference.**
`scripts/bootstrap_env.py` builds the schema from the ORM models and then calls
`command.stamp(cfg, "head")`, which INSERTs the head revision id into an
`alembic_version` table Alembic has just created with `version_num varchar(32)`.
Migration `103b_widen_alembic_version_num` widens that column to 255, but it never
runs on the stamp path, so a head id longer than 32 characters aborts the bootstrap
with StringDataRightTruncation. Any future head must stay <= 32.

Revision ID: 360_merge_container_status_spec
Revises: 323_cs_company_backfill, 356_human_source_boost_seed
"""

revision = "360_merge_container_status_spec"
down_revision = ("323_cs_company_backfill", "356_human_source_boost_seed")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing to do. A merge revision only joins two lineages."""


def downgrade() -> None:
    """Nothing to undo. Downgrading past this re-forks the graph, which is correct:
    the two lineages genuinely are independent below this point."""
