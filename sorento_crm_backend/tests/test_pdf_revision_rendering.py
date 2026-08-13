"""Snapshot-fed PDF rendering: one superseded version, and the full lineage.

PLAN-portal-submission-revisions 6.3 / 6.4. The assertions are on the HTML the
services build, not on the PDF bytes: WeasyPrint's native libraries are not
present on every host, and the thing that can actually be wrong is WHICH values
reach the page.

The one rule under test throughout: a revision page renders the values stored in
that version's snapshot, never the live row's. A printed history that quietly
shows today's data is worse than no history at all.

Every test seeds its own chain (settings -> config -> contact -> entity) through
the shared revision harness and drives the real revise transaction, so the
snapshots are the ones production writes.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.services.portal_revision_service import PortalRevisionService
from app.services.purchase_request_pdf_service import PurchaseRequestPDFService
from app.services.stock_inquiry_pdf_service import StockInquiryPDFService
from tests._pg_fixture import blank_session
from tests._revision_harness import (
    seed_config,
    seed_contact,
    seed_entity,
    seed_system_settings,
    seed_token,
)

ORIGINAL_DESCRIPTION = "Free Standing Bath Tub Mixer"  # what the harness seeds
SECOND_DESCRIPTION = "Second description"
THIRD_DESCRIPTION = "Third description"

FIRST_REASON = "Customer corrected the quantity"
SECOND_REASON = "Customer changed the model"

REQUEST_TYPES = ["purchase_request", "sponsorship_form"]


@pytest.fixture(autouse=True)
def no_queue():
    """Never enqueue a real RQ job: a worker in another worktree would pick it up."""
    with patch("app.services.queue_service.enqueue_job", return_value=None):
        yield


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _setup(db, kind, **entity_kwargs):
    seed_system_settings(db, cap=3)
    seed_config(db, kind)
    contact = seed_contact(db)
    row = seed_entity(db, kind, contact, **entity_kwargs)
    return seed_token(contact), row


def _revise(db, token, kind, row, payload, reason, expected):
    return PortalRevisionService(db).revise(
        token, kind, str(row.id), payload, reason, expected
    )


def _entries(db, kind, row):
    return PortalRevisionService(db).list_revisions(kind, str(row.id))


# --------------------------------------------------------------- stock inquiry


def _si_with_two_revisions(db):
    """Original -> revision 1 -> revision 2, so revision 1 is genuinely behind
    both the original and the live row."""
    token, row = _setup(db, "stock_inquiry")
    _revise(
        db, token, "stock_inquiry", row,
        {"item_description": SECOND_DESCRIPTION, "quantity": "9"},
        FIRST_REASON, 0,
    )
    _revise(
        db, token, "stock_inquiry", row,
        {"item_description": THIRD_DESCRIPTION, "quantity": "12"},
        SECOND_REASON, 1,
    )
    return row, _entries(db, "stock_inquiry", row)


def test_stock_inquiry_revision_renders_the_superseded_values(db):
    row, entries = _si_with_two_revisions(db)
    revision_one = next(e for e in entries if e["revision_no"] == 1)

    html = StockInquiryPDFService(db).build_html(
        str(row.id), revision_id=revision_one["id"]
    )

    # The version's own values, from its snapshot.
    assert SECOND_DESCRIPTION in html
    assert "Revision 1" in html
    assert FIRST_REASON in html
    # ...and NOT the live row's, which is two versions ahead.
    assert THIRD_DESCRIPTION not in html
    assert SECOND_REASON not in html
    # A version behind the newest says so, so nobody mistakes it for current.
    assert "(superseded)" in html


def test_stock_inquiry_revision_never_prints_a_status(db):
    """The snapshot is written BEFORE the restart status is applied, so its status
    is stale by design and must not reach the page."""
    row, entries = _si_with_two_revisions(db)
    revision_one = next(e for e in entries if e["revision_no"] == 1)

    html = StockInquiryPDFService(db).build_html(
        str(row.id), revision_id=revision_one["id"]
    )

    for status_text in (
        "Pending purchasing",
        "Pending project sales",
        "pending_purchasing",
        "pending_project_sales",
    ):
        assert status_text not in html, status_text


def test_stock_inquiry_revision_carries_the_suffixed_number(db):
    row, entries = _si_with_two_revisions(db)
    revision_one = next(e for e in entries if e["revision_no"] == 1)

    html = StockInquiryPDFService(db).build_html(
        str(row.id), revision_id=revision_one["id"]
    )
    assert f"{row.inquiry_number}-R1" in html


def test_stock_inquiry_original_entry_renders_the_first_submitted_values(db):
    row, entries = _si_with_two_revisions(db)
    original = next(e for e in entries if e["version_no"] == 0)

    html = StockInquiryPDFService(db).build_html(str(row.id), revision_id=original["id"])

    assert ORIGINAL_DESCRIPTION in html
    assert "Original" in html
    assert SECOND_DESCRIPTION not in html
    assert THIRD_DESCRIPTION not in html


def test_stock_inquiry_current_form_is_unchanged_by_default(db):
    row, _lineage = _si_with_two_revisions(db)

    html = StockInquiryPDFService(db).build_html(str(row.id))

    assert THIRD_DESCRIPTION in html
    assert SECOND_DESCRIPTION not in html
    assert "Revision 1" not in html
    assert "page-break-before" not in html


def test_stock_inquiry_include_revisions_appends_the_whole_lineage(db):
    row, _lineage = _si_with_two_revisions(db)

    html = StockInquiryPDFService(db).build_html(str(row.id), include_revisions=True)

    # Current form first, then newest revision, then the original.
    assert html.index(THIRD_DESCRIPTION) < html.index(SECOND_DESCRIPTION)
    assert html.index(SECOND_DESCRIPTION) < html.index(ORIGINAL_DESCRIPTION)
    assert "page-break-before: always" in html
    assert "Revision 2" in html and "Revision 1" in html


def test_stock_inquiry_include_revisions_on_a_never_revised_form_is_just_the_form(db):
    _token, row = _setup(db, "stock_inquiry")

    html = StockInquiryPDFService(db).build_html(str(row.id), include_revisions=True)

    assert ORIGINAL_DESCRIPTION in html
    assert "page-break-before" not in html
    # No lineage to append: a never-revised form prints exactly as it always has.
    assert "(superseded)" not in html
    assert "Reason:" not in html


def test_render_pdf_names_the_file_after_the_version(db):
    """The filename is what stops two versions of one form overwriting each other
    in a downloads folder (UAC N5). Skipped where WeasyPrint has no native libs.

    It is named after THAT version's own document number, not the record's
    current one plus a second revision marker: `-SI-26-0184-R2-rev1.pdf` states
    two different versions in one filename and leaves the reader to decode which
    one the document is. Exactly one marker rides along to say the file is a
    stored version rather than the live record.
    """
    from app.services.pdf_render import PDFRenderingUnavailable

    row, entries = _si_with_two_revisions(db)
    revision_one = next(e for e in entries if e["revision_no"] == 1)
    original = next(e for e in entries if e["version_no"] == 0)
    service = StockInquiryPDFService(db)

    try:
        _bytes, revision_name = service.render_pdf(
            str(row.id), revision_id=revision_one["id"]
        )
    except PDFRenderingUnavailable as exc:
        pytest.skip(f"WeasyPrint native libs unavailable on host: {exc}")
        return
    original_bytes, original_name = service.render_pdf(
        str(row.id), revision_id=original["id"]
    )

    assert original_bytes[:5] == b"%PDF-"
    assert revision_name == f"product-inquiry-{row.inquiry_number}-R1-as-submitted.pdf"
    # Version 0's own number is the bare one, which is exactly the current form's
    # filename on a never-revised record - so it carries its own marker, and the
    # two never stack.
    assert original_name == f"product-inquiry-{row.inquiry_number}-original.pdf"
    # The live record export stays unmarked, and is a DIFFERENT document from the
    # newest revision's (it carries the purchasing reply and the status), so the
    # two must not share a name in My Downloads.
    assert service.build_filename(row) == f"product-inquiry-{row.inquiry_number}-R2.pdf"
    _newest_html, newest_name = service._build(
        str(row.id), revision_id=entries[-1]["id"]
    )
    assert newest_name == f"product-inquiry-{row.inquiry_number}-R2-as-submitted.pdf"
    assert newest_name != service.build_filename(row)


# ------------------------------------------------------------------ timezone


def _stamp_submitted_at(db, entry_id, when):
    """Force ONE lineage row's submitted_at, so a fixed instant can be asserted."""
    from app.models.portal import PortalFormRevision

    row = (
        db.query(PortalFormRevision)
        .filter(PortalFormRevision.id == str(entry_id))
        .one()
    )
    row.submitted_at = when
    db.flush()


