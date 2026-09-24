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

1. Route: `POST {LIST}/{inquiry_id}/reserve-requests/{request_id}/commit` (plan 6e.1's
   own words), gated by `projects.order_inquiries.reserve` alone - the same grant the
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
   commit_request(request_id, reserves, amendments, actor_user_id)`, matching the
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

from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.models.project_so import (
    INQUIRY_PARTLY_LINKED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryReserveRequest,
    OrderInquiryRow,
)

from ._pg_fixture import blank_session
from .test_order_inquiry_reserve import (
    REQUESTER_PERMISSIONS,
    REQUEST_URL,
    ROW_HISTORY_URL,
    ROW_RESERVE_URL,
    ROW_UNRESERVE_URL,
    _as,
    _captured_dispatches,
    _load_reserve_seed_migration,
    _open_row,
    _register,
    _reserve_fixture_context,
    _reserved_calls,
    api as reserve_api,  # noqa: F401  (re-exported fixture: both permissions)
)
from .test_order_inquiry_worklist import (
    LIST,
    MARKER as WL_MARKER,
    _line_on_authored_order,
    _row,
    _uid,
    _user,
    api as worklist_api,  # noqa: F401  (re-exported fixture; header lines + worklist reader)
)
from .test_planning_changes import _warehouse

MARKER = "zzt-oi-reserve-commit"

COMMIT_URL = lambda inquiry_id, request_id: (  # noqa: E731
    f"{LIST}/{inquiry_id}/reserve-requests/{request_id}/commit"
)


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
        COMMIT_URL(world.inquiry.id, request_id),
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
        request_id=request.id,
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
        COMMIT_URL(world.inquiry.id, request_id),
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
        COMMIT_URL(world.inquiry.id, request_id),
        json={"reserves": [{"row_id": row.id, "warehouse_id": world.site.id, "qty_reserved": "10"}]},
    )
    assert again.status_code == 409, again.text
    assert row.item_code in again.text, (
        f"the 409 must NAME the offending row, not a generic message: {again.text}"
    )

    # A row belonging to ANOTHER request -> 404.
    other_row = _open_row(world, qty="10", item_code=f"{MARKER}-OTHER")
    other_request = client.post(
        REQUEST_URL(world.inquiry.id), json={"rows": [{"row_id": other_row.id, "qty_requested": "10"}]}
    )
    assert other_request.status_code == 201, other_request.text
    world.db.commit()
    wrong = client.post(
        COMMIT_URL(world.inquiry.id, request_id),
        json={
            "reserves": [
                {"row_id": other_row.id, "warehouse_id": world.site.id, "qty_reserved": "10"}
            ]
        },
    )
    assert wrong.status_code == 404, wrong.text

    # An empty payload is 422.
    empty = client.post(COMMIT_URL(world.inquiry.id, request_id), json={})
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
        COMMIT_URL(world.inquiry.id, batch_request_id),
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
        COMMIT_URL(world.inquiry.id, request_id),
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
        COMMIT_URL(world.inquiry.id, request_id),
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
        COMMIT_URL(world.inquiry.id, request_id),
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
        COMMIT_URL(world.inquiry.id, request_id),
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
        COMMIT_URL(world.inquiry.id, request_id),
        json={"amendments": [{"row_id": row.id, "qty_reserved": "51"}]},
    )
    assert above.status_code == 422, above.text

    # Short of requested with no reason is 422.
    short_no_reason = client.post(
        COMMIT_URL(world.inquiry.id, request_id),
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
    open_request_id = open_request.json()["id"]
    on_open = client.post(
        COMMIT_URL(world.inquiry.id, open_request_id),
        json={"amendments": [{"row_id": open_row.id, "qty_reserved": "5"}]},
    )
    assert on_open.status_code == 422, on_open.text

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
            COMMIT_URL(world.inquiry.id, request_id),
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

    # History still lists events, newest first.
    history = client.get(ROW_HISTORY_URL(request_id, row.id))
    assert history.status_code == 200, history.text
    kinds = [entry["kind"] for entry in history.json()]
    assert "requested" in kinds, history.json()


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
        COMMIT_URL(world.inquiry.id, request_id),
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
    first_rows = first_matches[0]["context"]["reserve"]["rows"]
    assert {r["item_code"] for r in first_rows} == {row_a.item_code}, first_rows

    second = client.post(
        COMMIT_URL(world.inquiry.id, request_id),
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
        request_id=request_id,
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
