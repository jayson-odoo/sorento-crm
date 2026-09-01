"""Certificate register service: identity, validity, revisions, coverage, merge.

Postgres only, on an isolated blank schema whose writes are discarded. Every
test seeds its own chain - attachment type, attachment, category, uom, product -
under a ZZTCERT marker. Nothing is borrowed from an existing table: CI's
database has no data, so a `LIMIT 1` off `products` there returns None and the
dependent insert dies on a not-null FK.
"""
from datetime import date, timedelta
from typing import Any

import pytest

from app.models.base import company_scope
from app.models.certificate import (
    CERTIFICATE_SOURCE_AI,
    CERTIFICATE_SOURCE_MANUAL,
    Certificate,
    CertificateProduct,
    CertificateRevision,
)
from app.models.company import Company
from app.models.product import Product, ProductAttachment, ProductCategory, UnitOfMeasure
from app.models.resources import Attachment, AttachmentType
from app.schemas.certificate import CertificateCreate
from app.services.certificate_service import (
    REVIEW_EXPIRED_AT_INGEST,
    REVIEW_IMPLAUSIBLE_SPAN,
    REVIEW_MISSING_FIELD,
    REVIEW_NO_COVERAGE,
    REVIEW_POSSIBLE_DUPLICATE,
    REVIEW_UNMATCHED_PRODUCTS,
    VALIDITY_EXPIRED,
    VALIDITY_EXPIRING_SOON,
    VALIDITY_NOT_YET_VALID,
    VALIDITY_UNKNOWN,
    VALIDITY_VALID,
    CertificateService,
    derive_validity,
    normalize_identity,
)
from app.services.error_handler import AppException
from tests._pg_fixture import blank_session, unique_code

MARKER = "ZZTCERT"
TODAY = date(2026, 8, 4)


# --------------------------------------------------------------------- fixtures
@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def chain(db) -> dict[str, Any]:
    """Attachment type + category + uom, the FK parents everything else needs."""
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
    return {"attachment_type": attachment_type, "category": category, "uom": uom}


def _product(db, chain, code_stem: str) -> Any:
    product = Product(
        product_code=unique_code(f"{MARKER}-{code_stem}"),
        product_name=f"{MARKER} {code_stem}",
        category_id=chain["category"].id,
        base_uom_id=chain["uom"].id,
        list_price=10,
    )
    db.add(product)
    db.flush()
    return product


def _attachment(db, chain, name: str, access_levels=None) -> Any:
    attachment = Attachment(
        attachment_type_id=chain["attachment_type"].id,
        original_filename=f"{MARKER}-{name}.pdf",
        stored_filename=f"{MARKER}-{name}.pdf",
        file_path=f"https://cdn.example/{MARKER}/{name}.pdf",
        access_levels=access_levels or ["dealer", "end_user"],
    )
    db.add(attachment)
    db.flush()
    return attachment


def _projection(db, attachment_id) -> list[Any]:
    return (
        db.query(ProductAttachment)
        .filter(ProductAttachment.attachment_id == str(attachment_id))
        .all()
    )


# ------------------------------------------------------------------- SCH: identity
def test_normalize_identity_strips_case_and_punctuation():
    assert normalize_identity("PPS", "0119") == "PPS0119"
    assert normalize_identity("pps", "-0119") == "PPS0119"
    assert normalize_identity(" PPS ", "0 1 1 9") == "PPS0119"
    # The scheme is part of the key, so these are two different certificates.
    assert normalize_identity("PPS", "04124FC") != normalize_identity("SPAN", "04124FC")


def test_pps_and_span_04124fc_stay_two_certificates(db, chain):
    """The live case: one IKRAM test-report number approved under two schemes,
    with different expiries. Keying on the number alone would merge them and
    silently overwrite the earlier expiry."""
    service = CertificateService(db)
    product = _product(db, chain, "WC8038")

    pps: Any = service.upsert_from_extraction(
        scheme="PPS",
        certificate_number="04124FC",
        certifying_body="IKRAM",
        attachment_id=_attachment(db, chain, "pps-04124fc").id,
        valid_until=date(2027, 4, 1),
        product_ids=[product.id],
    )
    span: Any = service.upsert_from_extraction(
        scheme="SPAN",
        certificate_number="04124FC",
        certifying_body="IKRAM",
        attachment_id=_attachment(db, chain, "span-04124fc").id,
        valid_until=date(2029, 4, 5),
        product_ids=[product.id],
    )

    assert pps.id != span.id
    assert pps._certificate_created is True
    assert span._certificate_created is True
    assert pps._revision_no == 1 and span._revision_no == 1
    # Different scheme, so not even a duplicate suspicion.
    assert span.possible_duplicate_of_certificate_id is None
    assert db.query(Certificate).count() == 2

    by_scheme = {c.scheme: c for c in db.query(Certificate).all()}
    current: dict[str, Any] = {
        scheme: service.get_current_revision(cert) for scheme, cert in by_scheme.items()
    }
    assert current["PPS"].valid_until == date(2027, 4, 1)
    assert current["SPAN"].valid_until == date(2029, 4, 5)


