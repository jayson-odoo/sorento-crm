"""A hand-made product<->certificate link must survive the next reconcile.

``product_attachments`` rows for a cert-bearing attachment are a PROJECTION of
``certificate_products`` x the current revision, and ``reconcile_certificate``
hard-deletes every row the coverage does not name. A link made by hand wrote
only the projection row - so the next external re-submit, or any coverage edit,
silently destroyed it.

The fix routes the manual surfaces through coverage:

  * linking a product to a cert file authors coverage (source ``manual``), and
    the projection row it produces survives a reconcile
  * unlinking removes coverage, so the row is not resurrected by the next one
  * a SUPERSEDED revision's file is refused outright - a row on it can never
    survive (the stale sweep removes it whatever coverage says)
  * an ordinary attachment is untouched: no coverage, no certificate, no change

Postgres only, isolated blank schema, ZZTMLS marker, nothing borrowed.
"""
from datetime import date
from typing import Any

import pytest
from app.services.error_handler import AppException

from app.models.certificate import CertificateProduct
from app.models.product import Product, ProductAttachment, ProductCategory, UnitOfMeasure
from app.models.resources import Attachment, AttachmentType
from app.schemas.product import ProductAttachmentCreate
from app.services.certificate_service import CertificateService
from tests._pg_fixture import blank_session, unique_code

MARKER = "ZZTMLS"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def chain(db) -> dict[str, Any]:
    cert_type = AttachmentType(
        type_name=f"{MARKER} Certification",
        allowed_extensions="pdf",
        max_file_size_mb=10,
        is_certificate=True,
    )
    spec_type = AttachmentType(
        type_name=f"{MARKER} Technical Specifications",
        allowed_extensions="pdf",
        max_file_size_mb=10,
    )
    category = ProductCategory(
        category_code=unique_code(MARKER), category_name=f"{MARKER} category"
    )
    uom = UnitOfMeasure(uom_code=unique_code(MARKER), uom_name=f"{MARKER} unit")
    db.add_all([cert_type, spec_type, category, uom])
    db.flush()
    covered = Product(
        product_code=unique_code(f"{MARKER}-A"),
        product_name=f"{MARKER} covered product",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=10,
    )
    manual = Product(
        product_code=unique_code(f"{MARKER}-B"),
        product_name=f"{MARKER} hand-linked product",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=10,
    )
    db.add_all([covered, manual])
    db.flush()
    return {
        "cert_type": cert_type,
        "spec_type": spec_type,
        "covered": covered,
        "manual": manual,
    }


def _attachment(db, chain, name: str, *, type_key: str = "cert_type") -> Any:
    attachment = Attachment(
        attachment_type_id=chain[type_key].id,
        original_filename=f"{MARKER}-{name}.pdf",
        stored_filename=f"{MARKER}-{name}.pdf",
        file_path=f"https://cdn.example/{MARKER}/{name}.pdf",
        access_levels=["dealer"],
    )
    db.add(attachment)
    db.flush()
    return attachment


def _file_certificate(db, chain, attachment, *, number: str, until: date = date(2030, 1, 1)):
    cert = CertificateService(db).upsert_from_extraction(
        scheme=f"{MARKER}PPS",
        certificate_number=number,
        certifying_body=f"{MARKER} IKRAM",
        attachment_id=str(attachment.id),
        valid_from=date(2020, 1, 1),
        valid_until=until,
        product_ids=[str(chain["covered"].id)],
        commit=False,
    )
    db.flush()
    return cert


def _linked_product_ids(db, attachment) -> set[str]:
    return {
        str(row.product_id)
        for row in db.query(ProductAttachment).filter(
            ProductAttachment.attachment_id == attachment.id
        )
    }


def _manual_link(db, chain, attachment, product):
    from app.services.product_service import ProductAttachmentService

    return ProductAttachmentService(db).create_product_attachment(
        ProductAttachmentCreate(
            product_id=str(product.id),
            attachment_id=str(attachment.id),
            access_levels=["dealer"],
        )
    )


def test_manual_link_to_certificate_file_authors_coverage(db, chain):
    attachment = _attachment(db, chain, "cert")
    cert = _file_certificate(db, chain, attachment, number=f"{MARKER}-001")

    _manual_link(db, chain, attachment, chain["manual"])
    db.flush()

    coverage = {
        str(row.product_id): row.source
        for row in db.query(CertificateProduct).filter(
            CertificateProduct.certificate_id == cert.id
        )
    }
    assert coverage.get(str(chain["manual"].id)) == "manual"
    assert coverage.get(str(chain["covered"].id)) == "ai"


def test_manual_link_survives_a_later_reconcile(db, chain):
    attachment = _attachment(db, chain, "cert")
    cert = _file_certificate(db, chain, attachment, number=f"{MARKER}-002")

    _manual_link(db, chain, attachment, chain["manual"])
    db.flush()

    # What the external re-submit does at the end of every call.
    CertificateService(db).reconcile_certificate(cert)
    db.flush()

    assert _linked_product_ids(db, attachment) == {
        str(chain["covered"].id),
        str(chain["manual"].id),
    }


def test_manual_unlink_removes_coverage_so_reconcile_does_not_resurrect(db, chain):
    from app.services.product_service import ProductAttachmentService

    attachment = _attachment(db, chain, "cert")
    cert = _file_certificate(db, chain, attachment, number=f"{MARKER}-003")
    row = _manual_link(db, chain, attachment, chain["manual"])
    db.flush()

    ProductAttachmentService(db).delete_product_attachment(str(row.id))
    db.flush()
    CertificateService(db).reconcile_certificate(cert)
    db.flush()

    assert _linked_product_ids(db, attachment) == {str(chain["covered"].id)}
    assert (
        db.query(CertificateProduct)
        .filter(
            CertificateProduct.certificate_id == cert.id,
            CertificateProduct.product_id == chain["manual"].id,
        )
        .count()
        == 0
    )


def test_manual_link_to_a_superseded_revision_is_refused(db, chain):
    first = _attachment(db, chain, "cert-rev1")
    renewal = _attachment(db, chain, "cert-rev2")
    _file_certificate(db, chain, first, number=f"{MARKER}-004", until=date(2030, 1, 1))
    # A real renewal: a NEW validity window, so a second revision is appended and
    # the first is superseded rather than swapped in place.
    _file_certificate(db, chain, renewal, number=f"{MARKER}-004", until=date(2033, 1, 1))
    db.flush()

    with pytest.raises(AppException) as excinfo:
        _manual_link(db, chain, first, chain["manual"])
    assert excinfo.value.status_code == 400
    assert "superseded" in str(excinfo.value.detail).lower()


def test_ordinary_attachment_link_is_unchanged(db, chain):
    attachment = _attachment(db, chain, "spec", type_key="spec_type")

    row = _manual_link(db, chain, attachment, chain["manual"])
    db.flush()

    assert str(row.product_id) == str(chain["manual"].id)
    assert _linked_product_ids(db, attachment) == {str(chain["manual"].id)}
    assert db.query(CertificateProduct).count() == 0
