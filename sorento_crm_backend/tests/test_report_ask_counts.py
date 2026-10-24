"""REPORT-SMART-1021 step 3: count measures on `GET /api/v1/order-management/report-ask`.

Real ask (dev chat, masked): "how many dealers do we have selling this product" was answered
with monthly totals. The report engine already counts distinct values (`registry.Column.agg
= "count_distinct"`); the sales ask datasets now carry three count measures: `customers`,
`orders`, `products`, each counting only lines with a figure on the basis asked.

Postgres only, every row seeded here. One SO per `_sale` (one line, fully delivered).

    cust  agent  product  qty / RM
    C1    A1     P1       10 / 1000
    C2    A1     P1        5 /  500
    C1    A2     P1        2 /  200
    C3    A2     P2        4 /  400
    C3    A3     P2        1 /  100
    C2    A3     P1        3 /  300   (August, outside the window)
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._pg_fixture import unique_code
from tests._sales_report_do_seed import (  # noqa: F401  (client / db are fixtures)
    client,
    db,
    seed_agent,
    seed_customer,
    warehouse,
)
from tests.test_report_ask_route import AUG, _full, _ok, _prod, _sale


def _world(db):
    w = SimpleNamespace()
    w.c1, w.c2, w.c3 = (seed_customer(db, name=unique_code(f"Cnt{n}")) for n in "123")
    w.wh = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("WH"))
    w.p1, w.p2 = _prod(db, "ZZTCNT-1"), _prod(db, "ZZTCNT-2")
    w.a1, w.a2, w.a3 = (seed_agent(db, code=f"ZZT-CNT-{n}") for n in "123")
    _sale(db, cust=w.c1, wh=w.wh, agent=w.a1, prod=w.p1, qty=10, total="1000.00")
    _sale(db, cust=w.c2, wh=w.wh, agent=w.a1, prod=w.p1, qty=5, total="500.00")
    _sale(db, cust=w.c1, wh=w.wh, agent=w.a2, prod=w.p1, qty=2, total="200.00")
    _sale(db, cust=w.c3, wh=w.wh, agent=w.a2, prod=w.p2, qty=4, total="400.00")
    _sale(db, cust=w.c3, wh=w.wh, agent=w.a3, prod=w.p2, qty=1, total="100.00")
    _sale(db, cust=w.c2, wh=w.wh, agent=w.a3, prod=w.p1, qty=3, total="300.00", when=AUG)
    db.commit()
    return w


def test_how_many_customers_buy_a_product_is_one_count(client, db):
    _world(db)
    body = _ok(client, _full(db), measure="customers", product_code="ZZTCNT-1")
    assert body["measure"] == "customers", body
    assert body["total"]["count"] == 2, body["total"]  # C1 twice is one customer; C2 in August is out
    assert body["total"]["qty"] == 17, body["total"]


def test_customers_per_agent_ranks_by_the_count(client, db):
    _world(db)
    body = _ok(client, _full(db), measure="customers", group_by="sales_agent", top_n=10, product_code="ZZTCNT")
    names = [(r["name"], r["count"]) for r in body["rows"]]
    # A1 C1+C2 = 2 (RM 1500), A2 C1+C3 = 2 (RM 600), A3 C3 = 1: ties break by amount.
    assert names == [("ZZT-CNT-1", 2), ("ZZT-CNT-2", 2), ("ZZT-CNT-3", 1)], body["rows"]
    # The whole set's count is distinct over everything, never the rows summed (5).
    assert body["total"]["count"] == 3, body["total"]


def test_orders_and_products_count_too(client, db):
    w = _world(db)
    contact = _full(db)
    orders = _ok(client, contact, measure="orders", customer_ids=[w.c1.id])
    assert orders["total"]["count"] == 2, orders
    products = _ok(client, contact, measure="products", group_by="customer", top_n=5, product_code="ZZTCNT")
    assert products["total"]["count"] == 2, products
    assert all(r["count"] == 1 for r in products["rows"]), products["rows"]


def test_a_sum_measure_carries_no_count(client, db):
    _world(db)
    body = _ok(client, _full(db), group_by="sales_agent", top_n=10, product_code="ZZTCNT")
    assert body["total"].get("count") is None and all(r.get("count") is None for r in body["rows"]), body


def test_an_unknown_measure_is_still_refused(client, db):
    from tests.test_report_ask_route import _ask

    resp = _ask(client, _full(db), measure="dealers")
    assert resp.status_code == 422 and resp.json().get("code") == "unknown_measure", resp.text


def test_the_count_window_is_the_period(client, db):
    _world(db)
    body = _ok(client, _full(db), measure="customers", product_code="ZZTCNT-1",
               date_from=date(2026, 8, 1).isoformat(), date_to=date(2026, 8, 31).isoformat())
    assert body["total"]["count"] == 1, body["total"]


def test_a_line_with_no_figure_on_the_basis_is_not_counted(client, db):
    """Review S2: an ordered line nothing was delivered on counts as ordered, never as delivered."""
    from tests._report_ask_so_seed import seed_so_line

    w = _world(db)
    c4 = seed_customer(db, name=unique_code("Cnt4"))
    seed_so_line(db, cust=c4, prod=w.p1, qty=7, total="700.00", agent=w.a1, wh=w.wh, order_date=date(2026, 9, 10), delivered=0)
    db.commit()
    contact = _full(db)
    delivered = _ok(client, contact, measure="customers", product_code="ZZTCNT-1")
    ordered = _ok(client, contact, measure="customers", product_code="ZZTCNT-1", basis="ordered")
    assert delivered["total"]["count"] == 2 and ordered["total"]["count"] == 3, (delivered, ordered)
    per_agent = _ok(client, contact, measure="customers", group_by="sales_agent", top_n=5, product_code="ZZTCNT-1")
    assert {r["name"]: r["count"] for r in per_agent["rows"]}["ZZT-CNT-1"] == 2, per_agent["rows"]
