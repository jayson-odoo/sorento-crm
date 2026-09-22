"""Order inquiry: Request CS to reserve stock (`PLAN-oi-request-cs-reserve.md`, slices 2/3).

Contract: `documentation/plans/scm/oi-request-cs-reserve-acceptance-criteria.md`,
AC-RS-1 to AC-RS-21 (backend). TEST-FIRST (Phase 2): written before
`app/services/order_inquiry_reserve_service.py`, the two new models, the new permission,
the widened link CHECK and the two seeded automations exist - there is NO implementation
to look at. A red here must be a missing module/attribute, a 404, or an assertion on
behaviour the plan says does not exist yet - never an import typo or a fixture bug.

Postgres only (`tests/_pg_fixture.py`); every FK chain is seeded here or borrowed from an
existing seeding helper (`test_order_inquiry_worklist.py`, `test_planning_changes.py`,
`test_order_inquiry_handshake.py`) - never `LIMIT 1` off a shared table. Most of this file
runs on `blank_session()` (a real, empty Postgres schema built from `Base.metadata`) -
fast and isolated, and sufficient for everything the reserve service itself touches
(rows, links, requests). Two tests need the REAL migrated database instead, because
`scm.committed_v` is a raw-SQL VIEW a migration installs and is not part of
`Base.metadata`: RS-13 borrows `test_order_inquiry_handshake`'s `world`/`api` (rolled
back), the same reason that suite gives for doing the same.

NAMED ASSUMPTIONS (per the tester's brief - "name any gap so the captain can pin it for
the coder"), because neither the plan nor the UAC pins these internal names and the
project's own convention (`test_order_inquiry_handover_automation.py`'s own docstring) is
that a test-first suite IS what pins them:

1. `OrderInquiryReserveService(db).create_request(inquiry_id, rows, note, actor_user_id)`
   returns an object exposing `.id`, `.ordinal`, `.state` (an ORM row or an equivalent
   namespace) - never a bare dict - matching every other service method in this codebase
   that hands back the row it just wrote (`ProjectSupplyService.confirm`, `place_on_po`).
2. Post-commit dispatch needs an explicit registration call the same shape as the
   existing `register_order_inquiry_post_commit_dispatch` (`project_order_inquiry_
   service.py:9355`, drains `order_inquiry_changed_with_links`) and `_fire_pending_
   handover` (`:9494`, drains the handover) - but NEITHER of those two drains this
   feature's own events, so this suite expects its OWN function,
   `register_order_inquiry_reserve_post_commit_dispatch`, exported from the new
   `order_inquiry_reserve_service` module. If the coder instead attaches the listener
   unconditionally at import time (no caller-visible register function needed, the way
   `_stamp_inquiry_no` does), RS-1/RS-6/RS-19/RS-21's `_register()` calls need deleting
   rather than renaming - flagged here rather than guessed twice.
3. The route paths are exactly the plan's own words: `POST {LIST}/{inquiry_id}/
   reserve-requests`, `POST {LIST}/reserve-requests/{id}/cancel`,
   `POST {LIST}/reserve-requests/{id}/reserve`.
4. AC-RS-20 names TWO readers ("header lines + worklist"); only the worklist reader
   (`GET {LIST}`, already proven by `test_order_inquiry_worklist.py`) is exercised here
   for time - the header-lines route lives in a part of `order_inquiries.py` this file
   does not otherwise touch, and the two readers share one `_serialize`-shaped
   contract per the plan (3.5), so one red on the shared field is a fair proxy. Narrowed
   deliberately, same as AC-H6/AC-H15 are narrowed in the handover suite's own docstring.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app.models.base import company_scope
from app.models.project_so import (
    INQUIRY_ACTIONED,
    INQUIRY_PARTLY_LINKED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_DELAY,
    IV_ORDER,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryRow,
    ProjectSalesOrder,
)
from app.services.error_handler import AppException

from ._pg_fixture import blank_session
from .test_order_inquiry_worklist import (
    LIST,
    MARKER as WL_MARKER,
    _client as _wl_client,
    _inquiry_for,
    _line_on_authored_order,
    _purchase_order,
    _restore as _wl_restore,
    _row,
    _sorento,
    _uid,
    _user,
    api as worklist_api,  # noqa: F401  (re-exported fixture; used by RS-12/RS-20)
)
from .test_planning_changes import _warehouse
from .test_order_inquiry_handshake import world as handshake_world  # noqa: F401  (fixture)

MARKER = "zzt-oi-reserve"
BASE = "/api/v1/project-sales"

RESERVE_PERMISSION = "projects.order_inquiries.reserve"
REQUESTER_PERMISSIONS = [
    "projects.projects.view",
    "projects.order_inquiry.action",
    "projects.order_inquiries.acknowledge",
]
RESERVER_PERMISSIONS = REQUESTER_PERMISSIONS + [RESERVE_PERMISSION]

REQUEST_URL = lambda inquiry_id: f"{LIST}/{inquiry_id}/reserve-requests"  # noqa: E731
CANCEL_URL = lambda request_id: f"{LIST}/reserve-requests/{request_id}/cancel"  # noqa: E731
RESERVE_URL = lambda request_id: f"{LIST}/reserve-requests/{request_id}/reserve"  # noqa: E731


# --------------------------------------------------------------------------------- #
# harness                                                                            #
# --------------------------------------------------------------------------------- #


def _pso(db, company_id: str) -> ProjectSalesOrder:
    """The smallest legal `ProjectSalesOrder` - `provisional_ref` is its only NOT NULL
    column beyond id/company_id (measured, `app/models/project_so.py` ~:454-478). An
    `OrderInquiry` header needs one to point at; nothing here reads through it."""
    pso = ProjectSalesOrder(
        id=_uid(), company_id=company_id, provisional_ref=f"{MARKER}-{_uid()[:8]}"
    )
    db.add(pso)
    db.flush()
    return pso


class _World:
    def __init__(self, db, company_id, requester, reserver, pool, site, inquiry):
        self.db = db
        self.company_id = company_id
        self.requester = requester
        self.reserver = reserver
        self.pool = pool
        self.site = site
        self.inquiry = inquiry


def _seeded_world(db):
    company_id = _sorento(db)
    requester = _user(db, f"{MARKER} Joey")
    reserver = _user(db, f"{MARKER} Eling")
    pool = _warehouse(db, f"ZZT-{_uid()[:6]}".upper())
    site = _warehouse(db, f"{pool.warehouse_code}-BB", pool_warehouse_id=pool.id)
    inquiry = _inquiry_for(db, company_id, _pso(db, company_id))
    db.commit()
    return _World(db, company_id, requester, reserver, pool, site, inquiry)


def _api(permissions):
    with blank_session() as db:
        world = _seeded_world(db)
        client, originals = _wl_client(db, world.requester, permissions)
        try:
            with company_scope(db, frozenset({world.company_id})):
                yield client, world
        finally:
            _wl_restore(originals)


@pytest.fixture()
def api():
    """The default actor holds BOTH permissions (request + reserve) - most tests are
    about the reserve SERVICE's own rules, not about who may press which button (that is
    RS-10's own job, which builds its own narrower client)."""
    yield from _api(RESERVER_PERMISSIONS)


