"""The planner flagged a line of this revision as a suspected system problem (R10).

`PLAN-scm-planning-inline-decisions.md` section 3.D5: beside the reason box the decision
editor carries "This might be a system problem, flag it for investigation". The flag is a
SECOND answer beside the verdict - a planner who amends a line because the availability
printed next to it reads wrong is telling us two things, and a decision that recorded only
the amendment lost the one worth chasing.

Per LINE it rides in `so_supply_decisions.line_snapshots`, beside `amend_reason`, which is
where every other per-line word of a decision is frozen. This column is the REVISION's own
answer to "was anything on it flagged": true when any of its lines carries the flag. It
exists so a revision with a doubt on it can be found in SQL without walking a JSONB array,
which is what the investigation listing (deliberately out of scope this round, R10) will
read.

Backfill: every existing revision is false, which is true of all of them - nothing could
have been flagged before the checkbox existed.

Revision ID: 439_decision_suspected_issue
Revises: 438_merge_price_supplier_sets
Create Date: 2026-08-27
"""
import sqlalchemy as sa
from alembic import op

revision = "439_decision_suspected_issue"
#: `main`'s own merge of the two heads this lane started from (#348).
down_revision = "438_merge_price_supplier_sets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "so_supply_decisions",
        sa.Column(
            "suspected_system_issue",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        schema="projects",
    )


def downgrade() -> None:
    op.drop_column("so_supply_decisions", "suspected_system_issue", schema="projects")
