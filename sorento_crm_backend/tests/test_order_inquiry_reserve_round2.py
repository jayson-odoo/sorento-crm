"""Order inquiry: Request CS to reserve - REVIEW ROUND 2 (`PLAN-oi-request-cs-reserve.md`
section 6c, owner rulings 22 Sep evening).

Contract: `documentation/plans/scm/oi-request-cs-reserve-acceptance-criteria.md`,
AC-RS-53 to AC-RS-60 (backend half of round 2). TEST-FIRST: written against the plan's
own words, before the coder has touched a line of round-2 code - `order_inquiry_reserve_
service.py`, `order_inquiries.py`'s routes and `app/models/user.py`'s `SystemSetting`
still carry only what round 1 shipped. A red here must be a missing route/column/table,
a 404, or an assertion on behaviour the plan states does not exist yet - never an import
typo or a fixture bug.

Postgres only, `tests/_pg_fixture.py`. Every FK chain is seeded here or borrowed from an
already-seeded helper in `test_order_inquiry_reserve.py` (round 1's own fixtures: `_api`,
`_seeded_world`, `_open_row`, ...) or `test_planning_changes.py` / `test_stock_detail_
locations.py` (`_product`, `_warehouse`) - never `LIMIT 1` off a shared table, CI's own
database is empty.

NAMED ASSUMPTIONS (per the tester's brief - the plan leaves several exact shapes open,
and a test-first suite IS what pins them, same convention `test_order_inquiry_reserve
.py`'s own docstring states):

1. **`{row_id}` in every new per-row route is `OrderInquiryRow.id`**, never `OrderInquiry
   ReserveRequestRow.id`. The plan's own words are "POST .../reserve-requests/{id}/rows/
   {row_id}/reserve" with no separate `request_row_id` in the path - and `row_id` means
   "an `order_inquiry_rows.id`" everywhere ELSE in this codebase (`ProjectOrderInquiry
   Service.unplace(row_id, ...)`, `_row_or_404`, the `rows[].row_id` key the CREATE
   payload already uses). The Lines grid already holds this id on every row it renders
   (AC-RS-61's own Reserve icon-button), so the FE needs no extra lookup to open the
   dialog - the strongest argument for this reading over the request-row's own id.
   Routes pinned exactly:
   - `POST {LIST}/reserve-requests/{request_id}/rows/{row_id}/reserve`
     `{ warehouse_id, qty_reserved, reason? }` -> 200 the answered request row (F2).
   - `POST {LIST}/reserve-requests/{request_id}/rows/{row_id}/unreserve`
     `{ qty, note? }` -> 200 (F5).
   - `GET {LIST}/reserve-requests/{request_id}/rows/{row_id}/history` -> a list, newest
     first (F3). The plan states no exact shape beyond "requested / reserved / unreserved
     / cancelled entries with actor name and timestamp" - pinned here as
     `{kind, qty, location, reason, actor_name, created_at}` per entry, `kind` one of
     those four strings.
2. **A conflict on the per-row Unlink of a reserve link is 409**, not 422: F5's own words
   are "the per-row Unlink is not offered on a reserve link", which is a STATE/kind
   conflict about the target the caller named (same family as `unplace`'s existing 409
   "This row is not linked to anything"), not a shape problem with the request body -
   422 is reserved elsewhere in this file for a bad qty/reason/warehouse.
3. `system_settings.oi_reserve_default_pool_warehouse_id` is validated the same way
   `default_uom_id` / the approver ids already are on `PUT .../settings/general`: a 422
   when the id does not resolve to an ACTIVE POOL warehouse (bare code, no group
   suffix) - a group warehouse (one carrying a `-SUFFIX` code, or one another warehouse's
   `pool_warehouse_id` already names as ITS pool) is refused by name.
4. F1's "every active own-company pool warehouse" widens `group_netting.netting_for_
   products`'s own membership rule for the `pools` axis specifically for THIS purpose -
   measured today (`app/services/scm/group_netting.py:284-288`) that function only
   counts a warehouse as a pool when some OTHER active warehouse's `pool_warehouse_id`
   already names it, so a standalone pool with no group members under it (WH3 in AC-RS-
   53's own fixture) is invisible to `stock-detail?group=pools` right now - this is the
   gap `test_pool_location_options_every_active_pool` pins as the fix's own target.
"""
from __future__ import annotations

