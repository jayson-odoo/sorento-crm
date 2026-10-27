"""HIDE-REMOVED-LINE-SO, red tests: a PO line AutoCount REMOVED shows no book S/O.

UAC: documentation/plans/scm/hide-removed-line-so-27oct-acceptance-criteria.md (AC-HR-01..06).

Owner, 27 Oct 2026: the CRM keeps a removed line as a Cancelled record, but AutoCount no
longer links it to any sales order, so the S/O cell reads "-". Driven through the real
ingest push (the `env` fixture of tests/test_ingest_documents.py) so the line's state is
exactly what the removed-line path writes, then read off both screens that print the book
S/O of a PO line: the SCM purchase-order detail (`PurchaseOrderService.get_one`) and the
order inquiry PO popup (`OrderInquiryWorklistService.get_po_detail`).

Postgres only. Every test seeds its own chain. No customer names.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text

from app.models.order import SalesOrder

from .test_ac_removed_lines_ingest import PoWorld, _oi_row_on, _repush_without_a
from .test_ingest_documents import (
    INGEST_PO,
    _po_line,
    _po_record,
    env,  # noqa: F401 - pytest fixture, imported for reuse
)

__all__ = ["env"]

SO_NUMBER = "ZZTHRSO396348"


def _world(env) -> PoWorld:
    """A pushed two-line PO whose BOTH lines name the same held sales order: line A (to be
    removed) and line B (stays)."""
    doc_key = f"ZZT_HR:{uuid.uuid4().hex[:8]}"
    env.db.add(
        SalesOrder(
            id=str(uuid.uuid4()), company_id=env.company_a, so_number=SO_NUMBER,
            order_date=date(2026, 7, 1), demand_class="project", source_ref=doc_key,
        )
    )
    env.db.commit()
    a = _po_line(env, qty_ordered=546, from_so_line_ref=f"{doc_key}:1001")
    b = _po_line(env, qty_ordered=10, from_so_line_ref=f"{doc_key}:1002")
    record = _po_record(env, lines=[a, b])
    res = env.post(INGEST_PO, [record])
    assert res.status_code == 200, res.text
    w = PoWorld(env, record, a, b)
    # Something references line A (an order inquiry link in production), so the sweep
    # keeps it as a cancelled record instead of deleting it.
    _oi_row_on(env, w)
    return w


def _scm_lines(env, w: PoWorld) -> dict:
    from app.services.scm.purchase_order_service import PurchaseOrderService

    env.db.expire_all()
    po = PurchaseOrderService(env.db).get_one(w.header_id)
    return {str(line["id"]): line for line in po["lines"]}


def _oi_lines(env, w: PoWorld) -> dict:
    from app.services.order_inquiry_worklist_service import OrderInquiryWorklistService

    env.db.expire_all()
    po = OrderInquiryWorklistService(env.db).get_po_detail(w.header_id)
    return {str(line["id"]): line for line in po["lines"]}


def _ref_of(env, line_id: str):
    return env.db.execute(
        text("SELECT from_so_line_ref FROM purchase_order_lines WHERE id = :i"), {"i": line_id}
    ).scalar()


def _status_of(env, line_id: str):
    return env.db.execute(
        text("SELECT line_status FROM purchase_order_lines WHERE id = :i"), {"i": line_id}
    ).scalar()


def _both(env, w):
    return {"scm": _scm_lines(env, w), "oi": _oi_lines(env, w)}


def test_fixture_both_lines_show_the_sales_order_before_the_push(env):
    w = _world(env)
    for screen, lines in _both(env, w).items():
        for line_id in (w.line_a, w.line_b):
            assert lines[line_id]["book_so_number"] == SO_NUMBER, (screen, line_id)


def test_ac_hr_01_05_a_removed_line_shows_no_sales_order_and_keeps_its_ref(env):
    w = _world(env)
    stored = _ref_of(env, w.line_a)

    _repush_without_a(env, w)

    assert _status_of(env, w.line_a) == "cancelled", "fixture: the sweep kept line A"
    for screen, lines in _both(env, w).items():
        removed = lines[w.line_a]
        assert removed["book_so_number"] is None, screen
        assert removed["book_so_unresolved"] is False, screen
        # AC-HR-04: the line AutoCount still carries is unchanged.
        assert lines[w.line_b]["book_so_number"] == SO_NUMBER, screen
    # AC-HR-05: the stored column is audit, untouched.
    assert _ref_of(env, w.line_a) == stored


def test_ac_hr_01_the_546_case_a_received_line_removed_later_shows_no_sales_order(env):
    w = _world(env)
    env.db.execute(
        text("UPDATE purchase_order_lines SET qty_received = qty_ordered, "
             "line_status = 'closed' WHERE id = :i"),
        {"i": w.line_a},
    )
    env.db.commit()

    _repush_without_a(env, w)

    for screen, lines in _both(env, w).items():
        assert lines[w.line_a]["book_so_number"] is None, screen


def test_ac_hr_02_a_line_cancelled_by_a_cancel_po_document_keeps_its_sales_order(env):
    w = _world(env)
    env.db.execute(
        text("UPDATE purchase_order_lines SET cancelled_by_cancel_doc = true, "
             "qty_cancelled = qty_ordered, line_status = 'cancelled' WHERE id = :i"),
        {"i": w.line_a},
    )
    env.db.commit()

    for screen, lines in _both(env, w).items():
        assert lines[w.line_a]["book_so_number"] == SO_NUMBER, screen


def test_ac_hr_03_a_line_on_a_cancelled_po_keeps_its_sales_order(env):
    w = _world(env)
    res = env.post(INGEST_PO, [dict(w.record, status="cancelled")])
    assert res.status_code == 200, res.text
    assert _status_of(env, w.line_a) == "cancelled", "fixture: the header cancel took line A"

    for screen, lines in _both(env, w).items():
        assert lines[w.line_a]["book_so_number"] == SO_NUMBER, screen
        assert lines[w.line_b]["book_so_number"] == SO_NUMBER, screen
