"""The CRM's own reorder-plan PO must not double-count once AutoCount states the same order.

The captain's ruling of 21 Aug: the CRM can raise its own purchase order from a reorder-plan
confirm (`source_system == "scm_recommendation"`, `status="active"` after `bulk_confirm`).
When the same physical order is later keyed into AutoCount and this outstanding-PO book is
uploaded, the two must not both count as on-order for the same (product, supplier) - AutoCount
is the book of record, so ITS import is what retires the CRM's own draft-turned-order. See
`app.services.scm.outstanding_import_service._supersede_crm_raised_pos`.

Same discipline as `test_outstanding_import_po.py`: every product, warehouse and supplier the
upload names is seeded under codes this test generates (`tests.scm._outstanding_workbooks`),
and the CRM-raised PO / order-inquiry chain is built directly on models under a
`zzt-oi-supersede` marker - never borrowed with `LIMIT 1` off a table CI's database holds
empty. Everything runs inside `pg_session()`, which rolls back.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.procurement import PurchaseOrder, PurchaseOrderLine
from app.models.product import Product
from app.models.project_so import (
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_ORDER,
    OrderInquiry,
    OrderInquiryRow,
)
from app.services.scm import outstanding_import_service as svc
from app.services.scm.outstanding_reader import PO
from tests._pg_fixture import pg_session
from tests.scm._outstanding_workbooks import (
    PO_MINIMAL,
    Codes,
    make_codes,
    po_minimal_row,
    po_workbook,
    seed_catalogue,
    seed_suppliers,
)
from tests.test_so_supply_confirmation import (
    _core_line as _confirm_core_line,
    _core_so as _confirm_core_so,
    _project_line as _confirm_project_line,
    _project_so as _confirm_project_so,
    _sorento as _confirm_sorento,
    _user as _confirm_user,
    _warehouse as _confirm_warehouse,
)

MARKER = "zzt-oi-supersede"


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def codes() -> Codes:
    return make_codes()


@pytest.fixture()
def seeded(db, codes):
    """Products, warehouses and suppliers under the exact codes this test's upload names."""
    seed_catalogue(db, codes, doc_type="outstanding_po")
    seed_suppliers(db, codes)
    return codes


# --------------------------------------------------------------------------- #
# readers
# --------------------------------------------------------------------------- #

def _company_id(db) -> str:
    return _confirm_sorento(db)


def _supplier_id(db, code: str) -> str:
    return db.execute(text("SELECT id FROM suppliers WHERE supplier_code = :c"),
                      {"c": code}).scalar()


def _product(db, code: str) -> Product:
    return db.query(Product).filter(Product.product_code == code).one()


def _po_status(db, po_id: str) -> str:
    return db.execute(text("SELECT status FROM purchase_orders WHERE id = :i"),
                      {"i": po_id}).scalar()


def _line_status(db, line_id: str) -> str:
    return db.execute(text("SELECT line_status FROM purchase_order_lines WHERE id = :i"),
                      {"i": line_id}).scalar()


def _ordered(db, item_code: str) -> float:
    """What `scm.po_ordered_v` counts as ORDERED for this item - the AutoCount book's own
    line if the CRM's duplicate was correctly retired, both if it was not."""
    return float(db.execute(text(
        "SELECT COALESCE(SUM(oo.ordered), 0) FROM scm.po_ordered_v oo "
        "JOIN products p ON p.id = oo.product_id WHERE p.product_code = :item"
    ), {"item": item_code}).scalar())


# --------------------------------------------------------------------------- #
# CRM-raised PO / order-inquiry seeding
# --------------------------------------------------------------------------- #

def _crm_po(db, company_id: str, supplier_id: str, *,
           status: str = "active", po_number: str | None = None) -> PurchaseOrder:
    """A purchase order the CRM itself raised from a reorder-plan `bulk_confirm` - the exact
    `source_system`/`status` shape `decision_service`/`purchase_order_service` leave behind."""
    po = PurchaseOrder(
        id=_u(),
        company_id=company_id,
        po_number=po_number or f"{MARKER}-CRMPO-{uuid.uuid4().hex[:8]}".upper(),
        supplier_id=supplier_id,
        status=status,
        source_system="scm_recommendation",
        source_ref="scm",
    )
    db.add(po)
    db.flush()
    return po


def _crm_po_line(db, company_id: str, po: PurchaseOrder, product_id: str, *,
                 qty_ordered="20", line_status="open") -> PurchaseOrderLine:
    line = PurchaseOrderLine(
        id=_u(),
        company_id=company_id,
        purchase_order_id=po.id,
        product_id=product_id,
        qty_ordered=Decimal(str(qty_ordered)),
        qty_received=Decimal("0"),
        line_status=line_status,
        source_system="scm_recommendation",
        source_ref=f"{MARKER}-rec-{uuid.uuid4().hex[:8]}",
    )
    db.add(line)
    db.flush()
    return line


