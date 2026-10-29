"""OI-AUTO-CONFIRM slice 1: the system keeps `order_inquiry_rows.ack_state` right by itself.

Contract: `documentation/plans/scm/oi-auto-confirm-29oct-acceptance-criteria.md`
(AC-AC-1..21). TEST-FIRST (Phase 2): written with no implementation to look at. Nobody
presses Confirm / Unconfirm any more:

* a DONE row (full qty on LIVE links, or `actioned`, or a non-buy verb, or
  `redirected_to_pool`, or a companion whose host is done) is `acknowledged`, by NULL, at now;
* a row that is not done and reads `acknowledged` goes back to `awaiting`;
* `awaiting` / `changed` not done stay as they are; `rejected` is never touched.

Every row below is driven through a REAL service entry point (`place_on_po_allocations`,
`unplace`, `mark_rows`, `refresh_link_state`, the reserve commit route, the board confirm),
never by setting `ack_state` by hand after the write under test.

Four substrates, all Postgres, each test seeding its own chain:

* `bundle_world`: `tests/test_order_inquiry_bundles.py::_World` on a blank schema (raw PO
  lines, SPO allocations, companion rules);
* `api` / `world`: the handshake harness (board confirm, amend, buyer client) on the
  rolled-back real database;
* `reserve_api`: the reserve request/commit harness;
* `header_api`: the OI header list harness.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.product import Product
from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    ACK_AWAITING,
    ACK_CHANGED,
    ACK_REJECTED,
    OrderInquiryRow,
)
from app.models.user import User
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from .test_oi_header_list import HEADERS, _header, _sorento as _hdr_sorento
from .test_oi_header_list import api as header_api  # noqa: F401  (re-exported fixture)
from .test_order_inquiry_bundles import world as bundle_world  # noqa: F401  (fixture)
from .test_order_inquiry_handshake import (  # noqa: F401  (re-exported fixtures + helpers)
    LINK_NOW,
    LIST as HS_LIST,
    _as_purchasing,
    _confirm,
    _line_payload,
    _open_po_line,
    _raise_one_row,
    _settle,
    api,
    world,
)
from .test_order_inquiry_reserve import REQUEST_URL, _open_row, _register
from .test_order_inquiry_reserve import api as reserve_api  # noqa: F401  (fixture)
from .test_order_inquiry_reserve_commit import COMMIT_URL, _request
from .test_planning_changes import _warehouse

BASE = "/api/v1/project-sales"


def _uid() -> str:
    return str(uuid.uuid4())


def _new_user(db) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name="ZZT Buyer"))
    db.flush()
    return user_id


def _reload(db, row):
    db.refresh(row)
    return row


def _assert_done_by_system(row) -> None:
    """AC-AC-10c: done, stamped at the moment it became done, and nobody pressed anything."""
    assert row.ack_state == ACK_ACKNOWLEDGED
    assert row.acknowledged_by is None
    assert row.acknowledged_at is not None


# =============================================================================================
# Row writer, blank-schema world (PO lines, SPO allocations, companions)
# =============================================================================================


def test_ac_ac_1_a_full_po_link_marks_the_row_done_by_the_system(bundle_world):
    w = bundle_world
    row = w.row("CKS1050", 10, ack_state=ACK_AWAITING)
    line = w.purchase_order("CKS1050", "ZZT-AC1-PO", "S1", 10)

    w.svc.place_on_po_allocations(
        row.id, [{"po_line_id": line, "qty": Decimal("10")}], actor_user_id=None
    )

    _assert_done_by_system(_reload(w.db, row))


def test_ac_ac_2_a_full_spo_allocation_link_marks_the_row_done(bundle_world):
    w = bundle_world
    row = w.row("CKS1050", 10, ack_state=ACK_AWAITING)
    allocation = w.spo_allocation("CKS1050", "ZZT-AC2-SPO", 10)

    w.svc.place_on_po_allocations(
        row.id, [{"spo_allocation_id": allocation, "qty": Decimal("10")}], actor_user_id=None
    )

    _assert_done_by_system(_reload(w.db, row))


def test_ac_ac_3_po_six_plus_spo_four_on_a_qty_ten_row_is_done(bundle_world):
    w = bundle_world
    row = w.row("CKS1050", 10, ack_state=ACK_AWAITING)
    po_line = w.purchase_order("CKS1050", "ZZT-AC3-PO", "S1", 6)
    allocation = w.spo_allocation("CKS1050", "ZZT-AC3-SPO", 4)

    w.svc.place_on_po_allocations(
        row.id,
        [
            {"po_line_id": po_line, "qty": Decimal("6")},
            {"spo_allocation_id": allocation, "qty": Decimal("4")},
        ],
        actor_user_id=None,
    )

    _assert_done_by_system(_reload(w.db, row))


def test_ac_ac_5_po_covering_six_of_ten_leaves_the_row_awaiting(bundle_world):
    w = bundle_world
    row = w.row("CKS1050", 10, ack_state=ACK_AWAITING)
    line = w.purchase_order("CKS1050", "ZZT-AC5-PO", "S1", 6)

    w.svc.place_on_po_allocations(
        row.id, [{"po_line_id": line, "qty": Decimal("6")}], actor_user_id=None
    )

    _reload(w.db, row)
    assert row.ack_state == ACK_AWAITING
    assert row.acknowledged_at is None


def test_ac_ac_5_a_partly_covered_acknowledged_row_goes_back_to_awaiting(bundle_world):
    """Same AC, the other direction: an `acknowledged` row (the pre-feature state of most
    rows) whose live links cover only part of it is not done after any refresh."""
    w = bundle_world
    row = w.row("CKS1050", 10, ack_state=ACK_ACKNOWLEDGED)
    line = w.purchase_order("CKS1050", "ZZT-AC5B-PO", "S1", 6)
    w.svc.place_on_po_allocations(
        row.id, [{"po_line_id": line, "qty": Decimal("6")}], actor_user_id=None
    )

    w.svc.refresh_link_state([row])
    w.db.flush()

    assert _reload(w.db, row).ack_state == ACK_AWAITING


def test_ac_ac_6_a_placed_row_with_no_link_is_not_done(bundle_world):
    """A supply state of `placed` with nothing behind it is not done, whatever it reads."""
    w = bundle_world
    awaiting = w.row("CKS1050", 10, state="placed", ack_state=ACK_AWAITING)
    stale = w.row("CKS1050", 10, state="placed", ack_state=ACK_ACKNOWLEDGED)

    w.svc.refresh_link_state([awaiting, stale])
    w.db.flush()

    assert _reload(w.db, awaiting).ack_state == ACK_AWAITING
    assert _reload(w.db, stale).ack_state == ACK_AWAITING, "no live link: back to To order"


@pytest.mark.parametrize("verb", ["DELAY", "ADVANCE"])
def test_ac_ac_8_an_information_only_row_is_done_once_raised(bundle_world, verb):
    w = bundle_world
    row = w.row("CKS1050", 1, verb=verb, ack_state=ACK_AWAITING)

    w.svc.refresh_link_state([row])
    w.db.flush()

    _assert_done_by_system(_reload(w.db, row))


def test_ac_ac_8_a_row_redirected_to_the_pool_is_done(bundle_world):
    w = bundle_world
    row = w.row("CKS1050", 10, ack_state=ACK_AWAITING)
    w.db.execute(
        text(
            "UPDATE " + _p() + ".order_inquiry_rows SET redirected_to_pool = true WHERE id = :i"
        ),
        {"i": row.id},
    )
    w.db.flush()
    w.db.refresh(row)

    w.svc.refresh_link_state([row])
    w.db.flush()

    _assert_done_by_system(_reload(w.db, row))


def test_ac_ac_7_marking_a_row_actioned_marks_it_done(bundle_world):
    w = bundle_world
    row = w.row("CKS1050", 10, ack_state=ACK_AWAITING)
    buyer = _new_user(w.db)

    w.svc.mark_rows([row.id], state="actioned", actor_user_id=buyer)

    _assert_done_by_system(_reload(w.db, row))


def test_ac_ac_9_removing_the_link_reopens_the_row_and_relinking_completes_it(bundle_world):
    w = bundle_world
    row = w.row("CKS1050", 10, ack_state=ACK_AWAITING)
    line = w.purchase_order("CKS1050", "ZZT-AC9-PO", "S1", 10)
    buyer = _new_user(w.db)
    w.svc.place_on_po_allocations(
        row.id, [{"po_line_id": line, "qty": Decimal("10")}], actor_user_id=buyer
    )
    _assert_done_by_system(_reload(w.db, row))

    w.svc.unplace(row.id, actor_user_id=buyer)
    assert _reload(w.db, row).ack_state == ACK_AWAITING, "untag: not done, nobody pressed"

    w.svc.place_on_po_allocations(
        row.id, [{"po_line_id": line, "qty": Decimal("10")}], actor_user_id=buyer
    )
    _assert_done_by_system(_reload(w.db, row))


def test_ac_ac_9_a_cancelled_po_line_is_a_dead_link_and_the_row_is_not_done(bundle_world):
    """The REAL path that cancels a PO line is the document deletion arm
    (`DeletionService._deactivate("purchase_orders", ...)`, which sets every line
    `cancelled`). It does not re-derive the order inquiry row today, so this is expected
    RED until the implementation hooks it."""
    from app.services.deletion_service import DeletionService

    w = bundle_world
    row = w.row("CKS1050", 10, ack_state=ACK_AWAITING)
    line = w.purchase_order("CKS1050", "ZZT-AC9D-PO", "S1", 10)
    w.svc.place_on_po_allocations(
        row.id, [{"po_line_id": line, "qty": Decimal("10")}], actor_user_id=None
    )
    _assert_done_by_system(_reload(w.db, row))
    po_id = w.db.execute(
        text("SELECT purchase_order_id FROM purchase_order_lines WHERE id = :l"), {"l": line}
    ).scalar()

    DeletionService(w.db, company_id=w.company_id)._deactivate("purchase_orders", str(po_id))
    w.db.flush()

    assert _reload(w.db, row).ack_state != ACK_ACKNOWLEDGED, "the PO line behind the link died"


def test_ac_ac_10a_a_companion_follows_its_host_in_the_same_write(bundle_world):
    w = bundle_world
    w.rule("CKSW015", ["CKS1050"], supplier=None, ratio="1")
    host = w.row("CKS1050", 1, ack_state=ACK_AWAITING)
    companion = w.row("CKSW015", 1, ack_state=ACK_AWAITING)
    w.svc.derive_bundles(w.inquiry)
    w.db.flush()
    assert _reload(w.db, companion).bundled_qty == Decimal("1")
    assert _reload(w.db, companion).bundled_with_row_id == host.id

    w.svc.refresh_link_state([host, companion])
    w.db.flush()
    assert _reload(w.db, companion).ack_state == ACK_AWAITING, "host has no link: not done"
    assert _reload(w.db, host).ack_state == ACK_AWAITING

    line = w.purchase_order("CKS1050", "ZZT-AC10A-PO", "S1", 1)
    w.svc.place_on_po_allocations(
        host.id, [{"po_line_id": line, "qty": Decimal("1")}], actor_user_id=None
    )
    _assert_done_by_system(_reload(w.db, host))
    _assert_done_by_system(_reload(w.db, companion))

    w.svc.unplace(host.id, actor_user_id=None)
    assert _reload(w.db, host).ack_state == ACK_AWAITING
    assert _reload(w.db, companion).ack_state == ACK_AWAITING, "host not done: companion follows"


def test_ac_ac_4_a_rejected_row_is_never_touched_by_the_system(api):
    _client, w = api
    fixture = _raise_one_row(api, qty="10")
    row = fixture["row"]
    svc = ProjectOrderInquiryService(w.db)
    svc.reject_row(str(row.id), reason="Factory closed", actor_user_id=w.buyer)
    w.db.commit()
    assert _reload(w.db, row).ack_state == ACK_REJECTED

    svc.refresh_link_state([row])
    w.db.flush()

    _reload(w.db, row)
    assert row.ack_state == ACK_REJECTED
    assert row.acknowledged_by is None
    assert row.acknowledged_at is None


# =============================================================================================
# Amendment (handshake world)
# =============================================================================================


def _header_state_of(client, core_so_number: str) -> str | None:
    """'outstanding' / 'completed' / None for the one OI header behind this SO number."""
    for state in ("outstanding", "completed"):
        body = client.get(
            HEADERS_URL, params={"state": state, "query": core_so_number, "limit": 100}
        )
        assert body.status_code == 200, body.text
        if body.json()["data"]:
            return state
    return None


HEADERS_URL = f"{BASE}/order-inquiry-headers"


def test_ac_ac_10_an_amend_above_the_links_keeps_changed_and_back_to_covered_is_done(api):
    client, w = api
    fixture = _raise_one_row(api, qty="10")
    row = fixture["row"]
    _po, line = _open_po_line(w, qty=50)
    ProjectOrderInquiryService(w.db).place_on_po_allocations(
        str(row.id), [{"po_line_id": str(line.id), "qty": "10"}], actor_user_id=None
    )
    w.db.commit()
    _assert_done_by_system(_reload(w.db, row))
    so_number = fixture["core_so"].so_number

    _settle(w, fixture, qty="14")
    _reload(w.db, row)
    assert row.ack_state == ACK_CHANGED, "10 linked of 14: not done, keeps the changed flag"
    assert _header_state_of(client, so_number) == "outstanding"

    _settle(w, fixture, qty="10")
    _assert_done_by_system(_reload(w.db, row))
    assert _header_state_of(client, so_number) == "completed"


# =============================================================================================
# Reserve (reserve harness)
# =============================================================================================


def _reserve_whole_row(reserve_api, qty: str):
    client, w = reserve_api
    _register()
    row = _open_row(w, qty=qty, ack_state=ACK_AWAITING)
    request_id = _request(client, w, (row, qty))
    response = client.post(
        COMMIT_URL(w.inquiry.id),
        json={"reserves": [{"row_id": row.id, "warehouse_id": w.site.id, "qty_reserved": qty}]},
    )
    assert response.status_code == 200, response.text
    w.db.commit()
    w.db.expire_all()
    return w, row, request_id


def test_ac_ac_3_a_full_reserve_link_marks_the_row_done(reserve_api):
    w, row, _request_id = _reserve_whole_row(reserve_api, "50")

    _assert_done_by_system(_reload(w.db, row))


def test_ac_ac_10b_the_links_reader_returns_a_reserve_link_as_a_reserve_entry(reserve_api):
    w, row, _request_id = _reserve_whole_row(reserve_api, "50")

    links = ProjectOrderInquiryService(w.db).links_for_rows([row.id]).get(row.id, [])

    reserves = [entry for entry in links if entry.get("kind") == "reserve"]
    assert len(reserves) == 1, f"a reserve link is an entry of kind 'reserve': {links}"
    assert reserves[0]["document"] == f"Reserved @ {w.site.warehouse_code}"
    assert Decimal(str(reserves[0]["qty"])) == Decimal("50")


# =============================================================================================
# OI header (header harness)
# =============================================================================================


def _po_line_for(db, company_id: str, product_code: str, qty: int) -> str:
    product = db.query(Product).filter(Product.product_code == product_code).one()
    supplier = Supplier(
        id=_uid(), company_id=company_id, supplier_code=f"ZZT-{_uid()[:8]}",
        supplier_name="ZZT AC supplier",
    )
    warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}".upper())
    db.add(supplier)
    db.flush()
    po = PurchaseOrder(
        id=_uid(), company_id=company_id, po_number=f"ZZT-PO-{_uid()[:8]}",
        supplier_id=supplier.id, issue_date=date(2026, 6, 1), status="active",
    )
    db.add(po)
    db.flush()
    line = PurchaseOrderLine(
        id=_uid(), company_id=company_id, purchase_order_id=po.id, product_id=product.id,
        warehouse_id=warehouse.id, qty_ordered=Decimal(qty), qty_received=Decimal("0"),
        expected_date=date(2026, 12, 1), line_status="open",
    )
    db.add(line)
    db.commit()
    return line.id


def _link(db, company_id: str, row, qty: int) -> None:
    line_id = _po_line_for(db, company_id, row.item_code, qty)
    ProjectOrderInquiryService(db).place_on_po_allocations(
        str(row.id), [{"po_line_id": line_id, "qty": Decimal(qty)}], actor_user_id=None
    )
    db.commit()


def _header_row(client, inquiry_id: str, state: str) -> dict | None:
    response = client.get(HEADERS, params={"state": state, "limit": 100})
    assert response.status_code == 200, response.text
    for item in response.json()["data"]:
        if item["id"] == inquiry_id:
            return item
    return None


def test_ac_ac_9_14_losing_the_link_reopens_the_oi_and_relinking_completes_it(header_api):
    client, db, company_id = header_api
    built = _header(db, company_id, rows=[{"qty": "10"}])
    row, inquiry_id = built["rows"][0], built["inquiry"].id
    _link(db, company_id, row, 10)
    assert _header_row(client, inquiry_id, "completed") is not None, "fully linked: Completed"

    ProjectOrderInquiryService(db).unplace(str(row.id), actor_user_id=_new_user(db))
    db.commit()
    reopened = _header_row(client, inquiry_id, "outstanding")
    assert reopened is not None, "a row lost its link: the OI reopens with nobody pressing"
    assert _header_row(client, inquiry_id, "completed") is None

    _link(db, company_id, row, 10)
    assert _header_row(client, inquiry_id, "completed") is not None, "relinked: Completed again"


def test_ac_ac_11_13_done_and_rejected_is_completed(header_api):
    client, db, company_id = header_api
    built = _header(
        db, company_id,
        rows=[{"qty": "10"}, {"qty": "4", "ack_state": ACK_REJECTED}],
    )
    done, _rejected = built["rows"]
    _link(db, company_id, done, 10)

    assert _header_row(client, built["inquiry"].id, "completed") is not None
    assert _header_row(client, built["inquiry"].id, "outstanding") is None


def test_ac_ac_11_13_done_and_partial_is_outstanding_with_one_line_to_order(header_api):
    client, db, company_id = header_api
    built = _header(db, company_id, rows=[{"qty": "10"}, {"qty": "10"}])
    done, partial = built["rows"]
    _link(db, company_id, done, 10)
    _link(db, company_id, partial, 6)

    item = _header_row(client, built["inquiry"].id, "outstanding")
    assert item is not None
    assert item["lines_to_confirm"] == 1
    assert item["lines_total"] == 2
    assert _header_row(client, built["inquiry"].id, "completed") is None


# =============================================================================================
# Routes
# =============================================================================================


@pytest.mark.parametrize("verb", ["acknowledge", "unacknowledge"])
def test_ac_ac_17_the_press_routes_are_gone(api, verb):
    _client, w = api
    row = _raise_one_row(api, qty="10")["row"]  # a REAL row: a missing row would 404 too
    with _as_purchasing(w) as buyer:  # holds the acknowledge grant: only a missing route says 404
        response = buyer.post(f"{BASE}/order-inquiries/{verb}", json={"row_ids": [str(row.id)]})
    assert response.status_code in (404, 405), response.text


def test_ac_ac_20_link_now_links_an_awaiting_row_and_the_worklist_lists_the_suggestion(api):
    client, w = api
    fixture = _raise_one_row(api, qty="10")
    row = fixture["row"]
    assert _reload(w.db, row).ack_state == ACK_AWAITING
    _open_po_line(w, qty=100)

    with _as_purchasing(w) as buyer:
        response = buyer.post(LINK_NOW, json={"product_ids": [str(w.product.id)]})
        assert response.status_code == 200, response.text
        w.db.commit()
        assert response.json()["placed_rows"] >= 1, "the awaiting row is in scope of Link now"

        listing = buyer.get(HS_LIST, params={"limit": 200})
    assert listing.status_code == 200, listing.text
    item = next(i for i in listing.json()["data"] if i["id"] == str(row.id))
    assert item.get("suggested_links"), "the worklist row carries the suggested link"


# =============================================================================================
# Board confirm (AC-AC-21)
# =============================================================================================


def test_ac_ac_21_the_board_confirm_still_hands_over_to_purchasing(api, monkeypatch):
    from .test_order_inquiry_handover_automation import (
        _captured_dispatches,
        _handover_calls,
        _register as _register_handover,
    )

    _client, w = api
    _register_handover(w)
    calls = _captured_dispatches(monkeypatch)

    fixture = _raise_one_row(api, qty="10")

    handover = _handover_calls(calls)
    assert handover, "the board confirm still sends the purchasing handover"
    lines = handover[-1]["context"]["handover"]["lines"]
    assert [line["remark"] for line in lines] == ["ORDER"]
    assert fixture["row"].ack_state == ACK_AWAITING, "nothing covers it yet: To order"


def _p() -> str:
    from . import test_order_inquiry_bundles as bundles

    return bundles.P
