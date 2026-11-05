"""OI-RESERVE-ANY-ROW: any OI row that is not Done, whatever its verb, can be requested for
reserve and reserved; a Done row and a used row cannot.

Plan: `documentation/plans/scm/PLAN-oi-reserve-any-row-05nov.md` (owner ruling 5 Nov 2026).
UAC: `oi-reserve-any-row-05nov-acceptance-criteria.md` (AC-AR-1..7 here; the grid ACs are
vitest, `orderInquiryLineFold.test.ts` / `reserveEligibility.test.ts`).

Postgres scratch schemas (`blank_session`), every chain seeded here.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.inventory import Warehouse
from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    INQUIRY_ACTIONED,
    INQUIRY_CANCELLED,
    INQUIRY_PARTLY_LINKED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_ADVANCE,
    IV_DELAY,
    IV_ORDER,
    IV_RESERVE_AND_ORDER,
    OrderInquiryLink,
    OrderInquiryReserveRequestRow,
)
from app.services import order_inquiry_reserve_service as reserve_module
from app.services.error_handler import AppException
from app.services.oi_row_visibility import is_reservable_row
from app.services.order_inquiry_reserve_service import OrderInquiryReserveService
from app.services.scm.stock_debt_snapshot_service import StockDebtSnapshotService

from .test_oi_no_double_count import _lines_tab, _Order, _uid, api  # noqa: F401
from .test_oi_reserve_used_row import _request

from scripts import repair_oi_reserve_used_rows as repair


def _warehouse(db, company_id):
    warehouse = Warehouse(
        id=_uid(),
        company_id=company_id,
        warehouse_code=f"ZZT{_uid()[:6]}",
        warehouse_name="ZZT any-row pool",
        is_active=True,
    )
    db.add(warehouse)
    db.flush()
    return warehouse


def _ask(db, order, row, qty, warehouse=None):
    return OrderInquiryReserveService(db).create_request(
        inquiry_id=order.inquiry.id,
        rows=[
            {
                "row_id": row.id,
                "qty_requested": qty,
                **({"warehouse_id": warehouse.id} if warehouse is not None else {}),
            }
        ],
        note=None,
        actor_user_id=None,
    )


# =============================================================================
# The one rule
# =============================================================================


@pytest.mark.parametrize(
    "verb", [IV_ORDER, "ORDER_BACK", IV_RESERVE_AND_ORDER, IV_DELAY, IV_ADVANCE, "CHANGE_SO"]
)
@pytest.mark.parametrize(
    "state, expected",
    [
        (INQUIRY_RAISED, True),
        (INQUIRY_PARTLY_LINKED, True),
        (INQUIRY_PLACED, True),
        (INQUIRY_ACTIONED, False),
        (INQUIRY_CANCELLED, False),
    ],
)
def test_reservable_is_live_and_not_done_whatever_the_verb(verb, state, expected):
    class Row:
        pass

    row = Row()
    row.verb, row.state, row.redirected_to_pool = verb, state, False
    assert is_reservable_row(row) is expected
    row.redirected_to_pool = True
    assert is_reservable_row(row) is False


def test_the_verb_list_is_gone():
    """One rule, no verb gate left for a caller to import by mistake."""
    assert not hasattr(reserve_module, "_REQUESTABLE_VERBS")


# =============================================================================
# AC-AR-1/2: DELAY row, request + reserve + email context
# =============================================================================


@pytest.mark.parametrize("verb", [IV_DELAY, IV_ADVANCE])
def test_a_not_done_notice_row_can_be_requested_and_reserved_AC_AR_1_2_3(api, verb):
    client, db, company_id = api
    order = _Order(db, company_id)
    product, _core, mirror = order.line(7, "33")
    row = order.row(mirror, product, "33", verb=verb, ack_state=ACK_ACKNOWLEDGED)
    warehouse = _warehouse(db, company_id)

    request = _ask(db, order, row, "33", warehouse)
    rr = db.query(OrderInquiryReserveRequestRow).filter_by(request_id=request.id).one()
    assert rr.row_id == row.id
    assert rr.qty_requested == Decimal("33")

    service = OrderInquiryReserveService(db)
    service.commit_request(
        inquiry_id=order.inquiry.id,
        reserves=[{"row_id": row.id, "warehouse_id": warehouse.id, "qty_reserved": "33"}],
        amendments=[],
        actor_user_id=None,
    )
    db.flush()
    link = db.query(OrderInquiryLink).filter(OrderInquiryLink.reserve_request_row_id == rr.id).one()
    assert (link.row_id, link.qty) == (row.id, Decimal("33"))

    # The reserved email's queued context names the row (no verb filter on the email side).
    pending = db.info.get(reserve_module._RESERVED_PENDING_KEY) or []
    rows_in_mail = [r for item in pending for r in item["context"]["reserve"]["rows"]]
    assert [(r["item_code"], r["qty_reserved"]) for r in rows_in_mail] == [(row.item_code, "33")]

    db.commit()
    listed = {r["id"]: r for r in _lines_tab(client, order.inquiry.id)}
    assert listed[row.id]["reserved_qty"] == "33"


# =============================================================================
# AC-AR-4/5: Done and used rows are refused, whatever the verb
# =============================================================================


@pytest.mark.parametrize("verb", [IV_ORDER, IV_DELAY])
def test_a_done_row_is_refused_AC_AR_4(api, verb):
    _client, db, company_id = api
    order = _Order(db, company_id)
    product, _core, mirror = order.line(1, "10")
    done = order.row(mirror, product, "10", verb=verb, state=INQUIRY_ACTIONED)
    with pytest.raises(AppException) as refused:
        _ask(db, order, done, "10")
    assert refused.value.status_code == 409
    assert refused.value.code == "reserve_request_wrong_state"


@pytest.mark.parametrize("verb", [IV_ORDER, IV_DELAY])
def test_a_used_row_is_refused_AC_AR_5(api, verb):
    _client, db, company_id = api
    order = _Order(db, company_id)
    product, _core, mirror = order.line(1, "10")
    used = order.row(mirror, product, "10", verb=verb, redirected=True)
    with pytest.raises(AppException) as refused:
        _ask(db, order, used, "10")
    assert refused.value.code == "reserve_request_used_row"


# =============================================================================
# AC-AR-6: stock debt snapshot drill
# =============================================================================


def test_snapshot_reads_a_not_done_delay_row_as_requestable_AC_AR_6(api):
    _client, db, company_id = api
    order = _Order(db, company_id)
    product, _core, mirror = order.line(1, "33")
    delay = order.row(mirror, product, "33", verb=IV_DELAY, ack_state=ACK_ACKNOWLEDGED)
    p2, _c2, m2 = order.line(2, "10")
    done = order.row(m2, p2, "10", verb=IV_DELAY, state=INQUIRY_ACTIONED)
    now = StockDebtSnapshotService(db)._oi_now([delay.id, done.id])
    assert now[delay.id]["requestable"] is True
    assert now[done.id]["requestable"] is False


# =============================================================================
# AC-AR-7: repair target selection reads the same rule
# =============================================================================


def test_repair_moves_a_stuck_request_onto_a_live_delay_row(api):
    """The OI-2609-0257 move PR #2160 made: the line's one live row is a DELAY row."""
    _client, db, company_id = api
    order = _Order(db, company_id)
    product, _core, mirror = order.line(7, "33")
    used = order.row(mirror, product, "55", redirected=True, ack_state=ACK_ACKNOWLEDGED)
    delay = order.row(mirror, product, "33", verb=IV_DELAY, ack_state=ACK_ACKNOWLEDGED)
    _req, rr = _request(db, order, used, "33")
    out = repair.run(db, apply=True, expect=1, inquiry_id=order.inquiry.id)
    assert out["moved"] == 1
    assert db.get(OrderInquiryReserveRequestRow, rr.id).row_id == delay.id


