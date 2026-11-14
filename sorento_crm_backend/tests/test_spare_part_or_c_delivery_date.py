"""SPARE-PART-OR-B C, red-first (Phase 2). C5: each OR line has its own delivery date.

Contract: documentation/plans/purchasing/spare-part-or-c-14nov-acceptance-criteria.md C5.1-C5.4
(backend half; the form's picker and the relabel are FE, SparePartRequestForm.orC.test.tsx).
Postgres only; every row seeded here.

NAMED CONTRACT CHOICES (the UAC leaves them open):
1. The line body key is `delivery_date` ("YYYY-MM-DD"); the header key stays `needed_by`.
2. A line sent with no `delivery_date` takes the header's (C5.1 default, C5.2 "header default
   fills a blank line"); a line with neither fails Submit with 422 on `lines`.
3. C5.4 on the API: an update of a draft that moves the header date and sends a line with no
   `delivery_date` moves that row only if it was on the PREVIOUS header date; a row on its
   own date keeps it.
4. The OR detail line carries `delivery_date` (ISO), and the OI worklist row's
   `delivery_date` is the line's (C5.3, `oi_delivery_date.resolve`).
"""
from __future__ import annotations

from datetime import date

import pytest

from app.services.error_handler import AppException

from ._spare_part_or_c_support import (  # noqa: F401  (fixtures)
    approve_as,
    create_as,
    dated_line,
    plain,
    reload,
    row_for,
    rows_of,
    save_form,
    sent,
    submit_as,
    svc,
    worklist_rows,
    world,
)
from ._spare_part_request_support import SPR


def _lines(w, a_date=None, b_date=None):
    return [
        dated_line(w.product_a, w.loc_a, qty="10", delivery_date=a_date),
        dated_line(w.product_b, w.loc_b, qty="4", unit_price="12.50", delivery_date=b_date),
    ]


def test_C5_1_each_line_stores_its_own_delivery_date(plain):
    w = plain
    inquiry = create_as(w, w.requester, lines=_lines(w, "2026-12-20", "2027-01-05"))
    assert row_for(w.db, inquiry, w.product_a).delivery_date == date(2026, 12, 20)
    assert row_for(w.db, inquiry, w.product_b).delivery_date == date(2027, 1, 5)


def test_C5_1_a_line_with_no_date_takes_the_header_date(plain):
    w = plain
    inquiry = create_as(w, w.requester, lines=_lines(w, "2026-12-20", None))
    assert row_for(w.db, inquiry, w.product_b).delivery_date == date(2026, 12, 15)


def test_C5_1_the_detail_line_carries_its_delivery_date(plain):
    w = plain
    inquiry = create_as(w, w.requester, lines=_lines(w, "2026-12-20", "2027-01-05"))
    res = w.as_user(w.requester).get(f"{SPR}/{inquiry.id}")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data.get("needed_by") == "2026-12-15", "the header API field name is unchanged"
    by_row = {l["id"]: l for l in data["lines"]}
    row_a = row_for(w.db, inquiry, w.product_a)
    assert by_row[str(row_a.id)].get("delivery_date") == "2026-12-20", by_row[str(row_a.id)]


def test_C5_2_submit_refuses_a_line_with_no_date_and_no_header_date(plain):
    w = plain
    inquiry = create_as(w, w.requester, needed_by=None, lines=_lines(w, "2026-12-20", None))
    with pytest.raises(AppException) as excinfo:
        svc().submit(w.db, reload(w.db, inquiry), w.requester)
    assert excinfo.value.status_code == 422
    assert "date" in (excinfo.value.message or "").lower(), excinfo.value.message
    w.db.rollback()


def test_C5_2_submit_passes_when_every_line_has_a_date(plain):
    w = plain
    inquiry = create_as(w, w.requester, needed_by=None, lines=_lines(w, "2026-12-20", "2027-01-05"))
    inquiry = submit_as(w, inquiry, w.requester)
    assert inquiry.state == "pending_approval"


def test_C5_3_the_oi_row_reads_the_line_date(plain):
    from app.services import oi_delivery_date

    w = plain
    inquiry = approve_as(
        w,
        submit_as(w, create_as(w, w.requester, lines=_lines(w, "2026-12-20", "2027-01-05")), w.requester),
        w.stage1.tier1,
    )
    row_b = row_for(w.db, inquiry, w.product_b)
    assert oi_delivery_date.resolve(w.db, [row_b])[str(row_b.id)].date == date(2027, 1, 5)
    listed = worklist_rows(w, inquiry)[str(row_b.id)]
    assert str(listed.get("delivery_date"))[:10] == "2027-01-05", listed


def test_C5_4_a_header_date_change_on_a_draft_moves_only_rows_on_the_old_header_date(plain):
    w = plain
    inquiry = create_as(w, w.requester, lines=_lines(w, None, "2027-01-05"))
    row_a = row_for(w.db, inquiry, w.product_a)
    row_b = row_for(w.db, inquiry, w.product_b)
    assert row_a.delivery_date == date(2026, 12, 15), "precondition: on the header date"
    lines = [
        {
            "id": str(r.id), "product_id": str(r.product_id), "stock_location": r.stock_location,
            "qty": str(r.qty), "unit_price": str(r.unit_price), "delivery_date": None,
        }
        for r in (row_a, row_b)
    ]
    save_form(w, inquiry, w.requester, lines, needed_by="2026-12-31")
    assert row_for(w.db, inquiry, w.product_a).delivery_date == date(2026, 12, 31)
    assert row_for(w.db, inquiry, w.product_b).delivery_date == date(2027, 1, 5)