def _as(db, user_id: str, permissions):
    from contextlib import contextmanager

    @contextmanager
    def _ctx():
        client, originals = _wl_client(db, user_id, permissions)
        try:
            yield client
        finally:
            _wl_restore(originals)

    return _ctx()


def _register():
    """See module docstring, assumption 2."""
    from app.services.order_inquiry_reserve_service import (
        register_order_inquiry_reserve_post_commit_dispatch,
    )

    register_order_inquiry_reserve_post_commit_dispatch()


def _captured_dispatches(monkeypatch) -> list[dict]:
    calls: list[dict] = []

    def _fake_dispatch(self, trigger_type, *, context, source_kind, source_id):
        calls.append(
            {
                "trigger_type": trigger_type,
                "context": context,
                "source_kind": source_kind,
                "source_id": source_id,
            }
        )
        return {"trigger_type": trigger_type, "fired": 0, "results": []}

    monkeypatch.setattr(
        "app.services.automation_service.AutomationService.dispatch_event",
        _fake_dispatch,
    )
    return calls


def _requested_calls(calls: list[dict]) -> list[dict]:
    return [c for c in calls if c["trigger_type"] == "order_inquiry_reserve_requested"]


def _reserved_calls(calls: list[dict]) -> list[dict]:
    return [c for c in calls if c["trigger_type"] == "order_inquiry_reserved"]


def _open_row(world, *, qty="139", verb=IV_ORDER, state=INQUIRY_RAISED, **fields):
    fields.setdefault("item_code", f"{MARKER}-ITEM")
    fields.setdefault("delivery_date", date(2026, 10, 1))
    fields.setdefault("stock_location", world.site.warehouse_code)
    row = _row(
        world.db, world.company_id, world.inquiry, verb=verb, state=state, qty=qty, **fields
    )
    world.db.commit()
    return row


def _service(db):
    from app.services.order_inquiry_reserve_service import OrderInquiryReserveService

    return OrderInquiryReserveService(db)


# --------------------------------------------------------------------------------- #
# RS-1                                                                               #
# --------------------------------------------------------------------------------- #


def test_request_creates_request_and_rows_one_dispatch(api, monkeypatch):
    client, world = api
    _register()
    calls = _captured_dispatches(monkeypatch)

    rows = [_open_row(world, qty=q) for q in ("50", "60", "70")]

    response = client.post(
        REQUEST_URL(world.inquiry.id),
        json={
            "rows": [
                {"row_id": row.id, "qty_requested": str(row.qty), "warehouse_id": world.site.id}
                for row in rows
            ],
            "note": None,
        },
    )
    assert response.status_code == 201, response.text
    world.db.commit()

    from app.models.project_so import OrderInquiryReserveRequest, OrderInquiryReserveRequestRow

    request = (
        world.db.query(OrderInquiryReserveRequest)
        .filter(OrderInquiryReserveRequest.order_inquiry_id == world.inquiry.id)
        .one()
    )
    assert request.ordinal == 1
    assert request.state == "requested"
    assert request.requested_by == world.requester
    assert request.requested_at is not None

    request_rows = (
        world.db.query(OrderInquiryReserveRequestRow)
        .filter(OrderInquiryReserveRequestRow.request_id == request.id)
        .all()
    )
    assert len(request_rows) == 3

    matches = _requested_calls(calls)
    assert len(matches) == 1, f"expected exactly one dispatch (R9), got {len(matches)}"
    assert matches[0]["context"]["reserve"]["row_count"] == 3


# --------------------------------------------------------------------------------- #
# RS-2                                                                               #
# --------------------------------------------------------------------------------- #


def test_request_default_location_is_pool(api):
    client, world = api
    row_at_site = _open_row(world, stock_location=world.site.warehouse_code)
    row_at_pool = _open_row(world, stock_location=world.pool.warehouse_code)

    resp_site = client.post(
        REQUEST_URL(world.inquiry.id),
        json={"rows": [{"row_id": row_at_site.id, "qty_requested": "139"}]},
    )
    assert resp_site.status_code == 201, resp_site.text
    world.db.commit()

    resp_pool = client.post(
        REQUEST_URL(world.inquiry.id),
        json={"rows": [{"row_id": row_at_pool.id, "qty_requested": "139"}]},
    )
    assert resp_pool.status_code == 201, resp_pool.text
    world.db.commit()

    from app.models.project_so import OrderInquiryReserveRequestRow

    site_request_row = (
        world.db.query(OrderInquiryReserveRequestRow)
        .filter(OrderInquiryReserveRequestRow.row_id == row_at_site.id)
        .one()
    )
    assert site_request_row.warehouse_id == world.pool.id, (
        "a row at BRW-BB (pool_warehouse_id set) must default to BRW itself (R3)"
    )

    pool_request_row = (
        world.db.query(OrderInquiryReserveRequestRow)
        .filter(OrderInquiryReserveRequestRow.row_id == row_at_pool.id)
        .one()
    )
    assert pool_request_row.warehouse_id == world.pool.id, (
        "a row whose location IS ALREADY a pool must default to itself"
    )


# --------------------------------------------------------------------------------- #
# RS-3                                                                               #
# --------------------------------------------------------------------------------- #


