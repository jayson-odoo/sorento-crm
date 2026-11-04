"""OI-RESERVE-USED-ROW: a used OI row is never listed, counted or requested.

Plan: `documentation/plans/scm/PLAN-oi-reserve-used-row-04nov.md` (owner rulings 4 Nov 2026):

* one visibility rule for Order Inquiries > Lines and the Documents tab (`oi_row_visibility`):
  a row is listed and counted when it is not cancelled and not used, on both, and the two tabs
  return the same row set;
* a used row can never carry a new reserve request (R1);
* the stock debt snapshot drill links only live rows, also for a snapshot saved before a row
  went used (R2);
* the one-off repair moves open requests stuck on used rows to the line's live row.

Postgres scratch schemas (`blank_session`), every chain seeded here.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    ACK_CHANGED,
    INQUIRY_CANCELLED,
    RESERVE_REQUESTED,
    OrderInquiryReserveRequest,
    OrderInquiryReserveRequestRow,
    OrderInquiryRow,
)
from app.services.error_handler import AppException
from app.services.oi_row_visibility import is_live_row
from app.services.order_inquiry_reserve_service import OrderInquiryReserveService
from app.services.scm.stock_debt_snapshot_service import StockDebtSnapshotService

from .test_oi_no_double_count import _header_of, _lines_tab, _Order, _uid, api  # noqa: F401

from scripts import repair_oi_reserve_used_rows as repair


def _request(db, order: _Order, row: OrderInquiryRow, qty: str, *, answered: bool = False):
    """An open reserve request naming `row`, written directly (the guard under test refuses
    a used row, which is exactly how the prod data got there before it existed)."""
    ordinal = (
        db.query(OrderInquiryReserveRequest)
        .filter(OrderInquiryReserveRequest.order_inquiry_id == row.order_inquiry_id)
        .count()
        + 1
    )
    request = OrderInquiryReserveRequest(
        id=_uid(),
        company_id=order.company_id,
        order_inquiry_id=row.order_inquiry_id,
        ordinal=ordinal,
        state=RESERVE_REQUESTED,
    )
    db.add(request)
    db.flush()
    rr = OrderInquiryReserveRequestRow(
        id=_uid(),
        company_id=order.company_id,
        request_id=request.id,
        row_id=row.id,
        qty_requested=Decimal(qty),
        qty_reserved=Decimal(qty) if answered else None,
    )
    db.add(rr)
    db.flush()
    return request, rr


def _split_line(db, company_id):
    """The prod shape: one SO line, the used 55 row it carried and the live 33 row raised when
    the line changed."""
    order = _Order(db, company_id)
    product, core, mirror = order.line(1, "33")
    used = order.row(mirror, product, "55", redirected=True, ack_state=ACK_ACKNOWLEDGED)
    live = order.row(mirror, product, "33", ack_state=ACK_ACKNOWLEDGED)
    return order, product, core, mirror, used, live


# =============================================================================
# One visibility rule: Lines and Documents
# =============================================================================


def test_lines_and_documents_list_the_same_live_rows(api):
    client, db, company_id = api
    order = _Order(db, company_id)
    p1, _c1, m1 = order.line(1, "33")
    used = order.row(m1, p1, "55", redirected=True)
    live = order.row(m1, p1, "33")
    p2, _c2, m2 = order.line(2, "10")
    cancelled = order.row(m2, p2, "10", state=INQUIRY_CANCELLED)
    live_2 = order.row(m2, p2, "10")
    p3, _c3, m3 = order.line(3, "5")
    used_only = order.row(m3, p3, "5", redirected=True, ack_state=ACK_CHANGED)
    db.commit()

    lines_tab = {r["id"] for r in _lines_tab(client, order.inquiry.id)}
    history = _lines_tab(client, order.inquiry.id, include_history="true")
    everything = {r["id"] for r in history}
    assert everything == {used.id, live.id, cancelled.id, live_2.id, used_only.id}

    # Lines lists exactly the live rows, the same rows the OI page reads as live.
    assert lines_tab == {live.id, live_2.id}
    assert lines_tab == {
        r["id"] for r in history if r["state"] != INQUIRY_CANCELLED and not r["redirected_to_pool"]
    }
    assert lines_tab == {
        r.id for r in db.query(OrderInquiryRow).filter(OrderInquiryRow.id.in_(everything)) if is_live_row(r)
    }

    # Documents counts the lines those rows sit on, and no other.
    header = _header_of(client, order.inquiry.id)
    listed_lines = {r["so_line_id"] for r in _lines_tab(client, order.inquiry.id)}
    assert header["lines_total"] == len(listed_lines) == 2


def test_an_explicit_state_filter_never_lists_a_used_row(api):
    client, db, company_id = api
    order, *_rest, used, live = _split_line(db, company_id)
    db.commit()
    rows = {r["id"] for r in _lines_tab(client, order.inquiry.id, state="raised")}
    assert rows == {live.id}


def test_a_line_with_only_used_rows_is_not_counted_and_does_not_hold_the_oi_open(api):
    client, db, company_id = api
    order = _Order(db, company_id)
    p1, _c1, m1 = order.line(1, "5")
    order.row(m1, p1, "5", redirected=True, ack_state=ACK_CHANGED)
    p2, _c2, m2 = order.line(2, "7")
    order.row(m2, p2, "7", ack_state=ACK_ACKNOWLEDGED)
    db.commit()

    header = _header_of(client, order.inquiry.id)
    assert header["lines_total"] == 1
    assert header["lines_to_confirm"] == 0
    assert header["status"] == "completed"


def test_only_a_waiting_live_row_makes_a_line_to_confirm_so_the_tabs_tally(api):
    """Review nit: a used row still waiting beside a confirmed live row no longer holds the
    OI open; Lines lists nothing to confirm for it, and Documents agrees."""
    client, db, company_id = api
    order = _Order(db, company_id)
    p1, _c1, m1 = order.line(1, "5")
    order.row(m1, p1, "2", redirected=True, ack_state=ACK_CHANGED)
    order.row(m1, p1, "5", ack_state=ACK_ACKNOWLEDGED)
    p2, _c2, m2 = order.line(2, "4")
    order.row(m2, p2, "4", ack_state=ACK_CHANGED)
    db.commit()

    header = _header_of(client, order.inquiry.id)
    assert header["lines_total"] == 2
    to_confirm = _lines_tab(client, order.inquiry.id, ack="to_confirm")
    assert header["lines_to_confirm"] == len({r["so_line_id"] for r in to_confirm}) == 1


def test_documents_search_does_not_match_an_item_only_on_a_used_row(api):
    client, db, company_id = api
    order = _Order(db, company_id)
    p1, _c1, m1 = order.line(1, "5")
    order.row(m1, p1, "5", redirected=True)
    p2, _c2, m2 = order.line(2, "7")
    order.row(m2, p2, "7")
    db.commit()

    def found(text: str) -> bool:
        response = client.get(
            "/api/v1/project-sales/order-inquiry-headers",
            params={"state": "all", "query": text, "limit": 100},
        )
        assert response.status_code == 200, response.text
        return any(item["id"] == order.inquiry.id for item in response.json()["data"])

    assert found(p2.product_code)
    assert not found(p1.product_code)


# =============================================================================
# R1: a used row is never requestable
# =============================================================================


def test_a_reserve_request_on_a_used_row_is_refused(api):
    _client, db, company_id = api
    order, *_rest, used, live = _split_line(db, company_id)
    service = OrderInquiryReserveService(db)
    with pytest.raises(AppException) as refused:
        service.create_request(
            inquiry_id=order.inquiry.id,
            rows=[{"row_id": used.id, "qty_requested": "33"}],
            note=None,
            actor_user_id=None,
        )
    assert refused.value.status_code == 409
    assert refused.value.code == "reserve_request_used_row"

    request = service.create_request(
        inquiry_id=order.inquiry.id,
        rows=[{"row_id": live.id, "qty_requested": "33"}],
        note=None,
        actor_user_id=None,
    )
    assert [r.row_id for r in db.query(OrderInquiryReserveRequestRow).filter_by(request_id=request.id)] == [live.id]


# =============================================================================
# R2: the snapshot drill links live rows only
# =============================================================================


def test_snapshot_links_only_the_live_row_of_a_line(api):
    _client, db, company_id = api
    _order, _p, core, _m, used, live = _split_line(db, company_id)
    linked = StockDebtSnapshotService(db)._linked_oi_rows([core.id])
    assert [oi_row.id for oi_row, _inq in linked[str(core.id)]] == [live.id]


def test_snapshot_reads_a_rejected_answer_as_no_reserve(api):
    """Review should-fix 3: CS answering 0 is a rejection, never "Reserved 0"."""
    _client, db, company_id = api
    order, *_rest, _used, live = _split_line(db, company_id)
    request, rr = _request(db, order, live, "33")
    rr.qty_reserved = Decimal("0")
    db.flush()
    now = StockDebtSnapshotService(db)._oi_now([live.id])
    assert now[live.id]["reserve_state"] is None
    assert now[live.id]["reserve_qty"] is None

    rr.qty_reserved = Decimal("20")
    db.flush()
    now = StockDebtSnapshotService(db)._oi_now([live.id])
    assert (now[live.id]["reserve_state"], now[live.id]["reserve_qty"]) == ("reserved", 20.0)


def test_snapshot_reads_a_used_row_as_not_live_and_not_requestable(api):
    _client, db, company_id = api
    *_rest, used, live = _split_line(db, company_id)
    now = StockDebtSnapshotService(db)._oi_now([used.id, live.id])
    assert now[used.id]["live"] is False
    assert now[used.id]["requestable"] is False
    assert now[live.id]["live"] is True
    assert now[live.id]["requestable"] is True


def test_a_snapshot_saved_before_a_row_went_used_no_longer_shows_it(api, monkeypatch):
    from app.models.stock_debt_snapshot import StockDebtSnapshot, StockDebtSnapshotRow
    from app.services.user_service import UserPermissionService

    _client, db, company_id = api
    order, product, core, _m, used, live = _split_line(db, company_id)
    frozen = lambda row: {  # noqa: E731
        "oi_id": order.inquiry.id, "inquiry_no": order.inquiry.inquiry_no, "row_id": row.id,
        "qty": float(row.qty), "delivery_date": None, "stock_location": None,
        "verb": row.verb, "state": row.state,
    }
    snapshot = StockDebtSnapshot(
        id=_uid(), company_id=company_id, name="zzt", filters={}, months=[], totals={}, row_count=1,
    )
    db.add(snapshot)
    db.flush()
    row = StockDebtSnapshotRow(
        id=_uid(), company_id=company_id, snapshot_id=snapshot.id, position=0,
        product_id=product.id, product_code=product.product_code, row_data={},
        lines=[{
            "bucket": "2026-10", "sales_order_line_id": str(core.id), "so_number": order.so.so_number,
            "required_date": "2026-10-15", "oi_rows": [frozen(used), frozen(live)],
        }],
    )
    db.add(row)
    db.flush()
    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", lambda *_a, **_k: True)

    out = StockDebtSnapshotService(db).lines(snapshot.id, row.id, None, "zzt-user")
    assert [oi["row_id"] for oi in out["data"][0]["oi_rows"]] == [live.id]


# =============================================================================
# Repair: open requests stuck on used rows
# =============================================================================


def test_repair_moves_an_open_request_to_the_single_live_row(api):
    _client, db, company_id = api
    order, *_rest, used, live = _split_line(db, company_id)
    _req, rr = _request(db, order, used, "33")

    dry = repair.run(db, apply=False, expect=None, inquiry_id=order.inquiry.id)
    assert (dry["found"], dry["move"], dry["held"]) == (1, 1, 0)
    assert db.get(OrderInquiryReserveRequestRow, rr.id).row_id == used.id

    applied = repair.run(db, apply=True, expect=1, inquiry_id=order.inquiry.id)
    assert applied["moved"] == 1
    moved = db.get(OrderInquiryReserveRequestRow, rr.id)
    assert moved.row_id == live.id
    assert moved.qty_requested == Decimal("33")

    again = repair.run(db, apply=True, expect=0, inquiry_id=order.inquiry.id)
    assert (again["found"], again["moved"]) == (0, 0)


def test_repair_refuses_when_the_expected_count_moved(api):
    _client, db, company_id = api
    order, *_rest, used, _live = _split_line(db, company_id)
    _req, rr = _request(db, order, used, "33")
    with pytest.raises(repair.CountMismatch):
        repair.run(db, apply=True, expect=2, inquiry_id=order.inquiry.id)
    assert db.get(OrderInquiryReserveRequestRow, rr.id).row_id == used.id


def test_repair_leaves_an_answered_request_row_alone(api):
    _client, db, company_id = api
    order, *_rest, used, _live = _split_line(db, company_id)
    _request(db, order, used, "33", answered=True)
    assert repair.run(db, apply=False, expect=None, inquiry_id=order.inquiry.id)["found"] == 0


def test_repair_never_sends_two_stuck_requests_to_one_live_row(api):
    """Review should-fix 1: two used rows on one line, both with open requests, one live row:
    the first (oldest) moves, the second is held for a person."""
    _client, db, company_id = api
    order = _Order(db, company_id)
    product, _core, mirror = order.line(1, "33")
    used_a = order.row(mirror, product, "55", redirected=True)
    used_b = order.row(mirror, product, "20", redirected=True)
    live = order.row(mirror, product, "33")
    _req_a, rr_a = _request(db, order, used_a, "10")
    _req_b, rr_b = _request(db, order, used_b, "10")

    out = repair.run(db, apply=True, expect=1, inquiry_id=order.inquiry.id)
    assert (out["found"], out["move"], out["held"], out["moved"]) == (2, 1, 1, 1)
    rows = {db.get(OrderInquiryReserveRequestRow, rr_a.id).row_id, db.get(OrderInquiryReserveRequestRow, rr_b.id).row_id}
    assert live.id in rows
    assert rows & {used_a.id, used_b.id}


@pytest.mark.parametrize("shape", ["no_live", "two_live", "live_has_request", "qty_too_big"])
def test_repair_holds_what_it_cannot_place(api, shape):
    _client, db, company_id = api
    order = _Order(db, company_id)
    product, _core, mirror = order.line(1, "33")
    used = order.row(mirror, product, "55", redirected=True)
    asked = "33"
    if shape == "two_live":
        order.row(mirror, product, "20")
        order.row(mirror, product, "13")
    elif shape == "live_has_request":
        live = order.row(mirror, product, "33")
        _request(db, order, live, "10")
    elif shape == "qty_too_big":
        order.row(mirror, product, "20")
        asked = "33"
    _req, rr = _request(db, order, used, asked)

    out = repair.run(db, apply=True, expect=0, inquiry_id=order.inquiry.id)
    assert (out["found"], out["move"], out["held"], out["moved"]) == (1, 0, 1, 0)
    assert db.get(OrderInquiryReserveRequestRow, rr.id).row_id == used.id


def test_the_cancelled_state_count_matches_the_cancelled_list(api):
    """Review should-fix 2: the State facet's Cancelled (n) leaves out used rows, as the list does."""
    client, db, company_id = api
    order = _Order(db, company_id)
    product, _core, mirror = order.line(1, "5")
    order.row(mirror, product, "5")
    order.row(mirror, product, "2", state=INQUIRY_CANCELLED)
    order.row(mirror, product, "3", state=INQUIRY_CANCELLED, redirected=True)
    db.commit()
    listed = _lines_tab(client, order.inquiry.id, state="cancelled")
    summary = client.get(
        "/api/v1/project-sales/order-inquiries/summary", params={"inquiry_id": order.inquiry.id}
    )
    assert summary.status_code == 200, summary.text
    assert summary.json()["by_state"]["cancelled"] == len(listed) == 1
