"""Stage 1B reconciliation service (PLAN-scm-front-planning.md 3.1/4, STAGE1B slice note
sections 2-4, UAC-scm-front-planning.md AC-A01..AC-A04). TEST-FIRST: this file is written
before ``app/services/project_so_reconciliation_service.py`` exists, so every test in it
is expected to fail on collection with an ``ImportError`` until the service lands. That is
the correct RED state, not a seeding bug.

The line-mapping rule under test (slice note section 2), verbatim:

  Given the Project SO's ``so_id``, candidate core lines are ``sales_order_lines`` rows
  with ``sales_order_id = so_id`` and ``line_status <> 'closed'``. A Project line whose
  existing ``core_sales_order_line_id`` still points at one of those candidates keeps it
  (stable relink) and that core line is removed from the pool. The rest are matched inside
  each ``product_id`` group in two passes: (1) exact required-date match, one Project line
  and one core line only - two or more of either at the same exact date is ambiguous, not
  paired; (2) whatever is left pairs positionally in date order. A core line nothing takes
  is a surplus exception. Header outcome is ``no_document`` (no ``autocount_doc_no``),
  ``no_core_so`` (``so_id`` still null), or ``linked``.

Review state (never a stored column):

  needs_cs_review          iff so_id is set AND lines_total > 0 AND every line linked
                            AND no surplus
  awaiting_reconciliation  otherwise

Postgres, blank scratch schema via ``tests/_pg_fixture.py::blank_session``, rolled back at
teardown. Every FK target is seeded here; nothing is borrowed from an existing row, per
PRINCIPLES.md (CI's database is empty).
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.base import company_scope
from app.models.company import Company
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    IV_ORDER,
    IV_RESERVE_AND_ORDER,
    SO_STATUS_PUBLISHED,
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.models.projects import ProjectParty, ProjectPurchaseOrder
from app.models.user import User
from app.services import project_seed_service
from app.services.project_so_ingest_service import (
    IngestDocument,
    IngestLine,
    ProjectSOIngestService,
)
from app.services.project_so_reconciliation_service import ProjectSOReconciliationService
from app.services.scm.demand import is_plan_demand_order

from ._pg_fixture import blank_session

MARKER = "zzt-so-recon"

# Three distinct required/delivery dates, used across the exact-date and date-order
# pass tests so a moved date is unambiguously a different value from the original.
D1 = date(2027, 1, 7)
D2 = date(2027, 2, 4)
D3 = date(2027, 3, 11)

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=f"{MARKER} CS"))
    db.flush()
    return user_id


def _product(db) -> Product:
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:6]}", uom_name="Unit")
    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} cat"
    )
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(),
        product_code=f"ZZT-{_uid()[:8]}",
        product_name=f"{MARKER} product",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
    )
    db.add(row)
    db.flush()
    return row


def _project(db, company_id: str, owner: str):
    from app.services.project_service import register_project

    return register_project(
        db,
        company_id=company_id,
        actor_user_id=owner,
        developer_party_id=None,
        title=f"{MARKER} Tuju Residences {_uid()[:6]}",
    )


def _core_order(
    db,
    *,
    so_number: str,
    company_id: str | None = None,
    demand_class: str | None = None,
    demand_origin: str | None = None,
    status: str = "open",
) -> SalesOrder:
    """One core `public.sales_orders` header, the AutoCount / outstanding-book row."""
    row = SalesOrder(
        id=_uid(),
        so_number=so_number,
        status=status,
        demand_class=demand_class,
        demand_origin=demand_origin,
    )
    if company_id is not None:
        row.company_id = company_id
    db.add(row)
    db.flush()
    return row


def _core_line(
    db,
    order: SalesOrder,
    product: Product,
    *,
    required_date: date | None,
    qty: str = "10",
    line_status: str = "open",
) -> SalesOrderLine:
    row = SalesOrderLine(
        id=_uid(),
        sales_order_id=order.id,
        product_id=product.id,
        qty_ordered=Decimal(qty),
        qty_delivered=Decimal("0"),
        required_date=required_date,
        line_status=line_status,
    )
    if order.company_id is not None:
        row.company_id = order.company_id
    db.add(row)
    db.flush()
    return row


def _project_order(
    db,
    project,
    *,
    autocount_doc_no: str | None = None,
    so_id: str | None = None,
    status: str = SO_STATUS_PUBLISHED,
    area_group: str = "TOWER",
) -> ProjectSalesOrder:
    row = ProjectSalesOrder(
        id=_uid(),
        company_id=project.company_id,
        project_id=project.id,
        area_group=area_group,
        provisional_ref=f"ZZT-PSO-{_uid()[:8]}",
        autocount_doc_no=autocount_doc_no,
        so_id=so_id,
        status=status,
        published_at=datetime.utcnow() if status == SO_STATUS_PUBLISHED else None,
        grouping_origin="area",
    )
    db.add(row)
    db.flush()
    return row


def _project_line(
    db,
    order: ProjectSalesOrder,
    product: Product,
    *,
    line_no: int,
    delivery_date: date | None = None,
    qty: str = "10",
    core_sales_order_line_id: str | None = None,
) -> ProjectSalesOrderLine:
    row = ProjectSalesOrderLine(
        id=_uid(),
        company_id=order.company_id,
        project_sales_order_id=order.id,
        line_no=line_no,
        product_id=product.id,
        description=f"{MARKER} line {line_no}",
        qty=Decimal(qty),
        uom="UNIT",
        unit_price=Decimal("10.00"),
        amount=Decimal(qty) * Decimal("10.00"),
        delivery_date=delivery_date,
        core_sales_order_line_id=core_sales_order_line_id,
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture()
def seeded():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        yield db, company_id, _user(db)


# --------------------------------------------------------------------------- #
# Line mapping (section 2, AC-A02)                                             #
# --------------------------------------------------------------------------- #


def test_exact_date_pairs_link_product_and_date_together(seeded):
    """AC-A02. Pass 1: an exact required-date match links, and it is the DATE that
    decides the pairing, not database row order -- lines are seeded reversed."""
    db, company_id, owner = seeded
    product = _product(db)
    project = _project(db, company_id, owner)
    core_order = _core_order(db, so_number=f"ZZT-SO-{_uid()[:8]}")
    core_d3 = _core_line(db, core_order, product, required_date=D3)
    core_d1 = _core_line(db, core_order, product, required_date=D1)
    order = _project_order(
        db, project, autocount_doc_no=core_order.so_number, so_id=core_order.id
    )
    line_d1 = _project_line(db, order, product, line_no=1, delivery_date=D1)
    line_d3 = _project_line(db, order, product, line_no=2, delivery_date=D3)

    summary = ProjectSOReconciliationService(db).reconcile(order)

    db.refresh(line_d1)
    db.refresh(line_d3)
    assert str(line_d1.core_sales_order_line_id) == str(core_d1.id)
    assert str(line_d3.core_sales_order_line_id) == str(core_d3.id)
    assert summary["lines_linked"] == summary["lines_total"] == 2
    assert summary["exceptions"] == []


def test_date_order_pass_pairs_a_moved_date_once_the_exact_pass_is_exhausted(seeded):
    """AC-A02. Pass 2: the project line moved from D2 to D3, so pass 1 leaves one
    project line and one core line unmatched by exact date; they still pair, in
    date order, one-to-one."""
    db, company_id, owner = seeded
    product = _product(db)
    project = _project(db, company_id, owner)
    core_order = _core_order(db, so_number=f"ZZT-SO-{_uid()[:8]}")
    core_d1 = _core_line(db, core_order, product, required_date=D1)
    core_d2 = _core_line(db, core_order, product, required_date=D2)
    order = _project_order(
        db, project, autocount_doc_no=core_order.so_number, so_id=core_order.id
    )
    line_d1 = _project_line(db, order, product, line_no=1, delivery_date=D1)
    line_moved = _project_line(db, order, product, line_no=2, delivery_date=D3)

    summary = ProjectSOReconciliationService(db).reconcile(order)

    db.refresh(line_d1)
    db.refresh(line_moved)
    assert str(line_d1.core_sales_order_line_id) == str(core_d1.id)
    assert str(line_moved.core_sales_order_line_id) == str(core_d2.id)
    assert summary["lines_linked"] == summary["lines_total"] == 2


def test_a_line_left_over_after_an_ambiguity_is_not_told_the_document_has_fewer(seeded):
    """N1. Ours A on D1 and B on D2; theirs C and D both on D1, same product.

    Pass 1 finds two core lines at D1 against our one, so A is ambiguous and BOTH core
    lines are accounted for by that ambiguity, which leaves B with nothing to pair with.
    The document carries exactly as many lines for the item as this sales order does, so
    a reason claiming it carries FEWER is a sentence CS would go and check and find false;
    and it carries lines for the item, so "no line for this item" is false too.
    """
    db, company_id, owner = seeded
    product = _product(db)
    project = _project(db, company_id, owner)
    core_order = _core_order(db, so_number=f"ZZT-SO-{_uid()[:8]}")
    _core_line(db, core_order, product, required_date=D1)
    _core_line(db, core_order, product, required_date=D1)
    order = _project_order(
        db, project, autocount_doc_no=core_order.so_number, so_id=core_order.id
    )
    line_a = _project_line(db, order, product, line_no=1, delivery_date=D1)
    line_b = _project_line(db, order, product, line_no=2, delivery_date=D2)

    summary = ProjectSOReconciliationService(db).evaluate(order)

    rows = {row["id"]: row for row in summary["lines"]}
    assert rows[line_a.id]["link"] == "ambiguous"
    assert rows[line_b.id]["link"] == "missing"
    reason = rows[line_b.id]["reason"]
    assert "fewer lines" not in reason, reason
    assert "no line for this item" not in reason, reason
    assert "accounted for" in reason, reason


def test_a_line_with_no_core_candidate_at_all_is_missing(seeded):
    """AC-A02. Product B has no core line whatsoever; its Project line stays open
    and is named in the exceptions by line number and item code."""
    db, company_id, owner = seeded
    product_a = _product(db)
    product_b = _product(db)
    project = _project(db, company_id, owner)
    core_order = _core_order(db, so_number=f"ZZT-SO-{_uid()[:8]}")
    _core_line(db, core_order, product_a, required_date=D1)
    order = _project_order(
        db, project, autocount_doc_no=core_order.so_number, so_id=core_order.id
    )
    _project_line(db, order, product_a, line_no=1, delivery_date=D1)
    missing_line = _project_line(db, order, product_b, line_no=2, delivery_date=D1)

    summary = ProjectSOReconciliationService(db).evaluate(order)

    row = next(r for r in summary["lines"] if r["id"] == missing_line.id)
    assert row["link"] == "missing"
    assert row["candidate_count"] == 0
    missing = [exc for exc in summary["exceptions"] if exc["kind"] == "missing"]
    assert len(missing) == 1
    assert missing[0]["line_no"] == 2
    assert missing[0]["item_code"] == product_b.product_code
    assert summary["review_state"] == "awaiting_reconciliation"


def test_two_project_lines_and_two_core_lines_on_the_same_exact_date_are_ambiguous(seeded):
    """AC-A02. Pass 1 pairs only when exactly one Project line and one core line
    share the exact date; two of each is unresolved and nothing is written."""
    db, company_id, owner = seeded
    product = _product(db)
    project = _project(db, company_id, owner)
    core_order = _core_order(db, so_number=f"ZZT-SO-{_uid()[:8]}")
    _core_line(db, core_order, product, required_date=D1)
    _core_line(db, core_order, product, required_date=D1)
    order = _project_order(
        db, project, autocount_doc_no=core_order.so_number, so_id=core_order.id
    )
    line_1 = _project_line(db, order, product, line_no=1, delivery_date=D1)
    line_2 = _project_line(db, order, product, line_no=2, delivery_date=D1)

    summary = ProjectSOReconciliationService(db).reconcile(order)

    db.refresh(line_1)
    db.refresh(line_2)
    assert line_1.core_sales_order_line_id is None
    assert line_2.core_sales_order_line_id is None
    for row in summary["lines"]:
        assert row["link"] == "ambiguous"
        assert row["candidate_count"] == 2
    ambiguous = [exc for exc in summary["exceptions"] if exc["kind"] == "ambiguous"]
    assert {exc["line_no"] for exc in ambiguous} == {1, 2}


def test_the_ambiguous_candidate_count_is_the_number_of_core_lines_at_that_date(seeded):
    """AC-A02. `candidate_count` answers "how many AutoCount lines could this be", so
    two of ours against ONE of theirs is one candidate each, not two. The screen prints
    the number, and "2 candidates" beside a document holding one is a wrong instruction."""
    db, company_id, owner = seeded
    product = _product(db)
    project = _project(db, company_id, owner)
    core_order = _core_order(db, so_number=f"ZZT-SO-{_uid()[:8]}")
    _core_line(db, core_order, product, required_date=D1)
    order = _project_order(
        db, project, autocount_doc_no=core_order.so_number, so_id=core_order.id
    )
    _project_line(db, order, product, line_no=1, delivery_date=D1)
    _project_line(db, order, product, line_no=2, delivery_date=D1)

    summary = ProjectSOReconciliationService(db).evaluate(order)

    for row in summary["lines"]:
        assert row["link"] == "ambiguous"
        assert row["candidate_count"] == 1


def test_a_surplus_core_line_is_named_by_item_code_and_blocks_needs_cs_review(seeded):
    """AC-A02/AC-A03. The AutoCount document has a line the Project SO does not:
    reported as a surplus exception, and the whole-SO state cannot advance."""
    db, company_id, owner = seeded
    product = _product(db)
    project = _project(db, company_id, owner)
    core_order = _core_order(db, so_number=f"ZZT-SO-{_uid()[:8]}")
    _core_line(db, core_order, product, required_date=D1)
    extra = _core_line(db, core_order, product, required_date=D2)
    order = _project_order(
        db, project, autocount_doc_no=core_order.so_number, so_id=core_order.id
    )
    _project_line(db, order, product, line_no=1, delivery_date=D1)

    summary = ProjectSOReconciliationService(db).evaluate(order)

    surplus = [exc for exc in summary["exceptions"] if exc["kind"] == "surplus"]
    assert len(surplus) == 1
    assert surplus[0]["item_code"] == product.product_code
    assert surplus[0].get("line_no") is None
    assert summary["lines_linked"] == 1 == summary["lines_total"]
    assert summary["review_state"] == "awaiting_reconciliation"


def test_an_existing_link_is_kept_even_when_a_fresher_dated_candidate_exists(seeded):
    """AC-A02. Stability: the Project line's date moved AFTER it was linked, so a
    naive re-match would prefer the other core line -- but the existing link wins,
    and the untaken core line is reported surplus instead."""
    db, company_id, owner = seeded
    product = _product(db)
    project = _project(db, company_id, owner)
    core_order = _core_order(db, so_number=f"ZZT-SO-{_uid()[:8]}")
    old_core_line = _core_line(db, core_order, product, required_date=D1)
    new_core_line = _core_line(db, core_order, product, required_date=D2)
    order = _project_order(
        db, project, autocount_doc_no=core_order.so_number, so_id=core_order.id
    )
    line = _project_line(
        db,
        order,
        product,
        line_no=1,
        delivery_date=D2,
        core_sales_order_line_id=old_core_line.id,
    )

    summary = ProjectSOReconciliationService(db).reconcile(order)

    db.refresh(line)
    assert str(line.core_sales_order_line_id) == str(old_core_line.id)
    assert summary["lines"][0]["link"] == "linked"
    surplus = [exc for exc in summary["exceptions"] if exc["kind"] == "surplus"]
    assert len(surplus) == 1
    assert surplus[0]["item_code"] == product.product_code
    assert str(new_core_line.id) != str(old_core_line.id)


def test_a_link_to_a_closed_core_line_is_cleared_and_reported_missing(seeded):
    """AC-A02. A previously linked core line that is now closed is not a candidate;
    the stale link is cleared and the line goes back to missing."""
    db, company_id, owner = seeded
    product = _product(db)
    project = _project(db, company_id, owner)
    core_order = _core_order(db, so_number=f"ZZT-SO-{_uid()[:8]}")
    stale = _core_line(db, core_order, product, required_date=D1, line_status="closed")
    order = _project_order(
        db, project, autocount_doc_no=core_order.so_number, so_id=core_order.id
    )
    line = _project_line(
        db, order, product, line_no=1, delivery_date=D1, core_sales_order_line_id=stale.id
    )

    summary = ProjectSOReconciliationService(db).reconcile(order)

    db.refresh(line)
    assert line.core_sales_order_line_id is None
    assert summary["lines"][0]["link"] == "missing"
    missing = [exc for exc in summary["exceptions"] if exc["kind"] == "missing"]
    assert missing and missing[0]["line_no"] == 1


def test_a_link_to_a_core_line_moved_to_another_sales_order_is_cleared_and_reported_missing(
    seeded,
):
    """AC-A02. The core line was reassigned to a different core SO between uploads;
    it is no longer a candidate of THIS Project SO's `so_id`."""
    db, company_id, owner = seeded
    product = _product(db)
    project = _project(db, company_id, owner)
    core_order = _core_order(db, so_number=f"ZZT-SO-{_uid()[:8]}")
    other_order = _core_order(db, so_number=f"ZZT-SO-{_uid()[:8]}")
    moved = _core_line(db, other_order, product, required_date=D1)
    order = _project_order(
        db, project, autocount_doc_no=core_order.so_number, so_id=core_order.id
    )
    line = _project_line(
        db, order, product, line_no=1, delivery_date=D1, core_sales_order_line_id=moved.id
    )

    summary = ProjectSOReconciliationService(db).reconcile(order)

    db.refresh(line)
    assert line.core_sales_order_line_id is None
    assert summary["lines"][0]["link"] == "missing"


