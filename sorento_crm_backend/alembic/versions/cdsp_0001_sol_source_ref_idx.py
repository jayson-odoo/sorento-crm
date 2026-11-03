"""Index sales_order_lines (source_ref) (CONFIRM-DIALOG-SPEED PR 2).

``documentation/plans/fulfilment/PLAN-confirm-dialog-speed-3nov.md``. `_oi_placements` (the
order inquiry's SPO placements behind Stock Debt's landed holds and the board's PO-received
read) looks SO lines up by `source_ref`; on the prod clone the table holds 869k rows and the
column had no index (crew profile, 3 Nov 2026). Same build shape as sodv_0001: CONCURRENTLY,
bounded lock wait, an INVALID leftover dropped and rebuilt. Additive only.

Revision ID: cdsp_0001_sol_source_ref_idx
Revises: sask_0002_span_supplier
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "cdsp_0001_sol_source_ref_idx"
down_revision = "sask_0002_span_supplier"
branch_labels = None
depends_on = None

INDEX = "ix_sales_order_lines_source_ref"
INDEX_LOCK_TIMEOUT = "30s"


def _index_valid(bind):
    """pg_index.indisvalid for the index (True / False), or None when there is none."""
    return bind.execute(
        sa.text(
            "SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
            "WHERE i.indrelid = 'sales_order_lines'::regclass AND c.relname = :name"
        ),
        {"name": INDEX},
    ).scalar()


def _ensure_index(bind, *, concurrently: bool) -> None:
    """Build the index unless a VALID one exists; drop an INVALID leftover of a failed
    CONCURRENTLY build first, which IF NOT EXISTS would otherwise keep forever."""
    if _index_valid(bind) is True:
        return
    c = "CONCURRENTLY" if concurrently else ""
    if _index_valid(bind) is False:
        bind.execute(sa.text(f"DROP INDEX {c} IF EXISTS {INDEX}"))
    bind.execute(
        sa.text(f"CREATE INDEX {c} IF NOT EXISTS {INDEX} ON sales_order_lines (source_ref)")
    )
    if _index_valid(bind) is not True:
        raise RuntimeError(
            f"cdsp_0001: index {INDEX} is INVALID after the build; drop it and rerun."
        )


def upgrade():
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction.
    with op.get_context().autocommit_block():
        bind = op.get_bind()
        previous = bind.execute(sa.text("SELECT current_setting('lock_timeout')")).scalar()
        bind.execute(sa.text(f"SET lock_timeout = '{INDEX_LOCK_TIMEOUT}'"))
        try:
            _ensure_index(bind, concurrently=True)
        finally:
            bind.execute(sa.text("SELECT set_config('lock_timeout', :v, false)"), {"v": previous})


def downgrade():
    with op.get_context().autocommit_block():
        op.get_bind().execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX}"))
