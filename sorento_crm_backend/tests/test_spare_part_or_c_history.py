"""SPARE-PART-OR-B C, red-first (Phase 2). C3: the OI page shows the approved qty and only
what happened from the first raise on.

Contract: documentation/plans/purchasing/spare-part-or-c-14nov-acceptance-criteria.md C3.1,
C3.3, C3.4 (C3.2 is the FE Qty cell, see orderInquiryHeaderLinesColumns.orC.test.tsx).
Postgres only; every row seeded here.

NAMED CONTRACT CHOICES (the UAC leaves them open):
1. `GET /order-inquiry-headers/{id}/history?view=inquiry` is the OI page's read; no `view`
   is the whole life (the OR page). The cut is the inquiry's EARLIEST `order_inquiry_raises`
   row: events strictly before it are dropped. The first "approved" event lands in the same
   moment as the raise, so it is not asserted either way.
2. During a revision the worklist row keeps `qty`, `item_code`, `product_id` and
   `delivery_date` (the approved values); the revision's values are never on it.
"""
from __future__ import annotations

from decimal import Decimal

from ._spare_part_or_c_support import (  # noqa: F401  (fixtures)
    approve_as,
    create_as,
    form_lines,
    make_product,
    plain,
    reload,
    revise_as,
    row_for,
    save_form,
    sent,
    submit_as,
    svc,
    worklist_rows,
    world,
)
from ._spare_part_request_support import HEADERS

PRE_RAISE = ("created", "edited", "submitted", "rejected")


def _life(w):
    """Created, edited, submitted, approver qty 10 -> 8, rejected, resubmitted, approved
    (raised), then revised after the raise."""
    inquiry = create_as(w, w.requester)
    save_form(w, inquiry, w.requester, form_lines(w, inquiry), reason="Edited reason")
    inquiry = submit_as(w, inquiry, w.requester)
    row_a = row_for(w.db, inquiry, w.product_a)
    svc().edit_line(w.db, reload(w.db, inquiry), row_a.id, w.stage1.tier1, qty="8")
    w.db.commit()
    svc().reject(w.db, reload(w.db, inquiry), w.stage1.tier1, "Try again")
    w.db.commit()
    inquiry = submit_as(w, inquiry, w.requester)
    inquiry = approve_as(w, inquiry, w.stage1.tier1)
    assert inquiry.state == "raised", "precondition"
    return revise_as(w, inquiry, w.requester)


def _events(w, inquiry, **params) -> list:
    res = w.as_user(w.admin).get(f"{HEADERS}/{inquiry.id}/history", params=params)
    assert res.status_code == 200, res.text
    return res.json()["events"]


def test_C3_4_no_view_param_is_the_whole_life(plain):
    w = plain
    kinds = [e["kind"] for e in _events(w, _life(w))]
    for kind in ("created", "submitted", "rejected", "changed", "raised", "revised"):
        assert kind in kinds, f"{kind}: {kinds}"


def test_C3_3_view_inquiry_drops_every_pre_raise_event(plain):
    w = plain
    events = _events(w, _life(w), view="inquiry")
    kinds = [e["kind"] for e in events]
    for kind in PRE_RAISE:
        assert kind not in kinds, f"{kind} is before the raise: {kinds}"
    assert "changed" not in kinds, f"the approver's 10 -> 8 is before the raise: {kinds}"


def test_C3_3_view_inquiry_keeps_the_raise_and_what_came_after(plain):
    w = plain
    kinds = [e["kind"] for e in _events(w, _life(w), view="inquiry")]
    assert "raised" in kinds, kinds
    assert "revised" in kinds, kinds


def test_C3_3_view_inquiry_is_still_newest_first(plain):
    w = plain
    stamps = [e["at"] for e in _events(w, _life(w), view="inquiry") if e.get("at")]
    assert stamps == sorted(stamps, reverse=True)


def test_C3_4_a_sales_order_inquiry_reads_the_same_with_view_inquiry(world):
    """Guard (green by design): `view=inquiry` changes nothing for an SO inquiry."""
    from app.models.project_so import OrderInquiryRaise

    from .test_oi_header_list import _header

    w = world
    inquiry = _header(w.db, w.company_id)["inquiry"]
    w.db.add(
        OrderInquiryRaise(
            company_id=w.company_id, order_inquiry_id=inquiry.id, kind="raised", raised_by=w.admin,
        )
    )
    w.db.commit()
    assert _events(w, inquiry, view="inquiry") == _events(w, inquiry)


# =============================================================================
# C3.1 - the OI rows read the approved values during a revision
# =============================================================================


def test_C3_1_the_worklist_row_keeps_the_approved_product_qty_and_date(plain):
    w = plain
    product_c = make_product(w.db, "bearing kit")
    w.db.commit()
    inquiry = approve_as(w, submit_as(w, create_as(w, w.requester), w.requester), w.stage1.tier1)
    row_a = row_for(w.db, inquiry, w.product_a)
    approved = worklist_rows(w, inquiry)[str(row_a.id)]
    inquiry = revise_as(w, inquiry, w.requester)
    lines = form_lines(w, inquiry)
    for entry in lines:
        if entry["id"] == str(row_a.id):
            entry.update(product_id=str(product_c.id), qty="12", delivery_date="2027-01-20")
    save_form(w, inquiry, w.requester, lines)
    now = worklist_rows(w, inquiry)[str(row_a.id)]
    assert Decimal(str(now["qty"])) == Decimal("10")
    assert now["item_code"] == w.product_a.product_code
    assert str(now.get("product_id")) == str(w.product_a.id)
    assert now.get("delivery_date") == approved.get("delivery_date")