def test_punctuation_variants_are_the_same_certificate(db, chain):
    service = CertificateService(db)
    product = _product(db, chain, "AV100")

    first: Any = service.upsert_from_extraction(
        scheme="PPS",
        certificate_number="PC 000321",
        attachment_id=_attachment(db, chain, "one").id,
        valid_until=date(2027, 1, 7),
        product_ids=[product.id],
    )
    second: Any = service.upsert_from_extraction(
        scheme="pps",
        certificate_number="pc-000321",
        attachment_id=_attachment(db, chain, "two").id,
        valid_until=date(2028, 1, 7),
    )

    assert first.id == second.id
    assert second._certificate_created is False
    assert second._revision_no == 2
    assert db.query(Certificate).count() == 1


def test_identity_unique_index_rejects_a_second_row(db, chain):
    """SCH-2 at the database level, not just in the service."""
    from sqlalchemy.exc import IntegrityError

    db.add(Certificate(scheme="PPS", certificate_number="0119"))
    db.flush()
    savepoint = db.begin_nested()
    db.add(Certificate(scheme="pps", certificate_number="-01-19-"))
    with pytest.raises(IntegrityError):
        db.flush()
    savepoint.rollback()


# --------------------------------------------------------------------- VAL: validity
@pytest.mark.parametrize(
    "valid_from,valid_until,expected,expired",
    [
        (date(2026, 1, 1), date(2027, 12, 31), VALIDITY_VALID, False),
        (date(2026, 1, 1), TODAY + timedelta(days=10), VALIDITY_EXPIRING_SOON, False),
        (date(2020, 1, 1), TODAY - timedelta(days=1), VALIDITY_EXPIRED, True),
        (TODAY + timedelta(days=5), date(2028, 1, 1), VALIDITY_NOT_YET_VALID, False),
        (date(2026, 1, 1), None, VALIDITY_UNKNOWN, False),
    ],
)
def test_derive_validity(valid_from, valid_until, expected, expired):
    state, is_expired, days = derive_validity(valid_from, valid_until, today=TODAY)
    assert state == expected
    assert is_expired is expired
    assert (days is None) is (valid_until is None)


def test_null_valid_until_serializes_unknown_and_flags_review(db, chain):
    """A missing date is never "no expiry": unknown, flagged, reminder-inert."""
    service = CertificateService(db)
    product = _product(db, chain, "NODATE")
    cert: Any = service.upsert_from_extraction(
        scheme=f"{MARKER}PPS",
        certificate_number="NO-EXPIRY-1",
        attachment_id=_attachment(db, chain, "nodate").id,
        valid_until=None,
        product_ids=[product.id],
    )

    row: Any = service.serialize(cert, today=TODAY)
    assert row.validity_state == VALIDITY_UNKNOWN
    assert row.is_expired is False
    assert row.days_until_expiry is None
    assert row.needs_review is True
    assert {r["code"] for r in row.review_reasons} >= {REVIEW_MISSING_FIELD}
    assert any(r.get("field") == "valid_until" for r in row.review_reasons)


def test_validity_reads_the_current_revision_only(db, chain):
    """A superseded expired window must not make the certificate read expired."""
    service = CertificateService(db)
    product = _product(db, chain, "SUPER")
    cert: Any = service.upsert_from_extraction(
        scheme=f"{MARKER}PPS",
        certificate_number="SUPERSEDED-1",
        attachment_id=_attachment(db, chain, "rev1").id,
        valid_from=date(2021, 1, 1),
        valid_until=date(2023, 1, 1),
        product_ids=[product.id],
    )
    assert service.serialize(cert, today=TODAY).validity_state == VALIDITY_EXPIRED

    service.upsert_from_extraction(
        scheme=f"{MARKER}PPS",
        certificate_number="SUPERSEDED-1",
        attachment_id=_attachment(db, chain, "rev2").id,
        valid_from=date(2026, 1, 1),
        valid_until=date(2029, 1, 1),
    )
    cert = service.get_certificate(cert.id)
    row: Any = service.serialize(cert, today=TODAY)
    assert row.validity_state == VALIDITY_VALID
    assert row.is_expired is False
    assert row.revision_no == 2


