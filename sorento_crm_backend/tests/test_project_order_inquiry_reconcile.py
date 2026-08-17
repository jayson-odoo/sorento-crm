"""Group F - the two numbers, and no double count (ADR 0010, AC-F2/F3/F4/F5).

The Order Inquiry sheet is exported BEFORE AutoCount has issued the SO number, so the core
`sales_orders` row the sheet creates carries the project's `provisional_ref`. CS's outstanding
book knows only the real number and inserts on a miss. Left alone, one piece of demand is
counted twice under two numbers.

`project_so_ingest_service` is the one place both references are known at once, and the
reconciliation lives there. Both orderings are asserted HERE, in one module (AC-F4): a
reconciliation that only works when the sheet lands first is not a reconciliation, and split
across two files one of them quietly stops being run.

The double count is proven against `scm.committed_v` itself, not against a row count - the
view is what the plan reads, and "there is one row" is a weaker claim than "the engine sees
this demand once". That is why this suite runs on the REAL database through ``pg_session``
(the blank scratch schema holds tables, not views) and every assertion is scoped to the rows
the test created.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.base import set_company_scope
from app.models.company import Company
from app.models.inventory import Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import SO_STATUS_PUBLISHED, ProjectSalesOrder
from app.models.projects import Project, ProjectParty, ProjectPurchaseOrder
from app.models.scm import OrderLinkClaim
from app.services.company_scope import company_scope
from app.services.project_order_inquiry_import_service import SOURCE as CLAIM_SOURCE
from app.services.project_order_inquiry_import_service import SOURCE_SYSTEM
from app.services.project_so_ingest_service import (
    RETIRED_ORDER_STATUS,
    IngestDocument,
    IngestLine,
    ProjectSOIngestService,
)

from tests._pg_fixture import pg_session

MARKER = "ZZTRECON"
SORENTO = "00000000-0000-0000-0000-000000000001"

#: What AutoCount eventually calls it, and what the sheet called it in the meantime.
DOC_NO = f"{MARKER}-SO910777"

AREA = "TOWER"
DUE = date(2026, 9, 1)

SHEET_QTY = 10.0
BOOK_QTY = 40.0


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as session:
        set_company_scope(session, frozenset({SORENTO}))
        yield session


@pytest.fixture()
def world(db):
    """One project sales order, published, waiting for its AutoCount number."""
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
        title=f"{MARKER} Tuju Residences", normalised_title=f"{MARKER.lower()} tuju {_u()[:6]}",
    )
    db.add(project)
    db.flush()
    party = ProjectParty(
        id=_u(), company_id=SORENTO, party_type="contractor", name=f"{MARKER} Buimaco"
    )
    db.add(party)
    db.flush()
    po = ProjectPurchaseOrder(
        id=_u(), company_id=SORENTO, project_id=project.id, issuing_party_id=party.id,
        po_number=f"{MARKER}-PO-{uuid.uuid4().hex[:6]}", po_date=date(2026, 2, 1),
        term_days=60, status="approved",
    )
    db.add(po)
    db.flush()
    pso = ProjectSalesOrder(
        id=_u(), company_id=SORENTO, project_id=project.id, purchase_order_id=po.id,
        area_group=AREA, provisional_ref=f"{MARKER}-PSO-{uuid.uuid4().hex[:8]}",
        status=SO_STATUS_PUBLISHED, published_at=datetime.utcnow(), grouping_origin="area",
    )
    db.add(pso)
    db.flush()
    return {"db": db, "product": product, "warehouse": warehouse, "po": po, "pso": pso}


# --------------------------------------------------------------------------- helpers


def _core_order(
    world, number: str, *, demand_origin: str | None, qty: float, company: str = SORENTO
) -> SalesOrder:
    """A core `sales_orders` row carrying open demand for the world's product.

    Each row is seeded as the channel that writes it actually writes it, because
    `scm.committed_v` reads BOTH demand columns since migration 346: a `project`-class
    order counts only when the inquiry created it.

    * The sheet's row - `project` class with the `scm_order_inquiry` origin, which is
      exactly what `project_order_inquiry_import_service` stamps on the header it creates.
    * Anybody else's row - `demand_class` NULL. No sales export carries an order type
      today, so `outstanding_import_service._classify_demand` REPORTS the document and
      leaves the column alone rather than guessing; a row CS's book creates therefore
      arrives unclassified. Unclassified demand counts straight from the book, which is
      what makes the double count visible in the view at all.

    Hardcoding `project` on every row instead made the committed-demand assertions read
    differently per database: the shared development one still carries the pre-346 view
    body, which has no demand-source clause and counts a project-class row with no origin
    that the current view deliberately sets aside.

    `company` is stated rather than left to the insert auto-stamp so a row can be seeded
    into a DIFFERENT company - the case the scoped lookups could not see at all.
    """
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


def _document(world, *, doc_no: str = DOC_NO) -> IngestDocument:
    return IngestDocument(
        doc_no=doc_no,
        customer_code=None,
        customer_po_no=world["po"].po_number,
        area_group=AREA,
        terms="*Net 60 days",
        total_amount=Decimal("1000.00"),
        lines=[
            IngestLine(
                product_code=world["product"].product_code, qty=Decimal("10"),
                unit_price=Decimal("100.00"), line_no=1, delivery_date=DUE,
            )
        ],
    )


def _ingest(world, *, doc_no: str = DOC_NO):
    return ProjectSOIngestService(world["db"]).ingest(_document(world, doc_no=doc_no))


def _committed(world) -> float:
    """What the plan actually sees for this product, straight out of the view.

    The view is read, never reimplemented here, so its demand-source clause is part of
    every assertion below. That is why the seeds have to be shaped like the rows their
    channel really writes - see `_core_order`.
    """
    value = world["db"].execute(
        text("SELECT COALESCE(SUM(committed), 0) FROM scm.committed_v WHERE product_id = :p"),
        {"p": str(world["product"].id)},
    ).scalar()
    return float(value or 0)


def _by_number(world, number: str) -> list[SalesOrder]:
    return world["db"].query(SalesOrder).filter(SalesOrder.so_number == number).all()


def _line_statuses(world, order_id: str) -> set[str]:
    return {
        row.line_status
        for row in world["db"].query(SalesOrderLine).filter(
            SalesOrderLine.sales_order_id == str(order_id)
        )
    }


def _first_line_id(world, order_id: str) -> str:
    return str(
        world["db"].query(SalesOrderLine)
        .filter(SalesOrderLine.sales_order_id == str(order_id))
        .first().id
    )


def _unscoped_ids(world, number: str) -> list[str]:
    """Every company's rows at this number, which is what the unique index sees."""
    with company_scope(world["db"], None):
        return sorted(
            str(row.id)
            for row in world["db"].query(SalesOrder).filter(SalesOrder.so_number == number)
        )


