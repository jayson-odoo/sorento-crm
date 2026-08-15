"""The orders behind one Who-bought-it row, over HTTP.

> "sells RM 0.94?"

The trend popover names who bought the product and how much. This endpoint serves the
evidence under one of those names, so the price question is answered on the row rather
than in another system. `customer_key` carries the same three cases the label falls back
through - a customer id, `debtor:<code>`, or `none` - so every row of the trend can be
opened, not only the named ones.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.scm.conftest import SORENTO_COMPANY_ID, as_user, requires_pg, seed_user

pytestmark = requires_pg

MARKER = "ZZTCOR"


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


def _world(db):
    """One product on a project warehouse, three orders, and a run naming it.

    Seeded whole, never borrowed: CI's database is empty, and a `LIMIT 1` off `products`
    is how a suite passes locally and dies there.
    """
    from app.models.order import Customer
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    cat = ProductCategory(id=_u(), category_code=_code("CAT"),
                          category_name=f"{MARKER} category")
    uom = UnitOfMeasure(id=_u(), uom_code=_code("U")[:20], uom_name=f"{MARKER} unit")
    db.add_all([cat, uom])
    db.flush()
    product = Product(id=_u(), product_code=_code("P"), product_name=f"{MARKER} product",
                      category_id=cat.id, base_uom_id=uom.id, list_price=0,
                      is_active=True, is_discontinued=False)
    # A second product with its own orders, on NO plan row of this run. The endpoint is
    # reached from a run, so a run this user may see must not become a key to the order
    # book for products that run never planned.
    offplan = Product(id=_u(), product_code=_code("PX"), product_name=f"{MARKER} off-plan",
                      category_id=cat.id, base_uom_id=uom.id, list_price=0,
                      is_active=True, is_discontinued=False)
    customer = Customer(id=_u(), customer_code=_code("C")[:20],
                        customer_name=f"{MARKER} Vivo Homes", is_active=True)
    db.add_all([product, offplan, customer])
    db.flush()
    pid, cust = str(product.id), str(customer.id)

    wid = _u()
    db.execute(text(
        "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, "
        "counts_as_available, segment, created_at, updated_at) "
        "VALUES (:i, :c, :c, true, true, 'project', now(), now())"),
        {"i": wid, "c": _code("W")[:20]})

    def order(day, qty, price, *, customer=None, debtor=None, product=None):
        oid = _u()
        number = f"{MARKER}-{oid[:8]}"
        db.execute(text(
            "INSERT INTO sales_orders (id, so_number, status, order_date, customer_id, "
            "debtor_code, created_at, updated_at) "
            "VALUES (:i, :n, 'closed', :d, :cu, :dc, now(), now())"),
            {"i": oid, "n": number, "d": day, "cu": customer, "dc": debtor})
        db.execute(text(
            "INSERT INTO sales_order_lines (id, sales_order_id, product_id, warehouse_id, "
            "qty_ordered, qty_delivered, unit_price, line_status, created_at, updated_at) "
            "VALUES (:i, :so, :p, :w, :q, :q, :up, 'closed', now(), now())"),
            {"i": _u(), "so": oid, "p": product or pid, "w": wid, "q": qty, "up": price})
        return number

    # LAST month: the trajectory window deliberately excludes the month the run sits in
    # (a partial month compared against whole ones reads as demand falling every time), so
    # an order dated today would be outside the window this endpoint shares with it.
    when = date.today().replace(day=1) - timedelta(days=15)
    debtor_code = _code("D")[:20]
    named = order(when, 60, 0.94, customer=cust)
    by_debtor = order(when, 5, 1.10, debtor=debtor_code)
    anonymous = order(when, 3, None)
    order(when, 11, 7.50, customer=cust, product=str(offplan.id))

    run_id = _u()
    # The run states its company explicitly: `assert_run_visible` filters on it, and the
    # column carries no default, so a run seeded without one is invisible to its own test.
    db.execute(text(
        "INSERT INTO scm.reorder_run (id, status, include_market, company_id, created_at) "
        "VALUES (:i, 'completed', false, :co, now())"),
        {"i": run_id, "co": SORENTO_COMPANY_ID})
    db.execute(text(
        "INSERT INTO scm.reorder_recommendation "
        "(id, run_id, product_id, warehouse_id, rec_type, rounded_qty, status) "
        "VALUES (:i, :r, :p, :w, 'buy', 10, 'proposed')"),
        {"i": _u(), "r": run_id, "p": pid, "w": wid})
    db.flush()
    return {"run_id": run_id, "product_id": pid, "off_plan_product_id": str(offplan.id),
            "customer_id": cust,
            "debtor_code": debtor_code, "named": named, "by_debtor": by_debtor,
            "anonymous": anonymous}


def _client(scm_app, role_slug):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return app, db


def _url(world, key: str) -> str:
    return (f"/api/v1/scm/reorder-runs/{world['run_id']}/customer-orders"
            f"?product_id={world['product_id']}&segment=project&customer_key={key}")


def test_it_serves_the_orders_behind_a_named_customer(scm_app):
    app, db = _client(scm_app, "purchasing")
    world = _world(db)

    with TestClient(app) as c:
        res = c.get(_url(world, world["customer_id"]))

    assert res.status_code == 200, res.text
    body = res.json()
    assert [l["so_number"] for l in body["lines"]] == [world["named"]]
    assert body["lines"][0]["unit_price"] == 0.94
    assert body["total"] == 1 and body["shown"] == 1


def test_it_serves_the_orders_behind_a_bare_debtor_code(scm_app):
    """The 2,546-order case: no customer row, a code on the face of the document."""
    app, db = _client(scm_app, "purchasing")
    world = _world(db)

    with TestClient(app) as c:
        res = c.get(_url(world, f"debtor:{world['debtor_code']}"))

    assert res.status_code == 200, res.text
    assert [l["so_number"] for l in res.json()["lines"]] == [world["by_debtor"]]


def test_it_serves_the_orders_that_name_nobody(scm_app):
    app, db = _client(scm_app, "purchasing")
    world = _world(db)

    with TestClient(app) as c:
        res = c.get(_url(world, "none"))

    assert res.status_code == 200, res.text
    body = res.json()
    assert [l["so_number"] for l in body["lines"]] == [world["anonymous"]]
    assert body["lines"][0]["unit_price"] is None


def test_an_unknown_segment_is_rejected_rather_than_answered_empty(scm_app):
    """An empty list would read as "this customer bought nothing", which is a lie."""
    app, db = _client(scm_app, "purchasing")
    world = _world(db)

    with TestClient(app) as c:
        res = c.get(
            f"/api/v1/scm/reorder-runs/{world['run_id']}/customer-orders"
            f"?product_id={world['product_id']}&segment=wholesale"
            f"&customer_key={world['customer_id']}"
        )

    assert res.status_code == 422, res.text


def test_a_missing_customer_key_is_a_bad_request(scm_app):
    app, db = _client(scm_app, "purchasing")
    world = _world(db)

    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/reorder-runs/{world['run_id']}/customer-orders"
                    f"?product_id={world['product_id']}&segment=project")

    assert res.status_code == 422, res.text


def test_a_product_this_run_never_planned_is_not_readable_through_it(scm_app):
    """Run visibility is not a key to the whole order book.

    The drill is opened from a row of THIS run, and the trend it drills from is built from
    the run's own (product, side) pairs. Gating on the run alone let a caller name any
    product in the query string and read its orders through a run that never planned it.
    """
    app, db = _client(scm_app, "purchasing")
    world = _world(db)

    with TestClient(app) as c:
        res = c.get(
            f"/api/v1/scm/reorder-runs/{world['run_id']}/customer-orders"
            f"?product_id={world['off_plan_product_id']}&segment=project"
            f"&customer_key={world['customer_id']}"
        )

    assert res.status_code == 404, res.text


def test_the_side_has_to_be_the_side_the_run_planned_the_product_on(scm_app):
    """The pair is (product, side), not a product with a free-text side beside it.

    The product sits on a project warehouse in this run, so asking for its dealer side is
    asking about a row that does not exist - and an empty list there would read as "nobody
    bought this on that side", which is a different and untrue statement.
    """
    app, db = _client(scm_app, "purchasing")
    world = _world(db)

    with TestClient(app) as c:
        res = c.get(
            f"/api/v1/scm/reorder-runs/{world['run_id']}/customer-orders"
            f"?product_id={world['product_id']}&segment=dealer"
            f"&customer_key={world['customer_id']}"
        )

    assert res.status_code == 404, res.text


def test_denied_without_dashboard_view(scm_app):
    """Auth: the drill is part of the read-only plan screen (scm.dashboard.view)."""
    app, _ = _client(scm_app, None)

    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/reorder-runs/{uuid.uuid4()}/customer-orders"
                    f"?product_id={uuid.uuid4()}&segment=project&customer_key=none")

    assert res.status_code == 403
