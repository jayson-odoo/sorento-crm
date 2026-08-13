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


def test_stock_inquiry_include_revisions_appends_every_earlier_version(db):
    row, _lineage = _si_with_two_revisions(db)

    html = StockInquiryPDFService(db).build_html(str(row.id), include_revisions=True)

    # Current form first, then revision 1, then the original. The NEWEST entry
    # gets no page of its own - it is the version the current form already shows.
    assert html.index(THIRD_DESCRIPTION) < html.index(SECOND_DESCRIPTION)
    assert html.index(SECOND_DESCRIPTION) < html.index(ORIGINAL_DESCRIPTION)
    assert "page-break-before: always" in html
    assert "Revision 2" in html and "Revision 1" in html


def test_stock_inquiry_include_revisions_prints_the_current_version_once(db):
    """The newest lineage entry is the version the current form shows.

    Printing it as its own page put the same form on page 1 and page 2, which is
    what the user reported: "if we print current revision again then will be
    double print".
    """
    row, entries = _si_with_two_revisions(db)
    assert entries[-1]["revision_no"] == 2

    html = StockInquiryPDFService(db).build_html(str(row.id), include_revisions=True)

    # The newest version's values appear exactly once, on the current form page.
    assert html.count(THIRD_DESCRIPTION) == 1
    # Exactly two pages carry a superseded heading: revision 1 and the original
    # (whose note folds into its own bracket, "Original (reconstructed, superseded)").
    assert html.count("superseded") == 2
    # ...and its context is not lost with its page: which revision the current
    # form is, who sent it and why, now reads on the current form itself.
    assert html.index("Revision 2") < html.index("Revision 1")
    assert SECOND_REASON in html


def test_stock_inquiry_include_revisions_handles_a_resubmission_at_revision_zero(db):
    """An office reject that the contact answers advances the VERSION, never the
    revision (UAC C1/C4), so both entries sit at ``revision_no = 0``. The newest is
    still the version in play, so it is still the one that must not print twice."""
    _token, row = _setup(db, "stock_inquiry")
    service = PortalRevisionService(db)
    service.record_initial("stock_inquiry", row, None)
    row.item_description = SECOND_DESCRIPTION
    db.commit()
    service.record_resubmission(
        "stock_inquiry", row, None, reason="Missing the delivery address"
    )
    db.commit()
    entries = _entries(db, "stock_inquiry", row)
    assert [e["revision_no"] for e in entries] == [0, 0]

    html = StockInquiryPDFService(db).build_html(str(row.id), include_revisions=True)

    assert html.count(SECOND_DESCRIPTION) == 1  # the current form, once
    assert ORIGINAL_DESCRIPTION in html  # the version behind it, on its own page
    assert html.count("(superseded)") == 1


def test_stock_inquiry_newest_revision_still_exports_on_its_own(db):
    """Skipping the newest entry is an ``include_revisions`` rule only.

    Asking for that entry BY ID is a different document (UAC P1/P2) - the snapshot
    without the office fields the live row carries - so it still prints in full.
    """
    row, entries = _si_with_two_revisions(db)
    newest = entries[-1]

    html = StockInquiryPDFService(db).build_html(str(row.id), revision_id=newest["id"])

    assert THIRD_DESCRIPTION in html
    assert "Revision 2" in html
    # It is the version in play, so it is not headed as superseded.
    assert "(superseded)" not in html
    assert SECOND_DESCRIPTION not in html


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


# ---------------------------------------------------------------- attachments


def _seed_attachment(db, row, *, filename: str, mime: str) -> str:
    """One file linked to the entity, so the next snapshot records it."""
    from app.models.entity_attachment import EntityAttachmentLink
    from app.models.resources import Attachment

    att = Attachment(
        id=str(uuid.uuid4()),
        original_filename=filename,
        stored_filename=filename,
        file_path=f"uploads/{filename}",
        mime_type=mime,
        file_size_bytes=1234,
    )
    db.add(att)
    db.add(
        EntityAttachmentLink(
            id=str(uuid.uuid4()),
            entity_type="stock_inquiry",
            entity_id=str(row.id),
            attachment_id=att.id,
        )
    )
    db.commit()
    return str(att.id)


@pytest.fixture
def storage(monkeypatch):
    """Stub the storage backend: what matters is which bytes reach the page, not
    that a real bucket answered. ``failing`` names files whose fetch blows up."""
    import app.services.storage_router as storage_router

    state = {"failing": set()}

    class _Backend:
        def download_file(self, key):
            if any(name in str(key) for name in state["failing"]):
                raise RuntimeError("object missing")
            return b"\xff\xd8\xff-image-bytes"

    monkeypatch.setattr(storage_router, "get_backend", lambda provider: _Backend())
    monkeypatch.setattr(
        storage_router, "resolve_signed_url", lambda path, provider=None: f"https://cdn/{path}"
    )
    return state


def test_stock_inquiry_revision_embeds_that_versions_own_photos(db, storage):
    """A revision page prints its photos, from ITS OWN attachment set.

    The file is unlinked after the revision, so nothing but the snapshot knows it
    was ever there (UAC G6) - which is exactly the file a historical page exists
    to show, and it still renders.
    """
    from app.models.entity_attachment import EntityAttachmentLink

    token, row = _setup(db, "stock_inquiry")
    _seed_attachment(db, row, filename="site-photo.jpg", mime="image/jpeg")
    _revise(
        db, token, "stock_inquiry", row,
        {"item_description": SECOND_DESCRIPTION}, FIRST_REASON, 0,
    )
    db.query(EntityAttachmentLink).filter(
        EntityAttachmentLink.entity_id == str(row.id)
    ).delete()
    db.commit()

    entries = _entries(db, "stock_inquiry", row)
    original = next(e for e in entries if e["version_no"] == 0)
    html = StockInquiryPDFService(db).build_html(str(row.id), revision_id=original["id"])

    assert "data:image/jpeg;base64," in html
    assert "site-photo.jpg" in html
    # The current form has no attachments left, so its own photo section is empty -
    # the revision page is not reading today's files.
    assert "data:image/jpeg;base64," not in StockInquiryPDFService(db).build_html(str(row.id))


