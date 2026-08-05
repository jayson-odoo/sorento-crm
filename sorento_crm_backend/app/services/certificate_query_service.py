"""Read side of the certificate register: the list query and the detail payload.

Split from ``certificate_service`` on the write/read line. Everything that
mutates the register lives there and is called from here; this module only
filters, sorts, paginates and assembles what a screen or an agent tool needs.

Three rules that are security requirements, not style:

**Every child query goes through ``Certificate``.** ``certificate_revisions``
and ``certificate_products`` are NOT company-scoped models - they carry no
``company_id`` at all. Isolation holds only because every read enters through
``Certificate``, which IS scoped. A direct ``db.query(CertificateRevision)``
filtered on nothing but an id would happily return another company's row, so
each one here either joins ``Certificate`` or restricts to ids already resolved
through it.

**Company is never filtered by hand.** ``app/services/company_scope.py`` injects
the predicate into every ORM SELECT touching ``Certificate``; adding a manual
``company_id ==`` here would be redundant at best and would mask a scope bug at
worst. Raw ``text()`` SQL is avoided for the same reason - it bypasses both the
filter and the insert-time auto-stamp.

**Only the CURRENT revision is ever URL-resolved.** ``resolve_signed_urls``
signs the live document and nothing else (MCP-8): superseded PDFs are reachable
from the certificate detail page, so no agent path can hand out an expired
document. A NULL or trashed attachment yields nulls for both URLs, never a
broken link.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Optional, Sequence

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, aliased

from app.models.certificate import (
    CERTIFICATE_STATUSES,
    Certificate,
    CertificateProduct,
    CertificateRevision,
)
from app.models.notification import Notification
from app.models.resources import Attachment
from app.schemas.certificate import (
    CertificateRef,
    CertificateReminderResponse,
    CertificateResponse,
)
from app.services.certificate_service import (
    EXPIRING_SOON_DAYS,
    VALIDITY_EXPIRED,
    VALIDITY_EXPIRING_SOON,
    VALIDITY_NOT_YET_VALID,
    VALIDITY_STATES,
    VALIDITY_UNKNOWN,
    VALIDITY_VALID,
    CertificateService,
    normalize_identity,
    today_malaysia,
)
from app.services.error_handler import handle_validation_error

logger = logging.getLogger(__name__)

# ``source_entity_type`` on the notifications an expiry reminder writes (S6).
# Reading them back is what makes the detail page's reminder-history section
# real rather than a placeholder - it is empty until the reminders ship, and
# populated afterwards with no further change here.
CERTIFICATE_NOTIFICATION_ENTITY_TYPE = "certificate"

DEFAULT_SORT = "valid_until"
DEFAULT_SORT_DIR = "asc"


def _normalize_number(value: Any) -> str:
    """Punctuation- and case-insensitive form of a certificate number."""
    return "".join(ch for ch in str(value or "") if ch.isalnum()).upper()


class CertificateQueryService:
    """List, filter and expand certificates for the UI and the agent tools."""

    def __init__(self, db: Session):
        self.db = db
        self.core = CertificateService(db)

    # ------------------------------------------------------------------ list
    def list_certificates(
        self,
        *,
        page: int = 1,
        limit: int = 50,
        sort: Optional[str] = None,
        dir: Optional[str] = None,
        query: Optional[str] = None,
        certificate_ids: Optional[Sequence[str]] = None,
        certificate_number: Optional[str] = None,
        product_ids: Optional[Sequence[str]] = None,
        scheme: Optional[str] = None,
        status: Optional[str] = None,
        validity_state: Optional[str] = None,
        expiring_within_days: Optional[int] = None,
        valid_on: Optional[date] = None,
        needs_review: Optional[bool] = None,
        expiry_notify_batch_id: Optional[str] = None,
        resolve_signed_urls: bool = False,
        today: Optional[date] = None,
    ) -> dict:
        today = today or today_malaysia()
        current = aliased(CertificateRevision)

        # LEFT join, not inner: a certificate with no revision yet must still be
        # listable (it reads validity_state='unknown'), otherwise the row a
        # reviewer needs to fix is the one they cannot see.
        q = self.db.query(Certificate).outerjoin(
            current, current.id == Certificate.current_revision_id
        )

        if certificate_ids:
            q = q.filter(Certificate.id.in_([str(x) for x in certificate_ids]))

        if certificate_number:
            key = _normalize_number(certificate_number)
            if key:
                # Accept either the bare number or a scheme-prefixed one, both
                # normalized: "0119", "PPS 0119" and "pps-0119" all land here.
                q = q.filter(
                    or_(
                        self._number_expression() == key,
                        CertificateService._identity_expression() == key,
                    )
                )

        if product_ids:
            covered = (
                self.db.query(CertificateProduct.certificate_id)
                .filter(CertificateProduct.product_id.in_([str(x) for x in product_ids]))
                .subquery()
            )
            # Correlated through Certificate.id, so the outer (scoped) query
            # still decides which companies' rows can come back.
            q = q.filter(Certificate.id.in_(self.db.query(covered.c.certificate_id)))

        if scheme:
            q = q.filter(func.upper(Certificate.scheme) == str(scheme).strip().upper())

        if status:
            value = str(status).strip()
            if value not in CERTIFICATE_STATUSES:
                raise handle_validation_error(
                    f"status must be one of {', '.join(CERTIFICATE_STATUSES)}."
                )
            q = q.filter(Certificate.status == value)

        if expiry_notify_batch_id:
            q = q.filter(
                Certificate.expiry_notify_batch_id == str(expiry_notify_batch_id)
            )

        if needs_review is not None:
            # Default TRUE, not FALSE: a NULL here means the certificate has no
            # current revision at all, so its expiry is unknown - exactly the row a
            # reviewer has to fix. Defaulting to False would hide it from the
            # needs-review view, which is the one place it was meant to surface.
            flag = func.coalesce(current.needs_review, True)
            q = q.filter(flag.is_(True) if needs_review else flag.is_(False))

        if validity_state:
            q = q.filter(self._validity_predicate(current, validity_state, today))

        if expiring_within_days is not None:
            days = int(expiring_within_days)
            if days < 0:
                raise handle_validation_error("expiring_within_days cannot be negative.")
            q = q.filter(
                current.valid_until.isnot(None),
                current.valid_until >= today,
                current.valid_until <= today + timedelta(days=days),
            )

        if valid_on is not None:
            q = q.filter(
                current.valid_until.isnot(None),
                current.valid_until >= valid_on,
                or_(current.valid_from.is_(None), current.valid_from <= valid_on),
            )

        if query:
            needle = f"%{str(query).strip()}%"
            normalized = _normalize_number(query)
            clauses = [
                Certificate.scheme.ilike(needle),
                Certificate.certificate_number.ilike(needle),
                Certificate.certifying_body.ilike(needle),
                Certificate.issuer.ilike(needle),
                Certificate.title.ilike(needle),
            ]
            if normalized:
                # A search for "PPS-0119" must find "PPS 0119" - the number is
                # matched on its normalized form as well as verbatim.
                clauses.append(self._number_expression().like(f"%{normalized}%"))
                clauses.append(
                    CertificateService._identity_expression().like(f"%{normalized}%")
                )
            q = q.filter(or_(*clauses))

        total = q.count()
        q = self._apply_sort(q, current, sort, dir)

        page = max(1, int(page or 1))
        limit = max(1, int(limit or 50))
        rows = q.offset((page - 1) * limit).limit(limit).all()

        data = self.core.serialize_many(rows, today=today)
        if resolve_signed_urls:
            self._attach_signed_urls(rows, data)

        return {
            "data": data,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
        }

    # ---------------------------------------------------------------- detail
    def get_detail(
        self,
        certificate_id: str,
        *,
        resolve_signed_urls: bool = False,
        today: Optional[date] = None,
    ) -> CertificateResponse:
        """One certificate with every section the detail page renders.

        Sections are always present, never omitted when empty - the page renders
        an explicit empty state rather than hiding a section, so "no covered
        products" is a visible fact instead of a missing panel.
        """
        certificate: Any = self.core.get_certificate(certificate_id)
        row = self.core.serialize(certificate, expand=True, today=today)

        current = self.core.get_current_revision(certificate)
        row.current_revision = (
            self.core.serialize_revision(current) if current is not None else None
        )
        # `revisions` is already newest-first from the core serializer.
        row.products = list(row.covered_products or [])
        row.reminders = self._reminders(str(certificate.id))
        row.possible_duplicate_of = self._duplicate_ref(certificate)
        if resolve_signed_urls:
            self._attach_signed_urls([certificate], [row])
        return row

    # ------------------------------------------------------------- internals
    @staticmethod
    def _number_expression():
        """The certificate number with punctuation and case stripped."""
        return func.upper(
            func.regexp_replace(
                Certificate.certificate_number, "[^A-Za-z0-9]", "", "g"
            )
        )

    def _duplicate_ref(self, certificate: Any) -> Optional[CertificateRef]:
        """Resolve the suspected-original pointer to something renderable.

        Reached through the scoped ``Certificate`` query, so a pointer at another
        company's row simply resolves to None rather than leaking its number.
        """
        pointer = certificate.possible_duplicate_of_certificate_id
        if not pointer:
            return None
        other: Any = (
            self.db.query(Certificate).filter(Certificate.id == str(pointer)).first()
        )
        if other is None:
            return None
        return CertificateRef(
            id=str(other.id),
            scheme=other.scheme,
            certificate_number=other.certificate_number,
        )

    def _reminders(self, certificate_id: str) -> list[CertificateReminderResponse]:
        """Expiry reminders that actually went out for this certificate.

        Read off ``notifications`` rather than a bespoke table: the reminders ride
        the existing automation engine, so one row per recipient per send is what
        exists. Grouped by ``event_type`` (the automation's identity) so a 90/30/7
        schedule reads as three sends, not thirty.
        """
        rows = (
            self.db.query(
                Notification.event_type,
                func.max(Notification.created_at).label("sent_at"),
                func.count(func.distinct(Notification.user_id)).label("recipients"),
                func.min(Notification.data["days_before"].astext).label("days_before"),
            )
            .filter(
                # AutomationService._enqueue_email stamps EVERY automation
                # notification with source_entity_type='automation_run' and the run
                # id, so filtering on 'certificate' here matched nothing and this
                # section was permanently empty. The real subject is encoded in
                # event_type as ":source:<kind>:id:<id>" - match on that instead of
                # changing the shared automation writer, which other features rely on.
                Notification.event_type.like(
                    f"%:source:{CERTIFICATE_NOTIFICATION_ENTITY_TYPE}:id:{certificate_id}%"
                )
            )
            .group_by(Notification.event_type)
            .order_by(func.max(Notification.created_at).desc())
            .all()
        )
        out: list[CertificateReminderResponse] = []
        for event_type, sent_at, recipients, days_before in rows:
            try:
                days = int(days_before) if days_before is not None else None
            except (TypeError, ValueError):
                days = None
            out.append(
                CertificateReminderResponse(
                    id=str(event_type or ""),
                    days_before=days,
                    sent_at=sent_at,
                    recipient_count=int(recipients or 0),
                )
            )
        return out

    def _validity_predicate(self, current, raw: str, today: date):
        """Turn a comma-separated ``validity_state`` list into one OR predicate.

        A list, not a single value, because the default list view is scoped to
        ``expiring_soon,expired`` - what needs attention - rather than to an
        undifferentiated "all". The SQL mirrors ``derive_validity`` exactly,
        including its order: expiry is decided before "not yet valid", so a
        nonsensical window can never read as anything but expired.
        """
        wanted = [part.strip() for part in str(raw).split(",") if part.strip()]
        unknown = [w for w in wanted if w not in VALIDITY_STATES]
        if unknown:
            raise handle_validation_error(
                f"validity_state must be one of {', '.join(VALIDITY_STATES)}; "
                f"got {', '.join(unknown)}."
            )
        if not wanted:
            raise handle_validation_error("validity_state cannot be blank.")

        warn_edge = today + timedelta(days=EXPIRING_SOON_DAYS)
        not_started = current.valid_from.isnot(None) & (current.valid_from > today)
        started = ~not_started

        by_state = {
            VALIDITY_UNKNOWN: current.valid_until.is_(None),
            VALIDITY_EXPIRED: current.valid_until.isnot(None)
            & (current.valid_until < today),
            VALIDITY_NOT_YET_VALID: current.valid_until.isnot(None)
            & (current.valid_until >= today)
            & not_started,
            VALIDITY_EXPIRING_SOON: current.valid_until.isnot(None)
            & (current.valid_until >= today)
            & (current.valid_until <= warn_edge)
            & started,
            VALIDITY_VALID: current.valid_until.isnot(None)
            & (current.valid_until > warn_edge)
            & started,
        }
        return or_(*[by_state[state] for state in wanted])

    def _apply_sort(self, q, current, sort: Optional[str], dir: Optional[str]):
        """Sort from an explicit allowlist - never ``getattr`` on user input."""
        coverage_count = (
            self.db.query(func.count(CertificateProduct.id))
            .filter(CertificateProduct.certificate_id == Certificate.id)
            .correlate(Certificate)
            .scalar_subquery()
        )
        sort_map = {
            "scheme": Certificate.scheme,
            "certificate_number": Certificate.certificate_number,
            "certifying_body": Certificate.certifying_body,
            "issuer": Certificate.issuer,
            "title": Certificate.title,
            "status": Certificate.status,
            "created_at": Certificate.created_at,
            "updated_at": Certificate.updated_at,
            "issued_at": current.issued_at,
            "valid_from": current.valid_from,
            "valid_until": current.valid_until,
            "needs_review": current.needs_review,
            "covered_product_count": coverage_count,
        }
        column = sort_map.get((sort or "").strip() or DEFAULT_SORT)
        if column is None:
            column = sort_map[DEFAULT_SORT]
        descending = str(dir or DEFAULT_SORT_DIR).strip().lower() == "desc"
        ordering = column.desc() if descending else column.asc()
        # Certificate.id last so pagination is stable when the sort key ties.
        return q.order_by(ordering, Certificate.id)

    def _attach_signed_urls(
        self, certificates: Sequence[Any], rows: Sequence[CertificateResponse]
    ) -> None:
        """Sign the CURRENT revision's file onto each row (MCP-7).

        Superseded revisions are never signed (MCP-8), and a NULL or trashed
        attachment leaves both URLs null - an agent hands out the live document
        or nothing, never a broken link to a withdrawn one.
        """
        by_certificate = {str(c.id): c for c in certificates}
        revision_ids = [r.current_revision_id for r in rows if r.current_revision_id]
        if not revision_ids:
            return

        # Reached via the certificate ids we already resolved through the scoped
        # query, so this child read cannot cross a company boundary.
        revisions: dict[str, Any] = {
            str(rev.id): rev
            for rev in self.db.query(CertificateRevision)
            .filter(
                CertificateRevision.id.in_([str(x) for x in revision_ids]),
                CertificateRevision.certificate_id.in_(list(by_certificate)),
            )
            .all()
        }
        attachment_ids = [
            str(rev.attachment_id) for rev in revisions.values() if rev.attachment_id
        ]
        attachments: dict[str, Any] = {
            str(a.id): a
            for a in (
                self.db.query(Attachment).filter(Attachment.id.in_(attachment_ids)).all()
                if attachment_ids
                else []
            )
        }

        from app.services.storage_router import resolve_signed_url

        for row in rows:
            if not row.current_revision_id:
                continue
            revision = revisions.get(str(row.current_revision_id))
            if revision is None or not revision.attachment_id:
                continue
            attachment = attachments.get(str(revision.attachment_id))
            if attachment is None or bool(attachment.is_deleted):
                continue
            try:
                signed = resolve_signed_url(
                    getattr(attachment, "file_path", None),
                    provider=getattr(attachment, "storage_provider", None),
                )
            except Exception as e:  # noqa: BLE001 - a listing must not 500 on storage
                logger.warning(
                    "Certificate signed-URL resolution failed for attachment=%s: %s",
                    revision.attachment_id,
                    e,
                    exc_info=True,
                )
                continue
            if not signed:
                continue
            # One signed object serves both actions: preview opens it inline,
            # download saves it. There is no separate signed download variant.
            row.preview_url = signed
            row.download_url = signed
