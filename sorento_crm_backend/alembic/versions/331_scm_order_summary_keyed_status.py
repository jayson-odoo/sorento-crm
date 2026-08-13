"""SCM: record whether a decided purchase order has been keyed into AutoCount.

AC-E2.2: the status is MANUAL, because nothing can detect it. No AutoCount integration
exists, so the person doing the keying is the only source of truth about whether it has
been done, and the alternative is a worklist that cannot tell a keyed row from an unkeyed
one - which is the whole job of the screen.

Three values (AC-E2.2 states them as the minimum). The middle one is load-bearing rather
than decorative: `keying` is what stops two people keying the same purchase order, which
is the failure a shared queue produces on day one.

It lives on `scm.order_summary_row` rather than in a table of its own because the grain is
identical - one decided product per run - and a second table keyed the same way would only
add a join and a way for the two to disagree about which rows exist.

`keyed_status` is NOT NULL with a default so every existing decided row starts as not
keyed, which is the truth: nothing has been keyed through this screen yet. `keyed_by` and
`keyed_at` stay nullable and move together with the first change; `keyed_by` is a human
NAME, not a user id, because it is rendered beside the row.

Revision ID: 331_scm_order_summary_keyed_status
Revises: 330_scm_order_summary_row
"""
from alembic import op
import sqlalchemy as sa


revision = "331_scm_order_summary_keyed_status"
down_revision = "330_scm_order_summary_row"
branch_labels = None
depends_on = None

_KEYED_STATUSES = ("not_keyed", "keying", "keyed")


def _columns(bind, table: str, schema: str = "scm") -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns(table, schema=schema)}


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("order_summary_row", schema="scm"):
        return
    existing = _columns(bind, "order_summary_row")
    if "keyed_status" not in existing:
        op.add_column(
            "order_summary_row",
            sa.Column(
                "keyed_status",
                sa.String(20),
                nullable=False,
                server_default="not_keyed",
            ),
            schema="scm",
        )
        # A CHECK rather than a lookup table: three values fixed by the acceptance criteria,
        # with no attributes of their own and nothing to configure. A typo'd status would
        # otherwise render as an unknown pill and filter to nothing.
        op.create_check_constraint(
            "ck_scm_order_summary_row_keyed_status",
            "order_summary_row",
            "keyed_status IN ('not_keyed', 'keying', 'keyed')",
            schema="scm",
        )
        # Filtering to not-keyed is the primary use of the worklist (AC-E2.4), and it is
        # always scoped to one run, so the index pairs the two.
        op.create_index(
            "ix_scm_order_summary_row_run_keyed",
            "order_summary_row",
            ["run_id", "keyed_status"],
            schema="scm",
        )
    if "keyed_by" not in existing:
        op.add_column(
            "order_summary_row",
            sa.Column("keyed_by", sa.String(), nullable=True),
            schema="scm",
        )
    if "keyed_at" not in existing:
        op.add_column(
            "order_summary_row",
            sa.Column("keyed_at", sa.DateTime(timezone=False), nullable=True),
            schema="scm",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("order_summary_row", schema="scm"):
        return
    existing = _columns(bind, "order_summary_row")
    for column in ("keyed_at", "keyed_by"):
        if column in existing:
            op.drop_column("order_summary_row", column, schema="scm")
    if "keyed_status" in existing:
        op.drop_index(
            "ix_scm_order_summary_row_run_keyed",
            table_name="order_summary_row",
            schema="scm",
        )
        op.drop_constraint(
            "ck_scm_order_summary_row_keyed_status",
            "order_summary_row",
            type_="check",
            schema="scm",
        )
        op.drop_column("order_summary_row", "keyed_status", schema="scm")
