"""The order inquiry handshake: CS raises, purchasing acknowledges (`PLAN-scm-oi-handshake.md`).

Links are purchasing's word. Nothing is linked when a row is raised; the cascade runs at
ACKNOWLEDGE, at Link now, and at a purchase-order confirm, and every one of those three is
restricted to rows purchasing has taken on. What is pinned here, one test each:

* AC-H1/AC-H11 a board confirm raises `awaiting` rows and links NOTHING, even with an open
  purchase-order line sitting there waiting for the product;
* AC-H2 Acknowledge takes a batch on, stamps who and when, and runs the cascade for exactly
  those rows;
* AC-H3 a CS user (no `project_sales.order_inquiries.acknowledge`) is refused 403 by every
  one of the three write routes;
* AC-H4 the `ack` filter is a closed set, and the facet counts all four states with its own
  filter dropped;
* AC-H5 a reject needs a reason, and 422 says so;
* AC-H6 a rejected row leaves `scm.committed_v` and the plan's own committed SELECT, and the
  line goes back to the board undecided carrying the reason;
* AC-H7/AC-H8/AC-H9 an amend before acknowledgement is silent, one after it reads `changed`
  with the previous value and its links kept, and re-acknowledging returns it;
* AC-H10 the plan counts acknowledged and changed rows only, and awaiting rows are a count;
* AC-H13 Link now is scoped to the products named;
* AC-H14 every new column is on the wire from the list, the summary and the export.

Runs on the REAL database (rolled back), like `test_planning_change_apply_on_board`:
`scm.committed_v` is a view a migration installs and the blank scratch schema has none.
Every row is seeded here behind the marker - CI's database has no data.
"""
from __future__ import annotations

import io
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import engine
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    ACK_AWAITING,
    ACK_CHANGED,
    ACK_REJECTED,
    INQUIRY_CANCELLED,
    IV_ORDER,
    OrderInquiryRow,
)
from app.services import project_seed_service
from app.services.project_order_inquiry_service import ProjectOrderInquiryService
from app.services.project_supply_service import ProjectSupplyService

from .test_planning_changes import (
    BASE,
    MARKER,
    _core_line,
    _core_so,
    _line_payload,
    _product,
    _project_line,
    _project_so,
    _sorento,
    _uid,
    _user,
    _warehouse,
)

VIEW = "projects.projects.view"
ACTION = "projects.order_inquiry.action"
EDIT = "projects.projects.edit"
ACKNOWLEDGE = "project_sales.order_inquiries.acknowledge"
PURCHASING = [VIEW, ACTION, ACKNOWLEDGE]
CS = [VIEW, EDIT, ACTION]

LIST = f"{BASE}/order-inquiries"
ACK_URL = f"{LIST}/acknowledge"
LINK_NOW = f"{LIST}/link-now"

WAS = date(2026, 8, 25)
NOW = date(2026, 8, 19)


# ---------------------------------------------------------------------------
# harness
# ---------------------------------------------------------------------------


