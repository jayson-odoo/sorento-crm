"""Narrowing the sales-order list to the orders somebody is actually looking for.

11,626 orders are in the book and 11,006 of them are absorbed history. Status, priority and
source were the only filters, and none of them answers the three questions people ask of this
screen: what came in over these dates, what belongs to this customer, and what is still owed.

Two rules the existing filters already follow and these keep:

* a value the filter does not understand matches NOTHING rather than being ignored, because a
  list quietly showing everything under a heading that claims it is narrowed is worse than an
  empty one;
* "still outstanding" is the SAME rule the plan uses (`app.services.scm.demand`), so this
  screen and the netting cannot disagree about which orders are owed.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.scm.sales_order_service import SalesOrderService
from tests._pg_fixture import pg_session, unique_code

MARKER = "ZZTSOF"


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def world(db):
    cat = ProductCategory(id=_u(), category_code=unique_code(MARKER),
                          category_name=f"{MARKER} cat")
    uom = UnitOfMeasure(id=_u(), uom_code=unique_code("U")[:20], uom_name=f"{MARKER} u")
    db.add_all([cat, uom])
    db.flush()
    product = Product(id=_u(), product_code=unique_code("P"), product_name=f"{MARKER} p",
                      category_id=cat.id, base_uom_id=uom.id, list_price=0,
                      is_active=True, is_discontinued=False)
    acme = Customer(id=_u(), customer_code=unique_code("C"), customer_name=f"{MARKER} Acme")
    other = Customer(id=_u(), customer_code=unique_code("C"), customer_name=f"{MARKER} Other")
    db.add_all([product, acme, other])
    db.flush()
    return {"product": product, "acme": acme, "other": other}


def _order(db, world, *, when: date, customer, ordered=100, delivered=0,
           purchasing_status="not_reviewed", demand_class="project") -> SalesOrder:
    so = SalesOrder(id=_u(), so_number=unique_code(MARKER), status="open",
                    order_date=when, customer_id=customer.id, demand_class=demand_class)
    db.add(so)
    db.flush()
    db.add(SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=world["product"].id,
        qty_ordered=ordered, qty_delivered=delivered, line_status="open",
        purchasing_status=purchasing_status, required_date=when,
    ))
    db.flush()
    return so


def _numbers(db, **filters) -> set[str]:
    """The SO numbers this filter returns, limited to rows this test seeded."""
    out = SalesOrderService(db).list(
        page=1, limit=200, sort="so_number", direction="asc",
        query=MARKER, status=None, priority=None, **filters,
    )
    return {row["so_number"] for row in out["data"]}


# --------------------------------------------------------------------------- #
# dates
# --------------------------------------------------------------------------- #

def test_a_date_range_keeps_the_orders_placed_inside_it_including_both_ends(db, world):
    early = _order(db, world, when=date(2026, 1, 10), customer=world["acme"])
    inside = _order(db, world, when=date(2026, 3, 1), customer=world["acme"])
    edge = _order(db, world, when=date(2026, 3, 31), customer=world["acme"])
    late = _order(db, world, when=date(2026, 5, 2), customer=world["acme"])

    got = _numbers(db, date_from=date(2026, 3, 1), date_to=date(2026, 3, 31))

    assert got == {inside.so_number, edge.so_number}
    assert early.so_number not in got and late.so_number not in got


def test_one_end_of_the_range_is_enough(db, world):
    early = _order(db, world, when=date(2026, 1, 10), customer=world["acme"])
    late = _order(db, world, when=date(2026, 5, 2), customer=world["acme"])

    assert _numbers(db, date_from=date(2026, 3, 1)) == {late.so_number}
    assert _numbers(db, date_to=date(2026, 3, 1)) == {early.so_number}


def test_an_order_with_no_date_is_not_claimed_by_a_range(db, world):
    """Absorbed rows can arrive undated. Including one in "January" states a fact we do not
    have; excluding it is the honest answer, and no filter still shows it."""
    undated = _order(db, world, when=None, customer=world["acme"])

    assert undated.so_number not in _numbers(db, date_from=date(2020, 1, 1))
    assert undated.so_number in _numbers(db)


# --------------------------------------------------------------------------- #
# customer
# --------------------------------------------------------------------------- #

def test_a_customer_filter_keeps_only_that_customers_orders(db, world):
    mine = _order(db, world, when=date(2026, 3, 1), customer=world["acme"])
    theirs = _order(db, world, when=date(2026, 3, 1), customer=world["other"])

    got = _numbers(db, customer_code=world["acme"].customer_code)

    assert got == {mine.so_number}
    assert theirs.so_number not in got


def test_a_customer_code_nobody_holds_matches_nothing(db, world):
    _order(db, world, when=date(2026, 3, 1), customer=world["acme"])

    assert _numbers(db, customer_code="ZZTSOF-NO-SUCH-CODE") == set()


def test_the_code_is_matched_whatever_its_casing_or_padding(db, world):
    """The dropdown supplies the code verbatim, but a code typed or pasted by hand arrives
    with the case and spacing of wherever it was copied from."""
    mine = _order(db, world, when=date(2026, 3, 1), customer=world["acme"])

    got = _numbers(db, customer_code=f"  {world['acme'].customer_code.lower()} ")

    assert got == {mine.so_number}


# --------------------------------------------------------------------------- #
# still outstanding
# --------------------------------------------------------------------------- #

def test_outstanding_keeps_the_orders_still_owed(db, world):
    owed = _order(db, world, when=date(2026, 3, 1), customer=world["acme"],
                  ordered=100, delivered=40)
    shipped = _order(db, world, when=date(2026, 3, 1), customer=world["acme"],
                     ordered=100, delivered=100)

    got = _numbers(db, outstanding=True)

    assert owed.so_number in got
    assert shipped.so_number not in got


def test_outstanding_reads_the_same_rule_as_the_plan(db, world):
    """A line CS marked covered is not demand, so this screen must not call it outstanding.
    One rule, in `app.services.scm.demand`, or the list and the plan disagree."""
    covered = _order(db, world, when=date(2026, 3, 1), customer=world["acme"],
                     ordered=100, purchasing_status="covered")

    assert covered.so_number not in _numbers(db, outstanding=True)


def test_asking_for_outstanding_false_is_the_same_as_not_asking(db, world):
    """An unticked box must not narrow anything. Otherwise clearing a filter changes the
    list, which reads as data appearing and disappearing on its own."""
    _order(db, world, when=date(2026, 3, 1), customer=world["acme"], ordered=100, delivered=100)

    assert _numbers(db, outstanding=False) == _numbers(db)


def test_the_filters_combine(db, world):
    want = _order(db, world, when=date(2026, 3, 15), customer=world["acme"],
                  ordered=100, delivered=10)
    _order(db, world, when=date(2026, 3, 15), customer=world["other"], ordered=100)
    _order(db, world, when=date(2026, 9, 1), customer=world["acme"], ordered=100)
    _order(db, world, when=date(2026, 3, 16), customer=world["acme"],
           ordered=100, delivered=100)

    got = _numbers(
        db,
        date_from=date(2026, 3, 1),
        date_to=date(2026, 3, 31),
        customer_code=world["acme"].customer_code,
        outstanding=True,
    )

    assert got == {want.so_number}


# --------------------------------------------------------------------------- #
# demand class (Type filter)
# --------------------------------------------------------------------------- #

def test_demand_class_project_keeps_only_project_orders(db, world):
    project = _order(db, world, when=date(2026, 3, 1), customer=world["acme"],
                     demand_class="project")
    retail = _order(db, world, when=date(2026, 3, 1), customer=world["acme"],
                    demand_class="retail")

    got = _numbers(db, demand_class="project")

    assert project.so_number in got
    assert retail.so_number not in got


def test_demand_class_retail_keeps_only_retail_orders(db, world):
    project = _order(db, world, when=date(2026, 3, 1), customer=world["acme"],
                     demand_class="project")
    retail = _order(db, world, when=date(2026, 3, 1), customer=world["acme"],
                    demand_class="retail")

    got = _numbers(db, demand_class="retail")

    assert retail.so_number in got
    assert project.so_number not in got


def test_demand_class_unclassified_reads_null_not_a_stored_value(db, world):
    """`unclassified` is not a third row in `DEMAND_CLASSES` - it means the column is NULL,
    which is what "nobody has classified this order" actually looks like in the data."""
    classified = _order(db, world, when=date(2026, 3, 1), customer=world["acme"],
                        demand_class="project")
    unclassified = _order(db, world, when=date(2026, 3, 1), customer=world["acme"],
                          demand_class=None)

    got = _numbers(db, demand_class="unclassified")

    assert unclassified.so_number in got
    assert classified.so_number not in got


def test_no_demand_class_filter_narrows_nothing(db, world):
    project = _order(db, world, when=date(2026, 3, 1), customer=world["acme"],
                     demand_class="project")
    unclassified = _order(db, world, when=date(2026, 3, 1), customer=world["acme"],
                          demand_class=None)

    got = _numbers(db, demand_class=None)

    assert {project.so_number, unclassified.so_number} <= got


def test_an_unrecognised_demand_class_matches_nothing(db, world):
    """Same rule as `source`/`status`: a value this filter does not understand must not be
    silently ignored, or the list shows the whole book under a heading claiming it is
    narrowed."""
    _order(db, world, when=date(2026, 3, 1), customer=world["acme"], demand_class="project")

    assert _numbers(db, demand_class="not-a-real-class") == set()


# --------------------------------------------------------------------------- #
# a stable order, or paging is meaningless
# --------------------------------------------------------------------------- #

def test_the_sort_is_always_made_total_by_id():
    """Asserted on the ORDER BY rather than on returned rows.

    With a handful of seeded rows Postgres happens to return a consistent order, so a test
    that compares two fetches passes whether or not the tiebreaker exists. The rule is what
    has to hold: whatever column the caller sorts on, `id` follows it.
    """
    from app.models.order import SalesOrder
    from app.services.scm.sales_order_service import _order_by

    cols = {"so_number": SalesOrder.so_number, "order_date": SalesOrder.order_date}

    for sort in (None, "", "so_number", "order_date", "unknown-column"):
        for direction in ("asc", "desc"):
            clause = _order_by(cols, sort, direction)
            assert len(clause) == 2, f"no tiebreaker for sort={sort!r} dir={direction}"
            assert "sales_orders.id" in str(clause[-1]), (
                f"the tiebreaker for sort={sort!r} dir={direction} is not the id"
            )
            # Both halves point the same way, or the second page of a descending list is
            # ordered against the first.
            assert str(clause[0]).endswith(direction.upper() if direction == "asc" else "DESC")
            assert str(clause[-1]).endswith("ASC" if direction == "asc" else "DESC")


def test_page_one_and_page_two_partition_the_result(db, world):
    """The consequence the rule exists for: no row on both pages, none on neither."""
    when = date(2026, 3, 1)
    for _ in range(6):
        _order(db, world, when=when, customer=world["acme"])

    def ids(page: int) -> list[str]:
        out = SalesOrderService(db).list(
            page=page, limit=3, sort=None, direction="desc",
            query=MARKER, status=None, priority=None,
        )
        return [row["id"] for row in out["data"]]

    first, second = ids(1), ids(2)

    assert not set(first) & set(second), "a row appears on both pages"
    assert len(set(first) | set(second)) == 6, "a row appears on neither page"