def test_stock_inquiry_revision_dates_print_in_malaysia_time(db):
    """A submission stored at 17:00 UTC is the 13th in Malaysia, and the PDF must
    say so.

    `submitted_at` is stored naive UTC and every other surface renders it through
    the frontend's `formatDateInMalaysia`. Printing the raw components would date
    this version 12/08/2026 on the PDF and 13/08/2026 on the screen and the Excel
    sheet - two documents of ONE revision disagreeing by a day, on a date UAC P2
    makes load-bearing.
    """
    from datetime import datetime

    row, entries = _si_with_two_revisions(db)
    revision_one = next(e for e in entries if e["revision_no"] == 1)
    _stamp_submitted_at(db, revision_one["id"], datetime(2026, 8, 12, 17, 0, 0))

    html = StockInquiryPDFService(db).build_html(
        str(row.id), revision_id=revision_one["id"]
    )

    assert "submitted 13/08/2026" in html
    assert "12/08/2026" not in html


def test_unknown_revision_id_is_a_404(db):
    row, _lineage = _si_with_two_revisions(db)

    with pytest.raises(HTTPException) as exc:
        StockInquiryPDFService(db).build_html(
            str(row.id), revision_id=str(uuid.uuid4())
        )
    assert exc.value.status_code == 404


def test_a_revision_of_another_inquiry_is_a_404(db):
    """A real revision id that belongs to a different record must 404 exactly as
    an invented one does - the export is scoped to ONE submission's lineage."""
    row, _lineage = _si_with_two_revisions(db)

    # A second inquiry under the SAME config (one config row per type).
    other_contact = seed_contact(db)
    other_row = seed_entity(db, "stock_inquiry", other_contact)
    _revise(
        db, seed_token(other_contact), "stock_inquiry", other_row,
        {"item_description": "Other description"}, FIRST_REASON, 0,
    )
    other_entries = _entries(db, "stock_inquiry", other_row)
    assert other_row.id != row.id

    with pytest.raises(HTTPException) as exc:
        StockInquiryPDFService(db).build_html(
            str(row.id), revision_id=other_entries[0]["id"]
        )
    assert exc.value.status_code == 404