def test_closed_core_lines_are_never_candidates(seeded):
    """AC-A02. A closed core line that exactly matches product and date is still
    not offered as a candidate to link against."""
    db, company_id, owner = seeded
    product = _product(db)
    project = _project(db, company_id, owner)
    core_order = _core_order(db, so_number=f"ZZT-SO-{_uid()[:8]}")
    _core_line(db, core_order, product, required_date=D1, line_status="closed")
    order = _project_order(
        db, project, autocount_doc_no=core_order.so_number, so_id=core_order.id
    )
    _project_line(db, order, product, line_no=1, delivery_date=D1)

    summary = ProjectSOReconciliationService(db).evaluate(order)

    assert summary["lines"][0]["link"] == "missing"
    assert summary["lines"][0]["candidate_count"] == 0


def test_a_core_so_with_the_same_doc_no_in_another_company_is_never_linked(seeded):
    """AC-A02/AC-G06. `reconcile()` attempts the header link itself when `so_id` is
    still null, so this is the call that exercises the ingest service's `_same_company`
    guard: the same-numbered row belongs to another company, so nothing is adopted,
    `so_id` stays null, and the line has no candidate to match against."""
    db, company_id, owner = seeded
    other_company_id = _uid()
    db.add(
        Company(
            id=other_company_id,
            name=f"{MARKER} other co",
            code=f"ZZT{_uid()[:6]}",
        )
    )
    db.flush()

    product = _product(db)
    doc_no = f"ZZT-SO-{_uid()[:8]}"
    foreign_order = _core_order(db, so_number=doc_no, company_id=other_company_id)
    _core_line(db, foreign_order, product, required_date=D1)

    project = _project(db, company_id, owner)
    order = _project_order(db, project, autocount_doc_no=doc_no, so_id=None)
    line = _project_line(db, order, product, line_no=1, delivery_date=D1)

    summary = ProjectSOReconciliationService(db).reconcile(order)

    db.refresh(order)
    db.refresh(line)
    assert order.so_id is None
    assert line.core_sales_order_line_id is None
    assert summary["header"]["outcome"] == "no_core_so"
    assert summary["lines"][0]["link"] == "missing"
    assert summary["lines"][0]["candidate_count"] == 0