def _claim(
    world,
    so_number: str,
    *,
    item_code: str | None = None,
    so_line_id: str | None = None,
    source: str = CLAIM_SOURCE,
) -> OrderLinkClaim:
    """One SO<->PO claim, resolved on the sales side when `so_line_id` is given."""
    claim = OrderLinkClaim(
        id=_u(),
        so_number=so_number,
        po_number=f"{MARKER}-POC-{uuid.uuid4().hex[:6]}",
        item_code=item_code,
        source=source,
        so_line_id=so_line_id,
    )
    world["db"].add(claim)
    world["db"].flush()
    return claim


def _claim_number(world, claim: OrderLinkClaim) -> str:
    return (
        world["db"].query(OrderLinkClaim)
        .filter(OrderLinkClaim.id == claim.id)
        .one()
        .so_number
    )


# --------------------------------------------------------------------------- #
# AC-F2 - the sheet landed first
# --------------------------------------------------------------------------- #

def test_the_sheet_created_row_is_renumbered_in_place(world):
    """No core row holds the real number, so the provisional row BECOMES it."""
    pso = world["pso"]
    sheet = _core_order(world, pso.provisional_ref, demand_origin=SOURCE_SYSTEM, qty=SHEET_QTY)
    sheet_id = str(sheet.id)

    _ingest(world)

    assert _by_number(world, pso.provisional_ref) == []
    renumbered = _by_number(world, DOC_NO)
    assert len(renumbered) == 1, "a second row was created instead of renaming the first"
    assert str(renumbered[0].id) == sheet_id
    assert renumbered[0].status == "open"
    assert renumbered[0].demand_origin == SOURCE_SYSTEM
    assert pso.so_id == sheet_id
    assert pso.autocount_doc_no == DOC_NO