# ------------------------------------------- purchase request / sponsorship form


def _request_with_one_revision(db, kind):
    """Original (Marker project / ITEM-A) -> revision 1 (Revised / ITEM-B)."""
    token, row = _setup(db, kind)
    _revise(
        db, token, kind, row,
        {
            "project_title": "Revised project",
            "products": [{"item_code": "ITEM-B", "quantity": 3}],
        },
        FIRST_REASON, 0,
    )
    return row, _entries(db, kind, row)


@pytest.mark.parametrize("kind", REQUEST_TYPES)
def test_request_include_revisions_prints_current_then_history(db, kind):
    row, _lineage = _request_with_one_revision(db, kind)

    html = PurchaseRequestPDFService(db).build_html(str(row.id), include_revisions=True)

    # The current form leads; the superseded version follows it.
    assert html.index("Revised project") < html.index("Marker project")
    assert "page-break-before: always" in html
    assert "Revision 1" in html
    assert FIRST_REASON in html
    # The type's own heading still comes from the live header, on every page.
    title = "Project Sales Sponsorship Form" if kind == "sponsorship_form" else "Purchase Request"
    assert title in html


@pytest.mark.parametrize("kind", REQUEST_TYPES)
def test_request_line_items_come_from_the_snapshot(db, kind):
    row, _lineage = _request_with_one_revision(db, kind)

    html = PurchaseRequestPDFService(db).build_html(str(row.id), include_revisions=True)

    # ITEM-A exists nowhere but the original's snapshot: the live row's lines were
    # replaced by the revision.
    assert "ITEM-A" in html
    assert html.index("ITEM-B") < html.index("ITEM-A")


