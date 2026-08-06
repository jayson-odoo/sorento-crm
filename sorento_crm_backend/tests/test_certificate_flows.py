"""The flows an operator actually drives: resubmit, replace, copy, delete.

These are the paths between the CRM and n8n that are easy to get wrong and
impossible to see from a single happy-path test:

  * resubmit the SAME file with the SAME reading  -> must NOT stack a duplicate
    revision (n8n retries, and a human can re-send an attachment at any time)
  * re-upload as REPLACE or COPY, same validity   -> same document, so the
    current revision is updated and re-pointed, not duplicated
  * a genuinely later expiry                      -> a NEW revision (renewal)
  * deleting the ATTACHMENT                       -> the certificate survives
  * deleting the CERTIFICATE                      -> the file survives

The revision key is the VALIDITY WINDOW (issued_at, valid_from, valid_until).
A revision represents an issued document, and an issued document is defined by
the window it is valid for - not by which upload row happens to carry the PDF.

Postgres only, isolated blank schema, ZZTFLOW marker, nothing borrowed.
"""
from datetime import date
from typing import Any

import pytest

from app.models.certificate import CertificateRevision
from app.models.product import Product, ProductAttachment, ProductCategory, UnitOfMeasure
from app.models.resources import Attachment, AttachmentType
from app.services.certificate_service import CertificateService
from tests._pg_fixture import blank_session, unique_code

MARKER = "ZZTFLOW"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def chain(db) -> dict[str, Any]:
    attachment_type = AttachmentType(
        type_name=f"{MARKER} Certification",
        allowed_extensions="pdf",
        max_file_size_mb=10,
        is_certificate=True,
    )
    category = ProductCategory(
        category_code=unique_code(MARKER), category_name=f"{MARKER} category"
    )
    uom = UnitOfMeasure(uom_code=unique_code(MARKER), uom_name=f"{MARKER} unit")
    db.add_all([attachment_type, category, uom])
    db.flush()
    product = Product(
        product_code=unique_code(f"{MARKER}-P"),
        product_name=f"{MARKER} product",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=10,
    )
    db.add(product)
    db.flush()
    return {"attachment_type": attachment_type, "product": product}


def _attachment(db, chain, name: str) -> Any:
    attachment = Attachment(
        attachment_type_id=chain["attachment_type"].id,
        original_filename=f"{MARKER}-{name}.pdf",
        stored_filename=f"{MARKER}-{name}.pdf",
        file_path=f"https://cdn.example/{MARKER}/{name}.pdf",
        access_levels=["dealer"],
    )
    db.add(attachment)
    db.flush()
    return attachment


def _submit(service, chain, attachment, *, number="FLOW-1", until=date(2026, 12, 31), **over):
    """One n8n post: the reader's payload for this attachment."""
    payload = dict(
        scheme=f"{MARKER}PPS",
        certificate_number=number,
        certifying_body=f"{MARKER} IKRAM",
        attachment_id=str(attachment.id),
        valid_from=date(2026, 1, 1),
        valid_until=until,
        product_ids=[str(chain["product"].id)],
        commit=False,
    )
    payload.update(over)
    return service.upsert_from_extraction(**payload)


def _revisions(service, cert) -> list[Any]:
    return service.get_revisions(cert.id)


# ------------------------------------------------------------------ resubmit
def test_resubmitting_the_same_payload_does_not_stack_a_revision(db, chain):
    """n8n retries, and a person can re-send an attachment. The same document
    read the same way is the same revision, not a new one."""
    service = CertificateService(db)
    attachment = _attachment(db, chain, "v1")

    _submit(service, chain, attachment)
    _submit(service, chain, attachment)
    db.flush()

    cert = service.find_by_identity(f"{MARKER}PPS", "FLOW-1")
    revisions = _revisions(service, cert)
    assert len(revisions) == 1
    assert revisions[0].revision_no == 1
    assert revisions[0].is_current is True
    # Coverage is derived once, on create, and never re-derived by a resubmit.
    assert service.count_coverage(cert.id) == 1


def test_resubmitting_refreshes_the_reading_in_place(db, chain):
    """An update, not a no-op: a re-read that corrects the unmatched list or the
    review flags must land on the current revision."""
    service = CertificateService(db)
    attachment = _attachment(db, chain, "v1")

    _submit(service, chain, attachment, unmatched_products=["NOPE-1"])
    db.flush()
    cert = service.find_by_identity(f"{MARKER}PPS", "FLOW-1")
    assert list(service.get_current_revision(cert).unmatched_products) == ["NOPE-1"]

    # Second pass: the reader got it right this time.
    _submit(service, chain, attachment, unmatched_products=[])
    db.flush()
    revisions = _revisions(service, cert)
    assert len(revisions) == 1
    assert list(revisions[0].unmatched_products) == []


