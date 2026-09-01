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
- H7: alembic hygiene for migration 453.

Postgres only, own seeded `ZZT-` chain (`blank_session`, ZZT- codes).
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

from app.models.base import UNSET, company_scope, set_company_scope
from app.models.certificate import (
    CERTIFICATE_SOURCE_AI,
    CERTIFICATE_SOURCE_MANUAL,
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
from app.services.certificate_service import CertificateService, normalize_identity
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.error_handler import AppException

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


# --- B1 regression: reconcile_certificate is consistently unscoped -------------


def test_b1_reconcile_shared_certificate_under_sorento_scope_is_a_no_op(db):
    """A shared certificate whose coverage AND projection are already correct
    (both twins covered, both product_attachments rows present and correctly
    stamped) reconciles to an ALL-ZERO result under a Sorento-only scope.

    This is the B1 regression: before `reconcile_certificate` ran entirely
    under `company_scope(db, None)`, the Sorento-scoped read of
    `product_attachments` silently missed the Mocha row, so `seen` never
    included it and reconcile tried to INSERT a duplicate for a product it
    could no longer see - a raw IntegrityError on the unique constraint.
    """
    type_id = _type(db)
    p_s, p_m = _twin_products(db, unique_code("SRTBV"))
    att = _attachment(db, company_id=None, type_id=type_id)
    cert = _filed_certificate(db, company_id=None, attachment=att, type_id=type_id, covers=p_s)
    # Coverage spans both twins, as AC-H1 would have left it.
    db.add(CertificateProduct(id=str(uuid.uuid4()), certificate_id=cert.id, product_id=p_m.id))
    db.flush()
    # Both projection rows already present and correctly stamped - the SAME
    # access_levels the filing attachment carries, so reconcile has nothing
    # to update either.
    access_levels = list(att.access_levels or [])
    db.add(ProductAttachment(
        id=str(uuid.uuid4()), product_id=p_s.id, attachment_id=att.id,
        company_id=DEFAULT_COMPANY_ID, access_levels=access_levels,
    ))
    db.add(ProductAttachment(
        id=str(uuid.uuid4()), product_id=p_m.id, attachment_id=att.id,
        company_id=MOCHA_ID, access_levels=access_levels,
    ))
    db.commit()

    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    result = CertificateService(db).reconcile(cert.id)

    assert result == {"inserted": 0, "updated": 0, "deleted": 0}

    with company_scope(db, None):
        rows = {
            str(r.product_id): str(r.company_id)
            for r in db.query(ProductAttachment).filter(ProductAttachment.attachment_id == att.id)
        }
    assert rows == {p_s.id: DEFAULT_COMPANY_ID, p_m.id: MOCHA_ID}, (
        "both rows must survive reconcile, each still stamped to its own company"
    )


def test_b1_reconcile_deletes_an_out_of_coverage_row_in_another_company(db):
    """Deliberate decision, documented in `reconcile_certificate`'s own
    docstring: `product_attachments` is a PURE FUNCTION of coverage. A
    Sorento-OWNED certificate (not shared) on a SHARED file covers only the
    Sorento twin; a Mocha `product_attachments` row exists on the SAME file
    but OUTSIDE this certificate's coverage (e.g. left over from a manual
    link, or a narrowed earlier certificate). Reconcile under Sorento scope
    deletes that Mocha row - it is not this certificate's to keep just
    because the caller cannot otherwise see it.
    """
    type_id = _type(db)
    p_s, p_m = _twin_products(db, unique_code("SRTBV"))
    att = _attachment(db, company_id=None, type_id=type_id)  # the FILE is shared
    cert = _filed_certificate(
        db, company_id=DEFAULT_COMPANY_ID, attachment=att, type_id=type_id, covers=p_s,
    )  # the CERTIFICATE is Sorento-owned, coverage = {p_s} only
    db.add(ProductAttachment(
        id=str(uuid.uuid4()), product_id=p_m.id, attachment_id=att.id,
        company_id=MOCHA_ID, access_levels=list(att.access_levels or []),
    ))
    db.commit()

    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    result = CertificateService(db).reconcile(cert.id)

    assert result["deleted"] == 1

    with company_scope(db, None):
        remaining = {
            str(r.product_id)
            for r in db.query(ProductAttachment).filter(ProductAttachment.attachment_id == att.id)
        }
    assert p_m.id not in remaining, "an out-of-coverage row must go regardless of company"
    assert p_s.id in remaining


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
    """The n8n path names products by CODE, not by id - the twin has to come
    from RESOLUTION (`resolve_codes_to_products`, same as the real external
    route runs before calling `upsert_from_extraction`), not from the test
    handing both companies' ids to `upsert_from_extraction` by hand."""
    from app.services.product_code_resolution import resolve_codes_to_products

    type_id = _type(db)
    code = unique_code("SRTBV")
    p_s, p_m = _twin_products(db, code)
    att = _attachment(db, company_id=None, type_id=type_id)
    db.commit()

    # The n8n binding path leaves scope at None (all companies) for a shared
    # attachment (scope_to_attachment_company) - reproduced directly here.
    with company_scope(db, None):
        resolved = resolve_codes_to_products(db, [code])
        product_ids = [str(m.product.id) for m in resolved.matches]
        assert set(product_ids) == {p_s.id, p_m.id}, (
            "the seeded code must resolve to both twins under the all-companies scope"
        )

        cert: any = CertificateService(db).upsert_from_extraction(
            scheme="SRTBV",
            certificate_number=unique_code("CERT")[:120],
            attachment_id=att.id,
            product_ids=product_ids,
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


# --- S2 (reviewer fix round): _resolve_new_certificate_company_id mirrors the
# retired auto-stamp - only a bound attachment with a NULL company yields a
# shared certificate; every other path resolves like `resolve_write_company_id`.


def test_s2_bound_attachment_owned_company_wins(db):
    type_id = _type(db)
    att = _attachment(db, company_id=MOCHA_ID, type_id=type_id)
    db.commit()

    # The realistic precondition: a caller can only NAME an attachment_id it
    # can already see, so its own scope already includes that company (or is
    # the n8n all-companies `None`) by the time this resolves.
    set_company_scope(db, frozenset({MOCHA_ID}))
    result = CertificateService(db)._resolve_new_certificate_company_id(att.id)

    assert result == MOCHA_ID


def test_s2_bound_attachment_shared_yields_none(db):
    type_id = _type(db)
    att = _attachment(db, company_id=None, type_id=type_id)
    db.commit()

    result = CertificateService(db)._resolve_new_certificate_company_id(att.id)

    assert result is None


def test_s2_no_attachment_single_active_company_wins(db):
    set_company_scope(db, frozenset({MOCHA_ID}))

    result = CertificateService(db)._resolve_new_certificate_company_id(None)

    assert result == MOCHA_ID


def test_s2_no_attachment_none_scope_falls_back_to_incumbent(db):
    set_company_scope(db, None)

    result = CertificateService(db)._resolve_new_certificate_company_id(None)

    assert result == DEFAULT_COMPANY_ID


def test_s2_no_attachment_unset_scope_raises(db):
    set_company_scope(db, UNSET)

    with pytest.raises(AppException):
        CertificateService(db)._resolve_new_certificate_company_id(None)


def test_s2_no_attachment_multi_company_scope_raises(db):
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))

    with pytest.raises(AppException):
        CertificateService(db)._resolve_new_certificate_company_id(None)