@contextmanager
def _real_db_session():
    """The real database, every write discarded, and a route's own `rollback()` survived.

    Same reasoning as `test_planning_change_apply_on_board._real_db_session`: the view lives
    in the migrated schema, and `autoflush=False` is how the application's session is built,
    so a service that queries for its own pending write fails here as it would live.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection, join_transaction_mode="create_savepoint", autoflush=False
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def _client(db, user_id: str, permissions):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    actor = {"id": user_id, "email": f"{user_id}@zzt.test", "role": "user"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = lambda: None

    originals = (
        UserPermissionService.check_user_has_permission,
        UserPermissionService.get_user_permission_slugs,
    )
    granted = list(permissions)
    UserPermissionService.check_user_has_permission = (
        lambda self, uid, slug: slug in granted
    )
    UserPermissionService.get_user_permission_slugs = lambda self, uid: list(granted)
    return TestClient(app), originals


def _restore(originals) -> None:
    from app.main import app
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = originals[0]
    UserPermissionService.get_user_permission_slugs = originals[1]
    app.dependency_overrides.clear()


class _World:
    def __init__(self, db, company_id, cs_user, buyer, project, product, warehouse):
        self.db = db
        self.company_id = company_id
        self.cs_user = cs_user
        self.buyer = buyer
        self.project = project
        self.product = product
        self.warehouse = warehouse


@pytest.fixture()
def world():
    from app.services.project_service import register_project

    with _real_db_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        cs_user = _user(db, f"{MARKER} Eling")
        buyer = _user(db, f"{MARKER} Joey")
        project = register_project(
            db,
            company_id=company_id,
            actor_user_id=cs_user,
            developer_party_id=None,
            title=f"{MARKER} Yotu Builder {_uid()[:8]}",
        )
        product = _product(db)
        warehouse = _warehouse(db, f"ZZT-IB-{_uid()[:4]}", segment="project")
        db.flush()
        db.commit()
        yield _World(db, company_id, cs_user, buyer, project, product, warehouse)


@pytest.fixture()
def api(world):
    """Two clients on one session: CS confirms on the board, purchasing acknowledges."""
    from app.models.base import company_scope

    cs_client, cs_originals = _client(world.db, world.cs_user, CS)
    try:
        with company_scope(world.db, frozenset({world.company_id})):
            yield cs_client, world
    finally:
        _restore(cs_originals)


@contextmanager
def _as_purchasing(world, permissions=PURCHASING):
    client, originals = _client(world.db, world.buyer, permissions)
    try:
        yield client
    finally:
        _restore(originals)
        # The CS client the `api` fixture installed is put back, so a test can go on
        # confirming on the board after purchasing has acted.
        _client(world.db, world.cs_user, CS)


# ---------------------------------------------------------------------------
# seeding
# ---------------------------------------------------------------------------


def _supplier(world) -> Supplier:
    supplier = Supplier(
        id=_uid(),
        company_id=world.company_id,
        supplier_code=f"ZZT-{_uid()[:8]}",
        supplier_name=f"{MARKER} DAFUYUAN",
    )
    world.db.add(supplier)
    world.db.flush()
    return supplier


def _open_po_line(world, *, qty, expected_date=date(2026, 8, 10), product=None):
    supplier = _supplier(world)
    po = PurchaseOrder(
        id=_uid(),
        company_id=world.company_id,
        po_number=f"ZZT-PO-{_uid()[:8]}",
        supplier_id=supplier.id,
        issue_date=date(2026, 6, 1),
        status="active",
    )
    world.db.add(po)
    world.db.flush()
    line = PurchaseOrderLine(
        id=_uid(),
        company_id=world.company_id,
        purchase_order_id=po.id,
        product_id=(product or world.product).id,
        warehouse_id=world.warehouse.id,
        qty_ordered=Decimal(str(qty)),
        qty_received=Decimal("0"),
        expected_date=expected_date,
        line_status="open",
    )
    world.db.add(line)
    world.db.flush()
    world.db.commit()
    return po, line


def _confirm(client, order_id, lines):
    return client.post(f"{BASE}/sales-orders/{order_id}/confirm", json={"lines": lines})


def _raise_one_row(api, *, qty="10", product=None):
    """One published order, one line, confirmed wholly as Buy: one raised inquiry row."""
    client, world = api
    db = world.db
    product = product or world.product
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(
        db, core_so, product, world.warehouse, qty_ordered=qty, required_date=WAS
    )
    order = _project_so(
        db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number
    )
    line = _project_line(db, order, line_no=1, product=product, core_line=core_line)
    db.commit()

    response = _confirm(client, order.id, [_line_payload(line.id, buy_qty=qty)])
    assert response.status_code == 200, response.text
    db.commit()
    return {
        "order": order,
        "line": line,
        "core_so": core_so,
        "core_line": core_line,
        "row": _order_row(world, line),
    }


def _order_row(world, line) -> OrderInquiryRow:
    return (
        world.db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.so_line_id == line.id,
            OrderInquiryRow.verb == IV_ORDER,
            OrderInquiryRow.state != INQUIRY_CANCELLED,
        )
        .one()
    )


def _links_of(world, row) -> list:
    return ProjectOrderInquiryService(world.db)._links_of(str(row.id))


def _project_committed(world, *, planned: bool) -> Decimal:
    """What is committed for the product at its warehouse - as the VIEW says it, or as the
    PLAN's own SELECT does (`demand.horizon_committed_select_sql`, acknowledged only)."""
    from app.services.scm import demand

    if planned:
        sql = (
            f"SELECT COALESCE(SUM(project_committed), 0) FROM ("
            f"{demand.horizon_committed_select_sql()}) cv "
            "WHERE cv.product_id = :pid"
        )
        params = {"pid": str(world.product.id), "horizon": None}
    else:
        sql = (
            "SELECT COALESCE(SUM(project_committed), 0) FROM scm.committed_v "
            "WHERE product_id = :pid"
        )
        params = {"pid": str(world.product.id)}
    return Decimal(str(world.db.execute(text(sql), params).scalar() or 0))


