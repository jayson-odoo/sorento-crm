"""PR / SF printable PDF, and the PIC field.

Two problems this covers, both reported from production.

1. **Printing.** The only export was Excel. A long delivery address stretched one
   cell to an enormous width and the printed sheet was unusable — a data format
   doing a document's job. PR/SF now render a fixed-layout PDF through the same
   mechanism complaints and stock inquiries use, so "tidy" is the acceptance
   criterion, not a nice-to-have: a pathological address must WRAP inside its
   cell and never widen the table.

2. **PIC.** There was nowhere to record the person receiving the delivery, so
   staff typed them into the address:
   ``2, Lebuh Cecil, Ghaut, 10300 George Town, Pulau Pinang Contact: Hanson
   (012-403 9611)``. The address became two facts in one column. PIC is a
   separate, optional, free-text field, printed on the PDF.

PR and SF share one table and one detail component, so every assertion here runs
against BOTH request_type values — a field that works for one and not the other
is the regression this guards.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.procurement import PurchaseRequestHeader
from tests._pg_fixture import blank_session

# The real address from the report, with the contact jammed on the end, plus a
# deliberately unbroken token: `pre-wrap` alone wraps on spaces, so a long
# no-space string is the case that actually escapes a fixed-width cell.
PATHOLOGICAL_ADDRESS = (
    "2, Lebuh Cecil, Ghaut, 10300 George Town, Pulau Pinang, Malaysia, "
    "Level 14 Menara Northam Jalan Sultan Ahmad Shah, Georgetown 10050 "
    "REFERENCE-NO-WITH-NO-SPACES-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
)
PIC_VALUE = "Hanson (012-403 9611)"

BOTH_TYPES = ["purchase_request", "sponsorship_form"]


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _make(db, *, request_type: str, **overrides) -> PurchaseRequestHeader:
    fields = dict(
        id=str(uuid.uuid4()),
        request_type=request_type,
        request_number=f"ZZT-{uuid.uuid4().hex[:6]}",
        customer_name="KEE LIN TRADING SDN BHD (PROJECT)",
        project_title="ECO SUMMIT AIRMAS SILK SPRING",
        delivery_address="2, Lebuh Cecil, Ghaut, 10300 George Town",
    )
    fields.update(overrides)  # a caller-supplied value replaces the default
    row = PurchaseRequestHeader(**fields)
    db.add(row)
    db.flush()
    return row


# --- PIC field -------------------------------------------------------------- #

@pytest.mark.parametrize("request_type", BOTH_TYPES)
def test_pic_persists_on_both_form_types(db, request_type):
    row = _make(db, request_type=request_type, pic=PIC_VALUE)
    db.commit()
    db.expire_all()

    fetched = db.query(PurchaseRequestHeader).filter_by(id=row.id).one()
    assert fetched.pic == PIC_VALUE


@pytest.mark.parametrize("request_type", BOTH_TYPES)
def test_pic_is_optional(db, request_type):
    """Explicitly not mandatory — a form with no named contact must still save."""
    row = _make(db, request_type=request_type)
    db.commit()
    db.expire_all()

    assert db.query(PurchaseRequestHeader).filter_by(id=row.id).one().pic is None


# --- PDF -------------------------------------------------------------------- #

def _render(db, row):
    from app.services.purchase_request_pdf_service import PurchaseRequestPDFService

    return PurchaseRequestPDFService(db).render_pdf(str(row.id))


@pytest.mark.parametrize("request_type", BOTH_TYPES)
def test_renders_a_pdf_for_both_form_types(db, request_type):
    row = _make(db, request_type=request_type, pic=PIC_VALUE)
    db.commit()

    pdf_bytes, filename = _render(db, row)

    assert pdf_bytes[:4] == b"%PDF", "not a PDF"
    assert len(pdf_bytes) > 800, "suspiciously small PDF"
    assert filename.endswith(".pdf")


def test_filename_names_the_document_type(db):
    """A folder of downloads must be sortable by what the document IS."""
    pr = _make(db, request_type="purchase_request", request_number="PR26-0332")
    sf = _make(db, request_type="sponsorship_form", request_number="PSSF26-0354")
    db.commit()

    assert _render(db, pr)[1] == "purchase-request-PR26-0332.pdf"
    assert _render(db, sf)[1] == "sponsorship-form-PSSF26-0354.pdf"


@pytest.mark.parametrize("request_type", BOTH_TYPES)
def test_pic_is_printed(db, request_type):
    """The whole point of the field is that it reaches the printed page."""
    from app.services.purchase_request_pdf_service import PurchaseRequestPDFService

    row = _make(db, request_type=request_type, pic=PIC_VALUE)
    db.commit()

    html = PurchaseRequestPDFService(db)._html(row)
    assert "PIC" in html.upper()
    assert "Hanson" in html


@pytest.mark.parametrize("request_type", BOTH_TYPES)
def test_a_long_address_cannot_widen_the_table(db, request_type):
    """AC-9, the actual bug being fixed.

    The Excel export blew its column out to the width of the address. The PDF
    must not: the table is a fixed 100% width and the cell has to break a long
    unbroken token rather than push the layout wider than the page.
    """
    from app.services.purchase_request_pdf_service import PurchaseRequestPDFService

    row = _make(db, request_type=request_type, delivery_address=PATHOLOGICAL_ADDRESS)
    db.commit()
    svc = PurchaseRequestPDFService(db)
    html = svc._html(row)

    assert "table-layout: fixed" in html, "a fixed layout is what stops a cell widening"
    assert "width: 100%" in html.replace("width:100%", "width: 100%")
    assert "overflow-wrap: anywhere" in html or "word-break: break-all" in html, (
        "without a break rule an unbroken token overflows the cell"
    )
    # And it must actually render at that size.
    pdf_bytes, _ = svc.render_pdf(str(row.id))
    assert pdf_bytes[:4] == b"%PDF"


@pytest.mark.parametrize("request_type", BOTH_TYPES)
def test_internal_only_fields_are_not_printed(db, request_type):
    """Same rule the complaint / stock-inquiry PDFs follow: a printed copy handed
    to a driver must not carry SLA tiers, assignees or audit trail."""
    from app.services.purchase_request_pdf_service import PurchaseRequestPDFService

    row = _make(db, request_type=request_type, pic=PIC_VALUE)
    db.commit()

    html = PurchaseRequestPDFService(db)._html(row).lower()
    for leaked in ("sla", "assignee", "escalat", "audit", "handling lock"):
        assert leaked not in html, f"internal field {leaked!r} reached the printed copy"


def test_a_form_with_no_line_items_still_renders(db):
    """An empty section gets an explicit empty state, never a crash or a blank."""
    row = _make(db, request_type="purchase_request")
    db.commit()

    pdf_bytes, _ = _render(db, row)
    assert pdf_bytes[:4] == b"%PDF"


def test_a_missing_record_is_a_404_not_a_500(db):
    from fastapi import HTTPException

    from app.services.purchase_request_pdf_service import PurchaseRequestPDFService

    with pytest.raises((HTTPException, Exception)) as exc:
        PurchaseRequestPDFService(db).render_pdf(str(uuid.uuid4()))
    assert "404" in str(exc.value) or "not found" in str(exc.value).lower()


# --- AI extraction ---------------------------------------------------------- #

@pytest.mark.parametrize(
    "form_key", ["portal.purchase_request", "portal.sponsorship_form"]
)
def test_pic_is_an_extractable_field_on_both_portal_forms(form_key):
    """The portal pre-fills from an uploaded document; PIC has to be in that set
    or the field the user was told about silently never populates."""
    from app.services.ai_extract.form_schema_registry import get_form_schema

    names = {f.name for f in get_form_schema(form_key)}
    assert "pic" in names, f"{form_key} cannot extract PIC"


@pytest.mark.parametrize(
    "form_key", ["portal.purchase_request", "portal.sponsorship_form"]
)
def test_the_pic_prompt_disambiguates_from_the_salesperson(form_key):
    """The model's failure mode here is grabbing whichever human name it sees
    first. customer_name needed the same steer and its note is long for exactly
    that reason."""
    from app.services.ai_extract.form_schema_registry import get_form_schema

    spec = next(f for f in get_form_schema(form_key) if f.name == "pic")
    note = (spec.note or "").lower()
    assert note, "PIC has no note, so nothing stops the model taking the salesperson"
    assert "salesperson" in note or "sales person" in note


# --- the portal allowlist (this one actually shipped broken) ---------------- #

@pytest.mark.parametrize("kind", ["purchase_request", "sponsorship_form"])
def test_pic_survives_a_portal_submission(kind):
    """PIC was on the portal form, the user filled it, and it silently vanished.

    ``PortalService`` applies an explicit per-kind allowlist of editable fields;
    anything absent is dropped without an error, so the field rendered, accepted
    input, and saved NULL. Adding a column and a form widget is not enough - the
    allowlist is a third place that has to know about it.
    """
    from app.services.portal_service import PortalService

    # instance method, but the allowlist depends only on `kind`
    fields = PortalService._editable_fields(None, kind)  # type: ignore[arg-type]
    assert "pic" in fields, (
        f"pic missing from the {kind} portal allowlist — the field renders, accepts "
        "input, and is then silently dropped on submit"
    )