import importlib.util
import re
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.models.project_so import (
    INQUIRY_RAISED,
    OrderInquiryLink,
    OrderInquiryRow,
)
from app.services.error_handler import AppException

from ._pg_fixture import blank_session
from .test_order_inquiry_reserve import (
    REQUESTER_PERMISSIONS,
    RESERVE_URL as OLD_ALL_ROWS_RESERVE_URL,
    REQUEST_URL,
    _as,
    _captured_dispatches,
    _open_row,
    _register,
    _reserved_calls,
    api as reserve_api,  # noqa: F401  (re-exported fixture: both permissions)
)
from .test_order_inquiry_worklist import LIST, _purchase_order, _uid
from .test_planning_changes import _product, _warehouse

MARKER = "zzt-oi-reserve-r2"

ROW_RESERVE_URL = lambda request_id, row_id: (  # noqa: E731
    f"{LIST}/reserve-requests/{request_id}/rows/{row_id}/reserve"
)
ROW_UNRESERVE_URL = lambda request_id, row_id: (  # noqa: E731
    f"{LIST}/reserve-requests/{request_id}/rows/{row_id}/unreserve"
)
ROW_HISTORY_URL = lambda request_id, row_id: (  # noqa: E731
    f"{LIST}/reserve-requests/{request_id}/rows/{row_id}/history"
)

_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)


# --------------------------------------------------------------------------------- #
# AC-RS-53: pool location options = every ACTIVE pool, not only ones a group member  #
# points at                                                                          #
# --------------------------------------------------------------------------------- #


def test_pool_location_options_every_active_pool():
    """A "site pool" is what the board's own pools axis already returns
    (`stock-detail?group=pools`): a warehouse some OTHER active warehouse's own
    `pool_warehouse_id` names (`group_netting.py:284-288`, unchanged by this fix -
    captain's ruling, review round). So each of BRW, DC1, WH3 is seeded here WITH a
    group member pointing at it, the same shape `test_fulfilment_board.py::
    test_the_pools_drill_lists_every_site_pool_even_for_an_agent_with_no_group`
    (`_pooled_warehouses`) already uses - this is "every ACTIVE pool is offered",
    not "a standalone warehouse with no member becomes one"."""
    from app.services.project_fulfilment_board_service import FulfilmentBoardService

    with blank_session() as db:
        product = _product(db)
        brw = _warehouse(db, f"ZZBRW{_uid()[:4]}")
        brw_member = _warehouse(db, f"{brw.warehouse_code}-IR", pool_warehouse_id=brw.id)
        dc1 = _warehouse(db, f"ZZDC1{_uid()[:4]}")
        dc1_member = _warehouse(db, f"{dc1.warehouse_code}-IB", pool_warehouse_id=dc1.id)
        wh3 = _warehouse(db, f"ZZWH3{_uid()[:4]}")
        wh3_member = _warehouse(db, f"{wh3.warehouse_code}-NTC", pool_warehouse_id=wh3.id)
        inactive_pool = _warehouse(db, f"ZZOFF{_uid()[:4]}")
        _warehouse(db, f"{inactive_pool.warehouse_code}-XX", pool_warehouse_id=inactive_pool.id)
        inactive_pool.is_active = False
        db.flush()

        detail = FulfilmentBoardService(db).stock_detail(str(product.id), None, group="pools")

        codes = {entry["location"] for entry in detail["locations"]}
        assert {brw.warehouse_code, dc1.warehouse_code, wh3.warehouse_code} <= codes, (
            f"F1: every ACTIVE pool warehouse must be offered: {codes}"
        )
        for group_wh in (brw_member, dc1_member, wh3_member):
            assert group_wh.warehouse_code not in codes, (
                f"a group warehouse ({group_wh.warehouse_code}) is not a pool: {codes}"
            )
        assert inactive_pool.warehouse_code not in codes, (
            f"an inactive pool must be absent, even with a group member: {codes}"
        )
        for entry in detail["locations"]:
            if entry["location"] in {brw.warehouse_code, dc1.warehouse_code, wh3.warehouse_code}:
                assert entry.get("available_qty") is not None, entry