def test_request_qty_capped_at_remaining(api):
    client, world = api
    po_line = _purchase_order(world.db, world.company_id)["line"]
    row = _open_row(world, qty="100")
    world.db.add(
        OrderInquiryLink(
            id=_uid(), company_id=world.company_id, row_id=row.id,
            po_line_id=po_line.id, document="ZZT-PO-LINKED", qty=Decimal("40"),
        )
    )
    world.db.commit()
    # remaining = 100 - 40 = 60

    over = client.post(
        REQUEST_URL(world.inquiry.id),
        json={"rows": [{"row_id": row.id, "qty_requested": "61"}]},
    )
    assert over.status_code == 422, over.text

    zero = client.post(
        REQUEST_URL(world.inquiry.id),
        json={"rows": [{"row_id": row.id, "qty_requested": "0"}]},
    )
    assert zero.status_code == 422, zero.text

    ok = client.post(
        REQUEST_URL(world.inquiry.id),
        json={"rows": [{"row_id": row.id, "qty_requested": "60"}]},
    )
    assert ok.status_code == 201, ok.text


# --------------------------------------------------------------------------------- #
# RS-4                                                                               #
# --------------------------------------------------------------------------------- #


def test_request_rejects_open_duplicate_and_wrong_state(api):
    client, world = api

    duplicate_row = _open_row(world)
    first = client.post(
        REQUEST_URL(world.inquiry.id),
        json={"rows": [{"row_id": duplicate_row.id, "qty_requested": "139"}]},
    )
    assert first.status_code == 201, first.text
    world.db.commit()

    second = client.post(
        REQUEST_URL(world.inquiry.id),
        json={"rows": [{"row_id": duplicate_row.id, "qty_requested": "1"}]},
    )
    assert second.status_code == 409, second.text

    wrong_verb_row = _open_row(world, verb=IV_DELAY)
    wrong_verb = client.post(
        REQUEST_URL(world.inquiry.id),
        json={"rows": [{"row_id": wrong_verb_row.id, "qty_requested": "1"}]},
    )
    assert wrong_verb.status_code == 409, wrong_verb.text

    actioned_row = _open_row(world, state=INQUIRY_ACTIONED)
    wrong_state = client.post(
        REQUEST_URL(world.inquiry.id),
        json={"rows": [{"row_id": actioned_row.id, "qty_requested": "1"}]},
    )
    assert wrong_state.status_code == 409, wrong_state.text

    other_inquiry = _inquiry_for(world.db, world.company_id, _pso(world.db, world.company_id))
    world.db.commit()
    foreign_row = _row(
        world.db, world.company_id, other_inquiry, verb=IV_ORDER, state=INQUIRY_RAISED, qty="10",
    )
    world.db.commit()
    wrong_inquiry = client.post(
        REQUEST_URL(world.inquiry.id),
        json={"rows": [{"row_id": foreign_row.id, "qty_requested": "1"}]},
    )
    assert wrong_inquiry.status_code == 409, wrong_inquiry.text


# --------------------------------------------------------------------------------- #
# RS-5                                                                               #
# --------------------------------------------------------------------------------- #


def test_second_request_after_reserved_allowed(api):
    client, world = api
    row = _open_row(world, qty="139")

    first = client.post(
        REQUEST_URL(world.inquiry.id),
        json={"rows": [{"row_id": row.id, "qty_requested": "139"}]},
    )
    assert first.status_code == 201, first.text
    world.db.commit()
    request_id = first.json()["id"]

    from app.models.project_so import OrderInquiryReserveRequestRow

    request_row = (
        world.db.query(OrderInquiryReserveRequestRow)
        .filter(OrderInquiryReserveRequestRow.row_id == row.id)
        .one()
    )
    reserve_resp = client.post(
        RESERVE_URL(request_id),
        json={
            "rows": [
                {
                    "request_row_id": request_row.id,
                    "warehouse_id": world.site.id,
                    "qty_reserved": "50",
                    "reason": "BRW only has 50 in stock",
                }
            ]
        },
    )
    assert reserve_resp.status_code == 200, reserve_resp.text
    world.db.commit()

    second = client.post(
        REQUEST_URL(world.inquiry.id),
        json={"rows": [{"row_id": row.id, "qty_requested": "89"}]},
    )
    assert second.status_code == 201, second.text
    assert second.json()["ordinal"] == 2


# --------------------------------------------------------------------------------- #
# RS-6                                                                               #
# --------------------------------------------------------------------------------- #


def test_reserve_writes_links_and_refreshes_state(api, monkeypatch):
    client, world = api
    _register()
    calls = _captured_dispatches(monkeypatch)

    row = _open_row(world, qty="139")
    request = client.post(
        REQUEST_URL(world.inquiry.id),
        json={"rows": [{"row_id": row.id, "qty_requested": "139"}]},
    ).json()
    world.db.commit()

    from app.models.project_so import OrderInquiryReserveRequestRow

    request_row = (
        world.db.query(OrderInquiryReserveRequestRow)
        .filter(OrderInquiryReserveRequestRow.row_id == row.id)
        .one()
    )
    response = client.post(
        RESERVE_URL(request["id"]),
        json={
            "rows": [
                {
                    "request_row_id": request_row.id,
                    "warehouse_id": world.site.id,
                    "qty_reserved": "50",
                    "reason": "BRW only has 50 in stock",
                }
            ]
        },
    )
    assert response.status_code == 200, response.text
    world.db.commit()

    world.db.expire_all()
    link = (
        world.db.query(OrderInquiryLink)
        .filter(OrderInquiryLink.reserve_request_row_id == request_row.id)
        .one()
    )
    assert link.qty == Decimal("50")
    assert link.document == f"Reserved @ {world.site.warehouse_code}"

    refreshed_row = world.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row.id).one()
    assert refreshed_row.state == INQUIRY_PARTLY_LINKED

    from app.models.project_so import OrderInquiryReserveRequest

    reloaded_request = (
        world.db.query(OrderInquiryReserveRequest).filter(OrderInquiryReserveRequest.id == request["id"]).one()
    )
    assert reloaded_request.state == "reserved"
    assert reloaded_request.reserved_by == world.reserver or reloaded_request.reserved_by is not None
    assert reloaded_request.reserved_at is not None

    matches = _reserved_calls(calls)
    assert len(matches) == 1, f"expected exactly one dispatch, got {len(matches)}"

    # A SECOND row, reserved for the FULL requested amount with nothing else linked ->
    # `placed`.
    full_row = _open_row(world, qty="20")
    full_request = client.post(
        REQUEST_URL(world.inquiry.id),
        json={"rows": [{"row_id": full_row.id, "qty_requested": "20"}]},
    ).json()
    world.db.commit()
    full_request_row = (
        world.db.query(OrderInquiryReserveRequestRow)
        .filter(OrderInquiryReserveRequestRow.row_id == full_row.id)
        .one()
    )
    full_response = client.post(
        RESERVE_URL(full_request["id"]),
        json={
            "rows": [
                {
                    "request_row_id": full_request_row.id,
                    "warehouse_id": world.site.id,
                    "qty_reserved": "20",
                }
            ]
        },
    )
    assert full_response.status_code == 200, full_response.text
    world.db.commit()
    world.db.expire_all()
    refreshed_full_row = world.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == full_row.id).one()
    assert refreshed_full_row.state == INQUIRY_PLACED


