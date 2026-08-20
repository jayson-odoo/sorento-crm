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
    # 40 units two months ago, then 60 + 5 + 3 one month ago, inside the 12-month project
    # window. The last two are the unattributed orders the fixture also carries (one with
    # only a debtor code, one naming nobody): they are demand like any other and count.
    assert entry["recent_qty"] == 108
    assert entry["verdict"] in ("rising", "holding", "falling", "quiet", "no_history")
    months = {m["month"]: m["qty"] for m in entry["months"]}
    assert months.get("2026-06") == 40
    assert months.get("2026-07") == 68


def test_the_popup_names_who_bought_it(db_world):
    from app.services.scm.trajectory_service import trajectory_for_run

    out = trajectory_for_run(db_world["db"], db_world["run_id"], as_of=AS_OF)
    entry = out["series"][f"{db_world['product_id']}:project"]

    assert any(c["customer_name"] == f"{MARKER} Vivo Homes" for c in entry["customers"])


def test_who_bought_it_carries_the_date_of_their_last_order(db_world):
    """The FE renders "Who bought it" as a table (Customer | Qty | Last order date), so
    each customer needs the MOST RECENT of their orders inside the studied window, not
    just the total quantity."""
    from app.services.scm.trajectory_service import trajectory_for_run

    out = trajectory_for_run(db_world["db"], db_world["run_id"], as_of=AS_OF)
    entry = out["series"][f"{db_world['product_id']}:project"]

    customer = next(c for c in entry["customers"] if c["customer_name"] == f"{MARKER} Vivo Homes")
    # Two orders on record for this customer: 2026-06-05 and 2026-07-12. The later one wins.
    assert customer["last_order_date"] == "2026-07-12"


def test_an_order_with_no_customer_is_named_by_its_debtor_code(db_world):
    """AC-4.3: "Unnamed customer" hid an attribution that was sitting on the document.

    2,546 of the 2,548 orders the outstanding book created had no `customer_id` and a
    debtor code on the face of the order. `Debtor 300-R009` is a name the buyer can act on.
    """
    from app.services.scm.trajectory_service import trajectory_for_run

    out = trajectory_for_run(db_world["db"], db_world["run_id"], as_of=AS_OF)
    entry = out["series"][f"{db_world['product_id']}:project"]
    names = {c["customer_name"] for c in entry["customers"]}

    assert f"Debtor {db_world['debtor_code']}" in names
    assert "Unnamed customer" not in names


def test_an_order_naming_nobody_at_all_says_so(db_world):
    """The honest end of the fallback: a fact about the order, not missing data."""
    from app.services.scm.trajectory_service import trajectory_for_run

    out = trajectory_for_run(db_world["db"], db_world["run_id"], as_of=AS_OF)
    entry = out["series"][f"{db_world['product_id']}:project"]

    assert "No customer on order" in {c["customer_name"] for c in entry["customers"]}


def test_every_customer_row_carries_the_key_its_orders_are_drilled_by(db_world):
    """A row the reader can see has to be a row the reader can open (AC-4.1)."""
    from app.services.scm.trajectory_service import trajectory_for_run

    out = trajectory_for_run(db_world["db"], db_world["run_id"], as_of=AS_OF)
    entry = out["series"][f"{db_world['product_id']}:project"]
    keys = {c["customer_name"]: c["customer_key"] for c in entry["customers"]}

    assert keys[f"{MARKER} Vivo Homes"] == db_world["customer_id"]
    assert keys[f"Debtor {db_world['debtor_code']}"] == f"debtor:{db_world['debtor_code']}"
    assert keys["No customer on order"] == "none"


# --------------------------------------------------------------------------- #
# the orders behind one of those customers (AC-4.1)
# --------------------------------------------------------------------------- #

def _orders(db_world, customer_key: str, **kw):
    from app.services.scm.trajectory_service import orders_for_customer

    return orders_for_customer(
        db_world["db"], run_id=db_world["run_id"],
        product_id=db_world["product_id"], segment="project",
        customer_key=customer_key, as_of=AS_OF, **kw,
    )


def test_the_drill_lists_a_named_customers_orders_newest_first(db_world):
    """> "sells RM 0.94?" - the price is on the order, so the order is what is shown."""
    out = _orders(db_world, db_world["customer_id"])

    assert [l["so_number"] for l in out["lines"]] == db_world["vivo_orders"]
    assert out["lines"][0]["order_date"] == "2026-07-12"
    assert out["lines"][0]["qty"] == 60
    assert out["lines"][0]["unit_price"] == 0.94
    assert out["total"] == 2 and out["shown"] == 2


def test_the_drill_works_for_an_order_that_only_carries_a_debtor_code(db_world):
    out = _orders(db_world, f"debtor:{db_world['debtor_code']}")

    assert [l["so_number"] for l in out["lines"]] == [db_world["debtor_order"]]


def test_the_drill_works_for_an_order_that_names_nobody(db_world):
    out = _orders(db_world, "none")

    assert [l["so_number"] for l in out["lines"]] == [db_world["anon_order"]]
    assert out["lines"][0]["unit_price"] is None, \
        "a line with no price says nothing, never 0.00"


