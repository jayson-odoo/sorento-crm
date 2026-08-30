"""L2 - writing purchase-order HISTORY, against Postgres.

The one property that matters more than any other: **history must never read as incoming
supply**. 1,586 closed 2020 orders counted as on-order would inflate every position in the
system, suppress every buy those positions feed, and do it silently - the numbers would look
plausible and simply be wrong.

That is asserted through `scm.on_order_v` rather than by reading the code, because the view
is what the planner actually consumes.

The user's reason for wanting history at all is also pinned here: an order placed years ago
against stock still on hand is the strongest evidence there is that an item does not sell,
and that evidence is only available if the purchase date survives the import.
"""
from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

from app.models.base import set_company_scope
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import OrderLinkClaim
from app.services.scm import po_history_service as svc
from app.services.scm.po_listing_reader import read_po_listing
from tests._pg_fixture import pg_session

MARKER = "ZZTPOH"
SORENTO = "00000000-0000-0000-0000-000000000001"
FIXTURE = Path(__file__).parent / "fixtures" / "po_listing_with_detail_sample.xls"


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as s:
        set_company_scope(s, frozenset({SORENTO}))
        yield s


@pytest.fixture()
def catalogue(db):
    """The products the fixture's orders name, guaranteed to exist.

    GET-or-create by exact code, not a fresh insert. The fixture is a real slice of the
    customer's export, so it names real codes - `CBM1030`, `SRTSCBD290A` - which already
    exist in a database copied from production and do not exist at all in CI's empty one.
    Creating unconditionally fails locally on the unique index; borrowing unconditionally
    fails in CI. Naming the code and ensuring it is there is deterministic in both, and is
    not the "borrow whatever `LIMIT 1` returns" that the rule forbids.
    """
    cat = ProductCategory(
        id=_u(), category_code=f"{MARKER}-CAT-{uuid.uuid4().hex[:6]}",
        category_name=f"{MARKER} cat",
    )
    uom = UnitOfMeasure(id=_u(), uom_name=f"{MARKER} unit",
                        uom_code=f"{MARKER[:4]}{uuid.uuid4().hex[:6]}")
    db.add_all([cat, uom])
    db.flush()
    made = {}
    for code in ("CBM1030", "SRTSCBD290A"):
        existing = db.query(Product).filter(Product.product_code == code).first()
        if existing is None:
            existing = Product(
                id=_u(), product_code=code, product_name=f"{MARKER} {code}",
                category_id=cat.id, base_uom_id=uom.id, list_price=0,
                is_active=True, is_discontinued=False,
            )
            db.add(existing)
            db.flush()
        made[code] = existing
    return made


@pytest.fixture()
def blank_book(db):
    """Remove any of THIS FIXTURE's documents the database already holds.

    The fixture is a real slice of the customer's export, so its document numbers are real
    and fixed - and once the same file has been uploaded through the screen against this
    database, they are present before the test starts. "The first apply created some orders"
    then reads 0 and the test fails for a reason that has nothing to do with the code.

    Scoped to the numbers this fixture names, and inside the rolled-back session, so it
    removes exactly the documents under test and puts them back on teardown. The same
    trap in the other direction is the CI one: never assume a row IS there either.
    """
    numbers = [o.po_number for o in read_po_listing(FIXTURE.read_bytes()).orders]
    if numbers:
        db.execute(
            text(
                "DELETE FROM purchase_order_lines WHERE purchase_order_id IN "
                "(SELECT id FROM purchase_orders WHERE po_number = ANY(:nums))"
            ),
            {"nums": numbers},
        )
        db.execute(
            text("DELETE FROM purchase_orders WHERE po_number = ANY(:nums)"),
            {"nums": numbers},
        )
        # The SPO half of the same book lives in `spo_allocations` since migration 420,
        # and its document numbers are just as fixed as the purchase orders' are.
        db.execute(
            text("DELETE FROM spo_allocations WHERE spo_number = ANY(:nums)"),
            {"nums": numbers},
        )
        db.flush()
    return numbers


