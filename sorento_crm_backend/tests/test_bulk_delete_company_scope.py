"""Bulk deletes and pending-action parks stay inside the caller's company.

Follows #2024 (products). The company scope filter (`app/services/company_scope.py`)
applies to ORM SELECTs only, so a bulk `query(...).delete()` reached every company's rows
by id. Order, promotion and stock bulk deletes now load their rows through the scoped read
and delete each one the way a single delete does. Parking a pending action reads the
record under the same scope first, so nobody can start a countdown on a record they
cannot see.

Postgres only, on the blank scratch schema, seeding its own chain.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be the first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.base import company_scope
from app.models.inventory import Stock, Warehouse
from app.models.marketing import Promotion
from app.models.order import Order, OrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.sla import SlaFormAction
from tests._pg_fixture import blank_session, unique_code

from app.services import record_actions  # noqa: F401  (registers the record actions)

_SORENTO = "00000000-0000-0000-0000-000000000001"
_ACTOR_ID = "5e6f7a8b-9c0d-4e1f-8a2b-3c4d5e6f7a8b"
_ROLE_ID = "6f7a8b9c-0d1e-4f2a-9b3c-4d5e6f7a8b9c"

ORDERS_BULK = "/api/v1/order-management/orders/bulk"
PROMOTIONS_BULK = "/api/v1/marketing/promotions/bulk"
STOCK_BULK = "/api/v1/inventory/stock/bulk"
PENDING = "/api/v1/pending-actions"

_SLUGS = (
    "order_management.orders.delete",
    "marketing.promotions.delete",
    "inventory.stock.delete",
    "master_data.products.delete",
)


def _seed_actor(db) -> None:
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    db.add(
        UserRole(
            id=_ROLE_ID,
            slug="zzt_bulk_scope",
            name="zzt_bulk_scope",
            description="",
            is_protected=False,
            is_default=False,
        )
    )
    db.add(User(id=_ACTOR_ID, email="zzt-bulk-scope@test.com", name="Bo Scope", status="ACTIVE"))
    db.flush()
    db.add(UserRoleAssignment(user_id=_ACTOR_ID, role_id=_ROLE_ID))
    for slug in _SLUGS:
        permission = db.query(UserPermission).filter(UserPermission.slug == slug).first()
        if permission is None:
            permission = UserPermission(id=str(uuid.uuid4()), slug=slug, name=slug, description="")
            db.add(permission)
            db.flush()
        db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=_ROLE_ID, permission_id=permission.id))
    db.commit()


@pytest.fixture
def api():
    """One session, one signed-in user, and a switchable company scope (the request's
    and the session's together, so rows created after `_in_company` are stamped to it)."""
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.models.company import Company
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed_actor(db)
        other_company = str(uuid.uuid4())
        db.add(Company(id=other_company, name="ZZT other co", code=unique_code("ZZTC")))
        db.commit()

        here = {"company": _SORENTO}

        def _override_get_db():
            yield db

        async def _override_scope():
            scope = frozenset({here["company"]})
            set_company_scope(db, scope)
            return scope

        principal = {"id": _ACTOR_ID, "email": "zzt-bulk-scope@test.com"}
        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[apply_company_scope] = _override_scope
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        def _in_company(company_id: str):
            here["company"] = company_id
            set_company_scope(db, frozenset({company_id}))

        yield db, _in_company, other_company

        app.dependency_overrides.clear()


def _order(db) -> str:
    row = Order(id=str(uuid.uuid4()), order_number=unique_code("ZZTDO"))
    db.add(row)
    db.commit()
    return row.id


def _promotion(db) -> str:
    row = Promotion(id=str(uuid.uuid4()), description=unique_code("ZZTPR"))
    db.add(row)
    db.commit()
    return row.id


def _product(db) -> str:
    category = ProductCategory(
        id=str(uuid.uuid4()), category_code=unique_code("CAT")[:50], category_name="Category"
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each")
    db.add_all([category, uom])
    db.flush()
    code = unique_code("ZZTP")
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=0,
        is_active=True,
    )
    db.add(row)
    db.commit()
    return row.id


def _stock(db) -> str:
    warehouse = Warehouse(id=str(uuid.uuid4()), warehouse_code=unique_code("WH")[:50], warehouse_name="ZZT WH")
    db.add(warehouse)
    db.flush()
    row = Stock(id=str(uuid.uuid4()), product_id=_product(db), warehouse_id=warehouse.id)
    db.add(row)
    db.commit()
    return row.id


_CASES = {
    "orders": (ORDERS_BULK, _order, Order),
    "promotions": (PROMOTIONS_BULK, _promotion, Promotion),
    "stock": (STOCK_BULK, _stock, Stock),
}


def _exists(db, model, row_id: str) -> bool:
    db.expire_all()
    with company_scope(db, None):
        return db.query(model).filter(model.id == row_id).first() is not None


def _bulk_delete(client: TestClient, url: str, ids):
    return client.request("DELETE", url, json={"ids": ids})


# --------------------------------------------------------------------------- #
# Bulk delete                                                                 #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("case", sorted(_CASES))
def test_bulk_delete_leaves_another_companys_row_alone(api, case):
    url, make, model = _CASES[case]
    db, _in_company, other = api
    _in_company(other)
    theirs = make(db)
    _in_company(_SORENTO)

    with TestClient(app) as client:
        res = _bulk_delete(client, url, [theirs])
    assert res.status_code == 200, res.text
    assert res.json()["deleted_count"] == 0
    assert _exists(db, model, theirs)


@pytest.mark.parametrize("case", sorted(_CASES))
def test_bulk_delete_of_a_mixed_list_deletes_only_own_company(api, case):
    url, make, model = _CASES[case]
    db, _in_company, other = api
    _in_company(other)
    theirs = make(db)
    _in_company(_SORENTO)
    mine = make(db)

    with TestClient(app) as client:
        res = _bulk_delete(client, url, [mine, theirs])
    assert res.status_code == 200, res.text
    assert res.json()["deleted_count"] == 1
    assert not _exists(db, model, mine)
    assert _exists(db, model, theirs)


@pytest.mark.parametrize("case", sorted(_CASES))
def test_bulk_delete_still_deletes_own_company_rows(api, case):
    url, make, model = _CASES[case]
    db, _in_company, _other = api
    a, b = make(db), make(db)

    with TestClient(app) as client:
        res = _bulk_delete(client, url, [a, b])
    assert res.status_code == 200, res.text
    assert res.json()["deleted_count"] == 2
    assert not _exists(db, model, a)
    assert not _exists(db, model, b)


def test_promotion_and_order_deletes_need_the_delete_permission(api):
    """These routes were gated on sign-in alone; they now ask for the `.delete` slug the
    screen already hides the single delete behind."""
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.models.user import User

    db, _in_company, _other = api
    stranger = str(uuid.uuid4())
    db.add(User(id=stranger, email=f"{stranger}@zzt.test", name="No Grants", status="ACTIVE"))
    db.commit()
    mine = _promotion(db)
    principal = {"id": stranger, "email": f"{stranger}@zzt.test"}
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

    order = _order(db)
    line_order, line_ids = _order_with_lines(db)

    with TestClient(app) as client:
        res = _bulk_delete(client, PROMOTIONS_BULK, [mine])
        single = client.delete(f"/api/v1/marketing/promotions/{mine}")
        single_order = client.delete(f"/api/v1/order-management/orders/{order}")
        lines = _bulk_delete_lines(client, line_order, line_ids)
    assert res.status_code == 403, res.text
    assert single.status_code == 403, single.text
    assert single_order.status_code == 403, single_order.text
    assert lines.status_code == 403, lines.text
    assert _line_ids(db, line_order) == set(line_ids)
    assert _exists(db, Promotion, mine)
    assert _exists(db, Order, order)


def _order_with_lines(db, n: int = 2) -> tuple[str, list[str]]:
    order_id = _order(db)
    warehouse = Warehouse(id=str(uuid.uuid4()), warehouse_code=unique_code("WH")[:50], warehouse_name="ZZT WH")
    db.add(warehouse)
    db.flush()
    line_ids = []
    for sequence in range(1, n + 1):
        line = OrderLine(
            id=str(uuid.uuid4()),
            order_id=order_id,
            line_sequence=sequence,
            product_id=_product(db),
            warehouse_id=warehouse.id,
        )
        db.add(line)
        line_ids.append(line.id)
    db.commit()
    return order_id, line_ids


def _line_ids(db, order_id: str) -> set[str]:
    db.expire_all()
    with company_scope(db, None):
        return {r.id for r in db.query(OrderLine).filter(OrderLine.order_id == order_id).all()}


def _bulk_delete_lines(client: TestClient, order_id: str, ids):
    return client.request("DELETE", f"/api/v1/order-management/orders/{order_id}/lines/bulk-delete", json={"ids": ids})


def test_order_line_bulk_delete_refuses_another_companys_order(api):
    db, _in_company, other = api
    _in_company(other)
    theirs, their_lines = _order_with_lines(db)
    _in_company(_SORENTO)

    with TestClient(app) as client:
        res = _bulk_delete_lines(client, theirs, their_lines)
    assert res.status_code == 404, res.text
    assert _line_ids(db, theirs) == set(their_lines)


def test_order_line_bulk_delete_still_deletes_own_lines(api):
    db, _in_company, _other = api
    mine, (gone, kept) = _order_with_lines(db)

    with TestClient(app) as client:
        res = _bulk_delete_lines(client, mine, [gone])
    assert res.status_code == 200, res.text
    assert res.json()["deleted_count"] == 1
    assert _line_ids(db, mine) == {kept}


# --------------------------------------------------------------------------- #
# Park-time record visibility                                                 #
# --------------------------------------------------------------------------- #


def _park(client: TestClient, action_key: str, entity_type: str, entity_id: str):
    return client.post(
        PENDING,
        json={"action_key": action_key, "entity_type": entity_type, "entity_id": entity_id, "payload": {}},
    )


def _parked(db, entity_id: str) -> int:
    db.expire_all()
    return db.query(SlaFormAction).filter(SlaFormAction.source_entity_id == entity_id).count()


@pytest.mark.parametrize(
    "action_key,entity_type,make",
    [("order.delete", "order", _order), ("product.delete", "product", _product)],
)
def test_parking_on_another_companys_record_is_not_found(api, action_key, entity_type, make):
    db, _in_company, other = api
    _in_company(other)
    theirs = make(db)
    _in_company(_SORENTO)

    with TestClient(app) as client:
        res = _park(client, action_key, entity_type, theirs)
    assert res.status_code == 404, res.text
    assert _parked(db, theirs) == 0


def test_parking_with_a_malformed_id_is_not_found(api):
    with TestClient(app) as client:
        res = _park(client, "order.delete", "order", "not-a-uuid")
    assert res.status_code == 404, res.text


@pytest.mark.parametrize(
    "action_key,entity_type,make",
    [("order.delete", "order", _order), ("product.delete", "product", _product)],
)
def test_parking_on_own_companys_record_still_works(api, action_key, entity_type, make):
    db, _in_company, _other = api
    mine = make(db)

    with TestClient(app) as client:
        res = _park(client, action_key, entity_type, mine)
    assert res.status_code == 202, res.text
    assert _parked(db, mine) == 1


def test_every_record_action_is_classified_for_park_time_visibility():
    """A new record action must say how its record is checked at park time: through the
    scoped model read, or by name in the reviewed list of keys that are not."""
    from app.api.v1.system import pending_actions
    from sqlalchemy.dialects.postgresql import UUID

    from app.models.base import CompanyScopedMixin
    from app.services.form_action_registry import REGISTRY

    record_keys = {key for key, action in REGISTRY.items() if action.permission}
    scoped = set(pending_actions._PARK_SCOPED_MODELS)
    exempt = set(pending_actions._PARK_SCOPE_EXEMPT)
    assert not scoped & exempt
    assert record_keys - scoped - exempt == set()
    assert (scoped | exempt) - record_keys == set()
    for key, model in pending_actions._PARK_SCOPED_MODELS.items():
        assert issubclass(model, CompanyScopedMixin), key
        # The id is format-checked as a UUID before the read.
        assert isinstance(model.__table__.c.id.type, UUID), key