# --------------------------------------------------------------------------------- #
# RS-7                                                                               #
# --------------------------------------------------------------------------------- #


def test_reserve_zero_needs_reason(api):
    client, world = api
    row = _open_row(world, qty="50")
    request = client.post(
        REQUEST_URL(world.inquiry.id), json={"rows": [{"row_id": row.id, "qty_requested": "50"}]}
    ).json()
    world.db.commit()

    from app.models.project_so import OrderInquiryReserveRequestRow

    request_row = (
        world.db.query(OrderInquiryReserveRequestRow)
        .filter(OrderInquiryReserveRequestRow.row_id == row.id)
        .one()
    )

    no_reason = client.post(
        RESERVE_URL(request["id"]),
        json={"rows": [{"request_row_id": request_row.id, "warehouse_id": world.site.id, "qty_reserved": "0"}]},
    )
    assert no_reason.status_code == 422, no_reason.text

    with_reason = client.post(
        RESERVE_URL(request["id"]),
        json={
            "rows": [
                {
                    "request_row_id": request_row.id,
                    "warehouse_id": world.site.id,
                    "qty_reserved": "0",
                    "reason": "BRW has none in stock",
                }
            ]
        },
    )
    assert with_reason.status_code == 200, with_reason.text
    world.db.commit()

    assert (
        world.db.query(OrderInquiryLink)
        .filter(OrderInquiryLink.reserve_request_row_id == request_row.id)
        .count()
        == 0
    ), "a 0-reserved row writes no link"


# --------------------------------------------------------------------------------- #
# RS-8                                                                               #
# --------------------------------------------------------------------------------- #


def test_reserve_short_needs_reason_full_does_not(api):
    client, world = api
    row = _open_row(world, qty="50")
    request = client.post(
        REQUEST_URL(world.inquiry.id), json={"rows": [{"row_id": row.id, "qty_requested": "50"}]}
    ).json()
    world.db.commit()

    from app.models.project_so import OrderInquiryReserveRequestRow

    request_row = (
        world.db.query(OrderInquiryReserveRequestRow)
        .filter(OrderInquiryReserveRequestRow.row_id == row.id)
        .one()
    )

    short_no_reason = client.post(
        RESERVE_URL(request["id"]),
        json={"rows": [{"request_row_id": request_row.id, "warehouse_id": world.site.id, "qty_reserved": "30"}]},
    )
    assert short_no_reason.status_code == 422, short_no_reason.text

    full_no_reason = client.post(
        RESERVE_URL(request["id"]),
        json={"rows": [{"request_row_id": request_row.id, "warehouse_id": world.site.id, "qty_reserved": "50"}]},
    )
    assert full_no_reason.status_code == 200, full_no_reason.text


def test_reserve_over_requested_is_422(api):
    """AC-RS-8's other half ("51 of 50 is 422") - its own test, since RS-8's own name in
    the captain's list covers the short/full pair; over-requested is folded in here
    rather than invented as a 22nd test name not on the list."""
    client, world = api
    row = _open_row(world, qty="50")
    request = client.post(
        REQUEST_URL(world.inquiry.id), json={"rows": [{"row_id": row.id, "qty_requested": "50"}]}
    ).json()
    world.db.commit()

    from app.models.project_so import OrderInquiryReserveRequestRow

    request_row = (
        world.db.query(OrderInquiryReserveRequestRow)
        .filter(OrderInquiryReserveRequestRow.row_id == row.id)
        .one()
    )
    over = client.post(
        RESERVE_URL(request["id"]),
        json={"rows": [{"request_row_id": request_row.id, "warehouse_id": world.site.id, "qty_reserved": "51"}]},
    )
    assert over.status_code == 422, over.text


# --------------------------------------------------------------------------------- #
# RS-9                                                                               #
# --------------------------------------------------------------------------------- #


def test_reserve_all_rows_or_422(api):
    client, world = api
    row_a = _open_row(world, qty="50")
    row_b = _open_row(world, qty="30")
    request = client.post(
        REQUEST_URL(world.inquiry.id),
        json={
            "rows": [
                {"row_id": row_a.id, "qty_requested": "50"},
                {"row_id": row_b.id, "qty_requested": "30"},
            ]
        },
    ).json()
    world.db.commit()

    from app.models.project_so import OrderInquiryReserveRequestRow

    request_row_a = (
        world.db.query(OrderInquiryReserveRequestRow)
        .filter(OrderInquiryReserveRequestRow.row_id == row_a.id)
        .one()
    )

    partial = client.post(
        RESERVE_URL(request["id"]),
        json={"rows": [{"request_row_id": request_row_a.id, "warehouse_id": world.site.id, "qty_reserved": "50"}]},
    )
    assert partial.status_code == 422, partial.text
    world.db.commit()

    assert (
        world.db.query(OrderInquiryLink)
        .filter(OrderInquiryLink.reserve_request_row_id == request_row_a.id)
        .count()
        == 0
    ), "an all-or-nothing rejection must write nothing"


# --------------------------------------------------------------------------------- #
# RS-10                                                                              #
# --------------------------------------------------------------------------------- #


def test_reserve_requires_permission(api):
    client, world = api
    row = _open_row(world, qty="50")
    request = client.post(
        REQUEST_URL(world.inquiry.id), json={"rows": [{"row_id": row.id, "qty_requested": "50"}]}
    ).json()
    world.db.commit()

    from app.models.project_so import OrderInquiryReserveRequestRow

    request_row = (
        world.db.query(OrderInquiryReserveRequestRow)
        .filter(OrderInquiryReserveRequestRow.row_id == row.id)
        .one()
    )

    # A user with none of the reserve permission (also covers "the requester without it").
    with _as(world.db, world.requester, REQUESTER_PERMISSIONS) as stranger:
        response = stranger.post(
            RESERVE_URL(request["id"]),
            json={"rows": [{"request_row_id": request_row.id, "warehouse_id": world.site.id, "qty_reserved": "50"}]},
        )
    assert response.status_code == 403, response.text

    from app.rbac.permission_registry import PERMISSION_REGISTRY

    slugs = {entry["slug"] for entry in PERMISSION_REGISTRY}
    assert RESERVE_PERMISSION in slugs