# --------------------------------------------------------------------------------- #
# AC-RS-54: system_settings.oi_reserve_default_pool_warehouse_id                    #
# --------------------------------------------------------------------------------- #


def test_default_pool_setting_column_in_schema_and_payload():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.database import get_db
    from app.dependencies import get_current_user
    from app.models.user import SystemSetting
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    with blank_session() as db:
        brw = _warehouse(db, f"ZZBRW{_uid()[:4]}")
        group_wh = _warehouse(db, f"{brw.warehouse_code}-IR", pool_warehouse_id=brw.id)
        db.add(SystemSetting(id=str(uuid.uuid4()), name=f"{MARKER} Co {_uid()[:6]}"))
        db.commit()

        caller = {"id": str(uuid.uuid4()), "email": f"{MARKER}-settings@zzt.test"}

        def _override_db():
            yield db

        # `warehouses` is company-scoped, and a principal with no grants resolves to
        # UNSET - fail-closed, zero rows - so the PUT's own validation lookup would
        # never find `brw`/`group_wh` at all. `None` is the documented "no predicate"
        # state (same fix `test_default_uom_setting.py::settings_api` names for the
        # identical trap): this test is about the column, not about isolation.
        async def _scope():
            from app.models.base import set_company_scope

            set_company_scope(db, None)
            return None

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: dict(caller)
        app.dependency_overrides[apply_company_scope] = _scope
        original_check = UserPermissionService.check_user_has_permission
        UserPermissionService.check_user_has_permission = lambda self, uid, slug: True
        try:
            with TestClient(app) as client:
                full = client.get("/api/v1/user-management/settings/")
                assert full.status_code == 200, full.text
                assert "oi_reserve_default_pool_warehouse_id" in full.json()["settings"], (
                    "F1/AC-RS-54: a new settings column reaches the FE only if it is on "
                    "the manual GET dict too - missing today: "
                    f"{sorted(full.json()['settings'].keys())}"
                )

                ok = client.put(
                    "/api/v1/user-management/settings/general",
                    json={"oi_reserve_default_pool_warehouse_id": brw.id},
                )
                assert ok.status_code == 200, ok.text
                assert (
                    client.get("/api/v1/user-management/settings/").json()["settings"][
                        "oi_reserve_default_pool_warehouse_id"
                    ]
                    == brw.id
                )

                cleared = client.put(
                    "/api/v1/user-management/settings/general",
                    json={"oi_reserve_default_pool_warehouse_id": None},
                )
                assert cleared.status_code == 200, cleared.text
                assert (
                    client.get("/api/v1/user-management/settings/").json()["settings"][
                        "oi_reserve_default_pool_warehouse_id"
                    ]
                    is None
                )

                bad = client.put(
                    "/api/v1/user-management/settings/general",
                    json={"oi_reserve_default_pool_warehouse_id": group_wh.id},
                )
                assert bad.status_code == 422, (
                    "a GROUP warehouse (a code with a hyphen, another warehouse's own "
                    f"pool) must be refused: {bad.status_code} {bad.text}"
                )
        finally:
            UserPermissionService.check_user_has_permission = original_check
            app.dependency_overrides.clear()


# --------------------------------------------------------------------------------- #
# AC-RS-56 / AC-RS-57: per-row reserve, the all-rows endpoint retired                #
# --------------------------------------------------------------------------------- #


