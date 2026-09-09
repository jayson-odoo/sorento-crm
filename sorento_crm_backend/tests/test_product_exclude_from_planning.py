"""S5 (PLAN-reorder-feedback-9sep.md) - a product can be excluded from reorder planning.

`products.exclude_from_planning BOOLEAN NOT NULL DEFAULT false`, no backfill (G3, 9 Sep
ruling - the buyer flips `**NEW` etc. by hand). AC-S5.1 to S5.5.

Harness copied from `tests/test_product_barcode_route.py` - the closest existing "a new
scalar column reaches ProductResponse on GET/PUT/list" pin - and
`tests/scm/test_m3_run.py` for the create-run engine harness. Postgres only, every row
marker-prefixed and seeded fresh; nothing borrowed off the shared prod-copy DB.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.dependencies import (
    get_current_user,
    get_current_user_or_api_key,
    get_db,
    get_external_api_user,
)
from app.main import app
from app.models.base import set_company_scope
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.company_scope_resolver import apply_company_scope
from app.services.scm import reorder_run_service as svc
from tests._pg_fixture import blank_session, unique_code
from tests.scm.conftest import requires_pg, scm_app  # noqa: F401 - pytest fixture import
from tests.scm.test_m3_run import (
    _client,
    _link,
    _mk_committed,
    _mk_demand,
    _mk_product,
    _mk_stock,
    _mk_supplier,
    _mk_warehouse,
)

pytestmark = requires_pg

SORENTO_ID = DEFAULT_COMPANY_ID
STEM = "ZZTXPLAN"


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, None)
        yield session


@pytest.fixture
def world(db):
    uom_id = str(uuid.uuid4())
    cat_id = str(uuid.uuid4())
    db.add(UnitOfMeasure(id=uom_id, uom_code=unique_code("U")[:20], uom_name="Each"))
    db.add(ProductCategory(id=cat_id, category_code=unique_code("C")[:50], category_name="C"))
    db.flush()

    def product(code: str) -> str:
        pid = str(uuid.uuid4())
        db.add(
            Product(
                id=pid, product_code=code, product_name=code,
                category_id=cat_id, base_uom_id=uom_id, list_price=Decimal("10.00"),
                is_active=True, company_id=SORENTO_ID,
            )
        )
        db.flush()
        return pid

    db.commit()
    return {"uom_id": uom_id, "cat_id": cat_id, "product": product}


@pytest.fixture
def api(db):
    def _override_get_db():
        yield db

    principal = {"id": str(uuid.uuid4()), "email": "zzt-xplan@test.com"}

    async def _override_scope():
        scope = frozenset({SORENTO_ID})
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
    app.dependency_overrides[get_external_api_user] = lambda: principal
    app.dependency_overrides[apply_company_scope] = _override_scope
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


# --- AC-S5.1: the model/column itself, defaulting False ------------------------------

def test_product_model_carries_exclude_from_planning_defaulting_false(db, world):
    pid = world["product"](f"{STEM}-MODEL")
    db.commit()

    row = db.query(Product).filter(Product.id == pid).one()
    assert row.exclude_from_planning is False


# --- AC-S5.3/S5.4: PUT round-trips on GET (detail) and the list serializer ------------

def test_put_sets_exclude_from_planning_and_get_detail_reflects_it(api, world, db):
    pid = world["product"](f"{STEM}-PUT")
    db.commit()

    res = api.put(
        f"/api/v1/master-data/products/{pid}", json={"exclude_from_planning": True}
    )
    assert res.status_code == 200, res.text
    assert res.json().get("exclude_from_planning") is True

    detail = api.get(f"/api/v1/master-data/products/{pid}")
    assert detail.json().get("exclude_from_planning") is True


def test_put_round_trips_on_an_autocount_placeholder_code(api, world, db):
    """AC-S5.7: a product whose CODE is one of the AutoCount placeholders (`**NEW`,
    `**SPARE PART`, `**REPLACE`, `**REPAIR`) must round-trip `exclude_from_planning`
    exactly like any other - no backend validator on `product_code` may reject the `*`
    the buyer needs to flip the switch on the very codes S5 exists for."""
    pid = world["product"]("**NEW")
    db.commit()

    res = api.put(
        f"/api/v1/master-data/products/{pid}", json={"exclude_from_planning": True}
    )
    assert res.status_code == 200, res.text
    assert res.json().get("product_code") == "**NEW"
    assert res.json().get("exclude_from_planning") is True

    detail = api.get(f"/api/v1/master-data/products/{pid}")
    assert detail.json().get("product_code") == "**NEW"
    assert detail.json().get("exclude_from_planning") is True


def test_the_products_list_serializer_carries_the_field(db, world):
    """`list_query_registry`'s `products` resource serializes through the SAME
    `ProductResponse` the routes use (`_serialize_products`) - pinned directly against
    that function so a drift between the two never hides behind only testing the route."""
    from app.services.list_query_registry import ADAPTERS

    pid = world["product"](f"{STEM}-LISTQ")
    db.execute(text(
        "UPDATE products SET exclude_from_planning = true WHERE id = :p"
    ), {"p": pid})
    db.commit()

    row = db.query(Product).filter(Product.id == pid).one()
    serialized = ADAPTERS["products"].serializer([row])
    assert serialized[0].exclude_from_planning is True


# --- AC-S5.2/S5.5: the engine never plans an excluded product -------------------------

def test_an_excluded_product_with_committed_demand_is_absent_from_the_run(scm_app):
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTXW-ENG")
    pid = _mk_product(db, "ZZTXP-ENG")
    _mk_stock(db, pid, wid, 5)
    _mk_demand(db, pid, wid, 10.0)
    _mk_committed(db, pid, wid, qty=1)
    _link(db, pid, _mk_supplier(db, "ZZT Exclude Eng Supplier"))
    db.execute(text(
        "UPDATE products SET exclude_from_planning = true WHERE id = :p"
    ), {"p": pid})
    db.flush()

    created = svc.create_run(db, ["ZZTXW-ENG"], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)

    rec = db.execute(text(
        "SELECT 1 FROM scm.reorder_recommendation WHERE run_id = :r AND product_id = :p"
    ), {"r": created["run_id"], "p": pid}).first()
    assert rec is None, "an excluded product must earn no row even with committed demand"


def test_naming_an_excluded_product_at_start_plan_answers_422_with_its_code(scm_app):
    """AC-S5.2: G10's named-product bypass does NOT extend to an excluded product - the
    create request refuses it outright, naming the code."""
    app_, db = _client(scm_app, "purchasing")
    wid = _mk_warehouse(db, "ZZTXW-422")
    pid = _mk_product(db, "ZZTXP-422")
    _mk_stock(db, pid, wid, 5)
    _mk_demand(db, pid, wid, 10.0)
    _link(db, pid, _mk_supplier(db, "ZZT Exclude 422 Supplier"))
    db.execute(text(
        "UPDATE products SET exclude_from_planning = true WHERE id = :p"
    ), {"p": pid})
    db.flush()

    with TestClient(app_) as c:
        resp = c.post("/api/v1/scm/reorder-runs", json={
            "warehouse_codes": ["ZZTXW-422"], "product_codes": ["ZZTXP-422"],
        })

    assert resp.status_code == 422, resp.text
    assert "ZZTXP-422" in resp.text


# --- S6 (Phase 3 fix round): the products list filters through the DB-seeded catalog ---

def test_the_products_field_catalog_lists_exclude_from_planning(scm_app):
    """The products list filters through `ListQueryFilterDialog`, driven entirely by the
    `list_query_fields` catalog - the column existing is not enough, a buyer cannot narrow
    the list by it until a catalog row names it too (`503_product_exclude_planning_flt`).

    Uses `scm_app` (the real, migrated database), not this file's own `db` fixture: that
    one is a from-scratch `Base.metadata.create_all` schema, which never carries the
    migration-SEEDED `list_query_fields` catalog row this test is pinning.
    """
    from app.services.list_query_metadata_service import ListQueryMetadataService

    _, real_db, _, _ = scm_app
    fields = ListQueryMetadataService(real_db).fields_by_key("products")
    field = fields.get("exclude_from_planning")
    assert field is not None, "exclude_from_planning must be in the products field catalog"
    assert field.data_type == "boolean"
    assert field.filterable is True
