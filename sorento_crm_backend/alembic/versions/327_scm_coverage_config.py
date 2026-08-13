"""SCM S3: Coverage Timeline config columns, and a re-emit of scm.on_order_v.

Three nullable columns on ``scm.reorder_policy``. That table is the right home rather than a
new one: it already carries scope resolution (``scope_type`` / ``scope_ref`` / ``priority``)
and an admin UI, so a per-warehouse or per-category override of any of these comes free
instead of needing new plumbing.

  * ``planning_horizon_months`` - how far ahead the dated coverage axis runs. Bounding the
    axis is necessary (a ten-year demand tail makes the report unreadable) and the figure
    had no source anywhere. NULL resolves to 6 in code.
  * ``transfer_lead_time_days`` and ``transfer_cost_per_unit`` - what makes a cross-site
    transfer proposal a judgement rather than a free win. Both stay NULL when unconfigured
    and are NEVER defaulted to 0: a zero cost reads as a free move and a zero lead time as
    an instant one, so either would make a proposal look better than the truth.

Nothing is seeded. An unconfigured tenant is a real state with a correct answer (the code
default for the horizon, "unknown" for the transfer economics), so seeding a row here would
only invent figures nobody chose. That also means ``scripts/bootstrap_env`` needs no new
data step for this revision: the columns come from the ORM model, which ``create_all``
emits.

**Why this also re-emits ``scm.on_order_v``.** 311 gave the view a
``purchase_order_lines.line_status = 'open'`` predicate by editing its own DDL constant, but
311 had already been stamped on some databases by then. Those databases keep the OLD
definition forever, so "on order" would mean one thing on one environment and another on
the next, and the Coverage Timeline (which now applies the same predicate) would agree with
the dashboard on one and contradict it on the other. Re-emitting from 311's own
``_ON_ORDER_V`` constant, imported rather than restated, makes the two impossible to drift.

Revision ID: 327_scm_coverage_config
Revises: 311_scm_purchasing_base
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic import op


revision = "327_scm_coverage_config"
down_revision = "311_scm_purchasing_base"
branch_labels = None
depends_on = None


def _load_311():
    """311's module, for its view DDL constant.

    Loaded by path because alembic revision files are not importable as a package. The
    migrations only touch ``alembic.op`` inside functions, so importing one for a
    module-level constant runs no DDL.
    """
    spec = importlib.util.spec_from_file_location(
        "_scm_327_base", Path(__file__).resolve().parent / "311_scm_purchasing_base.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# 311 is the single source of truth for this definition; this revision only guarantees it
# is actually in place. Exposed as a module-level constant in the same shape 311 uses so
# `scripts/bootstrap_env` can replay it in revision order (last write wins).
_REDEFINED_VIEWS = (_load_311()._ON_ORDER_V,)

_NEW_COLUMNS = (
    ("planning_horizon_months", sa.Integer()),
    ("transfer_lead_time_days", sa.Integer()),
    ("transfer_cost_per_unit", sa.Numeric(12, 2)),
)


def _has_table(bind, table: str, schema: str = "public") -> bool:
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = :s AND table_name = :t"
            ),
            {"s": schema, "t": table},
        ).scalar()
    )


def _has_column(bind, table: str, column: str, schema: str = "public") -> bool:
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = :s AND table_name = :t AND column_name = :c"
            ),
            {"s": schema, "t": table, "c": column},
        ).scalar()
    )


def upgrade() -> None:
    bind = op.get_bind()

    if _has_table(bind, "reorder_policy", schema="scm"):
        for name, type_ in _NEW_COLUMNS:
            if not _has_column(bind, "reorder_policy", name, schema="scm"):
                op.add_column(
                    "reorder_policy",
                    sa.Column(name, type_, nullable=True),
                    schema="scm",
                )

    # CREATE OR REPLACE rather than DROP + CREATE: net_position_v selects from this view
    # and dropping it would take that (and every consumer of it) with it. Replacing in
    # place keeps the column list identical, which is the only thing REPLACE requires.
    for ddl in _REDEFINED_VIEWS:
        op.execute(ddl.replace("CREATE VIEW", "CREATE OR REPLACE VIEW", 1))


def downgrade() -> None:
    bind = op.get_bind()

    # The view is deliberately NOT reverted. Its pre-311 definition counted closed PO lines
    # as incoming supply forever, and reinstating that on a downgrade would silently
    # overstate supply and suppress purchases. Dropping columns is reversible; publishing a
    # known-wrong figure is not.
    if _has_table(bind, "reorder_policy", schema="scm"):
        for name, _type in reversed(_NEW_COLUMNS):
            if _has_column(bind, "reorder_policy", name, schema="scm"):
                op.drop_column("reorder_policy", name, schema="scm")
