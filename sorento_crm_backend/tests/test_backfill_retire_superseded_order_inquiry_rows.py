"""The backfill for pairs that were double counted before reconciliation shipped.

`project_so_ingest_service` reconciles the sheet's provisional number with AutoCount's real
one AT INGEST TIME. Nothing re-runs for a document ingested before that existed, so those
projects keep an open provisional `sales_orders` row forever and `scm.committed_v` counts
the demand twice, permanently.

Two halves are worth pinning, and they fail in opposite directions:

* the MATCH - a real pair is found and merged exactly as the service would have merged it,
* the NON-match - a project whose AutoCount number was never recorded is left alone. That is
  the direction a backfill goes wrong quietly: retiring a row whose demand nothing else
  carries removes it from the plan, and the only symptom is a number that got smaller.

The suite runs on the real database through `pg_session` (rolled back) with the ALL-COMPANIES
scope the script itself sets, so the company checks are exercised rather than bypassed.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

import pytest

from app.models.base import set_company_scope
from app.models.company import Company
from app.models.inventory import Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import SO_STATUS_PUBLISHED, ProjectSalesOrder
from app.models.projects import Project
from app.models.scm import OrderLinkClaim
from app.services.project_order_inquiry_import_service import SOURCE as CLAIM_SOURCE
from app.services.project_order_inquiry_import_service import SOURCE_SYSTEM
from app.services.project_so_ingest_service import RETIRED_ORDER_STATUS
from tests._pg_fixture import pg_session

import scripts.backfill_retire_superseded_order_inquiry_rows as backfill

MARKER = "ZZTBACKFILL"
SORENTO = "00000000-0000-0000-0000-000000000001"

DOC_NO = f"{MARKER}-SO920111"
DUE = date(2026, 10, 1)
SHEET_QTY = 12.0
BOOK_QTY = 30.0


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as session:
        # The script runs with no request and no principal, so it sets the all-companies
        # scope. Mirror it here or the test proves something the script never does.
        set_company_scope(session, None)
        yield session


@pytest.fixture()
def world(db):
    """A published project sales order that already knows its AutoCount number."""
    category = ProductCategory(
        id=_u(), category_code=f"{MARKER}-C-{uuid.uuid4().hex[:6]}",
        category_name=f"{MARKER} cat",
    )
    uom = UnitOfMeasure(
        id=_u(), uom_code=f"{MARKER[:4]}{uuid.uuid4().hex[:6]}", uom_name=f"{MARKER} u"
    )
    db.add_all([category, uom])
    db.flush()
    product = Product(
        id=_u(), product_code=f"{MARKER}-ITEM-{uuid.uuid4().hex[:6]}",
        product_name=f"{MARKER} item", category_id=category.id, base_uom_id=uom.id,
        list_price=0, is_active=True, is_discontinued=False,
    )
    warehouse = Warehouse(
        id=_u(), warehouse_code=f"{MARKER[:8]}{uuid.uuid4().hex[:6]}",
        warehouse_name=f"{MARKER} wh", is_active=True, counts_as_available=True,
    )
    db.add_all([product, warehouse])
    db.flush()

    project = Project(
        id=_u(), company_id=SORENTO, project_code=f"{MARKER}-P-{uuid.uuid4().hex[:6]}",
        title=f"{MARKER} Seri Tower", normalised_title=f"{MARKER.lower()} seri {_u()[:6]}",
    )
    db.add(project)
    db.flush()
    pso = ProjectSalesOrder(
        id=_u(), company_id=SORENTO, project_id=project.id,
        provisional_ref=f"{MARKER}-PSO-{uuid.uuid4().hex[:8]}",
        autocount_doc_no=DOC_NO,
        status=SO_STATUS_PUBLISHED, published_at=datetime.utcnow(), grouping_origin="area",
    )
    db.add(pso)
    db.flush()
    return {"db": db, "product": product, "warehouse": warehouse, "project": project, "pso": pso}


def _core_order(
    world, number: str, *, demand_origin: str | None, qty: float, company: str = SORENTO
) -> SalesOrder:
    db = world["db"]
    order = SalesOrder(
        id=_u(), so_number=number, status="open", company_id=company,
        demand_class="project" if demand_origin == SOURCE_SYSTEM else None,
        demand_origin=demand_origin,
        source_system=SOURCE_SYSTEM if demand_origin == SOURCE_SYSTEM else "scm_upload",
        internal_note=f"Order Inquiry project: {MARKER}" if demand_origin else None,
    )
    db.add(order)
    db.flush()
    db.add(
        SalesOrderLine(
            id=_u(), sales_order_id=str(order.id), product_id=str(world["product"].id),
            warehouse_id=str(world["warehouse"].id), qty_ordered=qty, qty_delivered=0,
            qty_required=qty, line_status="open", purchasing_status="not_reviewed",
            required_date=DUE, company_id=company,
        )
    )
    db.flush()
    return order


def _the_pair(world) -> tuple[SalesOrder, SalesOrder]:
    """The state a project ingested before the reconciliation shipped is left in."""
    book = _core_order(world, DOC_NO, demand_origin=None, qty=BOOK_QTY)
    sheet = _core_order(
        world, world["pso"].provisional_ref, demand_origin=SOURCE_SYSTEM, qty=SHEET_QTY
    )
    return book, sheet


def _line_statuses(world, order_id: str) -> set[str]:
    return {
        row.line_status
        for row in world["db"].query(SalesOrderLine).filter(
            SalesOrderLine.sales_order_id == str(order_id)
        )
    }


def _numbers(pairs) -> set[str]:
    return {pair.provisional_number for pair in pairs}


# --------------------------------------------------------------------------- #
# the match
# --------------------------------------------------------------------------- #

def test_the_superseded_pair_is_found(world):
    _, sheet = _the_pair(world)

    found = backfill.find_superseded_pairs(world["db"])

    assert sheet.so_number in _numbers(found)
    mine = next(p for p in found if p.provisional_number == sheet.so_number)
    assert mine.real_number == DOC_NO
    assert mine.project_label == f"{MARKER} Seri Tower"
    assert mine.relinks_so_id is True
    assert mine.cross_company is False


def test_applying_retires_the_provisional_row_and_links_the_real_one(world):
    book, sheet = _the_pair(world)
    pso = world["pso"]

    backfill.run(world["db"], apply=True)

    assert sheet.status == RETIRED_ORDER_STATUS
    assert _line_statuses(world, str(sheet.id)) == {"closed"}
    assert DOC_NO in (sheet.internal_note or ""), "the retirement does not say what replaced it"
    assert sheet.so_number == pso.provisional_ref, "the row was renamed, not retired"
    assert pso.so_id == str(book.id)
    # CS's row is theirs. We link to it, we do not restate it.
    assert book.status == "open"
    assert _line_statuses(world, str(book.id)) == {"open"}


def test_applying_moves_the_claims_still_waiting(world):
    book, sheet = _the_pair(world)
    pso = world["pso"]
    waiting = OrderLinkClaim(
        id=_u(), company_id=SORENTO, so_number=pso.provisional_ref,
        po_number=f"{MARKER}-POC-{uuid.uuid4().hex[:6]}", item_code="ZZT-A",
        source=CLAIM_SOURCE,
    )
    already_paired = OrderLinkClaim(
        id=_u(), company_id=SORENTO, so_number=pso.provisional_ref,
        po_number=f"{MARKER}-POC-{uuid.uuid4().hex[:6]}", item_code="ZZT-B",
        source=CLAIM_SOURCE,
        so_line_id=str(
            world["db"].query(SalesOrderLine)
            .filter(SalesOrderLine.sales_order_id == str(sheet.id)).first().id
        ),
    )
    world["db"].add_all([waiting, already_paired])
    world["db"].flush()

    backfill.run(world["db"], apply=True)

    def _number(claim):
        return (
            world["db"].query(OrderLinkClaim)
            .filter(OrderLinkClaim.id == claim.id).one().so_number
        )

    assert _number(waiting) == DOC_NO
    assert _number(already_paired) == pso.provisional_ref


def test_a_second_run_finds_nothing_left_to_do(world):
    """Idempotent by the match itself: a retired row is no longer open, so it stops matching."""
    _, sheet = _the_pair(world)

    backfill.run(world["db"], apply=True)
    note_after_first = sheet.internal_note
    backfill.run(world["db"], apply=True)

    assert sheet.so_number not in _numbers(backfill.find_superseded_pairs(world["db"]))
    assert sheet.internal_note == note_after_first, "the retirement was stamped twice"
    assert (note_after_first or "").count(DOC_NO) == 1


def test_a_dry_run_writes_nothing(world):
    _, sheet = _the_pair(world)
    pso = world["pso"]

    backfill.run(world["db"], apply=False)

    assert sheet.so_number in _numbers(backfill.find_superseded_pairs(world["db"])), (
        "the pair must still be REPORTED by a dry run"
    )
    assert sheet.status == "open"
    assert _line_statuses(world, str(sheet.id)) == {"open"}
    assert sheet.internal_note == f"Order Inquiry project: {MARKER}"
    assert pso.so_id is None


def test_a_link_somebody_made_by_hand_is_left_where_it_is(world):
    _, sheet = _the_pair(world)
    pso = world["pso"]
    third = _core_order(world, f"{DOC_NO}-HAND", demand_origin=None, qty=BOOK_QTY)
    pso.so_id = str(third.id)
    world["db"].flush()

    backfill.run(world["db"], apply=True)

    assert pso.so_id == str(third.id), "the hand-made link was overwritten by the backfill"
    # The retire half still runs: the demand behind it is the demand the book row holds.
    assert sheet.status == RETIRED_ORDER_STATUS


# --------------------------------------------------------------------------- #
# the non-match - the direction that goes wrong quietly
# --------------------------------------------------------------------------- #

def test_a_project_with_no_autocount_number_is_never_a_pair(world):
    """Nothing else carries this demand, so retiring it would remove it from the plan."""
    pso = world["pso"]
    pso.autocount_doc_no = None
    world["db"].flush()
    sheet = _core_order(
        world, pso.provisional_ref, demand_origin=SOURCE_SYSTEM, qty=SHEET_QTY
    )

    assert sheet.so_number not in _numbers(backfill.find_superseded_pairs(world["db"]))

    backfill.run(world["db"], apply=True)
    assert sheet.status == "open"
    assert _line_statuses(world, str(sheet.id)) == {"open"}


def test_a_pair_with_no_real_numbered_row_is_never_a_pair(world):
    """AutoCount named the document, but nobody's book has created that row yet."""
    sheet = _core_order(
        world, world["pso"].provisional_ref, demand_origin=SOURCE_SYSTEM, qty=SHEET_QTY
    )

    assert sheet.so_number not in _numbers(backfill.find_superseded_pairs(world["db"]))

    backfill.run(world["db"], apply=True)
    assert sheet.status == "open"