def test_s2_unresolved_attachment_id_falls_back_to_scope(db):
    """A bound id that does not resolve (e.g. deleted / foreign) is treated
    the SAME as no attachment - never silently None."""
    set_company_scope(db, frozenset({MOCHA_ID}))

    result = CertificateService(db)._resolve_new_certificate_company_id(str(uuid.uuid4()))

    assert result == MOCHA_ID


# --- S4 (reviewer fix round): two same-identity certificates sharing in one
# action are rejected before commit, naming the identity.


def test_s4_two_same_identity_certificates_sharing_in_one_action_is_rejected(db):
    type_id = _type(db)
    scheme = unique_code("SCHEME")[:60]
    number = unique_code("CERT")[:120]

    att_a = _attachment(db, company_id=DEFAULT_COMPANY_ID, type_id=type_id)
    cert_a = Certificate(
        id=str(uuid.uuid4()), attachment_type_id=type_id,
        scheme=scheme, certificate_number=number,
        status=CERTIFICATE_STATUS_ACTIVE, company_id=DEFAULT_COMPANY_ID,
    )
    db.add(cert_a)
    db.flush()
    rev_a = CertificateRevision(
        id=str(uuid.uuid4()), certificate_id=cert_a.id, attachment_id=att_a.id,
        revision_no=1, is_current=True,
    )
    db.add(rev_a)
    db.flush()
    cert_a.current_revision_id = rev_a.id

    # A second, DIFFERENT certificate that happens to share the same identity
    # (a normalization collision - "SCHEME 001" vs "SCHEME001", say) but lives
    # under a different attachment, filed in Mocha.
    att_b = _attachment(db, company_id=MOCHA_ID, type_id=type_id)
    cert_b = Certificate(
        id=str(uuid.uuid4()), attachment_type_id=type_id,
        scheme=scheme, certificate_number=number,
        status=CERTIFICATE_STATUS_ACTIVE, company_id=MOCHA_ID,
    )
    db.add(cert_b)
    db.flush()
    rev_b = CertificateRevision(
        id=str(uuid.uuid4()), certificate_id=cert_b.id, attachment_id=att_b.id,
        revision_no=1, is_current=True,
    )
    db.add(rev_b)
    db.flush()
    cert_b.current_revision_id = rev_b.id
    db.commit()

    user_id = _user_with_grants(db, [DEFAULT_COMPANY_ID, MOCHA_ID])
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))

    with pytest.raises(AppException) as exc_info:
        AttachmentCompanyService(db).apply(
            attachment_ids=[att_a.id, att_b.id], company_id=None, actor_id=user_id,
        )

    assert exc_info.value.status_code == 409
    message = exc_info.value.detail["message"]
    assert scheme in message
    assert number in message

    # Nothing committed: both certificates keep their original company.
    db.rollback()
    with company_scope(db, None):
        db.refresh(cert_a)
        db.refresh(cert_b)
    assert cert_a.company_id == DEFAULT_COMPANY_ID
    assert cert_b.company_id == MOCHA_ID