def test_a_core_sales_order_outside_the_company_scope_reads_no_core_so(seeded):
    """AC-G06. `so_id` names a row this company cannot see. The header says exactly
    that rather than claiming a link to a sales order it cannot even name, and the
    review state cannot advance on a link nobody can read."""
    db, company_id, owner = seeded
    other_company_id = _uid()
    db.add(
        Company(
            id=other_company_id,
            name=f"{MARKER} unseen co",
            code=f"ZZT{_uid()[:6]}",
        )
    )
    db.flush()

    product = _product(db)
    doc_no = f"ZZT-SO-{_uid()[:8]}"
    foreign_order = _core_order(db, so_number=doc_no, company_id=other_company_id)
    _core_line(db, foreign_order, product, required_date=D1)

    project = _project(db, company_id, owner)
    order = _project_order(db, project, autocount_doc_no=doc_no, so_id=foreign_order.id)
    _project_line(db, order, product, line_no=1, delivery_date=D1)

    with company_scope(db, frozenset({company_id})):
        summary = ProjectSOReconciliationService(db).evaluate(order)

    assert summary["header"]["outcome"] == "no_core_so"
    assert "not visible" in summary["header"]["reason"]
    assert summary["header"]["core_so_number"] is None
    assert summary["review_state"] == "awaiting_reconciliation"