def test_another_feeds_row_at_the_provisional_number_is_never_a_pair(world):
    """`demand_origin` is MATCHED, not merely present - the same guard the service applies."""
    _core_order(world, DOC_NO, demand_origin=None, qty=BOOK_QTY)
    other_feed = _core_order(
        world, world["pso"].provisional_ref, demand_origin=None, qty=SHEET_QTY
    )
    other_feed.demand_origin = "some_future_feed"
    world["db"].flush()

    assert other_feed.so_number not in _numbers(backfill.find_superseded_pairs(world["db"]))

    backfill.run(world["db"], apply=True)
    assert other_feed.status == "open"
    assert other_feed.internal_note is None


# --------------------------------------------------------------------------- #
# two companies
# --------------------------------------------------------------------------- #

def test_a_cross_company_pair_is_reported_and_skipped(world):
    """The all-companies scope makes the collision VISIBLE, which is not permission to merge."""
    other = Company(id=_u(), name=f"{MARKER} Mocha", code=f"ZB{uuid.uuid4().hex[:8]}")
    world["db"].add(other)
    world["db"].flush()

    theirs = _core_order(world, DOC_NO, demand_origin=None, qty=BOOK_QTY, company=other.id)
    sheet = _core_order(
        world, world["pso"].provisional_ref, demand_origin=SOURCE_SYSTEM, qty=SHEET_QTY
    )

    found = backfill.find_superseded_pairs(world["db"])
    mine = next(p for p in found if p.provisional_number == sheet.so_number)
    assert mine.cross_company is True

    backfill.run(world["db"], apply=True)

    assert sheet.status == "open", "a row was retired against another company's number"
    assert _line_statuses(world, str(sheet.id)) == {"open"}
    assert world["pso"].so_id is None
    assert theirs.status == "open"