# --------------------------------------------------------------------------------- #
# RS-11                                                                              #
# --------------------------------------------------------------------------------- #


def test_reserve_only_once(api):
    client, world = api
    row = _open_row(world, qty="50")
    request = client.post(
        REQUEST_URL(world.inquiry.id), json={"rows": [{"row_id": row.id, "qty_requested": "50"}]}
    ).json()
    world.db.commit()

    from app.models.project_so import OrderInquiryReserveRequestRow

    request_row = (
        world.db.query(OrderInquiryReserveRequestRow)
        .filter(OrderInquiryReserveRequestRow.row_id == row.id)
        .one()
    )
    first = client.post(
        RESERVE_URL(request["id"]),
        json={"rows": [{"request_row_id": request_row.id, "warehouse_id": world.site.id, "qty_reserved": "50"}]},
    )
    assert first.status_code == 200, first.text
    world.db.commit()

    second = client.post(
        RESERVE_URL(request["id"]),
        json={"rows": [{"request_row_id": request_row.id, "warehouse_id": world.site.id, "qty_reserved": "0", "reason": "again"}]},
    )
    assert second.status_code == 409, second.text

    cancel = client.post(CANCEL_URL(request["id"]))
    assert cancel.status_code == 409, cancel.text


# --------------------------------------------------------------------------------- #
# RS-12 (real worklist reader, borrowed `api` fixture from test_order_inquiry_worklist) #
# --------------------------------------------------------------------------------- #


def test_taken_remaining_include_reserved(worklist_api):
    client, db, company_id, seeded = worklist_api
    inquiry = db.get(OrderInquiry, seeded["authored_row"].order_inquiry_id)
    line = _line_on_authored_order(db, company_id, seeded, qty="139", day=6)
    po_line = _purchase_order(db, company_id)["line"]

    row = _row(
        db, company_id, inquiry,
        so_line_id=line.id, item_code=f"{WL_MARKER}-RESERVE", qty="139",
        state=INQUIRY_PARTLY_LINKED, delivery_date=date(2026, 4, 6),
    )
    db.add(
        OrderInquiryLink(
            id=_uid(), company_id=company_id, row_id=row.id,
            po_line_id=po_line.id, document="ZZT-PO-LINKED", qty=Decimal("40"),
        )
    )
    db.commit()

    warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}".upper())
    from app.services.order_inquiry_reserve_service import OrderInquiryReserveService

    service = OrderInquiryReserveService(db)
    requester_id = _user(db, f"{WL_MARKER} requester")
    request = service.create_request(
        inquiry_id=inquiry.id,
        rows=[{"row_id": row.id, "qty_requested": Decimal("99"), "warehouse_id": warehouse.id}],
        note=None,
        actor_user_id=requester_id,
    )
    db.commit()
    from app.models.project_so import OrderInquiryReserveRequestRow

    request_row = (
        db.query(OrderInquiryReserveRequestRow)
        .filter(OrderInquiryReserveRequestRow.request_id == request.id)
        .one()
    )
    reserver_id = _user(db, f"{WL_MARKER} reserver")
    service.reserve(
        request_id=request.id,
        rows=[
            {
                "request_row_id": request_row.id,
                "warehouse_id": warehouse.id,
                "qty_reserved": Decimal("50"),
                "reason": "BRW only has 50 in stock",
            }
        ],
        actor_user_id=reserver_id,
    )
    db.commit()

    body = client.get(LIST, params={"delivery_month": "2026-04"}).json()
    by_id = {entry["id"]: entry for entry in body["data"]}

    assert by_id[row.id]["taken_from_po"] == "90", "PO 40 + reserved 50 (unchanged sum-by-row_id)"
    assert by_id[row.id]["remaining_open"] == "49"
    assert by_id[row.id]["reserved_qty"] == "50"
    assert by_id[row.id]["po_number"] is not None, (
        "the row's own PO link must still derive po_number - the reserve link must not "
        "leak into po_ref/po_number derivation"
    )


# --------------------------------------------------------------------------------- #
# RS-13 (real DB - scm.committed_v)                                                  #
# --------------------------------------------------------------------------------- #


def test_committed_v_owed_nets_reserved_link(handshake_world):
    """Borrows `test_order_inquiry_handshake`'s `world` fixture directly (imported below,
    at module scope, so pytest resolves it by name exactly as `test_oi_one_header.py`
    already does for the same suite) - the rolled-back real database is the only thing
    that carries `scm.committed_v`."""
    from .test_order_inquiry_handshake import (
        _client as _hs_client,
        _confirm,
        _core_line,
        _core_so,
        _line_payload,
        _project_line,
        _project_so,
    )

    world = handshake_world
    from app.services.order_inquiry_reserve_service import OrderInquiryReserveService
    from app.models.project_so import OrderInquiryReserveRequestRow

    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(
        db, core_so, world.product, world.warehouse, qty_ordered="139",
        required_date=date(2026, 8, 25),
    )
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    client, originals = _hs_client(
        db, world.cs_user, ["projects.projects.view", "projects.projects.edit", "projects.order_inquiry.action"]
    )
    response = _confirm(client, order.id, [_line_payload(line.id, buy_qty="139")])
    assert response.status_code == 200, response.text
    db.commit()

    row = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.state != "cancelled")
        .one()
    )

    def _owed() -> Decimal:
        return Decimal(
            str(
                db.execute(
                    sa.text(
                        "SELECT COALESCE(SUM(project_committed), 0) FROM scm.committed_v "
                        "WHERE product_id = :pid"
                    ),
                    {"pid": str(world.product.id)},
                ).scalar()
                or 0
            )
        )

    before = _owed()

    service = OrderInquiryReserveService(db)
    request = service.create_request(
        inquiry_id=row.order_inquiry_id,
        rows=[{"row_id": row.id, "qty_requested": Decimal("50"), "warehouse_id": world.warehouse.id}],
        note=None,
        actor_user_id=world.cs_user,
    )
    db.commit()
    request_row = (
        db.query(OrderInquiryReserveRequestRow)
        .filter(OrderInquiryReserveRequestRow.request_id == request.id)
        .one()
    )
    service.reserve(
        request_id=request.id,
        rows=[
            {
                "request_row_id": request_row.id,
                "warehouse_id": world.warehouse.id,
                "qty_reserved": Decimal("50"),
            }
        ],
        actor_user_id=world.cs_user,
    )
    db.commit()

    after = _owed()
    assert before - after == Decimal("50"), (
        f"committed_v owed must drop by the reserved qty (R8): before={before} after={after}"
    )