def test_a_core_line_already_taken_by_another_project_so_is_reported_duplicate(seeded):
    """AC-A02. Two Project SOs adopted the same AutoCount document, so one of them holds
    a core line the other's line would take. The holder keeps it; the second must NAME the
    sales order holding it rather than dying on `uq_projects_so_line_core_line`, and it
    cannot reach Needs CS review.

    The SETUP moved when migration 383 added `uq_projects_so_core_order` (AC-FP10): two
    planning records can no longer point at one core sales order at the same time, so the
    first one releases the header (its `so_id` is cleared) while KEEPING the line link it
    already wrote. That is the state a re-pointed or detached order actually leaves behind,
    and the behaviour under test - who is named, and what the second order's line reads -
    is unchanged.
    """
    db, company_id, owner = seeded
    product = _product(db)
    project = _project(db, company_id, owner)
    core_order = _core_order(db, so_number=f"ZZT-SO-{_uid()[:8]}")
    core_line = _core_line(db, core_order, product, required_date=D1)

    first = _project_order(
        db, project, autocount_doc_no=core_order.so_number, so_id=core_order.id
    )
    first_line = _project_line(db, first, product, line_no=1, delivery_date=D1)

    service = ProjectSOReconciliationService(db)
    service.reconcile(first)
    first.so_id = None
    db.flush()

    second = _project_order(
        db, project, autocount_doc_no=core_order.so_number, so_id=core_order.id
    )
    second_line = _project_line(db, second, product, line_no=7, delivery_date=D1)

    summary = service.reconcile(second)

    db.refresh(first_line)
    db.refresh(second_line)
    assert str(first_line.core_sales_order_line_id) == str(core_line.id)
    assert second_line.core_sales_order_line_id is None

    assert summary["lines"][0]["link"] == "duplicate"
    assert summary["review_state"] == "awaiting_reconciliation"
    duplicate = [exc for exc in summary["exceptions"] if exc["kind"] == "duplicate"]
    assert len(duplicate) == 1
    assert duplicate[0]["line_no"] == 7
    assert duplicate[0]["item_code"] == product.product_code
    assert first.provisional_ref in duplicate[0]["message"]
    # The core line is accounted for by the duplicate, so it is not ALSO surplus.
    assert not [exc for exc in summary["exceptions"] if exc["kind"] == "surplus"]