def test_the_drill_is_bounded_by_the_pairs_the_run_planned(db_world):
    """The drill reads the run's own rows, not the order book at large.

    `_CUSTOMERS_SQL` builds every Who-bought-it row from the run's (product, side) pairs;
    the drill under one of those rows has to be bounded by the same set, or a run somebody
    may see becomes a way to read the orders of a product it never planned.
    """
    from app.services.error_handler import AppException
    from app.services.scm.trajectory_service import orders_for_customer

    with pytest.raises(AppException) as caught:
        orders_for_customer(
            db_world["db"], run_id=db_world["run_id"], product_id=str(uuid.uuid4()),
            segment="project", customer_key=db_world["customer_id"], as_of=AS_OF,
        )

    assert caught.value.status_code == 404


def test_the_cap_is_reported_rather_than_silent(db_world):
    out = _orders(db_world, db_world["customer_id"], limit=1)

    assert out["shown"] == 1 and out["total"] == 2


def test_the_windows_come_from_the_policy_not_a_constant(db_world):
    from app.services.scm.trajectory_service import trajectory_for_run

    out = trajectory_for_run(db_world["db"], db_world["run_id"], as_of=AS_OF)

    assert out["windows"]["retail_months"] >= 1
    assert out["windows"]["project_months"] >= 1


def test_the_response_states_how_far_back_the_series_reaches(db_world):
    """The trend popover's empty state prints this number, and a copy of it on the screen
    would be free to disagree with the window the query actually read."""
    from app.services.scm.trajectory_service import SERIES_MONTHS, trajectory_for_run

    out = trajectory_for_run(db_world["db"], db_world["run_id"], as_of=AS_OF)

    assert out["series_months"] == SERIES_MONTHS


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
            "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, "
            "counts_as_available, segment) VALUES (:id, :c, :c, true, true, 'project')"),
            {"id": wid, "c": unique_code("W")[:20]})

        cust_id = _u()
        db.execute(text(
            "INSERT INTO customers (id, customer_code, customer_name, is_active) "
            "VALUES (:id, :c, :n, true)"),
            {"id": cust_id, "c": unique_code("C")[:20], "n": f"{MARKER} Vivo Homes"})

        def order(day: date, qty: float, *, customer=cust_id, debtor=None, price=None):
            oid = _u()
            number = f"{MARKER}-{oid[:8]}"
            db.execute(text(
                "INSERT INTO sales_orders (id, so_number, status, order_date, customer_id, "
                "debtor_code) VALUES (:id, :n, 'closed', :d, :cu, :dc)"),
                {"id": oid, "n": number, "d": day, "cu": customer, "dc": debtor})
            db.execute(text(
                "INSERT INTO sales_order_lines (id, sales_order_id, product_id, warehouse_id, "
                "qty_ordered, qty_delivered, unit_price, line_status) "
                "VALUES (:id, :so, :p, :w, :q, :q, :up, 'closed')"),
                {"id": _u(), "so": oid, "p": product.id, "w": wid, "q": qty, "up": price})
            return number

        first = order(date(2026, 6, 5), 40, price=0.90)
        second = order(date(2026, 7, 12), 60, price=0.94)
        # The two orders the plan screen could not name before: one carries the debtor code
        # the document printed and no customer row, the other names neither.
        debtor_code = unique_code("D")[:20]
        debtor_order = order(date(2026, 7, 2), 5, customer=None, debtor=debtor_code,
                             price=1.10)
        anon_order = order(date(2026, 7, 3), 3, customer=None)
        db.flush()

        run_id = _u()
        db.execute(text(
            "INSERT INTO scm.reorder_run (id, status, include_market, created_at) "
            "VALUES (:id, 'completed', false, now())"), {"id": run_id})
        db.execute(text(
            "INSERT INTO scm.reorder_recommendation "
            "(id, run_id, product_id, warehouse_id, rec_type, rounded_qty, status) "
            "VALUES (:id, :r, :p, :w, 'buy', 10, 'proposed')"),
            {"id": _u(), "r": run_id, "p": product.id, "w": wid})
        db.flush()

        yield {
            "db": db, "run_id": run_id, "product_id": str(product.id),
            "customer_id": cust_id,
            "debtor_code": debtor_code,
            # Newest first, which is the order the drill returns them in.
            "vivo_orders": [second, first],
            "debtor_order": debtor_order,
            "anon_order": anon_order,
        }


# --------------------------------------------------------------------------- #
# channel_trends - the per-demand_class trend behind the grouped Buy view's
# channel columns (front planning follow-up, 19-20 Aug)
# --------------------------------------------------------------------------- #