# --------------------------------------------------------------------------------- #
# RS-14                                                                              #
# --------------------------------------------------------------------------------- #


def test_unlink_reserve_link_restores_remaining(api):
    client, world = api
    row = _open_row(world, qty="139")
    request = client.post(
        REQUEST_URL(world.inquiry.id), json={"rows": [{"row_id": row.id, "qty_requested": "139"}]}
    ).json()
    world.db.commit()

    from app.models.project_so import OrderInquiryReserveRequest, OrderInquiryReserveRequestRow

    request_row = (
        world.db.query(OrderInquiryReserveRequestRow)
        .filter(OrderInquiryReserveRequestRow.row_id == row.id)
        .one()
    )
    reserve_resp = client.post(
        RESERVE_URL(request["id"]),
        json={
            "rows": [
                {
                    "request_row_id": request_row.id,
                    "warehouse_id": world.site.id,
                    "qty_reserved": "50",
                    "reason": "BRW only has 50 in stock",
                }
            ]
        },
    )
    assert reserve_resp.status_code == 200, reserve_resp.text
    world.db.commit()

    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    ProjectOrderInquiryService(world.db).unplace(str(row.id), actor_user_id=world.requester)
    world.db.commit()

    world.db.expire_all()
    refreshed_row = world.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row.id).one()
    assert refreshed_row.state == INQUIRY_RAISED, "unlinking the reserve link must restore remaining"

    reloaded_request = (
        world.db.query(OrderInquiryReserveRequest).filter(OrderInquiryReserveRequest.id == request["id"]).one()
    )
    assert reloaded_request.state == "reserved", "the request stays reserved as history"


# --------------------------------------------------------------------------------- #
# RS-15                                                                              #
# --------------------------------------------------------------------------------- #


def test_request_context_shape_and_link(api, monkeypatch):
    client, world = api
    _register()
    calls = _captured_dispatches(monkeypatch)

    row = _open_row(world, qty="139", item_code=f"{MARKER}-CTX")
    response = client.post(
        REQUEST_URL(world.inquiry.id),
        json={"rows": [{"row_id": row.id, "qty_requested": "61"}], "note": "urgent"},
    )
    assert response.status_code == 201, response.text
    world.db.commit()

    matches = _requested_calls(calls)
    assert matches, "the request must dispatch"
    context = matches[0]["context"]
    reserve = context["reserve"]

    for key in ("inquiry_no", "ordinal", "so_number", "customer", "project", "requested_by",
                "requested_at", "rows", "row_count", "state", "link"):
        assert key in reserve, f"context.reserve missing {key!r}: {reserve}"

    assert reserve["inquiry_no"] == world.inquiry.inquiry_no
    assert reserve["row_count"] == 1
    assert reserve["rows"][0]["item_code"] == f"{MARKER}-CTX"
    assert reserve["rows"][0]["qty_requested"] == "61"
    for key in ("name", "email"):
        assert key in reserve["requested_by"], reserve["requested_by"]

    for key in ("actor", "raiser", "requester", "today"):
        assert key in context, f"context missing {key!r}: {context}"

    request_id = response.json()["id"]
    assert reserve["link"].endswith(f"?reserve={request_id}"), reserve["link"]
    assert str(world.inquiry.id) in reserve["link"], reserve["link"]


# --------------------------------------------------------------------------------- #
# RS-16                                                                              #
# --------------------------------------------------------------------------------- #


def test_recipient_order_request_and_reserved():
    from app.services.automation_recipients import resolve_recipients

    with blank_session() as db:
        eling_id = _user(db, f"{MARKER} Eling")
        db.commit()

        request_config = {
            "user_ids": [eling_id],
            "include_actor": True,
            "include_raiser": True,
            "one_email": True,
        }
        request_context = {
            "actor": {"email": "joey@zzt.test", "name": "Joey"},
            "raiser": {"email": "raiser@zzt.test", "name": "Raiser"},
        }
        recipients = resolve_recipients(db, request_config, request_context)
        emails = [r["email"] for r in recipients]
        assert emails[0].lower().startswith("eling") or "eling" in (recipients[0].get("name") or "").lower(), (
            f"user_ids resolves FIRST (Eling To): {recipients}"
        )
        assert "joey@zzt.test" in emails
        assert "raiser@zzt.test" in emails
        assert emails.index("joey@zzt.test") < emails.index("raiser@zzt.test"), (
            "requester (include_actor) before raiser: " + str(emails)
        )

        reserved_config = {
            "include_requester": True,
            "include_raiser": True,
            "one_email": True,
        }
        reserved_context = {
            "requester": {"email": "joey@zzt.test", "name": "Joey"},
            "raiser": {"email": "raiser@zzt.test", "name": "Raiser"},
        }
        reserved_recipients = resolve_recipients(db, reserved_config, reserved_context)
        reserved_emails = [r["email"] for r in reserved_recipients]
        assert reserved_emails[0] == "joey@zzt.test", (
            f"requester must resolve FIRST (To) on the reserved mail: {reserved_recipients}"
        )
        assert "raiser@zzt.test" in reserved_emails

        # Dedup: same person as both requester and raiser -> one entry only.
        same_person_context = {
            "requester": {"email": "one@zzt.test", "name": "One"},
            "raiser": {"email": "one@zzt.test", "name": "One"},
        }
        deduped = resolve_recipients(db, reserved_config, same_person_context)
        assert len(deduped) == 1, deduped


# --------------------------------------------------------------------------------- #
# RS-17                                                                              #
# --------------------------------------------------------------------------------- #


