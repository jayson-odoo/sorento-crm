"""Is this demand going to last? Order more, just enough, or less.

> "i want to look at what is my last three months order ... and for projects, let's say I
>  want to look at how what is the last year order for this. Who are the customer and who
>  are the agents selling this? Just give me a judgment that whether this demand is going
>  to sustain or is going to die off."

The judgment is a comparison of OUR OWN order history, two ways at once (user decision
2026-08-10: "both, shown side by side"): the recent window against the window immediately
before it, and against the same window last year. The immediate comparison leads; the
year-ago sits beside it, named absent when history is shorter than a year.

Windows are configuration from day 1 - retail 3 months, project 12, on the planning
policy - never constants buried in the path.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.services.scm.trajectory import (
    MOVEMENT_THRESHOLD_PCT,
    assess_trajectory,
)

MARKER = "ZZTTRJ"
AS_OF = date(2026, 8, 10)


# --------------------------------------------------------------------------- #
# the verdict
# --------------------------------------------------------------------------- #

def test_orders_clearly_up_on_the_window_before_reads_rising():
    a = assess_trajectory(recent=120, previous=90, year_ago=100)

    assert a.verdict == "rising"
    assert a.change_pct == pytest.approx(33.33, abs=0.01)


def test_orders_clearly_down_reads_falling():
    a = assess_trajectory(recent=60, previous=90, year_ago=None)

    assert a.verdict == "falling"
    assert a.change_pct == pytest.approx(-33.33, abs=0.01)


def test_a_small_move_is_holding_not_news():
    a = assess_trajectory(recent=95, previous=90, year_ago=None)

    assert a.verdict == "holding"
    assert abs(a.change_pct) < MOVEMENT_THRESHOLD_PCT


def test_no_recent_orders_after_real_activity_reads_gone_quiet():
    a = assess_trajectory(recent=0, previous=90, year_ago=100)

    assert a.verdict == "quiet"


def test_no_orders_anywhere_is_no_history_not_quiet():
    """Quiet means "it stopped". A product that never sold is a different fact, and calling
    it quiet would imply a heyday that never happened."""
    a = assess_trajectory(recent=0, previous=0, year_ago=None)

    assert a.verdict == "no_history"


def test_orders_starting_from_nothing_reads_rising_without_a_percentage():
    """Percent change off zero is undefined; the direction is still real."""
    a = assess_trajectory(recent=50, previous=0, year_ago=None)

    assert a.verdict == "rising"
    assert a.change_pct is None


def test_the_year_ago_comparison_travels_beside_the_verdict():
    a = assess_trajectory(recent=120, previous=90, year_ago=200)

    assert a.year_change_pct == pytest.approx(-40.0)
    assert a.verdict == "rising", "the immediate comparison leads; year-ago informs"


def test_a_book_younger_than_a_year_names_the_absence():
    a = assess_trajectory(recent=120, previous=90, year_ago=None)

    assert a.year_change_pct is None


# --------------------------------------------------------------------------- #
# read from the book
# --------------------------------------------------------------------------- #

def test_the_run_reads_monthly_series_per_product_and_side(db_world):
    from app.services.scm.trajectory_service import trajectory_for_run

    out = trajectory_for_run(db_world["db"], db_world["run_id"], as_of=AS_OF)
    entry = out["series"].get(f"{db_world['product_id']}:project")

    assert entry is not None
    # 40 units two months ago + 60 one month ago inside the 12-month project window
    assert entry["recent_qty"] == 100
    assert entry["verdict"] in ("rising", "holding", "falling", "quiet", "no_history")
    months = {m["month"]: m["qty"] for m in entry["months"]}
    assert months.get("2026-06") == 40
    assert months.get("2026-07") == 60


def test_the_popup_names_who_bought_it(db_world):
    from app.services.scm.trajectory_service import trajectory_for_run

    out = trajectory_for_run(db_world["db"], db_world["run_id"], as_of=AS_OF)
    entry = out["series"][f"{db_world['product_id']}:project"]

    assert any(c["customer_name"] == f"{MARKER} Vivo Homes" for c in entry["customers"])


def test_the_windows_come_from_the_policy_not_a_constant(db_world):
    from app.services.scm.trajectory_service import trajectory_for_run

    out = trajectory_for_run(db_world["db"], db_world["run_id"], as_of=AS_OF)

    assert out["windows"]["retail_months"] >= 1
    assert out["windows"]["project_months"] >= 1


@pytest.fixture()
def db_world():
    """One product at a project warehouse, orders in the last two months, a run naming it."""
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from tests._pg_fixture import pg_session, unique_code

    def _u() -> str:
        return str(uuid.uuid4())

    with pg_session() as db:
        cat = ProductCategory(id=_u(), category_code=unique_code(MARKER),
                              category_name=f"{MARKER} cat")
        uom = UnitOfMeasure(id=_u(), uom_code=unique_code("U")[:20], uom_name=f"{MARKER} u")
        db.add_all([cat, uom])
        db.flush()
        product = Product(id=_u(), product_code=unique_code("P"), product_name=f"{MARKER} p",
                          category_id=cat.id, base_uom_id=uom.id, list_price=0,
                          is_active=True, is_discontinued=False)
        db.add(product)
        db.flush()

        wid = _u()
        db.execute(text(
            "INSERT INTO warehouses (id, warehouse_code, warehouse_name, counts_as_available, "
            "segment) VALUES (:id, :c, :c, true, 'project')"), {"id": wid, "c": unique_code("W")[:20]})

        cust_id = _u()
        db.execute(text(
            "INSERT INTO customers (id, customer_code, customer_name) VALUES (:id, :c, :n)"),
            {"id": cust_id, "c": unique_code("C")[:20], "n": f"{MARKER} Vivo Homes"})

        def order(day: date, qty: float):
            oid = _u()
            db.execute(text(
                "INSERT INTO sales_orders (id, so_number, status, order_date, customer_id) "
                "VALUES (:id, :n, 'closed', :d, :cu)"),
                {"id": oid, "n": f"{MARKER}-{oid[:8]}", "d": day, "cu": cust_id})
            db.execute(text(
                "INSERT INTO sales_order_lines (id, sales_order_id, product_id, warehouse_id, "
                "qty_ordered, qty_delivered, line_status) VALUES (:id, :so, :p, :w, :q, :q, 'closed')"),
                {"id": _u(), "so": oid, "p": product.id, "w": wid, "q": qty})

        order(date(2026, 6, 5), 40)
        order(date(2026, 7, 12), 60)
        db.flush()

        run_id = _u()
        db.execute(text(
            "INSERT INTO scm.reorder_run (id, status, created_at) "
            "VALUES (:id, 'completed', now())"), {"id": run_id})
        db.execute(text(
            "INSERT INTO scm.reorder_recommendation "
            "(id, run_id, product_id, warehouse_id, rec_type, rounded_qty) "
            "VALUES (:id, :r, :p, :w, 'buy', 10)"),
            {"id": _u(), "r": run_id, "p": product.id, "w": wid})
        db.flush()

        yield {"db": db, "run_id": run_id, "product_id": str(product.id)}
