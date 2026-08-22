"""order_inquiry_rows learns po_ref / po_line_id - tag an outstanding PO (PLAN section G).

The captain, 20 Aug: "identify which outstanding PO has quantity to fulfil this order
inquiry, tag it, and the quantity to be ordered is deducted." A deliberate, evidence-
carrying exception on the DEMAND side only - tagging never makes the PO supply
(`on_order_v` still reads `spo_allocations` only, PLAN-scm-purchasing-fulfilment S9). The
lever is the existing one: `committed_v`'s confirmed leg counts `state = 'raised'` rows
only (demand.py), so a new `placed` state removes the demand with no view change.

`po_line_id` targets `public.purchase_order_lines` (the AutoCount supplier PO book), SET
NULL so a purchase order line getting deleted keeps the row's history rather than taking
it down. `po_ref` is the PO NUMBER, printed the way the worklist's own PO column already
is - a denormalised copy rather than a join, for the same reason `stock_location` and
`spo_ref` on this table already are text.

Revision ID: 400_oi_place_on_po
Revises: 399_po_book_aliases
Create Date: 2026-08-20

Chained after `399_po_book_aliases` rather than `397_so_class_from_agent` (both were
authored against the same 397 head by concurrent lanes in this worktree): 399 landed
first in the tree, so this one is rebased onto it to keep a single head rather than
introducing a merge revision for two unrelated, non-overlapping changes.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "400_oi_place_on_po"
down_revision = "399_po_book_aliases"
branch_labels = None
depends_on = None

_SCHEMA = "projects"
_TABLE = "order_inquiry_rows"


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str, schema: str = _SCHEMA) -> bool:
    return _inspector().has_table(name, schema=schema)


def _has_column(table: str, column: str, schema: str = _SCHEMA) -> bool:
    if not _has_table(table, schema=schema):
        return False
    return column in {col["name"] for col in _inspector().get_columns(table, schema=schema)}


def _has_index(table: str, name: str, schema: str = _SCHEMA) -> bool:
    if not _has_table(table, schema=schema):
        return False
    return name in {idx["name"] for idx in _inspector().get_indexes(table, schema=schema)}


def _has_fk(table: str, name: str, schema: str = _SCHEMA) -> bool:
    if not _has_table(table, schema=schema):
        return False
    return name in {
        fk["name"] for fk in _inspector().get_foreign_keys(table, schema=schema)
    }


def upgrade() -> None:
    if not _has_table(_TABLE):
        return

    if not _has_column(_TABLE, "po_ref"):
        op.add_column(
            _TABLE,
            sa.Column("po_ref", sa.String(length=80), nullable=True),
            schema=_SCHEMA,
        )
    if not _has_column(_TABLE, "po_line_id"):
        op.add_column(
            _TABLE,
            sa.Column("po_line_id", UUID(as_uuid=False), nullable=True),
            schema=_SCHEMA,
        )
        op.create_foreign_key(
            "fk_project_order_inquiry_rows_po_line",
            source_table=_TABLE,
            referent_table="purchase_order_lines",
            local_cols=["po_line_id"],
            remote_cols=["id"],
            source_schema=_SCHEMA,
            ondelete="SET NULL",
        )
    if not _has_index(_TABLE, "ix_project_order_inquiry_rows_po_line"):
        op.create_index(
            "ix_project_order_inquiry_rows_po_line",
            _TABLE,
            ["po_line_id"],
            schema=_SCHEMA,
        )


def downgrade() -> None:
    if not _has_table(_TABLE):
        return
    if _has_index(_TABLE, "ix_project_order_inquiry_rows_po_line"):
        op.drop_index("ix_project_order_inquiry_rows_po_line", table_name=_TABLE, schema=_SCHEMA)
    if _has_column(_TABLE, "po_line_id"):
        # The column's presence doesn't imply THIS constraint name exists - a schema
        # built via `create_all` from the model (CI) or a partially-migrated state can
        # name the FK differently, or have none. Guard on the constraint itself; dropping
        # the column still removes any differently-named FK automatically (Postgres drops
        # dependent constraints with the column).
        if _has_fk(_TABLE, "fk_project_order_inquiry_rows_po_line"):
            op.drop_constraint(
                "fk_project_order_inquiry_rows_po_line",
                _TABLE,
                schema=_SCHEMA,
                type_="foreignkey",
            )
        op.drop_column(_TABLE, "po_line_id", schema=_SCHEMA)
    if _has_column(_TABLE, "po_ref"):
        op.drop_column(_TABLE, "po_ref", schema=_SCHEMA)