def _placed_oi_row(db, company_id: str, product: Product, crm_po: PurchaseOrder,
                   crm_line: PurchaseOrderLine) -> OrderInquiryRow:
    """A raised buy row already tagged onto the CRM's own PO line - the shape
    `place_on_po`/`place_on_po_allocations` leave behind, built directly on the models so
    this file stays independent of that route."""
    user_id = _confirm_user(db, f"{MARKER} buyer")
    warehouse = _confirm_warehouse(db, f"ZZT-{MARKER}-{uuid.uuid4().hex[:6]}".upper())
    core_so = _confirm_core_so(db, company_id)
    core_line = _confirm_core_line(db, core_so, product, warehouse, qty_ordered="20")

    from app.services.project_service import register_project

    project = register_project(
        db, company_id=company_id, actor_user_id=user_id, developer_party_id=None,
        title=f"{MARKER} Project {uuid.uuid4().hex[:6]}",
    )
    order = _confirm_project_so(db, project, so_id=core_so.id)
    line = _confirm_project_line(db, order, line_no=1, product=product, core_line=core_line)

    inquiry = OrderInquiry(
        id=_u(), company_id=company_id, project_sales_order_id=order.id,
        state=INQUIRY_RAISED,
    )
    db.add(inquiry)
    db.flush()
    row = OrderInquiryRow(
        id=_u(), company_id=company_id, order_inquiry_id=inquiry.id, so_line_id=line.id,
        item_code=product.product_code, qty=Decimal("20"), verb=IV_ORDER,
        state=INQUIRY_PLACED, po_ref=crm_po.po_number, po_line_id=crm_line.id,
    )
    db.add(row)
    db.flush()
    return row


def _minimal_file(doc_no: str, creditor: str, item: str, qty, eta: date, location: str) -> bytes:
    return po_workbook(
        [po_minimal_row(doc_no, creditor, item, qty, eta, location)], headers=PO_MINIMAL,
    )


# --------------------------------------------------------------------------- #
# (a) import matching (product, supplier) closes the CRM line + empties -> closes the PO
# --------------------------------------------------------------------------- #

def test_import_matching_product_and_supplier_closes_the_crm_line_and_po(db, seeded):
    company_id = _company_id(db)
    supplier_id = _supplier_id(db, seeded.creditor_main)
    product = _product(db, seeded.item_rl)
    crm_po = _crm_po(db, company_id, supplier_id)
    crm_line = _crm_po_line(db, company_id, crm_po, product.id)

    file = _minimal_file(seeded.main_po, seeded.creditor_main, seeded.item_rl, 15,
                         date(2026, 7, 1), seeded.loc_project)

    out = svc.apply(db, file, PO)

    assert out["ok"]
    assert _line_status(db, crm_line.id) == "closed", \
        "the CRM's own draft-turned-order was not retired when AutoCount confirmed it"
    assert _po_status(db, crm_po.id) == "closed", \
        "the CRM PO's only line closed, so the header must close with it"
    assert out["superseded_documents"] == [
        {"po_number": crm_po.po_number, "superseded_by": seeded.main_po}
    ], "the supersession must be traceable: which CRM PO, and which AutoCount PO retired it"
    # Only the AutoCount book's own line counts as supply now - not both.
    assert _ordered(db, seeded.item_rl) == 15.0


def test_supersession_matches_on_product_and_supplier_never_on_document_number(db, seeded):
    """The CRM's own PO number and AutoCount's number for the same physical order are never
    the same string - proving the match still fires pins that this is (product, supplier),
    not a document-number coincidence."""
    company_id = _company_id(db)
    supplier_id = _supplier_id(db, seeded.creditor_main)
    product = _product(db, seeded.item_wt)
    crm_po = _crm_po(db, company_id, supplier_id, po_number=f"{MARKER}-DIFFERENT-NUMBER")
    crm_line = _crm_po_line(db, company_id, crm_po, product.id)

    file = _minimal_file(seeded.alt_po, seeded.creditor_main, seeded.item_wt, 5,
                         date(2026, 7, 1), seeded.loc_dealer)

    svc.apply(db, file, PO)

    assert _line_status(db, crm_line.id) == "closed"


# --------------------------------------------------------------------------- #
# (b) a placed order-inquiry row on that line is unplaced first
# --------------------------------------------------------------------------- #