# ---------------------------------------------------------------------------
# AC-H1 / AC-H11: raising links nothing
# ---------------------------------------------------------------------------


def test_a_board_confirm_raises_awaiting_rows_and_links_nothing(api):
    """The cascade left `supply.confirm` (plan section 3). An open purchase-order line for
    the very product is sitting there, and the row still comes out unlinked: linking is
    purchasing's word, and nobody has said it yet."""
    _client, world = api
    _open_po_line(world, qty=50)

    fixture = _raise_one_row(api)
    row = fixture["row"]

    assert row.ack_state == ACK_AWAITING
    assert row.acknowledged_by is None and row.acknowledged_at is None
    assert _links_of(world, row) == [], "nothing links until somebody acknowledges"


# ---------------------------------------------------------------------------
# AC-H2: acknowledge, one and many
# ---------------------------------------------------------------------------


def test_acknowledge_stamps_who_and_when_and_runs_the_cascade_for_those_rows(api):
    _client, world = api
    _open_po_line(world, qty=50)
    fixture = _raise_one_row(api)
    row = fixture["row"]

    with _as_purchasing(world) as buyer:
        response = buyer.post(ACK_URL, json={"row_ids": [str(row.id)]})
    assert response.status_code == 200, response.text
    world.db.commit()

    body = response.json()
    assert body["acknowledged"] == 1
    assert body["linked_rows"] == 1 and body["links"] >= 1

    world.db.refresh(row)
    assert row.ack_state == ACK_ACKNOWLEDGED
    assert str(row.acknowledged_by) == str(world.buyer)
    assert row.acknowledged_at is not None
    assert sum(Decimal(str(link.qty)) for link in _links_of(world, row)) == Decimal("10")


def test_acknowledge_takes_a_batch_on_in_one_press(api):
    _client, world = api
    first = _raise_one_row(api, qty="4")
    second = _raise_one_row(api, qty="6")

    with _as_purchasing(world) as buyer:
        response = buyer.post(
            ACK_URL,
            json={"row_ids": [str(first["row"].id), str(second["row"].id)]},
        )
    assert response.status_code == 200, response.text
    world.db.commit()
    assert response.json()["acknowledged"] == 2
    for fixture in (first, second):
        world.db.refresh(fixture["row"])
        assert fixture["row"].ack_state == ACK_ACKNOWLEDGED


def test_acknowledging_a_rejected_row_is_refused(api):
    """`awaiting` and `changed` are the two an acknowledgement may be taken on. A rejected
    row is purchasing's own refusal: taking it on again means CS re-deciding the line."""
    _client, world = api
    fixture = _raise_one_row(api)
    row = fixture["row"]

    with _as_purchasing(world) as buyer:
        reject = buyer.post(
            f"{LIST}/{row.id}/reject", json={"reason": "No supplier until November"}
        )
        assert reject.status_code == 200, reject.text
        world.db.commit()
        response = buyer.post(ACK_URL, json={"row_ids": [str(row.id)]})

    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# AC-H3: CS cannot acknowledge, reject or link