def test_stock_inquiry_revision_lists_a_non_image_by_name(db, storage):
    token, row = _setup(db, "stock_inquiry")
    _seed_attachment(db, row, filename="quotation.pdf", mime="application/pdf")
    _revise(
        db, token, "stock_inquiry", row,
        {"item_description": SECOND_DESCRIPTION}, FIRST_REASON, 0,
    )

    entries = _entries(db, "stock_inquiry", row)
    original = next(e for e in entries if e["version_no"] == 0)
    html = StockInquiryPDFService(db).build_html(str(row.id), revision_id=original["id"])

    assert "quotation.pdf" in html
    assert "data:" not in html


def test_an_unfetchable_revision_photo_degrades_to_its_filename(db, storage):
    """One dead object must cost its own image, never the whole document."""
    token, row = _setup(db, "stock_inquiry")
    _seed_attachment(db, row, filename="gone.jpg", mime="image/jpeg")
    _seed_attachment(db, row, filename="kept.jpg", mime="image/jpeg")
    storage["failing"].add("gone.jpg")
    _revise(
        db, token, "stock_inquiry", row,
        {"item_description": SECOND_DESCRIPTION}, FIRST_REASON, 0,
    )

    entries = _entries(db, "stock_inquiry", row)
    original = next(e for e in entries if e["version_no"] == 0)
    html = StockInquiryPDFService(db).build_html(str(row.id), revision_id=original["id"])

    assert "data:image/jpeg;base64," in html  # the readable one still embeds
    assert "gone.jpg" in html  # ...and the dead one is still named


@pytest.mark.parametrize(
    "filename, mime, unfetchable",
    [
        ("site-photo.jpg", "image/jpeg", False),  # the caption under an embedded photo
        ("quotation.pdf", "application/pdf", False),  # a listed non-image
        ("gone.jpg", "image/jpeg", True),  # an image degraded to its name
    ],
)
def test_a_file_renamed_later_is_named_as_it_was_at_that_revision(
    db, storage, filename, mime, unfetchable
):
    """A historical page names a file as it was named THEN.

    Reading the live row would print today's name under an "as it was" heading -
    the same lie the snapshot exists to prevent, moved from the field values into
    the attachment list. Asserted on all three surfaces the name can reach: the
    photo caption, the listed non-image, and the degraded name of an image whose
    bytes cannot be fetched (UAC P3).
    """
    from app.models.resources import Attachment

    token, row = _setup(db, "stock_inquiry")
    attachment_id = _seed_attachment(db, row, filename=filename, mime=mime)
    if unfetchable:
        storage["failing"].add(filename)
    _revise(
        db, token, "stock_inquiry", row,
        {"item_description": SECOND_DESCRIPTION}, FIRST_REASON, 0,
    )

    # Renamed after that version was submitted. The object never moves, so the
    # version's own bytes are still the ones the page embeds.
    renamed = f"renamed-today{filename[filename.rfind('.'):]}"
    att = db.query(Attachment).filter(Attachment.id == attachment_id).one()
    att.original_filename = renamed
    att.stored_filename = renamed
    db.commit()

    entries = _entries(db, "stock_inquiry", row)
    original = next(e for e in entries if e["version_no"] == 0)
    html = StockInquiryPDFService(db).build_html(str(row.id), revision_id=original["id"])

    assert filename in html
    assert renamed not in html
    if mime.startswith("image/") and not unfetchable:
        assert "data:image/jpeg;base64," in html


@pytest.mark.parametrize("kind", REQUEST_TYPES)
def test_request_revision_embeds_that_versions_own_photos(db, storage, kind):
    token, row = _setup(db, kind)
    from app.models.entity_attachment import EntityAttachmentLink
    from app.models.resources import Attachment

    att = Attachment(
        id=str(uuid.uuid4()),
        original_filename="layout.png",
        stored_filename="layout.png",
        file_path="uploads/layout.png",
        mime_type="image/png",
        file_size_bytes=99,
    )
    db.add(att)
    db.add(
        EntityAttachmentLink(
            id=str(uuid.uuid4()),
            # Sponsorship forms share the purchase_request attachment entity type.
            entity_type="purchase_request",
            entity_id=str(row.id),
            attachment_id=att.id,
        )
    )
    db.commit()
    _revise(db, token, kind, row, {"project_title": "Revised project"}, FIRST_REASON, 0)

    entries = _entries(db, kind, row)
    original = next(e for e in entries if e["version_no"] == 0)
    html = PurchaseRequestPDFService(db).build_html(
        str(row.id), revision_id=original["id"]
    )

    assert "data:image/png;base64," in html
    assert "layout.png" in html


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

    # The current form leads; the superseded version follows it. Revision 1 is the
    # version the current form shows, so it has no page of its own - its label and
    # reason ride on the current form instead.
    assert html.index("Revised project") < html.index("Marker project")
    assert html.count("Revised project") == 1
    assert "page-break-before: always" in html
    assert "Revision 1" in html
    assert FIRST_REASON in html
    assert html.index("Revision 1") < html.index("Marker project")
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
