"""R2-1 BRAND-SCOPE-ATTACH (CHAT-CLOSED-LISTS-L security blocker, 18 Oct; synthetic codes).

`ProductAttachmentService.list_product_attachments` filtered by certificate_ids / attachment_type_ids alone
returned every brand's rows: the brand rule sits on Product and reached ProductAttachment only
through the joinedload LEFT JOIN, so out-of-brand rows came back with product null and the file
was still attached. A brand-scoped session lists only in-brand products' rows; an unscoped
session is unchanged. Not gated (a scope fix).
"""
from __future__ import annotations

import uuid

from app.models.base import set_brand_scope
from app.models.certificate import Certificate, CertificateRevision
from app.models.product import ProductAttachment
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.product_service import ProductAttachmentService
from tests._brand_scope_seed import db, world  # noqa: F401  (fixtures by name)
from tests._mc_lookup_seed import attachment, attachment_type
from tests._pg_fixture import unique_code


def _certificate_on_every_product(db, world) -> str:
    """One current certificate whose file is linked to the MOCHA, SORENTO and unbranded products."""
    kind = attachment_type(db, name="ZZT Certification")
    kind.is_certificate = True
    att = attachment(db, type_id=kind.id, filename=unique_code("cert") + ".pdf")
    cert = Certificate(
        id=str(uuid.uuid4()), attachment_type_id=kind.id, scheme="ZZSPAN", certificate_number=uuid.uuid4().hex[:10],
        status="active", company_id=DEFAULT_COMPANY_ID,
    )
    db.add(cert)
    db.flush()
    db.add(CertificateRevision(id=str(uuid.uuid4()), certificate_id=cert.id, revision_no=1, attachment_id=att.id, is_current=True))
    for prod in world.products:
        db.add(ProductAttachment(id=str(uuid.uuid4()), product_id=prod.id, attachment_id=att.id, company_id=DEFAULT_COMPANY_ID))
    db.flush()
    return cert.id


def _listed_codes(db, **filters) -> set[str]:
    payload = ProductAttachmentService(db).list_product_attachments(limit=50, **filters)
    return {str(row.product_id) for row in payload["data"]}


def test_a_brand_scoped_certificate_listing_returns_only_in_brand_rows(db, world) -> None:
    cert_id = _certificate_on_every_product(db, world)
    set_brand_scope(db, frozenset({world.mocha.id}))

    assert _listed_codes(db, certificate_ids=[cert_id]) == {str(world.p_mocha.id)}


def test_a_brand_scoped_attachment_type_listing_returns_only_in_brand_rows(db, world) -> None:
    type_id = world.stock_list.attachment_type_id
    set_brand_scope(db, frozenset({world.mocha.id}))

    assert _listed_codes(db, attachment_type_ids=[str(type_id)]) == {str(world.p_mocha.id)}


def test_guard_an_unscoped_session_lists_every_brand(db, world) -> None:
    cert_id = _certificate_on_every_product(db, world)

    assert _listed_codes(db, certificate_ids=[cert_id]) == {str(p.id) for p in world.products}
    assert _listed_codes(db, attachment_type_ids=[str(world.stock_list.attachment_type_id)]) == {str(p.id) for p in world.products}