def test_the_renumbered_row_is_still_counted_once(world):
    world_pso = world["pso"]
    _core_order(world, world_pso.provisional_ref, demand_origin=SOURCE_SYSTEM, qty=SHEET_QTY)

    _ingest(world)

    assert _committed(world) == SHEET_QTY


# --------------------------------------------------------------------------- #
# AC-F3 - the outstanding book landed first
# --------------------------------------------------------------------------- #

def test_the_book_row_wins_and_the_provisional_one_is_retired(world):
    pso = world["pso"]
    book = _core_order(world, DOC_NO, demand_origin=None, qty=BOOK_QTY)
    sheet = _core_order(world, pso.provisional_ref, demand_origin=SOURCE_SYSTEM, qty=SHEET_QTY)
    book_id, sheet_id = str(book.id), str(sheet.id)

    # The bug this exists to stop: one piece of demand, counted under both numbers.
    assert _committed(world) == BOOK_QTY + SHEET_QTY

    _ingest(world)

    assert pso.so_id == book_id, "the project order must point at the real-numbered row"
    assert _committed(world) == BOOK_QTY, "committed demand is still double counted"

    retired = world["db"].query(SalesOrder).filter(SalesOrder.id == sheet_id).one()
    assert retired.so_number == pso.provisional_ref, "the provisional row was renamed, not retired"
    assert retired.status == RETIRED_ORDER_STATUS
    assert _line_statuses(world, sheet_id) == {"closed"}
    assert retired.demand_origin == SOURCE_SYSTEM, "origin is history, not a switch"
    assert DOC_NO in (retired.internal_note or ""), "the retirement does not say what replaced it"


def test_the_book_row_itself_is_never_edited(world):
    """We link to CS's row. We do not restate it: their figures are theirs (AC-B1)."""
    pso = world["pso"]
    book = _core_order(world, DOC_NO, demand_origin=None, qty=BOOK_QTY)
    _core_order(world, pso.provisional_ref, demand_origin=SOURCE_SYSTEM, qty=SHEET_QTY)
    before = (book.so_number, book.status, book.demand_origin, book.source_system)

    _ingest(world)

    assert (book.so_number, book.status, book.demand_origin, book.source_system) == before


# --------------------------------------------------------------------------- #
# AC-F5 - somebody else's row
# --------------------------------------------------------------------------- #

def test_a_foreign_row_at_the_provisional_number_is_never_renumbered(world):
    """The number collides by accident. Renaming it would rewrite an order we do not own."""
    pso = world["pso"]
    foreign = _core_order(world, pso.provisional_ref, demand_origin=None, qty=BOOK_QTY)

    _ingest(world)

    assert foreign.so_number == pso.provisional_ref
    assert foreign.status == "open"
    assert _by_number(world, DOC_NO) == []
    assert pso.so_id is None, "so_id must not adopt a row this project never created"
    assert _committed(world) == BOOK_QTY


def test_a_foreign_row_at_the_provisional_number_is_never_retired(world):
    pso = world["pso"]
    book = _core_order(world, DOC_NO, demand_origin=None, qty=BOOK_QTY)
    foreign = _core_order(world, pso.provisional_ref, demand_origin=None, qty=SHEET_QTY)

    _ingest(world)

    assert foreign.status == "open"
    assert _line_statuses(world, str(foreign.id)) == {"open"}
    assert foreign.internal_note is None
    assert pso.so_id == str(book.id)
    # Untouched means still counted: it is somebody's demand, just not this project's.
    assert _committed(world) == BOOK_QTY + SHEET_QTY