# --------------------------------------------------------------------- RVW: review
def test_implausible_validity_span_is_flagged_not_swallowed(db, chain):
    """max_validity_months = 60 and a date 15 years out: the revision is still
    created, and the reason names the span."""
    chain["attachment_type"].max_validity_months = 60
    db.flush()
    service = CertificateService(db)
    product = _product(db, chain, "HALLUC")

    cert: Any = service.upsert_from_extraction(
        scheme=f"{MARKER}PPS",
        certificate_number="HALLUCINATED-1",
        attachment_id=_attachment(db, chain, "halluc").id,
        valid_from=date(2026, 1, 1),
        valid_until=date(2041, 1, 1),
        product_ids=[product.id],
    )

    revision: Any = service.get_current_revision(cert)
    assert revision is not None and revision.revision_no == 1
    assert revision.needs_review is True
    reason = next(
        r for r in revision.review_reasons if r["code"] == REVIEW_IMPLAUSIBLE_SPAN
    )
    assert reason["months"] == 180
    assert reason["max_months"] == 60


def test_plausible_span_within_the_cap_is_not_flagged(db, chain):
    chain["attachment_type"].max_validity_months = 60
    db.flush()
    service = CertificateService(db)
    product = _product(db, chain, "PLAUS")

    cert: Any = service.upsert_from_extraction(
        scheme=f"{MARKER}PPS",
        certificate_number="PLAUSIBLE-1",
        attachment_id=_attachment(db, chain, "plaus").id,
        valid_from=date(2026, 1, 1),
        valid_until=date(2029, 1, 1),
        product_ids=[product.id],
    )
    revision: Any = service.get_current_revision(cert)
    assert revision.needs_review is False
    assert revision.review_reasons == []


def test_unmatched_product_strings_are_persisted_verbatim(db, chain):
    """The PPS 04224FC failure, made visible: strings that matched nothing are
    kept exactly as extracted."""
    service = CertificateService(db)
    product = _product(db, chain, "MATCHED")

    cert: Any = service.upsert_from_extraction(
        scheme=f"{MARKER}PPS",
        certificate_number="UNMATCHED-1",
        attachment_id=_attachment(db, chain, "unmatched").id,
        valid_until=date(2029, 1, 1),
        product_ids=[product.id],
        unmatched_products=["WC 9999", "ANGLE VALVE 1/2"],
    )

    revision: Any = service.get_current_revision(cert)
    assert revision.unmatched_products == ["WC 9999", "ANGLE VALVE 1/2"]
    assert revision.needs_review is True
    reason = next(
        r for r in revision.review_reasons if r["code"] == REVIEW_UNMATCHED_PRODUCTS
    )
    assert reason["count"] == 2
    assert reason["values"] == ["WC 9999", "ANGLE VALVE 1/2"]


def test_zero_coverage_is_flagged(db, chain):
    service = CertificateService(db)
    cert: Any = service.upsert_from_extraction(
        scheme=f"{MARKER}PPS",
        certificate_number="ZEROCOVER-1",
        attachment_id=_attachment(db, chain, "zerocover").id,
        valid_until=date(2029, 1, 1),
    )
    revision: Any = service.get_current_revision(cert)
    assert revision.needs_review is True
    assert REVIEW_NO_COVERAGE in {r["code"] for r in revision.review_reasons}


def test_already_expired_at_ingest_is_flagged(db, chain):
    service = CertificateService(db)
    product = _product(db, chain, "OLD")
    cert: Any = service.upsert_from_extraction(
        scheme=f"{MARKER}PPS",
        certificate_number="ALREADYEXPIRED-1",
        attachment_id=_attachment(db, chain, "old").id,
        valid_from=date(2019, 1, 1),
        valid_until=date(2020, 1, 1),
        product_ids=[product.id],
    )
    revision: Any = service.get_current_revision(cert)
    assert REVIEW_EXPIRED_AT_INGEST in {r["code"] for r in revision.review_reasons}


def test_clearing_the_review_flag_needs_a_reviewer(db, chain):
    service = CertificateService(db)
    cert: Any = service.upsert_from_extraction(
        scheme=f"{MARKER}PPS",
        certificate_number="REVIEWME-1",
        attachment_id=_attachment(db, chain, "reviewme").id,
        valid_until=date(2029, 1, 1),
    )
    revision: Any = service.get_current_revision(cert)
    assert revision.needs_review is True

    with pytest.raises(AppException):
        service.mark_revision_reviewed(revision.id, reviewed_by="")

    reviewer = "00000000-0000-0000-0000-0000000000aa"
    cleared: Any = service.mark_revision_reviewed(revision.id, reviewed_by=reviewer)
    assert cleared.needs_review is False
    assert str(cleared.reviewed_by) == reviewer
    assert cleared.reviewed_at is not None