def test_a_placed_order_inquiry_row_on_the_closed_line_is_unplaced(db, seeded):
    company_id = _company_id(db)
    supplier_id = _supplier_id(db, seeded.creditor_main)
    product = _product(db, seeded.item_wt)
    crm_po = _crm_po(db, company_id, supplier_id)
    crm_line = _crm_po_line(db, company_id, crm_po, product.id)
    row = _placed_oi_row(db, company_id, product, crm_po, crm_line)

    file = _minimal_file(seeded.alt_po, seeded.creditor_main, seeded.item_wt, 5,
                         date(2026, 7, 1), seeded.loc_dealer)

    svc.apply(db, file, PO)

    db.refresh(row)
    assert row.state == INQUIRY_RAISED, \
        "a row left `placed` on a line that just closed would dangle"
    assert row.po_line_id is None
    assert row.po_ref is None
    assert _line_status(db, crm_line.id) == "closed"


# --------------------------------------------------------------------------- #
# (c) a non-matching CRM PO is untouched
# --------------------------------------------------------------------------- #

def test_a_non_matching_crm_po_is_untouched(db, seeded):
    """Same supplier, a DIFFERENT product than the file names - must not be swept up."""
    company_id = _company_id(db)
    supplier_id = _supplier_id(db, seeded.creditor_main)
    other_product = _product(db, seeded.item_blue)
    crm_po = _crm_po(db, company_id, supplier_id)
    crm_line = _crm_po_line(db, company_id, crm_po, other_product.id)

    file = _minimal_file(seeded.main_po, seeded.creditor_main, seeded.item_rl, 15,
                         date(2026, 7, 1), seeded.loc_project)

    out = svc.apply(db, file, PO)

    assert out["ok"]
    assert _line_status(db, crm_line.id) == "open"
    assert _po_status(db, crm_po.id) == "active"
    assert out["superseded_documents"] == []


def test_a_crm_po_for_a_different_supplier_is_untouched(db, seeded):
    """Same product, a DIFFERENT supplier than the file's creditor resolves to."""
    company_id = _company_id(db)
    other_supplier_id = _supplier_id(db, seeded.creditor_alt)
    product = _product(db, seeded.item_rl)
    crm_po = _crm_po(db, company_id, other_supplier_id)
    crm_line = _crm_po_line(db, company_id, crm_po, product.id)

    file = _minimal_file(seeded.main_po, seeded.creditor_main, seeded.item_rl, 15,
                         date(2026, 7, 1), seeded.loc_project)

    svc.apply(db, file, PO)

    assert _line_status(db, crm_line.id) == "open"
    assert _po_status(db, crm_po.id) == "active"


# --------------------------------------------------------------------------- #
# (d) idempotent: re-running the same upload does not error or double-close
# --------------------------------------------------------------------------- #

def test_reapplying_the_same_file_is_idempotent(db, seeded):
    company_id = _company_id(db)
    supplier_id = _supplier_id(db, seeded.creditor_main)
    product = _product(db, seeded.item_rl)
    crm_po = _crm_po(db, company_id, supplier_id)
    crm_line = _crm_po_line(db, company_id, crm_po, product.id)

    file = _minimal_file(seeded.main_po, seeded.creditor_main, seeded.item_rl, 15,
                         date(2026, 7, 1), seeded.loc_project)

    first = svc.apply(db, file, PO)
    second = svc.apply(db, file, PO)

    assert first["ok"] and second["ok"]
    assert first["superseded_documents"] == [
        {"po_number": crm_po.po_number, "superseded_by": seeded.main_po}
    ]
    assert second["superseded_documents"] == [], \
        "the CRM line is already closed; a second run must find nothing left to supersede"
    assert _line_status(db, crm_line.id) == "closed"
    assert _po_status(db, crm_po.id) == "closed"
    assert _ordered(db, seeded.item_rl) == 15.0, "re-running must not double the AutoCount line"


# --------------------------------------------------------------------------- #
# (e) a draft CRM recommendation is not on-order yet and is never touched
# --------------------------------------------------------------------------- #

def test_a_draft_recommendation_po_is_untouched(db, seeded):
    """`draft_recommendation` is not yet on-order (M4-D5), so there is nothing here for
    AutoCount to have superseded - the CRM has not even placed this order yet."""
    company_id = _company_id(db)
    supplier_id = _supplier_id(db, seeded.creditor_main)
    product = _product(db, seeded.item_rl)
    draft_po = _crm_po(db, company_id, supplier_id, status="draft_recommendation")
    draft_line = _crm_po_line(db, company_id, draft_po, product.id)

    file = _minimal_file(seeded.main_po, seeded.creditor_main, seeded.item_rl, 15,
                         date(2026, 7, 1), seeded.loc_project)

    out = svc.apply(db, file, PO)

    assert out["ok"]
    assert _line_status(db, draft_line.id) == "open"
    assert _po_status(db, draft_po.id) == "draft_recommendation"
    assert out["superseded_documents"] == []