def test_another_feeds_row_at_the_provisional_number_is_left_alone(world):
    """`demand_origin` must be MATCHED, not merely present.

    The two tests above use a NULL origin, which a test for "did this row come from the
    sheet" could pass by checking `demand_origin IS NOT NULL`. The next feed to write a
    `demand_origin` would then be adopted, renumbered and its number handed to a project
    that never created it. So the guard is asserted against a row that HAS an origin and
    a different one.
    """
    pso = world["pso"]
    other_feed = _core_order(world, pso.provisional_ref, demand_origin=None, qty=BOOK_QTY)
    other_feed.demand_origin = "some_future_feed"
    world["db"].flush()

    _ingest(world)

    assert other_feed.so_number == pso.provisional_ref, "another feed's row was renumbered"
    assert other_feed.status == "open"
    assert other_feed.demand_origin == "some_future_feed"
    assert other_feed.internal_note is None
    assert _by_number(world, DOC_NO) == []
    assert pso.so_id is None, "so_id adopted a row from a feed this project does not own"
    # Deliberately no `_committed` assertion: whether a row carrying some OTHER
    # `demand_origin` reaches `scm.committed_v` is that view's filtering decision, not this
    # guard's. Asserting it here would make the test fail whenever the view's demand-source
    # clause is retuned, for a reason that has nothing to do with reconciliation. The three
    # assertions above already fail if the row is renumbered, retired or stamped.


def test_another_feeds_row_is_not_retired_when_the_book_row_exists(world):
    """The merge branch is just as blind: only the sheet's own row may be closed."""
    pso = world["pso"]
    book = _core_order(world, DOC_NO, demand_origin=None, qty=BOOK_QTY)
    other_feed = _core_order(world, pso.provisional_ref, demand_origin=None, qty=SHEET_QTY)
    other_feed.demand_origin = "some_future_feed"
    world["db"].flush()

    _ingest(world)

    assert other_feed.status == "open"
    assert _line_statuses(world, str(other_feed.id)) == {"open"}
    assert other_feed.internal_note is None
    assert other_feed.so_number == pso.provisional_ref
    assert pso.so_id == str(book.id)


# --------------------------------------------------------------------------- #
# a link somebody put there by hand
# --------------------------------------------------------------------------- #

def test_a_human_set_so_id_pointing_elsewhere_is_not_repointed(world):
    """The merge branch is deliberately narrow (see `_reconcile_core_order`).

    `so_id` is repointed only when it is unset or still on the row about to be retired.
    A link a person put on a THIRD row is left exactly where they put it: they know
    something the matcher does not, and silently moving it would undo their correction
    with no record that it happened.

    The provisional row is still retired in the same pass, which is the point of pinning
    this: the two halves of the merge are independent, and a future tidy-up that fuses
    them would either start overwriting the human's link or stop stopping the double
    count. Both are regressions, and neither is visible from the other test.
    """
    pso = world["pso"]
    book = _core_order(world, DOC_NO, demand_origin=None, qty=BOOK_QTY)
    sheet = _core_order(world, pso.provisional_ref, demand_origin=SOURCE_SYSTEM, qty=SHEET_QTY)
    third = _core_order(world, f"{DOC_NO}-HAND", demand_origin=None, qty=BOOK_QTY)

    # What a person decided, before the ingest runs.
    pso.so_id = str(third.id)
    world["db"].flush()

    _ingest(world)

    assert pso.so_id == str(third.id), "the hand-made link was overwritten by the matcher"
    assert third.so_number == f"{DOC_NO}-HAND"
    assert third.status == "open"
    assert third.internal_note is None

    # The retire half still runs: the sheet's row stops counting regardless of where the
    # link points, because the demand behind it is the demand the book row already holds.
    assert sheet.status == RETIRED_ORDER_STATUS
    assert _line_statuses(world, str(sheet.id)) == {"closed"}
    assert DOC_NO in (sheet.internal_note or "")
    assert book.status == "open"


# --------------------------------------------------------------------------- #
# the second upload of the same document
# --------------------------------------------------------------------------- #

def test_re_ingesting_after_a_renumber_changes_nothing(world):
    pso = world["pso"]
    sheet = _core_order(world, pso.provisional_ref, demand_origin=SOURCE_SYSTEM, qty=SHEET_QTY)
    sheet_id = str(sheet.id)

    _ingest(world)
    _ingest(world)

    assert [str(row.id) for row in _by_number(world, DOC_NO)] == [sheet_id]
    assert _by_number(world, pso.provisional_ref) == []
    assert pso.so_id == sheet_id
    assert _committed(world) == SHEET_QTY


