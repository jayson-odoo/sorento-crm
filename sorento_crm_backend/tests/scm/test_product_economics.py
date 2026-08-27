"""Product economics: what the item really sells for, and how fast it moves.

What is pinned: the selling price is quantity-weighted off REAL order lines (discounts
included via line totals), list price only stands in when nothing sold and says so, a
zero list price reads as "no selling price" rather than a price of zero, and turnover
months divide stock by pace - with "nothing moves" reported as no_movement, never as a
number.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.services.scm import product_economics_service as svc
from tests.scm.conftest import requires_pg

pytestmark = requires_pg

MARKER = "ZZTECO"
AS_OF = date(2026, 8, 10)


def _u() -> str:
    return str(uuid.uuid4())


def _world(db, *, sold_lines=((10, 100.0), (30, 80.0)), list_price=250.0,
           on_hand=120.0):
    """One product on a run: `sold_lines` = (qty, unit_price) order lines this year."""
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from tests._pg_fixture import unique_code

    cat = ProductCategory(id=_u(), category_code=unique_code(MARKER),
                          category_name=f"{MARKER} cat")
    uom = UnitOfMeasure(id=_u(), uom_code=unique_code("U")[:20], uom_name=f"{MARKER} u")
    db.add_all([cat, uom])
    db.flush()
    product = Product(id=_u(), product_code=unique_code("P"), product_name=f"{MARKER} p",
                      category_id=cat.id, base_uom_id=uom.id, list_price=list_price,
                      is_active=True, is_discontinued=False)
    db.add(product)
    db.flush()
    pid = str(product.id)

    wid = _u()
    db.execute(text(
        "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, "
        "counts_as_available) VALUES (:id, :c, :c, true, true)"),
        {"id": wid, "c": unique_code("W")[:20]})

    for i, (qty, unit_price) in enumerate(sold_lines):
        oid = _u()
        # kpi_warning/subtotal_amount/discount_amount/tax_amount/total_amount/
        # synced_to_excel are NOT NULL with only a Python-side ORM default.
        db.execute(text(
            "INSERT INTO orders (id, order_number, order_date, is_cancelled, kpi_warning, "
            "subtotal_amount, discount_amount, tax_amount, total_amount, synced_to_excel, "
            "created_at, updated_at) "
            "VALUES (:id, :n, :d, false, false, 0, 0, 0, 0, false, now(), now())"),
            {"id": oid, "n": f"{MARKER}-{oid[:8]}", "d": date(2026, 3 + i, 10)})
        db.execute(text(
            "INSERT INTO order_lines (id, line_sequence, order_id, product_id, "
            "warehouse_id, quantity, unit_price, total_excluding_tax, created_at, "
            "updated_at) VALUES (:id, 1, :o, :p, :w, :q, :up, :tot, now(), now())"),
            {"id": _u(), "o": oid, "p": pid, "w": wid, "q": qty, "up": unit_price,
             "tot": qty * unit_price})

    if on_hand:
        db.execute(text(
            "INSERT INTO stock (id, product_id, warehouse_id, quantity_on_hand, "
            "synced_to_excel) VALUES (:id, :p, :w, :q, false)"),
            {"id": _u(), "p": pid, "w": wid, "q": on_hand})

    run_id = _u()
    db.execute(text(
        "INSERT INTO scm.reorder_run (id, status, include_market, created_at) "
        "VALUES (:id, 'completed', false, now())"), {"id": run_id})
    db.execute(text(
        "INSERT INTO scm.reorder_recommendation "
        "(id, run_id, product_id, warehouse_id, rec_type, rounded_qty, status) "
        "VALUES (:id, :r, :p, :w, 'buy', 10, 'proposed')"),
        {"id": _u(), "r": run_id, "p": pid, "w": wid})
    db.flush()
    return {"run_id": run_id, "product_id": pid, "warehouse_id": wid}


def test_selling_price_is_quantity_weighted_off_real_order_lines():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        w = _world(db)  # 10 @ 100 + 30 @ 80 = 3400 over 40 units
        out = svc.economics_for_run(db, w["run_id"], as_of=AS_OF)
        e = out["products"][w["product_id"]]

        assert e["avg_sell_price"] == 85.0
        assert e["sell_source"] == "orders"
        assert e["sold_qty"] == 40.0


def test_list_price_stands_in_only_when_nothing_sold_and_says_so():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        w = _world(db, sold_lines=())
        e = svc.economics_for_run(db, w["run_id"], as_of=AS_OF)["products"][w["product_id"]]

        assert e["avg_sell_price"] == 250.0
        assert e["sell_source"] == "list_price"


def test_a_zero_list_price_is_no_selling_price_not_a_price_of_zero():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        w = _world(db, sold_lines=(), list_price=0)
        e = svc.economics_for_run(db, w["run_id"], as_of=AS_OF)["products"][w["product_id"]]

        assert e["avg_sell_price"] is None
        assert e["sell_source"] is None


def test_turnover_is_months_of_stock_at_the_current_pace():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        # 40 units left over the 12-month window -> 3.333/month; 120 held -> 36 months.
        w = _world(db)
        e = svc.economics_for_run(db, w["run_id"], as_of=AS_OF)["products"][w["product_id"]]

        assert e["on_hand"] == 120.0
        assert e["avg_monthly_out"] == pytest.approx(3.3333, abs=0.001)
        assert e["turnover_months"] == pytest.approx(36.0, abs=0.1)
        assert e["no_movement"] is False


def test_no_movement_is_said_not_divided():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        w = _world(db, sold_lines=())
        e = svc.economics_for_run(db, w["run_id"], as_of=AS_OF)["products"][w["product_id"]]

        assert e["turnover_months"] is None
        assert e["no_movement"] is True


def test_lifecycle_decision_records_overwrites_and_withdraws():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        w = _world(db)
        pid = w["product_id"]

        svc.record_lifecycle_decision(db, product_id=pid, decision="discontinue",
                                      decided_by=None)
        e = svc.economics_for_run(db, w["run_id"], as_of=AS_OF)["products"][pid]
        assert e["lifecycle_decision"] == "discontinue"
        assert e["lifecycle_decided_at"] is not None

        # A change of mind overwrites - the decision is the current answer, not a history.
        svc.record_lifecycle_decision(db, product_id=pid, decision="keep", decided_by=None)
        e = svc.economics_for_run(db, w["run_id"], as_of=AS_OF)["products"][pid]
        assert e["lifecycle_decision"] == "keep"

        # Null withdraws, back to undecided.
        svc.record_lifecycle_decision(db, product_id=pid, decision=None, decided_by=None)
        e = svc.economics_for_run(db, w["run_id"], as_of=AS_OF)["products"][pid]
        assert e["lifecycle_decision"] is None


def test_lifecycle_decision_rejects_unknown_words_and_products():
    import pytest as _pytest
    from app.services.error_handler import AppException
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        w = _world(db)
        with _pytest.raises(AppException):
            svc.record_lifecycle_decision(db, product_id=w["product_id"],
                                          decision="pause", decided_by=None)
        with _pytest.raises(AppException):
            svc.record_lifecycle_decision(db, product_id=_u(), decision="keep",
                                          decided_by=None)


def test_thresholds_default_and_travel_with_the_payload():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        w = _world(db)
        # The local DB is a prod copy whose global policy row may carry values; NULL them
        # inside this rolled-back transaction so the assertion tests the DEFAULTS, not
        # whatever the environment happens to hold (CI has no policy row at all).
        db.execute(text(
            "UPDATE scm.reorder_policy SET margin_floor_pct = NULL, "
            "dead_turnover_months = NULL WHERE scope_type = 'global'"))
        out = svc.economics_for_run(db, w["run_id"], as_of=AS_OF)

        assert out["thresholds"]["margin_floor_pct"] == 15.0
        assert out["thresholds"]["dead_turnover_months"] == 6.0
        assert out["sell_window_months"] == 12


def test_on_hand_counts_the_site_pool_only_never_a_project_bin():
    """R16 (captain, 28 Aug): "On hand" in reorder planning is the site POOL.

    A project bin's stock is already spoken for by an Order Inquiry, so counting it in the
    product-health figure told a buyer they were holding 154 when the pool held 120 - and
    that number is what the discontinue advice and the turnover months are read off.
    """
    from tests._pg_fixture import pg_session, unique_code
    with pg_session() as db:
        w = _world(db)  # 120 on hand at a warehouse with no segment (a pool)
        bin_id = _u()
        db.execute(text(
            "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, "
            "counts_as_available, segment) VALUES (:id, :c, :c, true, true, 'project')"),
            {"id": bin_id, "c": unique_code("WB")[:20]})
        db.execute(text(
            "INSERT INTO stock (id, product_id, warehouse_id, quantity_on_hand, "
            "synced_to_excel) VALUES (:id, :p, :w, 34, false)"),
            {"id": _u(), "p": w["product_id"], "w": bin_id})
        db.flush()

        e = svc.economics_for_run(db, w["run_id"], as_of=AS_OF)["products"][w["product_id"]]

        assert e["on_hand"] == 120.0, "the 34 in the project bin are not the pool's"