# --------------------------------------------------------------------- REV: renewal
def test_renewal_appends_a_revision_and_leaves_coverage_untouched(db, chain):
    """68 links must survive a renewal with zero writes - coverage hangs off the
    identity, not the document."""
    service = CertificateService(db)
    products = [_product(db, chain, f"COV{i}") for i in range(3)]
    first_attachment = _attachment(db, chain, "renewal-rev1")

    cert: Any = service.upsert_from_extraction(
        scheme=f"{MARKER}PPS",
        certificate_number="RENEWAL-1",
        attachment_id=first_attachment.id,
        valid_until=date(2026, 12, 23),
        product_ids=[p.id for p in products],
    )
    before = {
        (str(row.id), str(row.product_id), row.source, row.created_at)
        for row in service.get_coverage(cert.id)
    }
    assert len(before) == 3

    second_attachment = _attachment(db, chain, "renewal-rev2")
    renewed: Any = service.upsert_from_extraction(
        scheme=f"{MARKER}PPS",
        certificate_number="RENEWAL-1",
        attachment_id=second_attachment.id,
        valid_until=date(2028, 12, 23),
        # A renewal PDF naming only one product must NOT shrink coverage.
        product_ids=[products[0].id],
    )

    assert renewed.id == cert.id
    assert renewed._certificate_created is False
    assert renewed._revision_no == 2
    after = {
        (str(row.id), str(row.product_id), row.source, row.created_at)
        for row in service.get_coverage(cert.id)
    }
    assert after == before

    revisions: list[Any] = service.get_revisions(cert.id)
    assert [r.revision_no for r in revisions] == [2, 1]
    assert [bool(r.is_current) for r in revisions] == [True, False]
    assert str(renewed.current_revision_id) == str(revisions[0].id)


def test_renewal_repoints_the_projection_hard_deleting_the_old_rows(db, chain):
    """A dealer can never be served the superseded PDF."""
    service = CertificateService(db)
    products = [_product(db, chain, f"PROJ{i}") for i in range(2)]
    old_attachment = _attachment(db, chain, "proj-rev1")
    new_attachment = _attachment(db, chain, "proj-rev2", access_levels=["dealer"])

    cert: Any = service.upsert_from_extraction(
        scheme=f"{MARKER}PPS",
        certificate_number="PROJECTION-1",
        attachment_id=old_attachment.id,
        valid_until=date(2026, 12, 23),
        product_ids=[p.id for p in products],
    )
    assert len(_projection(db, old_attachment.id)) == 2

    service.upsert_from_extraction(
        scheme=f"{MARKER}PPS",
        certificate_number="PROJECTION-1",
        attachment_id=new_attachment.id,
        valid_until=date(2028, 12, 23),
    )

    assert _projection(db, old_attachment.id) == []
    new_rows: list[Any] = _projection(db, new_attachment.id)
    assert {str(r.product_id) for r in new_rows} == {str(p.id) for p in products}
    # Access levels are inherited from the CURRENT revision's attachment.
    assert all(r.access_levels == ["dealer"] for r in new_rows)
    # The superseded attachment row itself survives, downloadable from the
    # certificate detail page.
    assert db.query(Attachment).filter(Attachment.id == old_attachment.id).count() == 1


def test_renewal_detection_is_scoped_to_the_scheme(db, chain):
    service = CertificateService(db)
    service.upsert_from_extraction(
        scheme="PPS",
        certificate_number="SCOPED-1",
        attachment_id=_attachment(db, chain, "scoped-pps").id,
        valid_until=date(2027, 1, 1),
    )
    span: Any = service.upsert_from_extraction(
        scheme="SPAN",
        certificate_number="SCOPED-1",
        attachment_id=_attachment(db, chain, "scoped-span").id,
        valid_until=date(2029, 1, 1),
    )
    assert span._certificate_created is True
    assert span._revision_no == 1
    assert db.query(Certificate).count() == 2


# --------------------------------------------------------------------- COV: coverage
def test_manual_coverage_add_and_remove_moves_the_projection(db, chain):
    service = CertificateService(db)
    seeded = _product(db, chain, "SEED")
    added = _product(db, chain, "ADDED")
    attachment = _attachment(db, chain, "coverage")

    cert: Any = service.upsert_from_extraction(
        scheme=f"{MARKER}PPS",
        certificate_number="COVERAGE-1",
        attachment_id=attachment.id,
        valid_until=date(2029, 1, 1),
        product_ids=[seeded.id],
    )
    assert {str(r.product_id) for r in _projection(db, attachment.id)} == {str(seeded.id)}

    service.add_coverage(cert.id, [added.id], source=CERTIFICATE_SOURCE_MANUAL)
    by_product = {str(r.product_id): r.source for r in service.get_coverage(cert.id)}
    assert by_product == {
        str(seeded.id): CERTIFICATE_SOURCE_AI,
        str(added.id): CERTIFICATE_SOURCE_MANUAL,
    }
    assert {str(r.product_id) for r in _projection(db, attachment.id)} == {
        str(seeded.id),
        str(added.id),
    }

    service.remove_coverage(cert.id, [seeded.id])
    assert {str(r.product_id) for r in service.get_coverage(cert.id)} == {str(added.id)}
    assert {str(r.product_id) for r in _projection(db, attachment.id)} == {str(added.id)}


