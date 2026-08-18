"""SCM: the keyed-into-AutoCount status of a LOCATION-grain decision.

Migration 331 put `keyed_status` / `keyed_by` / `keyed_at` on `scm.order_summary_row`,
which is one decided product per run - the right grain for a run decided at PRODUCT
grain. A run decided at LOCATION grain (plan 5.4, admin policy `plan_grain`) keeps its
decisions on `scm.reorder_recommendation` instead, one per (product, warehouse), and its
product summary row is a read-only aggregate that never carries a chosen quantity. So
under that grain there was nowhere to record that ONE location's order had been keyed:
the write 404'd on the aggregate row, and where it did land, one status covered every
location of the product, so keying WH-A silently keyed WH-B.

The same three columns, at the grain the decision actually lives at. Semantics are the
ones 331 states: NOT NULL with a `not_keyed` default so every existing decision starts
unkeyed (the truth), `keying` load-bearing as the lock between two people, `keyed_by` a
human NAME. The two tables never both apply to one run: `po_worklist` reads exactly the
run's own grain (AC-F09), so there is no row for the two statuses to disagree on.

Revision ID: 387_scm_reco_keyed_status
Revises: 386_merge_discontinued_scopes
"""
from alembic import op
import sqlalchemy as sa


revision = "387_scm_reco_keyed_status"
down_revision = "386_merge_discontinued_scopes"
branch_labels = None
depends_on = None

_TABLE = "reorder_recommendation"
_SCHEMA = "scm"


def _columns(bind) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns(_TABLE, schema=_SCHEMA)}


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(_TABLE, schema=_SCHEMA):
        return
    existing = _columns(bind)
    if "keyed_status" not in existing:
        op.add_column(
            _TABLE,
            sa.Column(
                "keyed_status",
                sa.String(20),
                nullable=False,
                server_default="not_keyed",
            ),
            schema=_SCHEMA,
        )
        op.create_check_constraint(
            "ck_scm_reorder_recommendation_keyed_status",
            _TABLE,
            "keyed_status IN ('not_keyed', 'keying', 'keyed')",
            schema=_SCHEMA,
        )
        op.create_index(
            "ix_scm_reorder_recommendation_run_keyed",
            _TABLE,
            ["run_id", "keyed_status"],
            schema=_SCHEMA,
        )
    if "keyed_by" not in existing:
        op.add_column(
            _TABLE, sa.Column("keyed_by", sa.String(), nullable=True), schema=_SCHEMA
        )
    if "keyed_at" not in existing:
        op.add_column(
            _TABLE,
            sa.Column("keyed_at", sa.DateTime(timezone=False), nullable=True),
            schema=_SCHEMA,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(_TABLE, schema=_SCHEMA):
        return
    existing = _columns(bind)
    for column in ("keyed_at", "keyed_by"):
        if column in existing:
            op.drop_column(_TABLE, column, schema=_SCHEMA)
    if "keyed_status" in existing:
        op.drop_index(
            "ix_scm_reorder_recommendation_run_keyed", table_name=_TABLE, schema=_SCHEMA
        )
        op.drop_constraint(
            "ck_scm_reorder_recommendation_keyed_status",
            _TABLE,
            type_="check",
            schema=_SCHEMA,
        )
        op.drop_column(_TABLE, "keyed_status", schema=_SCHEMA)
