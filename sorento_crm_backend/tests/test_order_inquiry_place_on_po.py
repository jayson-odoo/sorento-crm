"""Section G - "Place on PO" (PLAN-demo-followups-19aug-ladder-v2.md section G, migration
400_oi_place_on_po).

The captain, 20 Aug: "identify which outstanding PO has quantity to fulfil this order
inquiry, tag it, and the quantity to be ordered is deducted." A raised ORDER /
RESERVE_AND_ORDER row offers candidates from the product's open purchase-order lines,
netted by what other PLACED rows already tagged, soonest `expected_date` first with the
earliest covering line recommended. Placing sets `po_ref` / `po_line_id` / `state=placed`,
appends the note and writes a resolved `OrderLinkClaim`; Unplace reverses all of it. A
placed row leaves `scm.committed_v`'s confirmed leg - the deduction the captain asked for.

Most of this file runs on `blank_session` (Postgres, scratch schema) - candidates, place,
unplace and the worklist columns need only the tables involved, seeded fresh per test. The
NETTING PROOF against `scm.committed_v` cannot: that view is installed by a migration and
does not exist in the scratch schema, so it runs on `pg_session` (the real local database,
rolled back at teardown), reusing `test_so_supply_confirmation`'s seed helpers - the same
substrate `test_partial_decision_demand_invariants.py` uses for the identical reason.

Every test seeds its own chain with a `zzt-oi-place` marker rather than borrowing an
existing row (CI's database is empty).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.inventory import Warehouse
from app.models.project_so import (
    INQUIRY_ACTIONED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_ALREADY_INBOUND,
    IV_ORDER,
    IV_RESERVE_AND_ORDER,
    SO_STATUS_DRAFT,
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
    SOSupplyDecision,
)
from app.models.scm import OrderLinkClaim
from app.models.user import User
from app.services import project_seed_service

from ._pg_fixture import blank_session, pg_session
from .test_so_supply_confirmation import (
    _core_line as _confirm_core_line,
    _core_so as _confirm_core_so,
    _product as _confirm_product,
    _project_line as _confirm_project_line,
    _project_so as _confirm_project_so,
    _sorento as _confirm_sorento,
    _user as _confirm_user,
    _warehouse as _confirm_warehouse,
)

MARKER = "zzt-oi-place"
BASE = "/api/v1/project-sales"

READ_ONLY = ["projects.projects.view"]
PURCHASING = ["projects.projects.view", "projects.order_inquiry.action"]


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _product(db, company_id: str, code: str) -> Product:
    uom = UnitOfMeasure(id=_uid(), company_id=company_id, uom_code=f"ZZT{_uid()[:6]}", uom_name="Unit")
    category = ProductCategory(
        id=_uid(), company_id=company_id, category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} cat"
    )
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(),
        company_id=company_id,
        product_code=code,
        product_name=f"{MARKER} {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
    )
    db.add(row)
    db.flush()
    return row


def _warehouse(db, company_id: str, code: str) -> Warehouse:
    row = Warehouse(
        id=_uid(), company_id=company_id, warehouse_code=code, warehouse_name=code, location="ZZT"
    )
    db.add(row)
    db.flush()
    return row


def _supplier(db, company_id: str, name: str) -> Supplier:
    row = Supplier(
        id=_uid(), company_id=company_id, supplier_code=f"ZZT-{_uid()[:8]}", supplier_name=name
    )
    db.add(row)
    db.flush()
    return row


def _po(db, company_id: str, supplier: Supplier, po_number: str) -> PurchaseOrder:
    row = PurchaseOrder(
        id=_uid(), company_id=company_id, po_number=po_number,
        supplier_id=supplier.id if supplier else None,
    )
    db.add(row)
    db.flush()
    return row


def _po_line(
    db, company_id: str, po: PurchaseOrder, product: Product, warehouse,
    *, qty_ordered, qty_received="0", expected_date=None, line_status="open",
) -> PurchaseOrderLine:
    row = PurchaseOrderLine(
        id=_uid(),
        company_id=company_id,
        purchase_order_id=po.id,
        product_id=product.id,
        warehouse_id=warehouse.id if warehouse else None,
        qty_ordered=Decimal(str(qty_ordered)),
        qty_received=Decimal(str(qty_received)),
        expected_date=expected_date,
        line_status=line_status,
    )
    db.add(row)
    db.flush()
    return row


def _row(
    db, company_id: str, inquiry: OrderInquiry, *,
    verb=IV_ORDER, state=INQUIRY_RAISED, qty="10", item_code=None,
    po_ref=None, po_line_id=None, note=None,
) -> OrderInquiryRow:
    row = OrderInquiryRow(
        id=_uid(),
        company_id=company_id,
        order_inquiry_id=inquiry.id,
        item_code=item_code,
        qty=Decimal(str(qty)),
        verb=verb,
        state=state,
        po_ref=po_ref,
        po_line_id=po_line_id,
        note=note,
    )
    db.add(row)
    db.flush()
    return row


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


def _seed_world(db, company_id: str, user_id: str) -> dict:
    from app.services.project_service import register_project

    project = register_project(
        db, company_id=company_id, actor_user_id=user_id, developer_party_id=None,
        title=f"{MARKER} Residences {_uid()[:6]}",
    )
    order = ProjectSalesOrder(
        id=_uid(),
        company_id=company_id,
        project_id=project.id,
        area_group="TOWER",
        provisional_ref=f"ZZT-PSO-{_uid()[:8]}",
        autocount_doc_no=f"SO{_uid()[:6].upper()}",
        status=SO_STATUS_DRAFT,
        grouping_origin="area",
    )
    db.add(order)
    db.flush()
    inquiry = OrderInquiry(
        id=_uid(), company_id=company_id, project_sales_order_id=order.id, state=INQUIRY_RAISED,
    )
    db.add(inquiry)
    db.flush()
    product = _product(db, company_id, f"ZZT-BASIN-{_uid()[:6]}")
    other_product = _product(db, company_id, f"ZZT-WC-{_uid()[:6]}")
    warehouse = _warehouse(db, company_id, f"ZZT{_uid()[:6]}")
    supplier = _supplier(db, company_id, f"{MARKER} Dafuyuan")
    po = _po(db, company_id, supplier, f"ZZT-PO-{_uid()[:8]}")
    db.commit()
    return {
        "company_id": company_id,
        "project": project,
        "order": order,
        "inquiry": inquiry,
        "product": product,
        "other_product": other_product,
        "warehouse": warehouse,
        "supplier": supplier,
        "po": po,
    }


def _api(permissions):
    from app.models.base import company_scope

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        user_id = _user(db, f"{MARKER} Eling")
        world = _seed_world(db, company_id, user_id)
        client, originals = _client(db, user_id, permissions)
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, db, world, user_id
        finally:
            _restore(originals)


@pytest.fixture()
def api():
    yield from _api(PURCHASING)


@pytest.fixture()
def reader_api():
    yield from _api(READ_ONLY)


# ---------------------------------------------------------------- candidates


def test_candidates_are_soonest_expected_date_first_with_the_earliest_covering_recommended(api):
    client, db, world, _user_id = api
    early_short = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"],
        qty_ordered="10", expected_date=date(2026, 9, 1),
    )
    late_covers = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"],
        qty_ordered="30", expected_date=date(2026, 9, 15),
    )
    row = _row(db, world["company_id"], world["inquiry"], qty="25", item_code=world["product"].product_code)

    response = client.get(f"{BASE}/order-inquiry-rows/{row.id}/po-candidates")

    assert response.status_code == 200, response.text
    body = response.json()
    assert [c["po_line_id"] for c in body] == [early_short.id, late_covers.id]
    assert body[0]["covers"] is False
    assert body[0]["recommended"] is False
    assert body[0]["remaining"] == "10"
    assert body[1]["covers"] is True
    assert body[1]["recommended"] is True
    assert body[1]["remaining"] == "30"


def test_candidates_are_netted_by_what_other_placed_rows_already_tagged(api):
    client, db, world, _user_id = api
    line = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"],
        qty_ordered="50", expected_date=date(2026, 9, 1),
    )
    row_a = _row(db, world["company_id"], world["inquiry"], qty="20", item_code=world["product"].product_code)
    placed = client.post(
        f"{BASE}/order-inquiry-rows/{row_a.id}/place-on-po", json={"po_line_id": line.id}
    )
    assert placed.status_code == 200, placed.text

    row_b = _row(db, world["company_id"], world["inquiry"], qty="25", item_code=world["product"].product_code)
    response = client.get(f"{BASE}/order-inquiry-rows/{row_b.id}/po-candidates")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body[0]["already_tagged"] == "20"
    assert body[0]["remaining"] == "30"
    assert body[0]["covers"] is True


def test_candidates_409_for_a_verb_that_is_not_placeable(api):
    client, db, world, _user_id = api
    row = _row(
        db, world["company_id"], world["inquiry"], verb=IV_ALREADY_INBOUND, qty="10",
        item_code=world["product"].product_code,
    )

    response = client.get(f"{BASE}/order-inquiry-rows/{row.id}/po-candidates")

    assert response.status_code == 409
    assert response.json()["code"] == "order_inquiry_not_placeable_verb"


def test_candidates_409_for_a_row_that_is_not_raised(api):
    client, db, world, _user_id = api
    row = _row(
        db, world["company_id"], world["inquiry"], verb=IV_ORDER, state=INQUIRY_ACTIONED,
        qty="10", item_code=world["product"].product_code,
    )

    response = client.get(f"{BASE}/order-inquiry-rows/{row.id}/po-candidates")

    assert response.status_code == 409
    assert response.json()["code"] == "order_inquiry_not_raised"


def test_a_reader_cannot_reach_candidates(reader_api):
    client, db, world, _user_id = reader_api
    row = _row(db, world["company_id"], world["inquiry"], qty="10", item_code=world["product"].product_code)

    response = client.get(f"{BASE}/order-inquiry-rows/{row.id}/po-candidates")

    assert response.status_code == 403


# ---------------------------------------------------------------------- place


def test_placing_sets_the_tag_appends_the_note_and_writes_one_resolved_claim(api):
    client, db, world, user_id = api
    line = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"],
        qty_ordered="50", expected_date=date(2026, 9, 20),
    )
    row = _row(
        db, world["company_id"], world["inquiry"], qty="30",
        item_code=world["product"].product_code, note="Already had a note",
    )

    response = client.post(
        f"{BASE}/order-inquiry-rows/{row.id}/place-on-po", json={"po_line_id": line.id}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == INQUIRY_PLACED
    assert body["po_ref"] == world["po"].po_number
    assert body["po_line_id"] == line.id
    assert body["note"].startswith("Already had a note; Placed on")
    assert world["po"].po_number in body["note"]
    assert world["supplier"].supplier_name in body["note"]
    assert "2026-09-20" in body["note"]

    claims = (
        db.query(OrderLinkClaim)
        .filter(OrderLinkClaim.po_number == world["po"].po_number, OrderLinkClaim.source == "order_inquiry")
        .all()
    )
    assert len(claims) == 1
    assert claims[0].resolved_at is not None
    assert claims[0].po_line_id == line.id


def test_placing_refuses_a_purchase_order_line_of_a_different_product(api):
    client, db, world, _user_id = api
    line = _po_line(
        db, world["company_id"], world["po"], world["other_product"], world["warehouse"],
        qty_ordered="50",
    )
    row = _row(db, world["company_id"], world["inquiry"], qty="10", item_code=world["product"].product_code)

    response = client.post(
        f"{BASE}/order-inquiry-rows/{row.id}/place-on-po", json={"po_line_id": line.id}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "order_inquiry_product_mismatch"


def test_placing_names_the_shortfall_when_the_line_cannot_cover_the_row(api):
    client, db, world, _user_id = api
    line = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"], qty_ordered="10",
    )
    row = _row(db, world["company_id"], world["inquiry"], qty="30", item_code=world["product"].product_code)

    response = client.post(
        f"{BASE}/order-inquiry-rows/{row.id}/place-on-po", json={"po_line_id": line.id}
    )

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "order_inquiry_po_line_short"
    assert "10" in body["message"]
    assert "20" in body["message"]
    assert "30" in body["message"]


def test_two_rows_tagging_the_same_line_cannot_exceed_its_balance(api):
    client, db, world, _user_id = api
    line = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"], qty_ordered="50",
    )
    row_a = _row(db, world["company_id"], world["inquiry"], qty="30", item_code=world["product"].product_code)
    row_b = _row(db, world["company_id"], world["inquiry"], qty="25", item_code=world["product"].product_code)
    row_c = _row(db, world["company_id"], world["inquiry"], qty="20", item_code=world["product"].product_code)

    first = client.post(
        f"{BASE}/order-inquiry-rows/{row_a.id}/place-on-po", json={"po_line_id": line.id}
    )
    assert first.status_code == 200, first.text

    over = client.post(
        f"{BASE}/order-inquiry-rows/{row_b.id}/place-on-po", json={"po_line_id": line.id}
    )
    assert over.status_code == 409
    assert over.json()["code"] == "order_inquiry_po_line_short"

    exact = client.post(
        f"{BASE}/order-inquiry-rows/{row_c.id}/place-on-po", json={"po_line_id": line.id}
    )
    assert exact.status_code == 200, exact.text
    assert exact.json()["state"] == INQUIRY_PLACED


def test_a_placed_row_cannot_be_placed_again(api):
    client, db, world, _user_id = api
    line = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"], qty_ordered="50",
    )
    other_line = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"], qty_ordered="50",
    )
    row = _row(db, world["company_id"], world["inquiry"], qty="10", item_code=world["product"].product_code)

    first = client.post(
        f"{BASE}/order-inquiry-rows/{row.id}/place-on-po", json={"po_line_id": line.id}
    )
    assert first.status_code == 200, first.text

    again = client.post(
        f"{BASE}/order-inquiry-rows/{row.id}/place-on-po", json={"po_line_id": other_line.id}
    )
    assert again.status_code == 409
    assert again.json()["code"] == "order_inquiry_not_raised"


def test_a_reader_cannot_place_a_row(reader_api):
    client, db, world, _user_id = reader_api
    line = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"], qty_ordered="50",
    )
    row = _row(db, world["company_id"], world["inquiry"], qty="10", item_code=world["product"].product_code)

    response = client.post(
        f"{BASE}/order-inquiry-rows/{row.id}/place-on-po", json={"po_line_id": line.id}
    )

    assert response.status_code == 403


def test_placing_without_a_po_line_id_is_a_validation_error(api):
    client, db, world, _user_id = api
    row = _row(db, world["company_id"], world["inquiry"], qty="10", item_code=world["product"].product_code)

    response = client.post(f"{BASE}/order-inquiry-rows/{row.id}/place-on-po", json={})

    assert response.status_code == 422


# -------------------------------------------------------------------- unplace


def test_unplacing_reverts_the_row_and_deletes_the_claim(api):
    client, db, world, _user_id = api
    line = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"],
        qty_ordered="50", expected_date=date(2026, 10, 1),
    )
    row = _row(db, world["company_id"], world["inquiry"], qty="10", item_code=world["product"].product_code)
    placed = client.post(
        f"{BASE}/order-inquiry-rows/{row.id}/place-on-po", json={"po_line_id": line.id}
    )
    assert placed.status_code == 200, placed.text

    response = client.post(f"{BASE}/order-inquiry-rows/{row.id}/unplace")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == INQUIRY_RAISED
    assert body["po_ref"] is None
    assert body["po_line_id"] is None
    assert f"Unplaced from {world['po'].po_number}" in body["note"]

    claims = (
        db.query(OrderLinkClaim)
        .filter(OrderLinkClaim.po_number == world["po"].po_number, OrderLinkClaim.source == "order_inquiry")
        .all()
    )
    assert claims == []


def test_unplacing_a_row_that_is_not_placed_is_a_409(api):
    client, db, world, _user_id = api
    row = _row(db, world["company_id"], world["inquiry"], qty="10", item_code=world["product"].product_code)

    response = client.post(f"{BASE}/order-inquiry-rows/{row.id}/unplace")

    assert response.status_code == 409
    assert response.json()["code"] == "order_inquiry_not_placed"


def test_a_reader_cannot_unplace_a_row(reader_api):
    client, db, world, _user_id = reader_api
    row = _row(
        db, world["company_id"], world["inquiry"], qty="10", item_code=world["product"].product_code,
        state=INQUIRY_PLACED, po_ref=world["po"].po_number,
    )

    response = client.post(f"{BASE}/order-inquiry-rows/{row.id}/unplace")

    assert response.status_code == 403


# -------------------------------------------------------------------- worklist


def test_the_worklist_reads_po_no_and_supplier_off_the_direct_tag(api):
    client, db, world, _user_id = api
    line = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"], qty_ordered="50",
    )
    row = _row(
        db, world["company_id"], world["inquiry"], qty="10", item_code=world["product"].product_code,
        state=INQUIRY_PLACED, po_ref=world["po"].po_number, po_line_id=line.id,
    )

    response = client.get(f"{BASE}/order-inquiries", params={"query": row.item_code})

    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert len(rows) == 1
    assert rows[0]["po_number"] == world["po"].po_number
    assert rows[0]["supplier"] == world["supplier"].supplier_name


def test_the_worklist_state_filter_placed_returns_only_placed_rows(api):
    client, db, world, _user_id = api
    line = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"], qty_ordered="50",
    )
    raised_row = _row(db, world["company_id"], world["inquiry"], qty="5", item_code=f"{MARKER}-RAISED")
    placed_row = _row(
        db, world["company_id"], world["inquiry"], qty="5", item_code=f"{MARKER}-PLACED",
        state=INQUIRY_PLACED, po_ref=world["po"].po_number, po_line_id=line.id,
    )

    response = client.get(f"{BASE}/order-inquiries", params={"state": "placed"})

    assert response.status_code == 200, response.text
    ids = {row["id"] for row in response.json()["data"]}
    assert placed_row.id in ids
    assert raised_row.id not in ids


# -------------------------------------------------------------- netting proof


def test_placing_leaves_committed_v_confirmed_leg_and_unplacing_restores_it():
    """The captain's "the quantity to be ordered is deducted" (section G), proven against
    the view the reorder engine actually reads rather than against the row's own state."""
    from app.models.base import company_scope
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    with pg_session() as db:
        company_id = _confirm_sorento(db)
        user_id = _confirm_user(db, f"{MARKER} Buyer")
        product = _confirm_product(db)
        warehouse = _confirm_warehouse(db, f"ZZT-NT-{str(product.id)[:4]}")

        core_so = _confirm_core_so(db, company_id)
        core_line = _confirm_core_line(db, core_so, product, warehouse, qty_ordered="40")
        from app.services.project_service import register_project

        project = register_project(
            db, company_id=company_id, actor_user_id=user_id, developer_party_id=None,
            title=f"{MARKER} Netting Residences",
        )
        order = _confirm_project_so(db, project, so_id=core_so.id)
        line = _confirm_project_line(db, order, line_no=10, product=product, core_line=core_line)

        decision = SOSupplyDecision(
            id=_uid(), company_id=company_id, project_sales_order_id=order.id, revision_no=1,
            state="active", line_snapshots=[{"line_no": 10}], confirmed_by=user_id,
            confirmed_at=datetime.utcnow(),
        )
        db.add(decision)
        db.flush()

        inquiry = OrderInquiry(
            id=_uid(), company_id=company_id, project_sales_order_id=order.id, state=INQUIRY_RAISED,
        )
        db.add(inquiry)
        db.flush()
        row = OrderInquiryRow(
            id=_uid(), company_id=company_id, order_inquiry_id=inquiry.id, so_line_id=line.id,
            item_code=product.product_code, qty=Decimal("40"), verb=IV_ORDER, state=INQUIRY_RAISED,
            supply_decision_id=decision.id,
        )
        db.add(row)

        supplier = _supplier(db, company_id, f"{MARKER} Netting Supplier")
        po = _po(db, company_id, supplier, f"ZZT-PO-{_uid()[:8]}")
        po_line = _po_line(
            db, company_id, po, product, warehouse, qty_ordered="60", expected_date=date(2026, 9, 20),
        )
        db.commit()

        def confirmed_committed() -> Decimal:
            value = db.execute(
                text(
                    "SELECT COALESCE(SUM(project_confirmed_committed), 0) "
                    "FROM scm.committed_v WHERE product_id = :pid AND warehouse_id = :wid"
                ),
                {"pid": product.id, "wid": warehouse.id},
            ).scalar()
            return Decimal(str(value))

        assert confirmed_committed() == Decimal("40")

        service = ProjectOrderInquiryService(db)
        with company_scope(db, frozenset({company_id})):
            placed = service.place_on_po(row.id, po_line.id, actor_user_id=user_id)
        db.commit()
        assert placed["state"] == INQUIRY_PLACED

        db.expire_all()
        assert confirmed_committed() == Decimal("0"), (
            "a placed row must leave committed_v's confirmed leg - the captain's deduction"
        )

        with company_scope(db, frozenset({company_id})):
            unplaced = service.unplace(row.id, actor_user_id=user_id)
        db.commit()
        assert unplaced["state"] == INQUIRY_RAISED

        db.expire_all()
        assert confirmed_committed() == Decimal("40"), (
            "unplacing must return the row to raised so the reorder engine counts it again"
        )