def test_serialize_coverage_resolves_cross_company_and_shared_products(db, chain):
    """Coverage rows point at products from BOTH companies - AI document
    extraction matches codes across companies - and can point at a shared
    product (``company_id`` NULL). Scoped to Sorento only, every row must
    still resolve code/name/company_name; the OTHER company's product used
    to come back blank (product_code=None) because the outer join was
    filtered by the caller's ambient scope."""
    from app.models.base import set_company_scope
    from app.models.company import Company
    from app.services.company_scope import DEFAULT_COMPANY_ID

    mocha_id = "00000000-0000-0000-0000-000000000002"
    mocha = Company(id=mocha_id, name=f"{MARKER} Mocha", code=unique_code("MCH")[:20])
    db.add(mocha)
    db.flush()

    product_sorento = _product(db, chain, "COMPANY-A")
    product_mocha = Product(
        product_code=unique_code(f"{MARKER}-COMPANY-B"),
        product_name=f"{MARKER} company b",
        category_id=chain["category"].id,
        base_uom_id=chain["uom"].id,
        list_price=10,
        company_id=mocha_id,
    )
    db.add(product_mocha)
    product_shared = _product(db, chain, "SHARED")
    # The before_insert auto-stamp fills an unset company_id from the ambient
    # scope, so a genuinely shared row (company_id NULL) has to be forced in
    # afterwards - an UPDATE, which the stamp hook (before_insert only) never
    # touches.
    product_shared.company_id = None
    db.flush()

    service = CertificateService(db)
    cert: Any = service.upsert_from_extraction(
        scheme=f"{MARKER}PPS",
        certificate_number="CROSSCO-1",
        attachment_id=_attachment(db, chain, "crossco").id,
        valid_until=date(2029, 1, 1),
        product_ids=[product_sorento.id],
    )
    # add_coverage resolves products through the ambient (Sorento) scope, so a
    # cross-company / shared row is written directly - matching how the AI
    # extraction path (which runs under company_scope(db, None)) would leave it.
    db.add_all(
        [
            CertificateProduct(
                certificate_id=cert.id,
                product_id=product_mocha.id,
                source=CERTIFICATE_SOURCE_AI,
            ),
            CertificateProduct(
                certificate_id=cert.id,
                product_id=product_shared.id,
                source=CERTIFICATE_SOURCE_AI,
            ),
        ]
    )
    db.commit()

    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    rows = service.serialize_coverage(cert.id)

    by_product = {r.product_id: r for r in rows}
    assert len(rows) == 3
    sorento_row = by_product[str(product_sorento.id)]
    assert sorento_row.product_code == product_sorento.product_code
    assert sorento_row.product_name == product_sorento.product_name
    assert sorento_row.company_name == "Sorento"

    mocha_row = by_product[str(product_mocha.id)]
    assert mocha_row.product_code == product_mocha.product_code
    assert mocha_row.product_name == product_mocha.product_name
    assert mocha_row.company_name == mocha.name

    shared_row = by_product[str(product_shared.id)]
    assert shared_row.product_code == product_shared.product_code
    assert shared_row.product_name == product_shared.product_name
    assert shared_row.company_name == "Shared"


def test_set_coverage_keeps_the_source_of_rows_it_did_not_create(db, chain):
    service = CertificateService(db)
    kept = _product(db, chain, "KEPT")
    dropped = _product(db, chain, "DROPPED")
    fresh = _product(db, chain, "FRESH")
    cert: Any = service.upsert_from_extraction(
        scheme=f"{MARKER}PPS",
        certificate_number="SETCOVER-1",
        attachment_id=_attachment(db, chain, "setcover").id,
        valid_until=date(2029, 1, 1),
        product_ids=[kept.id, dropped.id],
    )

    service.set_coverage(cert.id, [kept.id, fresh.id], source=CERTIFICATE_SOURCE_MANUAL)
    by_product = {str(r.product_id): r.source for r in service.get_coverage(cert.id)}
    assert by_product == {
        str(kept.id): CERTIFICATE_SOURCE_AI,
        str(fresh.id): CERTIFICATE_SOURCE_MANUAL,
    }


