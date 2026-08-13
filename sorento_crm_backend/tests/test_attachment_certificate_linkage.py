"""The certificate side of an attachment's Linkages.

`get_linked_entities` is what fills the Linkages tabs on the attachment detail /
modal and the linked-entity list in the upload-activity drawer. Certificates
were missing from it, so a certification PDF opened from Resource Management
gave no way back to the register row it created - and the upload drawer called
it unlinked.

This linkage is not like the other four. Products, promotions, forms and packing
lists are join rows a user maintains; a certificate revision IS the document, so
the link exists because the file was filed. The tests below pin the parts of
that distinction a refactor could quietly break: the shape must still be a
`LinkedEntityRef` (so the shared table renders it), it must say WHICH revision
the file is, and a non-certificate file must come back with an empty list rather
than anything that reads as "unknown certificate".

Postgres only, isolated blank schema, ZZTACL marker, nothing borrowed.
"""
from datetime import date
from typing import Any

import pytest

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.resources import Attachment, AttachmentType
from app.services.certificate_service import CertificateService
from app.services.resources_service import AttachmentService
from tests._pg_fixture import blank_session, unique_code

MARKER = "ZZTACL"


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
    other_type = AttachmentType(
        type_name=f"{MARKER} Brochure",
        allowed_extensions="pdf",
        max_file_size_mb=10,
    )
    category = ProductCategory(
        category_code=unique_code(MARKER), category_name=f"{MARKER} category"
    )
    uom = UnitOfMeasure(uom_code=unique_code(MARKER), uom_name=f"{MARKER} unit")
    db.add_all([cert_type, other_type, category, uom])
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
    return {"cert_type": cert_type, "other_type": other_type, "product": product}


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


def _file_certificate(db, chain, attachment, *, number: str, until: date, **over):
    payload = dict(
        scheme=f"{MARKER}PPS",
        certificate_number=number,
        certifying_body=f"{MARKER} IKRAM",
        attachment_id=str(attachment.id),
        valid_from=date(2020, 1, 1),
        valid_until=until,
        product_ids=[str(chain["product"].id)],
        commit=False,
    )
    payload.update(over)
    cert = CertificateService(db).upsert_from_extraction(**payload)
    db.flush()
    return cert


def _linked(db, attachment) -> list[dict]:
    return AttachmentService(db).get_linked_entities(str(attachment.id))["linked_certificates"]


def test_a_filed_certificate_appears_in_the_attachments_linkages(db, chain):
    attachment = _attachment(db, chain, "cert")
    cert = _file_certificate(db, chain, attachment, number="ACL-1", until=date(2030, 1, 1))

    linked = _linked(db, attachment)

    assert len(linked) == 1
    # `id` must be the CERTIFICATE, not the revision: the shared Linkages table
    # builds its View href as `<route>/<id>`, and the route is the register's
    # detail page.
    assert linked[0]["id"] == str(cert.id)
    assert linked[0]["name"] == f"{MARKER}PPS ACL-1"


def test_the_row_says_which_revision_the_file_is(db, chain):
    """Read from the attachment side, a superseded PDF looks exactly like the
    live one unless the row says otherwise."""
    old = _attachment(db, chain, "rev1")
    _file_certificate(db, chain, old, number="ACL-REV", until=date(2021, 1, 1))
    new = _attachment(db, chain, "rev2")
    _file_certificate(db, chain, new, number="ACL-REV", until=date(2030, 1, 1))

    assert "superseded" in (_linked(db, old)[0]["description"] or "")
    assert "superseded" not in (_linked(db, new)[0]["description"] or "")
    assert "Revision 2" in (_linked(db, new)[0]["description"] or "")


def test_a_non_certificate_file_has_an_empty_certificate_list(db, chain):
    brochure = _attachment(db, chain, "brochure", type_key="other_type")

    assert _linked(db, brochure) == []


def test_the_other_four_linkage_groups_are_untouched(db, chain):
    """The certificate group is additive - nothing else may shift."""
    attachment = _attachment(db, chain, "keys")
    _file_certificate(db, chain, attachment, number="ACL-KEYS", until=date(2030, 1, 1))

    linked = AttachmentService(db).get_linked_entities(str(attachment.id))

    assert set(linked) == {
        "linked_products",
        "linked_promotions",
        "linked_form",
        "linked_packing_lists",
        "linked_certificates",
    }
    # Filing the certificate wrote the product projection, so the product group
    # is populated by the same act - and still separately.
    assert len(linked["linked_products"]) == 1


def test_one_file_under_two_schemes_yields_two_rows(db, chain):
    """PPS/04124FC and SPAN/04124FC are two identities. A single PDF filed under
    both must not collapse to one linkage row."""
    attachment = _attachment(db, chain, "dual")
    _file_certificate(db, chain, attachment, number="ACL-DUAL", until=date(2030, 1, 1))
    _file_certificate(
        db, chain, attachment, number="ACL-DUAL", until=date(2030, 1, 1),
        scheme=f"{MARKER}SPAN",
    )

    linked = _linked(db, attachment)

    assert len(linked) == 2
    assert {row["name"] for row in linked} == {
        f"{MARKER}PPS ACL-DUAL",
        f"{MARKER}SPAN ACL-DUAL",
    }


def test_the_serialized_row_matches_the_shared_linked_entity_shape(db, chain):
    """The API serializes every group through LinkedEntityRef; a missing key
    would 500 the whole attachment-metadata response, not just this tab."""
    from app.schemas.resources import LinkedEntityRef

    attachment = _attachment(db, chain, "shape")
    _file_certificate(db, chain, attachment, number="ACL-SHAPE", until=date(2030, 1, 1))

    ref = LinkedEntityRef.model_validate(_linked(db, attachment)[0])

    assert ref.id and ref.name
    assert ref.link_id  # the revision id