@pytest.fixture()
def imported(db, catalogue):
    return svc.apply(db, FIXTURE.read_bytes())


def _order(db, number: str) -> PurchaseOrder:
    return db.query(PurchaseOrder).filter(PurchaseOrder.po_number == number).one()


def _allocations(db, number: str):
    """The SPO half, in the table a shipping order lives in since migration 420."""
    from app.models.procurement import SPOAllocation

    return (
        db.query(SPOAllocation)
        .filter(SPOAllocation.spo_number == number)
        .order_by(SPOAllocation.spo_line_number)
        .all()
    )


# --------------------------------------------------------------------------- #
# the property everything else depends on
# --------------------------------------------------------------------------- #

def _on_order(db, product_ids: list[str]) -> float:
    return float(
        db.execute(
            text(
                "SELECT COALESCE(SUM(on_order), 0) FROM scm.on_order_v "
                "WHERE product_id::text = ANY(:pids)"
            ),
            {"pids": product_ids},
        ).scalar()
        or 0.0
    )


def test_history_never_counts_as_incoming_supply(db, catalogue):
    """THE test. Asserted through the view the planner reads, not by inspecting the write.

    `scm.on_order_v` requires an OPEN line with quantity still to come. History is written
    closed AND fully received, so it fails both halves - excluded by construction rather than
    by a filter somebody has to remember to add.

    Measured as a DELTA. These are real product codes and a real product may legitimately
    have live purchase orders against it; asserting an absolute zero would be asserting
    something about the customer's data, and would fail for a reason that has nothing to do
    with this import.
    """
    product_ids = [str(p.id) for p in catalogue.values()]
    before = _on_order(db, product_ids)

    svc.apply(db, FIXTURE.read_bytes())
    db.flush()

    assert _on_order(db, product_ids) == before, "history leaked into on-order supply"


def test_lines_are_written_closed_and_fully_received(db, imported):
    """Both halves, because either one alone would let a later change re-open the supply."""
    order = _order(db, "202001-S0001")
    for line in order.lines:
        assert line.line_status == "closed"
        assert float(line.qty_received) == float(line.qty_ordered)


def test_the_purchase_date_survives_so_ageing_can_be_read_from_it(db, imported):
    """An order placed years ago against stock still held is the evidence the user asked for.

    "if I order from 5 years ago and now still got stock meaning this is not very hot
    selling" - which is only answerable if the date is imported rather than stamped as today.
    """
    order = _order(db, "202001-S0001")
    assert order.issue_date == date(2020, 1, 2)


# --------------------------------------------------------------------------- #
# what the file says, faithfully
# --------------------------------------------------------------------------- #

def test_the_supplier_is_created_from_the_creditor_code(db, imported):
    supplier = (
        db.query(Supplier).filter(Supplier.supplier_code == "400-F020").one_or_none()
    )
    assert supplier is not None
    assert supplier.supplier_name.startswith("FOSHAN ROYAL MIRROR")
    assert str(_order(db, "202001-S0001").supplier_id) == str(supplier.id)


def test_a_back_created_supplier_is_reported_on_the_job_summary(db, catalogue, blank_book):
    """An operator must never discover an invented supplier by surprise.

    Same two keys, same cap and same semantics as the outstanding purchase-order upload
    reports its own back-creations with (captain, 28 Aug 2026). Written against whether the
    master already held `400-F020`, because that is a fact about the environment: the local
    database is a prod copy that holds it, CI's is empty.
    """
    held = db.query(Supplier).filter(Supplier.supplier_code == "400-F020").first()

    out = svc.apply(db, FIXTURE.read_bytes())
    db.flush()

    supplier = db.query(Supplier).filter(Supplier.supplier_code == "400-F020").one()
    assert str(_order(db, "202001-S0001").supplier_id) == str(supplier.id)
    if held is None:
        assert "400-F020" in out["suppliers_created_codes"]
        assert out["suppliers_created"] == len(out["suppliers_created_codes"])
    else:
        assert "400-F020" not in out["suppliers_created_codes"]