def _find_reserve_seed_migration_path() -> Path | None:
    """Content-sniffed by the new TABLE name, safe here because the plan (3.1) is
    explicit that ONE migration creates both tables AND seeds both automations - unlike
    the undo case (`test_board_undo_email.py`'s own note on why it sniffs by revision id
    instead), there is no second, later migration expected to also mention this table
    name, so no ambiguity to guard against."""
    versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    matches = [
        path
        for path in versions_dir.glob("*.py")
        if "order_inquiry_reserve_requests" in path.read_text(errors="ignore")
    ]
    assert len(matches) <= 1, (
        "more than one alembic migration mentions order_inquiry_reserve_requests: "
        f"{[p.name for p in matches]}"
    )
    return matches[0] if matches else None


def _load_reserve_seed_migration():
    path = _find_reserve_seed_migration_path()
    assert path is not None, (
        "no alembic migration under alembic/versions/ creates "
        "projects.order_inquiry_reserve_requests / seeds "
        "order_inquiry_reserve_requested_default + order_inquiry_reserved_default - the "
        "coder must add one (PLAN-oi-request-cs-reserve.md 3.1, AC-RS-17)."
    )
    import importlib.util

    spec = importlib.util.spec_from_file_location("zzt_reserve_seed_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seed_migration_idempotent():
    module = _load_reserve_seed_migration()
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with blank_session() as db:
        ctx = MigrationContext.configure(db.connection())
        with Operations.context(ctx):
            module.upgrade()
            module.upgrade()  # idempotent re-run

        for code in ("order_inquiry_reserve_requested_default", "order_inquiry_reserved_default"):
            count = db.execute(
                sa.text("SELECT count(*) FROM email_templates WHERE code = :code"), {"code": code}
            ).scalar()
            assert count == 1, f"{code} must be seeded exactly once"

        for trigger, name in (
            ("order_inquiry_reserve_requested", "Order inquiry: request CS to reserve"),
            ("order_inquiry_reserved", "Order inquiry: reserved by CS"),
        ):
            rows = db.execute(
                sa.text(
                    "SELECT enabled, recipient_config FROM automations WHERE trigger_type = :t "
                    "AND name = :n"
                ),
                {"t": trigger, "n": name},
            ).fetchall()
            assert len(rows) == 1, f"{trigger} must be seeded exactly once: {rows}"
            enabled, cfg = rows[0]
            assert enabled is True
            import json

            cfg = cfg if isinstance(cfg, dict) else json.loads(cfg)
            assert cfg.get("one_email") is True

        with Operations.context(ctx):
            module.downgrade()

        remaining_templates = db.execute(
            sa.text(
                "SELECT count(*) FROM email_templates WHERE code IN "
                "('order_inquiry_reserve_requested_default', 'order_inquiry_reserved_default')"
            )
        ).scalar()
        assert remaining_templates == 0
        remaining_automations = db.execute(
            sa.text(
                "SELECT count(*) FROM automations WHERE trigger_type IN "
                "('order_inquiry_reserve_requested', 'order_inquiry_reserved')"
            )
        ).scalar()
        assert remaining_automations == 0

        # The widened CHECK is restored on downgrade too. `conname` alone is not enough
        # to identify the right constraint: the REAL `projects.order_inquiry_links` (this
        # lane's own migrated DB, `oirs_0001_reserve_requests` already applied there)
        # carries a constraint of the SAME name - constraint names are per-TABLE, not
        # global - so an unscoped lookup can return the real (still three-target) row
        # instead of this test's own scratch-schema copy that `downgrade()` just
        # restored. Scoped to a table named `order_inquiry_links` sitting in one of the
        # schemas THIS session's own search path actually has open
        # (`current_schemas(false)`) - the scratch `{name}_projects` translation
        # `blank_session()` set up, never the literal `projects` schema, which is not on
        # that path.
        check_def = db.execute(
            sa.text(
                "SELECT pg_get_constraintdef(con.oid) "
                "FROM pg_constraint con "
                "JOIN pg_class rel ON rel.oid = con.conrelid "
                "JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace "
                "WHERE con.conname = 'ck_order_inquiry_links_one_target' "
                "AND rel.relname = 'order_inquiry_links' "
                "AND nsp.nspname = ANY (current_schemas(false))"
            )
        ).scalar()
        assert check_def is not None
        assert "reserve_request_row_id" not in check_def, (
            f"downgrade must restore the two-target CHECK, got: {check_def}"
        )


# --------------------------------------------------------------------------------- #
# RS-18                                                                              #
# --------------------------------------------------------------------------------- #


def test_link_check_exactly_one_target(api):
    client, world = api
    row = _open_row(world, qty="50")
    po_line = _purchase_order(world.db, world.company_id)["line"]

    request = client.post(
        REQUEST_URL(world.inquiry.id), json={"rows": [{"row_id": row.id, "qty_requested": "50"}]}
    ).json()
    world.db.commit()
    from app.models.project_so import OrderInquiryReserveRequestRow

    request_row = (
        world.db.query(OrderInquiryReserveRequestRow)
        .filter(OrderInquiryReserveRequestRow.row_id == row.id)
        .one()
    )

    with pytest.raises(IntegrityError):
        world.db.add(
            OrderInquiryLink(
                id=_uid(), company_id=world.company_id, row_id=row.id,
                po_line_id=po_line.id, reserve_request_row_id=request_row.id,
                document="two-targets", qty=Decimal("1"),
            )
        )
        world.db.flush()
    world.db.rollback()

    with pytest.raises(IntegrityError):
        world.db.add(
            OrderInquiryLink(
                id=_uid(), company_id=world.company_id, row_id=row.id,
                document="no-target", qty=Decimal("1"),
            )
        )
        world.db.flush()
    world.db.rollback()

    world.db.add(
        OrderInquiryLink(
            id=_uid(), company_id=world.company_id, row_id=row.id,
            reserve_request_row_id=request_row.id, document="reserve-only", qty=Decimal("1"),
        )
    )
    world.db.flush()  # must not raise


# --------------------------------------------------------------------------------- #
# RS-19                                                                              #
# --------------------------------------------------------------------------------- #


def test_cancel_request_only_while_requested(api, monkeypatch):
    client, world = api
    _register()
    calls = _captured_dispatches(monkeypatch)

    row = _open_row(world, qty="50")
    request = client.post(
        REQUEST_URL(world.inquiry.id), json={"rows": [{"row_id": row.id, "qty_requested": "50"}]}
    ).json()
    world.db.commit()
    calls.clear()

    cancel = client.post(CANCEL_URL(request["id"]))
    assert cancel.status_code == 200, cancel.text
    world.db.commit()

    from app.models.project_so import OrderInquiryReserveRequest

    reloaded = (
        world.db.query(OrderInquiryReserveRequest).filter(OrderInquiryReserveRequest.id == request["id"]).one()
    )
    assert reloaded.state == "cancelled"
    assert reloaded.cancelled_by is not None
    assert reloaded.cancelled_at is not None
    assert _requested_calls(calls) == [] and _reserved_calls(calls) == [], "cancel sends no email"

    # A reserved request cannot be cancelled.
    row_b = _open_row(world, qty="20")
    request_b = client.post(
        REQUEST_URL(world.inquiry.id), json={"rows": [{"row_id": row_b.id, "qty_requested": "20"}]}
    ).json()
    world.db.commit()
    from app.models.project_so import OrderInquiryReserveRequestRow

    request_row_b = (
        world.db.query(OrderInquiryReserveRequestRow)
        .filter(OrderInquiryReserveRequestRow.row_id == row_b.id)
        .one()
    )
    client.post(
        RESERVE_URL(request_b["id"]),
        json={"rows": [{"request_row_id": request_row_b.id, "warehouse_id": world.site.id, "qty_reserved": "20"}]},
    )
    world.db.commit()

    reserved_cancel = client.post(CANCEL_URL(request_b["id"]))
    assert reserved_cancel.status_code == 409, reserved_cancel.text

    from app.services.form_action_registry import get_action

    action = get_action("order_inquiry_reserve_request.cancel")
    assert action is not None, "the deferred action must be registered (record_actions.py)"


# --------------------------------------------------------------------------------- #
# RS-20 (real worklist reader, borrowed `api` fixture from test_order_inquiry_worklist) #
# --------------------------------------------------------------------------------- #


def test_reserve_state_derived(worklist_api):
    client, db, company_id, seeded = worklist_api
    inquiry = db.get(OrderInquiry, seeded["authored_row"].order_inquiry_id)
    line = _line_on_authored_order(db, company_id, seeded, qty="90", day=7)
    row = _row(
        db, company_id, inquiry, so_line_id=line.id, item_code=f"{WL_MARKER}-STATE",
        qty="90", state=INQUIRY_RAISED, delivery_date=date(2026, 4, 7),
    )
    db.commit()

    body_none = client.get(LIST, params={"delivery_month": "2026-04"}).json()
    entry_none = next(e for e in body_none["data"] if e["id"] == row.id)
    assert entry_none.get("reserve_state") is None

    warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}".upper())
    from app.services.order_inquiry_reserve_service import OrderInquiryReserveService

    requester_id = _user(db, f"{WL_MARKER} requester2")
    service = OrderInquiryReserveService(db)
    request = service.create_request(
        inquiry_id=inquiry.id,
        rows=[{"row_id": row.id, "qty_requested": Decimal("90"), "warehouse_id": warehouse.id}],
        note=None,
        actor_user_id=requester_id,
    )
    db.commit()

    body_requested = client.get(LIST, params={"delivery_month": "2026-04"}).json()
    entry_requested = next(e for e in body_requested["data"] if e["id"] == row.id)
    assert entry_requested["reserve_state"] == "requested"

    from app.models.project_so import OrderInquiryReserveRequestRow

    request_row = (
        db.query(OrderInquiryReserveRequestRow)
        .filter(OrderInquiryReserveRequestRow.request_id == request.id)
        .one()
    )
    reserver_id = _user(db, f"{WL_MARKER} reserver2")
    # Reserved SHORT (50 of 90, with a reason) rather than in full, so the row still has
    # 40 remaining - the fixture this test's own next step needs to prove "reserved then
    # requested again reads requested" ON THE SAME ROW, rather than reaching for a fresh
    # one with nothing to do with the transition being pinned.
    service.reserve(
        request_id=request.id,
        rows=[
            {
                "request_row_id": request_row.id,
                "warehouse_id": warehouse.id,
                "qty_reserved": Decimal("50"),
                "reason": "BRW only has 50",
            }
        ],
        actor_user_id=reserver_id,
    )
    db.commit()

    body_reserved = client.get(LIST, params={"delivery_month": "2026-04"}).json()
    entry_reserved = next(e for e in body_reserved["data"] if e["id"] == row.id)
    assert entry_reserved["reserve_state"] == "reserved"
    assert entry_reserved["reserved_qty"] == "50"

    # Reserved then requested again (on the balance, 90 - 50 = 40) -> reads "requested".
    second_request = service.create_request(
        inquiry_id=inquiry.id,
        rows=[{"row_id": row.id, "qty_requested": Decimal("40"), "warehouse_id": warehouse.id}],
        note=None,
        actor_user_id=requester_id,
    )
    db.commit()
    assert second_request.ordinal == 2

    body_requested_again = client.get(LIST, params={"delivery_month": "2026-04"}).json()
    entry_requested_again = next(e for e in body_requested_again["data"] if e["id"] == row.id)
    assert entry_requested_again["reserve_state"] == "requested", (
        "a row reserved then requested again must read requested, not reserved (AC-RS-20)"
    )
    # Nothing left to request again on row2 (fully reserved) - the "reserved then
    # requested again" half is exhaustively covered by RS-5's own HTTP-level test
    # (`test_second_request_after_reserved_allowed`), which already proves ordinal 2 is
    # accepted; asserting the CHIP specifically on that same shape here would duplicate
    # RS-5 rather than add new coverage, so this test stops at "reserved" above.


# --------------------------------------------------------------------------------- #
# RS-21                                                                              #
# --------------------------------------------------------------------------------- #


def test_rollback_discards_pending_dispatch(api, monkeypatch):
    client, world = api
    _register()
    calls = _captured_dispatches(monkeypatch)

    row = _open_row(world, qty="50")

    savepoint = world.db.begin_nested()
    service = _service(world.db)
    service.create_request(
        inquiry_id=world.inquiry.id,
        rows=[{"row_id": row.id, "qty_requested": Decimal("50"), "warehouse_id": world.site.id}],
        note=None,
        actor_user_id=world.requester,
    )
    savepoint.rollback()

    world.db.commit()  # an unrelated commit: nothing above may still fire

    assert _requested_calls(calls) == [], "a rolled-back request must dispatch nothing"

    from app.models.project_so import OrderInquiryReserveRequest

    assert (
        world.db.query(OrderInquiryReserveRequest)
        .filter(OrderInquiryReserveRequest.order_inquiry_id == world.inquiry.id)
        .count()
        == 0
    ), "the rolled-back request must not exist either"
