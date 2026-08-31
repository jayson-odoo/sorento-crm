"""Certificate register service: identity, revisions, coverage and projection.

Four rules govern everything in this file.

**Identity includes the scheme.** ``04124FC`` exists under both ``PPS`` and
``SPAN`` with different expiries, so the upsert key is
``upper(regexp_replace(scheme || certificate_number, '[^A-Za-z0-9]', '', 'g'))``
within a company - the same expression as the unique index, so the probe uses it.

**Validity is derived, never stored.** ``derive_validity`` runs at read time off
the CURRENT revision only. A superseded revision's expired window never makes
the certificate read expired, and a NULL ``valid_until`` is ``unknown`` (flagged
for review and inert to every expiry reminder) - never "no expiry".

**Coverage belongs to the identity.** A renewal appends a revision and touches
zero ``certificate_products`` rows. The 68 links on ``PPS 04424FC`` survive every
renewal with no writes.

**This service is the only writer of the projection.** ``product_attachments``
rows for a cert-bearing attachment are derived from
``certificate_products`` x current revision. On renewal the projection re-points:
the superseded attachment's rows are HARD-deleted and the new attachment's are
inserted, so no consumer can be served the expired PDF. ``reconcile`` is the one
implementation, written JOIN-style as "set it to the correct value where it
differs" rather than "insert where missing", so it is safe to re-run.

Company scope is never filtered by hand here: ``app/services/company_scope.py``
injects the predicate into every ORM SELECT touching ``Certificate`` /
``Product`` / ``ProductAttachment`` and auto-stamps ``company_id`` on insert.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from typing import Any, Iterable, Optional, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.certificate import (
    CERTIFICATE_SOURCE_AI,
    CERTIFICATE_SOURCE_MANUAL,
    CERTIFICATE_SOURCES,
    CERTIFICATE_STATUS_ACTIVE,
    CERTIFICATE_STATUSES,
    Certificate,
    CertificateProduct,
    CertificateRevision,
)
from app.models.product import Product, ProductAttachment
from app.models.resources import Attachment, AttachmentType
from app.schemas.certificate import (
    CertificateCreate,
    CertificateProductResponse,
    CertificateResponse,
    CertificateRevisionResponse,
    CertificateUpdate,
)
from app.services.error_handler import (
    handle_not_found,
    handle_unprocessable,
    handle_validation_error,
)

logger = logging.getLogger(__name__)

_MY_TZ = ZoneInfo("Asia/Kuala_Lumpur")

# --- derived validity ---------------------------------------------------------
VALIDITY_VALID = "valid"
VALIDITY_EXPIRING_SOON = "expiring_soon"
VALIDITY_EXPIRED = "expired"
VALIDITY_NOT_YET_VALID = "not_yet_valid"
VALIDITY_UNKNOWN = "unknown"
VALIDITY_STATES = (
    VALIDITY_VALID,
    VALIDITY_EXPIRING_SOON,
    VALIDITY_EXPIRED,
    VALIDITY_NOT_YET_VALID,
    VALIDITY_UNKNOWN,
)

# How close to expiry counts as "expiring soon" in the derived state. The expiry
# REMINDERS are a separate, automation-configured 90/30/7 - this is only the
# window the list and the agent read as a warning.
EXPIRING_SOON_DAYS = 30

# --- needs_review reason codes (machine readable, never prose) ----------------
REVIEW_MISSING_FIELD = "missing_required_field"
REVIEW_UNMATCHED_PRODUCTS = "unmatched_products"
REVIEW_NO_COVERAGE = "no_product_coverage"
REVIEW_INVALID_DATE_ORDER = "valid_until_not_after_valid_from"
REVIEW_EXPIRED_AT_INGEST = "expired_at_ingest"
REVIEW_IMPLAUSIBLE_SPAN = "implausible_validity_span"
REVIEW_POSSIBLE_DUPLICATE = "possible_duplicate"
REVIEW_BACKFILLED_FROM_FILENAME = "backfilled_from_filename"

# The codes ``_evaluate_review`` decides for itself. A recompute may add or drop
# any of these. Anything else already stored on a revision - today
# ``backfilled_from_filename``, tomorrow any caller-supplied
# ``extra_review_reasons`` - is carried over untouched, because the evaluator has
# no way to re-derive it and dropping it would erase provenance.
EVALUATED_REVIEW_CODES = frozenset(
    {
        REVIEW_MISSING_FIELD,
        REVIEW_UNMATCHED_PRODUCTS,
        REVIEW_NO_COVERAGE,
        REVIEW_INVALID_DATE_ORDER,
        REVIEW_EXPIRED_AT_INGEST,
        REVIEW_IMPLAUSIBLE_SPAN,
        REVIEW_POSSIBLE_DUPLICATE,
    }
)

# Fields a cert-bearing extraction must produce. ``valid_from`` is deliberately
# NOT here: most certificate PDFs state only an expiry, so requiring it would
# flag nearly every genuine ingest and make the badge meaningless. A missing
# ``valid_until`` IS flagged - that is the one that makes the row reminder-inert.
REQUIRED_EXTRACTION_FIELDS = ("scheme", "certificate_number", "valid_until")

# --- near-match (duplicate suspicion) -----------------------------------------
# Trigram similarity above this, under the same (company, scheme), means "this
# might be an OCR-mangled renewal". It NEVER merges - it stamps a pointer and
# flags for review, because a wrong merge overwrites a real identity.
NEAR_MATCH_THRESHOLD = 0.55
NEAR_MATCH_LIMIT = 5

# pg_trgm's schema, resolved once per process. The blank-schema test fixture
# pins search_path to its scratch schema, which drops ``public`` - where the
# extension lives - so an unqualified ``similarity()`` would not resolve there.
_TRGM_SCHEMA: dict[str, Optional[str]] = {}


def today_malaysia() -> date:
    """Today in Asia/Kuala_Lumpur - the timezone every date in this system means."""
    return datetime.now(_MY_TZ).date()


def normalize_identity(scheme: Optional[str], certificate_number: Optional[str]) -> str:
    """The identity key: scheme + number, punctuation and case stripped.

    Python mirror of ``uq_certificates_company_scheme_number``. Keep the two in
    step: "PPS 0119", "PPS-0119" and "pps0119" are one certificate, and
    PPS/04124FC is not SPAN/04124FC.
    """
    raw = f"{(scheme or '').strip()}{(certificate_number or '').strip()}"
    return "".join(ch for ch in raw if ch.isalnum()).upper()


def derive_validity(
    valid_from: Optional[date],
    valid_until: Optional[date],
    *,
    today: Optional[date] = None,
    warn_days: int = EXPIRING_SOON_DAYS,
) -> tuple[str, bool, Optional[int]]:
    """Return ``(validity_state, is_expired, days_until_expiry)``.

    Computed, never stored. ``valid_until`` absent is ``unknown`` - a missing
    date is not "no expiry", and an unknown row is inert to expiry reminders.
    Expiry is evaluated BEFORE ``not_yet_valid`` so a nonsensical window (both
    dates in the wrong order, which is itself a review reason) can never present
    a past expiry as anything other than expired.
    """
    if valid_until is None:
        return VALIDITY_UNKNOWN, False, None

    today = today or today_malaysia()
    days = (valid_until - today).days
    if days < 0:
        return VALIDITY_EXPIRED, True, days
    if valid_from is not None and valid_from > today:
        return VALIDITY_NOT_YET_VALID, False, days
    if days <= warn_days:
        return VALIDITY_EXPIRING_SOON, False, days
    return VALIDITY_VALID, False, days


def _clean(value: Any) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _months_between(start: date, end: date) -> int:
    """Whole months from ``start`` to ``end``, rounding a part-month up."""
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day > start.day:
        months += 1
    return months


def _single_active_company(scope: Any) -> Optional[str]:
    """The one company a new row may be stamped with, or None.

    Only an unambiguous single-company scope counts; UNSET / all-companies /
    multi-company stay None rather than guess - a wrong guess is worse than a
    company-less (shared) row. Mirrors ``resources_service._single_active_company``;
    kept local rather than imported to avoid coupling the two service modules
    over a three-line helper.
    """
    if isinstance(scope, frozenset) and len(scope) == 1:
        return next(iter(scope))
    return None


class CertificateService:
    """Every write to the certificate register goes through here.

    ORM rows we mutate or read fields off are held in ``Any``-typed locals and
    parameters. The models declare plain ``Column(...)`` attributes, so a type
    checker sees ``Column[str]`` rather than ``str`` on every field; pinning the
    row to ``Any`` states that once, instead of scattering casts.
    """

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ reads
    def get_certificate(self, certificate_id: Any) -> Certificate:
        """Load one certificate or raise 404.

        Company scope is applied by the session listener, so a cross-company id
        is simply not found - 404, never 403-with-data.
        """
        cert = (
            self.db.query(Certificate)
            .filter(Certificate.id == str(certificate_id))
            .first()
        )
        if cert is None:
            raise handle_not_found("Certificate", str(certificate_id))
        return cert

    def find_by_identity(
        self, scheme: Any, certificate_number: Any
    ) -> Optional[Certificate]:
        """Exact identity match, using the same expression as the unique index."""
        key = normalize_identity(scheme, certificate_number)
        if not key:
            return None
        return (
            self.db.query(Certificate)
            .filter(self._identity_expression() == key)
            .first()
        )

    def find_by_revision_attachment(self, attachment_id: Any) -> tuple[Optional[Certificate], bool]:
        """The certificate this attachment is a revision of, and whether it is CURRENT.

        ``product_attachments`` rows for such an attachment are a projection of
        ``certificate_products`` x the current revision, so any surface that links
        or unlinks one by hand has to author coverage instead - otherwise the next
        ``reconcile`` sweeps its row away. Returns ``(None, False)`` for an
        ordinary attachment, which keeps the plain linking path untouched.
        """
        if not attachment_id:
            return None, False
        revision = (
            self.db.query(CertificateRevision)
            .filter(CertificateRevision.attachment_id == str(attachment_id))
            .order_by(CertificateRevision.is_current.desc(), CertificateRevision.id)
            .first()
        )
        if revision is None:
            return None, False
        cert = (
            self.db.query(Certificate)
            .filter(Certificate.id == revision.certificate_id)
            .first()
        )
        if cert is None:
            return None, False
        current = self.get_current_revision(cert)
        return cert, bool(current is not None and str(current.id) == str(revision.id))

    @staticmethod
    def _identity_expression():
        return func.upper(
            func.regexp_replace(
                Certificate.scheme + Certificate.certificate_number,
                "[^A-Za-z0-9]",
                "",
                "g",
            )
        )

    def _trgm_similarity(self, column, value: str):
        """``similarity(column, value)``, schema-qualified so it resolves under a
        pinned search_path. Returns None when pg_trgm is not installed."""
        if "schema" not in _TRGM_SCHEMA:
            try:
                _TRGM_SCHEMA["schema"] = self.db.execute(
                    text(
                        "SELECT n.nspname FROM pg_extension e "
                        "JOIN pg_namespace n ON n.oid = e.extnamespace "
                        "WHERE e.extname = 'pg_trgm'"
                    )
                ).scalar()
            except SQLAlchemyError:
                _TRGM_SCHEMA["schema"] = None
        schema = _TRGM_SCHEMA.get("schema")
        if not schema:
            return None
        return getattr(func, schema).similarity(column, value)

    def find_near_matches(
        self,
        scheme: Any,
        certificate_number: Any,
        *,
        threshold: float = NEAR_MATCH_THRESHOLD,
        exclude_id: Optional[str] = None,
    ) -> list[tuple[Certificate, float]]:
        """Trigram probe for an OCR-mangled version of this number.

        Scoped to the same scheme (and, by the session listener, the same
        company). Advisory: a hit never merges anything, and a database without
        pg_trgm degrades to "no suspicion" rather than breaking ingest.
        """
        scheme = _clean(scheme)
        number = _clean(certificate_number)
        if not scheme or not number:
            return []

        sim = self._trgm_similarity(Certificate.certificate_number, number)
        if sim is None:
            return []

        key = normalize_identity(scheme, number)
        try:
            query = (
                self.db.query(Certificate, sim.label("sim"))
                .filter(Certificate.scheme == scheme)
                .filter(self._identity_expression() != key)
                .filter(sim >= threshold)
            )
            if exclude_id:
                query = query.filter(Certificate.id != str(exclude_id))
            rows = query.order_by(sim.desc(), Certificate.certificate_number).limit(
                NEAR_MATCH_LIMIT
            ).all()
        except SQLAlchemyError as exc:  # pragma: no cover - defensive
            logger.warning("Certificate near-match probe failed: %s", exc, exc_info=True)
            return []
        return [(row[0], float(row[1] or 0)) for row in rows]

    def get_revisions(self, certificate_id: Any) -> list[CertificateRevision]:
        """Newest issue first - the order the timeline reads in."""
        return (
            self.db.query(CertificateRevision)
            .filter(CertificateRevision.certificate_id == str(certificate_id))
            .order_by(CertificateRevision.revision_no.desc())
            .all()
        )

    def get_current_revision(self, certificate: Any) -> Optional[CertificateRevision]:
        """The live revision. Reads ``current_revision_id`` and falls back to the
        ``is_current`` flag, so a half-written row still resolves."""
        if certificate.current_revision_id:
            row = (
                self.db.query(CertificateRevision)
                .filter(CertificateRevision.id == certificate.current_revision_id)
                .first()
            )
            if row is not None:
                return row
        return (
            self.db.query(CertificateRevision)
            .filter(
                CertificateRevision.certificate_id == certificate.id,
                CertificateRevision.is_current.is_(True),
            )
            .first()
        )

    def get_coverage(self, certificate_id: Any) -> list[CertificateProduct]:
        return (
            self.db.query(CertificateProduct)
            .filter(CertificateProduct.certificate_id == str(certificate_id))
            .all()
        )

    # ------------------------------------------------------------- write: CRUD
    def create_certificate(
        self,
        payload: CertificateCreate,
        *,
        created_by: Optional[str] = None,
        commit: bool = True,
    ) -> Certificate:
        """Manual create. Files revision 1 when any revision field is supplied."""
        scheme = _clean(payload.scheme)
        number = _clean(payload.certificate_number)
        if not scheme or not number:
            raise handle_validation_error(
                "A certificate needs both a scheme and a certificate number."
            )
        if self.find_by_identity(scheme, number) is not None:
            raise handle_validation_error(
                f"Certificate {scheme} {number} already exists. "
                "File the new document as a revision of it instead."
            )

        # DUP-1/DUP-2 apply to the manual path too, not just to extraction. A human
        # typing "04124FG" for "04124FC" forks a certificate exactly the way OCR does,
        # and the forked row then counts down its own expiry while the real one keeps
        # nagging. Flag it and let a person decide; never auto-merge.
        near = self.find_near_matches(scheme, number)
        duplicate_of = near[0][0] if near else None

        cert: Any = self._new_certificate(
            scheme=scheme,
            certificate_number=number,
            certifying_body=_clean(payload.certifying_body),
            issuer=_clean(payload.issuer),
            title=_clean(payload.title),
            attachment_type_id=_clean(payload.attachment_type_id),
            status=payload.status or CERTIFICATE_STATUS_ACTIVE,
            created_by=created_by,
            company_id=self._resolve_new_certificate_company_id(_clean(payload.attachment_id)),
            possible_duplicate_of_certificate_id=(
                str(duplicate_of.id) if duplicate_of is not None else None
            ),
        )

        product_ids = list(payload.product_ids or [])
        if product_ids:
            self._apply_coverage(
                cert, product_ids, source=payload.source, created_by=created_by
            )

        has_revision_input = any(
            v is not None
            for v in (
                payload.attachment_id,
                payload.issued_at,
                payload.valid_from,
                payload.valid_until,
            )
        )
        if has_revision_input:
            needs_review, reasons = self._evaluate_review(
                scheme=scheme,
                certificate_number=number,
                valid_from=payload.valid_from,
                valid_until=payload.valid_until,
                issued_at=payload.issued_at,
                unmatched_products=[],
                attachment_type_id=_clean(payload.attachment_type_id),
                covered_count=len(product_ids),
            )
            self._append_revision(
                cert,
                attachment_id=_clean(payload.attachment_id),
                issued_at=payload.issued_at,
                valid_from=payload.valid_from,
                valid_until=payload.valid_until,
                source=payload.source,
                needs_review=needs_review,
                review_reasons=reasons,
                unmatched_products=[],
                extracted_json=None,
                created_by=created_by,
            )

        self.reconcile_certificate(cert)
        self._finish(commit)
        return cert

    def update_certificate(
        self,
        certificate_id: str,
        payload: CertificateUpdate,
        *,
        commit: bool = True,
    ) -> Certificate:
        """Identity and lifecycle edit. Dates and coverage have their own paths."""
        cert: Any = self.get_certificate(certificate_id)
        data = payload.model_dump(exclude_unset=True)

        scheme = _clean(data.get("scheme")) or cert.scheme
        number = _clean(data.get("certificate_number")) or cert.certificate_number
        if normalize_identity(scheme, number) != normalize_identity(
            cert.scheme, cert.certificate_number
        ):
            clash = self.find_by_identity(scheme, number)
            if clash is not None and str(clash.id) != str(cert.id):
                raise handle_validation_error(
                    f"Certificate {scheme} {number} already exists."
                )

        for field in (
            "scheme",
            "certificate_number",
            "certifying_body",
            "issuer",
            "title",
            "attachment_type_id",
            "status",
        ):
            if field in data:
                value = data[field]
                setattr(cert, field, _clean(value) if isinstance(value, str) else value)
        if cert.status not in CERTIFICATE_STATUSES:
            raise handle_validation_error(
                f"status must be one of {', '.join(CERTIFICATE_STATUSES)}."
            )

        self.db.flush()
        # scheme, certificate_number and attachment_type_id are all inputs to the
        # review rules (required fields, and the plausible-span ceiling), so an
        # identity edit has to re-run them or the flag describes the old values.
        self.refresh_review_state(cert)
        self._finish(commit)
        return cert

    def delete_certificate(self, certificate_id: str, *, commit: bool = True) -> None:
        """Hard delete: revisions, coverage and projection go; the attachments stay.

        Children first, exactly like the FK order - the ``current_revision_id``
        pointer is cleared before its target is removed.
        """
        cert: Any = self.get_certificate(certificate_id)
        attachment_ids = self._revision_attachment_ids(cert)
        if attachment_ids:
            self._delete_projection_rows(attachment_ids)

        cert.current_revision_id = None
        self.db.flush()
        self.db.query(CertificateProduct).filter(
            CertificateProduct.certificate_id == cert.id
        ).delete(synchronize_session=False)
        self.db.query(CertificateRevision).filter(
            CertificateRevision.certificate_id == cert.id
        ).delete(synchronize_session=False)
        # Anything that suspected this row as its original loses the pointer
        # rather than a dangling id.
        self.db.query(Certificate).filter(
            Certificate.possible_duplicate_of_certificate_id == cert.id
        ).update({"possible_duplicate_of_certificate_id": None}, synchronize_session="fetch")
        self.db.delete(cert)
        self._finish(commit)

    # -------------------------------------------------------- write: ingest
    def upsert_from_extraction(
        self,
        *,
        scheme: Optional[str],
        certificate_number: Optional[str],
        attachment_id: Optional[str] = None,
        attachment_type_id: Optional[str] = None,
        certifying_body: Optional[str] = None,
        issuer: Optional[str] = None,
        title: Optional[str] = None,
        issued_at: Optional[date] = None,
        valid_from: Optional[date] = None,
        valid_until: Optional[date] = None,
        product_ids: Optional[Sequence[str]] = None,
        unmatched_products: Optional[Sequence[str]] = None,
        extracted_json: Optional[dict] = None,
        source: str = CERTIFICATE_SOURCE_AI,
        created_by: Optional[str] = None,
        extra_review_reasons: Optional[Sequence[dict]] = None,
        commit: bool = True,
    ) -> Certificate:
        """File an extracted certificate: upsert the identity, append a revision.

        Exact identity match -> a REVISION is appended and coverage is left
        completely alone (a renewal must not re-derive 68 product links from one
        PDF's text). No match -> the certificate is created, coverage recorded,
        and a trigram near-match - if any - stamped as a suspicion, never merged.

        Two markers ride home on the returned object for the caller's log line:
        ``_certificate_created`` and ``_revision_no``. They die on re-query, so
        read them before calling ``get_certificate`` again.
        """
        scheme = _clean(scheme)
        number = _clean(certificate_number)
        if not scheme or not number:
            raise handle_validation_error(
                "A certificate needs both a scheme and a certificate number."
            )
        if source not in CERTIFICATE_SOURCES:
            raise handle_validation_error(
                f"source must be one of {', '.join(CERTIFICATE_SOURCES)}."
            )

        attachment_id = _clean(attachment_id)
        attachment_type_id = _clean(attachment_type_id) or self._attachment_type_of(
            attachment_id
        )
        unmatched = [str(x).strip() for x in (unmatched_products or []) if str(x).strip()]

        cert: Any = self.find_by_identity(scheme, number)
        created = cert is None
        duplicate_of = None

        if created:
            near = self.find_near_matches(scheme, number)
            duplicate_of = near[0][0] if near else None
            cert = self._new_certificate(
                scheme=scheme,
                certificate_number=number,
                certifying_body=_clean(certifying_body),
                issuer=_clean(issuer),
                title=_clean(title),
                attachment_type_id=attachment_type_id,
                status=CERTIFICATE_STATUS_ACTIVE,
                created_by=created_by,
                # The certificate follows the FILING attachment's company (S6,
                # R5) - a shared file (company_id NULL) makes a shared
                # certificate, not one guessed from the caller's own scope
                # (which is `None`/all-companies for the n8n path here).
                company_id=self._resolve_new_certificate_company_id(attachment_id),
                possible_duplicate_of_certificate_id=(
                    str(duplicate_of.id) if duplicate_of is not None else None
                ),
            )
            # Resolved through the scoped Product query, so a product in another
            # company is never linked - it simply does not resolve.
            resolved = self._resolve_product_ids(product_ids or [])
            if resolved:
                self._apply_coverage(
                    cert, resolved, source=source, created_by=created_by
                )
        else:
            # Renewal. Fill identity blanks only - never overwrite a value a
            # human may have corrected, and never touch coverage (the whole
            # point of hanging coverage off the identity).
            for field, value in (
                ("certifying_body", _clean(certifying_body)),
                ("issuer", _clean(issuer)),
                ("title", _clean(title)),
                ("attachment_type_id", attachment_type_id),
            ):
                if value and not getattr(cert, field, None):
                    setattr(cert, field, value)

        covered_count = self.count_coverage(cert.id)
        needs_review, reasons = self._evaluate_review(
            scheme=scheme,
            certificate_number=number,
            valid_from=valid_from,
            valid_until=valid_until,
            issued_at=issued_at,
            unmatched_products=unmatched,
            attachment_type_id=attachment_type_id,
            covered_count=covered_count,
            duplicate_of=duplicate_of,
        )
        if extra_review_reasons:
            reasons.extend(dict(r) for r in extra_review_reasons)
            needs_review = True

        revision = self._upsert_revision(
            cert,
            attachment_id=attachment_id,
            issued_at=issued_at,
            valid_from=valid_from,
            valid_until=valid_until,
            source=source,
            needs_review=needs_review,
            review_reasons=reasons,
            unmatched_products=unmatched,
            extracted_json=extracted_json,
            created_by=created_by,
        )

        self.reconcile_certificate(cert)
        self._finish(commit)
        cert._certificate_created = created
        cert._revision_no = revision.revision_no
        return cert

    def add_revision(
        self,
        certificate_id: str,
        *,
        attachment_id: Optional[str] = None,
        issued_at: Optional[date] = None,
        valid_from: Optional[date] = None,
        valid_until: Optional[date] = None,
        source: str = CERTIFICATE_SOURCE_MANUAL,
        created_by: Optional[str] = None,
        commit: bool = True,
    ) -> CertificateRevision:
        """File a renewal by hand. Coverage is untouched, same as an AI renewal."""
        cert: Any = self.get_certificate(certificate_id)
        needs_review, reasons = self._evaluate_review(
            scheme=cert.scheme,
            certificate_number=cert.certificate_number,
            valid_from=valid_from,
            valid_until=valid_until,
            issued_at=issued_at,
            unmatched_products=[],
            attachment_type_id=cert.attachment_type_id,
            covered_count=self.count_coverage(cert.id),
        )
        revision = self._append_revision(
            cert,
            attachment_id=_clean(attachment_id),
            issued_at=issued_at,
            valid_from=valid_from,
            valid_until=valid_until,
            source=source,
            needs_review=needs_review,
            review_reasons=reasons,
            unmatched_products=[],
            extracted_json=None,
            created_by=created_by,
        )
        self.reconcile_certificate(cert)
        self._finish(commit)
        return revision

    def update_revision(
        self,
        revision_id: str,
        *,
        issued_at: Optional[date] = None,
        valid_from: Optional[date] = None,
        valid_until: Optional[date] = None,
        attachment_id: Optional[str] = None,
        fields_set: Optional[Iterable[str]] = None,
        reviewed_by: Optional[str] = None,
        commit: bool = True,
    ) -> CertificateRevision:
        """Human correction of a filed revision.

        Re-runs the review rules afterwards: the flag clears only when a real
        reviewer is supplied AND nothing is left to complain about. It never
        clears itself.
        """
        revision: Any = self._get_revision(revision_id)
        cert: Any = self.get_certificate(revision.certificate_id)
        touched = set(fields_set or ("issued_at", "valid_from", "valid_until", "attachment_id"))
        if "issued_at" in touched:
            revision.issued_at = issued_at
        if "valid_from" in touched:
            revision.valid_from = valid_from
        if "valid_until" in touched:
            revision.valid_until = valid_until
        if "attachment_id" in touched:
            revision.attachment_id = _clean(attachment_id)

        needs_review, reasons = self._evaluate_review(
            scheme=cert.scheme,
            certificate_number=cert.certificate_number,
            valid_from=revision.valid_from,
            valid_until=revision.valid_until,
            issued_at=revision.issued_at,
            unmatched_products=list(revision.unmatched_products or []),
            attachment_type_id=cert.attachment_type_id,
            covered_count=self.count_coverage(cert.id),
        )
        revision.review_reasons = reasons
        if needs_review:
            revision.needs_review = True
        elif reviewed_by:
            revision.needs_review = False
            revision.reviewed_at = datetime.utcnow()
            revision.reviewed_by = str(reviewed_by)
        self.db.flush()

        if bool(revision.is_current):
            self.reconcile_certificate(cert)
        self._finish(commit)
        return revision

    def mark_revision_reviewed(
        self, revision_id: str, *, reviewed_by: str, commit: bool = True
    ) -> CertificateRevision:
        """Accept a flagged revision as-is. Requires a real reviewer."""
        if not reviewed_by:
            raise handle_validation_error("A reviewer is required to clear the review flag.")
        revision: Any = self._get_revision(revision_id)
        revision.needs_review = False
        revision.reviewed_at = datetime.utcnow()
        revision.reviewed_by = str(reviewed_by)
        self.db.flush()
        self._finish(commit)
        return revision

    # ------------------------------------------------------- write: coverage
    def set_coverage(
        self,
        certificate_id: str,
        product_ids: Sequence[str],
        *,
        source: str = CERTIFICATE_SOURCE_MANUAL,
        created_by: Optional[str] = None,
        commit: bool = True,
    ) -> list[CertificateProduct]:
        """Replace coverage with exactly ``product_ids``.

        Rows already present keep their own ``source`` - re-saving a list must
        not relabel an AI-inferred link as human-confirmed.
        """
        cert: Any = self.get_certificate(certificate_id)
        wanted = self._resolve_product_ids(product_ids)
        existing = {str(row.product_id): row for row in self.get_coverage(cert.id)}

        for product_id, row in existing.items():
            if product_id not in wanted:
                self.db.delete(row)
        self.db.flush()
        self._apply_coverage(
            cert,
            [pid for pid in wanted if pid not in existing],
            source=source,
            created_by=created_by,
        )
        self.reconcile_certificate(cert)
        self.refresh_review_state(cert)
        self._finish(commit)
        return self.get_coverage(cert.id)

    def add_coverage(
        self,
        certificate_id: str,
        product_ids: Sequence[str],
        *,
        source: str = CERTIFICATE_SOURCE_MANUAL,
        created_by: Optional[str] = None,
        commit: bool = True,
    ) -> list[CertificateProduct]:
        """Cover more products. Inserts the projection row for the current
        revision's attachment, inheriting that attachment's access levels."""
        cert: Any = self.get_certificate(certificate_id)
        wanted = self._resolve_product_ids(product_ids)
        self._apply_coverage(cert, list(wanted), source=source, created_by=created_by)
        self.reconcile_certificate(cert)
        self.refresh_review_state(cert)
        self._finish(commit)
        return self.get_coverage(cert.id)

    def remove_coverage(
        self,
        certificate_id: str,
        product_ids: Sequence[str],
        *,
        commit: bool = True,
    ) -> list[CertificateProduct]:
        """Uncover products. The projection rows are hard-deleted with them."""
        cert: Any = self.get_certificate(certificate_id)
        ids = [str(pid) for pid in product_ids if pid]
        if ids:
            self.db.query(CertificateProduct).filter(
                CertificateProduct.certificate_id == cert.id,
                CertificateProduct.product_id.in_(ids),
            ).delete(synchronize_session="fetch")
            self.db.flush()
        self.reconcile_certificate(cert)
        self.refresh_review_state(cert)
        self._finish(commit)
        return self.get_coverage(cert.id)

    def refresh_review_state(self, certificate: Any) -> Optional[CertificateRevision]:
        """Recompute the CURRENT revision's review flags from live state.

        The flags are stored, not derived on read, so anything that changes an
        input to ``_evaluate_review`` has to re-run it. Coverage is the input
        that moves most: without this, adding the products a certificate covers
        left ``no_product_coverage`` on the row forever, and the detail page
        kept saying "No product is covered by this certificate" after the user
        had fixed exactly that.

        A revision a PERSON already accepted (``mark_revision_reviewed`` stamps
        ``reviewed_at``) is never re-flagged behind their back: its reason list
        is still pruned so it cannot show a stale complaint, but ``needs_review``
        stays False. Re-raising it would mean a human decision silently expires
        the moment anyone touches coverage.

        Idempotent: it computes the correct value and assigns it, so a second
        call is a no-op.
        """
        current = self.get_current_revision(certificate)
        if current is None:
            return None

        duplicate = None
        duplicate_id = getattr(certificate, "possible_duplicate_of_certificate_id", None)
        if duplicate_id:
            duplicate = (
                self.db.query(Certificate)
                .filter(Certificate.id == str(duplicate_id))
                .first()
            )

        needs_review, reasons = self._evaluate_review(
            scheme=certificate.scheme,
            certificate_number=certificate.certificate_number,
            valid_from=current.valid_from,
            valid_until=current.valid_until,
            unmatched_products=list(current.unmatched_products or []),
            attachment_type_id=certificate.attachment_type_id,
            covered_count=self.count_coverage(certificate.id),
            issued_at=current.issued_at,
            duplicate_of=duplicate,
        )

        current.review_reasons = reasons
        # reviewed_at is the human's signature on this revision; only an
        # unreviewed revision follows the computed flag.
        current.needs_review = False if current.reviewed_at is not None else needs_review
        self.db.flush()
        return current

    def count_coverage(self, certificate_id: Any) -> int:
        return (
            self.db.query(func.count(CertificateProduct.id))
            .filter(CertificateProduct.certificate_id == str(certificate_id))
            .scalar()
            or 0
        )

    # ----------------------------------------------------- write: projection
    def reconcile(self, certificate_id: str, *, commit: bool = True) -> dict:
        """Public reconciler: bring ``product_attachments`` back into agreement.

        Idempotent by construction - it computes the correct set and makes the
        table equal it, so a second run is a no-op and a partial earlier run is
        corrected rather than compounded.
        """
        cert: Any = self.get_certificate(certificate_id)
        result = self.reconcile_certificate(cert)
        self._finish(commit)
        return result

    def reconcile_certificate(self, certificate: Any) -> dict:
        """The single projection writer. Returns per-action counters."""
        counters = {"inserted": 0, "updated": 0, "deleted": 0}
        current = self.get_current_revision(certificate)
        current_attachment_id = (
            str(current.attachment_id)
            if current is not None and current.attachment_id is not None
            else None
        )

        # 1. Superseded revisions' attachments must serve nothing (REV-3).
        stale = self._revision_attachment_ids(certificate) - {current_attachment_id}
        if stale:
            counters["deleted"] += self._delete_projection_rows(stale)

        if current_attachment_id is None:
            return counters

        attachment: Any = (
            self.db.query(Attachment)
            .filter(Attachment.id == current_attachment_id)
            .first()
        )
        if attachment is None:
            return counters

        wanted = {str(row.product_id) for row in self.get_coverage(certificate.id)}
        access_levels = list(attachment.access_levels or [])
        rows: list[Any] = (
            self.db.query(ProductAttachment)
            .filter(ProductAttachment.attachment_id == current_attachment_id)
            .all()
        )
        seen: set[str] = set()
        for row in rows:
            product_id = str(row.product_id)
            if product_id not in wanted:
                self.db.delete(row)
                counters["deleted"] += 1
                continue
            seen.add(product_id)
            # Set it to the correct value where it differs - not "insert where
            # missing", so a drifted access level is repaired on re-run.
            if list(row.access_levels or []) != access_levels:
                row.access_levels = access_levels
                counters["updated"] += 1

        missing = sorted(wanted - seen)
        # Stamp from the COVERED PRODUCT's own company, not the certificate's:
        # a shared certificate (company_id NULL) covers twins in DIFFERENT
        # companies, so there is no one company to fall back to, and leaning on
        # the session scope would auto-stamp every row into the incumbent
        # company when this runs under company_scope(db, None) (the
        # bulk-company follow hook's widened scope, S6) - the same latent bug
        # S2 fixed for the twin linker. Gives an identical result for a
        # single-company certificate, since its wanted products are all in
        # that one company anyway.
        product_company_ids: dict[str, str] = {}
        if missing:
            product_company_ids = {
                str(pid): str(cid)
                for pid, cid in self.db.query(Product.id, Product.company_id)
                .filter(Product.id.in_(missing))
                .all()
                if cid is not None
            }
        for product_id in missing:
            row = ProductAttachment(
                id=str(uuid.uuid4()),
                product_id=product_id,
                attachment_id=current_attachment_id,
                access_levels=access_levels,
                created_by=certificate.created_by,
            )
            stamp = product_company_ids.get(product_id) or certificate.company_id
            if stamp is not None:
                row.company_id = stamp
            self.db.add(row)
            counters["inserted"] += 1

        self.db.flush()
        return counters

    # ---------------------------------------------------------- write: merge
    def merge_into(
        self, source_id: str, target_id: str, *, commit: bool = True
    ) -> Certificate:
        """Fold ``source`` into ``target`` and hard-delete the emptied source.

        Only ever called by a human who decided the near-match flag was right.
        Revisions are renumbered from the target's max, coverage is unioned with
        each row's ``source`` preserved, and the projection is re-pointed at
        whichever revision ends up current.
        """
        if str(source_id) == str(target_id):
            raise handle_unprocessable("A certificate cannot be merged into itself.")
        source: Any = self.get_certificate(source_id)
        target: Any = self.get_certificate(target_id)
        if str(source.company_id or "") != str(target.company_id or ""):
            raise handle_unprocessable(
                "These certificates belong to different companies and cannot be merged."
            )

        source_revisions: list[Any] = (
            self.db.query(CertificateRevision)
            .filter(CertificateRevision.certificate_id == source.id)
            .order_by(CertificateRevision.revision_no)
            .all()
        )
        target_max = (
            self.db.query(func.coalesce(func.max(CertificateRevision.revision_no), 0))
            .filter(CertificateRevision.certificate_id == target.id)
            .scalar()
            or 0
        )

        # Clear every current flag first: the partial unique index allows only
        # one, and the winner is decided after the move.
        source.current_revision_id = None
        target.current_revision_id = None
        self.db.flush()
        self.db.query(CertificateRevision).filter(
            CertificateRevision.certificate_id.in_([source.id, target.id]),
            CertificateRevision.is_current.is_(True),
        ).update({"is_current": False}, synchronize_session="fetch")
        self.db.flush()

        for offset, revision in enumerate(source_revisions, start=1):
            revision.certificate_id = target.id
            revision.revision_no = target_max + offset
        self.db.flush()

        # The highest revision number is the last document filed, so it is the
        # one that is live after the merge.
        winner: Any = (
            self.db.query(CertificateRevision)
            .filter(CertificateRevision.certificate_id == target.id)
            .order_by(CertificateRevision.revision_no.desc())
            .first()
        )
        if winner is not None:
            winner.is_current = True
            self.db.flush()
            target.current_revision_id = winner.id

        target_products = {
            str(row.product_id) for row in self.get_coverage(target.id)
        }
        for row in self.get_coverage(source.id):
            if str(row.product_id) in target_products:
                self.db.delete(row)  # target's row wins, keeping its own source
            else:
                row.certificate_id = target.id
        self.db.flush()

        self.db.query(Certificate).filter(
            Certificate.possible_duplicate_of_certificate_id == source.id
        ).update(
            {"possible_duplicate_of_certificate_id": target.id},
            synchronize_session="fetch",
        )
        if str(target.possible_duplicate_of_certificate_id or "") == str(source.id):
            target.possible_duplicate_of_certificate_id = None
        self.db.flush()

        self.db.delete(source)
        self.db.flush()
        self.reconcile_certificate(target)
        self._finish(commit)
        return target

    # ------------------------------------------------------------ serializing
    def serialize(
        self,
        certificate: Any,
        *,
        expand: bool = False,
        today: Optional[date] = None,
    ) -> CertificateResponse:
        return self.serialize_many([certificate], expand=expand, today=today)[0]

    def serialize_many(
        self,
        certificates: Sequence[Any],
        *,
        expand: bool = False,
        today: Optional[date] = None,
    ) -> list[CertificateResponse]:
        """Serialize with derived validity, in a fixed number of queries."""
        certificates = list(certificates)
        if not certificates:
            return []
        today = today or today_malaysia()
        ids = [str(c.id) for c in certificates]

        counts = {
            str(certificate_id): int(total)
            for certificate_id, total in self.db.query(
                CertificateProduct.certificate_id, func.count(CertificateProduct.id)
            )
            .filter(CertificateProduct.certificate_id.in_(ids))
            .group_by(CertificateProduct.certificate_id)
            .all()
        }
        revisions: dict[str, list[Any]] = {}
        for revision in (
            self.db.query(CertificateRevision)
            .filter(CertificateRevision.certificate_id.in_(ids))
            .order_by(CertificateRevision.revision_no.desc())
            .all()
        ):
            revisions.setdefault(str(revision.certificate_id), []).append(revision)

        attachment_ids = {
            str(r.attachment_id)
            for rows in revisions.values()
            for r in rows
            if r.attachment_id
        }
        attachments: dict[str, Any] = {
            str(a.id): a
            for a in (
                self.db.query(Attachment).filter(Attachment.id.in_(attachment_ids)).all()
                if attachment_ids
                else []
            )
        }

        out: list[CertificateResponse] = []
        for cert in certificates:
            cert_revisions = revisions.get(str(cert.id), [])
            current = next(
                (r for r in cert_revisions if str(r.id) == str(cert.current_revision_id)),
                None,
            ) or next((r for r in cert_revisions if bool(r.is_current)), None)
            state, is_expired, days = derive_validity(
                current.valid_from if current else None,
                current.valid_until if current else None,
                today=today,
            )
            duplicate_label = None
            if cert.possible_duplicate_of_certificate_id:
                other: Any = (
                    self.db.query(Certificate)
                    .filter(Certificate.id == cert.possible_duplicate_of_certificate_id)
                    .first()
                )
                if other is not None:
                    duplicate_label = f"{other.scheme} {other.certificate_number}"

            out.append(
                CertificateResponse(
                    id=str(cert.id),
                    scheme=cert.scheme,
                    certificate_number=cert.certificate_number,
                    certifying_body=cert.certifying_body,
                    issuer=cert.issuer,
                    title=cert.title,
                    status=cert.status,
                    attachment_type_id=(
                        str(cert.attachment_type_id) if cert.attachment_type_id else None
                    ),
                    attachment_type_name=(
                        cert.attachment_type.type_name if cert.attachment_type else None
                    ),
                    possible_duplicate_of_certificate_id=(
                        str(cert.possible_duplicate_of_certificate_id)
                        if cert.possible_duplicate_of_certificate_id
                        else None
                    ),
                    possible_duplicate_of_label=duplicate_label,
                    expiry_notified_at=cert.expiry_notified_at,
                    expiry_notify_batch_id=(
                        str(cert.expiry_notify_batch_id)
                        if cert.expiry_notify_batch_id
                        else None
                    ),
                    created_at=cert.created_at,
                    updated_at=cert.updated_at,
                    created_by=str(cert.created_by) if cert.created_by else None,
                    current_revision_id=str(current.id) if current else None,
                    revision_no=current.revision_no if current else None,
                    issued_at=current.issued_at if current else None,
                    valid_from=current.valid_from if current else None,
                    valid_until=current.valid_until if current else None,
                    # No current revision means no expiry on file at all, which is a
                    # review case, not a clean one. Kept in step with the same default
                    # in CertificateQueryService's needs_review filter - if these two
                    # disagree, the flag and the filter show different rows.
                    needs_review=bool(current.needs_review) if current else True,
                    review_reasons=(
                        list(current.review_reasons or [])
                        if current
                        else [{"code": "no_revision_on_file"}]
                    ),
                    unmatched_products=(
                        list(current.unmatched_products or []) if current else []
                    ),
                    validity_state=state,
                    is_expired=is_expired,
                    days_until_expiry=days,
                    covered_product_count=int(counts.get(str(cert.id), 0)),
                    revisions=(
                        [
                            self.serialize_revision(r, attachments.get(str(r.attachment_id)))
                            for r in cert_revisions
                        ]
                        if expand
                        else None
                    ),
                    covered_products=(
                        self.serialize_coverage(str(cert.id)) if expand else None
                    ),
                )
            )
        return out

    def serialize_revision(
        self,
        revision: Any,
        attachment: Any = None,
    ) -> CertificateRevisionResponse:
        if attachment is None and revision.attachment_id:
            attachment = (
                self.db.query(Attachment)
                .filter(Attachment.id == revision.attachment_id)
                .first()
            )
        return CertificateRevisionResponse(
            id=str(revision.id),
            certificate_id=str(revision.certificate_id),
            revision_no=revision.revision_no,
            attachment_id=str(revision.attachment_id) if revision.attachment_id else None,
            attachment_filename=(
                attachment.stored_filename or attachment.original_filename
                if attachment is not None
                else None
            ),
            attachment_is_deleted=bool(attachment.is_deleted) if attachment is not None else False,
            access_levels=list(attachment.access_levels or []) if attachment is not None else None,
            issued_at=revision.issued_at,
            valid_from=revision.valid_from,
            valid_until=revision.valid_until,
            is_current=bool(revision.is_current),
            source=revision.source,
            needs_review=bool(revision.needs_review),
            review_reasons=list(revision.review_reasons or []),
            unmatched_products=list(revision.unmatched_products or []),
            extracted_json=revision.extracted_json,
            reviewed_at=revision.reviewed_at,
            reviewed_by=str(revision.reviewed_by) if revision.reviewed_by else None,
            created_at=revision.created_at,
            created_by=str(revision.created_by) if revision.created_by else None,
        )

    def serialize_coverage(self, certificate_id: Any) -> list[CertificateProductResponse]:
        rows: list[Any] = (
            self.db.query(CertificateProduct, Product)
            .outerjoin(Product, Product.id == CertificateProduct.product_id)
            .filter(CertificateProduct.certificate_id == str(certificate_id))
            .order_by(Product.product_code)
            .all()
        )
        return [
            CertificateProductResponse(
                id=str(coverage.id),
                certificate_id=str(coverage.certificate_id),
                product_id=str(coverage.product_id),
                product_code=product.product_code if product is not None else None,
                product_name=product.product_name if product is not None else None,
                source=coverage.source,
                created_at=coverage.created_at,
                created_by=str(coverage.created_by) if coverage.created_by else None,
            )
            for coverage, product in rows
        ]

    # ------------------------------------------------------------- internals
    def _finish(self, commit: bool) -> None:
        if commit:
            self.db.commit()
        else:
            self.db.flush()

    def _new_certificate(
        self,
        *,
        scheme: str,
        certificate_number: str,
        certifying_body: Optional[str],
        issuer: Optional[str],
        title: Optional[str],
        attachment_type_id: Optional[str],
        status: str,
        created_by: Optional[str],
        company_id: Optional[str],
        possible_duplicate_of_certificate_id: Optional[str] = None,
    ) -> Certificate:
        if status not in CERTIFICATE_STATUSES:
            raise handle_validation_error(
                f"status must be one of {', '.join(CERTIFICATE_STATUSES)}."
            )
        cert = Certificate(
            id=str(uuid.uuid4()),
            scheme=scheme,
            certificate_number=certificate_number,
            certifying_body=certifying_body,
            issuer=issuer,
            title=title,
            attachment_type_id=attachment_type_id,
            status=status,
            possible_duplicate_of_certificate_id=possible_duplicate_of_certificate_id,
            created_by=str(created_by) if created_by else None,
            # Explicit - Certificate is __company_shared__, so the before_insert
            # auto-stamp leaves this untouched (see _resolve_new_certificate_company_id).
            company_id=company_id,
        )
        self.db.add(cert)
        self.db.flush()
        return cert

    def _get_revision(self, revision_id: Any) -> CertificateRevision:
        revision: Any = (
            self.db.query(CertificateRevision)
            .filter(CertificateRevision.id == str(revision_id))
            .first()
        )
        if revision is None:
            raise handle_not_found("Certificate revision", str(revision_id))
        # Reached through its certificate so the company scope still applies.
        self.get_certificate(revision.certificate_id)
        return revision

    def _upsert_revision(
        self,
        certificate: Any,
        *,
        attachment_id: Optional[str],
        issued_at: Optional[date],
        valid_from: Optional[date],
        valid_until: Optional[date],
        source: str,
        needs_review: bool,
        review_reasons: list[dict],
        unmatched_products: list[str],
        extracted_json: Optional[dict],
        created_by: Optional[str],
    ) -> CertificateRevision:
        """Append a revision only for a genuinely NEW issue; otherwise update.

        A revision represents an issued document, and an issued document is
        defined by the window it is valid for - not by which upload row happens
        to carry the PDF. So a new revision is appended ONLY when both the
        validity window AND the file differ from the current revision:

          * resubmit (same file, same window)      -> update. n8n retries, and a
            person can re-send an attachment; neither is a renewal.
          * replace / copy (new file, same window) -> update, re-pointed at the
            new file. Same document, new upload row.
          * correction (same file, new window)     -> update. The reader changed
            its mind about ONE document.
          * renewal (new file, new window)         -> APPEND.

        Without this, every resubmission stacked a byte-identical revision and
        the timeline claimed renewals that never happened.
        """
        current: Any = self.get_current_revision(certificate)
        if current is not None:
            same_window = (
                current.issued_at == issued_at
                and current.valid_from == valid_from
                and current.valid_until == valid_until
            )
            incoming_attachment = _clean(attachment_id)
            current_attachment = (
                str(current.attachment_id) if current.attachment_id else None
            )
            same_file = current_attachment == incoming_attachment
            if same_window or same_file:
                previous_attachment = current_attachment
                current.attachment_id = incoming_attachment
                current.issued_at = issued_at
                current.valid_from = valid_from
                current.valid_until = valid_until
                current.source = source
                current.needs_review = needs_review
                current.review_reasons = review_reasons
                current.unmatched_products = unmatched_products
                if extracted_json is not None:
                    current.extracted_json = extracted_json
                self.db.flush()
                # reconcile only sweeps attachments still referenced by a
                # revision, so the file we just un-referenced has to be cleaned
                # up here or its rows keep serving on the product pages.
                if previous_attachment and previous_attachment != incoming_attachment:
                    self._delete_projection_rows([previous_attachment])
                return current

        return self._append_revision(
            certificate,
            attachment_id=attachment_id,
            issued_at=issued_at,
            valid_from=valid_from,
            valid_until=valid_until,
            source=source,
            needs_review=needs_review,
            review_reasons=review_reasons,
            unmatched_products=unmatched_products,
            extracted_json=extracted_json,
            created_by=created_by,
        )

    def _append_revision(
        self,
        certificate: Any,
        *,
        attachment_id: Optional[str],
        issued_at: Optional[date],
        valid_from: Optional[date],
        valid_until: Optional[date],
        source: str,
        needs_review: bool,
        review_reasons: list[dict],
        unmatched_products: list[str],
        extracted_json: Optional[dict],
        created_by: Optional[str],
    ) -> CertificateRevision:
        """Append revision max+1 as the current one and demote the incumbent."""
        next_no = (
            self.db.query(func.coalesce(func.max(CertificateRevision.revision_no), 0))
            .filter(CertificateRevision.certificate_id == certificate.id)
            .scalar()
            or 0
        ) + 1

        # Demote before inserting: uq_certificate_revisions_one_current allows
        # exactly one current row per certificate at any point in the statement
        # order, not just at commit.
        self.db.query(CertificateRevision).filter(
            CertificateRevision.certificate_id == certificate.id,
            CertificateRevision.is_current.is_(True),
        ).update({"is_current": False}, synchronize_session="fetch")
        self.db.flush()

        revision = CertificateRevision(
            id=str(uuid.uuid4()),
            certificate_id=certificate.id,
            revision_no=next_no,
            attachment_id=attachment_id,
            issued_at=issued_at,
            valid_from=valid_from,
            valid_until=valid_until,
            is_current=True,
            source=source,
            needs_review=needs_review,
            review_reasons=review_reasons,
            unmatched_products=unmatched_products,
            extracted_json=extracted_json,
            created_by=str(created_by) if created_by else None,
        )
        self.db.add(revision)
        self.db.flush()
        certificate.current_revision_id = revision.id
        self.db.flush()
        return revision

    def _attachment_type_of(self, attachment_id: Optional[str]) -> Optional[str]:
        if not attachment_id:
            return None
        attachment: Any = (
            self.db.query(Attachment).filter(Attachment.id == attachment_id).first()
        )
        return str(attachment.attachment_type_id) if attachment is not None and attachment.attachment_type_id else None

    def _resolve_new_certificate_company_id(self, attachment_id: Optional[str]) -> Optional[str]:
        """The company to stamp on a BRAND NEW certificate (S6, R5).

        A certificate follows its filing attachment's company: a shared file
        (``company_id`` NULL) makes a shared certificate; a single-company
        file makes a certificate in that same company. ``Certificate`` is now
        ``__company_shared__`` (see the model), so the ``before_insert``
        auto-stamp skips it entirely - every create path has to decide this
        explicitly or the row silently lands company-less.

        No attachment bound yet (a manual create with the file to follow) has
        nothing to inherit from, so it falls back to the caller's own single
        active company - the same value the auto-stamp would have chosen
        before this table became shareable.
        """
        if attachment_id:
            attachment: Any = (
                self.db.query(Attachment).filter(Attachment.id == attachment_id).first()
            )
            if attachment is not None:
                return str(attachment.company_id) if attachment.company_id else None
        from app.models.base import get_company_scope

        return _single_active_company(get_company_scope(self.db))

    def _max_validity_months(self, attachment_type_id: Any) -> Optional[int]:
        if not attachment_type_id:
            return None
        return (
            self.db.query(AttachmentType.max_validity_months)
            .filter(AttachmentType.id == str(attachment_type_id))
            .scalar()
        )

    def _resolve_product_ids(self, product_ids: Sequence[str]) -> list[str]:
        """Keep only ids that resolve to a product visible in the current scope.

        The scope listener does the company filtering, so a product in another
        company simply does not come back and is reported as unknown.
        """
        ids = [str(pid) for pid in product_ids if pid]
        if not ids:
            return []
        found = {
            str(row[0])
            for row in self.db.query(Product.id).filter(Product.id.in_(ids)).all()
        }
        missing = [pid for pid in ids if pid not in found]
        if missing:
            raise handle_validation_error(
                f"{len(missing)} product(s) could not be found in this company."
            )
        # Preserve caller order, drop duplicates.
        seen: set[str] = set()
        return [pid for pid in ids if not (pid in seen or seen.add(pid))]

    def _apply_coverage(
        self,
        certificate: Any,
        product_ids: Sequence[str],
        *,
        source: str,
        created_by: Optional[str],
    ) -> None:
        """Insert missing coverage rows. Existing rows keep their own source."""
        ids = [str(pid) for pid in product_ids if pid]
        if not ids:
            return
        if source not in CERTIFICATE_SOURCES:
            raise handle_validation_error(
                f"source must be one of {', '.join(CERTIFICATE_SOURCES)}."
            )
        existing = {
            str(row[0])
            for row in self.db.query(CertificateProduct.product_id)
            .filter(
                CertificateProduct.certificate_id == certificate.id,
                CertificateProduct.product_id.in_(ids),
            )
            .all()
        }
        seen: set[str] = set()
        for product_id in ids:
            if product_id in existing or product_id in seen:
                continue
            seen.add(product_id)
            self.db.add(
                CertificateProduct(
                    id=str(uuid.uuid4()),
                    certificate_id=certificate.id,
                    product_id=product_id,
                    source=source,
                    created_by=str(created_by) if created_by else None,
                )
            )
        self.db.flush()

    def _revision_attachment_ids(self, certificate: Any) -> set[str]:
        return {
            str(row[0])
            for row in self.db.query(CertificateRevision.attachment_id)
            .filter(
                CertificateRevision.certificate_id == certificate.id,
                CertificateRevision.attachment_id.isnot(None),
            )
            .all()
        }

    def _delete_projection_rows(self, attachment_ids: Iterable[Any]) -> int:
        ids = [str(a) for a in attachment_ids if a]
        if not ids:
            return 0
        return (
            self.db.query(ProductAttachment)
            .filter(ProductAttachment.attachment_id.in_(ids))
            .delete(synchronize_session="fetch")
            or 0
        )

    def _evaluate_review(
        self,
        *,
        scheme: Any,
        certificate_number: Any,
        valid_from: Optional[date],
        valid_until: Optional[date],
        unmatched_products: Sequence[str],
        attachment_type_id: Any,
        covered_count: int,
        issued_at: Optional[date] = None,
        duplicate_of: Optional[Certificate] = None,
        today: Optional[date] = None,
    ) -> tuple[bool, list[dict]]:
        """Deterministic review rules. No model judgement anywhere in here.

        Returns ``(needs_review, reasons)`` where each reason is a dict with a
        machine-readable ``code`` - the FE renders the copy, so the stored value
        never has to be translated or parsed.
        """
        today = today or today_malaysia()
        reasons: list[dict] = []

        values = {
            "scheme": scheme,
            "certificate_number": certificate_number,
            "valid_until": valid_until,
        }
        for field in REQUIRED_EXTRACTION_FIELDS:
            if not values.get(field):
                reasons.append({"code": REVIEW_MISSING_FIELD, "field": field})

        if unmatched_products:
            reasons.append(
                {
                    "code": REVIEW_UNMATCHED_PRODUCTS,
                    "count": len(unmatched_products),
                    "values": list(unmatched_products)[:50],
                }
            )
        elif covered_count == 0:
            # The live PPS 04224FC failure: nine certificates uploaded, one with
            # zero product links and nothing recording it. Zero coverage with
            # nothing even attempted is now loud.
            reasons.append({"code": REVIEW_NO_COVERAGE})

        if valid_from is not None and valid_until is not None and valid_until <= valid_from:
            reasons.append(
                {
                    "code": REVIEW_INVALID_DATE_ORDER,
                    "valid_from": valid_from.isoformat(),
                    "valid_until": valid_until.isoformat(),
                }
            )

        if valid_until is not None and valid_until < today:
            reasons.append(
                {"code": REVIEW_EXPIRED_AT_INGEST, "valid_until": valid_until.isoformat()}
            )

        max_months = self._max_validity_months(attachment_type_id)
        # Most PDFs state only an expiry, so the span is measured from the best
        # start we have. Falling back to today still catches the hallucination
        # this rule exists for: a date 15 years out.
        span_start = valid_from or issued_at or today
        if max_months and valid_until is not None and span_start is not None:
            months = _months_between(span_start, valid_until)
            if months > int(max_months):
                reasons.append(
                    {
                        "code": REVIEW_IMPLAUSIBLE_SPAN,
                        "months": months,
                        "max_months": int(max_months),
                    }
                )

        if duplicate_of is not None:
            reasons.append(
                {
                    "code": REVIEW_POSSIBLE_DUPLICATE,
                    "certificate_id": str(duplicate_of.id),
                    "label": f"{duplicate_of.scheme} {duplicate_of.certificate_number}",
                }
            )

        return bool(reasons), reasons