def test_re_ingesting_after_a_retire_does_not_fire_again(world):
    pso = world["pso"]
    book = _core_order(world, DOC_NO, demand_origin=None, qty=BOOK_QTY)
    sheet = _core_order(world, pso.provisional_ref, demand_origin=SOURCE_SYSTEM, qty=SHEET_QTY)

    _ingest(world)
    note_after_first = sheet.internal_note
    _ingest(world)

    assert sheet.internal_note == note_after_first, "the retirement was stamped twice"
    assert (note_after_first or "").count(DOC_NO) == 1
    assert sheet.status == RETIRED_ORDER_STATUS
    assert pso.so_id == str(book.id)
    assert _committed(world) == BOOK_QTY


# --------------------------------------------------------------------------- #
# the plain case the reconciliation must not break
# --------------------------------------------------------------------------- #

def test_an_order_the_sheet_never_touched_still_backfills_its_link(world):
    """No provisional row was ever created. The existing behaviour is unchanged."""
    book = _core_order(world, DOC_NO, demand_origin=None, qty=BOOK_QTY)

    _ingest(world)

    assert world["pso"].so_id == str(book.id)
    assert book.status == "open"
    assert _committed(world) == BOOK_QTY


def test_a_document_with_no_number_reconciles_nothing(world):
    """AutoCount has not issued one yet. Nothing is renamed on the strength of a guess."""
    pso = world["pso"]
    sheet = _core_order(world, pso.provisional_ref, demand_origin=SOURCE_SYSTEM, qty=SHEET_QTY)

    ProjectSOIngestService(world["db"]).ingest(_document(world, doc_no=None))

    assert sheet.so_number == pso.provisional_ref
    assert sheet.status == "open"
    assert pso.so_id is None


# --------------------------------------------------------------------------- #
# a number another COMPANY already holds
# --------------------------------------------------------------------------- #
#
# `sales_orders.so_number` is unique across the whole table, but the company-scope filter
# is injected into SELECTs only. A scoped existence check therefore answers "is the number
# free IN MY COMPANY", which is not the question the unique index asks, and the rename that
# followed died on the index with the whole ingest transaction. The lookups now run
# unscoped and the company is compared in the open.


@pytest.fixture()
def other_company(db):
    """A second company, so a foreign row can actually be seeded and pointed at."""
    company = Company(
        id=_u(), name=f"{MARKER} Mocha", code=f"ZC{uuid.uuid4().hex[:8]}"
    )
    db.add(company)
    db.flush()
    return company


def test_a_real_number_held_by_another_company_reconciles_nothing(world, other_company):
    """Fail-closed: no rename, no retire, no link, and above all no IntegrityError."""
    pso = world["pso"]
    theirs = _core_order(
        world, DOC_NO, demand_origin=None, qty=BOOK_QTY, company=other_company.id
    )
    sheet = _core_order(world, pso.provisional_ref, demand_origin=SOURCE_SYSTEM, qty=SHEET_QTY)

    _ingest(world)

    # The rename is the statement that used to raise. It never runs now.
    assert sheet.so_number == pso.provisional_ref
    assert sheet.status == "open"
    assert _line_statuses(world, str(sheet.id)) == {"open"}
    assert sheet.internal_note == f"Order Inquiry project: {MARKER}"
    assert pso.so_id is None, "so_id was linked to another company's sales order"
    assert _unscoped_ids(world, DOC_NO) == [str(theirs.id)]


def test_another_companys_row_is_never_retired_or_edited(world, other_company):
    """Their row is theirs. The double count is a reporting error; this would be a breach."""
    pso = world["pso"]
    theirs = _core_order(
        world, DOC_NO, demand_origin=None, qty=BOOK_QTY, company=other_company.id
    )
    before = (theirs.so_number, theirs.status, theirs.internal_note, theirs.company_id)

    _ingest(world)

    assert (theirs.so_number, theirs.status, theirs.internal_note, theirs.company_id) == before
    # Read unscoped: their lines are correctly invisible to a scoped query, which is the
    # very reason the reconciliation could not see the collision in the first place.
    with company_scope(world["db"], None):
        assert _line_statuses(world, str(theirs.id)) == {"open"}
    assert pso.so_id is None


