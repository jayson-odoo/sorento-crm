"""QUOTE-STOCK-AGENT-LOC red tests (UAC AC-QSA-1 to AC-QSA-11).

GET /api/v1/project-sales/quotation-line-stock?product_id= answers the StockDetail shape over
the locations the signed-in user's contact (users.respond_contact_id) may see through Stock
visibility, intersected with active fulfilment-planning warehouses; JSON null when none.
Sales agents and roles play no part.

Postgres only (blank_session). Every row, FK target included, is seeded here.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.access import RespondContact, StockVisibilityPolicy
from app.models.inventory import Stock, Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.user import User

from ._pg_fixture import blank_session

MARKER = "zzt-qsal"
URL = "/api/v1/project-sales/quotation-line-stock"
VIEW = "projects.projects.view"


def _uid() -> str:
    return str(uuid.uuid4())


def _product(db) -> Product:
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:6]}", uom_name="Unit")
    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} cat"
    )
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(), product_code=f"ZZT-{_uid()[:8]}", product_name=f"{MARKER} Basin",
        category_id=category.id, base_uom_id=uom.id, list_price=Decimal("100.00"),
    )
    db.add(row)
    db.flush()
    return row


def _warehouse(
    db, code: str, *, planning: bool = True, pool: bool = False, active: bool = True
) -> Warehouse:
    row = Warehouse(
        id=_uid(), warehouse_code=f"{code}-{_uid()[:4]}", warehouse_name=code, is_active=active,
        segment=None if pool else "project", fulfilment_planning=planning,
    )
    db.add(row)
    db.flush()
    return row


def _stock(db, product, warehouse, on_hand: int) -> None:
    db.add(Stock(
        id=_uid(), product_id=product.id, warehouse_id=warehouse.id,
        quantity_on_hand=on_hand, quantity_reserved=0,
    ))
    db.flush()


def _so(db, product, warehouse, qty: int) -> None:
    order = SalesOrder(
        id=_uid(), so_number=f"ZZT-SO-{_uid()[:8]}", demand_class="project", status="open",
    )
    db.add(order)
    db.flush()
    db.add(SalesOrderLine(
        id=_uid(), sales_order_id=order.id, product_id=product.id, warehouse_id=warehouse.id,
        qty_ordered=Decimal(qty), qty_delivered=Decimal(0), line_status="open",
        purchasing_status="not_reviewed",
    ))
    db.flush()


def _spo(db, product, warehouse, qty: int, *, supplier: bool = False) -> str:
    from app.models.procurement import InboundShipment, SPOAllocation

    number = f"ZZT-SPO-{_uid()[:8]}"
    shipment = InboundShipment(
        id=_uid(), shipment_number=f"ZZT-SHIP-{_uid()[:8]}", shipment_date=date(2026, 1, 1),
        estimated_arrival_date=date(2099, 1, 1),
    )
    db.add(shipment)
    db.flush()
    supplier_id = None
    if supplier:
        from app.models.procurement import Supplier

        row = Supplier(id=_uid(), supplier_code=f"ZZT{_uid()[:6]}", supplier_name=f"{MARKER} Supplier")
        db.add(row)
        db.flush()
        supplier_id = row.id
    db.add(SPOAllocation(
        id=_uid(), spo_number=number, spo_line_number=1, inbound_shipment_id=shipment.id,
        supplier_id=supplier_id,
        warehouse_id=warehouse.id, product_id=product.id, allocated_quantity=qty,
        quantity_received=0, receipt_status="pending",
    ))
    db.flush()
    return number


def _contact(db) -> RespondContact:
    row = RespondContact(id=_uid(), phone_number=f"+6{uuid.uuid4().int % 10**10:010d}")
    db.add(row)
    db.flush()
    return row


def _user(db, contact: RespondContact | None) -> str:
    user_id = _uid()
    db.add(User(
        id=user_id, email=f"{user_id}@zzt.test", name=f"{MARKER} user",
        respond_contact_id=contact.id if contact else None,
    ))
    db.flush()
    return user_id


def _policy(db, *, contact=None, access_type=None, include=None, exclude=None, mode="detailed"):
    db.add(StockVisibilityPolicy(
        id=_uid(), contact_id=contact.id if contact else None,
        access_type_code=access_type, mode=mode,
        warehouse_ids=[w.id for w in include] if include is not None else None,
        excluded_warehouse_ids=[w.id for w in exclude] if exclude is not None else None,
    ))
    db.flush()


class _World:
    """Two planning groups (W1, W2 / W3), a site pool, a non-planning bin, one product."""

    def __init__(self, db):
        self.db = db
        db.query(StockVisibilityPolicy).delete()
        self.product = _product(db)
        self.w1 = _warehouse(db, "QA1-AA")
        self.w2 = _warehouse(db, "QA2-AA")
        self.w3 = _warehouse(db, "QB3-BB")
        self.pool = _warehouse(db, "QPOOL", pool=True)
        self.off = _warehouse(db, "QOFF", planning=False)
        self.dead = _warehouse(db, "QDEAD", active=False)
        _stock(db, self.product, self.dead, 13)
        for wh, qty in ((self.w1, 100), (self.w2, 50), (self.w3, 25), (self.pool, 10),
                        (self.off, 7)):
            _stock(db, self.product, wh, qty)
        _so(db, self.product, self.w1, 30)
        _so(db, self.product, self.w2, 5)
        _so(db, self.product, self.w3, 4)
        self.contact = _contact(db)
        self.user = _user(db, self.contact)

    def codes(self, *whs):
        return {w.warehouse_code for w in whs}


class _Caller:
    def __init__(self, db, user_id, *, slugs=(VIEW,), roles=()):
        from app.services.user_service import UserPermissionService

        self.cls = UserPermissionService
        self.saved = (
            UserPermissionService.check_user_has_permission,
            UserPermissionService.get_user_permission_slugs,
            UserPermissionService.get_user_role_slugs,
        )
        self.db, self.user_id, self.slugs, self.roles = db, user_id, list(slugs), set(roles)

    def __enter__(self):
        from fastapi.testclient import TestClient

        from app.database import get_db
        from app.dependencies import get_current_user, get_current_user_or_api_key
        from app.main import app
        from app.services.company_scope_resolver import apply_company_scope

        actor = {"id": self.user_id, "email": f"{self.user_id}@zzt.test", "role": "user"}
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[get_current_user] = lambda: dict(actor)
        app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
        app.dependency_overrides[apply_company_scope] = lambda: None
        slugs, roles = self.slugs, self.roles
        self.cls.check_user_has_permission = lambda s, uid, slug: slug in slugs
        self.cls.get_user_permission_slugs = lambda s, uid: list(slugs)
        self.cls.get_user_role_slugs = lambda s, uid: set(roles)
        return TestClient(app)

    def __exit__(self, *exc):
        from app.main import app

        (self.cls.check_user_has_permission, self.cls.get_user_permission_slugs,
         self.cls.get_user_role_slugs) = self.saved
        app.dependency_overrides.clear()
        return False


@pytest.fixture()
def world():
    from app.models.base import company_scope

    with blank_session() as db:
        company_id = db.execute(text("select id from companies where code = 'SRT'")).scalar()
        w = _World(db)
        db.commit()
        with company_scope(db, frozenset({company_id})):
            yield w


def _ask(w, user_id=None, product_id=None, **caller):
    with _Caller(w.db, user_id or w.user, **caller) as client:
        return client.get(URL, params={"product_id": product_id or w.product.id})


def _locations(response) -> set:
    assert response.status_code == 200, response.text
    body = response.json()
    assert body is not None, "expected a StockDetail, got null"
    return {row["location"] for row in body["locations"]}


def test_ac_qsa_1_user_without_a_contact_gets_null(world):
    user = _user(world.db, None)
    world.db.commit()
    response = _ask(world, user)
    assert response.status_code == 200, response.text
    assert response.json() is None


def test_ac_qsa_2_no_agent_needed_override_include_w1(world):
    w = world
    _policy(w.db, contact=w.contact, include=[w.w1])
    w.db.commit()
    assert _locations(_ask(w)) == w.codes(w.w1)
    w.db.query(StockVisibilityPolicy).delete()
    w.db.commit()
    assert _locations(_ask(w)) == w.codes(w.w1, w.w2, w.w3, w.pool)


def test_ac_qsa_3_override_two_warehouses_sums_only_those(world):
    w = world
    _policy(w.db, contact=w.contact, include=[w.w1, w.w2])
    w.db.commit()
    response = _ask(w)
    assert _locations(response) == w.codes(w.w1, w.w2)
    body = response.json()
    assert Decimal(body["available_qty"]) == Decimal((100 - 30) + (50 - 5))
    assert Decimal(body["qty_on_hand"]) == Decimal(150)


def test_ac_qsa_4_no_policy_rows_means_every_planning_warehouse(world):
    w = world
    w.db.commit()
    assert _locations(_ask(w)) == w.codes(w.w1, w.w2, w.w3, w.pool)
    assert w.dead.warehouse_code not in _locations(_ask(w))
    assert Decimal(_ask(w).json()["qty_on_hand"]) == Decimal(100 + 50 + 25 + 10)
    _policy(w.db, include=None)  # global default row, warehouse_ids NULL
    w.db.commit()
    assert _locations(_ask(w)) == w.codes(w.w1, w.w2, w.w3, w.pool)


def test_ac_qsa_5_nothing_allowed_gives_null(world):
    w = world
    every = w.db.query(Warehouse).filter(Warehouse.is_active.is_(True)).all()
    _policy(w.db, contact=w.contact, exclude=every)
    w.db.commit()
    first = _ask(w)
    assert first.status_code == 200, first.text
    assert first.json() is None
    w.db.query(StockVisibilityPolicy).delete()
    _policy(w.db, contact=w.contact, include=[])
    w.db.commit()
    second = _ask(w)
    assert second.status_code == 200, second.text
    assert second.json() is None


def test_ac_qsa_6_override_excluding_w3_keeps_the_rest(world):
    w = world
    _policy(w.db, contact=w.contact, exclude=[w.w3])
    w.db.commit()
    assert _locations(_ask(w)) == w.codes(w.w1, w.w2, w.pool)


def test_ac_qsa_7_a_non_planning_warehouse_is_neither_listed_nor_counted(world):
    w = world
    _policy(w.db, contact=w.contact, include=[w.w1, w.off])
    w.db.commit()
    response = _ask(w)
    assert _locations(response) == w.codes(w.w1)
    assert Decimal(response.json()["qty_on_hand"]) == Decimal(100)


def test_ac_qsa_8_access_type_tier_applies_without_an_override(world):
    from app.models.access import ContactAccessType, respond_contact_access_types

    w = world
    code = f"zzt{_uid()[:8]}"
    w.db.add(ContactAccessType(code=code, name=f"{MARKER} type", is_active=True))
    w.db.flush()
    w.db.execute(respond_contact_access_types.insert().values(
        contact_id=w.contact.id, access_type_code=code))
    _policy(w.db, access_type=code, include=[w.w1])
    w.db.commit()
    assert _locations(_ask(w)) == w.codes(w.w1)


def test_ac_qsa_9_two_agents_with_different_groups_change_nothing(world):
    from app.models.sales_agent import SalesAgent

    w = world
    for group in ("AA", "BB"):
        w.db.add(SalesAgent(
            id=_uid(), sales_agent=f"{MARKER}-{group}-{_uid()[:4]}", is_active=True,
            contact_id=w.contact.id, location_group=group,
        ))
    _policy(w.db, contact=w.contact, include=[w.w1, w.w3])
    w.db.commit()
    assert _locations(_ask(w)) == w.codes(w.w1, w.w3)


def test_ac_qsa_10_incoming_is_limited_to_allowed_locations(world):
    w = world
    kept = _spo(w.db, w.product, w.w1, 40)
    dropped = _spo(w.db, w.product, w.w3, 60)
    _policy(w.db, contact=w.contact, include=[w.w1])
    w.db.commit()
    response = _ask(w)
    assert _locations(response) == w.codes(w.w1)
    numbers = {row["spo_number"] for row in response.json()["incoming"]}
    assert numbers == {kept}
    assert dropped not in numbers
    assert Decimal(response.json()["spo_qty"]) == Decimal(40)


def test_ac_qsa_11_admin_has_no_bypass_and_guards(world):
    w = world
    w.db.commit()
    assert _locations(_ask(w, roles={"admin"})) == w.codes(w.w1, w.w2, w.w3, w.pool)
    bare = _user(w.db, None)
    w.db.commit()
    admin_no_contact = _ask(w, bare, roles={"admin"})
    assert admin_no_contact.status_code == 200, admin_no_contact.text
    assert admin_no_contact.json() is None
    # Guards against a missing route: the allowed call above answered 200.
    assert _ask(w, slugs=()).status_code == 403
    assert _ask(w, product_id="not-a-uuid").status_code == 422


def test_review_response_is_trimmed_of_orders_holds_and_supplier(world):
    w = world
    _spo(w.db, w.product, w.w1, 40, supplier=True)
    w.db.commit()
    response = _ask(w)
    assert _locations(response) == w.codes(w.w1, w.w2, w.w3, w.pool)
    body = response.json()
    assert body["sales_orders"] == [], body["sales_orders"]
    assert body["holds"] == []
    assert body["incoming"], "the SPO itself must still be listed"
    assert all(row["supplier_name"] is None for row in body["incoming"]), body["incoming"]


def test_review_view_own_only_user_gets_200_with_the_same_trimmed_response(world):
    w = world
    _spo(w.db, w.product, w.w1, 40, supplier=True)
    w.db.commit()
    response = _ask(w, slugs=("projects.projects.view_own",))
    assert _locations(response) == w.codes(w.w1, w.w2, w.w3, w.pool)
    body = response.json()
    assert body["sales_orders"] == []
    assert body["holds"] == []
    assert body["incoming"] and all(r["supplier_name"] is None for r in body["incoming"])


def test_mode_availability_override_answers_null(world):
    w = world
    _policy(w.db, contact=w.contact, include=[w.w1], mode="availability")
    w.db.commit()
    response = _ask(w)
    assert response.status_code == 200, response.text
    assert response.json() is None


def test_mode_availability_access_type_tier_answers_null(world):
    from app.models.access import ContactAccessType, respond_contact_access_types

    w = world
    code = f"zzt{_uid()[:8]}"
    w.db.add(ContactAccessType(code=code, name=f"{MARKER} type", is_active=True))
    w.db.flush()
    w.db.execute(respond_contact_access_types.insert().values(
        contact_id=w.contact.id, access_type_code=code))
    _policy(w.db, access_type=code, include=[w.w1], mode="availability")
    w.db.commit()
    response = _ask(w)
    assert response.status_code == 200, response.text
    assert response.json() is None


@pytest.mark.parametrize("mode", ["compact", "detailed"])
def test_only_availability_mode_blanks_the_quotation_stock(world, mode):
    w = world
    _policy(w.db, contact=w.contact, include=[w.w1], mode=mode)
    w.db.commit()
    assert _locations(_ask(w)) == w.codes(w.w1)