def test_reserve_one_row_endpoint_answers_row_by_row(reserve_api, monkeypatch):
    client, world = reserve_api
    _register()
    calls = _captured_dispatches(monkeypatch)

    row_a = _open_row(world, qty="50")
    row_b = _open_row(world, qty="30")
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

    # row_a fully answered - the REQUEST stays open (row_b unanswered), F2.
    first = client.post(
        ROW_RESERVE_URL(request_id, row_a.id),
        json={"warehouse_id": world.site.id, "qty_reserved": "50"},
    )
    assert first.status_code == 200, first.text
    world.db.commit()

    from app.models.project_so import OrderInquiryReserveRequest

    reloaded = (
        world.db.query(OrderInquiryReserveRequest)
        .filter(OrderInquiryReserveRequest.id == request_id)
        .one()
    )
    assert reloaded.state == "requested", (
        "one row still unanswered - the request must stay open while any row is (F2)"
    )
    assert _reserved_calls(calls) == [], "no email until EVERY row of the request is answered"

    # answering row_a again -> 409, already answered.
    again = client.post(
        ROW_RESERVE_URL(request_id, row_a.id),
        json={"warehouse_id": world.site.id, "qty_reserved": "50"},
    )
    assert again.status_code == 409, again.text

    # a row belonging to a DIFFERENT request -> 404.
    other_row = _open_row(world, qty="10")
    other_request = client.post(
        REQUEST_URL(world.inquiry.id),
        json={"rows": [{"row_id": other_row.id, "qty_requested": "10"}]},
    ).json()
    world.db.commit()
    wrong = client.post(
        ROW_RESERVE_URL(request_id, other_row.id),
        json={"warehouse_id": world.site.id, "qty_reserved": "10"},
    )
    assert wrong.status_code == 404, wrong.text

    # row_b answered SHORT with no reason -> 422 (3.3 validation carries over per-row).
    short_no_reason = client.post(
        ROW_RESERVE_URL(request_id, row_b.id),
        json={"warehouse_id": world.site.id, "qty_reserved": "10"},
    )
    assert short_no_reason.status_code == 422, short_no_reason.text

    # row_b answered SHORT with a reason -> 200, and this COMPLETES the request:
    # `reserved`, ONE dispatch, every row named in the context.
    last = client.post(
        ROW_RESERVE_URL(request_id, row_b.id),
        json={
            "warehouse_id": world.site.id,
            "qty_reserved": "10",
            "reason": "DC1 only has 10",
        },
    )
    assert last.status_code == 200, last.text
    world.db.commit()

    world.db.expire_all()
    reloaded2 = (
        world.db.query(OrderInquiryReserveRequest)
        .filter(OrderInquiryReserveRequest.id == request_id)
        .one()
    )
    assert reloaded2.state == "reserved"

    matches = _reserved_calls(calls)
    assert len(matches) == 1, f"exactly ONE dispatch, only on completion: {matches}"
    context_rows = matches[0]["context"]["reserve"]["rows"]
    assert len(context_rows) == 2, (
        f"every row must be in the completion context, not only the last answer: {context_rows}"
    )


def test_all_rows_reserve_endpoint_removed(reserve_api):
    client, world = reserve_api
    row = _open_row(world, qty="50")
    created = client.post(
        REQUEST_URL(world.inquiry.id), json={"rows": [{"row_id": row.id, "qty_requested": "50"}]}
    )
    assert created.status_code == 201, created.text
    world.db.commit()
    request_id = created.json()["id"]

    response = client.post(
        OLD_ALL_ROWS_RESERVE_URL(request_id),
        json={
            "rows": [
                {"request_row_id": str(uuid.uuid4()), "warehouse_id": world.site.id, "qty_reserved": "50"}
            ]
        },
    )
    assert response.status_code in (404, 405), (
        "F2 deletes the all-rows reserve endpoint (one seam - 3.3 is superseded); a "
        f"200 here means it is still live: {response.status_code} {response.text}"
    )


# --------------------------------------------------------------------------------- #
# AC-RS-58: unreserve, its own action                                               #
# --------------------------------------------------------------------------------- #