def test_a_provisional_number_held_by_another_company_is_left_alone(world, other_company):
    """The sheet stamp matches, the company does not. Same refusal, one table further out."""
    pso = world["pso"]
    theirs = _core_order(
        world, pso.provisional_ref, demand_origin=SOURCE_SYSTEM, qty=SHEET_QTY,
        company=other_company.id,
    )

    _ingest(world)

    assert theirs.so_number == pso.provisional_ref
    assert theirs.status == "open"
    assert _unscoped_ids(world, DOC_NO) == []
    assert pso.so_id is None


# --------------------------------------------------------------------------- #
# a link somebody put there by hand - the renumber half
# --------------------------------------------------------------------------- #

def test_a_human_set_so_id_is_not_repointed_on_the_renumber_path(world):
    """The same narrowness as the merge branch, which the renumber branch used to lack.

    Renumbering and linking are separate decisions. The sheet's row IS this order, so it is
    renamed either way; where `so_id` points is a person's call once they have made it.
    """
    pso = world["pso"]
    sheet = _core_order(world, pso.provisional_ref, demand_origin=SOURCE_SYSTEM, qty=SHEET_QTY)
    third = _core_order(world, f"{DOC_NO}-HAND", demand_origin=None, qty=BOOK_QTY)

    pso.so_id = str(third.id)
    world["db"].flush()

    _ingest(world)

    assert sheet.so_number == DOC_NO, "the renumber must still happen"
    assert pso.so_id == str(third.id), "the hand-made link was overwritten by the matcher"
    assert third.so_number == f"{DOC_NO}-HAND"
    assert third.status == "open"


# --------------------------------------------------------------------------- #
# the SO<->PO claims the sheet wrote
# --------------------------------------------------------------------------- #
#
# `order_link_claim` holds both numbers as TEXT so a claim can outlive the absence of either
# document, which also means nothing in the database follows a renumber. Left behind, the
# claim names a number that no longer exists (renumber) or one whose lines have just been
# closed (retire), and `order_link_service` reports it as still waiting for a sales order we
# are holding.


def test_the_renumber_moves_the_sheets_claims_to_the_real_number(world):
    pso = world["pso"]
    sheet = _core_order(world, pso.provisional_ref, demand_origin=SOURCE_SYSTEM, qty=SHEET_QTY)
    waiting = _claim(world, pso.provisional_ref, item_code="ZZT-A")
    already_paired = _claim(
        world, pso.provisional_ref, item_code="ZZT-B",
        so_line_id=_first_line_id(world, str(sheet.id)),
    )

    _ingest(world)

    # Both move: the ROW moved, so a claim left on the old number names nothing at all.
    assert _claim_number(world, waiting) == DOC_NO
    assert _claim_number(world, already_paired) == DOC_NO


def test_the_renumber_leaves_another_feeds_claims_where_they_are(world):
    """Only claims this feed wrote are touched, on the same reasoning as the row itself."""
    pso = world["pso"]
    _core_order(world, pso.provisional_ref, demand_origin=SOURCE_SYSTEM, qty=SHEET_QTY)
    from_the_po_notes = _claim(world, pso.provisional_ref, source="po_history")

    _ingest(world)

    assert _claim_number(world, from_the_po_notes) == pso.provisional_ref


def test_the_retire_moves_only_the_claims_still_waiting(world):
    """The provisional row keeps its number here, and its lines are now closed.

    An unresolved claim would resolve onto one of those closed lines, so it is repointed at
    the row that actually carries the demand. A claim somebody already resolved is left
    alone: the line it names still exists, and the pairing was somebody's decision.
    """
    pso = world["pso"]
    _core_order(world, DOC_NO, demand_origin=None, qty=BOOK_QTY)
    sheet = _core_order(world, pso.provisional_ref, demand_origin=SOURCE_SYSTEM, qty=SHEET_QTY)
    waiting = _claim(world, pso.provisional_ref, item_code="ZZT-A")
    already_paired = _claim(
        world, pso.provisional_ref, item_code="ZZT-B",
        so_line_id=_first_line_id(world, str(sheet.id)),
    )

    _ingest(world)

    assert _claim_number(world, waiting) == DOC_NO
    assert _claim_number(world, already_paired) == pso.provisional_ref