# ---------------------------------------------------------------------------


def test_a_cs_user_is_refused_by_every_write_route(api):
    """CS sees the column and the filter; the three actions are purchasing's grant."""
    cs_client, world = api
    fixture = _raise_one_row(api)
    row_id = str(fixture["row"].id)

    assert cs_client.post(ACK_URL, json={"row_ids": [row_id]}).status_code == 403
    assert (
        cs_client.post(f"{LIST}/{row_id}/reject", json={"reason": "no"}).status_code
        == 403
    )
    assert cs_client.post(LINK_NOW, json={}).status_code == 403
    # ... and the read they DO hold is unaffected.
    assert cs_client.get(LIST).status_code == 200


# ---------------------------------------------------------------------------
# AC-H4: the filter and the facet
# ---------------------------------------------------------------------------


def test_the_ack_filter_narrows_the_list_and_the_facet_counts_all_four_states(api):
    client, world = api
    awaiting = _raise_one_row(api, qty="4")
    acknowledged = _raise_one_row(api, qty="6")

    with _as_purchasing(world) as buyer:
        assert (
            buyer.post(
                ACK_URL, json={"row_ids": [str(acknowledged["row"].id)]}
            ).status_code
            == 200
        )
    world.db.commit()

    listed = client.get(LIST, params={"ack": "awaiting", "limit": 200}).json()
    ids = {row["id"] for row in listed["data"]}
    assert str(awaiting["row"].id) in ids
    assert str(acknowledged["row"].id) not in ids

    summary = client.get(
        f"{LIST}/summary", params={"ack": "awaiting"}
    ).json()
    # The facet drops its OWN filter, like every other control on this screen, so the
    # acknowledged row is still counted while the awaiting one is the only one listed.
    assert set(summary["ack"]) == {"awaiting", "acknowledged", "changed", "rejected"}
    assert summary["ack"]["acknowledged"] >= 1
    assert summary["ack"]["awaiting"] >= 1


def test_an_unknown_ack_value_is_refused(api):
    client, _world = api
    response = client.get(LIST, params={"ack": "maybe"})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# AC-H5 / AC-H6: reject
# ---------------------------------------------------------------------------


def test_a_reject_with_no_reason_is_refused(api):
    _client, world = api
    fixture = _raise_one_row(api)

    with _as_purchasing(world) as buyer:
        blank = buyer.post(f"{LIST}/{fixture['row'].id}/reject", json={"reason": "   "})
        missing = buyer.post(f"{LIST}/{fixture['row'].id}/reject", json={})

    assert blank.status_code == 422, blank.text
    assert missing.status_code == 422, missing.text
    world.db.refresh(fixture["row"])
    assert fixture["row"].ack_state == ACK_AWAITING


def test_a_rejected_row_records_who_when_and_why(api):
    _client, world = api
    fixture = _raise_one_row(api)
    row = fixture["row"]

    with _as_purchasing(world) as buyer:
        response = buyer.post(
            f"{LIST}/{row.id}/reject", json={"reason": "Factory closed until November"}
        )
    assert response.status_code == 200, response.text
    world.db.commit()

    body = response.json()
    assert body["ack_state"] == ACK_REJECTED
    assert body["rejected_reason"] == "Factory closed until November"
    assert body["rejected_by_name"] and f"{MARKER} Joey" in body["rejected_by_name"]
    world.db.refresh(row)
    assert str(row.rejected_by) == str(world.buyer) and row.rejected_at is not None


