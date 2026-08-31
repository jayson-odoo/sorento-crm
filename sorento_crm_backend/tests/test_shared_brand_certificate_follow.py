"""AC-H1..H7 (PLAN-shared-brand-attachments.md S6, UAC group H): a certificate
follows its filed attachment's company.

- H1/H2: `bulk-company` on a filed certificate revision moves
  `certificate.company_id`, rewrites `certificate_products` coverage with the
  same expand/shrink rule the twin linker uses, and re-projects
  `product_attachments` (`AttachmentCompanyService._apply_certificate_follow`).
- H3: a shared certificate (`__company_shared__`) is visible under EVERY
  company scope, not duplicated.
- H4: the rebuilt `uq_certificates_company_scheme_number` index rejects a
  second NULL-company certificate with the same identity.
- H5: `upsert_from_extraction` takes the FILING ATTACHMENT's company, not the
  session's write scope.
- H6: the expiry-sweep trigger returns ONE match for a shared certificate,
  never one per company.
- H7: alembic hygiene for migration 449.

Postgres only, own seeded `ZZT-` chain (`blank_session`, ZZT- codes).
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.base import company_scope, set_company_scope
from app.models.certificate import (
    CERTIFICATE_STATUS_ACTIVE,
    Certificate,
    CertificateProduct,
    CertificateRevision,
)
from app.models.company import Company, UserCompany
from app.models.product import Product, ProductAttachment, ProductCategory, UnitOfMeasure
from app.models.resources import Attachment, AttachmentType
from app.models.user import User
from app.services.attachment_company_service import AttachmentCompanyService
from app.services.certificate_service import CertificateService
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners

from tests._pg_fixture import blank_session, unique_code

MOCHA_ID = "00000000-0000-0000-0000-000000000002"


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


@pytest.fixture
def db():
    with blank_session() as session:
        session.add(Company(id=MOCHA_ID, name="Mocha", code=unique_code("MCH")[:20]))
        session.flush()
        yield session


def _user_with_grants(db, company_ids: list[str]) -> str:
    user = User(id=str(uuid.uuid4()), email=f"{unique_code('user')}@test.local", name="ZZT Grantee")
    db.add(user)
    db.flush()
    for cid in company_ids:
        db.add(UserCompany(id=str(uuid.uuid4()), user_id=user.id, company_id=cid))
    db.flush()
    return user.id


def _type(db, *, is_certificate=True) -> str:
    row = AttachmentType(
        id=str(uuid.uuid4()), type_name=unique_code("ZZT-Cert")[:50],
        allowed_extensions="pdf", is_certificate=is_certificate,
    )
    db.add(row)
    db.flush()
    return row.id


def _twin_products(db, code: str) -> tuple[Product, Product]:
    cat_s = ProductCategory(id=str(uuid.uuid4()), category_code=unique_code("CAT")[:50], category_name="ZZT cat", company_id=DEFAULT_COMPANY_ID)
    cat_m = ProductCategory(id=str(uuid.uuid4()), category_code=unique_code("CAT")[:50], category_name="ZZT cat", company_id=MOCHA_ID)
    uom_s = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each", company_id=DEFAULT_COMPANY_ID)
    uom_m = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each", company_id=MOCHA_ID)
    db.add_all([cat_s, cat_m, uom_s, uom_m])
    db.flush()
    p_s = Product(id=str(uuid.uuid4()), product_code=code, product_name=code, category_id=cat_s.id, base_uom_id=uom_s.id, list_price=1, company_id=DEFAULT_COMPANY_ID)
    p_m = Product(id=str(uuid.uuid4()), product_code=code, product_name=code, category_id=cat_m.id, base_uom_id=uom_m.id, list_price=1, company_id=MOCHA_ID)
    db.add_all([p_s, p_m])
    db.flush()
    return p_s, p_m


def _attachment(db, *, company_id, type_id: str) -> Attachment:
    row = Attachment(
        id=str(uuid.uuid4()),
        original_filename=f"{unique_code('ZZT-cert')}.pdf",
        stored_filename=f"{unique_code('ZZT-cert')}.pdf",
        file_path="https://cdn.test/zzt-cert.pdf",
        attachment_type_id=type_id,
        is_deleted=False,
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def _filed_certificate(db, *, company_id, attachment: Attachment, type_id: str, covers: Product) -> Certificate:
    """A certificate whose CURRENT revision is ``attachment``, covering one product."""
    cert = Certificate(
        id=str(uuid.uuid4()), attachment_type_id=type_id,
        scheme=unique_code("SCHEME")[:60], certificate_number=unique_code("CERT")[:120],
        status=CERTIFICATE_STATUS_ACTIVE, company_id=company_id,
    )
    db.add(cert)
    db.flush()
    revision = CertificateRevision(
        id=str(uuid.uuid4()), certificate_id=cert.id, attachment_id=attachment.id,
        revision_no=1, is_current=True, valid_until=date(2030, 1, 1),
    )
    db.add(revision)
    db.flush()
    cert.current_revision_id = revision.id
    db.add(CertificateProduct(id=str(uuid.uuid4()), certificate_id=cert.id, product_id=covers.id))
    db.flush()
    return cert


# --- AC-H1: share expands coverage + projection --------------------------------


def test_h1_sharing_a_filed_certificate_widens_coverage_and_projection(db):
    type_id = _type(db)
    p_s, p_m = _twin_products(db, unique_code("SRTBV"))
    att = _attachment(db, company_id=DEFAULT_COMPANY_ID, type_id=type_id)
    cert = _filed_certificate(db, company_id=DEFAULT_COMPANY_ID, attachment=att, type_id=type_id, covers=p_s)
    user_id = _user_with_grants(db, [DEFAULT_COMPANY_ID, MOCHA_ID])
    db.commit()

    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    result = AttachmentCompanyService(db).apply(
        attachment_ids=[att.id], company_id=None, actor_id=user_id,
    )

    assert result["certificates_updated"] == 1

    with company_scope(db, None):
        db.refresh(cert)
        assert cert.company_id is None

        coverage_ids = {
            str(r.product_id)
            for r in db.query(CertificateProduct).filter(CertificateProduct.certificate_id == cert.id)
        }
        assert coverage_ids == {p_s.id, p_m.id}

        projection = {
            str(r.product_id): str(r.company_id)
            for r in db.query(ProductAttachment).filter(ProductAttachment.attachment_id == att.id)
        }
        assert projection == {p_s.id: DEFAULT_COMPANY_ID, p_m.id: MOCHA_ID}, (
            "each projected row must be stamped from its OWN product's company, "
            "not left to auto-stamp into the incumbent company"
        )


# --- AC-H2: moving back to one company shrinks coverage + projection -----------


def test_h2_moving_a_shared_certificate_back_to_one_company_shrinks(db):
    type_id = _type(db)
    p_s, p_m = _twin_products(db, unique_code("SRTBV"))
    att = _attachment(db, company_id=None, type_id=type_id)
    cert = _filed_certificate(db, company_id=None, attachment=att, type_id=type_id, covers=p_s)
    # Coverage already spans both twins, as AC-H1 would have left it.
    db.add(CertificateProduct(id=str(uuid.uuid4()), certificate_id=cert.id, product_id=p_m.id))
    db.add(ProductAttachment(id=str(uuid.uuid4()), product_id=p_m.id, attachment_id=att.id, company_id=MOCHA_ID))
    db.flush()
    user_id = _user_with_grants(db, [DEFAULT_COMPANY_ID, MOCHA_ID])
    db.commit()

    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))
    result = AttachmentCompanyService(db).apply(
        attachment_ids=[att.id], company_id=DEFAULT_COMPANY_ID, actor_id=user_id,
    )

    assert result["certificates_updated"] == 1
    with company_scope(db, None):
        db.refresh(cert)
        assert cert.company_id == DEFAULT_COMPANY_ID

        coverage_ids = {
            str(r.product_id)
            for r in db.query(CertificateProduct).filter(CertificateProduct.certificate_id == cert.id)
        }
        assert coverage_ids == {p_s.id}

        projection_ids = {
            str(r.product_id)
            for r in db.query(ProductAttachment).filter(ProductAttachment.attachment_id == att.id)
        }
        assert projection_ids == {p_s.id}


# --- AC-H3: a shared certificate is visible under every company scope ----------


def test_h3_shared_certificate_visible_under_both_company_scopes(db):
    type_id = _type(db)
    att = _attachment(db, company_id=None, type_id=type_id)
    p_s, _p_m = _twin_products(db, unique_code("SRTBV"))
    cert = _filed_certificate(db, company_id=None, attachment=att, type_id=type_id, covers=p_s)
    db.commit()

    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    seen_under_s = db.query(Certificate).filter(Certificate.id == cert.id).first()
    assert seen_under_s is not None

    set_company_scope(db, frozenset({MOCHA_ID}))
    seen_under_m = db.query(Certificate).filter(Certificate.id == cert.id).first()
    assert seen_under_m is not None

    # Once, not duplicated - a plain unscoped count is still 1 row.
    with company_scope(db, None):
        assert db.query(Certificate).filter(Certificate.id == cert.id).count() == 1


# --- AC-H4: the rebuilt identity index rejects a second shared duplicate -------


def test_h4_two_null_company_certificates_same_identity_rejected(db):
    type_id = _type(db)
    scheme = unique_code("SCHEME")[:60]
    number = unique_code("CERT")[:120]
    db.add(Certificate(
        id=str(uuid.uuid4()), attachment_type_id=type_id, scheme=scheme,
        certificate_number=number, status=CERTIFICATE_STATUS_ACTIVE, company_id=None,
    ))
    db.flush()

    db.add(Certificate(
        id=str(uuid.uuid4()), attachment_type_id=type_id, scheme=scheme,
        certificate_number=number, status=CERTIFICATE_STATUS_ACTIVE, company_id=None,
    ))
    with pytest.raises(IntegrityError):
        db.flush()


# --- AC-H5: upsert_from_extraction takes the filing attachment's company -------


def test_h5_upsert_from_extraction_shared_attachment_makes_a_shared_certificate(db):
    type_id = _type(db)
    p_s, p_m = _twin_products(db, unique_code("SRTBV"))
    att = _attachment(db, company_id=None, type_id=type_id)
    db.commit()

    # The n8n binding path leaves scope at None (all companies) for a shared
    # attachment (scope_to_attachment_company) - reproduced directly here.
    with company_scope(db, None):
        cert: any = CertificateService(db).upsert_from_extraction(
            scheme="SRTBV",
            certificate_number=unique_code("CERT")[:120],
            attachment_id=att.id,
            product_ids=[p_s.id, p_m.id],
            commit=True,
        )

    assert cert.company_id is None
    with company_scope(db, None):
        coverage_ids = {
            str(r.product_id)
            for r in db.query(CertificateProduct).filter(CertificateProduct.certificate_id == cert.id)
        }
    assert coverage_ids == {p_s.id, p_m.id}, "product resolution must span both twins"


def test_h5_upsert_from_extraction_single_company_attachment_unchanged(db):
    type_id = _type(db)
    p_s, _p_m = _twin_products(db, unique_code("SRTBV"))
    att = _attachment(db, company_id=DEFAULT_COMPANY_ID, type_id=type_id)
    db.commit()

    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    cert: any = CertificateService(db).upsert_from_extraction(
        scheme="SRTBV",
        certificate_number=unique_code("CERT")[:120],
        attachment_id=att.id,
        product_ids=[p_s.id],
        commit=True,
    )

    assert cert.company_id == DEFAULT_COMPANY_ID


# --- AC-H6: the expiry sweep fires ONE match for a shared certificate ----------


def test_h6_expiry_sweep_one_match_for_a_shared_certificate(db):
    from app.services import automation_triggers

    type_id = _type(db)
    att = _attachment(db, company_id=None, type_id=type_id)
    p_s, _p_m = _twin_products(db, unique_code("SRTBV"))
    days_before = 30
    target_expiry = automation_triggers._today_in_tz("Asia/Kuala_Lumpur") + timedelta(days=days_before)
    cert = Certificate(
        id=str(uuid.uuid4()), attachment_type_id=type_id,
        scheme=unique_code("SCHEME")[:60], certificate_number=unique_code("CERT")[:120],
        status=CERTIFICATE_STATUS_ACTIVE, company_id=None,
    )
    db.add(cert)
    db.flush()
    revision = CertificateRevision(
        id=str(uuid.uuid4()), certificate_id=cert.id, attachment_id=att.id,
        revision_no=1, is_current=True, valid_until=target_expiry,
    )
    db.add(revision)
    db.flush()
    cert.current_revision_id = revision.id
    db.commit()

    matches = list(
        automation_triggers._trigger_days_before_certificate_expiry(
            db, {"days_before": days_before}, "Asia/Kuala_Lumpur"
        )
    )
    matches = [m for m in matches if m.source_id == str(cert.id)]

    assert len(matches) == 1, "a shared certificate must fire exactly one match, not one per company"