def test_reconcile_repairs_drift_and_is_safe_to_rerun(db, chain):
    service = CertificateService(db)
    covered = _product(db, chain, "RECON")
    stranger = _product(db, chain, "STRANGER")
    attachment = _attachment(db, chain, "recon")
    cert: Any = service.upsert_from_extraction(
        scheme=f"{MARKER}PPS",
        certificate_number="RECONCILE-1",
        attachment_id=attachment.id,
        valid_until=date(2029, 1, 1),
        product_ids=[covered.id],
    )

    # Drift it three ways: a wrong access level, a row for an uncovered
    # product, and a missing row.
    rows: list[Any] = _projection(db, attachment.id)
    rows[0].access_levels = ["end_user"]
    db.add(
        ProductAttachment(
            product_id=stranger.id,
            attachment_id=attachment.id,
            access_levels=["dealer"],
        )
    )
    db.flush()

    counters = service.reconcile(cert.id)
    assert counters == {"inserted": 0, "updated": 1, "deleted": 1}
    repaired: list[Any] = _projection(db, attachment.id)
    assert len(repaired) == 1
    assert str(repaired[0].product_id) == str(covered.id)
    assert repaired[0].access_levels == ["dealer", "end_user"]

    # Re-running changes nothing: it sets the correct value where it differs,
    # rather than inserting where missing.
    assert service.reconcile(cert.id) == {"inserted": 0, "updated": 0, "deleted": 0}


def test_delete_certificate_hard_deletes_children_and_keeps_the_file(db, chain):
    service = CertificateService(db)
    product = _product(db, chain, "DELME")
    attachment = _attachment(db, chain, "delme")
    cert: Any = service.upsert_from_extraction(
        scheme=f"{MARKER}PPS",
        certificate_number="DELETE-1",
        attachment_id=attachment.id,
        valid_until=date(2029, 1, 1),
        product_ids=[product.id],
    )
    cert_id = str(cert.id)

    service.delete_certificate(cert_id)

    assert db.query(Certificate).filter(Certificate.id == cert_id).count() == 0
    assert (
        db.query(CertificateRevision)
        .filter(CertificateRevision.certificate_id == cert_id)
        .count()
        == 0
    )
    assert (
        db.query(CertificateProduct)
        .filter(CertificateProduct.certificate_id == cert_id)
        .count()
        == 0
    )
    assert _projection(db, attachment.id) == []
    assert db.query(Attachment).filter(Attachment.id == attachment.id).count() == 1


# --------------------------------------------------------------- DUP: near match
def test_near_match_flags_a_suspicion_and_never_merges(db, chain):
    service = CertificateService(db)
    original: Any = service.upsert_from_extraction(
        scheme="PPS",
        certificate_number="WCM PC 000321",
        attachment_id=_attachment(db, chain, "dup-original").id,
        valid_until=date(2027, 1, 7),
    )
    mangled: Any = service.upsert_from_extraction(
        scheme="PPS",
        certificate_number="WCM PC 0O0321",
        attachment_id=_attachment(db, chain, "dup-mangled").id,
        valid_until=date(2027, 1, 7),
    )

    assert mangled.id != original.id
    assert str(mangled.possible_duplicate_of_certificate_id) == str(original.id)
    revision: Any = service.get_current_revision(mangled)
    reason = next(
        r for r in revision.review_reasons if r["code"] == REVIEW_POSSIBLE_DUPLICATE
    )
    assert reason["certificate_id"] == str(original.id)
    assert db.query(Certificate).count() == 2


def test_merge_into_moves_revisions_unions_coverage_and_repoints(db, chain):
    service = CertificateService(db)
    shared = _product(db, chain, "SHARED")
    only_target = _product(db, chain, "TGTONLY")
    only_source = _product(db, chain, "SRCONLY")
    hand_added = _product(db, chain, "SRCMANUAL")
    target_attachment = _attachment(db, chain, "merge-target")
    source_attachment = _attachment(db, chain, "merge-source")

    target: Any = service.upsert_from_extraction(
        scheme="PPS",
        certificate_number="MERGE-TARGET",
        attachment_id=target_attachment.id,
        valid_until=date(2026, 12, 23),
        product_ids=[shared.id, only_target.id],
    )
    source: Any = service.upsert_from_extraction(
        scheme="PPS",
        certificate_number="MERGE-SOURCE",
        attachment_id=source_attachment.id,
        valid_until=date(2028, 12, 23),
        product_ids=[shared.id, only_source.id],
    )
    service.add_coverage(source.id, [hand_added.id], source=CERTIFICATE_SOURCE_MANUAL)
    target_id, source_id = str(target.id), str(source.id)

    merged: Any = service.merge_into(source_id, target_id)

    assert str(merged.id) == target_id
    assert db.query(Certificate).filter(Certificate.id == source_id).count() == 0
    revisions: list[Any] = service.get_revisions(target_id)
    assert [r.revision_no for r in revisions] == [2, 1]
    assert [bool(r.is_current) for r in revisions] == [True, False]
    # The moved document is the newest issue, so it is the live one.
    assert str(revisions[0].attachment_id) == str(source_attachment.id)
    assert str(merged.current_revision_id) == str(revisions[0].id)

    coverage = {str(r.product_id): r.source for r in service.get_coverage(target_id)}
    assert coverage == {
        str(shared.id): CERTIFICATE_SOURCE_AI,  # the target's row won, source kept
        str(only_target.id): CERTIFICATE_SOURCE_AI,
        str(only_source.id): CERTIFICATE_SOURCE_AI,
        # A hand-confirmed link stays hand-confirmed after being moved.
        str(hand_added.id): CERTIFICATE_SOURCE_MANUAL,
    }

    assert _projection(db, target_attachment.id) == []
    assert {str(r.product_id) for r in _projection(db, source_attachment.id)} == set(
        coverage
    )