def test_a_line_whose_own_core_line_closed_is_told_that_not_about_someone_elses(seeded):
    """N3. This line HELD a core line and that core line is now closed; a different core
    line for the same item is held by another Project SO.

    The two answers live in different places - "your line closed, look at the document"
    versus "go and look at sales order X" - so telling this line about a core line it
    never touched sends CS to the wrong screen. The reason it held one wins.

    The other order holds its core line WITHOUT holding the header, because
    `uq_projects_so_core_order` (migration 383, AC-FP10) allows one planning record per
    core sales order. What is under test is which reason wins, and that is untouched.
    """
    db, company_id, owner = seeded
    product = _product(db)
    project = _project(db, company_id, owner)
    core_order = _core_order(db, so_number=f"ZZT-SO-{_uid()[:8]}")
    closed_line = _core_line(
        db, core_order, product, required_date=D1, line_status="closed"
    )
    taken_line = _core_line(db, core_order, product, required_date=D1)

    theirs = _project_order(
        db, project, autocount_doc_no=core_order.so_number, so_id=None
    )
    _project_line(
        db,
        theirs,
        product,
        line_no=1,
        delivery_date=D1,
        core_sales_order_line_id=taken_line.id,
    )
    ours = _project_order(
        db, project, autocount_doc_no=core_order.so_number, so_id=core_order.id
    )
    line = _project_line(
        db,
        ours,
        product,
        line_no=1,
        delivery_date=D1,
        core_sales_order_line_id=closed_line.id,
    )

    summary = ProjectSOReconciliationService(db).evaluate(ours)

    row = next(r for r in summary["lines"] if r["id"] == line.id)
    assert row["link"] == "missing"
    assert row["reason"] == "Its previous core line is now closed."
    assert not [
        exc for exc in summary["exceptions"] if "already linked" in exc["message"]
    ]