def test_unreserve_endpoint(reserve_api, monkeypatch):
    client, world = reserve_api
    _register()
    calls = _captured_dispatches(monkeypatch)

    row = _open_row(world, qty="50")
    created = client.post(
        REQUEST_URL(world.inquiry.id), json={"rows": [{"row_id": row.id, "qty_requested": "50"}]}
    )
    assert created.status_code == 201, created.text
    world.db.commit()
    request_id = created.json()["id"]

    reserved = client.post(
        ROW_RESERVE_URL(request_id, row.id),
        json={"warehouse_id": world.site.id, "qty_reserved": "50"},
    )
    assert reserved.status_code == 200, reserved.text
    world.db.commit()
    calls.clear()

    with _as(world.db, world.requester, REQUESTER_PERMISSIONS) as stranger:
        forbidden = stranger.post(ROW_UNRESERVE_URL(request_id, row.id), json={"qty": "10"})
    assert forbidden.status_code == 403, forbidden.text

    zero = client.post(ROW_UNRESERVE_URL(request_id, row.id), json={"qty": "0"})
    assert zero.status_code == 422, zero.text

    over = client.post(ROW_UNRESERVE_URL(request_id, row.id), json={"qty": "51"})
    assert over.status_code == 422, over.text
    assert "50" in over.text, f"the 422 must NAME the net-reserved limit: {over.text}"

    partial = client.post(
        ROW_UNRESERVE_URL(request_id, row.id), json={"qty": "20", "note": "transferred back"}
    )
    assert partial.status_code == 200, partial.text
    world.db.commit()

    from app.models.project_so import OrderInquiryReserveRequestRow

    request_row = (
        world.db.query(OrderInquiryReserveRequestRow)
        .filter(OrderInquiryReserveRequestRow.row_id == row.id)
        .one()
    )
    world.db.expire_all()
    link = (
        world.db.query(OrderInquiryLink)
        .filter(OrderInquiryLink.reserve_request_row_id == request_row.id)
        .one()
    )
    assert link.qty == Decimal("30"), link.qty

    full = client.post(ROW_UNRESERVE_URL(request_id, row.id), json={"qty": "30"})
    assert full.status_code == 200, full.text
    world.db.commit()

    world.db.expire_all()
    assert (
        world.db.query(OrderInquiryLink)
        .filter(OrderInquiryLink.reserve_request_row_id == request_row.id)
        .count()
        == 0
    ), "the link must be DELETED at net 0, not left sitting at qty 0"

    refreshed_row = world.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row.id).one()
    assert refreshed_row.state == INQUIRY_RAISED, (
        "unreserving everything must restore the row's own state (refresh_link_state)"
    )

    events = world.db.execute(
        sa.text(
            "SELECT count(*) FROM order_inquiry_reserve_events "
            "WHERE reserve_request_row_id = :rr AND kind = 'unreserved'"
        ),
        {"rr": request_row.id},
    ).scalar()
    assert events == 2, f"one 'unreserved' event PER unreserve call (F3): {events}"

    assert _reserved_calls(calls) == [], "unreserve must send no email (F5)"


# --------------------------------------------------------------------------------- #
# AC-RS-59: Unlink skips reserve links entirely                                     #
# --------------------------------------------------------------------------------- #