# --- S5 (reviewer fix round): find_by_identity ties break deterministically,
# an owned row over a shared one.


def test_s5_find_by_identity_prefers_the_owned_row_over_a_shared_one(db):
    type_id = _type(db)
    scheme = unique_code("SCHEME")[:60]
    number = unique_code("CERT")[:120]

    shared_cert = Certificate(
        id=str(uuid.uuid4()), attachment_type_id=type_id,
        scheme=scheme, certificate_number=number,
        status=CERTIFICATE_STATUS_ACTIVE, company_id=None,
    )
    owned_cert = Certificate(
        id=str(uuid.uuid4()), attachment_type_id=type_id,
        scheme=scheme, certificate_number=number,
        status=CERTIFICATE_STATUS_ACTIVE, company_id=DEFAULT_COMPANY_ID,
    )
    db.add_all([shared_cert, owned_cert])
    db.commit()

    with company_scope(db, None):
        found = CertificateService(db).find_by_identity(scheme, number)

    assert found is not None
    assert str(found.id) == str(owned_cert.id), (
        "a real company's own row must win the tie over a shared one"
    )


# --- S7 (reviewer fix round): a twin coverage row inherits `source` (and
# `created_by`) from the SAME-code row it was expanded from, never defaults
# to manual.


def test_s7_twin_coverage_row_inherits_source_from_the_same_code_row(db):
    type_id = _type(db)
    p_s, p_m = _twin_products(db, unique_code("SRTBV"))
    att = _attachment(db, company_id=DEFAULT_COMPANY_ID, type_id=type_id)
    cert = _filed_certificate(
        db, company_id=DEFAULT_COMPANY_ID, attachment=att, type_id=type_id, covers=p_s,
    )
    # The source row was AI-extracted, and created by a specific integration
    # principal - both must survive onto the twin.
    source_row = (
        db.query(CertificateProduct)
        .filter(CertificateProduct.certificate_id == cert.id, CertificateProduct.product_id == p_s.id)
        .first()
    )
    ai_created_by = str(uuid.uuid4())
    source_row.source = CERTIFICATE_SOURCE_AI
    source_row.created_by = ai_created_by
    user_id = _user_with_grants(db, [DEFAULT_COMPANY_ID, MOCHA_ID])
    db.commit()

    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    AttachmentCompanyService(db).apply(
        attachment_ids=[att.id], company_id=None, actor_id=user_id,
    )

    with company_scope(db, None):
        twin_row = (
            db.query(CertificateProduct)
            .filter(CertificateProduct.certificate_id == cert.id, CertificateProduct.product_id == p_m.id)
            .first()
        )
    assert twin_row is not None
    assert twin_row.source == CERTIFICATE_SOURCE_AI, (
        "a twin row must inherit the source-code row's source, never default to manual"
    )
    assert str(twin_row.created_by) == ai_created_by
