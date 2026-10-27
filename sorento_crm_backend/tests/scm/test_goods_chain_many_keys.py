"""GOODSCHAIN-INDEX-QUERY (PLAN-goodschain-index-query-27oct): the PO -> SPO key readers
give the same answer for 9,000 keys as for the handful that match, with no stack-depth error.

Prod incident 27 Oct 2026: Stock Debt passed ~6,800 keys to `transferred_allocations` as a
literal row-IN, which seq-scanned `spo_allocations` per call and overflows the default 2MB
`max_stack_depth` at that size. Each test seeds a small real chain and pads the call with
thousands of keys that match nothing; the answer must be exactly the real chain's.
"""
from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import text

from tests.scm.conftest import SORENTO_COMPANY_ID, requires_pg
from tests.scm.test_goods_chain import _World, _gc
from tests.scm.test_stock_debt_routes import _u

pytestmark = requires_pg

PADDING = 9_000


def _ids(transferred):
    return {line: [str(row.spo_allocation_id) for row in rows] for line, rows in transferred.items()}


def _po_line_row(po, po_line):
    """The row shape `transferred_allocations` reads (`_transfer_key` columns)."""
    return SimpleNamespace(
        po_line_id=po_line.id,
        po_number=po.po_number,
        po_line_ref=po_line.source_ref.strip(),
        po_product_id=po_line.product_id,
        po_company_id=po_line.company_id,
    )


def _padding_po_rows(product_id):
    return [
        SimpleNamespace(
            po_line_id=_u(),
            po_number=f"ZZTPAD{n}",
            po_line_ref=f"ZZT:PAD:{n}",
            po_product_id=product_id,
            po_company_id=SORENTO_COMPANY_ID,
        )
        for n in range(PADDING)
    ]


def _chain_world(db):
    """Three PO lines: one reached by the key, one by `po_line_id` only (a CRM-raised SPO
    with no key), one reached BOTH ways by the same allocation, which must be listed once."""
    w = _World(db)
    po1, line1 = w.po(ordered=100, transferred=100)
    a1 = w.onto(po1, line1, qty=60)
    a1b = w.onto(po1, line1, qty=40, arrives=w.due.replace(day=1))
    po2, line2 = w.po(ordered=50, transferred=50)
    a2 = w.onto(po2, line2, qty=50)
    a2.from_po_number = None
    a2.from_po_line_ref = None
    a2.po_line_id = line2.id
    po3, line3 = w.po(ordered=30, transferred=30)
    a3 = w.onto(po3, line3, qty=30)
    a3.po_line_id = line3.id
    db.flush()
    rows = [_po_line_row(po1, line1), _po_line_row(po2, line2), _po_line_row(po3, line3)]
    return w, rows, {"line1": line1, "line2": line2, "line3": line3,
                     "a1": a1, "a1b": a1b, "a2": a2, "a3": a3}


def test_transferred_allocations_same_answer_with_9000_padding_keys(scm_app):
    db = scm_app[1]
    w, rows, seeded = _chain_world(db)
    alone = _gc().transferred_allocations(db, rows)
    assert _ids(alone) == {
        seeded["line1"].id: sorted(
            [seeded["a1"].id, seeded["a1b"].id],
            key=lambda i: 0 if i == seeded["a1b"].id else 1,
        ),
        seeded["line2"].id: [seeded["a2"].id],
        seeded["line3"].id: [seeded["a3"].id],
    }
    padded = _gc().transferred_allocations(db, _padding_po_rows(w.product.id) + rows)
    assert _ids(padded) == _ids(alone)
    assert [r._asdict() for r in padded[seeded["line1"].id]] == [
        r._asdict() for r in alone[seeded["line1"].id]
    ]


def test_transferred_allocations_include_withdrawn_with_padding(scm_app):
    from datetime import datetime

    db = scm_app[1]
    w, rows, seeded = _chain_world(db)
    seeded["a2"].retired_at = datetime.utcnow()
    db.flush()
    visible = _gc().transferred_allocations(db, _padding_po_rows(w.product.id) + rows)
    assert seeded["line2"].id not in visible
    withdrawn = _gc().transferred_allocations(
        db, _padding_po_rows(w.product.id) + rows, include_withdrawn=True
    )
    assert _ids(withdrawn)[seeded["line2"].id] == [seeded["a2"].id]


def test_po_lines_feeding_same_answer_with_9000_padding_keys(scm_app):
    db = scm_app[1]
    w, _rows, seeded = _chain_world(db)

    def spo_row(allocation):
        return SimpleNamespace(
            spo_po_line_id=allocation.po_line_id,
            spo_from_po_number=allocation.from_po_number,
            spo_from_ref=(allocation.from_po_line_ref or "").strip() or None,
            spo_product_id=allocation.product_id,
            spo_company_id=allocation.company_id,
        )

    real = [spo_row(seeded[k]) for k in ("a1", "a2", "a3")]
    padding = [
        SimpleNamespace(
            spo_po_line_id=None,
            spo_from_po_number=f"ZZTPAD{n}",
            spo_from_ref=f"ZZT:PAD:{n}",
            spo_product_id=w.product.id,
            spo_company_id=SORENTO_COMPANY_ID,
        )
        for n in range(PADDING)
    ]
    alone = _gc()._po_lines_feeding(db, real)
    assert alone == {seeded["line1"].id, seeded["line2"].id, seeded["line3"].id}
    assert _gc()._po_lines_feeding(db, padding + real) == alone


def _pad_allocations(db, like_id):
    """PADDING copies of allocation `like_id`, each its own SPO naming its own PO number
    that no PO carries, in one INSERT ... SELECT."""
    columns = [
        name
        for (name,) in db.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'spo_allocations' "
                "AND column_name NOT IN ('id', 'from_po_number', 'source_ref', 'po_line_id', 'spo_number') "
                "AND is_generated = 'NEVER'"
            )
        )
    ]
    cols = ", ".join(columns)
    return [
        str(i)
        for (i,) in db.execute(
            text(
                f"INSERT INTO spo_allocations (id, from_po_number, spo_number, {cols}) "
                f"SELECT gen_random_uuid(), 'ZZTPAD' || n, 'ZZTPAD' || n, {cols} "
                "FROM spo_allocations, generate_series(1, :n) AS n WHERE id = :like "
                "RETURNING id"
            ),
            {"n": PADDING, "like": like_id},
        )
    ]


def test_stock_debt_follow_totals_same_answer_with_9000_padding_allocations(scm_app):
    from app.services.scm.stock_debt_service import StockDebtService

    db = scm_app[1]
    w, _rows, seeded = _chain_world(db)
    w.place_on_po(seeded["line1"], 70)
    real = [seeded[k].id for k in ("a1", "a1b", "a2", "a3")]
    service = StockDebtService(db)
    alone = service._follow_totals([seeded["line1"].id], real)
    assert alone[0][seeded["line1"].id] > 0
    padding = _pad_allocations(db, seeded["a1"].id)
    assert len(padding) == PADDING
    assert service._follow_totals([seeded["line1"].id], padding + real) == alone
