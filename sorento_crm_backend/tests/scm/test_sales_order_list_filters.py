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
from app.models.sales_agent import SalesAgent
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
    # The category and the unit ride along so the search tests can seed a SECOND product
    # (one order carries it, one does not) without restating the chain.
    return {"product": product, "acme": acme, "other": other, "category": cat, "uom": uom}


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


def _search(db, term: str) -> set[str]:
    """The SO numbers the free-text search returns for `term`."""
    out = SalesOrderService(db).list(
        page=1, limit=200, sort="so_number", direction="asc",
        query=term, status=None, priority=None,
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
# free-text search
# --------------------------------------------------------------------------- #
# The four things a person holds when they come looking for an order: the document number,
# who it is for, WHAT IS ON IT, and WHO SOLD IT. The first two were matched; the last two
# were not, so "which orders have that sink on them" and "show me Eric's orders" both
# answered nothing. Matched with EXISTS subqueries rather than joins - an order with three
# matching lines is one row in the result, not three.


def _product(db, world, code_stem: str, name: str) -> Product:
    p = Product(id=_u(), product_code=unique_code(code_stem), product_name=name,
                category_id=world["category"].id, base_uom_id=world["uom"].id,
                list_price=0, is_active=True, is_discontinued=False)
    db.add(p)
    db.flush()
    return p


def _agent(db, code: str, person_label=None) -> SalesAgent:
    a = SalesAgent(id=_u(), sales_agent=code, person_label=person_label, is_active=True,
                   source="manual")
    db.add(a)
    db.flush()
    return a


def _order_with(db, world, *, product=None, agent=None) -> SalesOrder:
    so = SalesOrder(id=_u(), so_number=unique_code(MARKER), status="open",
                    order_date=date(2026, 3, 1), customer_id=world["acme"].id,
                    sales_agent_id=agent.id if agent else None)
    db.add(so)
    db.flush()
    db.add(SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=(product or world["product"]).id,
        qty_ordered=10, qty_delivered=0, line_status="open",
        purchasing_status="not_reviewed", required_date=date(2026, 3, 1),
    ))
    db.flush()
    return so


def test_the_search_finds_an_order_by_a_lines_product_code(db, world):
    wanted = _product(db, world, "SINKX", f"{MARKER} sink")
    on_it = _order_with(db, world, product=wanted)
    not_on_it = _order_with(db, world)

    got = _search(db, wanted.product_code[-8:])

    assert on_it.so_number in got
    assert not_on_it.so_number not in got


def test_the_search_finds_an_order_by_a_lines_product_name(db, world):
    wanted = _product(db, world, "P", f"{MARKER} Granite Sink 900")
    on_it = _order_with(db, world, product=wanted)
    not_on_it = _order_with(db, world)

    got = _search(db, "granite sink 900")

    assert on_it.so_number in got
    assert not_on_it.so_number not in got


def test_an_order_is_returned_once_however_many_of_its_lines_match(db, world):
    """EXISTS, not a join: a matching product on three lines is still one order."""
    wanted = _product(db, world, "P", f"{MARKER} Repeated Item")
    so = _order_with(db, world, product=wanted)
    for _ in range(2):
        db.add(SalesOrderLine(
            id=_u(), sales_order_id=so.id, product_id=wanted.id, qty_ordered=5,
            qty_delivered=0, line_status="open", purchasing_status="not_reviewed",
        ))
    db.flush()

    out = SalesOrderService(db).list(
        page=1, limit=200, sort="so_number", direction="asc",
        query="Repeated Item", status=None, priority=None,
    )

    numbers = [row["so_number"] for row in out["data"]]
    assert numbers.count(so.so_number) == 1
    assert out["pagination"]["total"] == 1


def test_the_search_finds_an_order_by_its_agent_code(db, world):
    eric = _agent(db, unique_code("ERICNG"))
    his = _order_with(db, world, agent=eric)
    hers = _order_with(db, world)

    got = _search(db, "ERICNG")

    assert his.so_number in got
    assert hers.so_number not in got


def test_the_search_finds_an_order_by_the_person_behind_the_code(db, world):
    """The codes are `SEAN I` / `SEAN III`; the person is what anybody actually types."""
    sean = _agent(db, unique_code("S3"), person_label=f"{MARKER} Sean Lim")
    his = _order_with(db, world, agent=sean)
    hers = _order_with(db, world)

    got = _search(db, "sean lim")

    assert his.so_number in got
    assert hers.so_number not in got


def test_the_search_still_finds_an_order_by_number_and_customer(db, world):
    """The two that already worked keep working - widening a search must not narrow it."""
    so = _order_with(db, world)

    assert so.so_number in _search(db, so.so_number)
    assert so.so_number in _search(db, world["acme"].customer_name)


def test_a_term_nothing_carries_matches_nothing(db, world):
    _order_with(db, world)

    assert _search(db, "ZZTSOF-NOTHING-CARRIES-THIS") == set()


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
            # ordered against the first. The sorted column also carries NULLS LAST, so an
            # undated row never reads as the newest thing in the book under DESC.
            assert str(clause[0]).endswith(
                f"{direction.upper()} NULLS LAST"
            ), f"no NULLS LAST on the sorted column for sort={sort!r} dir={direction}"
            assert str(clause[-1]).endswith("ASC" if direction == "asc" else "DESC")


def test_order_date_desc_puts_a_null_dated_order_last_not_first(db, world):
    """Postgres defaults `ORDER BY ... DESC` to NULLS FIRST. Left alone, that would put a row
    nobody dated at the very TOP of the list's shipped default (latest Document date first,
    PLAN-listing-view-memory) - read as the newest thing in the book rather than as the
    unfiled row it is. Belongs last in both directions.
    """
    early = _order(db, world, when=date(2026, 3, 1), customer=world["acme"])
    late = _order(db, world, when=date(2026, 9, 1), customer=world["acme"])
    undated = _order(db, world, when=None, customer=world["acme"])

    desc = SalesOrderService(db).list(
        page=1, limit=200, sort="order_date", direction="desc",
        query=MARKER, status=None, priority=None,
    )
    desc_numbers = [row["so_number"] for row in desc["data"]]
    assert desc_numbers == [late.so_number, early.so_number, undated.so_number]

    asc = SalesOrderService(db).list(
        page=1, limit=200, sort="order_date", direction="asc",
        query=MARKER, status=None, priority=None,
    )
    asc_numbers = [row["so_number"] for row in asc["data"]]
    assert asc_numbers == [early.so_number, late.so_number, undated.so_number]


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
