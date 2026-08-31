"""Fulfilment priority: transfer_days becomes a policy setting, default 0.

S2 of `PLAN-scm-planning-feedback-31aug.md`, R-B.

`front_planning_engine.TRANSFER_DAYS` was a literal (`= 2`), charged on any option whose
stock is not already at the asking line's own location. The captain's 31 Aug ruling
retires it: the charge is configurable, default 0, so an unconfigured install charges
nothing and "Take from the pool" fulfils the same day as "Use our locations" whenever the
two bins are the same distance apart in practice.

`scm.priority_policy.transfer_days` (integer, not null, default 0) - one preference, one
column, on the row `app.services.scm.priority` already reads for `tba_date_from` and
`reorder_coverage_until`.

Hand-written and guarded with an `IF NOT EXISTS` check, for the reason 443 and 450 state:
the shared dev database is a prod copy whose `alembic_version` points at another lane's
head, so this is applied there by hand and re-running it has to be a no-op rather than a
failure.

Revision ID: 451_transfer_days
Revises: 450_spec_rules_readable
"""
import sqlalchemy as sa
from alembic import op

revision = "451_transfer_days"
down_revision = "450_spec_rules_readable"
branch_labels = None
depends_on = None


def _columns(table: str, schema: "str | None" = None) -> set:
    bind = op.get_bind()
    return {
        column["name"]
        for column in sa.inspect(bind).get_columns(table, schema=schema)
    }


def upgrade() -> None:
    if "transfer_days" not in _columns("priority_policy", schema="scm"):
        op.add_column(
            "priority_policy",
            sa.Column(
                "transfer_days",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            schema="scm",
        )


def downgrade() -> None:
    if "transfer_days" in _columns("priority_policy", schema="scm"):
        op.drop_column("priority_policy", "transfer_days", schema="scm")