def test_merge_refuses_a_self_merge(db, chain):
    service = CertificateService(db)
    cert: Any = service.upsert_from_extraction(
        scheme="PPS",
        certificate_number="SELFMERGE-1",
        attachment_id=_attachment(db, chain, "selfmerge").id,
        valid_until=date(2029, 1, 1),
    )
    with pytest.raises(AppException) as excinfo:
        service.merge_into(cert.id, cert.id)
    assert excinfo.value.status_code == 422


def test_merge_refuses_across_companies(db, chain):
    other: Any = Company(name=f"{MARKER} Other", code=unique_code(MARKER)[:20], is_active=True)
    db.add(other)
    db.flush()

    service = CertificateService(db)
    mine: Any = service.upsert_from_extraction(
        scheme="PPS",
        certificate_number="CROSSCO-MINE",
        attachment_id=_attachment(db, chain, "crossco-mine").id,
        valid_until=date(2029, 1, 1),
    )
    theirs: Any = Certificate(
        scheme="PPS", certificate_number="CROSSCO-THEIRS", company_id=other.id
    )
    db.add(theirs)
    db.flush()

    # An all-companies scope so both rows are visible; the refusal must come
    # from the company check, not from the row being invisible.
    with company_scope(db, None):
        with pytest.raises(AppException) as excinfo:
            CertificateService(db).merge_into(str(theirs.id), str(mine.id))
    assert excinfo.value.status_code == 422


# ------------------------------------------------------------------ manual create
def test_manual_create_files_revision_one_with_its_coverage(db, chain):
    service = CertificateService(db)
    product = _product(db, chain, "MANUAL")
    attachment = _attachment(db, chain, "manual")

    cert: Any = service.create_certificate(
        CertificateCreate(
            scheme=f"{MARKER}SPAN",
            certificate_number="MANUAL-1",
            certifying_body="IKRAM",
            attachment_id=str(attachment.id),
            valid_from=date(2026, 1, 1),
            valid_until=date(2029, 1, 1),
            product_ids=[str(product.id)],
        )
    )

    revision: Any = service.get_current_revision(cert)
    assert revision.revision_no == 1
    assert revision.source == CERTIFICATE_SOURCE_MANUAL
    assert {str(r.product_id) for r in service.get_coverage(cert.id)} == {str(product.id)}
    assert {str(r.product_id) for r in _projection(db, attachment.id)} == {str(product.id)}

    row: Any = service.serialize(cert, expand=True, today=TODAY)
    assert row.covered_product_count == 1
    assert row.validity_state == VALIDITY_VALID
    assert len(row.revisions) == 1
    assert row.revisions[0].attachment_filename.endswith(".pdf")
    assert row.covered_products[0].product_code.startswith("ZZT")


def test_manual_create_rejects_a_duplicate_identity(db, chain):
    service = CertificateService(db)
    payload = CertificateCreate(
        scheme=f"{MARKER}SPAN", certificate_number="DUPCREATE-1"
    )
    service.create_certificate(payload)
    with pytest.raises(AppException) as excinfo:
        service.create_certificate(
            CertificateCreate(scheme=f"{MARKER}span", certificate_number="dupcreate 1")
        )
    assert excinfo.value.status_code == 400


def test_upsert_requires_a_scheme_and_a_number(db, chain):
    service = CertificateService(db)
    with pytest.raises(AppException) as excinfo:
        service.upsert_from_extraction(scheme="PPS", certificate_number="   ")
    assert excinfo.value.status_code == 400


# ------------------------------------------------- RVW: flags follow live state
def _reason_codes(revision) -> set[str]:
    return {r["code"] for r in (revision.review_reasons or [])}


def test_adding_coverage_clears_the_no_coverage_flag(db, chain):
    """The user-reported defect: coverage was added, the flag stayed. The flags
    are STORED on the revision, so every coverage write has to re-run the rules."""
    service = CertificateService(db)
    cert: Any = service.upsert_from_extraction(
        scheme=f"{MARKER}PPS",
        certificate_number="RECOMPUTE-1",
        attachment_id=_attachment(db, chain, "recompute1").id,
        valid_until=date(2029, 1, 1),
    )
    revision: Any = service.get_current_revision(cert)
    assert revision.needs_review is True
    assert _reason_codes(revision) == {REVIEW_NO_COVERAGE}

    product = _product(db, chain, "RECOMP1")
    service.add_coverage(cert.id, [product.id], commit=False)

    revision = service.get_current_revision(cert)
    assert REVIEW_NO_COVERAGE not in _reason_codes(revision)
    # It was the ONLY reason, so the certificate is clean now.
    assert revision.needs_review is False