@pytest.mark.parametrize("kind", REQUEST_TYPES)
def test_request_single_revision_document_is_snapshot_only(db, kind):
    row, entries = _request_with_one_revision(db, kind)
    original = next(e for e in entries if e["version_no"] == 0)

    html = PurchaseRequestPDFService(db).build_html(
        str(row.id), revision_id=original["id"]
    )

    assert "Marker project" in html
    assert "ITEM-A" in html
    assert "Revised project" not in html
    assert "ITEM-B" not in html
    # The original was reconstructed on first revise, and the note folds into the
    # label's own bracket rather than stuttering a second one.
    assert "Original (reconstructed, superseded)" in html


@pytest.mark.parametrize("kind", REQUEST_TYPES)
def test_request_current_form_is_unchanged_by_default(db, kind):
    row, _lineage = _request_with_one_revision(db, kind)

    html = PurchaseRequestPDFService(db).build_html(str(row.id))

    assert "Revised project" in html
    assert "Marker project" not in html
    assert "page-break-before" not in html


@pytest.mark.parametrize("kind", REQUEST_TYPES)
def test_request_revision_id_wins_over_include_revisions(db, kind):
    """The route rejects the combination; the service still has to be unambiguous."""
    row, entries = _request_with_one_revision(db, kind)
    original = next(e for e in entries if e["version_no"] == 0)

    html = PurchaseRequestPDFService(db).build_html(
        str(row.id), revision_id=original["id"], include_revisions=True
    )

    assert "Marker project" in html
    assert "Revised project" not in html


@pytest.mark.parametrize("kind", REQUEST_TYPES)
def test_request_revision_filename_is_that_versions_own_number(db, kind):
    """The filename rule, on the two types whose stem differs from the inquiry's."""
    row, entries = _request_with_one_revision(db, kind)
    revision_one = next(e for e in entries if e["revision_no"] == 1)
    original = next(e for e in entries if e["version_no"] == 0)
    service = PurchaseRequestPDFService(db)
    stem = "sponsorship-form" if kind == "sponsorship_form" else "purchase-request"

    _html, revision_name = service._build(str(row.id), revision_id=revision_one["id"])
    _original_html, original_name = service._build(
        str(row.id), revision_id=original["id"]
    )

    assert revision_name == f"{stem}-{row.request_number}-R1-as-submitted.pdf"
    assert original_name == f"{stem}-{row.request_number}-original.pdf"
    # The record sits at R1 too, and its own export is a different document.
    assert revision_name != service.build_filename(row)


@pytest.mark.parametrize("kind", REQUEST_TYPES)
def test_request_revision_dates_print_in_malaysia_time(db, kind):
    """The 17:00 UTC instant again, on the form whose Date sits beside the number."""
    from datetime import datetime

    row, entries = _request_with_one_revision(db, kind)
    revision_one = next(e for e in entries if e["revision_no"] == 1)
    _stamp_submitted_at(db, revision_one["id"], datetime(2026, 8, 12, 17, 0, 0))

    html = PurchaseRequestPDFService(db).build_html(
        str(row.id), revision_id=revision_one["id"]
    )

    assert "submitted 13/08/2026" in html
    # The Date cell beside the number carries the same day, in the type's format.
    assert ("13-Aug-2026" if kind == "sponsorship_form" else "13/8/2026") in html
