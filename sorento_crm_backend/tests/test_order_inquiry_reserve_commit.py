"""Order inquiry: Request CS to reserve stock (`PLAN-oi-request-cs-reserve.md` section
6e, owner round 4, 24 Sep). Contract: `documentation/plans/scm/oi-request-cs-reserve-
acceptance-criteria.md`, AC-RS-76 to AC-RS-82 (backend). TEST-FIRST (Phase 2): written
before the coder has touched a line of round-4 code - the commit route, the service's
own orchestration method, and the reserved template's "N line(s) still to reserve" line
all still carry only what rounds 1-3 shipped. A red here must be a missing route/
attribute/template line, a 404, or an assertion on behaviour the plan states does not
exist yet - never an import typo or a fixture bug.

Postgres only (`tests/_pg_fixture.py`); every FK chain is seeded here or borrowed from
`test_order_inquiry_reserve.py` (round 1's own fixtures: `api`/`reserve_api`,
`_seeded_world`, `_open_row`, `_register`, `_captured_dispatches`, `_reserved_calls`,
`_as`, `_load_reserve_seed_migration`, `_reserve_fixture_context`) or
`test_order_inquiry_worklist.py` (`LIST`) - never `LIMIT 1` off a shared table, CI's own
database is empty.

NAMED ASSUMPTIONS (per the tester's brief - the plan leaves several exact shapes open,
and a test-first suite IS what pins them, same convention every reserve suite before
this one uses):

1. Route: `POST {LIST}/{inquiry_id}/reserve-commit` (plan 6e.4 re-keyed it from 6e.1's
   request-keyed path: rows resolve server-side to their open / latest answered request
   row inside `{inquiry_id}`), gated by `projects.order_inquiries.reserve` alone - the same grant the
   retired per-row `.../reserve` route used, never `ACKNOWLEDGE` (that stays purchasing's
   own grant to raise a request).
2. Payload: `{ "reserves": [{row_id, warehouse_id, qty_reserved, reason}],
   "amendments": [{row_id, qty_reserved, reason}] }`, both keys optional, at least one
   row across the two lists (an empty payload is 422).
3. Post-commit dispatch context: `reserve.rows` are ONLY the rows touched in THIS call
   (reserved or amended), each carrying `qty_reserved`, `balance` (plan 6e.1's own word -
   NOT `remaining`, the field name rounds 1/2's `_row_context` used for the per-row
   routes; the two are read at different moments and the plan gives the new one its own
   name) and `reason`; `reserve.row_count` is the WHOLE request's row count;
   `reserve.open_row_count` is what is left unanswered after this call. Dispatch fires
   ONCE per commit call - never gated on the whole request completing (R4-1, owner
   ruling 24 Sep: "the reserved mail goes out on every Reserve click"), which is the one
   respect this route's dispatch timing differs from the retired per-row route's own
   (AC-RS-57's `test_reserve_one_row_endpoint_answers_row_by_row`, "no email until EVERY
   row of the request is answered").
4. The service exposes ONE orchestration method for this, `OrderInquiryReserveService.
   commit_request(inquiry_id, reserves, amendments, actor_user_id)`, matching the
   existing request-level naming family (`create_request`, `cancel_request`) rather than
   the row-level one (`reserve_row`, `unreserve_row`) - this call spans every row of ONE
   request in ONE transaction, the same shape `create_request` already has. Needed only
   by AC-RS-82's rollback test, which (like AC-RS-21 before it) must call the service
   directly inside a manual savepoint rather than through the route, since the route
   commits its own transaction.
5. The reserved template's new line reads `{{ reserve.open_row_count }} line(s) still to
   reserve` (or equivalent Jinja producing that exact rendered English for N=1: "1 line
   still to reserve") when `open_row_count > 0`, and renders nothing when it is 0 - the
   plan's own words, section 6e.1 last sentence.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.models.base import company_scope
from app.models.project_so import (
    INQUIRY_PARTLY_LINKED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryReserveRequest,
    OrderInquiryReserveRequestRow,
    OrderInquiryRow,
)
from app.services.error_handler import AppException

from ._pg_fixture import blank_session
from .test_order_inquiry_reserve import (
    CANCEL_URL,
    REQUESTER_PERMISSIONS,
    REQUEST_URL,
    ROW_HISTORY_URL,
    ROW_RESERVE_URL,
    ROW_UNRESERVE_URL,
    _as,
    _captured_dispatches,
    _load_reserve_seed_migration,
    _open_row,
    _pso,
    _register,
    _reserve_fixture_context,
    _reserved_calls,
    api as reserve_api,  # noqa: F401  (re-exported fixture: both permissions)
)
from .test_order_inquiry_worklist import (
    LIST,
    _inquiry_for,
    MARKER as WL_MARKER,
    _line_on_authored_order,
    _purchase_order,
    _row,
    _uid,
    _user,
    api as worklist_api,  # noqa: F401  (re-exported fixture; header lines + worklist reader)
)
from .test_planning_changes import _warehouse

MARKER = "zzt-oi-reserve-commit"

COMMIT_URL = lambda inquiry_id: f"{LIST}/{inquiry_id}/reserve-commit"  # noqa: E731


# --------------------------------------------------------------------------------- #
# AC-RS-76                                                                           #
# --------------------------------------------------------------------------------- #


def test_AC_RS_76_commit_two_of_three_rows_one_dispatch(reserve_api, monkeypatch):
    client, world = reserve_api
    _register()
    calls = _captured_dispatches(monkeypatch)

    row_a = _open_row(world, qty="50", item_code=f"{MARKER}-A")
    row_b = _open_row(world, qty="30", item_code=f"{MARKER}-B")
    row_c = _open_row(world, qty="20", item_code=f"{MARKER}-C")

    created = client.post(
        REQUEST_URL(world.inquiry.id),
        json={
            "rows": [
                {"row_id": row_a.id, "qty_requested": "50"},
                {"row_id": row_b.id, "qty_requested": "30"},
                {"row_id": row_c.id, "qty_requested": "20"},
            ]
        },
    )
    assert created.status_code == 201, created.text
    world.db.commit()
    request_id = created.json()["id"]

    response = client.post(
        COMMIT_URL(world.inquiry.id),
        json={
            "reserves": [
                {"row_id": row_a.id, "warehouse_id": world.site.id, "qty_reserved": "50"},
                {
                    "row_id": row_b.id,
                    "warehouse_id": world.site.id,
                    "qty_reserved": "20",
                    "reason": "BRW only has 20",
                },
            ]
        },
    )
    assert response.status_code == 200, response.text
    world.db.commit()

    from app.models.project_so import OrderInquiryReserveRequest, OrderInquiryReserveRequestRow

    world.db.expire_all()
    rr_by_row = {
        rr.row_id: rr
        for rr in world.db.query(OrderInquiryReserveRequestRow)
        .filter(OrderInquiryReserveRequestRow.request_id == request_id)
        .all()
    }

    assert rr_by_row[row_a.id].qty_reserved == Decimal("50")
    assert rr_by_row[row_b.id].qty_reserved == Decimal("20")
    assert rr_by_row[row_c.id].qty_reserved is None, "the third row must stay open"

    link_count = (
        world.db.query(OrderInquiryLink)
        .filter(
            OrderInquiryLink.reserve_request_row_id.in_(
                [rr_by_row[row_a.id].id, rr_by_row[row_b.id].id]
            )
        )
        .count()
    )
    assert link_count == 2, "two reserve links, one per committed row"

    reserved_events = world.db.execute(
        sa.text(
            "SELECT count(*) FROM order_inquiry_reserve_events "
            "WHERE reserve_request_row_id IN (:a, :b) AND kind = 'reserved'"
        ),
        {"a": rr_by_row[row_a.id].id, "b": rr_by_row[row_b.id].id},
    ).scalar()
    assert reserved_events == 2, "two 'reserved' events, one per committed row"

    request = (
        world.db.query(OrderInquiryReserveRequest)
        .filter(OrderInquiryReserveRequest.id == request_id)
        .one()
    )
    assert request.state == "requested", "the request stays open while row_c is unanswered"

    refreshed_a = world.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row_a.id).one()
    assert refreshed_a.state == INQUIRY_PLACED, "refresh_link_state must have run for row_a"
    refreshed_b = world.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row_b.id).one()
    assert refreshed_b.state == INQUIRY_PARTLY_LINKED, "refresh_link_state must have run for row_b"

    matches = _reserved_calls(calls)
    assert len(matches) == 1, f"exactly ONE dispatch after commit, got {len(matches)}"
    reserve_ctx = matches[0]["context"]["reserve"]
    assert reserve_ctx["open_row_count"] == 1, reserve_ctx
    assert reserve_ctx["row_count"] == 3, reserve_ctx
    touched_rows = reserve_ctx["rows"]
    assert len(touched_rows) == 2, (
        f"reserve.rows must be ONLY the two rows touched this call: {touched_rows}"
    )
    touched_item_codes = {r["item_code"] for r in touched_rows}
    assert touched_item_codes == {row_a.item_code, row_b.item_code}, touched_item_codes
    for entry in touched_rows:
        assert "qty_reserved" in entry, entry
        assert "balance" in entry, (
            "PLAN-oi-request-cs-reserve.md 6e.1: reserve.rows carries "
            f"qty_reserved/balance/reason: {entry}"
        )
        assert "reason" in entry, entry


# --------------------------------------------------------------------------------- #
# AC-RS-76b (fix, not in the tester's original list): a partial `commit_request` call #
# must not leave the ALREADY-answered row reading `requested`.                        #
# --------------------------------------------------------------------------------- #


def test_AC_RS_76b_partial_commit_answered_row_reads_reserved(worklist_api):
    """`PLAN-oi-request-cs-reserve.md` 6e.1 / AC-RS-76: committing ONE row of a two-row
    request must not leave the ALREADY-answered row reading `requested` on the header
    lines / worklist just because its sibling keeps the whole request `requested`.
    `_HAS_OPEN_RESERVE_REQUEST`/`_OPEN_REQUEST_QTY` (`order_inquiry_worklist_service.py`)
    used to key off the request's own `state` alone, an accurate proxy while rounds 1-3's
    per-row route answered every row of a request in lockstep; `commit_request` breaks
    that lockstep (a partial commit answers SOME rows while the request stays
    `requested` until its LAST row is done), so the two need the row's OWN `qty_reserved
    IS NULL` on top of the request state. Runs `commit_request` itself (the route the
    Lines grid now calls), not the legacy `reserve_row` `test_reserve_state_derived`
    (above, in `test_order_inquiry_reserve.py`) already covers.
    """
    client, db, company_id, seeded = worklist_api
    inquiry = db.get(OrderInquiry, seeded["authored_row"].order_inquiry_id)
    line_a = _line_on_authored_order(db, company_id, seeded, qty="50", day=8)
    line_b = _line_on_authored_order(db, company_id, seeded, qty="30", day=9)
    row_a = _row(
        db,
        company_id,
        inquiry,
        so_line_id=line_a.id,
        item_code=f"{WL_MARKER}-PARTIAL-A",
        qty="50",
        state=INQUIRY_RAISED,
        delivery_date=date(2026, 4, 8),
    )
    row_b = _row(
        db,
        company_id,
        inquiry,
        so_line_id=line_b.id,
        item_code=f"{WL_MARKER}-PARTIAL-B",
        qty="30",
        state=INQUIRY_RAISED,
        delivery_date=date(2026, 4, 9),
    )
    db.commit()

    warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}".upper())
    from app.services.order_inquiry_reserve_service import OrderInquiryReserveService

    requester_id = _user(db, f"{WL_MARKER} requester3")
    service = OrderInquiryReserveService(db)
    request = service.create_request(
        inquiry_id=inquiry.id,
        rows=[
            {"row_id": row_a.id, "qty_requested": Decimal("50"), "warehouse_id": warehouse.id},
            {"row_id": row_b.id, "qty_requested": Decimal("30"), "warehouse_id": warehouse.id},
        ],
        note=None,
        actor_user_id=requester_id,
    )
    db.commit()

    reserver_id = _user(db, f"{WL_MARKER} reserver3")
    service.commit_request(
        inquiry_id=inquiry.id,
        reserves=[{"row_id": row_a.id, "warehouse_id": warehouse.id, "qty_reserved": Decimal("50")}],
        amendments=[],
        actor_user_id=reserver_id,
    )
    db.commit()

    db.expire_all()
    reloaded_request = (
        db.query(OrderInquiryReserveRequest).filter(OrderInquiryReserveRequest.id == request.id).one()
    )
    assert reloaded_request.state == "requested", "row_b is still open, the request must stay open"

    body = client.get(LIST, params={"delivery_month": "2026-04"}).json()
    entry_a = next(e for e in body["data"] if e["id"] == row_a.id)
    entry_b = next(e for e in body["data"] if e["id"] == row_b.id)

    assert entry_a["reserve_state"] == "reserved", (
        "row_a is already answered - it must read reserved, not requested, even though "
        f"its sibling row_b keeps the request itself requested: {entry_a}"
    )
    assert entry_a["requested_qty"] == "0", entry_a
    assert entry_a["reserved_qty"] == "50", entry_a

    assert entry_b["reserve_state"] == "requested", entry_b
    assert entry_b["requested_qty"] == "30", entry_b


# --------------------------------------------------------------------------------- #
# AC-RS-77                                                                           #
# --------------------------------------------------------------------------------- #


def test_AC_RS_77_completes_conflict_404_422_and_atomicity(reserve_api):
    client, world = reserve_api

    row = _open_row(world, qty="50", item_code=f"{MARKER}-LAST")
    created = client.post(
        REQUEST_URL(world.inquiry.id), json={"rows": [{"row_id": row.id, "qty_requested": "50"}]}
    )
    assert created.status_code == 201, created.text
    world.db.commit()
    request_id = created.json()["id"]

    completed = client.post(
        COMMIT_URL(world.inquiry.id),
        json={"reserves": [{"row_id": row.id, "warehouse_id": world.site.id, "qty_reserved": "50"}]},
    )
    assert completed.status_code == 200, completed.text
    world.db.commit()

    from app.models.project_so import OrderInquiryReserveRequest

    world.db.expire_all()
    request = (
        world.db.query(OrderInquiryReserveRequest)
        .filter(OrderInquiryReserveRequest.id == request_id)
        .one()
    )
    assert request.state == "reserved", "the last open row must flip the request"
    assert request.reserved_by is not None
    assert request.reserved_at is not None

    # Committing again with an already-answered row -> 409 naming it.
    again = client.post(
        COMMIT_URL(world.inquiry.id),
        json={"reserves": [{"row_id": row.id, "warehouse_id": world.site.id, "qty_reserved": "10"}]},
    )
    assert again.status_code == 409, again.text
    assert row.item_code in again.text, (
        f"the 409 must NAME the offending row, not a generic message: {again.text}"
    )

    # A row of ANOTHER inquiry (same company) -> 404 (AC-RS-77b): the route is keyed by
    # inquiry and resolves every row inside it, never a row of a sibling header.
    other_inquiry = _inquiry_for(world.db, world.company_id, _pso(world.db, world.company_id))
    world.db.commit()
    other_row = _row(
        world.db, world.company_id, other_inquiry, qty="10", item_code=f"{MARKER}-OTHER",
        state=INQUIRY_RAISED, stock_location=world.site.warehouse_code,
    )
    world.db.commit()
    other_request = client.post(
        REQUEST_URL(other_inquiry.id), json={"rows": [{"row_id": other_row.id, "qty_requested": "10"}]}
    )
    assert other_request.status_code == 201, other_request.text
    world.db.commit()
    wrong = client.post(
        COMMIT_URL(world.inquiry.id),
        json={
            "reserves": [
                {"row_id": other_row.id, "warehouse_id": world.site.id, "qty_reserved": "10"}
            ]
        },
    )
    assert wrong.status_code == 404, wrong.text

    # An empty payload is 422.
    empty = client.post(COMMIT_URL(world.inquiry.id), json={})
    assert empty.status_code == 422, empty.text

    # Atomicity: a short row without a reason in a batch of two leaves BOTH unwritten.
    row_x = _open_row(world, qty="50", item_code=f"{MARKER}-X")
    row_y = _open_row(world, qty="30", item_code=f"{MARKER}-Y")
    batch_request = client.post(
        REQUEST_URL(world.inquiry.id),
        json={
            "rows": [
                {"row_id": row_x.id, "qty_requested": "50"},
                {"row_id": row_y.id, "qty_requested": "30"},
            ]
        },
    )
    assert batch_request.status_code == 201, batch_request.text
    world.db.commit()
    batch_request_id = batch_request.json()["id"]

    batch = client.post(
        COMMIT_URL(world.inquiry.id),
        json={
            "reserves": [
                {"row_id": row_x.id, "warehouse_id": world.site.id, "qty_reserved": "50"},
                {"row_id": row_y.id, "warehouse_id": world.site.id, "qty_reserved": "10"},
            ]
        },
    )
    assert batch.status_code == 422, batch.text

    from app.models.project_so import OrderInquiryReserveRequestRow

    world.db.expire_all()
    rr_x = (
        world.db.query(OrderInquiryReserveRequestRow)
        .filter(
            OrderInquiryReserveRequestRow.request_id == batch_request_id,
            OrderInquiryReserveRequestRow.row_id == row_x.id,
        )
        .one()
    )
    rr_y = (
        world.db.query(OrderInquiryReserveRequestRow)
        .filter(
            OrderInquiryReserveRequestRow.request_id == batch_request_id,
            OrderInquiryReserveRequestRow.row_id == row_y.id,
        )
        .one()
    )
    assert rr_x.qty_reserved is None, "row_x must be untouched - the batch is atomic"
    assert rr_y.qty_reserved is None, "row_y must be untouched - the batch is atomic"
    assert (
        world.db.query(OrderInquiryLink)
        .filter(OrderInquiryLink.reserve_request_row_id.in_([rr_x.id, rr_y.id]))
        .count()
        == 0
    ), "no link may be written for either row when the batch fails validation"


# --------------------------------------------------------------------------------- #
# AC-RS-78                                                                           #
# --------------------------------------------------------------------------------- #


def test_AC_RS_78_amendments_lower_raise_zero_reason_and_open_row_guard(reserve_api):
    client, world = reserve_api

    row = _open_row(world, qty="100", item_code=f"{MARKER}-AMEND")
    created = client.post(
        REQUEST_URL(world.inquiry.id),
        json={"rows": [{"row_id": row.id, "qty_requested": "50"}]},
    )
    assert created.status_code == 201, created.text
    world.db.commit()
    request_id = created.json()["id"]

    # Initial reserve (full 50 of 50) via the commit route's own `reserves` list.
    first = client.post(
        COMMIT_URL(world.inquiry.id),
        json={
            "reserves": [
                {"row_id": row.id, "warehouse_id": world.site.id, "qty_reserved": "50"}
            ]
        },
    )
    assert first.status_code == 200, first.text
    world.db.commit()

    from app.models.project_so import OrderInquiryReserveRequestRow

    def _rr_and_link():
        world.db.expire_all()
        rr = (
            world.db.query(OrderInquiryReserveRequestRow)
            .filter(
                OrderInquiryReserveRequestRow.request_id == request_id,
                OrderInquiryReserveRequestRow.row_id == row.id,
            )
            .one()
        )
        link = (
            world.db.query(OrderInquiryLink)
            .filter(OrderInquiryLink.reserve_request_row_id == rr.id)
            .first()
        )
        return rr, link

    def _event_count(kind, qty):
        rr, _ = _rr_and_link()
        return world.db.execute(
            sa.text(
                "SELECT count(*) FROM order_inquiry_reserve_events "
                "WHERE reserve_request_row_id = :rr AND kind = :kind AND qty = :qty"
            ),
            {"rr": rr.id, "kind": kind, "qty": str(qty)},
        ).scalar()

    rr, link = _rr_and_link()
    assert link is not None and link.qty == Decimal("50")

    # Lowering 50 -> 30 (short of requested 50): reason required, one unreserved
    # event of 20.
    lower = client.post(
        COMMIT_URL(world.inquiry.id),
        json={
            "amendments": [
                {"row_id": row.id, "qty_reserved": "30", "reason": "transferred back"}
            ]
        },
    )
    assert lower.status_code == 200, lower.text
    world.db.commit()
    rr, link = _rr_and_link()
    assert link.qty == Decimal("30"), link.qty
    assert _event_count("unreserved", "20") == 1

    # Raising 30 -> 45 (<= requested 50, still short so a reason is required): one
    # reserved event of 15.
    raise_ = client.post(
        COMMIT_URL(world.inquiry.id),
        json={
            "amendments": [
                {"row_id": row.id, "qty_reserved": "45", "reason": "more became available"}
            ]
        },
    )
    assert raise_.status_code == 200, raise_.text
    world.db.commit()
    rr, link = _rr_and_link()
    assert link.qty == Decimal("45"), link.qty
    assert _event_count("reserved", "15") == 1

    # 0: deletes the link, writes one unreserved event of the net (45).
    zero = client.post(
        COMMIT_URL(world.inquiry.id),
        json={"amendments": [{"row_id": row.id, "qty_reserved": "0", "reason": "none left"}]},
    )
    assert zero.status_code == 200, zero.text
    world.db.commit()
    rr, link = _rr_and_link()
    assert link is None, "amending to 0 must delete the link"
    assert _event_count("unreserved", "45") == 1

    refreshed_row = world.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row.id).one()
    assert refreshed_row.state == INQUIRY_RAISED, (
        "unreserving everything via an amendment must restore the row's own state"
    )

    # Above qty_requested (50) is 422.
    above = client.post(
        COMMIT_URL(world.inquiry.id),
        json={"amendments": [{"row_id": row.id, "qty_reserved": "51"}]},
    )
    assert above.status_code == 422, above.text

    # Short of requested with no reason is 422.
    short_no_reason = client.post(
        COMMIT_URL(world.inquiry.id),
        json={"amendments": [{"row_id": row.id, "qty_reserved": "10"}]},
    )
    assert short_no_reason.status_code == 422, short_no_reason.text

    # An amendment on an OPEN row (never answered) is 422.
    open_row = _open_row(world, qty="20", item_code=f"{MARKER}-OPEN")
    open_request = client.post(
        REQUEST_URL(world.inquiry.id),
        json={"rows": [{"row_id": open_row.id, "qty_requested": "20"}]},
    )
    assert open_request.status_code == 201, open_request.text
    world.db.commit()
    # Reviewer B4: a reason is sent so the reason rule cannot be what rejects it - the
    # open-row guard alone must, and the error code proves which rule fired.
    on_open = client.post(
        COMMIT_URL(world.inquiry.id),
        json={
            "amendments": [
                {"row_id": open_row.id, "qty_reserved": "5", "reason": "only 5 on hand"}
            ]
        },
    )
    assert on_open.status_code == 422, on_open.text
    assert on_open.json()["code"] == "reserve_amend_not_reserved", on_open.text
    assert open_row.item_code in on_open.text, on_open.text

    # Taken/Remaining follow - the worklist reader, the same field set AC-RS-12's own
    # `test_taken_remaining_include_reserved` reads (`reserved_qty`).
    listing = client.get(LIST, params={"query": row.item_code}).json()
    by_id = {entry["id"]: entry for entry in listing["data"]}
    assert row.id in by_id, listing
    assert by_id[row.id]["reserved_qty"] in (None, "0"), by_id[row.id]


# --------------------------------------------------------------------------------- #
# AC-RS-79                                                                           #
# --------------------------------------------------------------------------------- #


def test_AC_RS_79_permission_retired_routes_deferred_action_and_history(reserve_api):
    client, world = reserve_api
    row = _open_row(world, qty="50", item_code=f"{MARKER}-PERM")
    created = client.post(
        REQUEST_URL(world.inquiry.id), json={"rows": [{"row_id": row.id, "qty_requested": "50"}]}
    )
    assert created.status_code == 201, created.text
    world.db.commit()
    request_id = created.json()["id"]

    # 403 without the reserve permission.
    with _as(world.db, world.requester, REQUESTER_PERMISSIONS) as stranger:
        forbidden = stranger.post(
            COMMIT_URL(world.inquiry.id),
            json={
                "reserves": [
                    {"row_id": row.id, "warehouse_id": world.site.id, "qty_reserved": "50"}
                ]
            },
        )
    assert forbidden.status_code == 403, forbidden.text

    # The two old per-row routes are retired.
    old_reserve = client.post(
        ROW_RESERVE_URL(request_id, row.id),
        json={"warehouse_id": world.site.id, "qty_reserved": "50"},
    )
    assert old_reserve.status_code == 404, old_reserve.text

    old_unreserve = client.post(ROW_UNRESERVE_URL(request_id, row.id), json={"qty": "10"})
    assert old_unreserve.status_code == 404, old_unreserve.text

    # The deferred action is no longer registered.
    from app.services.form_action_registry import get_action

    assert get_action("order_inquiry_reserve_row.unreserve") is None, (
        "6e.1: the per-row unreserve deferred action is removed with the retired route"
    )

    # History still lists requested / reserved / unreserved / cancelled, newest first.
    reserved = client.post(
        COMMIT_URL(world.inquiry.id),
        json={"reserves": [{"row_id": row.id, "warehouse_id": world.site.id, "qty_reserved": "50"}]},
    )
    assert reserved.status_code == 200, reserved.text
    world.db.commit()
    lowered = client.post(
        COMMIT_URL(world.inquiry.id),
        json={"amendments": [{"row_id": row.id, "qty_reserved": "40", "reason": "10 went back"}]},
    )
    assert lowered.status_code == 200, lowered.text
    world.db.commit()
    history = client.get(ROW_HISTORY_URL(request_id, row.id))
    assert history.status_code == 200, history.text
    kinds = [entry["kind"] for entry in history.json()]
    assert kinds == ["unreserved", "reserved", "requested"], history.json()
    qtys = [entry["qty"] for entry in history.json()]
    assert qtys == ["10", "50", "50"], history.json()


# --------------------------------------------------------------------------------- #
# AC-RS-80                                                                           #
# --------------------------------------------------------------------------------- #


def test_AC_RS_80_reserved_template_open_row_count_line():
    from app.models.email_template import EmailTemplate
    from app.services.email_template_service import EmailTemplateService

    module = _load_reserve_seed_migration()
    with blank_session() as db:
        ctx = MigrationContext.configure(db.connection())
        with Operations.context(ctx):
            module.upgrade()

        reserved_template = (
            db.query(EmailTemplate)
            .filter(EmailTemplate.code == "order_inquiry_reserved_default")
            .one()
        )

        partial_context = _reserve_fixture_context()
        partial_context["reserve"]["open_row_count"] = 1
        partial_rendered = EmailTemplateService(db).render(reserved_template, partial_context)
        partial_html = partial_rendered["body_html"]

        for row in partial_context["reserve"]["rows"]:
            assert row["item_code"] in partial_html, partial_html

        assert "1 line still to reserve" in partial_html, (
            "PLAN-oi-request-cs-reserve.md 6e.1: a partial commit's own reserved mail "
            f"carries 'N line(s) still to reserve': {partial_html}"
        )

        completing_context = _reserve_fixture_context()
        completing_context["reserve"]["open_row_count"] = 0
        completing_rendered = EmailTemplateService(db).render(reserved_template, completing_context)
        completing_html = completing_rendered["body_html"]
        assert "still to reserve" not in completing_html, (
            f"a completing commit must carry no such line: {completing_html}"
        )


# --------------------------------------------------------------------------------- #
# AC-RS-81                                                                           #
# --------------------------------------------------------------------------------- #


def test_AC_RS_81_two_sequential_commits_send_two_mails_each_own_rows(reserve_api, monkeypatch):
    client, world = reserve_api
    _register()
    calls = _captured_dispatches(monkeypatch)

    row_a = _open_row(world, qty="50", item_code=f"{MARKER}-SEQA")
    row_b = _open_row(world, qty="30", item_code=f"{MARKER}-SEQB")
    created = client.post(
        REQUEST_URL(world.inquiry.id),
        json={
            "rows": [
                {"row_id": row_a.id, "qty_requested": "50"},
                {"row_id": row_b.id, "qty_requested": "30"},
            ]
        },
    )
    assert created.status_code == 201, created.text
    world.db.commit()
    request_id = created.json()["id"]

    first = client.post(
        COMMIT_URL(world.inquiry.id),
        json={
            "reserves": [
                {"row_id": row_a.id, "warehouse_id": world.site.id, "qty_reserved": "50"}
            ]
        },
    )
    assert first.status_code == 200, first.text
    world.db.commit()

    first_matches = _reserved_calls(calls)
    assert len(first_matches) == 1, first_matches
    assert first_matches[0]["source_id"] == request_id, first_matches
    first_rows = first_matches[0]["context"]["reserve"]["rows"]
    assert {r["item_code"] for r in first_rows} == {row_a.item_code}, first_rows

    second = client.post(
        COMMIT_URL(world.inquiry.id),
        json={
            "reserves": [
                {"row_id": row_b.id, "warehouse_id": world.site.id, "qty_reserved": "30"}
            ]
        },
    )
    assert second.status_code == 200, second.text
    world.db.commit()

    all_matches = _reserved_calls(calls)
    assert len(all_matches) == 2, all_matches
    second_rows = all_matches[1]["context"]["reserve"]["rows"]
    assert {r["item_code"] for r in second_rows} == {row_b.item_code}, second_rows


# --------------------------------------------------------------------------------- #
# AC-RS-82                                                                           #
# --------------------------------------------------------------------------------- #


def test_AC_RS_82_rollback_dispatches_nothing(reserve_api, monkeypatch):
    client, world = reserve_api
    _register()
    calls = _captured_dispatches(monkeypatch)

    row = _open_row(world, qty="50", item_code=f"{MARKER}-RB")
    created = client.post(
        REQUEST_URL(world.inquiry.id), json={"rows": [{"row_id": row.id, "qty_requested": "50"}]}
    )
    assert created.status_code == 201, created.text
    world.db.commit()
    request_id = created.json()["id"]

    from app.services.order_inquiry_reserve_service import OrderInquiryReserveService

    savepoint = world.db.begin_nested()
    service = OrderInquiryReserveService(world.db)
    service.commit_request(
        inquiry_id=world.inquiry.id,
        reserves=[{"row_id": row.id, "warehouse_id": world.site.id, "qty_reserved": "50"}],
        amendments=[],
        actor_user_id=world.reserver,
    )
    savepoint.rollback()

    world.db.commit()  # an unrelated commit: nothing above may still fire

    assert _reserved_calls(calls) == [], "a rolled-back commit must dispatch nothing"

    from app.models.project_so import OrderInquiryReserveRequestRow

    world.db.expire_all()
    rr = (
        world.db.query(OrderInquiryReserveRequestRow)
        .filter(
            OrderInquiryReserveRequestRow.request_id == request_id,
            OrderInquiryReserveRequestRow.row_id == row.id,
        )
        .one()
    )
    assert rr.qty_reserved is None, "the rolled-back reserve must not exist either"


# --------------------------------------------------------------------------------- #
# Review round (plan 6e.4): AC-RS-76c, 77b, 78b, 78c, 79b and the coverage the       #
# retired `reserve_row` tests carried                                                #
# --------------------------------------------------------------------------------- #


def _request(client, world, *rows):
    """`rows` = `(row, qty_requested)` pairs; returns the request id."""
    created = client.post(
        REQUEST_URL(world.inquiry.id),
        json={"rows": [{"row_id": row.id, "qty_requested": qty} for row, qty in rows]},
    )
    assert created.status_code == 201, created.text
    world.db.commit()
    return created.json()["id"]


def _rr(world, request_id, row):
    world.db.expire_all()
    return (
        world.db.query(OrderInquiryReserveRequestRow)
        .filter(
            OrderInquiryReserveRequestRow.request_id == request_id,
            OrderInquiryReserveRequestRow.row_id == row.id,
        )
        .one()
    )


def _events(world, rr_id):
    return world.db.execute(
        sa.text(
            "SELECT kind, qty FROM order_inquiry_reserve_events "
            "WHERE reserve_request_row_id = :rr ORDER BY created_at"
        ),
        {"rr": rr_id},
    ).all()


def test_AC_RS_76c_duplicate_row_is_422_before_any_read(reserve_api):
    client, world = reserve_api
    # Ids that name NO row at all: a 404 would prove the service read before refusing.
    ghost = str(uuid.uuid4())

    twice_in_reserves = client.post(
        COMMIT_URL(world.inquiry.id),
        json={
            "reserves": [
                {"row_id": ghost, "qty_reserved": "1"},
                {"row_id": ghost, "qty_reserved": "2"},
            ]
        },
    )
    assert twice_in_reserves.status_code == 422, twice_in_reserves.text
    assert twice_in_reserves.json()["code"] == "reserve_commit_duplicate_row", twice_in_reserves.text

    in_both_lists = client.post(
        COMMIT_URL(world.inquiry.id),
        json={
            "reserves": [{"row_id": ghost, "qty_reserved": "1"}],
            "amendments": [{"row_id": ghost, "qty_reserved": "1"}],
        },
    )
    assert in_both_lists.status_code == 422, in_both_lists.text
    assert in_both_lists.json()["code"] == "reserve_commit_duplicate_row", in_both_lists.text


def test_AC_RS_77b_row_resolution_404_409_422(reserve_api):
    from .test_order_inquiry_reserve_round2 import _foreign_reserve_request

    client, world = reserve_api
    _foreign_request_id, foreign_row_id, foreign_inquiry_id = _foreign_reserve_request(world.db)

    row = _open_row(world, qty="20", item_code=f"{MARKER}-RESOLVE")
    _request(client, world, (row, "20"))

    # A foreign-company inquiry in the URL: 404, nothing written.
    foreign_inquiry = client.post(
        COMMIT_URL(foreign_inquiry_id),
        json={"reserves": [{"row_id": row.id, "qty_reserved": "20"}]},
    )
    assert foreign_inquiry.status_code == 404, foreign_inquiry.text

    # A foreign-company row under the caller's own inquiry: 404.
    foreign_row = client.post(
        COMMIT_URL(world.inquiry.id),
        json={"reserves": [{"row_id": foreign_row_id, "qty_reserved": "10"}]},
    )
    assert foreign_row.status_code == 404, foreign_row.text

    # `reserves` on a row nobody ever requested: no open request row, 409 naming it.
    never_requested = _open_row(world, qty="20", item_code=f"{MARKER}-NEVER")
    no_open = client.post(
        COMMIT_URL(world.inquiry.id),
        json={"reserves": [{"row_id": never_requested.id, "qty_reserved": "20"}]},
    )
    assert no_open.status_code == 409, no_open.text
    assert never_requested.item_code in no_open.text, no_open.text

    # `amendments` on a row with no answered request row: 422 naming it.
    no_answer = client.post(
        COMMIT_URL(world.inquiry.id),
        json={"amendments": [{"row_id": never_requested.id, "qty_reserved": "5", "reason": "x"}]},
    )
    assert no_answer.status_code == 422, no_answer.text
    assert no_answer.json()["code"] == "reserve_amend_not_reserved", no_answer.text
    assert never_requested.item_code in no_answer.text, no_answer.text

    world.db.expire_all()
    assert (
        world.db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id == row.id).count() == 0
    ), "every refusal above must write nothing"


def test_AC_RS_78b_amend_up_cap_declined_row_and_no_op(reserve_api, monkeypatch):
    client, world = reserve_api
    _register()
    calls = _captured_dispatches(monkeypatch)

    # Row qty 100, requested in full, reserved 10; a PO link then covers 80 more, so the
    # row's live remaining is 10 and the amend-up cap is 10 + 10 = 20.
    row = _open_row(world, qty="100", item_code=f"{MARKER}-CAP")
    request_id = _request(client, world, (row, "100"))
    first = client.post(
        COMMIT_URL(world.inquiry.id),
        json={"reserves": [{"row_id": row.id, "qty_reserved": "10", "reason": "BRW has 10"}]},
    )
    assert first.status_code == 200, first.text
    world.db.commit()
    po_line = _purchase_order(world.db, world.company_id)["line"]
    world.db.add(
        OrderInquiryLink(
            id=_uid(), company_id=world.company_id, row_id=row.id,
            po_line_id=po_line.id, document="ZZT-PO-80", qty=Decimal("80"),
        )
    )
    world.db.commit()

    over = client.post(
        COMMIT_URL(world.inquiry.id),
        json={"amendments": [{"row_id": row.id, "qty_reserved": "100"}]},
    )
    assert over.status_code == 422, over.text
    assert over.json()["code"] == "reserve_amend_qty_out_of_range", over.text
    assert row.item_code in over.text and "20" in over.text, over.text

    up_to_cap = client.post(
        COMMIT_URL(world.inquiry.id),
        json={"amendments": [{"row_id": row.id, "qty_reserved": "20", "reason": "10 more found"}]},
    )
    assert up_to_cap.status_code == 200, up_to_cap.text
    world.db.commit()
    rr = _rr(world, request_id, row)
    link = (
        world.db.query(OrderInquiryLink)
        .filter(OrderInquiryLink.reserve_request_row_id == rr.id)
        .one()
    )
    assert link.qty == Decimal("20"), link.qty
    total = (
        world.db.query(sa.func.sum(OrderInquiryLink.qty))
        .filter(OrderInquiryLink.row_id == row.id)
        .scalar()
    )
    assert Decimal(str(total)) == Decimal("100"), "links never exceed the row's own qty"

    # No-op: the same qty again touches nothing - no event, no mail, reason untouched.
    events_before = len(_events(world, rr.id))
    calls.clear()
    no_op = client.post(
        COMMIT_URL(world.inquiry.id),
        json={"amendments": [{"row_id": row.id, "qty_reserved": "20", "reason": "changed my mind"}]},
    )
    assert no_op.status_code == 200, no_op.text
    world.db.commit()
    rr = _rr(world, request_id, row)
    assert len(_events(world, rr.id)) == events_before, _events(world, rr.id)
    assert rr.reason == "10 more found", rr.reason
    assert _reserved_calls(calls) == [], "a no-op amendment sends no mail"

    # A declined row (Reserve 0) amended up to 15 re-creates the link and writes a
    # `reserved` event of 15.
    declined = _open_row(world, qty="50", item_code=f"{MARKER}-DECL")
    declined_request_id = _request(client, world, (declined, "50"))
    zero = client.post(
        COMMIT_URL(world.inquiry.id),
        json={"reserves": [{"row_id": declined.id, "qty_reserved": "0", "reason": "none on hand"}]},
    )
    assert zero.status_code == 200, zero.text
    world.db.commit()
    up = client.post(
        COMMIT_URL(world.inquiry.id),
        json={"amendments": [{"row_id": declined.id, "qty_reserved": "15", "reason": "15 came in"}]},
    )
    assert up.status_code == 200, up.text
    world.db.commit()
    declined_rr = _rr(world, declined_request_id, declined)
    assert declined_rr.qty_reserved == Decimal("15")
    declined_link = (
        world.db.query(OrderInquiryLink)
        .filter(OrderInquiryLink.reserve_request_row_id == declined_rr.id)
        .one()
    )
    assert declined_link.qty == Decimal("15")
    assert [(kind, Decimal(str(qty))) for kind, qty in _events(world, declined_rr.id)] == [
        ("reserved", Decimal("0")),
        ("reserved", Decimal("15")),
    ]


def test_AC_RS_78c_declined_state_and_reserve_zero_event(worklist_api):
    client, db, company_id, seeded = worklist_api
    inquiry = db.get(OrderInquiry, seeded["authored_row"].order_inquiry_id)
    line = _line_on_authored_order(db, company_id, seeded, qty="40", day=11)
    row = _row(
        db, company_id, inquiry, so_line_id=line.id, item_code=f"{WL_MARKER}-DECLINED",
        qty="40", state=INQUIRY_RAISED, delivery_date=date(2026, 4, 11),
    )
    db.commit()
    warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}".upper())
    from app.services.order_inquiry_reserve_service import OrderInquiryReserveService

    service = OrderInquiryReserveService(db)
    requester_id = _user(db, f"{WL_MARKER} requester-decl")
    request = service.create_request(
        inquiry_id=inquiry.id,
        rows=[{"row_id": row.id, "qty_requested": Decimal("40"), "warehouse_id": warehouse.id}],
        note=None,
        actor_user_id=requester_id,
    )
    db.commit()
    service.commit_request(
        inquiry_id=inquiry.id,
        reserves=[{"row_id": row.id, "qty_reserved": "0", "reason": "nothing on hand"}],
        amendments=[],
        actor_user_id=_user(db, f"{WL_MARKER} reserver-decl"),
    )
    db.commit()

    rr = (
        db.query(OrderInquiryReserveRequestRow)
        .filter(OrderInquiryReserveRequestRow.request_id == request.id)
        .one()
    )
    events = db.execute(
        sa.text(
            "SELECT kind, qty FROM order_inquiry_reserve_events WHERE reserve_request_row_id = :rr"
        ),
        {"rr": rr.id},
    ).all()
    assert [(kind, Decimal(str(qty))) for kind, qty in events] == [("reserved", Decimal("0"))], (
        f"Reserve 0 writes one `reserved` event of 0 so History shows the decision: {events}"
    )

    body = client.get(LIST, params={"delivery_month": "2026-04"}).json()
    entry = next(e for e in body["data"] if e["id"] == row.id)
    assert entry["reserve_state"] == "declined", entry

    # An open request row still wins over the declined answer.
    service.create_request(
        inquiry_id=inquiry.id,
        rows=[{"row_id": row.id, "qty_requested": Decimal("40"), "warehouse_id": warehouse.id}],
        note=None,
        actor_user_id=requester_id,
    )
    db.commit()
    body = client.get(LIST, params={"delivery_month": "2026-04"}).json()
    entry = next(e for e in body["data"] if e["id"] == row.id)
    assert entry["reserve_state"] == "requested", entry


def test_AC_RS_79b_cancel_partly_answered_two_requests_and_rerequest(reserve_api, monkeypatch):
    client, world = reserve_api
    _register()
    calls = _captured_dispatches(monkeypatch)

    # Cancel a partly answered request: open rows withdrawn, answered rows keep links.
    row_a = _open_row(world, qty="50", item_code=f"{MARKER}-CXA")
    row_b = _open_row(world, qty="30", item_code=f"{MARKER}-CXB")
    request_id = _request(client, world, (row_a, "50"), (row_b, "30"))
    answered = client.post(
        COMMIT_URL(world.inquiry.id),
        json={"reserves": [{"row_id": row_a.id, "qty_reserved": "50"}]},
    )
    assert answered.status_code == 200, answered.text
    world.db.commit()
    cancelled = client.post(CANCEL_URL(request_id))
    assert cancelled.status_code == 200, cancelled.text
    world.db.commit()
    world.db.expire_all()
    assert (
        world.db.query(OrderInquiryReserveRequest)
        .filter(OrderInquiryReserveRequest.id == request_id)
        .one()
        .state
        == "cancelled"
    )
    assert _rr(world, request_id, row_b).qty_reserved is None
    rr_a = _rr(world, request_id, row_a)
    assert (
        world.db.query(OrderInquiryLink)
        .filter(OrderInquiryLink.reserve_request_row_id == rr_a.id)
        .count()
        == 1
    ), "the answered row keeps its link through the cancel"

    amend_after_cancel = client.post(
        COMMIT_URL(world.inquiry.id),
        json={"amendments": [{"row_id": row_a.id, "qty_reserved": "40", "reason": "10 back"}]},
    )
    assert amend_after_cancel.status_code == 200, amend_after_cancel.text
    world.db.commit()
    assert _rr(world, request_id, row_a).qty_reserved == Decimal("40")

    reserve_after_cancel = client.post(
        COMMIT_URL(world.inquiry.id),
        json={"reserves": [{"row_id": row_b.id, "qty_reserved": "30"}]},
    )
    assert reserve_after_cancel.status_code == 409, reserve_after_cancel.text
    assert row_b.item_code in reserve_after_cancel.text, reserve_after_cancel.text

    # One commit touching rows of TWO open requests: one dispatch per request, each
    # naming its own rows only.
    row_c = _open_row(world, qty="10", item_code=f"{MARKER}-TWOC")
    row_d = _open_row(world, qty="10", item_code=f"{MARKER}-TWOD")
    request_c = _request(client, world, (row_c, "10"))
    request_d = _request(client, world, (row_d, "10"))
    calls.clear()
    both = client.post(
        COMMIT_URL(world.inquiry.id),
        json={
            "reserves": [
                {"row_id": row_c.id, "qty_reserved": "10"},
                {"row_id": row_d.id, "qty_reserved": "10"},
            ]
        },
    )
    assert both.status_code == 200, both.text
    world.db.commit()
    matches = _reserved_calls(calls)
    assert len(matches) == 2, matches
    by_source = {m["source_id"]: {r["item_code"] for r in m["context"]["reserve"]["rows"]} for m in matches}
    assert by_source == {request_c: {row_c.item_code}, request_d: {row_d.item_code}}, by_source

    # Re-requesting the balance of a row answered inside a STILL-OPEN request.
    row_e = _open_row(world, qty="50", item_code=f"{MARKER}-REQE")
    row_f = _open_row(world, qty="50", item_code=f"{MARKER}-REQF")
    _request(client, world, (row_e, "50"), (row_f, "50"))
    partial = client.post(
        COMMIT_URL(world.inquiry.id),
        json={"reserves": [{"row_id": row_e.id, "qty_reserved": "20", "reason": "20 only"}]},
    )
    assert partial.status_code == 200, partial.text
    world.db.commit()
    again = client.post(
        REQUEST_URL(world.inquiry.id), json={"rows": [{"row_id": row_e.id, "qty_requested": "30"}]}
    )
    assert again.status_code == 201, again.text
    world.db.commit()
    ordinals = [
        r.ordinal
        for r in world.db.query(OrderInquiryReserveRequest)
        .filter(OrderInquiryReserveRequest.order_inquiry_id == world.inquiry.id)
        .all()
    ]
    assert again.json()["ordinal"] == max(ordinals), (again.json(), ordinals)

    # `reserves` on row_e now resolves to the NEW request's open row.
    second_answer = client.post(
        COMMIT_URL(world.inquiry.id),
        json={"reserves": [{"row_id": row_e.id, "qty_reserved": "30"}]},
    )
    assert second_answer.status_code == 200, second_answer.text
    world.db.commit()
    assert _rr(world, again.json()["id"], row_e).qty_reserved == Decimal("30")


def test_commit_reserve_validation_carried_from_reserve_row(reserve_api):
    """The coverage the retired per-row `reserve_row` tests carried (6e.4, reviewer S9):
    over requested, foreign / inactive warehouse, non-finite qty reaching the service
    directly, Reserve 0, history newest first."""
    from app.models.company import Company
    from app.models.inventory import Warehouse

    client, world = reserve_api
    row = _open_row(world, qty="100", item_code=f"{MARKER}-VALID")
    request_id = _request(client, world, (row, "50"))

    over_requested = client.post(
        COMMIT_URL(world.inquiry.id),
        json={"reserves": [{"row_id": row.id, "qty_reserved": "60"}]},
    )
    assert over_requested.status_code == 422, over_requested.text
    assert over_requested.json()["code"] == "reserve_qty_out_of_range", over_requested.text

    inactive = _warehouse(world.db, f"ZZT-{_uid()[:6]}".upper())
    inactive.is_active = False
    other_company_id = _uid()
    with company_scope(world.db, None):
        world.db.add(Company(id=other_company_id, name=f"{MARKER} Other", code=f"ZZ{_uid()[:6]}"))
        world.db.flush()
        foreign_wh = Warehouse(
            id=_uid(), company_id=other_company_id, warehouse_code=f"ZZT{_uid()[:6]}",
            warehouse_name=f"{MARKER} foreign", is_active=True,
        )
        world.db.add(foreign_wh)
        world.db.flush()
    world.db.commit()
    for warehouse_id in (inactive.id, foreign_wh.id):
        bad = client.post(
            COMMIT_URL(world.inquiry.id),
            json={"reserves": [{"row_id": row.id, "warehouse_id": warehouse_id, "qty_reserved": "50"}]},
        )
        assert bad.status_code == 422, bad.text
        assert bad.json()["code"] == "reserve_bad_warehouse", bad.text

    from app.services.order_inquiry_reserve_service import OrderInquiryReserveService

    for bad_qty in ("nan", "inf", "abc"):
        with pytest.raises(AppException) as excinfo:
            OrderInquiryReserveService(world.db).commit_request(
                inquiry_id=world.inquiry.id,
                reserves=[{"row_id": row.id, "qty_reserved": bad_qty, "reason": "x"}],
                amendments=[],
                actor_user_id=world.reserver,
            )
        assert excinfo.value.status_code == 422, excinfo.value.message
        world.db.rollback()

    zero = client.post(
        COMMIT_URL(world.inquiry.id),
        json={"reserves": [{"row_id": row.id, "qty_reserved": "0", "reason": "none on hand"}]},
    )
    assert zero.status_code == 200, zero.text
    world.db.commit()
    rr = _rr(world, request_id, row)
    assert rr.qty_reserved == Decimal("0")
    assert (
        world.db.query(OrderInquiryLink).filter(OrderInquiryLink.reserve_request_row_id == rr.id).count()
        == 0
    ), "Reserve 0 writes no link"

    history = client.get(ROW_HISTORY_URL(request_id, row.id))
    assert history.status_code == 200, history.text
    assert [(e["kind"], e["qty"]) for e in history.json()] == [
        ("reserved", "0"),
        ("requested", "50"),
    ], history.json()


def _is_utc_iso(value) -> bool:
    return isinstance(value, str) and (value.endswith("Z") or value.endswith("+00:00"))


def test_history_and_request_timestamps_serialize_as_utc(reserve_api):
    """The reserve columns are `TIMESTAMP` without time zone and hold naive UTC
    (`datetime.utcnow()`); the wire must say so, or the browser reads them as local."""
    client, world = reserve_api
    row = _open_row(world, qty="20", item_code=f"{MARKER}-TZ")
    request_id = _request(client, world, (row, "20"))
    committed = client.post(
        COMMIT_URL(world.inquiry.id),
        json={"reserves": [{"row_id": row.id, "qty_reserved": "20"}]},
    )
    assert committed.status_code == 200, committed.text
    world.db.commit()
    body = committed.json()[0]
    assert _is_utc_iso(body["requested_at"]), body
    assert _is_utc_iso(body["reserved_at"]), body

    history = client.get(ROW_HISTORY_URL(request_id, row.id))
    assert history.status_code == 200, history.text
    for entry in history.json():
        assert _is_utc_iso(entry["created_at"]), entry

    listed = client.get(REQUEST_URL(world.inquiry.id)).json()
    assert all(_is_utc_iso(item["requested_at"]) for item in listed), listed


def test_reserve_mail_dates_are_malaysia_calendar_days(reserve_api):
    """`requested_at` is naive UTC: 2026-09-23 17:30 UTC is 24/09/2026 01:30 in Malaysia,
    so both reserve mails must print 24/09/2026, and `today` is Malaysia's today."""
    from datetime import datetime

    from app.services.certificate_service import today_malaysia
    from app.services.order_inquiry_reserve_service import (
        _build_commit_context,
        _build_context,
    )

    client, world = reserve_api
    row = _open_row(world, qty="10", item_code=f"{MARKER}-MYT")
    request_id = _request(client, world, (row, "10"))
    request = (
        world.db.query(OrderInquiryReserveRequest)
        .filter(OrderInquiryReserveRequest.id == request_id)
        .one()
    )
    request.requested_at = datetime(2026, 9, 23, 17, 30, 0)
    world.db.flush()
    rr = _rr(world, request_id, row)
    request = world.db.get(OrderInquiryReserveRequest, request_id)

    requested_ctx = _build_context(world.db, request, [(rr, row)], actor_user_id=world.requester)
    committed_ctx = _build_commit_context(
        world.db, request, [{"rr": rr, "row": row}], open_row_count=0, row_count=1,
        actor_user_id=world.reserver,
    )
    for ctx in (requested_ctx, committed_ctx):
        assert ctx["reserve"]["requested_at"] == "24/09/2026", ctx["reserve"]
        assert ctx["today"] == today_malaysia().strftime("%d/%m/%Y"), ctx["today"]