def test_channel_trends_split_by_demand_class_and_match_the_seeded_series(channel_db_world):
    """Two demand classes on the SAME product, different monthly quantities, must land in
    two DIFFERENT `channel_trends[product_id]` entries - keyed by `sales_orders.demand_class`
    (`committed_v`'s own split), never by warehouse segment - and each entry's `recent_qty`
    must be exactly the seeded quantity for that class, not a blend of the two.
    """
    from app.services.scm.trajectory_service import trajectory_for_run

    w = channel_db_world
    out = trajectory_for_run(w["db"], w["run_id"], as_of=AS_OF)

    trends = out["channel_trends"][w["product_id"]]
    assert set(trends.keys()) >= {"project", "retail"}
    # 40 project-class units and 15 retail-class units, both dated inside July 2026 -
    # inside BOTH windows (project 12 months, retail 3 months) - so the only thing that can
    # tell them apart is the demand_class each order actually carries.
    assert trends["project"]["recent_qty"] == 40
    assert trends["retail"]["recent_qty"] == 15
    assert trends["project"]["recent_qty"] != trends["retail"]["recent_qty"]


def test_channel_trends_windows_come_from_the_project_retail_policy_split(channel_db_world):
    """Project reads the 12-month window, Retail the 3-month one - the same windows
    `out["windows"]` reports for the segment-keyed series, applied per channel."""
    from app.services.scm.trajectory_service import trajectory_for_run

    w = channel_db_world
    out = trajectory_for_run(w["db"], w["run_id"], as_of=AS_OF)

    trends = out["channel_trends"][w["product_id"]]
    assert trends["project"]["window_months"] == out["windows"]["project_months"]
    assert trends["retail"]["window_months"] == out["windows"]["retail_months"]


def test_channel_trends_avg_day_is_the_recent_qty_rate_over_its_own_window(channel_db_world):
    """The per-channel "avg N/day" subline - the same rate-over-a-window arithmetic the row's
    own SO column already uses, narrowed to one channel's own orders."""
    from app.services.scm.trajectory_service import trajectory_for_run

    w = channel_db_world
    out = trajectory_for_run(w["db"], w["run_id"], as_of=AS_OF)

    trends = out["channel_trends"][w["product_id"]]
    project_months = trends["project"]["window_months"]
    retail_months = trends["retail"]["window_months"]
    assert trends["project"]["avg_day"] == round(40 / (project_months * 30), 2)
    assert trends["retail"]["avg_day"] == round(15 / (retail_months * 30), 2)


@pytest.fixture()
def channel_db_world():
    """One product with a project-class order (qty 40) and a retail-class order (qty 15),
    both dated inside the same recent month, so only `demand_class` - never the amount of
    history or the warehouse - can explain a difference between the two channel entries.
    """
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from tests._pg_fixture import pg_session, unique_code

    def _u() -> str:
        return str(uuid.uuid4())

    with pg_session() as db:
        cat = ProductCategory(id=_u(), category_code=unique_code(MARKER),
                              category_name=f"{MARKER} channel cat")
        uom = UnitOfMeasure(id=_u(), uom_code=unique_code("U")[:20], uom_name=f"{MARKER} u")
        db.add_all([cat, uom])
        db.flush()
        product = Product(id=_u(), product_code=unique_code("P"), product_name=f"{MARKER} chan p",
                          category_id=cat.id, base_uom_id=uom.id, list_price=0,
                          is_active=True, is_discontinued=False)
        db.add(product)
        db.flush()

        wid = _u()
        db.execute(text(
            "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, "
            "counts_as_available, segment) VALUES (:id, :c, :c, true, true, 'project')"),
            {"id": wid, "c": unique_code("W")[:20]})

        def order(day: date, qty: float, demand_class: str):
            oid = _u()
            number = f"{MARKER}-{oid[:8]}"
            db.execute(text(
                "INSERT INTO sales_orders (id, so_number, status, order_date, demand_class) "
                "VALUES (:id, :n, 'closed', :d, :dc)"),
                {"id": oid, "n": number, "d": day, "dc": demand_class})
            db.execute(text(
                "INSERT INTO sales_order_lines (id, sales_order_id, product_id, warehouse_id, "
                "qty_ordered, qty_delivered, line_status) "
                "VALUES (:id, :so, :p, :w, :q, :q, 'closed')"),
                {"id": _u(), "so": oid, "p": product.id, "w": wid, "q": qty})
            return number

        # Both inside July 2026 - inside the project window (12mo back from Aug) AND the
        # retail window (3mo back from Aug) alike, so the split is by class, not by date.
        order(date(2026, 7, 5), 40, "project")
        order(date(2026, 7, 12), 15, "retail")

        run_id = _u()
        db.execute(text(
            "INSERT INTO scm.reorder_run (id, status, include_market, created_at) "
            "VALUES (:id, 'completed', false, now())"), {"id": run_id})
        db.execute(text(
            "INSERT INTO scm.reorder_recommendation "
            "(id, run_id, product_id, warehouse_id, rec_type, rounded_qty, status) "
            "VALUES (:id, :r, :p, :w, 'buy', 10, 'proposed')"),
            {"id": _u(), "r": run_id, "p": product.id, "w": wid})
        db.flush()

        yield {"db": db, "run_id": run_id, "product_id": str(product.id)}
