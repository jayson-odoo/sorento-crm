"""Sorting the fulfilment-planning worklist, on every column the screen renders.

Captain's request, 18 August 2026: "all columns should be sortable". Contract:
`documentation/plans/scm/PLAN-fulfilment-planning-from-autocount-so.md` section 6, amended
in place with the closed set and the null rule.

The worklist is a UNION of two arms over two different tables, and it is PAGED, so a sort
has three obligations rather than one:

1. **It is applied to the union, not per arm.** A core sales order and an authored planning
   record interleave on every field, and sorting each arm separately would produce two
   sorted lists concatenated - which looks sorted at the top of page 1 and is wrong
   everywhere else.
2. **It is TOTAL and STABLE.** Every sort ends in the same final tiebreaker (the human key,
   then the row's own identity), so a tie breaks the same way on page 2 as on page 1. A
   non-total order is what puts one row on two pages and another on none, and it is
   invisible until somebody counts.
3. **NULLS ARE LAST IN BOTH DIRECTIONS.** Postgres puts them last ascending and first
   descending, which means reversing a sort would march every row that has no value to the
   top - "sort by earliest required date, descending" would answer with the orders that
   have no date at all. A missing value is not an extreme value, so it sorts last whichever
   way the arrow points.

A field one arm cannot supply is not a reason to hide that arm: an authored record has no
sales-order number and a not-started row has no reference, and both still appear, at the
end, by the null rule.

TEST-FIRST. Written before `sort` / `dir` existed on the service, so the red state was
`TypeError: list_fulfilment_planning() got an unexpected keyword argument 'sort'` on every
test here - the parameter's absence, not a wrong answer.

Postgres, blank scratch schema via `tests/_pg_fixture.py::blank_session`, rolled back at
teardown. Seeding helpers are imported from the sibling adoption and worklist files; every
row carries a marker and nothing is borrowed.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.models.base import company_scope
from app.services import project_seed_service
from app.services.project_so_adoption_service import ProjectSOAdoptionService
from app.services.project_so_reconciliation_service import (
    SORTABLE_FIELDS,
    ProjectSOReconciliationService,
)

from ._pg_fixture import blank_session
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
from .test_fulfilment_planning_worklist import (
    _authored_line,
    _authored_order,
    _project,
    _user,
)

D_EARLY = date(2025, 1, 6)
D_MID = date(2026, 6, 9)
D_LATE = date(2027, 11, 30)


def _list(db, **kwargs):
    return ProjectSOReconciliationService(db).list_fulfilment_planning(**kwargs)


def _key(row) -> str:
    """A SUBJECT's identity, whichever arm it came from.

    The core sales order when there is one - a planned core order is the same subject it
    was before somebody planned it, and it must not count as two - else the planning
    record, which is all an arm-2 row has.
    """
    return str(row["sales_order_id"] or row["id"])


def _world(db, company_id):
    """Four subjects, chosen so every sortable field has both values AND nulls.

    * A - a core order nobody has planned: a customer, a project string, the earliest date,
      the smallest quantity, one line. No reference, no area group, no PO, no updated_at.
    * B - a core order that HAS been adopted: a reference (its own sales-order number), a
      later date, a bigger quantity, two lines, an updated_at, Needs CS review.
    * C - a core order with NO customer, NO project string and NO required date at all: the
      null side of three fields at once, and the biggest quantity.
    * D - an authored planning record with no core sales order: no sales-order number, but a
      registered project, an area group, a customer PO and its own reference.
    """
    owner = _user(db)
    project = _project(db, company_id, owner)
    product = _product(db)
    warehouse = _warehouse(db, company_id)

    a = _core_order(
        db,
        company_id,
        customer=_customer(db, company_id, f"{MARKER} AAA CUSTOMER"),
        internal_note="Order Inquiry project: AAA PROJECT",
    )
    a.so_number = f"{MARKER}-SO-AAA"
    _core_line(db, a, product, warehouse=warehouse, required_date=D_EARLY, qty_ordered="5")

    b = _core_order(
        db,
        company_id,
        customer=_customer(db, company_id, f"{MARKER} BBB CUSTOMER"),
        internal_note="Order Inquiry project: BBB PROJECT",
    )
    b.so_number = f"{MARKER}-SO-BBB"
    _core_line(db, b, product, warehouse=warehouse, required_date=D_MID, qty_ordered="50")
    _core_line(db, b, product, warehouse=warehouse, required_date=D_LATE, qty_ordered="50")

    c = _core_order(db, company_id, customer=None, internal_note=None)
    c.so_number = f"{MARKER}-SO-CCC"
    for _ in range(3):
        _core_line(
            db, c, product, warehouse=warehouse, required_date=None, qty_ordered="500"
        )

    d = _authored_order(db, project)
    d.area_group = "TOWER"
    _authored_line(db, d, product, qty="7", delivery_date=D_LATE)
    db.flush()

    ProjectSOAdoptionService(db).adopt(b.id, actor_user_id=None)
    db.flush()
    return {"a": a, "b": b, "c": c, "d": d, "project": project}


@pytest.fixture()
def world():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        with company_scope(db, frozenset({company_id})):
            yield db, _world(db, company_id)


# --------------------------------------------------------------------------- #
# the closed set is declared twice, so it is asserted once                     #
# --------------------------------------------------------------------------- #


def test_the_route_and_the_service_agree_on_the_sortable_set():
    """FastAPI cannot build a `Literal` from a runtime set, so the route restates the
    names. Restating is fine; DRIFTING is not - a name the route accepts and the service
    refuses is a 422 on a column the grid was told it could sort by."""
    import typing

    from app.api.v1.projects.fulfilment_planning import list_fulfilment_planning

    annotation = typing.get_type_hints(list_fulfilment_planning)["sort"]
    # Optional[Literal[...]] -> the Literal arm's values.
    literal_arm = next(
        arg for arg in typing.get_args(annotation) if typing.get_args(arg)
    )
    assert set(typing.get_args(literal_arm)) == set(SORTABLE_FIELDS)


# --------------------------------------------------------------------------- #
# every field, both directions                                                #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("field", sorted(SORTABLE_FIELDS))
@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_every_sortable_field_orders_its_values_and_puts_nulls_last(
    world, field, direction
):
    db, _seeded = world

    rows = _list(db, sort=field, dir=direction, limit=50)["data"]
    assert len(rows) == 4

    values = [row[field] for row in rows]
    present = [value for value in values if value is not None]
    # Nulls last WHICHEVER WAY THE ARROW POINTS: a row with no value is not the largest
    # value and it is not the smallest one either.
    assert values[: len(present)] == present, (
        f"{field} {direction}: a null sorted before a value"
    )

    comparable = [_comparable(field, value) for value in present]
    if direction == "asc":
        assert comparable == sorted(comparable)
    else:
        assert comparable == sorted(comparable, reverse=True)


@pytest.mark.parametrize("field", sorted(SORTABLE_FIELDS))
@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_the_union_still_returns_each_subject_exactly_once_under_every_sort(
    world, field, direction
):
    db, seeded = world

    body = _list(db, sort=field, dir=direction, limit=50)
    keys = [_key(row) for row in body["data"]]

    assert len(keys) == len(set(keys)) == 4
    assert body["pagination"]["total"] == 4
    assert set(keys) == {
        str(seeded["a"].id),
        str(seeded["b"].id),
        str(seeded["c"].id),
        str(seeded["d"].id),
    }


#: The order the pills MOVE in, which is what `review_state` sorts by. Restated here rather
#: than imported so the test asserts the intended rule instead of echoing the code's own.
_WORKFLOW_ORDER = [
    "not_started",
    "awaiting_reconciliation",
    "needs_cs_review",
    "confirmed",
]


def _comparable(field, value):
    """The documented sort key for a field: quantities as numbers, review states in
    workflow order, text case-folded (or `Zebra` sorts above `apple`)."""
    if field == "outstanding_qty":
        return Decimal(str(value))
    if field == "review_state":
        return _WORKFLOW_ORDER.index(value)
    return value.casefold() if isinstance(value, str) else value


# --------------------------------------------------------------------------- #
# the two fields whose order is not their raw value                           #
# --------------------------------------------------------------------------- #


def test_review_state_sorts_in_workflow_order_not_alphabetical_order(world):
    db, _seeded = world

    ascending = [row["review_state"] for row in _list(db, sort="review_state", limit=50)["data"]]

    # Alphabetically this would be awaiting, confirmed, needs, not_started - which reads as
    # a random order to the person looking at the pills. The order that means something is
    # the order the work moves in.
    assert ascending == [
        "not_started",
        "not_started",
        "awaiting_reconciliation",
        "needs_cs_review",
    ]

    descending = [
        row["review_state"] for row in _list(db, sort="review_state", dir="desc", limit=50)["data"]
    ]
    assert descending == list(reversed(ascending))


def test_line_count_sorts_on_the_number_the_row_actually_shows(world):
    db, seeded = world

    rows = _list(db, sort="line_count", dir="desc", limit=50)["data"]

    assert [row["line_count"] for row in rows] == [3, 2, 1, 1]
    # The adopted order's count comes from its mirror, and the sort must agree with the
    # number printed in the cell rather than with a different count of the same thing.
    adopted = next(row for row in rows if row["sales_order_id"] == str(seeded["b"].id))
    assert adopted["line_count"] == adopted["lines_linked"] == 2


# --------------------------------------------------------------------------- #
# total and stable across a page boundary                                     #
# --------------------------------------------------------------------------- #


def test_a_tie_breaks_the_same_way_on_page_two_as_on_page_one():
    """Five rows carrying ONE value on the sorted field, so the tiebreaker is the only
    thing holding the order together."""
    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            product = _product(db)
            warehouse = _warehouse(db, company_id)
            for letter in "EDCBA":
                core = _core_order(db, company_id)
                core.so_number = f"{MARKER}-SO-{letter}"
                _core_line(
                    db,
                    core,
                    product,
                    warehouse=warehouse,
                    required_date=D_MID,
                    qty_ordered="10",
                )
            db.flush()

            for direction in ("asc", "desc"):
                whole = [
                    row["so_number"]
                    for row in _list(
                        db, sort="outstanding_qty", dir=direction, limit=50
                    )["data"]
                ]
                paged = []
                for page in (1, 2, 3):
                    paged.extend(
                        row["so_number"]
                        for row in _list(
                            db,
                            sort="outstanding_qty",
                            dir=direction,
                            page=page,
                            limit=2,
                        )["data"]
                    )
                assert len(paged) == 5
                assert len(set(paged)) == 5
                assert paged == whole
                # The tiebreaker is the human key ASCENDING whichever way the primary
                # sort runs, so "which of these equal rows comes first" has one answer.
                assert whole == sorted(whole)


def test_sorting_does_not_change_which_rows_the_filters_left(world):
    db, seeded = world

    rows = _list(db, review_state="not_started", sort="outstanding_qty", dir="desc")

    assert rows["pagination"]["total"] == 2
    assert [row["sales_order_id"] for row in rows["data"]] == [
        str(seeded["c"].id),
        str(seeded["a"].id),
    ]


def test_no_sort_is_still_earliest_required_date_ascending_nulls_last(world):
    """The default is the order the work is due in, and it does not move (AC-FP04)."""
    db, seeded = world

    default = [_key(row) for row in _list(db, limit=50)["data"]]
    explicit = [
        _key(row)
        for row in _list(db, sort="earliest_required_date", dir="asc", limit=50)["data"]
    ]

    assert default == explicit
    assert default[0] == str(seeded["a"].id)
    # C has no required date on any line, so it is last rather than first.
    assert default[-1] == str(seeded["c"].id)
