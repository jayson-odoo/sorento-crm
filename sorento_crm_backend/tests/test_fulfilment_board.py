"""The multi-order planning board (PLAN-fulfilment-planning-from-autocount-so section 13).

TEST-FIRST: every assertion below is written from the contract the Phase 1 mock was built
against (`_shared/types/fulfilmentPlanning.types.ts` and `_shared/lib/fulfilmentBoard.ts`),
before the service exists.

What the board is: dates across the top, products down the side, one cell per (product, date
bucket) anybody owes, with the contributing sales-order lines underneath it. It is a LENS - it
writes nothing - so every test here reads.

The four things worth arguing about, and so the four things pinned here:

  * which column a line lands in (13.3): its OWN period, past or future, with No date pinned
    last as the only column that is not a period. There is no aggregate for the past - an
    earlier build had one and it swallowed 160 of 160 lines into a single column - so what a
    past date carries instead is a flag (`is_past`) on its bucket, its cell count and its line;
  * that several orders owing one product by one date aggregate into ONE cell;
  * that scarce free stock is served per (product, LOCATION) and never across - moving stock
    between locations is a transfer, and a non-goal here (13.7);
  * that the row which loses the contest is REPORTED as contested rather than being shown a
    clean Reserve that the confirmation would later refuse (13.5.1).

Postgres, blank scratch schema, every FK target seeded here (PRINCIPLES).
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.inventory import Stock, Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import PriorityPolicy
from app.models.user import User
from app.services.scm import priority

from ._pg_fixture import blank_session

MARKER = "zzt-board"
BASE = "/api/v1/project-sales"
VIEW = "projects.projects.view"

TODAY = date(2026, 8, 18)


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _ensure_payment_terms_column(db) -> None:
    """`customers.payment_terms_days` is in the production database but not on the ORM model.

    So a scratch schema built from the models alone does not have it, and the credit factor
    would be absent here for a reason that has nothing to do with the behaviour under test.
    The DDL is idempotent and inside the rolled-back transaction, exactly like importing a
    migration and running its `upgrade()` in one.
    """
    db.execute(
        text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS payment_terms_days integer")
    )


def _customer(db, name: str, *, terms: int | None = None) -> Customer:
    row = Customer(
        id=_uid(),
        customer_code=f"ZZT-{_uid()[:8]}",
        customer_name=name,
    )
    db.add(row)
    db.flush()
    if terms is not None:
        _ensure_payment_terms_column(db)
        db.execute(
            text("UPDATE customers SET payment_terms_days = :t WHERE id = :id"),
            {"t": terms, "id": str(row.id)},
        )
    return row


def _product(db, code: str) -> Product:
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:6]}", uom_name="Unit")
    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} cat"
    )
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(),
        product_code=code,
        product_name=f"{MARKER} {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
    )
    db.add(row)
    db.flush()
    return row


def _warehouse(db, code: str) -> Warehouse:
    row = Warehouse(
        id=_uid(), warehouse_code=code, warehouse_name=code, is_active=True,
        segment="project",
    )
    db.add(row)
    db.flush()
    return row


def _stock(db, product: Product, warehouse: Warehouse, *, on_hand: int, reserved: int = 0):
    row = Stock(
        id=_uid(),
        product_id=product.id,
        warehouse_id=warehouse.id,
        quantity_on_hand=on_hand,
        quantity_reserved=reserved,
    )
    db.add(row)
    db.flush()
    return row


def _order(
    db,
    *,
    so_number: str,
    customer: Customer | None = None,
    order_date: date | None = None,
    demand_class: str = "project",
    status: str = "open",
) -> SalesOrder:
    row = SalesOrder(
        id=_uid(),
        so_number=so_number,
        customer_id=customer.id if customer else None,
        order_date=order_date,
        demand_class=demand_class,
        status=status,
        internal_note=f"Order Inquiry project: {MARKER} tower",
    )
    db.add(row)
    db.flush()
    return row


def _line(
    db,
    order: SalesOrder,
    product: Product,
    *,
    qty: str,
    required_date: date | None,
    warehouse: Warehouse | None,
    delivered: str = "0",
    line_status: str = "open",
    purchasing_status: str = "not_reviewed",
) -> SalesOrderLine:
    row = SalesOrderLine(
        id=_uid(),
        sales_order_id=order.id,
        product_id=product.id,
        warehouse_id=warehouse.id if warehouse else None,
        qty_ordered=Decimal(qty),
        qty_delivered=Decimal(delivered),
        required_date=required_date,
        line_status=line_status,
        purchasing_status=purchasing_status,
    )
    db.add(row)
    db.flush()
    return row


def _policy(db, factors: dict, class_weights: dict | None = None, *, name: str | None = None,
            active: bool = True) -> PriorityPolicy:
    row = PriorityPolicy(
        id=_uid(),
        name=name or f"{MARKER}-policy-{_uid()[:6]}",
        is_active=active,
        factors=factors,
        demand_class_weights=class_weights or {"project": 1.0},
    )
    db.add(row)
    db.flush()
    return row


def _service(db):
    from app.services.project_fulfilment_board_service import FulfilmentBoardService

    return FulfilmentBoardService(db)


def _cell(board, item_code: str, bucket_key: str) -> dict:
    return next(
        c for c in board["cells"]
        if c["item_code"] == item_code and c["bucket_key"] == bucket_key
    )


# --------------------------------------------------------------------------- #
# 13.3 - which column a line lands in
# --------------------------------------------------------------------------- #


def test_bucket_assignment_for_day_week_and_month():
    from app.services.project_fulfilment_board_service import bucket_key_for

    # A Thursday, so the week bucket has to be the Monday before it and not the date itself.
    when = date(2026, 9, 3)
    assert bucket_key_for(when, TODAY, "day") == "2026-09-03"
    assert bucket_key_for(when, TODAY, "week") == "2026-08-31"
    assert bucket_key_for(when, TODAY, "month") == "2026-09-01"


def test_a_past_date_keeps_its_own_period_and_only_no_date_is_special():
    """The captain, on seeing 160 of 160 lines collapse into one column: "don't put overdue
    together, still split by the date, don't put under overdue".

    So a date in the past buckets by ITS OWN period, exactly like a future one. The only
    non-period column left is No date, because an absent date is a different thing from an old
    one and there is no period to put it in.
    """
    from app.services.project_fulfilment_board_service import bucket_key_for

    long_ago = date(2022, 7, 6)  # a Wednesday, so the week key must be the Monday before it
    assert bucket_key_for(long_ago, TODAY, "day") == "2022-07-06"
    assert bucket_key_for(long_ago, TODAY, "week") == "2022-07-04"
    assert bucket_key_for(long_ago, TODAY, "month") == "2022-07-01"
    for granularity in ("day", "week", "month"):
        assert bucket_key_for(None, TODAY, granularity) == "no_date"


def test_no_aggregate_bucket_exists_and_a_years_old_line_keeps_its_own_column():
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}"[:20])
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        _line(db, order, product, qty="5", required_date=date(2022, 7, 6), warehouse=warehouse)
        _line(db, order, product, qty="5", required_date=date(2025, 6, 15), warehouse=warehouse)
        _line(db, order, product, qty="5", required_date=date(2026, 9, 3), warehouse=warehouse)
        _line(db, order, product, qty="5", required_date=None, warehouse=warehouse)

        board = _service(db).build([order.so_number], granularity="month", as_of=TODAY)

        keys = [bucket["key"] for bucket in board["dateBuckets"]]
        assert "overdue" not in keys, "the aggregate column is gone, not renamed"
        # Chronological, earliest first, and the two past months are two columns.
        assert keys == ["2022-07-01", "2025-06-01", "2026-09-01", "no_date"]
        kinds = {b["key"]: b["kind"] for b in board["dateBuckets"]}
        assert kinds["2022-07-01"] == "dated"
        assert kinds["no_date"] == "no_date"
        # And the line is IN its own column, carrying its own real date.
        cell = _cell(board, product.product_code, "2022-07-01")
        assert cell["total_qty"] == "5"
        assert cell["contributions"][0]["required_date"] == date(2022, 7, 6)


def test_a_bucket_whose_period_has_ended_says_so_and_the_current_one_does_not():
    """The information the Overdue column used to carry, without the lumping.

    A bucket is past when its whole period ended before the as-of date. The period CONTAINING
    the as-of date is not past: some of its dates are still to come, and tinting it would tell
    the planner this week is already lost.
    """
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}"[:20])
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        # TODAY is 2026-08-18, a Tuesday, so its week runs 17 to 23 August.
        _line(db, order, product, qty="5", required_date=date(2025, 6, 15), warehouse=warehouse)
        _line(db, order, product, qty="5", required_date=date(2026, 8, 17), warehouse=warehouse)
        _line(db, order, product, qty="5", required_date=date(2026, 9, 3), warehouse=warehouse)
        _line(db, order, product, qty="5", required_date=None, warehouse=warehouse)

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        past = {bucket["key"]: bucket["is_past"] for bucket in board["dateBuckets"]}
        assert past["2025-06-09"] is True
        assert past["2026-08-17"] is False, "the week we are in has not ended"
        assert past["2026-08-31"] is False  # w/c 31 Aug, which holds the 3 September line
        assert past["no_date"] is False, "no date is not a date that has passed"


def test_every_contribution_says_whether_its_own_date_has_passed():
    """What the "160 of 160 lines are past their required date" summary counts.

    Per LINE, not per bucket: the line dated 17 August is past even though the week it sits in
    has not ended, and a summary built off the bucket flag alone would miss it.
    """
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}"[:20])
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        _line(db, order, product, qty="5", required_date=date(2026, 8, 17), warehouse=warehouse)
        _line(db, order, product, qty="5", required_date=date(2026, 8, 19), warehouse=warehouse)
        _line(db, order, product, qty="5", required_date=None, warehouse=warehouse)

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        by_date = {
            contribution["required_date"]: contribution["is_past"]
            for cell in board["cells"]
            for contribution in cell["contributions"]
        }
        assert by_date[date(2026, 8, 17)] is True
        assert by_date[date(2026, 8, 19)] is False
        assert by_date[None] is False, "an absent date has not passed; it is simply absent"
        # And the cell counts them, so the summary needs no second pass over contributions.
        this_week = _cell(board, product.product_code, "2026-08-17")
        assert this_week["past_count"] == 1


def test_day_granularity_is_a_thirty_day_window_not_a_column_per_distinct_date():
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}"[:20])
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        _line(db, order, product, qty="5", required_date=date(2026, 9, 3), warehouse=warehouse)
        # Two years out: far outside the window, and it must not stretch the axis to reach it.
        _line(db, order, product, qty="5", required_date=date(2028, 9, 3), warehouse=warehouse)

        board = _service(db).build([order.so_number], granularity="day", as_of=TODAY)

        dated = [b for b in board["dateBuckets"] if b["kind"] == "dated"]
        assert len(dated) == 30
        assert dated[0]["key"] == "2026-09-03"
        # Empty days inside the window are still columns: a calendar that hides its empty days
        # is not a calendar, and the gap is the information.
        assert dated[1]["key"] == "2026-09-04"


# --------------------------------------------------------------------------- #
# aggregation
# --------------------------------------------------------------------------- #


def test_several_orders_owing_one_product_by_one_date_aggregate_into_one_cell():
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}"[:20])
        first = _order(db, so_number="ZZT-SO-AAA1", order_date=date(2026, 1, 1))
        second = _order(db, so_number="ZZT-SO-BBB2", order_date=date(2026, 2, 1))
        third = _order(db, so_number="ZZT-SO-CCC3", order_date=date(2026, 3, 1))
        _line(db, first, product, qty="10", required_date=date(2026, 9, 3), warehouse=warehouse)
        _line(db, second, product, qty="20", required_date=date(2026, 9, 4), warehouse=warehouse)
        _line(db, third, product, qty="30", required_date=date(2026, 9, 2), warehouse=warehouse)

        board = _service(db).build(
            ["ZZT-SO-AAA1", "ZZT-SO-BBB2", "ZZT-SO-CCC3"], granularity="week", as_of=TODAY
        )

        cell = _cell(board, product.product_code, "2026-08-31")
        assert cell["total_qty"] == "60"
        assert len(cell["contributions"]) == 3
        assert {c["so_number"] for c in cell["contributions"]} == {
            "ZZT-SO-AAA1", "ZZT-SO-BBB2", "ZZT-SO-CCC3"
        }
        # One row per product, and one standing per selected order.
        assert [row["item_code"] for row in board["productRows"]] == [product.product_code]
        assert {o["so_number"] for o in board["orders"]} == {
            "ZZT-SO-AAA1", "ZZT-SO-BBB2", "ZZT-SO-CCC3"
        }


def test_the_contribution_key_is_the_one_the_frontend_recomputes():
    """The FE rebuilds this key to count what the planner has decided (`standingsFor`).

    So it is part of the contract, not an implementation detail: `${sales_order_id}|${line_no}|
    ${item_code}|${bucket_key}`.
    """
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}"[:20])
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        _line(db, order, product, qty="10", required_date=date(2026, 9, 3), warehouse=warehouse)

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        contribution = board["cells"][0]["contributions"][0]
        assert contribution["key"] == (
            f"{order.id}|{contribution['line_no']}|{product.product_code}|2026-08-31"
        )


def test_only_open_demand_of_an_open_project_order_reaches_the_board():
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}"[:20])
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        _line(db, order, product, qty="10", required_date=date(2026, 9, 3), warehouse=warehouse)
        _line(
            db, order, product, qty="10", required_date=date(2026, 9, 3),
            warehouse=warehouse, delivered="10",
        )
        _line(
            db, order, product, qty="7", required_date=date(2026, 9, 3),
            warehouse=warehouse, purchasing_status="covered",
        )
        _line(
            db, order, product, qty="9", required_date=date(2026, 9, 3),
            warehouse=warehouse, line_status="closed",
        )

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        cell = _cell(board, product.product_code, "2026-08-31")
        assert cell["total_qty"] == "10", "only the still-owed line is demand"
        assert len(cell["contributions"]) == 1


# --------------------------------------------------------------------------- #
# 13.7 - allocation is per (product, location), never across
# --------------------------------------------------------------------------- #


def test_a_cell_spanning_two_locations_allocates_per_location():
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        here = _warehouse(db, f"ZZTA{_uid()[:6]}"[:20])
        there = _warehouse(db, f"ZZTB{_uid()[:6]}"[:20])
        _stock(db, product, here, on_hand=10)
        _stock(db, product, there, on_hand=0)
        first = _order(db, so_number="ZZT-SO-LOC1", order_date=date(2026, 1, 1))
        second = _order(db, so_number="ZZT-SO-LOC2", order_date=date(2026, 1, 1))
        _line(db, first, product, qty="10", required_date=date(2026, 9, 3), warehouse=here)
        _line(db, second, product, qty="10", required_date=date(2026, 9, 3), warehouse=there)

        board = _service(db).build(
            ["ZZT-SO-LOC1", "ZZT-SO-LOC2"], granularity="week", as_of=TODAY
        )

        cell = _cell(board, product.product_code, "2026-08-31")
        assert cell["total_qty"] == "20"
        assert {(loc["location"], loc["qty"]) for loc in cell["locations"]} == {
            (here.warehouse_code, "10"), (there.warehouse_code, "10")
        }
        by_order = {c["so_number"]: c for c in cell["contributions"]}
        assert [
            (s["kind"], s["qty"]) for s in by_order["ZZT-SO-LOC1"]["sources"]
        ] == [("reserve", "10")]
        # The other location's line is bought: free stock at one location cannot cover a line
        # that must be fulfilled from another. That is a transfer, and a non-goal here.
        assert [
            (s["kind"], s["qty"]) for s in by_order["ZZT-SO-LOC2"]["sources"]
        ] == [("buy", "10")]
        assert by_order["ZZT-SO-LOC2"]["contested"] is False, (
            "a location that never held stock is a plain Buy, not a contest"
        )


def test_free_stock_is_what_the_supply_service_computes_not_a_second_opinion():
    """On hand minus reserved: the board must not invent its own availability figure."""
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}"[:20])
        _stock(db, product, warehouse, on_hand=10, reserved=4)
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        _line(db, order, product, qty="10", required_date=date(2026, 9, 3), warehouse=warehouse)

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        sources = board["cells"][0]["contributions"][0]["sources"]
        assert [(s["kind"], s["qty"]) for s in sources] == [("reserve", "6"), ("buy", "4")]


# --------------------------------------------------------------------------- #
# 13.5 / 13.5.1 - the ranking, and the contest it makes visible
# --------------------------------------------------------------------------- #


def test_the_loser_of_a_contest_is_reported_as_contested_and_named_who_took_it():
    with blank_session() as db:
        _policy(db, {"need_by_date": 1.0})
        product = _product(db, f"ZZT-{_uid()[:6]}")
        warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}"[:20])
        _stock(db, product, warehouse, on_hand=10)
        winner = _order(db, so_number="ZZT-SO-WIN", order_date=date(2026, 1, 1))
        loser = _order(db, so_number="ZZT-SO-LOSE", order_date=date(2026, 1, 1))
        # Same cell (same ISO week), different real dates: the sooner one outranks.
        _line(db, winner, product, qty="10", required_date=date(2026, 9, 1), warehouse=warehouse)
        _line(db, loser, product, qty="10", required_date=date(2026, 9, 4), warehouse=warehouse)

        board = _service(db).build(
            ["ZZT-SO-WIN", "ZZT-SO-LOSE"], granularity="week", as_of=TODAY
        )

        cell = _cell(board, product.product_code, "2026-08-31")
        assert [c["so_number"] for c in cell["contributions"]] == [
            "ZZT-SO-WIN", "ZZT-SO-LOSE"
        ], "contributions are served in rank order, highest first"
        won, lost = cell["contributions"]
        assert won["rank_score"] > lost["rank_score"]
        assert [(s["kind"], s["qty"]) for s in won["sources"]] == [("reserve", "10")]
        assert [(s["kind"], s["qty"]) for s in lost["sources"]] == [("buy", "10")]
        assert lost["contested"] is True
        assert won["contested"] is False
        assert cell["contested_count"] == 1
        # A ranking nobody can inspect is a ranking nobody will trust: the reason names the
        # order that took the stock, and the row carries the factors behind its score.
        assert "ZZT-SO-WIN" in lost["sources"][0]["reason"]
        assert {f["key"] for f in lost["rank_factors"]} >= {
            "need_by_date", "document_age", "customer_credit",
            "demand_class", "po_document_sequence",
        }


def test_shorter_payment_terms_win_the_stock_when_the_policy_weights_credit():
    with blank_session() as db:
        _policy(db, {"customer_credit": 1.0})
        product = _product(db, f"ZZT-{_uid()[:6]}")
        warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}"[:20])
        _stock(db, product, warehouse, on_hand=10)
        prompt = _customer(db, f"{MARKER} pays in 30", terms=30)
        slow = _customer(db, f"{MARKER} pays in 90", terms=90)
        # The slower payer is FIRST by sales-order number, so an alphabetical answer loses.
        a = _order(db, so_number="ZZT-SO-AAA", customer=slow, order_date=date(2026, 1, 1))
        b = _order(db, so_number="ZZT-SO-BBB", customer=prompt, order_date=date(2026, 1, 1))
        _line(db, a, product, qty="10", required_date=date(2026, 9, 3), warehouse=warehouse)
        _line(db, b, product, qty="10", required_date=date(2026, 9, 3), warehouse=warehouse)

        board = _service(db).build(
            ["ZZT-SO-AAA", "ZZT-SO-BBB"], granularity="week", as_of=TODAY
        )

        cell = _cell(board, product.product_code, "2026-08-31")
        assert [c["so_number"] for c in cell["contributions"]] == ["ZZT-SO-BBB", "ZZT-SO-AAA"]
        assert cell["contributions"][0]["sources"][0]["kind"] == "reserve"


def test_the_older_sales_order_wins_the_stock_when_the_policy_weights_document_age():
    """The prototype had this inverted, with the NEWEST document winning. 2024 beats 2026."""
    with blank_session() as db:
        _policy(db, {"document_age": 1.0})
        product = _product(db, f"ZZT-{_uid()[:6]}")
        warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}"[:20])
        _stock(db, product, warehouse, on_hand=10)
        # The NEWER order is first alphabetically, so an accidental sort cannot pass this.
        new = _order(db, so_number="ZZT-SO-AAA", order_date=date(2026, 7, 28))
        old = _order(db, so_number="ZZT-SO-BBB", order_date=date(2024, 1, 9))
        _line(db, new, product, qty="10", required_date=date(2026, 9, 3), warehouse=warehouse)
        _line(db, old, product, qty="10", required_date=date(2026, 9, 3), warehouse=warehouse)

        board = _service(db).build(
            ["ZZT-SO-AAA", "ZZT-SO-BBB"], granularity="week", as_of=TODAY
        )

        cell = _cell(board, product.product_code, "2026-08-31")
        assert [c["so_number"] for c in cell["contributions"]] == ["ZZT-SO-BBB", "ZZT-SO-AAA"]
        assert cell["contributions"][0]["sources"][0]["kind"] == "reserve"


def test_a_policy_that_ranks_nothing_is_reported_flat_rather_than_dressed_up():
    """No policy row at all falls back to `po_document_sequence`, which no board row has."""
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}"[:20])
        _stock(db, product, warehouse, on_hand=10)
        a = _order(db, so_number="ZZT-SO-AAA", order_date=date(2026, 1, 1))
        b = _order(db, so_number="ZZT-SO-BBB", order_date=date(2026, 7, 1))
        _line(db, a, product, qty="10", required_date=date(2026, 9, 1), warehouse=warehouse)
        _line(db, b, product, qty="10", required_date=date(2026, 9, 4), warehouse=warehouse)

        board = _service(db).build(
            ["ZZT-SO-AAA", "ZZT-SO-BBB"], granularity="week", as_of=TODAY
        )

        assert board["policy"]["discriminates_nothing"] is True
        assert board["policy"]["is_preview"] is False
        cell = _cell(board, product.product_code, "2026-08-31")
        assert [c["rank_score"] for c in cell["contributions"]] == [0.0, 0.0]
        # Flat, so the tie-break is what orders them, and it is TOTAL: sales-order number then
        # line number, so the same facts give the same answer on every refresh.
        assert [c["so_number"] for c in cell["contributions"]] == [
            "ZZT-SO-AAA", "ZZT-SO-BBB"
        ]


def test_the_named_preview_ranks_without_activating_anything():
    with blank_session() as db:
        live = _policy(db, {"po_document_sequence": 1.0})
        product = _product(db, f"ZZT-{_uid()[:6]}")
        warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}"[:20])
        _stock(db, product, warehouse, on_hand=10)
        soon = _order(db, so_number="ZZT-SO-BBB", order_date=date(2026, 1, 1))
        late = _order(db, so_number="ZZT-SO-AAA", order_date=date(2026, 1, 1))
        _line(db, soon, product, qty="10", required_date=date(2026, 9, 1), warehouse=warehouse)
        _line(db, late, product, qty="10", required_date=date(2026, 9, 4), warehouse=warehouse)

        board = _service(db).build(
            ["ZZT-SO-AAA", "ZZT-SO-BBB"],
            granularity="week",
            as_of=TODAY,
            preview_policy=priority.BOARD_PREVIEW_NAME,
        )

        assert board["policy"]["is_preview"] is True
        assert board["policy"]["name"] == priority.BOARD_PREVIEW_NAME
        assert board["policy"]["discriminates_nothing"] is False
        cell = _cell(board, product.product_code, "2026-08-31")
        assert [c["so_number"] for c in cell["contributions"]] == ["ZZT-SO-BBB", "ZZT-SO-AAA"]
        # Nothing was written and nothing was switched on.
        assert str(priority.active_policy(db).id) == str(live.id)
        assert (
            db.query(PriorityPolicy).filter(PriorityPolicy.name == priority.BOARD_PREVIEW_NAME)
            .count() == 0
        )


def test_an_unknown_preview_policy_name_is_refused_by_name():
    from app.services.error_handler import AppException

    with blank_session() as db:
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))

        with pytest.raises(AppException) as excinfo:
            _service(db).build(
                [order.so_number], as_of=TODAY, preview_policy=f"{MARKER}-nope"
            )

        assert excinfo.value.status_code == 404
        assert f"{MARKER}-nope" in excinfo.value.detail["message"]


# --------------------------------------------------------------------------- #
# AC-FP16 on the board (13.7)
# --------------------------------------------------------------------------- #


def test_a_line_whose_order_states_no_location_is_counted_but_unplannable():
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}"[:20])
        _stock(db, product, warehouse, on_hand=100)
        stated = _order(db, so_number="ZZT-SO-HASWH", order_date=date(2026, 1, 1))
        silent = _order(db, so_number="ZZT-SO-NOWH", order_date=date(2026, 1, 1))
        _line(db, stated, product, qty="10", required_date=date(2026, 9, 3), warehouse=warehouse)
        _line(db, silent, product, qty="4", required_date=date(2026, 9, 3), warehouse=None)

        board = _service(db).build(
            ["ZZT-SO-HASWH", "ZZT-SO-NOWH"], granularity="week", as_of=TODAY
        )

        cell = _cell(board, product.product_code, "2026-08-31")
        # Counted, so the demand is not hidden by the source record being incomplete.
        assert cell["total_qty"] == "14"
        assert cell["unplannable_count"] == 1
        blocked = next(c for c in cell["contributions"] if c["so_number"] == "ZZT-SO-NOWH")
        assert blocked["unplannable"] is True
        assert blocked["fulfilment_location"] is None
        assert [s["kind"] for s in blocked["sources"]] == ["unplannable"]
        # Nothing is proposed for it: a Reserve of zero presented as a plan is worse than a
        # refusal, and no location is ever guessed.
        assert {(loc["location"], loc["qty"]) for loc in cell["locations"]} == {
            (warehouse.warehouse_code, "10"), (None, "4")
        }


# --------------------------------------------------------------------------- #
# the selection itself (13.2)
# --------------------------------------------------------------------------- #


def test_more_than_fifty_orders_is_refused_and_the_cap_is_stated():
    from app.services.error_handler import AppException

    with blank_session() as db:
        with pytest.raises(AppException) as excinfo:
            _service(db).build([f"ZZT-SO-{n}" for n in range(51)], as_of=TODAY)

        assert excinfo.value.status_code == 422
        assert "50" in excinfo.value.detail["message"]


def test_an_empty_selection_is_an_empty_board_not_the_whole_book():
    with blank_session() as db:
        board = _service(db).build([], as_of=TODAY)

        assert board["cells"] == []
        assert board["productRows"] == []
        assert board["orders"] == []


# --------------------------------------------------------------------------- #
# the route
# --------------------------------------------------------------------------- #


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _client(db, user_id: str, permissions):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    actor = {"id": user_id, "email": f"{user_id}@zzt.test", "role": "user"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = lambda: None

    originals = (
        UserPermissionService.check_user_has_permission,
        UserPermissionService.get_user_permission_slugs,
    )
    granted = list(permissions)
    UserPermissionService.check_user_has_permission = (
        lambda self, uid, slug: slug in granted
    )
    UserPermissionService.get_user_permission_slugs = lambda self, uid: list(granted)
    return TestClient(app), originals


def _restore(originals) -> None:
    from app.main import app
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = originals[0]
    UserPermissionService.get_user_permission_slugs = originals[1]
    app.dependency_overrides.clear()


def _board_world(db):
    product = _product(db, f"ZZT-{_uid()[:6]}")
    warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}"[:20])
    _stock(db, product, warehouse, on_hand=10)
    order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
    _line(db, order, product, qty="10", required_date=date(2026, 9, 3), warehouse=warehouse)
    return order, product


def test_the_board_route_answers_the_selection_it_was_given():
    from app.models.base import company_scope

    with blank_session() as db:
        company_id = _sorento(db)
        actor = _user(db, f"{MARKER} Eling")
        order, product = _board_world(db)
        db.commit()
        client, originals = _client(db, actor, [VIEW])
        try:
            with company_scope(db, frozenset({company_id})):
                response = client.get(
                    f"{BASE}/fulfilment-planning/board",
                    params={"orders": order.so_number, "granularity": "week"},
                )
        finally:
            _restore(originals)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["granularity"] == "week"
        assert body["policy"]["name"]
        assert [row["item_code"] for row in body["productRows"]] == [product.product_code]
        assert body["cells"][0]["contributions"][0]["so_number"] == order.so_number
        # The selection-scoped totals reach the wire. A field the service returns but the
        # response model does not declare is dropped silently, and the banner would then read
        # zero rather than fail.
        assert body["line_count"] == 1
        assert body["past_line_count"] == 0
        assert body["unplannable_line_count"] == 0
        assert body["contested_line_count"] == 0
        # The named quantities and the raw facts reach the wire too: a field the service
        # returns but the response model does not declare is dropped silently.
        contribution = body["cells"][0]["contributions"][0]
        assert contribution["qty_ordered"] == "10"
        assert contribution["qty_outstanding"] == "10"
        assert contribution["qty_proposed_reserve"] == "10"
        location = body["cells"][0]["locations"][0]
        assert location["qty_on_hand"] == "10" and location["qty_free"] == "10"
        assert {f["key"]: f["raw"] for f in contribution["rank_factors"]}["need_by_date"] == (
            "2026-09-03"
        )
        # No identifier a person has to resolve is rendered anywhere: the human keys are the
        # sales-order number, the item code and the warehouse code.
        assert body["cells"][0]["contributions"][0]["item_code"] == product.product_code


def test_the_board_route_refuses_a_caller_without_the_view_permission():
    from app.models.base import company_scope

    with blank_session() as db:
        company_id = _sorento(db)
        actor = _user(db, f"{MARKER} Eling")
        order, _product = _board_world(db)
        db.commit()
        client, originals = _client(db, actor, [])
        try:
            with company_scope(db, frozenset({company_id})):
                response = client.get(
                    f"{BASE}/fulfilment-planning/board",
                    params={"orders": order.so_number},
                )
        finally:
            _restore(originals)

        assert response.status_code == 403


def test_an_unknown_granularity_is_a_422_not_a_silently_weekly_board():
    from app.models.base import company_scope

    with blank_session() as db:
        company_id = _sorento(db)
        actor = _user(db, f"{MARKER} Eling")
        order, _product = _board_world(db)
        db.commit()
        client, originals = _client(db, actor, [VIEW])
        try:
            with company_scope(db, frozenset({company_id})):
                response = client.get(
                    f"{BASE}/fulfilment-planning/board",
                    params={"orders": order.so_number, "granularity": "fortnight"},
                )
        finally:
            _restore(originals)

        assert response.status_code == 422


def test_a_named_policy_row_that_is_actually_live_is_not_labelled_a_preview():
    """Whether it is a preview is a fact about the ROW, not about how it was asked for."""
    with blank_session() as db:
        live = _policy(db, {"need_by_date": 1.0}, name=f"{MARKER}-live-by-name")
        product = _product(db, f"ZZT-{_uid()[:6]}")
        warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}"[:20])
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        _line(db, order, product, qty="10", required_date=date(2026, 9, 3), warehouse=warehouse)

        board = _service(db).build(
            [order.so_number], as_of=TODAY, preview_policy=live.name
        )

        assert board["policy"]["name"] == live.name
        assert board["policy"]["is_preview"] is False


def test_preview_policy_1_means_the_modules_own_board_preview():
    """The frontend sends `preview_policy=1`, and that translation belongs to the service.

    Split between route and service it would be untested on one side of the seam and the two
    would come to disagree about what "preview" was asked for.
    """
    with blank_session() as db:
        _policy(db, {"po_document_sequence": 1.0})
        product = _product(db, f"ZZT-{_uid()[:6]}")
        warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}"[:20])
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        _line(db, order, product, qty="10", required_date=date(2026, 9, 3), warehouse=warehouse)

        board = _service(db).build([order.so_number], as_of=TODAY, preview_policy="1")

        assert board["policy"]["name"] == priority.BOARD_PREVIEW_NAME
        assert board["policy"]["is_preview"] is True


def test_the_day_window_opens_on_the_work_still_to_come_not_three_years_ago():
    """With the Overdue column gone, "the earliest dated bucket" can be years in the past.

    The prototype's day view opened on the earliest STILL-FUTURE date, and it has to keep
    doing that: a 30-day window that opens in December 2024 shows the planner one line and an
    empty month. Past demand is reached by moving the window, which is what the control is for.
    """
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}"[:20])
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        _line(db, order, product, qty="5", required_date=date(2024, 12, 3), warehouse=warehouse)
        _line(db, order, product, qty="5", required_date=date(2026, 9, 3), warehouse=warehouse)

        board = _service(db).build([order.so_number], granularity="day", as_of=TODAY)

        dated = [b for b in board["dateBuckets"] if b["kind"] == "dated"]
        assert dated[0]["key"] == "2026-09-03"
        # And the past line is still reachable: the window is a display control, so asking for
        # it by date brings it back rather than the plan having lost it.
        back = _service(db).build(
            [order.so_number],
            granularity="day",
            as_of=TODAY,
            day_window_start=date(2024, 12, 1),
        )
        assert [b["key"] for b in back["dateBuckets"]][0] == "2024-12-01"
        assert _cell(back, product.product_code, "2024-12-03")["past_count"] == 1


def test_the_day_window_falls_back_to_the_earliest_owed_when_everything_is_past():
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}"[:20])
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        _line(db, order, product, qty="5", required_date=date(2025, 6, 15), warehouse=warehouse)

        board = _service(db).build([order.so_number], granularity="day", as_of=TODAY)

        dated = [b for b in board["dateBuckets"] if b["kind"] == "dated"]
        assert dated[0]["key"] == "2025-06-15", "open where the work is, not on an empty today"
        assert dated[0]["is_past"] is True


# --------------------------------------------------------------------------- #
# board-level totals: the selection's truth, not the window's
# --------------------------------------------------------------------------- #


def _past_world(db):
    """One order, three products, most of it already past, spread over three years."""
    warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}"[:20])
    order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
    for offset, when in enumerate(
        [date(2024, 3, 4), date(2025, 6, 15), date(2026, 8, 17), date(2026, 9, 3)]
    ):
        product = _product(db, f"ZZT-{_uid()[:6]}")
        _stock(db, product, warehouse, on_hand=1)
        _line(db, order, product, qty="5", required_date=when, warehouse=warehouse)
    # One line nobody stated a location for, and one with no date at all.
    spare = _product(db, f"ZZT-{_uid()[:6]}")
    _line(db, order, spare, qty="5", required_date=date(2024, 3, 4), warehouse=None)
    _line(db, order, spare, qty="5", required_date=None, warehouse=warehouse)
    return order


def test_the_board_totals_are_the_selections_and_do_not_move_with_the_granularity():
    """The FE banner reads "143 of 153 lines are already past their required date".

    Summed off the cells ON SCREEN that sentence is true at week and month and vanishes at day,
    because the day window opens on work still to come and so holds no past cell at all - the
    planner switching to the closest view silently loses the most important number on the
    board. So the total is the SELECTION's, computed before any window is applied.
    """
    with blank_session() as db:
        order = _past_world(db)

        boards = {
            gran: _service(db).build([order.so_number], granularity=gran, as_of=TODAY)
            for gran in ("day", "week", "month")
        }

        for gran, board in boards.items():
            assert board["line_count"] == 6, gran
            assert board["past_line_count"] == 4, gran
            assert board["unplannable_line_count"] == 1, gran
        # And the day board really does show none of them, which is the whole point.
        day_cells_past = sum(cell["past_count"] for cell in boards["day"]["cells"])
        assert day_cells_past == 0
        assert boards["day"]["past_line_count"] == 4


def test_moving_the_day_window_does_not_change_the_board_totals():
    with blank_session() as db:
        order = _past_world(db)

        here = _service(db).build([order.so_number], granularity="day", as_of=TODAY)
        long_ago = _service(db).build(
            [order.so_number],
            granularity="day",
            as_of=TODAY,
            day_window_start=date(2024, 3, 1),
        )
        empty = _service(db).build(
            [order.so_number],
            granularity="day",
            as_of=TODAY,
            day_window_start=date(2029, 1, 1),
        )

        for board in (here, long_ago, empty):
            assert board["line_count"] == 6
            assert board["past_line_count"] == 4
            assert board["unplannable_line_count"] == 1
        # The windows genuinely differ, so the totals holding still means something. The
        # dateless column survives the window because it is not on the timeline at all, which
        # is why this counts DATED cells rather than all of them.
        assert [c for c in empty["cells"] if c["bucket_key"] != "no_date"] == []
        assert sum(c["past_count"] for c in long_ago["cells"]) == 2


def test_a_line_outside_the_day_window_is_still_served_from_its_pile():
    """The window is a display bound, so it must not change what anybody is proposed.

    Two lines competing for one unit at one location: whoever the ranking serves first takes
    it and the other is contested. Look at that through a day window containing neither of
    them, and the contest still has to be reported - the board's totals describe the selection,
    not the columns that happen to be on screen.
    """
    with blank_session() as db:
        _policy(db, {"need_by_date": 1.0})
        product = _product(db, f"ZZT-{_uid()[:6]}")
        warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}"[:20])
        _stock(db, product, warehouse, on_hand=10)
        winner = _order(db, so_number="ZZT-SO-WINDOW1", order_date=date(2026, 1, 1))
        loser = _order(db, so_number="ZZT-SO-WINDOW2", order_date=date(2026, 1, 1))
        _line(db, winner, product, qty="10", required_date=date(2026, 9, 1), warehouse=warehouse)
        _line(db, loser, product, qty="10", required_date=date(2026, 9, 4), warehouse=warehouse)

        week = _service(db).build(
            ["ZZT-SO-WINDOW1", "ZZT-SO-WINDOW2"], granularity="week", as_of=TODAY
        )
        far = _service(db).build(
            ["ZZT-SO-WINDOW1", "ZZT-SO-WINDOW2"],
            granularity="day",
            as_of=TODAY,
            day_window_start=date(2029, 1, 1),
        )

        assert week["contested_line_count"] == 1
        assert [c for c in far["cells"] if c["bucket_key"] != "no_date"] == [], (
            "the window shows nothing of the timeline"
        )
        assert far["contested_line_count"] == 1, "and the contest is still reported"


def test_each_orders_standing_counts_the_whole_order_not_the_window():
    """`orders[]` is the other place the window could lie, and it must not.

    The screen prints "N of M lines decided" per order. Rebuilt from the cells on screen, M
    shrinks to the window at day granularity and an order of forty lines reads as three - so
    the standings are counted from the selection here, and the screen overlays only its own
    draft count on top.
    """
    with blank_session() as db:
        order = _past_world(db)

        day = _service(db).build([order.so_number], granularity="day", as_of=TODAY)
        month = _service(db).build([order.so_number], granularity="month", as_of=TODAY)

        assert [(s["so_number"], s["line_count"], s["unplannable_count"]) for s in day["orders"]] == [
            (order.so_number, 6, 1)
        ]
        assert day["orders"] == month["orders"]
        # And the window really is narrower than the order, so the equality means something.
        assert sum(len(c["contributions"]) for c in day["cells"]) < 6


# --------------------------------------------------------------------------- #
# the numbers, by name
#
# The captain, on the live board: "how do i see the available quantity for each stock, is it
# BRW-BB - 22?, we need to be clear on the quantity, like what is the quantity on hand, what is
# the SO quantity, what is the PO qty, what is the incoming quantity". `22` was the DEMAND at
# that location, which is the one reading nobody guessed.
#
# The fixture below deliberately makes EVERY number different, so a field crossed with its
# neighbour fails instead of passing:
#   ordered 28, delivered 8    -> outstanding 20
#   on hand 30, reserved 25    -> free 5
#   SPO allocated 9, received 2 -> incoming 7, arriving before the required date
#   so the proposal must be    -> reserve 5 + incoming 7 + buy 8
# --------------------------------------------------------------------------- #


def _incoming(db, product, warehouse, *, spo_number: str, allocated: int, received: int,
              arrives: date):
    from app.models.procurement import InboundShipment, SPOAllocation

    shipment = InboundShipment(
        id=_uid(),
        shipment_number=f"ZZT-SHIP-{_uid()[:8]}",
        shipment_date=date(2026, 1, 1),
        estimated_arrival_date=arrives,
    )
    db.add(shipment)
    db.flush()
    row = SPOAllocation(
        id=_uid(),
        spo_number=spo_number,
        spo_line_number=1,
        inbound_shipment_id=shipment.id,
        warehouse_id=warehouse.id,
        product_id=product.id,
        allocated_quantity=allocated,
        quantity_received=received,
        receipt_status="pending",
    )
    db.add(row)
    db.flush()
    return row


def _quantity_world(db):
    product = _product(db, f"ZZT-{_uid()[:6]}")
    warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}"[:20])
    _stock(db, product, warehouse, on_hand=30, reserved=25)
    _incoming(
        db, product, warehouse,
        spo_number="ZZT-SPO-0001", allocated=9, received=2, arrives=date(2026, 8, 25),
    )
    order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
    _line(
        db, order, product, qty="28", delivered="8",
        required_date=date(2026, 9, 3), warehouse=warehouse,
    )
    return order, product, warehouse


def test_a_contribution_states_the_sales_order_quantities_by_name():
    with blank_session() as db:
        order, product, _warehouse = _quantity_world(db)

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        contribution = _cell(board, product.product_code, "2026-08-31")["contributions"][0]
        assert contribution["qty_ordered"] == "28"
        assert contribution["qty_delivered"] == "8"
        assert contribution["qty_outstanding"] == "20"
        # The owed quantity is what the board plans against, never the original order.
        assert contribution["qty"] == contribution["qty_outstanding"]


def test_a_contribution_states_the_proposal_by_name():
    with blank_session() as db:
        order, product, _warehouse = _quantity_world(db)

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        contribution = _cell(board, product.product_code, "2026-08-31")["contributions"][0]
        assert contribution["qty_proposed_reserve"] == "5"
        assert contribution["qty_proposed_incoming"] == "7"
        assert contribution["qty_proposed_buy"] == "8"
        # And they still add up to what is owed, which is the invariant the sheet also keeps.
        assert (
            int(contribution["qty_proposed_reserve"])
            + int(contribution["qty_proposed_incoming"])
            + int(contribution["qty_proposed_buy"])
        ) == int(contribution["qty_outstanding"])


def test_a_cells_location_states_the_availability_not_only_the_demand():
    """"is it BRW-BB - 22?" - no. 22 was the demand, and the stock facts were nowhere."""
    with blank_session() as db:
        order, product, warehouse = _quantity_world(db)

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        location = _cell(board, product.product_code, "2026-08-31")["locations"][0]
        assert location["location"] == warehouse.warehouse_code
        assert location["qty_demand"] == "20"
        assert location["qty_on_hand"] == "30"
        assert location["qty_reserved"] == "25"
        # What this engine may actually use, after existing holds - the number the strip was
        # silently NOT showing.
        assert location["qty_free"] == "5"
        assert location["qty_incoming"] == "7"
        assert location["qty_proposed_reserve"] == "5"
        assert location["qty_proposed_incoming"] == "7"
        assert location["qty_proposed_buy"] == "8"


def test_a_cells_location_names_the_incoming_document_and_its_arrival_date():
    with blank_session() as db:
        order, product, _warehouse = _quantity_world(db)

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        location = _cell(board, product.product_code, "2026-08-31")["locations"][0]
        assert location["incoming"] == [
            {
                "spo_number": "ZZT-SPO-0001",
                "arrival_date": date(2026, 8, 25),
                "qty": "7",
            }
        ]


def test_the_free_figure_says_what_was_left_when_this_cell_was_served():
    """Stock is not per date, so the same free figure appears in every column of a product.

    That is the truth and it is also the reading most likely to mislead, because an earlier
    date has already drawn the pile down. So each cell also states what was still unclaimed
    when ITS lines were served.
    """
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}"[:20])
        _stock(db, product, warehouse, on_hand=10)
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        _line(db, order, product, qty="6", required_date=date(2026, 9, 3), warehouse=warehouse)
        _line(db, order, product, qty="6", required_date=date(2026, 12, 1), warehouse=warehouse)

        board = _service(db).build([order.so_number], granularity="month", as_of=TODAY)

        september = _cell(board, product.product_code, "2026-09-01")["locations"][0]
        december = _cell(board, product.product_code, "2026-12-01")["locations"][0]
        assert september["qty_free"] == december["qty_free"] == "10"
        assert september["qty_free_remaining"] == "10"
        assert december["qty_free_remaining"] == "4", "September took six of the ten"
        assert december["qty_proposed_reserve"] == "4"
        assert december["qty_proposed_buy"] == "2"


def test_a_line_with_no_location_states_no_availability_rather_than_zeroes():
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        _line(db, order, product, qty="4", required_date=date(2026, 9, 3), warehouse=None)

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        location = _cell(board, product.product_code, "2026-08-31")["locations"][0]
        assert location["location"] is None
        assert location["qty_demand"] == "4"
        # Null, not zero: nobody said where this is fulfilled from, so there is no location
        # whose stock could be counted. A zero would read as "that location is empty".
        assert location["qty_on_hand"] is None
        assert location["qty_free"] is None
        assert location["qty_incoming"] is None


# --------------------------------------------------------------------------- #
# the rank, made readable
# --------------------------------------------------------------------------- #


def test_every_factor_carries_the_absolute_fact_that_produced_it():
    """A normalised 0.00 next to a normalised 1.00 explains nothing on its own.

    The planner needs the fact: this line's required date, this order's document date, this
    customer's terms. So each factor carries its raw value beside the normalised one.
    """
    with blank_session() as db:
        _policy(db, dict(priority.BOARD_PREVIEW_WEIGHTS))
        product = _product(db, f"ZZT-{_uid()[:6]}")
        warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}"[:20])
        customer = _customer(db, f"{MARKER} pays in 45", terms=45)
        order = _order(
            db, so_number=f"ZZT-SO-{_uid()[:8]}", customer=customer,
            order_date=date(2025, 4, 16),
        )
        _line(db, order, product, qty="5", required_date=date(2026, 9, 3), warehouse=warehouse)

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        factors = {
            f["key"]: f
            for f in _cell(board, product.product_code, "2026-08-31")["contributions"][0][
                "rank_factors"
            ]
        }
        assert factors["need_by_date"]["raw"] == "2026-09-03"
        assert factors["document_age"]["raw"] == "2025-04-16"
        assert factors["customer_credit"]["raw"] == "45 days"
        assert factors["demand_class"]["raw"] == "project"
        # An absent factor has no fact to state, and must not invent one.
        assert factors["po_document_sequence"]["raw"] is None
        assert factors["po_document_sequence"]["present"] is False


def test_the_sign_of_every_factor_is_verified_against_its_raw_fact():
    """The prototype had `document_age` inverted once, so each sign is pinned to real facts.

    One cell, three competing lines, and for each factor the row whose RAW fact should win is
    asserted to be the row that scores 1.0 - read off the raw value rather than off knowledge
    of the seeding order.
    """
    with blank_session() as db:
        _policy(db, dict(priority.BOARD_PREVIEW_WEIGHTS))
        product = _product(db, f"ZZT-{_uid()[:6]}")
        warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}"[:20])
        rows = [
            ("ZZT-SO-SIGN1", date(2024, 1, 9), 90, date(2026, 9, 1)),
            ("ZZT-SO-SIGN2", date(2025, 6, 30), 60, date(2026, 9, 2)),
            ("ZZT-SO-SIGN3", date(2026, 7, 28), 30, date(2026, 9, 4)),
        ]
        for so_number, order_date, terms, required in rows:
            customer = _customer(db, f"{MARKER} {terms}d", terms=terms)
            order = _order(
                db, so_number=so_number, customer=customer, order_date=order_date
            )
            _line(db, order, product, qty="5", required_date=required, warehouse=warehouse)

        board = _service(db).build(
            [r[0] for r in rows], granularity="week", as_of=TODAY
        )

        cell = _cell(board, product.product_code, "2026-08-31")
        facts = {
            contribution["so_number"]: {
                f["key"]: (f["raw"], f["value"]) for f in contribution["rank_factors"]
            }
            for contribution in cell["contributions"]
        }

        def top(key):
            return max(facts.items(), key=lambda pair: pair[1][key][1])

        # SOONER required date is higher: the winner's raw date is the earliest of the three.
        winner, values = top("need_by_date")
        assert values["need_by_date"] == ("2026-09-01", 1.0)
        assert winner == "ZZT-SO-SIGN1"
        # OLDER document is higher: the winner's raw order date is the earliest.
        winner, values = top("document_age")
        assert values["document_age"] == ("2024-01-09", 1.0)
        # SHORTER terms are higher: the winner pays in 30 days, not 90.
        winner, values = top("customer_credit")
        assert values["customer_credit"] == ("30 days", 1.0)
        assert winner == "ZZT-SO-SIGN3"


# --------------------------------------------------------------------------- #
# the source ladder: the board must give the SAME answer as the sheet
#
# The captain, reading a breakdown line by line: "so for this one, no free stock available, so
# did it go through the process of whether want to borrow / use BRW (depending on the hot
# selling / cold selling or discontinued) then only arrive at buy?"
#
# It did not, and that made the board's Buy overstate what has to be bought - purchasing acting
# on the board and purchasing acting on the sheet would disagree about the same line. The
# ladder is `project_supply_service`'s, and the board runs THAT rather than a reduced copy.
# --------------------------------------------------------------------------- #


def _pooled_warehouses(db):
    """A project location whose shortfall may draw on a shared pool, as BRW-BB draws on BRW."""
    pool = _warehouse(db, f"ZZTP{_uid()[:6]}"[:20])
    own = _warehouse(db, f"ZZTO{_uid()[:6]}"[:20])
    own.pool_warehouse_id = pool.id
    db.flush()
    return own, pool


def test_the_board_covers_a_shortfall_from_the_pool_instead_of_buying_it():
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        own, pool = _pooled_warehouses(db)
        _stock(db, product, own, on_hand=2)
        _stock(db, product, pool, on_hand=50)
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        _line(db, order, product, qty="10", required_date=date(2026, 9, 3), warehouse=own)

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        contribution = _cell(board, product.product_code, "2026-08-31")["contributions"][0]
        kinds = [(s["kind"], s["qty"], s["location"]) for s in contribution["sources"]]
        assert kinds == [
            ("reserve", "2", own.warehouse_code),
            ("reserve", "8", pool.warehouse_code),
        ], "the shared pool covers the shortfall before anything is bought"
        assert contribution["qty_proposed_buy"] == "0"


def test_a_dealer_hot_selling_product_may_not_take_its_own_stock_on_the_board_either():
    """PLAN 3.3, which the board was skipping entirely: hot-selling protects dealer stock.

    Dealer-facing free stock contributes nothing and the pool contributes only above its own
    reorder level, so the answer is a Buy for a REASON rather than a Buy because the ladder was
    never walked.
    """
    from app.models.scm import ItemClassification, ReorderLevel

    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        own, pool = _pooled_warehouses(db)
        own.segment = "dealer"
        db.flush()
        _stock(db, product, own, on_hand=20)
        _stock(db, product, pool, on_hand=12)
        db.add(
            ItemClassification(
                id=_uid(), product_id=product.id, warehouse_id=own.id, abc_class="A"
            )
        )
        db.add(
            ReorderLevel(
                id=_uid(), product_id=product.id, warehouse_id=pool.id, level=10
            )
        )
        db.flush()
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        _line(db, order, product, qty="10", required_date=date(2026, 9, 3), warehouse=own)

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        contribution = _cell(board, product.product_code, "2026-08-31")["contributions"][0]
        kinds = [(s["kind"], s["qty"], s["location"]) for s in contribution["sources"]]
        # Only the pool's headroom above its reorder level (12 - 10), never the dealer stock.
        assert kinds == [
            ("reserve", "2", pool.warehouse_code),
            ("buy", "8", None),
        ]


def test_the_board_proposes_exactly_what_the_sheet_proposes_for_the_same_line():
    """The point of the whole change: one ladder, two surfaces, the same answer.

    Not "the same shape" - the same quantities, from the same code, for a line that has a
    partial own-location cover, a pool behind it and a residual.
    """
    from datetime import datetime

    from app.models.project_so import (
        SO_STATUS_PUBLISHED,
        ProjectSalesOrder,
        ProjectSalesOrderLine,
    )
    from app.services.project_supply_service import ProjectSupplyService

    with blank_session() as db:
        company_id = _sorento(db)
        product = _product(db, f"ZZT-{_uid()[:6]}")
        own, pool = _pooled_warehouses(db)
        _stock(db, product, own, on_hand=3)
        _stock(db, product, pool, on_hand=4)
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        core_line = _line(
            db, order, product, qty="10", required_date=date(2026, 9, 3), warehouse=own
        )
        planning = ProjectSalesOrder(
            id=_uid(),
            company_id=company_id,
            project_id=None,
            provisional_ref=order.so_number,
            autocount_doc_no=order.so_number,
            so_id=order.id,
            status=SO_STATUS_PUBLISHED,
            published_at=datetime.utcnow(),
            grouping_origin="area",
        )
        db.add(planning)
        db.flush()
        db.add(
            ProjectSalesOrderLine(
                id=_uid(),
                company_id=company_id,
                project_sales_order_id=planning.id,
                line_no=1,
                product_id=product.id,
                description=f"{MARKER} line",
                qty=Decimal("10"),
                uom="UNIT",
                unit_price=Decimal("10.00"),
                amount=Decimal("100.00"),
                delivery_date=date(2026, 9, 3),
                core_sales_order_line_id=core_line.id,
            )
        )
        db.flush()

        sheet = ProjectSupplyService(db).proposal_for(planning)
        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        sheet_components = [
            (c["kind"], c["qty"], c["source_location"])
            for c in sheet["lines"][0]["components"]
        ]
        board_sources = [
            (s["kind"], s["qty"], s["location"])
            for s in _cell(board, product.product_code, "2026-08-31")["contributions"][0][
                "sources"
            ]
        ]
        assert board_sources == sheet_components
        assert ("buy", "3", None) in board_sources


def test_a_buy_the_board_cannot_avoid_still_says_borrowing_is_possible():
    """Borrow is never PROPOSED - not on the sheet either, because it needs a donor and a
    reason from a person. What the sheet does do is OFFER it, and a board that prints a bare
    Buy hides the fact that the stock exists somewhere."""
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        own = _warehouse(db, f"ZZTO{_uid()[:6]}"[:20])
        elsewhere = _warehouse(db, f"ZZTE{_uid()[:6]}"[:20])
        _stock(db, product, own, on_hand=0)
        _stock(db, product, elsewhere, on_hand=25)
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        _line(db, order, product, qty="10", required_date=date(2026, 9, 3), warehouse=own)

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        contribution = _cell(board, product.product_code, "2026-08-31")["contributions"][0]
        assert contribution["qty_proposed_buy"] == "10"
        assert contribution["qty_borrow_available"] == "25"
        assert [c["warehouse_code"] for c in contribution["borrow_candidates"]] == [
            elsewhere.warehouse_code
        ]
        assert "borrow" in contribution["sources"][-1]["reason"].lower()


# --------------------------------------------------------------------------- #
# the two nonsense sentences
# --------------------------------------------------------------------------- #


def test_a_contribution_never_names_its_own_sales_order_as_the_winner():
    """From the captain's paste: "Free stock at BRW-BB went to SO396563, which outranks this
    line 0.00 to 0.00" - printed on a contribution FROM SO396563. An order cannot outrank
    itself; when its own earlier line took the stock, that is what the sentence has to say."""
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}"[:20])
        _stock(db, product, warehouse, on_hand=10)
        order = _order(db, so_number="ZZT-SO-SELF", order_date=date(2026, 1, 1))
        _line(db, order, product, qty="10", required_date=date(2026, 9, 1), warehouse=warehouse)
        _line(db, order, product, qty="10", required_date=date(2026, 9, 2), warehouse=warehouse)

        board = _service(db).build(["ZZT-SO-SELF"], granularity="week", as_of=TODAY)

        loser = _cell(board, product.product_code, "2026-08-31")["contributions"][1]
        buy = loser["sources"][-1]
        assert buy["kind"] == "buy"
        assert "ZZT-SO-SELF" not in buy["reason"], buy["reason"]
        assert "outranks" not in buy["reason"], buy["reason"]
        assert "earlier line of this sales order" in buy["reason"]


def test_equal_ranks_are_never_described_as_one_outranking_the_other():
    """"outranks this line 0.00 to 0.00" describes a TIE as a ranking. When the scores are
    equal the tiebreaker decided it, and the sentence has to say which."""
    with blank_session() as db:
        # No policy row at all, so every score is 0.0 - the live board's situation exactly.
        product = _product(db, f"ZZT-{_uid()[:6]}")
        warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}"[:20])
        _stock(db, product, warehouse, on_hand=10)
        first = _order(db, so_number="ZZT-SO-TIE1", order_date=date(2026, 1, 1))
        second = _order(db, so_number="ZZT-SO-TIE2", order_date=date(2026, 1, 1))
        _line(db, first, product, qty="10", required_date=date(2026, 9, 3), warehouse=warehouse)
        _line(db, second, product, qty="10", required_date=date(2026, 9, 3), warehouse=warehouse)

        board = _service(db).build(
            ["ZZT-SO-TIE1", "ZZT-SO-TIE2"], granularity="week", as_of=TODAY
        )

        cell = _cell(board, product.product_code, "2026-08-31")
        assert [c["rank_score"] for c in cell["contributions"]] == [0.0, 0.0]
        buy = cell["contributions"][1]["sources"][-1]
        assert "outranks" not in buy["reason"], buy["reason"]
        assert "ZZT-SO-TIE1" in buy["reason"]
        assert "rank" in buy["reason"].lower() and "sales order number" in buy["reason"]