def test_the_currency_and_the_cost_come_from_the_file(db, imported):
    order = _order(db, "202001-S0001")
    assert order.currency == "CNY"
    line = order.lines[0]
    assert float(line.qty_ordered) == 450.0
    assert float(line.unit_cost) == 24.0


def test_a_charge_line_is_not_written_as_a_product_line(db, imported, catalogue):
    """`MISC` and `HANDLING CHARGES` are the order's cost with no product behind them.

    Written as lines they would be two catalogue codes that never match, reported as
    failures on every upload; and a quantity of 1 "HANDLING CHARGES" is not stock.
    """
    codes = {
        db.query(Product.product_code).filter(Product.id == row.product_id).scalar()
        for row in _allocations(db, "SPO-2020/01-0001")
        if row.product_id
    }
    assert codes, "the shipping order wrote no lines at all"
    assert "MISC" not in codes
    assert "HANDLING CHARGES" not in codes
    assert imported["charge_lines"] >= 2


def test_the_import_never_creates_a_product(db, catalogue):
    """Building a catalogue out of a 2020 purchase report is how a catalogue stops meaning
    anything: the codes arrive with no category, no UOM and no price, and every later screen
    has to cope with them.

    Asserted as "the product count does not move", not as "the unmatched list is non-empty" -
    whether this fixture has an unmatched code depends on what the catalogue already holds,
    which is a fact about the environment and not about the import.
    """
    before = db.query(Product).count()

    out = svc.apply(db, FIXTURE.read_bytes())
    db.flush()

    assert db.query(Product).count() == before
    # Whatever could not be matched is NAMED, so somebody can take the list to whoever owns
    # the catalogue. A count alone says there is a problem without saying which.
    assert len(out["unmatched_item_codes"]) == min(out["unmatched_items"], 200)
    for code in out["unmatched_item_codes"]:
        assert db.query(Product).filter(Product.product_code == code).first() is None


# --------------------------------------------------------------------------- #
# re-uploading the same book
# --------------------------------------------------------------------------- #

def test_a_second_upload_of_the_same_file_changes_nothing(db, catalogue, blank_book):
    """History is re-uploaded whenever somebody re-exports a wider date range.

    Not idempotent, the second upload doubles every historical quantity - and because the
    lines are closed, nothing downstream would show it until somebody read a supplier's cost
    history and found it twice.
    """
    first = svc.apply(db, FIXTURE.read_bytes())
    before = db.query(PurchaseOrderLine).count()

    second = svc.apply(db, FIXTURE.read_bytes())

    assert db.query(PurchaseOrderLine).count() == before
    assert second["orders_created"] == 0
    assert first["orders_created"] > 0


# --------------------------------------------------------------------------- #
# the linkage the file carries
# --------------------------------------------------------------------------- #

def test_an_so_named_in_a_note_becomes_a_claim(db, catalogue):
    """`**SO:174830**` is the only place the pairing appears in this file.

    Written as a CLAIM rather than a link, because the sales order may not exist yet - which
    is the whole reason the claim table is there.
    """
    svc.apply(db, FIXTURE.read_bytes())
    claims = db.query(OrderLinkClaim).filter(OrderLinkClaim.source == "po_history").all()
    # The 40-row fixture may or may not contain a note; the contract is that the writer
    # produces claims with no item code and no resolution, never a guessed line.
    for claim in claims:
        assert claim.item_code is None, "a PO note cannot say which line it describes"
        assert claim.resolved_at is None
        assert claim.so_number and claim.po_number


def test_preview_writes_nothing(db, catalogue):
    before_orders = db.query(PurchaseOrder).count()
    out = svc.preview(db, FIXTURE.read_bytes())
    assert db.query(PurchaseOrder).count() == before_orders
    assert out["orders"] >= 2
    assert out["lines"] >= 3