def test_a_rejected_row_leaves_committed_v_and_the_plans_own_demand(api):
    _client, world = api
    fixture = _raise_one_row(api)
    row = fixture["row"]

    before = _project_committed(world, planned=False)
    assert before >= Decimal("10"), "the raised row is owed, so the view counts it"

    with _as_purchasing(world) as buyer:
        assert (
            buyer.post(
                f"{LIST}/{row.id}/reject", json={"reason": "Nothing to buy this with"}
            ).status_code
            == 200
        )
    world.db.commit()

    assert _project_committed(world, planned=False) == before - Decimal("10")
    assert _project_committed(world, planned=True) == Decimal("0")


def test_a_rejected_rows_line_goes_back_to_the_board_undecided_with_the_reason(api):
    """AC-H6. The decision is uncovered through `confirm`'s own `uncover_line_ids` seam, so
    the line is planned again from scratch; the cell carries the refusal."""
    _client, world = api
    fixture = _raise_one_row(api)
    line = fixture["line"]
    order = fixture["order"]

    supply = ProjectSupplyService(world.db)
    assert supply.active_decision(str(order.id)) is not None

    with _as_purchasing(world) as buyer:
        assert (
            buyer.post(
                f"{LIST}/{fixture['row'].id}/reject",
                json={"reason": "Factory closed until November"},
            ).status_code
            == 200
        )
    world.db.commit()

    decision = supply.active_decision(str(order.id))
    covered = {
        str(snap.get("project_line_id"))
        for snap in ((decision.line_snapshots if decision else None) or [])
    }
    assert str(line.id) not in covered, "the line is undecided again"

    from app.services.project_fulfilment_board_service import FulfilmentBoardService

    cell = FulfilmentBoardService(world.db)._order_inquiries(
        [str(fixture["core_line"].id)]
    )[str(fixture["core_line"].id)]
    assert cell["ack_state"] == ACK_REJECTED
    assert cell["rejected_reason"] == "Factory closed until November"
    assert f"{MARKER} Joey" in (cell["rejected_by_name"] or "")


# ---------------------------------------------------------------------------
# AC-H7 / AC-H8 / AC-H9: change after acknowledgement
# ---------------------------------------------------------------------------


def _settle(world, fixture, *, qty, required_date=NOW):
    """What a planning change does to the line: settle its row in place (part 3)."""
    supply = ProjectSupplyService(world.db)
    from app.schemas.project_supply import ConfirmSupplyBody, ConfirmLine

    body = ConfirmSupplyBody(
        lines=[
            ConfirmLine(
                project_line_id=str(fixture["line"].id),
                timely_spo_qty="0",
                reserve=[],
                borrow=[],
                buy_qty=str(qty),
            )
        ]
    )
    fixture["core_line"].qty_ordered = Decimal(str(qty))
    fixture["core_line"].required_date = required_date
    fixture["line"].qty = Decimal(str(qty))
    fixture["line"].delivery_date = required_date
    world.db.flush()
    result = supply.confirm(
        fixture["order"],
        body,
        actor_user_id=world.cs_user,
        settle_in_place_line_ids=[str(fixture["line"].id)],
    )
    world.db.commit()
    return result


def test_an_amend_before_acknowledgement_leaves_the_row_awaiting(api):
    """AC-H7. CS is free to change what nobody has read; the row says nothing about it."""
    _client, world = api
    fixture = _raise_one_row(api)
    row = fixture["row"]

    _settle(world, fixture, qty="25")

    world.db.refresh(row)
    assert row.ack_state == ACK_AWAITING
    assert row.changed_at is None
    assert Decimal(str(row.qty)) == Decimal("25")


def test_an_amend_after_acknowledgement_reads_changed_and_keeps_its_links(api):
    """AC-H8. The row is updated in place with the previous value, and purchasing sees it
    as a change rather than as something it has already dealt with."""
    _client, world = api
    _open_po_line(world, qty=50)
    fixture = _raise_one_row(api)
    row = fixture["row"]

    with _as_purchasing(world) as buyer:
        assert buyer.post(ACK_URL, json={"row_ids": [str(row.id)]}).status_code == 200
    world.db.commit()
    assert _links_of(world, row), "acknowledging linked it"

    _settle(world, fixture, qty="25")

    world.db.refresh(row)
    assert row.ack_state == ACK_CHANGED
    assert row.changed_at is not None
    assert Decimal(str(row.qty)) == Decimal("25")
    assert _links_of(world, row), "a change keeps what the buyer already arranged"
    assert "Was 10" in (row.note or ""), "the previous value travels with the row"