def test_repair_holds_a_request_whose_only_live_row_is_done_AC_AR_7(api):
    _client, db, company_id = api
    order = _Order(db, company_id)
    product, _core, mirror = order.line(1, "33")
    used = order.row(mirror, product, "55", redirected=True)
    order.row(mirror, product, "33", state=INQUIRY_ACTIONED)
    _req, rr = _request(db, order, used, "33")
    out = repair.run(db, apply=True, expect=0, inquiry_id=order.inquiry.id)
    assert (out["found"], out["move"], out["held"], out["moved"]) == (1, 0, 1, 0)
    assert db.get(OrderInquiryReserveRequestRow, rr.id).row_id == used.id


# =============================================================================
# OI-2609-0257 shape, server side: the rows the Lines tab serves carry the figures
# =============================================================================


def test_oi_2609_0257_shape_serves_the_request_on_the_delay_row(api):
    client, db, company_id = api
    order = _Order(db, company_id)
    p7, _c7, m7 = order.line(7, "33")
    order.row(m7, p7, "55", redirected=True, ack_state=ACK_ACKNOWLEDGED)
    delay = order.row(m7, p7, "33", verb=IV_DELAY, ack_state=ACK_ACKNOWLEDGED)
    p416, _c416, m416 = order.line(416, "22")
    order_row = order.row(m416, p416, "22")
    _ask(db, order, delay, "33")
    db.commit()

    listed = {r["id"]: r for r in _lines_tab(client, order.inquiry.id)}
    assert set(listed) == {delay.id, order_row.id}
    assert listed[delay.id]["asked_reserve_qty"] == "33"
    assert listed[delay.id]["reserve_state"] == "requested"
    assert listed[order_row.id]["asked_reserve_qty"] == "0"
    assert listed[order_row.id]["ack_state"] == "awaiting"


def test_owner_b_a_delay_row_beside_a_live_order_row_is_reservable_too(api):
    """Owner (5 Nov, ~10:40 MYT, "more lenient"): no line restriction. Since S2 a date move
    stamps the live buy row instead of raising a DELAY beside it, so the shape is legacy; if it
    is there, each row is requestable on its own."""
    _client, db, company_id = api
    order = _Order(db, company_id)
    product, _core, mirror = order.line(1, "33")
    buy = order.row(mirror, product, "22")
    delay = order.row(mirror, product, "33", verb=IV_DELAY, ack_state=ACK_ACKNOWLEDGED)
    now = StockDebtSnapshotService(db)._oi_now([buy.id, delay.id])
    assert (now[buy.id]["requestable"], now[delay.id]["requestable"]) == (True, True)
    request = OrderInquiryReserveService(db).create_request(
        inquiry_id=order.inquiry.id,
        rows=[{"row_id": buy.id, "qty_requested": "22"}, {"row_id": delay.id, "qty_requested": "33"}],
        note=None,
        actor_user_id=None,
    )
    rows = db.query(OrderInquiryReserveRequestRow).filter_by(request_id=request.id).all()
    assert sorted((r.row_id, r.qty_requested) for r in rows) == sorted(
        [(buy.id, Decimal("22")), (delay.id, Decimal("33"))]
    )