# ------------------------------------------------------- replace / make a copy
def test_replacing_the_file_repoints_the_same_revision(db, chain):
    """"Replace" gives a NEW attachment id for the SAME document. The validity
    window is unchanged, so it is the same revision pointing at the new file."""
    service = CertificateService(db)
    first = _attachment(db, chain, "v1")
    replacement = _attachment(db, chain, "v1-replaced")

    _submit(service, chain, first)
    db.flush()
    _submit(service, chain, replacement)
    db.flush()

    cert = service.find_by_identity(f"{MARKER}PPS", "FLOW-1")
    revisions = _revisions(service, cert)
    assert len(revisions) == 1
    assert str(revisions[0].attachment_id) == str(replacement.id)

    # The projection follows: the old file serves nothing, the new one serves.
    assert _projection_count(db, first.id) == 0
    assert _projection_count(db, replacement.id) == 1


def test_uploading_a_copy_with_the_same_validity_is_not_a_renewal(db, chain):
    """"Make a copy" is the same document under a new upload row. Treating it as
    a renewal would invent a revision history that never happened."""
    service = CertificateService(db)
    original = _attachment(db, chain, "v1")
    copy = _attachment(db, chain, "v1-copy")

    _submit(service, chain, original)
    db.flush()
    _submit(service, chain, copy)
    db.flush()

    cert = service.find_by_identity(f"{MARKER}PPS", "FLOW-1")
    assert len(_revisions(service, cert)) == 1


# ------------------------------------------------------------------- renewal
def test_a_later_expiry_appends_a_revision_and_keeps_coverage(db, chain):
    """The real renewal: same scheme + number, a NEW window. Coverage is hung
    off the identity, so it must survive untouched."""
    service = CertificateService(db)
    first = _attachment(db, chain, "v1")
    renewal = _attachment(db, chain, "v2")

    _submit(service, chain, first, until=date(2026, 12, 31))
    db.flush()
    cert = service.find_by_identity(f"{MARKER}PPS", "FLOW-1")
    coverage_before = service.count_coverage(cert.id)

    _submit(service, chain, renewal, until=date(2029, 12, 31))
    db.flush()

    revisions = sorted(_revisions(service, cert), key=lambda r: r.revision_no)
    assert [r.revision_no for r in revisions] == [1, 2]
    assert revisions[0].is_current is False
    assert revisions[1].is_current is True
    assert revisions[1].valid_until == date(2029, 12, 31)
    assert service.count_coverage(cert.id) == coverage_before
    # Superseded file stops serving; the current one serves.
    assert _projection_count(db, first.id) == 0
    assert _projection_count(db, renewal.id) == 1


def test_a_corrected_expiry_on_the_same_file_is_not_a_renewal(db, chain):
    """Same attachment, different date: the reader changed its mind about ONE
    document. That is a correction to the current revision, not a new issue."""
    service = CertificateService(db)
    attachment = _attachment(db, chain, "v1")

    _submit(service, chain, attachment, until=date(2026, 12, 31))
    db.flush()
    _submit(service, chain, attachment, until=date(2027, 6, 30))
    db.flush()

    cert = service.find_by_identity(f"{MARKER}PPS", "FLOW-1")
    revisions = _revisions(service, cert)
    assert len(revisions) == 1
    assert revisions[0].valid_until == date(2027, 6, 30)


# ------------------------------------------------------------------ deletion
def test_deleting_the_attachment_does_not_delete_the_certificate(db, chain):
    """Trashing the file must leave the register intact - the certificate is the
    record of the approval, not of the upload."""
    service = CertificateService(db)
    attachment = _attachment(db, chain, "v1")
    _submit(service, chain, attachment)
    db.flush()
    cert = service.find_by_identity(f"{MARKER}PPS", "FLOW-1")
    cert_id = str(cert.id)

    # Soft delete, which is what the attachment UI does.
    attachment.is_deleted = True
    db.flush()
    assert service.get_certificate(cert_id) is not None
    assert len(_revisions(service, service.get_certificate(cert_id))) == 1

    # And a hard delete of the row must not cascade into the register either.
    db.query(ProductAttachment).filter(
        ProductAttachment.attachment_id == str(attachment.id)
    ).delete(synchronize_session=False)
    db.query(CertificateRevision).filter(
        CertificateRevision.attachment_id == str(attachment.id)
    ).update({"attachment_id": None}, synchronize_session="fetch")
    db.delete(attachment)
    db.flush()
    survivor = service.get_certificate(cert_id)
    assert survivor is not None
    assert len(_revisions(service, survivor)) == 1


def test_deleting_the_certificate_keeps_the_uploaded_file(db, chain):
    """COV-5, the other direction: the register owns the metadata, never bytes."""
    service = CertificateService(db)
    attachment = _attachment(db, chain, "v1")
    _submit(service, chain, attachment)
    db.flush()
    cert = service.find_by_identity(f"{MARKER}PPS", "FLOW-1")

    service.delete_certificate(str(cert.id), commit=False)
    db.flush()

    assert (
        db.query(Attachment).filter(Attachment.id == str(attachment.id)).first()
        is not None
    )


def _projection_count(db, attachment_id) -> int:
    return (
        db.query(ProductAttachment)
        .filter(ProductAttachment.attachment_id == str(attachment_id))
        .count()
    )