def test_a_stale_reason_reads_as_state_not_as_something_this_read_did(seeded):
    """N2. `evaluate` writes nothing, so a reason claiming the link "was cleared" would
    describe a write the reader never asked for. It states the core line's state."""
    db, company_id, owner = seeded
    product = _product(db)
    project = _project(db, company_id, owner)
    core_order = _core_order(db, so_number=f"ZZT-SO-{_uid()[:8]}")
    closed_line = _core_line(
        db, core_order, product, required_date=D1, line_status="closed"
    )
    order = _project_order(
        db, project, autocount_doc_no=core_order.so_number, so_id=core_order.id
    )
    line = _project_line(
        db,
        order,
        product,
        line_no=1,
        delivery_date=D1,
        core_sales_order_line_id=closed_line.id,
    )

    summary = ProjectSOReconciliationService(db).evaluate(order)

    row = next(r for r in summary["lines"] if r["id"] == line.id)
    assert "was cleared" not in row["reason"], row["reason"]
    assert row["reason"] == "Its previous core line is now closed."
    # And the link really is untouched: the read wrote nothing.
    db.refresh(line)
    assert str(line.core_sales_order_line_id) == str(closed_line.id)


# --------------------------------------------------------------------------- #
# Header outcomes (section 2)                                                  #
# --------------------------------------------------------------------------- #


def test_header_outcome_is_no_document_when_autocount_doc_no_is_null(seeded):
    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    order = _project_order(db, project, autocount_doc_no=None, so_id=None)

    summary = ProjectSOReconciliationService(db).evaluate(order)

    assert summary["header"]["outcome"] == "no_document"
    assert summary["review_state"] == "awaiting_reconciliation"


def test_header_outcome_is_no_core_so_when_so_id_is_still_null(seeded):
    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    order = _project_order(
        db, project, autocount_doc_no=f"ZZT-SO-{_uid()[:8]}", so_id=None
    )

    summary = ProjectSOReconciliationService(db).evaluate(order)

    assert summary["header"]["outcome"] == "no_core_so"


def test_header_outcome_is_linked_when_so_id_resolves(seeded):
    db, company_id, owner = seeded
    product = _product(db)
    project = _project(db, company_id, owner)
    core_order = _core_order(db, so_number=f"ZZT-SO-{_uid()[:8]}")
    _core_line(db, core_order, product, required_date=D1)
    order = _project_order(
        db, project, autocount_doc_no=core_order.so_number, so_id=core_order.id
    )
    _project_line(db, order, product, line_no=1, delivery_date=D1)

    summary = ProjectSOReconciliationService(db).evaluate(order)

    assert summary["header"]["outcome"] == "linked"
    assert summary["header"]["core_so_number"] == core_order.so_number


# --------------------------------------------------------------------------- #
# Review state (AC-A02, AC-A03)                                                #
# --------------------------------------------------------------------------- #


def test_review_state_is_needs_cs_review_only_when_header_and_every_line_link_with_no_surplus(
    seeded,
):
    db, company_id, owner = seeded
    product = _product(db)
    project = _project(db, company_id, owner)

    complete_core = _core_order(db, so_number=f"ZZT-SO-{_uid()[:8]}")
    _core_line(db, complete_core, product, required_date=D1)
    complete = _project_order(
        db, project, autocount_doc_no=complete_core.so_number, so_id=complete_core.id
    )
    _project_line(db, complete, product, line_no=1, delivery_date=D1)

    incomplete_core = _core_order(db, so_number=f"ZZT-SO-{_uid()[:8]}")
    incomplete = _project_order(
        db, project, autocount_doc_no=incomplete_core.so_number, so_id=incomplete_core.id
    )
    _project_line(db, incomplete, product, line_no=1, delivery_date=D1)

    complete_summary = ProjectSOReconciliationService(db).evaluate(complete)
    incomplete_summary = ProjectSOReconciliationService(db).evaluate(incomplete)

    assert complete_summary["review_state"] == "needs_cs_review"
    assert incomplete_summary["review_state"] == "awaiting_reconciliation"


