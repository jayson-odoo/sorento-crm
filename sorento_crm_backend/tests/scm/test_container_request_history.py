"""F3 - the sales-history sidecar behind a loading-plan row.

`PLAN-scm-fulfilment-feedback.md` section 2 and AC-B6 / B7 / B8 are this file's contract:
twelve zero-filled monthly buckets per product, in two series (project and retail), read off
the sales-order book by `order_date`. "Ordered", never "sold" - a booked order counts from the
day it was booked.

Every test seeds its own chain under a marker-prefixed tag (CI's database is empty).
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.order import SalesOrder, SalesOrderLine
from tests.scm.conftest import as_user, requires_pg, seed_user
from tests.scm.test_container_request import MARKER, _foreign_supplier
from tests.scm.test_loading_plan import World
from tests.scm.test_outstanding_import_routes import as_company_user

pytestmark = requires_pg

HISTORY_URL = "/api/v1/scm/container-requests/history"

def _bucket(n: int) -> date:
    """The first day of the month `n` months before the CURRENT one.

    Every date in this file is relative: the window is the twelve full months before today,
    so a suite written in August has to mean the same twelve buckets in September.
    `_bucket(1)` is the newest bucket (last full month) and `_bucket(12)` the oldest.
    """
    today = date.today()
    total = today.year * 12 + (today.month - 1) - n
    return date(total // 12, total % 12 + 1, 1)


def _label(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _expected_months() -> list[str]:
    return [_label(_bucket(n)) for n in range(12, 0, -1)]


def _booked(db, w: World, key: str, qty: float, when: date, *, demand_class: str) -> None:
    """One booked SO line. Status is irrelevant here on purpose - history is what was
    ORDERED, whatever became of it."""
    so = SalesOrder(
        id=str(uuid.uuid4()),
        so_number=f"{MARKER}-HSO-{uuid.uuid4().hex[:8]}",
        status="closed",
        demand_class=demand_class,
        order_date=when,
    )
    db.add(so)
    db.flush()
    db.add(
        SalesOrderLine(
            id=str(uuid.uuid4()),
            sales_order_id=so.id,
            product_id=w.product(key).id,
            qty_ordered=qty,
            qty_delivered=qty,
            line_status="closed",
        )
    )
    db.flush()


def _get(app, supplier_id: str, product_ids: list[str]):
    params = [("supplier_id", supplier_id)] + [("product_ids", p) for p in product_ids]
    return TestClient(app).get(HISTORY_URL, params=params)


def test_history_returns_twelve_zero_filled_buckets_oldest_first(scm_app):
    # AC-B7: a month with no order is a fact about the product. A chart that skips it turns
    # four scattered orders into a solid year.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    _booked(db, w, "A", 40, _bucket(4).replace(day=10), demand_class="project")

    r = _get(app, str(w.supplier.id), [str(w.product("A").id)])

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["from_month"] == _label(_bucket(12))
    assert body["to_month"] == _label(_bucket(1))
    series = body["products"][0]["project"]
    assert [m["month"] for m in series["months"]] == _expected_months()
    assert [m["qty"] for m in series["months"]] == [0] * 8 + [40] + [0] * 3


def test_history_reports_the_peak_month_the_total_and_the_average(scm_app):
    # AC-B6: the peak is the question ("how big does this get in a month"); an average over
    # twelve months hides the one month that decides how much to hold, so both are stated.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    _booked(db, w, "A", 100, _bucket(6).replace(day=3), demand_class="project")
    _booked(db, w, "A", 20, _bucket(6).replace(day=20), demand_class="project")
    _booked(db, w, "A", 60, _bucket(3), demand_class="project")

    r = _get(app, str(w.supplier.id), [str(w.product("A").id)])

    assert r.status_code == 200, r.text
    series = r.json()["products"][0]["project"]
    assert series["peak_month"] == _label(_bucket(6))
    assert series["peak_qty"] == 120
    assert series["total"] == 180
    assert series["avg"] == pytest.approx(15.0)


def test_history_splits_project_from_retail_on_the_orders_own_class(scm_app):
    # Q5, two series everywhere. The split is `sales_orders.demand_class`, the same field the
    # row's Project / Retail columns are counted on, so the history cannot contradict the
    # columns it sits beside.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    _booked(db, w, "A", 90, _bucket(5).replace(day=5), demand_class="project")
    _booked(db, w, "A", 30, _bucket(2).replace(day=5), demand_class="retail")
    _booked(db, w, "A", 7, _bucket(2).replace(day=6), demand_class=None)  # unstated = retail

    r = _get(app, str(w.supplier.id), [str(w.product("A").id)])

    assert r.status_code == 200, r.text
    product = r.json()["products"][0]
    assert product["project"]["total"] == 90
    assert product["project"]["peak_month"] == _label(_bucket(5))
    assert product["retail"]["total"] == 37
    assert product["retail"]["peak_month"] == _label(_bucket(2))


def test_history_ignores_orders_outside_the_twelve_full_months(scm_app):
    # The current, partial month is out too: a half-month bar next to twelve whole ones reads
    # as a collapse in demand every time the page is opened before the 28th.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    _booked(db, w, "A", 500, _bucket(13), demand_class="project")  # one month too old
    _booked(db, w, "A", 400, _bucket(0).replace(day=2), demand_class="project")  # this month
    _booked(db, w, "A", 11, _bucket(12), demand_class="project")  # the first bucket

    r = _get(app, str(w.supplier.id), [str(w.product("A").id)])

    assert r.status_code == 200, r.text
    series = r.json()["products"][0]["project"]
    assert series["total"] == 11
    assert series["months"][0] == {"month": _label(_bucket(12)), "qty": 11}


def test_history_answers_only_for_the_products_asked_about(scm_app):
    # AC-B8: the sidecar is scoped to the page on screen. A product not asked about is not
    # answered, even when the supplier makes it.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    _booked(db, w, "A", 10, _bucket(4), demand_class="project")
    _booked(db, w, "B", 20, _bucket(4), demand_class="project")

    r = _get(app, str(w.supplier.id), [str(w.product("A").id)])

    assert r.status_code == 200, r.text
    ids = [p["product_id"] for p in r.json()["products"]]
    assert ids == [str(w.product("A").id)]


def test_history_answers_a_product_with_no_orders_with_zeros_not_an_absence(scm_app):
    # Every requested product comes back, so the grid cell can say "No orders in 12 months"
    # rather than "Loading" forever.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)

    r = _get(app, str(w.supplier.id), [str(w.product("A").id)])

    assert r.status_code == 200, r.text
    product = r.json()["products"][0]
    assert product["project"]["total"] == 0
    assert product["project"]["peak_month"] is None
    assert product["project"]["peak_qty"] == 0
    assert len(product["retail"]["months"]) == 12


def test_history_with_no_product_ids_is_an_empty_answer_not_the_whole_book(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)

    r = TestClient(app).get(HISTORY_URL, params={"supplier_id": str(w.supplier.id)})

    assert r.status_code == 200, r.text
    assert r.json()["products"] == []


def test_history_for_a_foreign_supplier_is_a_404(scm_app):
    # Same company boundary `build` keeps - a supplier in another company is not found here
    # either, and its products' order history is never quoted back.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)

    r = _get(app, _foreign_supplier(db), [str(w.product("A").id)])

    assert r.status_code == 404, r.text


def test_history_with_a_malformed_supplier_id_is_a_404_not_a_500(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)

    r = _get(app, "not-a-uuid", [str(uuid.uuid4())])

    assert r.status_code == 404, r.text


def test_history_requires_the_read_permission(scm_app):
    app, db, gcu, gcuk = scm_app
    as_user(app, gcu, gcuk, seed_user(db, None))

    r = _get(app, str(uuid.uuid4()), [str(uuid.uuid4())])

    assert r.status_code == 403, r.text


def test_history_does_not_count_another_companys_orders(scm_app):
    # The order book is company-scoped; a raw-SQL reader has to say so by hand.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    _booked(db, w, "A", 25, _bucket(4), demand_class="project")
    other = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO companies (id, name, code, is_active, created_at) "
            "VALUES (:i, :n, :c, true, now())"
        ),
        {"i": other, "n": f"{MARKER} history co", "c": f"{MARKER}-HCO-{other[:8]}"},
    )
    db.execute(
        text("UPDATE sales_orders SET company_id = :co WHERE so_number LIKE :like"),
        {"co": other, "like": f"{MARKER}-HSO-%"},
    )
    db.flush()

    r = _get(app, str(w.supplier.id), [str(w.product("A").id)])

    assert r.status_code == 200, r.text
    assert r.json()["products"][0]["project"]["total"] == 0