def test_re_acknowledging_a_changed_row_returns_it_and_links_the_remainder(api):
    _client, world = api
    _open_po_line(world, qty=30)
    fixture = _raise_one_row(api)
    row = fixture["row"]

    with _as_purchasing(world) as buyer:
        assert buyer.post(ACK_URL, json={"row_ids": [str(row.id)]}).status_code == 200
        world.db.commit()
        _settle(world, fixture, qty="25")
        # A second purchase order arrives for what the change added.
        _open_po_line(world, qty=40)
        response = buyer.post(ACK_URL, json={"row_ids": [str(row.id)]})
    assert response.status_code == 200, response.text
    world.db.commit()

    world.db.refresh(row)
    assert row.ack_state == ACK_ACKNOWLEDGED
    assert sum(Decimal(str(link.qty)) for link in _links_of(world, row)) == Decimal("25")


def test_a_supersede_of_an_acknowledged_row_raises_its_replacement_changed(api):
    """AC-H9. A reconfirm that cannot settle in place still owes purchasing the fact that
    this line is one they had already taken on."""
    _client, world = api
    fixture = _raise_one_row(api)
    row = fixture["row"]

    with _as_purchasing(world) as buyer:
        assert buyer.post(ACK_URL, json={"row_ids": [str(row.id)]}).status_code == 200
    world.db.commit()

    # A plain reconfirm of the same line: no settle-in-place seam, so the row is
    # superseded and a fresh one is raised in its place.
    response = _confirm(
        _client, fixture["order"].id, [_line_payload(fixture["line"].id, buy_qty="10")]
    )
    assert response.status_code == 200, response.text
    world.db.commit()

    world.db.refresh(row)
    assert row.state == INQUIRY_CANCELLED, "the old row was superseded"
    replacement = _order_row(world, fixture["line"])
    assert str(replacement.id) != str(row.id)
    assert replacement.ack_state == ACK_CHANGED


# ---------------------------------------------------------------------------
# AC-H10: what the plan counts
# ---------------------------------------------------------------------------


def test_the_plan_counts_acknowledged_and_changed_rows_only(api):
    _client, world = api
    fixture = _raise_one_row(api)
    row = fixture["row"]

    assert _project_committed(world, planned=True) == Decimal("0"), (
        "an awaiting row is not something to buy against"
    )
    assert _project_committed(world, planned=False) >= Decimal("10")

    with _as_purchasing(world) as buyer:
        assert buyer.post(ACK_URL, json={"row_ids": [str(row.id)]}).status_code == 200
    world.db.commit()

    assert _project_committed(world, planned=True) == Decimal("10")


def test_the_awaiting_count_is_reported_for_the_plan_page_chip(api):
    from app.services.scm.reorder_run_service import awaiting_acknowledgement_rows

    _client, world = api
    before = awaiting_acknowledgement_rows(world.db)
    fixture = _raise_one_row(api)
    assert awaiting_acknowledgement_rows(world.db) == before + 1

    with _as_purchasing(world) as buyer:
        assert (
            buyer.post(ACK_URL, json={"row_ids": [str(fixture["row"].id)]}).status_code
            == 200
        )
    world.db.commit()
    assert awaiting_acknowledgement_rows(world.db) == before


# ---------------------------------------------------------------------------
# AC-H13: link now
# ---------------------------------------------------------------------------


