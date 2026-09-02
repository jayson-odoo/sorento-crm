"""Fulfilment priority: immediate_window_days + pool_share_pct settings.

S1 of `PLAN-scm-fulfilment-feedback-2sep.md`, ruling R-B.

The BRW-first share step S2 wires into the walk needs two numbers, and per the plan they
join `scm.priority_policy` beside `transfer_days` / `tba_date_from` / `reorder_coverage_until`
rather than a new table: one policy, activated as a whole, so a planner tuning the share
cannot leave it pointing at a different revision than the rest of the row.

`immediate_window_days` (integer, not null, default 30) - how many days out a line counts as
"immediate" for the pool's share step; beyond it a line takes the whole allowance or nothing.

`pool_share_pct` (integer, not null, default 50) - percent of the site pool's free pile kept
back for dealers before a project line may take a share.

Hand-written and guarded with an `IF NOT EXISTS` check, for the reason 443/450/452 state: the
shared dev database is a prod copy whose `alembic_version` points at another lane's head, so
this is applied there by hand and re-running it has to be a no-op rather than a failure.

Revision ID: 460_fulfilment_immediate_share
Revises: 456_reorder_perf_quickwins
"""
import sqlalchemy as sa
from alembic import op

revision = "460_fulfilment_immediate_share"
down_revision = "456_reorder_perf_quickwins"
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
    if "immediate_window_days" not in existing:
        op.add_column(
            "priority_policy",
            sa.Column(
                "immediate_window_days",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("30"),
            ),
            schema="scm",
        )
    if "pool_share_pct" not in existing:
        op.add_column(
            "priority_policy",
            sa.Column(
                "pool_share_pct",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("50"),
            ),
            schema="scm",
        )


def downgrade() -> None:
    existing = _columns("priority_policy", schema="scm")
    if "pool_share_pct" in existing:
        op.drop_column("priority_policy", "pool_share_pct", schema="scm")
    if "immediate_window_days" in existing:
        op.drop_column("priority_policy", "immediate_window_days", schema="scm")
