"""AC-KC-6: `scripts/restore_deleted_removed_lines.py` puts back AutoCount lines the
pre-fix ingest hard-deleted, Cancelled and unlinked.

The live side is the ingest `env` fixture's scratch schema (its connection, so nothing
outlives the test). The snapshot side is a real second database, built the way the
runbook builds one (only the two line tables, no foreign keys) and dropped afterwards.
The deletion is simulated with a plain DELETE, which is exactly what the bug ran.

Postgres only. No real customer names.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.schema import CreateTable

from app.database import engine as app_engine
from app.models.order import SalesOrderLine
from app.models.procurement import PurchaseOrderLine
from scripts import restore_deleted_removed_lines as script

from .test_ac_removed_lines_ingest import _push_po, _push_so
from .test_ingest_documents import env  # noqa: F401 - pytest fixture, imported for reuse

__all__ = ["env"]

TABLES = (PurchaseOrderLine.__table__, SalesOrderLine.__table__)


@pytest.fixture
def snapshot_db():
    name = f"zzt_snapshot_{uuid.uuid4().hex[:10]}"
    admin = app_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    admin.exec_driver_sql(f'CREATE DATABASE "{name}"')
    snap_engine = create_engine(app_engine.url.set(database=name))
    try:
        with snap_engine.begin() as conn:
            for table in TABLES:
                # Only the line tables, no foreign keys: what `pg_restore -t` yields.
                bare = table.to_metadata(MetaData())
                for fk in list(bare.foreign_key_constraints):
                    bare.constraints.discard(fk)
                conn.execute(CreateTable(bare, include_foreign_key_constraints=[]))
        yield snap_engine
    finally:
        snap_engine.dispose()
        admin.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.close()


def _copy_to_snapshot(env, snap_engine):
    """Snapshot = the live line tables as they are NOW (before the simulated deletion)."""
    live = env.db.connection()
    with snap_engine.begin() as snap:
        for table in TABLES:
            rows = [dict(r) for r in live.execute(text(f"SELECT * FROM {table.name}")).mappings()]
            if rows:
                snap.execute(table.insert(), rows)


def _line(env, table, line_id):
    env.db.expire_all()
    row = env.db.execute(
        text(f"SELECT * FROM {table} WHERE id = :i"), {"i": line_id}
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


def _delete(env, table, line_id):
    env.db.execute(text(f"DELETE FROM {table} WHERE id = :i"), {"i": line_id})
    env.db.commit()


def _run(env, snap_engine, *, apply, company_id=None):
    with snap_engine.connect() as snap:
        return script.restore(
            snap, env.db.connection(), company_id=company_id, apply=apply
        )


def test_ac_kc_6_dry_run_lists_the_deleted_line_and_writes_nothing(env, snapshot_db, capsys):
    w = _push_po(env, a_received=10)
    _copy_to_snapshot(env, snapshot_db)
    _delete(env, "purchase_order_lines", w.line_a)

    out = _run(env, snapshot_db, apply=False)

    assert out == {"purchase_order_lines": 1, "sales_order_lines": 0}
    assert _line(env, "purchase_order_lines", w.line_a) is None
    printed = capsys.readouterr().out
    assert w.po_number in printed
    assert f"DtlKey={script._dtl_key(w.payload_a['source_ref'])}" in printed
    assert f"product={w.product_code}" in printed
    assert "DRY RUN" in printed


def test_ac_kc_6_apply_restores_po_and_so_lines_cancelled_with_original_values(
    env, snapshot_db
):
    w = _push_po(env, a_received=10)
    record, header, line_x, _y = _push_so(env)
    before_po = _line(env, "purchase_order_lines", w.line_a)
    _copy_to_snapshot(env, snapshot_db)
    _delete(env, "purchase_order_lines", w.line_a)
    _delete(env, "sales_order_lines", line_x["id"])

    out = _run(env, snapshot_db, apply=True)

    assert out == {"purchase_order_lines": 1, "sales_order_lines": 1}
    po_line = _line(env, "purchase_order_lines", w.line_a)
    assert po_line is not None and po_line["line_status"] == "cancelled"
    for column in ("purchase_order_id", "product_id", "source_ref", "qty_ordered",
                   "qty_received", "unit_cost", "company_id"):
        assert po_line[column] == before_po[column], column
    assert po_line["qty_received"] == Decimal(10)
    so_line = _line(env, "sales_order_lines", line_x["id"])
    assert so_line is not None and so_line["line_status"] == "cancelled"
    assert so_line["source_ref"] == line_x["source_ref"]
    # untouched siblings
    assert _line(env, "purchase_order_lines", w.line_b)["line_status"] == "open"

    # a second run finds nothing
    assert _run(env, snapshot_db, apply=True) == {
        "purchase_order_lines": 0, "sales_order_lines": 0,
    }


def test_ac_kc_6_a_live_ref_or_a_gone_document_is_not_restored(env, snapshot_db):
    kept_ref = _push_po(env)  # line A deleted, but its DtlKey is live again under a new id
    gone_doc = _push_po(env)  # the whole PO is gone live
    _copy_to_snapshot(env, snapshot_db)
    env.db.execute(
        text("UPDATE purchase_order_lines SET id = :n WHERE id = :o"),
        {"n": str(uuid.uuid4()), "o": kept_ref.line_a},
    )
    env.db.execute(
        text("DELETE FROM purchase_orders WHERE id = :i"), {"i": gone_doc.header_id}
    )
    env.db.commit()
    assert _line(env, "purchase_order_lines", gone_doc.line_a) is None  # cascaded

    out = _run(env, snapshot_db, apply=True)

    assert out == {"purchase_order_lines": 0, "sales_order_lines": 0}
    assert _line(env, "purchase_order_lines", kept_ref.line_a) is None
    assert _line(env, "purchase_order_lines", gone_doc.line_a) is None


def test_ac_kc_6_company_filter_limits_the_run(env, snapshot_db):
    w = _push_po(env)
    _copy_to_snapshot(env, snapshot_db)
    _delete(env, "purchase_order_lines", w.line_a)

    other = str(uuid.uuid4())
    assert _run(env, snapshot_db, apply=False, company_id=other)["purchase_order_lines"] == 0
    assert (
        _run(env, snapshot_db, apply=False, company_id=str(env.company_a))[
            "purchase_order_lines"
        ]
        == 1
    )