def test_link_now_links_acknowledged_rows_and_leaves_awaiting_ones_alone(api):
    _client, world = api
    acknowledged = _raise_one_row(api, qty="10")
    awaiting = _raise_one_row(api, qty="10")

    with _as_purchasing(world) as buyer:
        assert (
            buyer.post(
                ACK_URL, json={"row_ids": [str(acknowledged["row"].id)]}
            ).status_code
            == 200
        )
        world.db.commit()
        # Only now does the purchase order arrive, so the acknowledge itself linked
        # nothing and Link now is what has work to do.
        _open_po_line(world, qty=100)
        response = buyer.post(LINK_NOW, json={"product_ids": [str(world.product.id)]})
    assert response.status_code == 200, response.text
    world.db.commit()

    assert response.json()["placed_rows"] == 1
    assert _links_of(world, acknowledged["row"])
    assert _links_of(world, awaiting["row"]) == []


def test_link_now_is_scoped_to_the_products_it_is_given(api):
    _client, world = api
    other_product = _product(world.db)
    world.db.commit()
    mine = _raise_one_row(api, qty="10")
    theirs = _raise_one_row(api, qty="10", product=other_product)
    _open_po_line(world, qty=100)
    _open_po_line(world, qty=100, product=other_product)

    with _as_purchasing(world) as buyer:
        assert (
            buyer.post(
                ACK_URL,
                json={"row_ids": [str(mine["row"].id), str(theirs["row"].id)]},
            ).status_code
            == 200
        )
        world.db.commit()
        for row in (mine["row"], theirs["row"]):
            ProjectOrderInquiryService(world.db).unplace(
                str(row.id), actor_user_id=world.buyer
            )
        world.db.commit()
        response = buyer.post(LINK_NOW, json={"product_ids": [str(world.product.id)]})
    assert response.status_code == 200, response.text
    world.db.commit()

    assert _links_of(world, mine["row"])
    assert _links_of(world, theirs["row"]) == []


# ---------------------------------------------------------------------------
# AC-H14: on the wire
# ---------------------------------------------------------------------------


def test_every_new_field_reaches_the_list_the_row_and_the_export(api):
    client, world = api
    fixture = _raise_one_row(api)
    row = fixture["row"]

    with _as_purchasing(world) as buyer:
        assert (
            buyer.post(
                f"{LIST}/{row.id}/reject", json={"reason": "Factory closed"}
            ).status_code
            == 200
        )
    world.db.commit()

    listed = client.get(LIST, params={"ack": "rejected", "limit": 200}).json()
    on_wire = next(item for item in listed["data"] if item["id"] == str(row.id))
    for field in (
        "ack_state",
        "acknowledged_by_name",
        "acknowledged_at",
        "rejected_by_name",
        "rejected_at",
        "rejected_reason",
        "changed_at",
    ):
        assert field in on_wire, f"`response_model` dropped {field}"
    assert on_wire["ack_state"] == ACK_REJECTED
    assert on_wire["rejected_reason"] == "Factory closed"

    export = client.get(f"{LIST}/export", params={"ack": "rejected"})
    assert export.status_code == 200
    import openpyxl

    book = openpyxl.load_workbook(io.BytesIO(export.content))
    sheet = book[book.sheetnames[0]]
    headings = [cell.value for cell in sheet[2]]
    assert "ACKNOWLEDGED" in headings
    printed = [
        row_values[headings.index("ACKNOWLEDGED")]
        for row_values in sheet.iter_rows(min_row=3, values_only=True)
    ]
    assert any("Factory closed" in (value or "") for value in printed)


def test_the_sales_order_detail_carries_the_handshake(api):
    """The per-project / SO-detail serializer is a second reader of the same row, and it
    drops a field just as silently."""
    client, world = api
    fixture = _raise_one_row(api)

    body = client.get(f"{BASE}/sales-orders/{fixture['order'].id}/order-inquiry").json()
    row = next(item for item in body["rows"] if item["id"] == str(fixture["row"].id))
    assert row["ack_state"] == ACK_AWAITING
    assert "rejected_reason" in row and "changed_at" in row
