"""Fulfilment priority policy: reorder coverage until date, replacing buy_all_horizon_days.

19 Aug follow-up (captain, live on the demo): "purchasing reorders until October, for
example - anything beyond that is suggested to buy immediately." A ROLLING day count
answers a different question than the one the captain asked - it cannot express "cover
demand through a fixed calendar date" without the planner recomputing the day gap by
hand every time today changes. So `scm.priority_policy.buy_all_horizon_days` (an
INTEGER count of days, added by migration ed706a98ddc6) is replaced outright by
`reorder_coverage_until` (a nullable DATE): a line due AFTER this date is proposed as
`Buy now`, untouched; NULL means no coverage limit is set (nothing is auto-forced to
Buy now on horizon grounds alone). This slice still does not wire the setting into
scoring - the ladder (workstream E) is the eventual reader, same as the column it
replaces.

Upgrade adds the new column and drops the old one outright, rather than backfilling a
date from the old day count: `buy_all_horizon_days` was a ROLLING offset from "today",
so no single date it ever pointed at survives being turned into a migration-time
constant - the only honest value for every existing row is NULL, unset, which is
also `ADD COLUMN ... DEFAULT NULL`'s natural answer.

Downgrade restores `buy_all_horizon_days` with its original default (180, migration
ed706a98ddc6's literal) and drops `reorder_coverage_until` - the reverse loses the
planner's chosen date the same way the upgrade cannot recover a day count from it,
which is what a downgrade after this feature shipped is expected to cost.

Revision ID: 394_reorder_coverage_until
Revises: 393_extractor_page_text
Create Date: 2026-08-19 22:58:57.358184

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '394_reorder_coverage_until'
down_revision = '393_extractor_page_text'
branch_labels = None
depends_on = None

#: The default `buy_all_horizon_days` carried (migration ed706a98ddc6's literal),
#: restored on downgrade. Repeated here rather than imported so this migration stays
#: standalone (same rule 385 and ed706a98ddc6 state).
_BUY_ALL_HORIZON_DAYS_DEFAULT = 180


def _has_table(bind, table: str, schema: str | None = None) -> bool:
    return sa.inspect(bind).has_table(table, schema=schema)


def _columns(insp, table: str, schema: str | None = None) -> set[str]:
    return {c["name"] for c in insp.get_columns(table, schema=schema)}


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not _has_table(bind, "priority_policy", schema="scm"):
        return
    present = _columns(insp, "priority_policy", schema="scm")

    if "reorder_coverage_until" not in present:
        op.add_column(
            "priority_policy",
            sa.Column("reorder_coverage_until", sa.Date(), nullable=True),
            schema="scm",
        )
    if "buy_all_horizon_days" in present:
        op.drop_column("priority_policy", "buy_all_horizon_days", schema="scm")


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not _has_table(bind, "priority_policy", schema="scm"):
        return
    present = _columns(insp, "priority_policy", schema="scm")

    if "buy_all_horizon_days" not in present:
        op.add_column(
            "priority_policy",
            sa.Column(
                "buy_all_horizon_days", sa.Integer(), nullable=False,
                server_default=sa.text(str(_BUY_ALL_HORIZON_DAYS_DEFAULT)),
            ),
            schema="scm",
        )
    if "reorder_coverage_until" in present:
        op.drop_column("priority_policy", "reorder_coverage_until", schema="scm")
