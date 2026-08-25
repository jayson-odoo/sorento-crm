"""S5 - the purchase-history channel reads the structured PO + SPO export as well.

The channel has always read AutoCount's banded "Purchase Order Listing With Detail". The
captain's own book is a different shape entirely: one flat sheet, 27 columns, 27,192 rows,
holding BOTH document families at once - 13,641 rows on `######-S####` purchase orders and
13,550 on `SPO-####/##-####` shipping orders, plus one grand-total row with no document
number at all.

Three properties are pinned here, and each one is a way the import could be silently wrong.

**Detection is by header shape.** The banded report must keep reading byte-identically; a
regression there loses the format the channel already serves.

**The family comes from the Doc No PREFIX, never the `Shipping Order` flag.** Nine rows of
the captain's real file disagree with their own flag (measured 2026-08-14), and this fixture
carries one of them: `202309-S0054` is flagged `Checked` and is a purchase order.

**Everything lands closed and fully received, both families.** This is HISTORY. The rule the
PO half already enforces (`test_po_history_import.py`) is asserted here for the SPO half
through the same view the planner reads.

The fixture is a 33-row excerpt of the captain's own file, cell values copied verbatim.
"""
from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

from app.models.base import set_company_scope
from app.models.inventory import Warehouse
from app.models.procurement import (
    PurchaseOrder,
    PurchaseOrderLine,
    SPOAllocation,
    Supplier,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import OrderLinkClaim
from app.services import import_outcome_codes as oc
from app.services.import_alias_service import AliasResolver
from app.services.import_outcome import ImportOutcome
from app.services.scm import po_history_service as svc
from app.services.scm.po_listing_reader import read_po_listing
from app.services.scm.purchase_history_reader import (
    STRUCTURED_DOC_TYPE,
    doc_family,
    read_purchase_history,
)
from tests._pg_fixture import pg_session
from tests.scm._outstanding_workbooks import (
    SUPPLIER_MAIN_LABEL,
    make_codes,
    po_minimal_row,
    po_workbook,
    seed_catalogue,
    seed_suppliers,
    workbook,
    PO_MINIMAL,
)

MARKER = "ZZTPOSPO"
SORENTO = "00000000-0000-0000-0000-000000000001"
FIXTURES = Path(__file__).parent / "fixtures"
STRUCTURED = FIXTURES / "po_spo_history_sample.xlsx"
BANDED = FIXTURES / "po_listing_with_detail_sample.xls"

# What the fixture holds, counted off the source file it was cut from.
PO_LINES = 19
SPO_LINES = 12
CAPTION_ROWS = 1        # a document row with no item code and no quantity
MISSING_DOC_ROWS = 1    # the grand-total row at the foot of the export
SOURCE_ROWS = PO_LINES + SPO_LINES + CAPTION_ROWS + MISSING_DOC_ROWS

PO_DOCS = {"202301-S0001", "202301-S0002", "202301-S0003", "202301-S0008",
           "202309-S0020", "202309-S0054"}
SPO_DOCS = {"SPO-2023/01-0001", "SPO-2023/01-0002", "SPO-2023/10-0004"}

# Flagged `Shipping Order = Checked` and a purchase order all the same.
FLAG_DISAGREES = "202309-S0054"

# Every item code the fixture names, so the catalogue fixture can guarantee them.
ITEM_CODES = (
    "BRBC22350W-1-SG", "BRC21131XUW-3AS-ENG", "CB4702", "CB4924-CR", "CB4932-BL",
    "CBF66403", "CBMC5865", "CGB3600WTR", "CGB3601WTR", "RPACC", "SRT373-8-NL",
    "SRTBF11705", "SRTSA625A-NL", "SRTWB247", "SRTWC287A-RL", "SRTWCY8605-PJ",
    "SRTWHBWP", "SRTWT9513", "SRTWT9802", "SRTWT9813", "WESERP10B",
)
# Locations the fixture names. `RESERVE` is deliberately NOT seeded: an unknown location must
# leave the line unplaced, never drop it.
KNOWN_LOCATIONS = ("BRW", "BRW-ACTS", "BRW-AM", "BRW-BB", "BRW-NTC")
UNKNOWN_LOCATION = "RESERVE"


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    """The session this channel actually runs on: `autoflush=False`, as `SessionLocal` is.

    Not a detail. Every get-or-create in the write path below - the claim especially -
    checks the database for a row it has only `db.add`ed, and under autoflush that row is
    already written by the time the check reads. The check then passes for the wrong reason
    and the test proves nothing about the API, where the same file dies at flush on the
    unique index it was supposed to be guarding.
    """
    with pg_session(autoflush=False) as s:
        set_company_scope(s, frozenset({SORENTO}))
        yield s


@pytest.fixture()
def resolver(db) -> AliasResolver:
    return AliasResolver.for_doc_type(db, STRUCTURED_DOC_TYPE)


@pytest.fixture()
def catalogue(db):
    """The products and warehouses the fixture names, guaranteed to exist.

    Get-or-create by exact code rather than a fresh insert: the fixture is a real slice of
    the captain's export, so it names real codes that already exist on a database copied
    from production and do not exist at all on an empty one. Creating unconditionally fails
    on the unique index locally; borrowing whatever is there fails in CI.
    """
    cat = ProductCategory(id=_u(), category_code=f"{MARKER}-CAT-{uuid.uuid4().hex[:6]}",
                          category_name=f"{MARKER} cat")
    uom = UnitOfMeasure(id=_u(), uom_name=f"{MARKER} unit",
                        uom_code=f"{MARKER[:4]}{uuid.uuid4().hex[:6]}")
    db.add_all([cat, uom])
    db.flush()

    products = {}
    for code in ITEM_CODES:
        row = db.query(Product).filter(Product.product_code == code).first()
        if row is None:
            row = Product(id=_u(), product_code=code, product_name=f"{MARKER} {code}",
                          category_id=cat.id, base_uom_id=uom.id, list_price=0,
                          is_active=True, is_discontinued=False)
            db.add(row)
            db.flush()
        products[code] = row

    warehouses = {}
    for code in KNOWN_LOCATIONS:
        row = db.query(Warehouse).filter(Warehouse.warehouse_code == code).first()
        if row is None:
            row = Warehouse(id=_u(), warehouse_code=code,
                            warehouse_name=f"{MARKER} {code}", is_active=True)
            db.add(row)
            db.flush()
        warehouses[code] = row

    return {"products": products, "warehouses": warehouses}


@pytest.fixture()
def blank_book(db):
    """Remove any of THIS fixture's documents the database already holds.

    Its document numbers are real and fixed, so once the same book has been uploaded through
    the screen they are present before the test starts and "the apply created some orders"
    reads zero. Scoped to the numbers the fixture names and inside the rolled-back session.
    """
    numbers = sorted(PO_DOCS | SPO_DOCS)
    db.execute(
        text("DELETE FROM purchase_order_lines WHERE purchase_order_id IN "
             "(SELECT id FROM purchase_orders WHERE po_number = ANY(:nums))"),
        {"nums": numbers},
    )
    db.execute(text("DELETE FROM purchase_orders WHERE po_number = ANY(:nums)"),
               {"nums": numbers})
    # The SPO half lives in `spo_allocations` since migration 420, and its documents are
    # just as fixed as the purchase orders' are.
    db.execute(text("DELETE FROM spo_allocations WHERE spo_number = ANY(:nums)"),
               {"nums": numbers})
    db.execute(text("DELETE FROM scm.order_link_claim WHERE po_number = ANY(:nums)"),
               {"nums": numbers})
    db.flush()
    return numbers


@pytest.fixture()
def imported(db, catalogue, blank_book):
    return svc.apply(db, STRUCTURED.read_bytes())


def _order(db, number: str) -> PurchaseOrder:
    return db.query(PurchaseOrder).filter(PurchaseOrder.po_number == number).one()


def _allocations(db, number: str) -> list[SPOAllocation]:
    """The SPO half, in the table it lives in since migration 420 (section K)."""
    return (
        db.query(SPOAllocation)
        .filter(SPOAllocation.spo_number == number)
        .order_by(SPOAllocation.spo_line_number)
        .all()
    )


class _Recorder(ImportOutcome):
    """An `ImportOutcome` that also remembers which row got which code.

    The counts alone cannot answer "did the grand-total row get an outcome or vanish", and
    that question is the whole reason a queued import records per source row.
    """

    def __init__(self) -> None:
        super().__init__(None, persist=False)
        self.rows: list[tuple[int | None, str, str]] = []

    def _record(self, *, outcome, code, row=None, **kwargs):  # noqa: ANN001
        self.rows.append((row, code, outcome))
        return super()._record(outcome=outcome, code=code, row=row, **kwargs)

    def code_for(self, row: int) -> str | None:
        for number, code, _outcome in self.rows:
            if number == row:
                return code
        return None


# --------------------------------------------------------------------------- #
# detection: two shapes, one entry point
# --------------------------------------------------------------------------- #

def test_the_structured_export_is_recognised_by_its_header_row(db, resolver):
    parsed = read_purchase_history(STRUCTURED.read_bytes(), resolver)

    assert parsed.ok
    assert {o.po_number for o in parsed.orders} == PO_DOCS | SPO_DOCS
    assert parsed.line_count == PO_LINES + SPO_LINES


def test_the_banded_report_still_reads_exactly_as_it_did(db, resolver):
    """The format the channel already serves, through the new entry point.

    Its header band carries `Doc No` and its line band carries `Item Code` and `Qty`, but
    never in the same row - which is what tells the two shapes apart, and what a naive
    "does it mention Item Code" check would get wrong.
    """
    through_entry_point = read_purchase_history(BANDED.read_bytes(), resolver)
    direct = read_po_listing(BANDED.read_bytes())

    assert [o.po_number for o in through_entry_point.orders] == \
        [o.po_number for o in direct.orders]
    assert through_entry_point.line_count == direct.line_count
    assert through_entry_point.total_rows == direct.total_rows
    assert through_entry_point.layout_row_numbers == direct.layout_row_numbers


def test_every_column_of_the_captains_file_resolves(db, resolver):
    """AC-1.2. A list of unrecognised columns that is never empty is a list nobody reads."""
    parsed = read_purchase_history(STRUCTURED.read_bytes(), resolver)

    assert parsed.unmapped_headers == []


# --------------------------------------------------------------------------- #
# routing: the prefix, never the flag
# --------------------------------------------------------------------------- #

def test_the_doc_number_prefix_decides_the_family():
    assert doc_family("SPO-2023/01-0001") == "spo"
    assert doc_family("202301-S0001") == "po"
    # The banded export writes the same two families in its own spellings.
    assert doc_family("SPO-2020/01-0001") == "spo"
    assert doc_family("spo-2023/01-0001") == "spo", "the prefix is case-insensitive"
    # Anchored on the hyphen: a future series merely STARTING with those three letters is
    # not a shipping order, and filing it as one would exclude it from supply for ever.
    assert doc_family("SPOT-1") == "po"
    assert doc_family("SPOOL-99") == "po"


def test_a_row_whose_shipping_order_flag_disagrees_follows_its_prefix(db, resolver):
    """Nine rows of the real file are flagged `Checked` on a purchase-order number.

    Read from the flag, each one would be filed as a shipping order - and a misfiled row is
    how history would become netting supply (ADR 337).
    """
    parsed = read_purchase_history(STRUCTURED.read_bytes(), resolver)

    order = next(o for o in parsed.orders if o.po_number == FLAG_DISAGREES)
    assert order.doc_family == "po"


def test_the_two_families_reconcile_against_the_file(db, resolver):
    parsed = read_purchase_history(STRUCTURED.read_bytes(), resolver)

    po = [o for o in parsed.orders if o.doc_family == "po"]
    spo = [o for o in parsed.orders if o.doc_family == "spo"]
    assert {o.po_number for o in po} == PO_DOCS
    assert {o.po_number for o in spo} == SPO_DOCS
    assert sum(len(o.lines) for o in po) == PO_LINES
    assert sum(len(o.lines) for o in spo) == SPO_LINES


def test_every_source_row_is_accounted_for(db, resolver):
    """`processed == total` is the invariant every queued channel is held to.

    A row that is neither a line nor named as something else is a row the job cannot
    explain, and there are 925 of them in the captain's own book.
    """
    parsed = read_purchase_history(STRUCTURED.read_bytes(), resolver)

    assert parsed.total_rows == SOURCE_ROWS
    assert (parsed.line_count
            + len(parsed.layout_row_numbers)
            + len(parsed.problem_row_codes)) == parsed.total_rows


# --------------------------------------------------------------------------- #
# the write: history, both families
# --------------------------------------------------------------------------- #

def _on_order(db, product_ids: list[str]) -> float:
    return float(
        db.execute(
            text("SELECT COALESCE(SUM(on_order), 0) FROM scm.on_order_v "
                 "WHERE product_id::text = ANY(:pids)"),
            {"pids": product_ids},
        ).scalar()
        or 0.0
    )


def test_neither_family_ever_counts_as_incoming_supply(db, catalogue, blank_book):
    """THE test, asserted through the view the planner reads rather than by inspecting the
    write. Measured as a delta: these are real product codes and a real product may
    legitimately have live purchase orders against it.

    It matters MORE since migration 420, not less: the SPO half now lands in
    `spo_allocations`, which is the only table this view reads. What keeps 2023 out of the
    plan is that history is written closed and fully received, and this is where that is
    proved rather than asserted about the write.
    """
    product_ids = [str(p.id) for p in catalogue["products"].values()]
    before = _on_order(db, product_ids)

    svc.apply(db, STRUCTURED.read_bytes())
    db.flush()

    assert _on_order(db, product_ids) == before


def test_no_shipping_order_is_written_as_a_purchase_order(db, imported):
    """Section K, AC-K1: `purchase_orders` stops receiving the SPO family altogether."""
    for number in SPO_DOCS:
        assert db.query(PurchaseOrder).filter(PurchaseOrder.po_number == number).count() == 0
        assert _allocations(db, number)


def test_spo_lines_land_closed_and_fully_received(db, imported):
    """Both halves, now asserted on the allocation. Either one alone would let a later
    status edit re-open supply that was delivered years ago - and the SPO family sits in
    the very table `scm.on_order_v` reads, so there is no second line of defence."""
    for number in SPO_DOCS:
        rows = _allocations(db, number)
        assert rows
        for row in rows:
            assert row.line_status == "closed"
            assert row.receipt_status == "fully_received"
            assert row.quantity_received == row.allocated_quantity


def test_each_family_carries_its_own_source_stamp(db, imported):
    """Same tables, discriminated by the source system, so a later reader can tell a
    shipping order from a purchase order without re-parsing the number."""
    assert _order(db, "202301-S0001").source_system == svc.SOURCE_SYSTEM
    assert all(row.source_system == svc.SPO_SOURCE_SYSTEM
               for row in _allocations(db, "SPO-2023/01-0001"))
    for number in PO_DOCS:
        assert _order(db, number).source_ref == svc.STRUCTURED_SOURCE_REF


def test_the_document_date_survives(db, imported):
    assert _order(db, "202301-S0001").issue_date == date(2023, 1, 3)
    assert all(row.issue_date == date(2023, 1, 4)
               for row in _allocations(db, "SPO-2023/01-0001"))


def test_both_families_are_counted_separately_on_the_result(db, imported):
    assert imported["orders_po"] == len(PO_DOCS)
    assert imported["orders_spo"] == len(SPO_DOCS)
    assert imported["lines_po"] == PO_LINES
    assert imported["lines_spo"] == SPO_LINES
    assert imported["lines_created"] == PO_LINES + SPO_LINES


# --------------------------------------------------------------------------- #
# per-row outcomes: nothing is silent
# --------------------------------------------------------------------------- #

def test_the_grand_total_row_at_the_foot_of_the_file_gets_an_outcome(db, catalogue,
                                                                    blank_book):
    """The last row of the captain's export states 2,726,969 and names no document.

    It is not a line and it is not a failure of ours - but a row with no outcome is a row
    the job page cannot explain, and "27,191 of 27,192" is exactly the kind of gap that
    sends somebody looking for a bug that is not there.
    """
    recorder = _Recorder()
    svc.apply(db, STRUCTURED.read_bytes(), outcome=recorder)

    assert recorder.code_for(SOURCE_ROWS + 1) == oc.MISSING_DOC_NO


def test_a_caption_row_inside_a_document_is_named_not_a_line(db, catalogue, blank_book):
    recorder = _Recorder()
    svc.apply(db, STRUCTURED.read_bytes(), outcome=recorder)

    caption_rows = [r for r, code, _o in recorder.rows if code == oc.NOT_A_LINE]
    assert len(caption_rows) == CAPTION_ROWS


def test_processed_reaches_the_total(db, catalogue, blank_book):
    recorder = _Recorder()
    out = svc.apply(db, STRUCTURED.read_bytes(), outcome=recorder)

    assert out["total_rows"] == SOURCE_ROWS
    assert recorder.processed == SOURCE_ROWS


# --------------------------------------------------------------------------- #
# what the structured file states that the banded report could not
# --------------------------------------------------------------------------- #

def test_the_stock_location_lands_on_the_line(db, imported, catalogue):
    """The banded report names no location at all; this one does, on every row."""
    line = _order(db, "202301-S0001").lines[0]
    assert str(line.warehouse_id) == str(catalogue["warehouses"]["BRW"].id)


def test_an_unknown_location_is_reported_and_the_line_is_still_written(db, imported):
    """History cannot be mis-placed the way an outstanding line can - it is closed - so a
    location we do not hold costs the line its warehouse and never the line itself."""
    order = _order(db, "202309-S0020")
    assert len(order.lines) == 5
    assert all(line.warehouse_id is None for line in order.lines)
    assert UNKNOWN_LOCATION in imported["unknown_locations"]


def test_the_line_level_sales_order_becomes_a_claim_that_names_the_item(db, imported):
    """`FromSODocList` states the pairing per ROW. The banded report only ever carried an
    order-level `**SO:174830**` note, which cannot say which line it describes."""
    claim = (
        db.query(OrderLinkClaim)
        .filter(OrderLinkClaim.so_number == "SO247365",
                OrderLinkClaim.po_number == "202301-S0003")
        .one()
    )
    assert claim.item_code == "BRBC22350W-1-SG"
    assert claim.source == "po_history"


def test_the_import_never_invents_a_supplier(db, catalogue, blank_book):
    """This export carries the creditor's NAME and no creditor code.

    `suppliers.supplier_code` is unique and NOT NULL, so a supplier could only be created
    here by inventing its code - which is how a supplier master stops meaning anything.
    """
    before = db.query(Supplier).count()

    svc.apply(db, STRUCTURED.read_bytes())
    db.flush()

    assert db.query(Supplier).count() == before


def test_each_order_is_linked_to_exactly_what_the_matcher_resolved(db, catalogue, blank_book):
    """The writer and the summary must agree about who the creditor is.

    Asserted against the matcher's own answer rather than against a named supplier, because
    which of these 2023 creditors a given database holds is a fact about the environment: on
    the local prod copy several exist, on CI none do, and a test that names one passes in one
    place and fails in the other for a reason that has nothing to do with the code.
    """
    parsed = read_purchase_history(STRUCTURED.read_bytes(),
                                   AliasResolver.for_doc_type(db, STRUCTURED_DOC_TYPE))
    names = {o.supplier_name for o in parsed.orders if o.supplier_name}
    expected = svc._suppliers_by_name(db, names)

    out = svc.apply(db, STRUCTURED.read_bytes())
    db.flush()

    for order in parsed.orders:
        written = (
            _allocations(db, order.po_number)[0].supplier_id
            if order.doc_family == "spo"
            else _order(db, order.po_number).supplier_id
        )
        match = expected.get(order.supplier_name)
        if match is None:
            assert written is None, "an unmatched creditor was linked to something"
            assert order.supplier_name in out["unmatched_creditors"]
        else:
            assert str(written) == str(match.id)
    assert out["unmatched_creditor_count"] == len(names) - len(expected)


def test_a_trailing_currency_marker_is_folded_away_and_a_country_is_not(db):
    """AutoCount writes the same creditor as `X` and as `X (RMB)`: one company, two accounts.

    `(CHINA)` / `(HK)` / `(M)` are the opposite case - separate legal entities that bill
    separately - so the fold is a fixed CURRENCY list rather than a shape like "a short word
    in brackets", which cannot tell the two apart and would merge two real companies.
    """
    stem = f"{MARKER} FOLD {uuid.uuid4().hex[:6]}"
    supplier = Supplier(id=_u(), supplier_code=f"{MARKER}-{uuid.uuid4().hex[:6]}",
                        supplier_name=stem)
    db.add(supplier)
    db.flush()

    resolved = svc._suppliers_by_name(db, {stem, f"{stem} (RMB)", f"{stem} (CHINA)"})

    assert str(resolved[stem].id) == str(supplier.id)
    assert str(resolved[f"{stem} (RMB)"].id) == str(supplier.id)
    assert f"{stem} (CHINA)" not in resolved, "a country suffix was folded into the parent"


def test_an_ambiguous_creditor_name_resolves_to_nothing(db):
    """Two supplier rows can fold to one key: the same company held once per currency account.

    The query that finds them has no ORDER BY, so picking one would attribute a year of
    purchases to whichever row Postgres returned first - differently on the next run, and
    silently either way. Unmatched is the honest answer, and it names the creditor to merge.
    """
    stem = f"{MARKER} TWICE {uuid.uuid4().hex[:6]}"
    db.add_all([
        Supplier(id=_u(), supplier_code=f"{MARKER}-A-{uuid.uuid4().hex[:6]}",
                 supplier_name=stem),
        Supplier(id=_u(), supplier_code=f"{MARKER}-B-{uuid.uuid4().hex[:6]}",
                 supplier_name=f"{stem} (USD)"),
    ])
    db.flush()

    assert svc._suppliers_by_name(db, {stem}) == {}


def test_the_import_never_creates_a_product(db, blank_book):
    """No catalogue fixture here on purpose: whatever is missing must be reported, not made."""
    before = db.query(Product).count()

    out = svc.apply(db, STRUCTURED.read_bytes())
    db.flush()

    assert db.query(Product).count() == before
    for code in out["unmatched_item_codes"]:
        assert db.query(Product).filter(Product.product_code == code).first() is None


# --------------------------------------------------------------------------- #
# re-uploading the same book
# --------------------------------------------------------------------------- #

def test_a_second_upload_of_the_same_file_changes_nothing(db, catalogue, blank_book):
    """There is no line-number column in this export, so line identity is POSITIONAL within
    its document - the same rule the outstanding book uses (AC-2.2). Re-reading the same
    file reproduces the same positions, so the second upload rewrites rather than doubles.

    `202301-S0001` names `CB4924-CR` twice, on two different containers, which is what makes
    a content key insufficient and the position necessary.
    """
    first = svc.apply(db, STRUCTURED.read_bytes())
    db.flush()
    before = db.query(PurchaseOrderLine).count()

    second = svc.apply(db, STRUCTURED.read_bytes())
    db.flush()

    assert db.query(PurchaseOrderLine).count() == before
    assert first["orders_created"] == len(PO_DOCS | SPO_DOCS)
    assert second["orders_created"] == 0
    assert len(_order(db, "202301-S0001").lines) == 3


# --------------------------------------------------------------------------- #
# the same pairing stated twice: normal data, one claim
# --------------------------------------------------------------------------- #

def _repeat_book(doc: str, item: str, so_number: str) -> bytes:
    """A structured export naming ONE item twice on ONE document, from ONE sales order.

    Exactly the shape the captain's own file carries - `(SO253918, 202302-S0001, CKS813)`
    appears on two rows, two containers of the same item on the same purchase order against
    the same sales order - and the shape that took the whole 27,192-row job down.

    Written with the file's real header spellings rather than all 27 columns: the reader
    detects this layout on `Doc No` + `Item Code` + `Qty` resolving in one row, so a
    narrower book exercises the same path and cannot drift from the fixture.
    """
    return workbook(
        [
            (doc, date(2023, 2, 1), item, 20, "BRW", f"{MARKER} CREDITOR", so_number),
            (doc, date(2023, 2, 1), item, 60, "BRW", f"{MARKER} CREDITOR", so_number),
        ],
        headers=("Doc No", "Doc Date", "Item Code", "Qty", "Location", "Creditor Name",
                 "FromSODocList"),
        title="PO SPO",
    )


@pytest.fixture()
def repeated_pairing(db, catalogue):
    """A document number and a sales order number nothing else in the database holds."""
    stem = uuid.uuid4().hex[:8].upper()
    doc = f"2302{stem[:2]}-S9{stem[2:5]}"
    return {"doc": doc, "item": "CB4702", "so_number": f"SO9{stem}",
            "book": _repeat_book(doc, "CB4702", f"SO9{stem}")}


def _claims(db, so_number: str, doc: str, item_code: str) -> list[OrderLinkClaim]:
    return (
        db.query(OrderLinkClaim)
        .filter(OrderLinkClaim.so_number == so_number,
                OrderLinkClaim.po_number == doc,
                OrderLinkClaim.item_code == item_code)
        .all()
    )


def test_one_item_named_twice_on_a_document_claims_its_sales_order_once(db, repeated_pairing):
    """Two lines of the same item on one purchase order, both from the same sales order.

    This is ORDINARY data - two containers of one product bought on one document - and it
    is not a row problem: both lines are written, and the pairing they both state is ONE
    claim. `uq_scm_order_link_claim_identity` is on
    `(company, so_number, po_number, coalesce(item_code, ''))`, so a second claim is not a
    duplicate row to clean up later, it is a `UniqueViolation` at flush that fails the whole
    job - 0 of 27,192 processed, with nothing on screen naming the two rows responsible.

    The existence check alone cannot see it: `SessionLocal` runs `autoflush=False`, so the
    claim written for the first line is still pending when the second line's check reads.
    """
    r = repeated_pairing

    out = svc.apply(db, r["book"])
    db.flush()

    assert len(_claims(db, r["so_number"], r["doc"], r["item"])) == 1
    assert len(_order(db, r["doc"]).lines) == 2, "the repeated line lost its second row"
    assert out["lines_created"] == 2


def test_a_re_upload_of_a_repeated_pairing_still_adds_no_claim(db, repeated_pairing):
    """The per-run guard must not replace the database check, only stand beside it.

    A second upload starts with an empty set and would write the pairing again if the
    existence query were dropped - the same `UniqueViolation`, one job later.
    """
    r = repeated_pairing
    svc.apply(db, r["book"])
    db.flush()

    svc.apply(db, r["book"])
    db.flush()

    assert len(_claims(db, r["so_number"], r["doc"], r["item"])) == 1


# --------------------------------------------------------------------------- #
# preview and the Test verdict
# --------------------------------------------------------------------------- #

def test_preview_writes_nothing_and_splits_the_two_families(db, catalogue, blank_book):
    before = db.query(PurchaseOrder).count()

    out = svc.preview(db, STRUCTURED.read_bytes())

    assert db.query(PurchaseOrder).count() == before
    assert out["orders_po"] == len(PO_DOCS)
    assert out["orders_spo"] == len(SPO_DOCS)
    assert out["total_rows"] == SOURCE_ROWS


def test_the_test_verdict_accepts_the_structured_file(db, catalogue, blank_book):
    out = svc.validate(db, STRUCTURED.read_bytes())

    assert out["valid"] is True
    assert out["errors"] == []


# --------------------------------------------------------------------------- #
# the cross-channel invariant: the OTHER writer of these tables
# --------------------------------------------------------------------------- #

def test_the_outstanding_book_never_revives_a_history_line(db):
    """`purchase_orders` has two writers, and only one of them states the past.

    `outstanding_import_service` revives a closed line rather than inserting a second row -
    correctly, for its own lines: a line that comes back is the same line, and the receipt
    already booked against it belongs to it. Applied to a HISTORY line the same act is
    corruption. The revive sets `line_status='open'` and `qty_ordered = already_received +
    incoming`, which puts a 2023 purchase that was delivered years ago into
    `scm.po_ordered_v` as an order still to arrive, permanently, and destroys the quantity
    the file actually stated.

    It became reachable in S5. `_closed_line` matches on (header, product, warehouse, date),
    and history lines used to carry NULL for the last two - the structured PO + SPO export
    states both, so the equality now matches.

    MUTATION PROOF: drop `source_system.notin_(HISTORY_SOURCE_SYSTEMS)` from `_closed_line`
    and this test fails on all three counts - the history line goes open, its ordered
    quantity becomes 50, and the outstanding channel's own line is never inserted.
    """
    from app.services.scm import outstanding_import_service as outstanding
    from app.services.scm.outstanding_reader import PO

    codes = make_codes()
    seed_catalogue(db, codes, doc_type="outstanding_po")
    seed_suppliers(db, codes)

    product_id = str(
        db.query(Product.id).filter(Product.product_code == codes.item_rl).scalar()
    )
    warehouse_id = str(
        db.query(Warehouse.id).filter(Warehouse.warehouse_code == codes.loc_project).scalar()
    )
    eta = date(2026, 7, 1)

    # History as this channel writes it: closed, fully received, with the location and the
    # date the structured export states.
    order = PurchaseOrder(
        id=_u(), po_number=codes.main_po, issue_date=date(2023, 1, 3), status="closed",
        source_system=svc.SOURCE_SYSTEM, source_ref=svc.STRUCTURED_SOURCE_REF,
    )
    db.add(order)
    db.flush()
    history_line = PurchaseOrderLine(
        id=_u(), purchase_order_id=str(order.id), product_id=product_id,
        warehouse_id=warehouse_id, qty_ordered=40, qty_received=40, expected_date=eta,
        line_status="closed", source_system=svc.SOURCE_SYSTEM, source_ref="1",
    )
    db.add(history_line)
    db.flush()
    history_id = str(history_line.id)

    # The outstanding PO book names the same document, item, location and date.
    book = po_workbook(
        [po_minimal_row(codes.main_po, codes.creditor_main, codes.item_rl, 10, eta,
                        codes.loc_project)],
        headers=PO_MINIMAL,
    )
    outstanding.apply(db, book, PO)
    db.flush()
    db.expire_all()

    rows = db.execute(text(
        "SELECT pol.id::text, pol.line_status, pol.qty_ordered, pol.qty_received, "
        "       pol.source_system "
        "FROM purchase_order_lines pol JOIN purchase_orders po "
        "  ON po.id = pol.purchase_order_id "
        "WHERE po.po_number = :po AND pol.product_id = :pid"
    ), {"po": codes.main_po, "pid": product_id}).mappings().fetchall()

    kept = next(r for r in rows if r["id"] == history_id)
    assert kept["line_status"] == "closed", "the outstanding book re-opened a history line"
    assert float(kept["qty_ordered"]) == 40.0, "history's ordered quantity was rewritten"
    assert float(kept["qty_received"]) == 40.0
    assert kept["source_system"] == svc.SOURCE_SYSTEM

    added = [r for r in rows if r["id"] != history_id]
    assert len(added) == 1, "the outstanding book wrote no line of its own"
    assert added[0]["line_status"] == "open"
    assert float(added[0]["qty_ordered"]) == 10.0
    assert added[0]["source_system"] != svc.SOURCE_SYSTEM

    # What the planner reads: the 10 still to arrive, and not the 2023 purchase beside it.
    ordered = float(db.execute(text(
        "SELECT COALESCE(SUM(oo.ordered), 0) FROM scm.po_ordered_v oo "
        "WHERE oo.product_id::text = :pid"
    ), {"pid": product_id}).scalar())
    assert ordered == 10.0
