"""Migration `ac_grn_do_0001_ingest` (#1354 S2): up, down, up (AC-AG070).

Adds the `branches` table and the AutoCount identity, typed and link columns to `orders`,
`order_lines`, `picking_headers` and `picking_lines`. The DDL runs on the real tables inside
an outer transaction that is rolled back, so nothing survives the test. Named
`test_migration_*.py`: CI runs it in the serial migration pass.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.database import engine

VERSIONS = (Path(__file__).resolve().parent / ".." / "alembic" / "versions").resolve()
REVISION = "ac_grn_do_0001_ingest"

NEW_COLUMNS = {
    "orders": {"source_book", "doc_key", "source_modified_at", "source_vanished_at",
               "last_synced_at", "source_record", "branch_code", "branch_name",
               "deliver_address", "deliver_contact", "deliver_phone", "ship_via", "ship_info",
               "ref", "ref_doc_no", "sales_order_id", "description", "doc_status",
               "currency_code", "currency_rate", "local_net_total"},
    "order_lines": {"dtl_key", "item_code", "location_code", "description", "foc_qty", "uom",
                    "discount_text", "batch_no", "delivery_date", "proj_no", "your_po_no",
                    "your_po_date", "from_doc_type", "from_doc_no", "from_dtl_key"},
    "picking_headers": {"source_book", "doc_key", "source_modified_at", "source_vanished_at",
                        "last_synced_at", "source_record", "creditor_code", "creditor_name",
                        "supplier_do_no", "purchase_agent", "ship_via", "ship_info", "ref",
                        "ref_doc_no", "remarks", "description", "doc_status", "is_cancelled",
                        "currency_code", "currency_rate", "subtotal_amount", "tax_amount",
                        "total_amount", "local_net_total"},
    "picking_lines": {"dtl_key", "seq", "item_code", "location_code", "description", "uom_code",
                      "qty", "foc_qty", "discount_text", "discount_amount", "tax_amount",
                      "delivery_date", "proj_no", "our_po_no", "our_po_date", "from_doc_type",
                      "from_doc_no", "from_dtl_key", "purchase_order_id"},
}
NEW_INDEXES = {
    "orders": "uq_orders_company_book_doc_key",
    "picking_headers": "uq_picking_headers_company_book_doc_key",
    "order_lines": "uq_order_lines_order_dtl_key",
    "picking_lines": "uq_picking_lines_header_dtl_key",
}


def _load():
    alembic_dir = str(VERSIONS.parent)
    if alembic_dir not in sys.path:
        sys.path.insert(0, alembic_dir)
    spec = importlib.util.spec_from_file_location(f"m_{REVISION}", VERSIONS / f"{REVISION}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(conn, fn):
    with Operations.context(MigrationContext.configure(conn)):
        fn()


def _columns(conn, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def _state(conn) -> bool:
    """True when every new column, index and the table are present; False when none is."""
    inspector = sa.inspect(conn)
    present = [
        NEW_COLUMNS[t] <= _columns(conn, t) for t in NEW_COLUMNS
    ] + [
        name in {i["name"] for i in inspector.get_indexes(t)} for t, name in NEW_INDEXES.items()
    ] + [inspector.has_table("branches")]
    absent = [
        not (NEW_COLUMNS[t] & _columns(conn, t)) for t in NEW_COLUMNS
    ] + [
        name not in {i["name"] for i in inspector.get_indexes(t)} for t, name in NEW_INDEXES.items()
    ] + [not inspector.has_table("branches")]
    if all(present):
        return True
    if all(absent):
        return False
    raise AssertionError("partially migrated")


def test_revision_fits_and_chains_onto_the_main_head():
    module = _load()
    assert module.revision == REVISION
    assert len(module.revision) <= 32
    assert module.down_revision == "cpc4_cost_packaging_method"


def test_up_down_up():
    module = _load()
    with engine.connect() as conn:
        outer = conn.begin()
        try:
            if not _state(conn):
                _run(conn, module.upgrade)
            assert _state(conn) is True
            _run(conn, module.downgrade)
            assert _state(conn) is False
            _run(conn, module.upgrade)
            assert _state(conn) is True
        finally:
            outer.rollback()
