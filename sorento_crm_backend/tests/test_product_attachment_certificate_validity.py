"""Certificate validity reaching the product-attachment listing.

The MCP render envelope was already written to read a nested ``certificate`` off
each product-attachment row - but the backend never emitted one, so every row
reported ``expired: false`` including a certificate that lapsed in 2016. These
tests pin the half that was missing.

What matters here:

  * a row whose file IS a filed certificate carries the derived window
  * a brochure / spec sheet carries ``certificate = None`` and is otherwise
    byte-identical to before
  * the state is DERIVED on read (valid / expiring_soon / expired), never a
    stored column and never dependent on a scheduler having run
  * a SUPERSEDED revision reports its OWN window, not the renewal's, and says so
  * one query per page, not one per row

Postgres only, isolated blank schema, ZZTPAV marker, nothing borrowed.
"""
from datetime import date, timedelta
from typing import Any

import pytest

from app.models.product import Product, ProductAttachment, ProductCategory, UnitOfMeasure
from app.models.resources import Attachment, AttachmentType
from app.services.certificate_query_service import certificate_validity_for_attachments
from app.services.certificate_service import (
    EXPIRING_SOON_DAYS,
    CertificateService,
    today_malaysia,
)
from app.services.product_service import ProductAttachmentService
from tests._pg_fixture import blank_session, unique_code

MARKER = "ZZTPAV"


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
    product = Product(
        product_code=unique_code(f"{MARKER}-P"),
        product_name=f"{MARKER} product",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=10,
    )
    db.add(product)
    db.flush()
    return {"cert_type": cert_type, "spec_type": spec_type, "product": product}


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


def _link(db, chain, attachment) -> Any:
    """The product<->attachment projection row the listing reads.

    Only for NON-certificate files: filing a certificate writes this projection
    itself (that is the register's whole contract with `product_attachments`),
    so calling this after `_file_certificate` trips `uq_product_attachment`.
    """
    row = ProductAttachment(
        product_id=chain["product"].id,
        attachment_id=attachment.id,
        access_levels=["dealer"],
    )
    db.add(row)
    db.flush()
    return row


def _projection(db, chain, attachment) -> Any:
    """The projection row the certificate service already wrote for this file."""
    return (
        db.query(ProductAttachment)
        .filter(
            ProductAttachment.product_id == chain["product"].id,
            ProductAttachment.attachment_id == attachment.id,
        )
        .one()
    )


def _file_certificate(db, chain, attachment, *, number: str, until: date, frm: date | None = None):
    service = CertificateService(db)
    cert = service.upsert_from_extraction(
        scheme=f"{MARKER}PPS",
        certificate_number=number,
        certifying_body=f"{MARKER} IKRAM",
        attachment_id=str(attachment.id),
        valid_from=frm or date(2020, 1, 1),
        valid_until=until,
        product_ids=[str(chain["product"].id)],
        commit=False,
    )
    db.flush()
    return cert


def _listing_row(db, chain):
    result = ProductAttachmentService(db).list_product_attachments(
        product_ids=[str(chain["product"].id)]
    )
    return result["data"]


# ------------------------------------------------------- the mapping itself
def test_certificate_attachment_maps_to_its_derived_window(db, chain):
    attachment = _attachment(db, chain, "cert")
    _file_certificate(db, chain, attachment, number="PAV-1", until=date(2029, 4, 5))

    found = certificate_validity_for_attachments(db, [str(attachment.id)])

    entry = found[str(attachment.id)]
    assert entry["certificate_number"] == "PAV-1"
    assert entry["valid_until"] == date(2029, 4, 5)
    assert entry["validity_state"] == "valid"
    assert entry["is_expired"] is False
    assert entry["is_current_revision"] is True


def test_a_non_certificate_attachment_is_simply_absent(db, chain):
    """Absent must be the answer for a brochure - not a row claiming `unknown`,
    which a consumer could read as "a certificate we could not date"."""
    spec = _attachment(db, chain, "spec", type_key="spec_type")

    assert certificate_validity_for_attachments(db, [str(spec.id)]) == {}


def test_empty_input_short_circuits_without_a_query(db):
    assert certificate_validity_for_attachments(db, []) == {}
    assert certificate_validity_for_attachments(db, [None]) == {}


def test_all_three_states_are_derived_from_today(db, chain):
    today = today_malaysia()
    cases = {
        "valid": today + timedelta(days=EXPIRING_SOON_DAYS + 30),
        "expiring_soon": today + timedelta(days=max(EXPIRING_SOON_DAYS - 1, 0)),
        "expired": today - timedelta(days=1),
    }
    ids = {}
    for i, (expected, until) in enumerate(cases.items()):
        attachment = _attachment(db, chain, f"state-{i}")
        _file_certificate(
            db, chain, attachment, number=f"PAV-STATE-{i}", until=until,
            frm=today - timedelta(days=365),
        )
        ids[expected] = str(attachment.id)

    found = certificate_validity_for_attachments(db, list(ids.values()))

    for expected, attachment_id in ids.items():
        assert found[attachment_id]["validity_state"] == expected, expected
    assert found[ids["expired"]]["is_expired"] is True
    # Expiring soon is NOT expired - the file is still the live certificate.
    assert found[ids["expiring_soon"]]["is_expired"] is False


