"""Fulfilment priority: overdue_grace_days + overdue_dead_days (R-O, #586).

S4 of `PLAN-scm-pool-chain-first.md`, ruling R-O (captain, 3 Sep 2026): "overdue yeah we
can have a grace period". R31 counted an overdue document as nothing at all, and on
SO419417 that left the ladder lending 4 units off the 11 standing at BRW while 725 SPO
units dated 24 July and 6 August sat unreceived. The display was right and the engine was
ignoring a late document.

`overdue_grace_days` (integer, not null, default 14) - a document whose arrival has passed
counts as supply on its outstanding balance, landing on `today + this`, so a line due before
that day still gets nothing from it.

`overdue_dead_days` (integer, not null, default 90) - past this much lateness the document
counts as nothing at all, which is R31 kept for the dead.

Both join `scm.priority_policy` beside `immediate_window_days` / `pool_share_pct` rather
than a new table, for the reason 460 states: one policy, activated as a whole, so a planner
tuning the grace cannot leave it pointing at a different revision than the rest of the row.

Hand-written and guarded with an `IF NOT EXISTS` check, for the reason 443/450/452/460/461/463
state: the shared dev database is a prod copy whose `alembic_version` points at another
lane's head, so this is applied there by hand and re-running it has to be a no-op rather
than a failure.

Revision ID: 464_overdue_grace
Revises: 463_draft_proposed
"""
import sqlalchemy as sa
from alembic import op

revision = "464_overdue_grace"
down_revision = "463_draft_proposed"
branch_labels = None
depends_on = None


def _columns(table: str, schema: "str | None" = None) -> set:
    bind = op.get_bind()
    return {
        column["name"]
        for column in sa.inspect(bind).get_columns(table, schema=schema)
    }


def upgrade() -> None:
    existing = _columns("priority_policy", schema="scm")
    if "overdue_grace_days" not in existing:
        op.add_column(
            "priority_policy",
            sa.Column(
                "overdue_grace_days",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("14"),
            ),
            schema="scm",
        )
    if "overdue_dead_days" not in existing:
        op.add_column(
            "priority_policy",
            sa.Column(
                "overdue_dead_days",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("90"),
            ),
            schema="scm",
        )


def downgrade() -> None:
    existing = _columns("priority_policy", schema="scm")
    if "overdue_dead_days" in existing:
        op.drop_column("priority_policy", "overdue_dead_days", schema="scm")
    if "overdue_grace_days" in existing:
        op.drop_column("priority_policy", "overdue_grace_days", schema="scm")
