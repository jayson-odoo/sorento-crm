"""REPORT-OUTSTANDING-SUMMARY (29 Oct 2026): the outstanding SUMMARY on `GET /order-management/report-ask`.

`documentation/plans/reports/report-outstanding-summary-behaviour-card.md`. #1922 left an outstanding kind with one
total; the pre-#1922 tool printed counts, the quantity lines, the date range, By location and By customer (or By
product). The route now adds a `summary` block, every figure from the same engine run (`reports.ask.run_ask`), when
the basis is undelivered orders or pending delivery, nothing is grouped or compared, and a product or customer is
named (the old tool's subjects; R13: a product gets By customer, a customer gets By product, both get neither).

Postgres only; every row is seeded here.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._pg_fixture import unique_code
from tests._report_ask_so_seed import seed_so_line
from tests._report_unify_seed import make_product
from tests._sales_report_do_seed import (  # noqa: F401  (client / db are fixtures)
    client,
    db,
    money,
    seed_customer,
    warehouse,
)
from tests.test_report_unify_outstanding_bases import _ok, _pending_world, _staff

D = Decimal


def _rows(rows):
    return [(r["name"], r["qty"], money(r["amount"])) for r in rows]


# ================================================================ pending delivery (the prod turn's kind)


def test_pending_delivery_for_a_product_carries_the_summary_with_by_location_and_by_customer(client, db):
    """pC, every date: DO1 (C1, Sep, W2 2 / 200) and DO4 (C1, Aug, W2 1 / 100); the delivered DO3 is pA only."""
    w = _pending_world(db)
    body = _ok(client, _staff(db), basis="pending_delivery", product_ids=[w.pc.id], period=None)
    s = body["summary"]
    assert s["documents"] == 2, s
    assert (s["qty"], money(s["amount"])) == (3, D("300.00")), s
    assert (s["date_first"], s["date_last"]) == ("2026-08-15", "2026-09-10"), s
    assert _rows(s["by_location"]) == [(w.w2.warehouse_code, 3, D("300.00"))], s
    assert s["second"] == "customer", s
    assert _rows(s["by_second"]) == [(w.c1.customer_name, 3, D("300.00"))], s
    # The summary is the total's own population.
    assert (body["total"]["qty"], money(body["total"]["amount"])) == (s["qty"], money(s["amount"]))


def test_pending_delivery_for_a_customer_breaks_down_by_product(client, db):
    """C1, every date: DO1 (pA W1 3, pC W2 2), DO4 (pC W2 1). The delivered DO3 is in nothing."""
    w = _pending_world(db)
    body = _ok(client, _staff(db), basis="pending_delivery", customer_ids=[w.c1.id], period=None)
    s = body["summary"]
    assert s["documents"] == 2, s
    assert (s["qty"], money(s["amount"])) == (6, D("600.00")), s
    assert sorted(_rows(s["by_location"])) == sorted(
        [(w.w1.warehouse_code, 3, D("300.00")), (w.w2.warehouse_code, 3, D("300.00"))]
    ), s
    assert s["second"] == "product", s
    assert sorted(_rows(s["by_second"])) == sorted(
        [(w.pa.product_code, 3, D("300.00")), (w.pc.product_code, 3, D("300.00"))]
    ), s


def test_pending_delivery_naming_product_and_customer_has_by_location_only(client, db):
    w = _pending_world(db)
    body = _ok(
        client, _staff(db), basis="pending_delivery", product_ids=[w.pc.id], customer_ids=[w.c1.id], period=None
    )
    s = body["summary"]
    assert s["second"] is None and s["by_second"] == [], s
    assert _rows(s["by_location"]) == [(w.w2.warehouse_code, 3, D("300.00"))], s


def test_a_period_narrows_the_summary_like_the_total(client, db):
    """September only: pC is DO1 alone."""
    w = _pending_world(db)
    body = _ok(client, _staff(db), basis="pending_delivery", product_ids=[w.pc.id])
    s = body["summary"]
    assert (s["documents"], s["qty"], s["date_first"], s["date_last"]) == (1, 2, "2026-09-10", "2026-09-10"), s


# ================================================================ undelivered orders


def test_undelivered_orders_for_a_customer_carry_ordered_and_the_open_lines_only(client, db):
    """Two open lines (10 ordered / 4 delivered, 5 / 0) and one fully delivered line (8 / 8): the delivered line is in
    no figure, so Ordered 15, Outstanding 11, Transferred (15 - 11) 4. Dated by the SO's own order date."""
    cust = seed_customer(db, name=unique_code("Cust"))
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("WS"))
    p1, p2, p3 = (make_product(db, unique_code(s)) for s in ("S1", "S2", "S3"))
    seed_so_line(db, cust=cust, prod=p1, qty=10, delivered=4, total="1000.00", wh=wh, order_date=date(2026, 8, 5))
    seed_so_line(db, cust=cust, prod=p2, qty=5, delivered=0, total="500.00", wh=wh, order_date=date(2026, 9, 20))
    seed_so_line(db, cust=cust, prod=p3, qty=8, delivered=8, total="800.00", wh=wh, order_date=date(2025, 1, 1))
    db.commit()
    body = _ok(client, _staff(db), basis="outstanding", customer_ids=[cust.id], period=None)
    s = body["summary"]
    assert s["documents"] == 2, s
    assert (s["ordered_qty"], s["qty"], money(s["amount"])) == (15, 11, D("1100.00")), s
    assert (s["date_first"], s["date_last"]) == ("2026-08-05", "2026-09-20"), s
    assert [(r["name"], r["ordered_qty"], r["qty"]) for r in s["by_location"]] == [(wh.warehouse_code, 15, 11)], s
    assert s["second"] == "product", s
    assert [(r["name"], r["ordered_qty"], r["qty"]) for r in s["by_second"]] == [
        (p1.product_code, 10, 6), (p2.product_code, 5, 5)
    ], s


# ================================================================ no summary


def test_no_subject_no_summary(client, db):
    _pending_world(db)
    body = _ok(client, _staff(db), basis="pending_delivery", period=None)
    assert body.get("summary") is None, body


def test_a_brand_alone_is_a_filter_not_a_subject(client, db):
    w = _pending_world(db)
    body = _ok(client, _staff(db), basis="pending_delivery", brand_ids=[w.brand_b.id], period=None)
    assert body.get("summary") is None, body


def test_a_breakdown_carries_no_summary(client, db):
    w = _pending_world(db)
    body = _ok(
        client, _staff(db), basis="pending_delivery", product_ids=[w.pc.id], group_by="customer", top_n=10, period=None
    )
    assert body.get("summary") is None, body


def test_a_sales_basis_carries_no_summary(client, db):
    w = _pending_world(db)
    body = _ok(client, _staff(db), basis="ordered", product_ids=[w.pc.id])
    assert body.get("summary") is None, body


# ================================================================ the delivery order list (the offer's target)


def test_pending_delivery_groups_by_delivery_order(client, db):
    """The list the "Reply 1 for the delivery order list." offer runs: the held ask grouped by delivery order."""
    w = _pending_world(db)
    body = _ok(
        client, _staff(db), basis="pending_delivery", product_ids=[w.pc.id], group_by="delivery_order", top_n=50,
        period=None,
    )
    assert body["group_by"] == "delivery_order", body
    assert len(body["rows"]) == 2 and sum(r["qty"] for r in body["rows"]) == 3, body["rows"]
