"""The keyed-into-AutoCount status at the grain the decision actually lives at.

A run decided at LOCATION grain keeps its decisions on `scm.reorder_recommendation`, one
per (product, warehouse), and its product summary row is a read-only aggregate with no
chosen quantity. So keying under that grain is per location: the write names the
warehouse, lands on that recommendation, and leaves the product's other locations alone.
A run decided at PRODUCT grain is unchanged - no location on the write, the summary row
holds the status.

Postgres, marker-prefixed seeding, rolled back at teardown. Nothing borrowed with LIMIT 1.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.models.inventory import Warehouse
from app.models.procurement import ProductSupplier, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import ReorderRecommendation, ReorderRun
from app.services.error_handler import AppException
from app.services.scm import summary_order_service as svc
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime
from tests._pg_fixture import pg_session
from tests.scm.conftest import (  # noqa: F401  (scm_app is a fixture)
    requires_pg,
    scm_app,
    single_location_plan_basis,
)
from tests.scm.test_order_summary_routes import _company, _principal

pytestmark = requires_pg

MARKER = "ZZTPWK"


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


def _now():
    return to_naive_datetime(datetime.now(MALAYSIA_TZ))


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


def _product(db) -> Product:
    cat = ProductCategory(id=_u(), category_code=_code("CAT")[:40], category_name=f"{MARKER} cat")
    uom = UnitOfMeasure(id=_u(), uom_code=_code("U")[:20], uom_name=f"{MARKER} uom")
    db.add_all([cat, uom])
    db.flush()
    product = Product(
        id=_u(), product_code=_code("P"), product_name=f"{MARKER} product",
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    db.add(product)
    db.flush()
    return product


def _warehouse(db, stem="W") -> Warehouse:
    wh = Warehouse(
        id=_u(), warehouse_code=_code(stem)[:30], warehouse_name=f"{MARKER} {stem}",
        is_active=True, counts_as_available=True,
    )
    db.add(wh)
    db.flush()
    return wh


def _run(db, *, decision_grain, contract_version=1) -> ReorderRun:
    run = ReorderRun(
        id=_u(), status="completed", buy_scope="warehouse",
        started_at=_now(), source_system="scm", source_ref=_code("RUN"),
        decision_grain=decision_grain, front_planning_contract_version=contract_version,
    )
    db.add(run)
    db.flush()
    return run


def _rec(db, run, product, warehouse, *, rounded_qty, status="accepted") -> ReorderRecommendation:
    inputs = {"project_need": rounded_qty, "retail_need": 0, "unclassified_need": 0}
    inputs["plan_basis"] = single_location_plan_basis(inputs, warehouse, rounded=float(rounded_qty))
    r = ReorderRecommendation(
        id=_u(), run_id=run.id, rec_type="buy", product_id=product.id,
        warehouse_id=warehouse.id, rounded_qty=rounded_qty, inputs=inputs, status=status,
    )
    db.add(r)
    db.flush()
    return r


def _supplier_link(db, product) -> Supplier:
    sup = Supplier(id=_u(), supplier_code=_code("S")[:30], supplier_name=f"{MARKER} supplier")
    db.add(sup)
    db.flush()
    db.add(ProductSupplier(
        id=_u(), product_id=product.id, supplier_id=sup.id, standard_lead_time_days=14,
        unit_cost=10, currency="MYR", is_primary_supplier=True,
    ))
    db.flush()
    return sup


def _location_run(db):
    """One product decided at TWO locations on a location-grain run."""
    product = _product(db)
    run = _run(db, decision_grain="location")
    wh_a, wh_b = _warehouse(db, "A"), _warehouse(db, "B")
    _rec(db, run, product, wh_a, rounded_qty=8)
    _rec(db, run, product, wh_b, rounded_qty=5)
    svc.write_rows(db, run.id)
    return product, run, wh_a, wh_b


def _worklist_row(db, run, product, warehouse):
    return next(
        r for r in svc.po_worklist(db, run_id=run.id)["rows"]
        if r["product_code"] == product.product_code
        and r["warehouse_code"] == warehouse.warehouse_code
    )


# --------------------------------------------------------------------------- #
# location grain: per (product, location)
# --------------------------------------------------------------------------- #

def test_keying_one_location_leaves_the_products_other_location_alone(db):
    product, run, wh_a, wh_b = _location_run(db)

    out = svc.set_keyed_status(
        db, product.product_code, run_id=run.id, keyed_status="keyed", actor="Joey",
        warehouse_code=wh_a.warehouse_code,
    )

    assert out["keyed_status"] == "keyed"
    assert out["keyed_by"] == "Joey"
    assert out["warehouse_code"] == wh_a.warehouse_code
    a = _worklist_row(db, run, product, wh_a)
    b = _worklist_row(db, run, product, wh_b)
    assert (a["keyed_status"], a["keyed_by"]) == ("keyed", "Joey")
    assert (b["keyed_status"], b["keyed_by"], b["keyed_at"]) == ("not_keyed", None, None)


def test_the_location_status_can_move_backwards(db):
    product, run, wh_a, _wh_b = _location_run(db)
    svc.set_keyed_status(
        db, product.product_code, run_id=run.id, keyed_status="keyed", actor="Joey",
        warehouse_code=wh_a.warehouse_code,
    )

    out = svc.set_keyed_status(
        db, product.product_code, run_id=run.id, keyed_status="not_keyed", actor="Joey",
        warehouse_code=wh_a.warehouse_code,
    )

    assert out["keyed_status"] == "not_keyed"
    assert _worklist_row(db, run, product, wh_a)["keyed_status"] == "not_keyed"


def test_a_location_not_on_the_run_is_a_404(db):
    product, run, _wh_a, _wh_b = _location_run(db)
    elsewhere = _warehouse(db, "C")

    with pytest.raises(AppException) as e:
        svc.set_keyed_status(
            db, product.product_code, run_id=run.id, keyed_status="keyed", actor="Joey",
            warehouse_code=elsewhere.warehouse_code,
        )
    assert e.value.status_code == 404


def test_an_unknown_warehouse_code_is_a_404(db):
    product, run, _wh_a, _wh_b = _location_run(db)

    with pytest.raises(AppException) as e:
        svc.set_keyed_status(
            db, product.product_code, run_id=run.id, keyed_status="keyed", actor="Joey",
            warehouse_code=_code("NOWHERE"),
        )
    assert e.value.status_code == 404


def test_a_location_run_needs_the_location_named(db):
    """The product summary row under this grain is an aggregate that owns no decision, so a
    write that names no location has nowhere honest to land."""
    product, run, _wh_a, _wh_b = _location_run(db)

    with pytest.raises(AppException) as e:
        svc.set_keyed_status(
            db, product.product_code, run_id=run.id, keyed_status="keyed", actor="Joey",
        )
    assert e.value.status_code == 422


def test_a_dismissed_recommendation_is_not_keyable(db):
    """Only an accepted or adjusted recommendation is on the worklist, so only that is keyable."""
    product = _product(db)
    run = _run(db, decision_grain="location")
    wh = _warehouse(db, "A")
    _rec(db, run, product, wh, rounded_qty=8, status="dismissed")
    svc.write_rows(db, run.id)

    with pytest.raises(AppException) as e:
        svc.set_keyed_status(
            db, product.product_code, run_id=run.id, keyed_status="keyed", actor="Joey",
            warehouse_code=wh.warehouse_code,
        )
    assert e.value.status_code == 404


def test_the_location_worklist_starts_every_row_not_keyed(db):
    product, run, wh_a, wh_b = _location_run(db)

    for wh in (wh_a, wh_b):
        row = _worklist_row(db, run, product, wh)
        assert (row["keyed_status"], row["keyed_by"], row["keyed_at"]) == ("not_keyed", None, None)


# --------------------------------------------------------------------------- #
# product grain: unchanged
# --------------------------------------------------------------------------- #

def test_a_product_run_still_keys_the_product_row(db):
    product = _product(db)
    run = _run(db, decision_grain="product")
    wh = _warehouse(db, "A")
    sup = _supplier_link(db, product)
    _rec(db, run, product, wh, rounded_qty=8, status="proposed")
    svc.write_rows(db, run.id)
    svc.record_decision(db, product.product_code, run_id=run.id, chosen_qty=8,
                        supplier_code=sup.supplier_code, actor="mr loo")

    out = svc.set_keyed_status(
        db, product.product_code, run_id=run.id, keyed_status="keying", actor="Joey",
    )

    assert out["keyed_status"] == "keying"
    assert out["warehouse_code"] is None
    row = next(r for r in svc.po_worklist(db, run_id=run.id)["rows"]
               if r["product_code"] == product.product_code)
    assert row["keyed_status"] == "keying"


def test_a_product_run_refuses_a_location_on_the_write(db):
    """A product decision is ONE purchase order for the company; keying a location of it
    would record a status the product row does not carry."""
    product = _product(db)
    run = _run(db, decision_grain="product")
    wh = _warehouse(db, "A")
    sup = _supplier_link(db, product)
    _rec(db, run, product, wh, rounded_qty=8, status="proposed")
    svc.write_rows(db, run.id)
    svc.record_decision(db, product.product_code, run_id=run.id, chosen_qty=8,
                        supplier_code=sup.supplier_code, actor="mr loo")

    with pytest.raises(AppException) as e:
        svc.set_keyed_status(
            db, product.product_code, run_id=run.id, keyed_status="keying", actor="Joey",
            warehouse_code=wh.warehouse_code,
        )
    assert e.value.status_code == 409


# --------------------------------------------------------------------------- #
# the worklist names the run's contract version, so the chip can tell legacy apart
# --------------------------------------------------------------------------- #

def test_the_worklist_carries_the_runs_contract_version(db):
    product, run, _wh_a, _wh_b = _location_run(db)

    out = svc.po_worklist(db, run_id=run.id)

    assert out["decision_grain"] == "location"
    assert out["front_planning_contract_version"] == 1


def test_a_legacy_worklist_carries_a_null_contract_version(db):
    product = _product(db)
    run = _run(db, decision_grain=None, contract_version=None)

    out = svc.po_worklist(db, run_id=run.id)

    assert out["decision_grain"] is None
    assert out["front_planning_contract_version"] is None
    assert out["rows"] == []


# --------------------------------------------------------------------------- #
# over the wire
# --------------------------------------------------------------------------- #

_VIEW_PERM = "scm.dashboard.view"
_RUN_PERM = "scm.reorder.run"


def test_the_route_keys_one_location_and_the_next_read_shows_it(scm_app):  # noqa: F811
    app, db, gcu, gcuk = scm_app
    _company(app, db)
    product, run, wh_a, wh_b = _location_run(db)
    _principal(app, db, gcu, gcuk, perms=[_VIEW_PERM, _RUN_PERM], name="Joey")
    client = TestClient(app)

    res = client.post(
        f"/api/v1/scm/po-worklist/{product.product_code}/keyed-status",
        json={"run_id": str(run.id), "keyed_status": "keying",
              "warehouse_code": wh_a.warehouse_code},
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["keyed_status"] == "keying"
    assert body["warehouse_code"] == wh_a.warehouse_code
    assert body["keyed_by"] == "Joey"
    listing = client.get(f"/api/v1/scm/po-worklist?run_id={run.id}").json()
    assert listing["front_planning_contract_version"] == 1
    by_wh = {r["warehouse_code"]: r for r in listing["rows"]
             if r["product_code"] == product.product_code}
    assert by_wh[wh_a.warehouse_code]["keyed_status"] == "keying"
    assert by_wh[wh_b.warehouse_code]["keyed_status"] == "not_keyed"


def test_the_route_404s_a_location_not_on_the_run(scm_app):  # noqa: F811
    app, db, gcu, gcuk = scm_app
    _company(app, db)
    product, run, _wh_a, _wh_b = _location_run(db)
    elsewhere = _warehouse(db, "C")
    _principal(app, db, gcu, gcuk, perms=[_VIEW_PERM, _RUN_PERM], name="Joey")
    client = TestClient(app)

    res = client.post(
        f"/api/v1/scm/po-worklist/{product.product_code}/keyed-status",
        json={"run_id": str(run.id), "keyed_status": "keying",
              "warehouse_code": elsewhere.warehouse_code},
    )

    assert res.status_code == 404, res.text