def test_a_fully_linked_summary_never_labels_a_line_confirmed_partial_or_purchasing(seeded):
    """AC-A03. No per-line word reads 'confirmed', 'partial' or 'purchasing' -- that
    vocabulary belongs to Stage 1C, which has not run yet."""
    db, company_id, owner = seeded
    product = _product(db)
    project = _project(db, company_id, owner)
    core_order = _core_order(db, so_number=f"ZZT-SO-{_uid()[:8]}")
    _core_line(db, core_order, product, required_date=D1)
    order = _project_order(
        db, project, autocount_doc_no=core_order.so_number, so_id=core_order.id
    )
    _project_line(db, order, product, line_no=1, delivery_date=D1)

    summary = ProjectSOReconciliationService(db).evaluate(order)

    assert summary["review_state"] == "needs_cs_review"
    forbidden = ("confirmed", "partial", "purchasing")
    for row in summary["lines"]:
        text_blob = f"{row.get('link', '')} {row.get('reason', '')}".lower()
        for word in forbidden:
            assert word not in text_blob, (word, row)


def test_reconcile_is_idempotent_on_rerun(seeded):
    """AC-A02. A second `reconcile()` writes nothing new: same link, same summary."""
    db, company_id, owner = seeded
    product = _product(db)
    project = _project(db, company_id, owner)
    core_order = _core_order(db, so_number=f"ZZT-SO-{_uid()[:8]}")
    _core_line(db, core_order, product, required_date=D1)
    order = _project_order(
        db, project, autocount_doc_no=core_order.so_number, so_id=core_order.id
    )
    line = _project_line(db, order, product, line_no=1, delivery_date=D1)

    service = ProjectSOReconciliationService(db)
    first = service.reconcile(order)
    db.refresh(line)
    first_link_id = line.core_sales_order_line_id

    second = service.reconcile(order)
    db.refresh(line)

    assert line.core_sales_order_line_id == first_link_id
    assert second["lines_total"] == first["lines_total"] == 1
    assert second["lines_linked"] == first["lines_linked"] == 1
    assert second["review_state"] == first["review_state"] == "needs_cs_review"
    assert second["exceptions"] == first["exceptions"] == []


def test_review_states_for_returns_every_requested_order_in_one_call(seeded):
    db, company_id, owner = seeded
    product = _product(db)
    project = _project(db, company_id, owner)

    core_order = _core_order(db, so_number=f"ZZT-SO-{_uid()[:8]}")
    _core_line(db, core_order, product, required_date=D1)
    linked = _project_order(
        db, project, autocount_doc_no=core_order.so_number, so_id=core_order.id
    )
    _project_line(db, linked, product, line_no=1, delivery_date=D1)

    awaiting = _project_order(db, project, autocount_doc_no=None, so_id=None)
    _project_line(db, awaiting, product, line_no=1, delivery_date=D1)

    states = ProjectSOReconciliationService(db).review_states_for([linked.id, awaiting.id])

    assert states[linked.id]["review_state"] == "needs_cs_review"
    assert states[linked.id]["lines_linked"] == 1
    assert states[linked.id]["exception_count"] == 0
    assert states[awaiting.id]["review_state"] == "awaiting_reconciliation"
    assert states[awaiting.id]["exception_count"] >= 1


# --------------------------------------------------------------------------- #
# AC-A04: pre-confirmation demand is excluded                                  #
# --------------------------------------------------------------------------- #


def test_a_reconciled_needs_cs_review_so_creates_no_order_inquiry_demand_and_stays_excluded(
    seeded,
):
    """AC-A04. Reconciling writes core-line links only. No standard demand row is written
    on this path - the only writer is the atomic confirmation - so `order_inquiry_rows`
    gains no ORDER / RESERVE_AND_ORDER row, and the demand reader's own predicate
    (`app.services.scm.demand.is_plan_demand_order`) still excludes the linked core
    SO while it carries `demand_class = 'project'` and no sheet-leg origin."""
    db, company_id, owner = seeded
    product = _product(db)
    core_order = _core_order(
        db,
        so_number=f"ZZT-SO-{_uid()[:8]}",
        demand_class="project",
        demand_origin=None,
    )
    _core_line(db, core_order, product, required_date=D1)
    project = _project(db, company_id, owner)
    order = _project_order(
        db, project, autocount_doc_no=core_order.so_number, so_id=core_order.id
    )
    _project_line(db, order, product, line_no=1, delivery_date=D1)

    summary = ProjectSOReconciliationService(db).reconcile(order)

    assert summary["review_state"] == "needs_cs_review"

    inquiry_rows = (
        db.query(OrderInquiryRow)
        .join(OrderInquiry, OrderInquiryRow.order_inquiry_id == OrderInquiry.id)
        .filter(OrderInquiry.project_sales_order_id == order.id)
        .filter(OrderInquiryRow.verb.in_((IV_ORDER, IV_RESERVE_AND_ORDER)))
        .count()
    )
    assert inquiry_rows == 0

    excluded = (
        db.query(SalesOrder.id)
        .filter(SalesOrder.id == core_order.id, is_plan_demand_order())
        .first()
    )
    assert excluded is None


