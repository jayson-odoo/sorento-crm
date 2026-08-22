"""Searching the fulfilment-planning worklist, including BY PRODUCT.

Captain's request, 18 August 2026: "i should be able to search by product, by sales order,
by customer, to shrink the dataset i am viewing". One box, `query`, matching any of them -
a planner shrinking a list should not have to learn our field taxonomy first.

What the box matched BEFORE this change: the sales-order number, the customer name and the
project label (the Order Inquiry project string on a core order; the project code or title
on an authored record), plus an authored record's own reference, AutoCount document number
and area group. **Not the product** - the product is the one that needs the LINES, which is
why it is the expensive arm and why it has its own tests here.

The product arm has four obligations, and each one is a test below:

1. **Both arms, or the same search returns different kinds of row inconsistently.** A core
   sales order matches on its core lines' products; an authored record with no core sales
   order matches on its own lines' products.
2. **It must not multiply rows.** An order with six matching lines is ONE row. The match is
   a membership test against a separately-computed id set, never a join that fans out, and
   the aggregates the row prints (`line_count`, `outstanding_qty`, `earliest_required_date`)
   are the whole order's whether the search matched one line or six.
3. **It obeys the SAME open-line predicate as the rest of the worklist.** An order whose
   only matching line is closed, delivered or covered does not appear. A filter that
   surfaces an order on the strength of a line the same screen calls finished is the kind of
   quiet inconsistency that makes a planner stop trusting the box.
4. **It composes.** Search narrows what `review_state`, `project_id`, `sales_order_id`,
   `sort` and `dir` then act on, and changes none of their guarantees.

TEST-FIRST. Written before the product arm existed, so the red state was every product
needle returning an empty list - the search running and finding nothing, which is the honest
"not implemented" for a filter.

Postgres, blank scratch schema via `tests/_pg_fixture.py::blank_session`, rolled back at
teardown. Seeding helpers are imported from the sibling files; every row carries a marker.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.models.base import company_scope
from app.services import project_seed_service
from app.services.project_so_adoption_service import ProjectSOAdoptionService
from app.services.project_so_reconciliation_service import ProjectSOReconciliationService

from ._pg_fixture import blank_session
from .test_fulfilment_planning_worklist import (
    _authored_line,
    _authored_order,
    _project,
    _user,
)
from .test_project_so_adoption import (
    MARKER,
    _core_line,
    _core_order,
    _customer,
    _product,
    _sorento,
    _uid,
    _warehouse,
)

D_MID = date(2026, 6, 9)

#: Distinctive enough that no other seeded row can answer to it by accident.
WANTED_CODE = f"{MARKER}-ITEM-WANTED"
WANTED_NAME = "Chrome basin mixer WANTEDNAME"
OTHER_CODE = f"{MARKER}-ITEM-OTHER"


def _named_product(db, *, code: str, name: str):
    row = _product(db, code=code)
    row.product_name = name
    db.flush()
    return row


def _list(db, **kwargs):
    return ProjectSOReconciliationService(db).list_fulfilment_planning(**kwargs)


def _numbers(body) -> set:
    return {row["so_number"] for row in body["data"] if row["so_number"]}


def _ids(body) -> set:
    return {row["id"] for row in body["data"] if row["id"]}


@pytest.fixture()
def world():
    """One core order carrying the wanted product, one carrying something else, one whose
    ONLY wanted line is finished, and one authored record carrying the wanted product."""
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        with company_scope(db, frozenset({company_id})):
            wanted = _named_product(db, code=WANTED_CODE, name=WANTED_NAME)
            other = _named_product(db, code=OTHER_CODE, name=f"{MARKER} something else")
            warehouse = _warehouse(db, company_id)

            hit = _core_order(
                db,
                company_id,
                customer=_customer(db, company_id, f"{MARKER} HIT CUSTOMER"),
                internal_note="Order Inquiry project: HIT PROJECT",
            )
            hit.so_number = f"{MARKER}-SO-HIT"
            _core_line(db, hit, wanted, warehouse=warehouse, required_date=D_MID)
            _core_line(db, hit, other, warehouse=warehouse, required_date=D_MID)

            # Six matching lines: the row must still be ONE row, with the whole order's
            # numbers on it.
            many = _core_order(db, company_id)
            many.so_number = f"{MARKER}-SO-MANY"
            for _ in range(6):
                _core_line(
                    db, many, wanted, warehouse=warehouse, required_date=D_MID, qty_ordered="3"
                )
            _core_line(
                db, many, other, warehouse=warehouse, required_date=D_MID, qty_ordered="3"
            )

            miss = _core_order(db, company_id)
            miss.so_number = f"{MARKER}-SO-MISS"
            _core_line(db, miss, other, warehouse=warehouse, required_date=D_MID)

            # Its only wanted line is CLOSED; it stays outstanding on another product, so
            # it is on the worklist but must NOT answer to the wanted needle.
            finished = _core_order(db, company_id)
            finished.so_number = f"{MARKER}-SO-FINISHED"
            _core_line(
                db, finished, wanted, warehouse=warehouse, required_date=D_MID,
                line_status="closed",
            )
            _core_line(
                db, finished, wanted, warehouse=warehouse, required_date=D_MID,
                purchasing_status="covered",
            )
            _core_line(
                db, finished, wanted, warehouse=warehouse, required_date=D_MID,
                qty_ordered="9", qty_delivered="9",
            )
            _core_line(db, finished, other, warehouse=warehouse, required_date=D_MID)

            owner = _user(db)
            project = _project(db, company_id, owner)
            authored = _authored_order(db, project)
            _authored_line(db, authored, wanted, line_no=1)
            _authored_line(db, authored, other, line_no=2)

            authored_miss = _authored_order(db, project)
            _authored_line(db, authored_miss, other, line_no=1)
            db.flush()

            yield db, {
                "hit": hit,
                "many": many,
                "miss": miss,
                "finished": finished,
                "authored": authored,
                "authored_miss": authored_miss,
                "wanted": wanted,
            }


# --------------------------------------------------------------------------- #
# what the one box matches                                                    #
# --------------------------------------------------------------------------- #


def test_searching_by_item_code_finds_the_orders_owing_that_product(world):
    db, seeded = world

    body = _list(db, query=WANTED_CODE, limit=50)

    assert _numbers(body) == {seeded["hit"].so_number, seeded["many"].so_number}
    assert _ids(body) == {seeded["authored"].id}
    assert body["pagination"]["total"] == 3


def test_searching_by_product_name_finds_the_same_orders(world):
    db, seeded = world

    body = _list(db, query="WANTEDNAME", limit=50)

    assert _numbers(body) == {seeded["hit"].so_number, seeded["many"].so_number}
    assert _ids(body) == {seeded["authored"].id}


def test_the_box_still_matches_the_sales_order_number(world):
    db, seeded = world

    body = _list(db, query=seeded["hit"].so_number, limit=50)

    assert _numbers(body) == {seeded["hit"].so_number}


def test_the_box_still_matches_the_customer(world):
    db, seeded = world

    body = _list(db, query="HIT CUSTOMER", limit=50)

    assert _numbers(body) == {seeded["hit"].so_number}


def test_the_box_still_matches_the_project_label(world):
    db, seeded = world

    body = _list(db, query="HIT PROJECT", limit=50)

    assert _numbers(body) == {seeded["hit"].so_number}


def test_a_needle_matching_nothing_shrinks_the_list_to_nothing(world):
    """The failure this guards is a filter that silently falls back to no filter, which
    reads as "my search did nothing" and is worse than an empty page."""
    db, _seeded = world

    body = _list(db, query=f"{MARKER}-NO-SUCH-THING", limit=50)

    assert body["data"] == []
    assert body["pagination"]["total"] == 0
    assert body["empty"] is True


# --------------------------------------------------------------------------- #
# the product arm's three hazards                                             #
# --------------------------------------------------------------------------- #


def test_an_order_with_six_matching_lines_is_still_one_row_with_the_whole_order_on_it(world):
    db, seeded = world

    searched = _list(db, query=WANTED_CODE, limit=50)["data"]
    rows = [row for row in searched if row["so_number"] == seeded["many"].so_number]
    assert len(rows) == 1

    unsearched = next(
        row
        for row in _list(db, limit=50)["data"]
        if row["so_number"] == seeded["many"].so_number
    )
    # Searching narrows WHICH rows come back, never what a row says: seven open lines and
    # their whole quantity, not the six the needle happened to match.
    assert rows[0]["line_count"] == unsearched["line_count"] == 7
    assert rows[0]["outstanding_qty"] == unsearched["outstanding_qty"]
    assert rows[0]["earliest_required_date"] == unsearched["earliest_required_date"]


def test_an_order_whose_only_matching_line_is_finished_does_not_answer_to_it(world):
    db, seeded = world

    body = _list(db, query=WANTED_CODE, limit=50)
    assert seeded["finished"].so_number not in _numbers(body)

    # It IS on the worklist - it is still outstanding on another product - so its absence
    # above is the open-line predicate doing its job, not the order having gone away.
    assert seeded["finished"].so_number in _numbers(_list(db, limit=50))


def test_an_order_that_does_not_carry_the_product_never_appears(world):
    db, seeded = world

    body = _list(db, query=WANTED_CODE, limit=50)

    assert seeded["miss"].so_number not in _numbers(body)
    assert seeded["authored_miss"].id not in _ids(body)


# --------------------------------------------------------------------------- #
# it composes with everything already there                                   #
# --------------------------------------------------------------------------- #


def test_a_product_search_composes_with_the_review_state_filter(world):
    db, seeded = world
    ProjectSOAdoptionService(db).adopt(seeded["many"].id, actor_user_id=None)
    db.flush()

    not_started = _list(db, query=WANTED_CODE, review_state="not_started", limit=50)
    assert _numbers(not_started) == {seeded["hit"].so_number}
    assert not_started["pagination"]["total"] == 1

    needs_review = _list(db, query=WANTED_CODE, review_state="needs_cs_review", limit=50)
    assert _numbers(needs_review) == {seeded["many"].so_number}

    awaiting = _list(db, query=WANTED_CODE, review_state="awaiting_reconciliation", limit=50)
    assert _ids(awaiting) == {seeded["authored"].id}


def test_a_product_search_composes_with_a_non_default_sort_and_stays_total(world):
    db, seeded = world

    ascending = _list(db, query=WANTED_CODE, sort="so_number", dir="asc", limit=50)["data"]
    descending = _list(db, query=WANTED_CODE, sort="so_number", dir="desc", limit=50)["data"]

    numbers = [row["so_number"] for row in ascending if row["so_number"]]
    assert numbers == sorted(numbers)
    # The authored record has no sales-order number, so it sorts LAST in BOTH directions
    # rather than leading the descending page.
    assert ascending[-1]["id"] == seeded["authored"].id
    assert descending[-1]["id"] == seeded["authored"].id

    paged = []
    for page in (1, 2):
        paged.extend(
            row["so_number"] or row["id"]
            for row in _list(
                db, query=WANTED_CODE, sort="so_number", dir="desc", page=page, limit=2
            )["data"]
        )
    assert len(paged) == len(set(paged)) == 3
    assert paged == [row["so_number"] or row["id"] for row in descending]


def test_a_product_search_composes_with_the_sales_order_filter(world):
    db, seeded = world

    body = _list(db, query=WANTED_CODE, sales_order_id=str(seeded["hit"].id), limit=50)

    assert _numbers(body) == {seeded["hit"].so_number}
    assert body["pagination"]["total"] == 1


def test_a_product_search_is_company_scoped_like_every_other_read(world):
    """The product arm is a second query, so it is a second place scoping could be missed -
    and a missed scope there leaks the existence of another company's order by name."""
    db, seeded = world
    from app.models.company import Company

    other_company_id = _uid()
    db.add(Company(id=other_company_id, name=f"{MARKER} other", code=f"ZZT{_uid()[:6]}"))
    db.flush()
    with company_scope(db, frozenset({other_company_id})):
        their_product = _named_product(db, code=WANTED_CODE + "-X", name=WANTED_NAME)
        their_warehouse = _warehouse(db, other_company_id)
        theirs = _core_order(db, other_company_id)
        theirs.so_number = f"{MARKER}-SO-THEIRS"
        _core_line(db, theirs, their_product, warehouse=their_warehouse, required_date=D_MID)
        db.flush()

    body = _list(db, query="WANTEDNAME", limit=50)
    assert theirs.so_number not in _numbers(body)
    assert body["pagination"]["total"] == len(body["data"])