def test_a_superseded_file_reports_its_own_window_not_the_renewals(db, chain):
    """A renewal does not retroactively make last year's PDF valid."""
    old = _attachment(db, chain, "rev1")
    _file_certificate(db, chain, old, number="PAV-RENEW", until=date(2021, 1, 1))
    new = _attachment(db, chain, "rev2")
    _file_certificate(db, chain, new, number="PAV-RENEW", until=date(2030, 1, 1))

    found = certificate_validity_for_attachments(db, [str(old.id), str(new.id)])

    assert found[str(old.id)]["valid_until"] == date(2021, 1, 1)
    assert found[str(old.id)]["validity_state"] == "expired"
    assert found[str(old.id)]["is_current_revision"] is False
    assert found[str(new.id)]["is_current_revision"] is True
    # Both point at the one identity, so a caller can find the renewal.
    assert found[str(old.id)]["certificate_id"] == found[str(new.id)]["certificate_id"]


def test_a_certificate_with_no_expiry_is_unknown_not_valid(db, chain):
    """A missing date is not "no expiry"; calling it valid would be a guess."""
    attachment = _attachment(db, chain, "nodate")
    _file_certificate(db, chain, attachment, number="PAV-NODATE", until=None)

    entry = certificate_validity_for_attachments(db, [str(attachment.id)])[str(attachment.id)]
    assert entry["validity_state"] == "unknown"
    assert entry["is_expired"] is False


# ------------------------------------------------ reaching the listing rows
def test_the_listing_stamps_certificate_on_a_cert_row(db, chain):
    attachment = _attachment(db, chain, "listed")
    _file_certificate(db, chain, attachment, number="PAV-LIST", until=date(2016, 6, 14))

    row = _listing_row(db, chain)[0]

    assert row.certificate is not None
    assert row.certificate["validity_state"] == "expired"
    assert row.certificate["is_expired"] is True
    assert row.certificate["certificate_number"] == "PAV-LIST"


def test_the_listing_leaves_a_non_cert_row_alone(db, chain):
    """The attribute is always set so the response never has to guess, but it is
    None - brochures and spec sheets read exactly as they did before."""
    spec = _attachment(db, chain, "brochure", type_key="spec_type")
    _link(db, chain, spec)

    row = _listing_row(db, chain)[0]

    assert row.certificate is None


def test_a_mixed_page_resolves_each_row_independently(db, chain):
    cert_file = _attachment(db, chain, "mixed-cert")
    _file_certificate(db, chain, cert_file, number="PAV-MIX", until=date(2030, 1, 1))
    _link(db, chain, _attachment(db, chain, "mixed-spec", type_key="spec_type"))

    by_file = {r.attachment.original_filename: r.certificate for r in _listing_row(db, chain)}

    assert by_file[f"{MARKER}-mixed-cert.pdf"]["validity_state"] == "valid"
    assert by_file[f"{MARKER}-mixed-spec.pdf"] is None


def test_single_get_also_carries_the_certificate(db, chain):
    attachment = _attachment(db, chain, "single")
    _file_certificate(db, chain, attachment, number="PAV-ONE", until=date(2030, 1, 1))
    link = _projection(db, chain, attachment)

    fetched = ProductAttachmentService(db).get_product_attachment(str(link.id))

    assert fetched.certificate["certificate_number"] == "PAV-ONE"


def test_by_product_listing_also_carries_the_certificate(db, chain):
    attachment = _attachment(db, chain, "byproduct")
    _file_certificate(db, chain, attachment, number="PAV-BP", until=date(2030, 1, 1))

    rows = ProductAttachmentService(db).get_product_attachments_by_product(
        str(chain["product"].id)
    )

    assert rows[0].certificate["certificate_number"] == "PAV-BP"


def test_the_lookup_costs_one_query_per_page_not_one_per_row(db, chain):
    """N+1 here would be paid on every brochure listing in the system."""
    for i in range(5):
        attachment = _attachment(db, chain, f"n1-{i}")
        _file_certificate(db, chain, attachment, number=f"PAV-N1-{i}", until=date(2030, 1, 1))

    statements: list[str] = []
    from sqlalchemy import event

    def record(conn, cursor, statement, params, context, executemany):
        if "certificate_revisions" in statement.lower():
            statements.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", record)
    try:
        rows = _listing_row(db, chain)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", record)

    assert len(rows) == 5
    assert len(statements) == 1, statements