def test_unlink_never_touches_a_reserve_link(reserve_api):
    client, world = reserve_api
    row = _open_row(world, qty="200")
    po_line = _purchase_order(world.db, world.company_id)["line"]
    world.db.add(
        OrderInquiryLink(
            id=_uid(), company_id=world.company_id, row_id=row.id,
            po_line_id=po_line.id, document="ZZT-PO-KEEP", qty=Decimal("40"),
        )
    )
    world.db.commit()

    created = client.post(
        REQUEST_URL(world.inquiry.id), json={"rows": [{"row_id": row.id, "qty_requested": "150"}]}
    )
    assert created.status_code == 201, created.text
    world.db.commit()
    request_id = created.json()["id"]
    reserved = client.post(
        ROW_RESERVE_URL(request_id, row.id),
        json={
            "warehouse_id": world.site.id,
            "qty_reserved": "50",
            "reason": "BRW only has 50 in stock",
        },
    )
    assert reserved.status_code == 200, reserved.text
    world.db.commit()

    from app.models.project_so import OrderInquiryReserveRequestRow

    request_row = (
        world.db.query(OrderInquiryReserveRequestRow)
        .filter(OrderInquiryReserveRequestRow.row_id == row.id)
        .one()
    )
    reserve_link = (
        world.db.query(OrderInquiryLink)
        .filter(OrderInquiryLink.reserve_request_row_id == request_row.id)
        .one()
    )

    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    service = ProjectOrderInquiryService(world.db)

    # Bulk unlink: PO link removed, reserve link left standing.
    service.unplace_rows([row.id])
    world.db.commit()
    world.db.expire_all()
    remaining = world.db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id == row.id).all()
    remaining_ids = {link.id for link in remaining}
    assert reserve_link.id in remaining_ids, (
        f"F5: the BULK Unlink must SKIP a reserve link, not delete it: {remaining_ids}"
    )
    assert all(link.po_line_id is None for link in remaining), (
        f"the PO link must be gone: {[(link.id, link.po_line_id) for link in remaining]}"
    )

    # Per-row unlink against the reserve link's OWN id is refused.
    with pytest.raises(AppException) as excinfo:
        service.unplace(row.id, actor_user_id=world.requester, link_id=reserve_link.id)
    assert excinfo.value.status_code in (409, 422), excinfo.value.status_code
    world.db.rollback()


# --------------------------------------------------------------------------------- #
# AC-RS-60: history, newest first                                                   #
# --------------------------------------------------------------------------------- #


def test_reserve_row_history(reserve_api):
    client, world = reserve_api
    row = _open_row(world, qty="50")
    created = client.post(
        REQUEST_URL(world.inquiry.id), json={"rows": [{"row_id": row.id, "qty_requested": "50"}]}
    )
    assert created.status_code == 201, created.text
    world.db.commit()
    request_id = created.json()["id"]

    reserved = client.post(
        ROW_RESERVE_URL(request_id, row.id),
        json={"warehouse_id": world.site.id, "qty_reserved": "30", "reason": "DC1 only has 30"},
    )
    assert reserved.status_code == 200, reserved.text
    world.db.commit()

    unreserved = client.post(
        ROW_UNRESERVE_URL(request_id, row.id), json={"qty": "10", "note": "transferred back"}
    )
    assert unreserved.status_code == 200, unreserved.text
    world.db.commit()

    history = client.get(ROW_HISTORY_URL(request_id, row.id))
    assert history.status_code == 200, history.text
    entries = history.json()
    assert isinstance(entries, list) and len(entries) >= 3, entries

    kinds = [entry["kind"] for entry in entries]
    assert kinds[0] == "unreserved", f"newest first: {kinds}"
    assert "reserved" in kinds and "requested" in kinds, kinds
    assert kinds.index("unreserved") < kinds.index("reserved") < kinds.index("requested"), kinds

    for entry in entries:
        assert entry.get("actor_name"), entry
        assert not _UUID_RE.search(str(entry["actor_name"])), (
            f"no UUID in the frontend UI (CLAUDE.md Cursor rules): {entry}"
        )
        assert entry.get("created_at"), entry


# --------------------------------------------------------------------------------- #
# Migration: the events table + the settings column, and their downgrade            #
# --------------------------------------------------------------------------------- #


def _versions_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _find_migration_mentioning(needle: str) -> Path | None:
    matches = [p for p in _versions_dir().glob("*.py") if needle in p.read_text(errors="ignore")]
    assert len(matches) <= 1, (
        f"more than one alembic migration mentions {needle!r}: {[m.name for m in matches]}"
    )
    return matches[0] if matches else None


def _oirs_0001_path() -> Path:
    return _versions_dir() / "oirs_0001_reserve_requests.py"