# --------------------------------------------------------------------------- #
# AC-A01: ingest reconciles in the same call                                   #
# --------------------------------------------------------------------------- #


def test_ingest_links_so_id_and_every_line_in_the_same_call(seeded):
    """AC-A01. `ProjectSOIngestService.ingest` sets `so_id` (via
    `_reconcile_core_order`) and reconciles every line in ONE call, so the P8a
    upload does not depend on a second step a person could forget to run."""
    db, company_id, owner = seeded
    product = _product(db)
    customer = Customer(
        id=_uid(), customer_code=f"ZZTC{_uid()[:6]}", customer_name=f"{MARKER} customer"
    )
    db.add(customer)
    db.flush()
    project = _project(db, company_id, owner)
    party = ProjectParty(
        id=_uid(),
        company_id=project.company_id,
        party_type="contractor",
        name=f"{MARKER} {customer.customer_name}",
        customer_id=customer.id,
    )
    db.add(party)
    db.flush()
    po = ProjectPurchaseOrder(
        id=_uid(),
        company_id=project.company_id,
        project_id=project.id,
        issuing_party_id=party.id,
        po_number=f"PO-{_uid()[:6]}",
        po_date=date(2026, 2, 1),
        term_days=60,
        status="approved",
    )
    db.add(po)
    db.flush()
    order = ProjectSalesOrder(
        id=_uid(),
        company_id=project.company_id,
        project_id=project.id,
        purchase_order_id=po.id,
        area_group="TOWER",
        provisional_ref=f"ZZT-PSO-{_uid()[:8]}",
        status=SO_STATUS_PUBLISHED,
        published_at=datetime.utcnow(),
        grouping_origin="area",
    )
    db.add(order)
    db.flush()
    line = ProjectSalesOrderLine(
        id=_uid(),
        company_id=project.company_id,
        project_sales_order_id=order.id,
        line_no=1,
        product_id=product.id,
        description=f"{MARKER} {product.product_code}",
        qty=Decimal("10"),
        uom="UNIT",
        unit_price=Decimal("12.50"),
        amount=Decimal("125.00"),
        delivery_date=D1,
    )
    db.add(line)
    db.flush()

    doc_no = f"ZZT-SO-{_uid()[:8]}"
    real_core_order = _core_order(db, so_number=doc_no)
    real_core_line = _core_line(db, real_core_order, product, required_date=D1)

    document = IngestDocument(
        doc_no=doc_no,
        customer_code=customer.customer_code,
        customer_po_no=po.po_number,
        area_group="TOWER",
        lines=[
            IngestLine(
                line_no=1,
                product_code=product.product_code,
                description=product.product_code,
                qty=Decimal("10"),
                unit_price=Decimal("12.50"),
                uom="UNIT",
                delivery_date=D1,
            )
        ],
    )

    ProjectSOIngestService(db).ingest(document, actor_user_id=owner)

    db.refresh(order)
    db.refresh(line)
    assert order.so_id == real_core_order.id
    # The specific core line, not merely "something": the point of doing the line half in
    # the same call is that each Project line ends up on the line it actually became.
    assert str(line.core_sales_order_line_id) == str(real_core_line.id)


# --------------------------------------------------------------------------- #
# Human-readable exceptions                                                    #
# --------------------------------------------------------------------------- #


def test_no_exception_message_names_a_uuid(seeded):
    """Every exception is named by line number and item code, never by an id."""
    db, company_id, owner = seeded
    product_surplus = _product(db)
    product_missing = _product(db)
    project = _project(db, company_id, owner)
    core_order = _core_order(db, so_number=f"ZZT-SO-{_uid()[:8]}")
    _core_line(db, core_order, product_surplus, required_date=D1)
    order = _project_order(
        db, project, autocount_doc_no=core_order.so_number, so_id=core_order.id
    )
    _project_line(db, order, product_missing, line_no=1, delivery_date=D1)

    summary = ProjectSOReconciliationService(db).evaluate(order)

    kinds = {exc["kind"] for exc in summary["exceptions"]}
    assert {"missing", "surplus"} <= kinds
    for exc in summary["exceptions"]:
        assert not _UUID_RE.search(exc["message"])