def test_adding_coverage_keeps_an_unrelated_reason(db, chain):
    """Clearing one reason must not clear the row: an expired-at-ingest
    certificate with coverage added is still a certificate that needs a look."""
    service = CertificateService(db)
    cert: Any = service.upsert_from_extraction(
        scheme=f"{MARKER}PPS",
        certificate_number="RECOMPUTE-2",
        attachment_id=_attachment(db, chain, "recompute2").id,
        valid_from=date(2019, 1, 1),
        valid_until=date(2020, 1, 1),
    )
    revision: Any = service.get_current_revision(cert)
    assert {REVIEW_NO_COVERAGE, REVIEW_EXPIRED_AT_INGEST} <= _reason_codes(revision)

    product = _product(db, chain, "RECOMP2")
    service.add_coverage(cert.id, [product.id], commit=False)

    revision = service.get_current_revision(cert)
    assert _reason_codes(revision) == {REVIEW_EXPIRED_AT_INGEST}
    assert revision.needs_review is True


def test_removing_all_coverage_reflags_it(db, chain):
    service = CertificateService(db)
    product = _product(db, chain, "RECOMP3")
    cert: Any = service.upsert_from_extraction(
        scheme=f"{MARKER}PPS",
        certificate_number="RECOMPUTE-3",
        attachment_id=_attachment(db, chain, "recompute3").id,
        valid_until=date(2029, 1, 1),
        product_ids=[product.id],
    )
    revision: Any = service.get_current_revision(cert)
    assert revision.needs_review is False

    service.remove_coverage(cert.id, [product.id], commit=False)
    revision = service.get_current_revision(cert)
    assert _reason_codes(revision) == {REVIEW_NO_COVERAGE}
    assert revision.needs_review is True


def test_set_coverage_both_directions(db, chain):
    service = CertificateService(db)
    cert: Any = service.upsert_from_extraction(
        scheme=f"{MARKER}PPS",
        certificate_number="RECOMPUTE-4",
        attachment_id=_attachment(db, chain, "recompute4").id,
        valid_until=date(2029, 1, 1),
    )
    product = _product(db, chain, "RECOMP4")

    service.set_coverage(cert.id, [product.id], commit=False)
    assert service.get_current_revision(cert).needs_review is False

    service.set_coverage(cert.id, [], commit=False)
    revision: Any = service.get_current_revision(cert)
    assert _reason_codes(revision) == {REVIEW_NO_COVERAGE}
    assert revision.needs_review is True


def test_an_accepted_revision_is_never_reflagged_by_a_coverage_edit(db, chain):
    """A human signed off on this revision. A later coverage change prunes the
    stale reason but must not silently expire that decision."""
    service = CertificateService(db)
    product = _product(db, chain, "RECOMP5")
    cert: Any = service.upsert_from_extraction(
        scheme=f"{MARKER}PPS",
        certificate_number="RECOMPUTE-5",
        attachment_id=_attachment(db, chain, "recompute5").id,
        valid_until=date(2029, 1, 1),
        product_ids=[product.id],
    )
    revision: Any = service.get_current_revision(cert)
    service.mark_revision_reviewed(
        revision.id, reviewed_by="00000000-0000-0000-0000-0000000000aa", commit=False
    )

    service.remove_coverage(cert.id, [product.id], commit=False)
    revision = service.get_current_revision(cert)
    assert revision.needs_review is False
    # The reason list still tells the truth about the current state.
    assert _reason_codes(revision) == {REVIEW_NO_COVERAGE}


def test_refresh_review_state_is_idempotent(db, chain):
    service = CertificateService(db)
    cert: Any = service.upsert_from_extraction(
        scheme=f"{MARKER}PPS",
        certificate_number="RECOMPUTE-6",
        attachment_id=_attachment(db, chain, "recompute6").id,
        valid_until=date(2029, 1, 1),
    )
    first: Any = service.refresh_review_state(cert)
    snapshot = (bool(first.needs_review), list(first.review_reasons or []))
    second: Any = service.refresh_review_state(cert)
    assert (bool(second.needs_review), list(second.review_reasons or [])) == snapshot


def test_refresh_review_state_is_a_noop_without_a_revision(db, chain):
    service = CertificateService(db)
    cert = Certificate(
        scheme=f"{MARKER}PPS",
        certificate_number="RECOMPUTE-7",
        certifying_body=f"{MARKER} body",
    )
    db.add(cert)
    db.flush()
    assert service.refresh_review_state(cert) is None