def _load_migration_module(path: Path):
    spec = importlib.util.spec_from_file_location(f"zzt2_{path.stem}_{_uid()[:6]}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _upgrade_chain(db, extra_path: Path | None) -> None:
    """Round 1's own migration first (always present, already merged in this lane), then
    the round-2 one too when it is a SEPARATE file - a no-op re-run when the coder
    instead amended `oirs_0001_reserve_requests.py` in place."""
    ctx = MigrationContext.configure(db.connection())
    base_path = _oirs_0001_path()
    assert base_path.exists(), "round 1's own migration is missing from this branch"
    with Operations.context(ctx):
        _load_migration_module(base_path).upgrade()
        if extra_path is not None and extra_path != base_path:
            _load_migration_module(extra_path).upgrade()


def _columns_of(db, table_name: str) -> set[str]:
    """Scoped to the SCRATCH copies of the search path only, never `public` - the real
    database (this lane's own CI DB is at `oirs_0002_reserve_round2` head already), where
    `system_settings.oi_reserve_default_pool_warehouse_id` legitimately exists. Without
    the exclusion, a downgrade of the SCRATCH schema's own column still reads it back via
    `public`'s real row and the assertion passes for the wrong reason."""
    return {
        row[0]
        for row in db.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :t AND table_schema = ANY (current_schemas(false)) "
                "AND table_schema <> 'public'"
            ),
            {"t": table_name},
        ).fetchall()
    }


def test_round2_migration_creates_events_table_with_downgrade():
    events_path = _find_migration_mentioning("order_inquiry_reserve_events")
    assert events_path is not None, (
        "no alembic migration creates projects.order_inquiry_reserve_events (plan 6c "
        "F3, AC-RS-60) - the coder must add one, either amending "
        "oirs_0001_reserve_requests.py or a new oirs_0002 revision chained onto it"
    )

    with blank_session() as db:
        _upgrade_chain(db, events_path)

        columns = _columns_of(db, "order_inquiry_reserve_events")
        for expected in (
            "id", "company_id", "reserve_request_row_id", "kind", "qty",
            "warehouse_id", "note", "actor_id", "created_at",
        ):
            assert expected in columns, f"missing column {expected!r} (plan 6c F3): {columns}"

        ctx = MigrationContext.configure(db.connection())
        with Operations.context(ctx):
            _load_migration_module(events_path).downgrade()

        remaining = db.execute(
            sa.text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_name = 'order_inquiry_reserve_events' "
                "AND table_schema = ANY (current_schemas(false))"
            )
        ).scalar()
        assert remaining == 0, "downgrade must drop order_inquiry_reserve_events"


def test_round2_migration_seeds_default_pool_setting_with_downgrade():
    settings_path = _find_migration_mentioning("oi_reserve_default_pool_warehouse_id")
    assert settings_path is not None, (
        "no alembic migration adds system_settings.oi_reserve_default_pool_warehouse_id "
        "(plan 6c F1, AC-RS-54) - the coder must add it"
    )

    with blank_session() as db:
        from app.models.user import SystemSetting

        brw = _warehouse(db, "BRW")
        db.add(SystemSetting(id=_uid(), name=f"{MARKER} Co {_uid()[:6]}"))
        db.commit()

        _upgrade_chain(db, settings_path)

        columns = _columns_of(db, "system_settings")
        assert "oi_reserve_default_pool_warehouse_id" in columns, columns

        seeded = db.execute(
            sa.text("SELECT oi_reserve_default_pool_warehouse_id FROM system_settings")
        ).scalar()
        assert str(seeded) == str(brw.id), (
            f"the migration must seed the column to the BRW pool BY CODE: got {seeded}"
        )

        ctx = MigrationContext.configure(db.connection())
        with Operations.context(ctx):
            _load_migration_module(settings_path).downgrade()

        remaining_columns = _columns_of(db, "system_settings")
        assert "oi_reserve_default_pool_warehouse_id" not in remaining_columns, (
            "downgrade must drop the settings column too"
        )
