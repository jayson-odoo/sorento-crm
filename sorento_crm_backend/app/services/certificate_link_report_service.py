"""CERT-LINK-CLEANUP: the "Certificate links to check" report, its check job, Confirm and Remove.

Card: documentation/plans/certificates/CARD-cert-link-cleanup-08nov.md (R1-R7, owner answers Q1-Q3).

- **Verdicts are stored, not computed per request.** Reading ~10k links means reading every
  certificate PDF, so `check_certificates` reads each current PDF ONCE (on the worker, queue
  `flyer_read`) and stamps every link of it with `check_verdict` and the `check_key` it was read
  against. A link whose stored key differs from its live key (new revision, changed Code on
  certificate, changed product code) reads `pending` ("Checking") until the next check.
- **Never automatic.** Nothing here removes a link by itself. Remove is the `certificate_link.remove`
  pending action (10 s, record_actions); Confirm flips `source` to `manual` (Q3 (a)).
- **Scope.** Every read goes through the scoped `Certificate` query, so a link of another company's
  certificate is never listed, confirmed or removed (`certificate_products` itself is unscoped).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Iterable, Optional, Sequence

from sqlalchemy import String, and_, asc, case, cast, desc, func, literal, or_
from sqlalchemy.orm import Session

from app.models.certificate import Certificate, CertificateProduct, CertificateRevision
from app.models.product import Product
from app.models.resources import AttachmentType
from app.services import certificate_link_check as link_check
from app.services.audit_service import log_audit
from app.services.error_handler import handle_not_found, handle_validation_error

logger = logging.getLogger(__name__)

PENDING = "pending"
FILTER_VERDICTS = link_check.VERDICTS + (PENDING,)
CHECK_QUEUE = "flyer_read"


def enqueue_job(func, *args, **kwargs):
    """`queue_service.enqueue_job`, looked up when called so a test can stand in for it."""
    from app.services.queue_service import enqueue_job as _enqueue

    return _enqueue(func, *args, **kwargs)


# ----------------------------------------------------------------------------- the key


def check_key(revision_id: Any, model_code_source: Any, model_code: Any, product_code: Any) -> str:
    """What a verdict was read against. Mirrored by `_live_key` in SQL: keep the two in lockstep."""
    return "|".join(str(v or "") for v in (revision_id, model_code_source, model_code, product_code))


def _live_key():
    sep = literal("|")
    return (
        func.coalesce(cast(Certificate.current_revision_id, String), "")
        + sep
        + func.coalesce(CertificateProduct.model_code_source, "")
        + sep
        + func.coalesce(CertificateProduct.model_code, "")
        + sep
        + func.coalesce(Product.product_code, "")
    )


def _verdict_expr():
    return case(
        (
            and_(CertificateProduct.check_verdict.isnot(None), CertificateProduct.check_key == _live_key()),
            CertificateProduct.check_verdict,
        ),
        else_=literal(PENDING),
    )


# ----------------------------------------------------------------------------- list

_SORTS = {
    "certificate_number": lambda: Certificate.certificate_number,
    "scheme": lambda: Certificate.scheme,
    "certificate_type": lambda: AttachmentType.type_name,
    "product_code": lambda: Product.product_code,
    "product_name": lambda: Product.product_name,
    "model_code": lambda: CertificateProduct.model_code,
    "source": lambda: CertificateProduct.source,
    "verdict": _verdict_expr,
    "checked_at": lambda: CertificateProduct.checked_at,
    "created_at": lambda: CertificateProduct.created_at,
}


def _split(values: Optional[Sequence[str] | str]) -> list[str]:
    if values is None:
        return []
    items = [values] if isinstance(values, str) else list(values)
    out: list[str] = []
    for item in items:
        out.extend(part.strip() for part in str(item).split(",") if part.strip())
    return out


def _base(db: Session):
    return (
        db.query(CertificateProduct, Certificate, Product, AttachmentType.type_name, _verdict_expr().label("verdict"))
        .join(Certificate, Certificate.id == CertificateProduct.certificate_id)
        .join(Product, Product.id == CertificateProduct.product_id)
        .outerjoin(AttachmentType, AttachmentType.id == Certificate.attachment_type_id)
    )


def _filtered(q, *, query, certificate_ids, attachment_type_ids, sources, statuses):
    if certificate_ids:
        q = q.filter(Certificate.id.in_(certificate_ids))
    if attachment_type_ids:
        q = q.filter(Certificate.attachment_type_id.in_(attachment_type_ids))
    if sources:
        bad = [s for s in sources if s not in ("ai", "manual")]
        if bad:
            raise handle_validation_error("source must be ai or manual.")
        q = q.filter(CertificateProduct.source.in_(sources))
    if statuses:
        q = q.filter(Certificate.status.in_(statuses))
    if query and str(query).strip():
        raw = str(query).strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        needle = f"%{raw}%"
        q = q.filter(
            or_(
                *(
                    column.ilike(needle, escape="\\")
                    for column in (
                        Product.product_code,
                        Product.product_name,
                        Certificate.certificate_number,
                        Certificate.scheme,
                        CertificateProduct.model_code,
                    )
                )
            )
        )
    return q


def list_links(
    db: Session,
    *,
    page: int = 1,
    limit: int = 50,
    sort: Optional[str] = None,
    dir: Optional[str] = None,
    query: Optional[str] = None,
    certificate_ids: Optional[Sequence[str]] = None,
    attachment_type_ids: Optional[Sequence[str]] = None,
    verdict: Optional[Sequence[str] | str] = None,
    source: Optional[Sequence[str] | str] = None,
    status: Optional[Sequence[str] | str] = None,
) -> dict:
    verdicts = _split(verdict)
    bad = [v for v in verdicts if v not in FILTER_VERDICTS]
    if bad:
        raise handle_validation_error(f"verdict must be one of {', '.join(FILTER_VERDICTS)}.")
    filters = dict(
        query=query,
        certificate_ids=[str(x) for x in (certificate_ids or [])],
        attachment_type_ids=[str(x) for x in (attachment_type_ids or [])],
        sources=_split(source),
        statuses=_split(status),
    )

    # Counts per verdict under every filter EXCEPT the verdict one, so the filter can show them.
    verdict_col = _verdict_expr()
    counted = _filtered(
        db.query(verdict_col.label("v"), func.count(CertificateProduct.id))
        .join(Certificate, Certificate.id == CertificateProduct.certificate_id)
        .join(Product, Product.id == CertificateProduct.product_id),
        **filters,
    ).group_by(verdict_col)
    summary = {v: 0 for v in FILTER_VERDICTS}
    for value, count in counted.all():
        summary[value] = int(count)

    q = _filtered(_base(db), **filters)
    if verdicts:
        q = q.filter(_verdict_expr().in_(verdicts))
    total = q.count()

    column = _SORTS.get(str(sort or "").strip())
    order = desc if str(dir or "").lower() == "desc" else asc
    if column is not None:
        q = q.order_by(order(column()).nulls_last(), CertificateProduct.id)
    else:
        q = q.order_by(Certificate.certificate_number, Product.product_code, CertificateProduct.id)

    page = max(1, int(page or 1))
    limit = max(1, int(limit or 50))
    rows = q.offset((page - 1) * limit).limit(limit).all()
    data = [_serialize(cp, cert, product, type_name, verdict_value) for cp, cert, product, type_name, verdict_value in rows]
    # The certificate types that have links in scope: the type filter's options, so a viewer
    # needs no attachment-types permission to filter by type.
    types = (
        db.query(AttachmentType.id, AttachmentType.type_name)
        .join(Certificate, Certificate.attachment_type_id == AttachmentType.id)
        .join(CertificateProduct, CertificateProduct.certificate_id == Certificate.id)
        .distinct()
        .order_by(AttachmentType.type_name)
        .all()
    )
    return {
        "data": data,
        "pagination": {"total": total, "page": page, "limit": limit},
        "empty": total == 0,
        "summary": summary,
        "types": [{"id": str(type_id), "name": name} for type_id, name in types],
    }


def _serialize(cp, cert, product, type_name, verdict_value) -> dict:
    return {
        "id": str(cp.id),
        "certificate_id": str(cert.id),
        "scheme": cert.scheme,
        "certificate_number": cert.certificate_number,
        "certificate_type": type_name,
        "certificate_status": cert.status,
        "product_id": str(product.id),
        "product_code": product.product_code,
        "product_name": product.product_name,
        "model_code": cp.model_code,
        "model_code_source": cp.model_code_source,
        "source": cp.source,
        "verdict": verdict_value,
        "check_code": cp.check_code if verdict_value != PENDING else None,
        "checked_at": cp.checked_at.isoformat() if cp.checked_at and verdict_value != PENDING else None,
    }


# ----------------------------------------------------------------------------- check


def pending_certificate_ids(db: Session) -> list[str]:
    """Certificates (in the caller's scope) with at least one link not checked against its live key."""
    rows = (
        db.query(Certificate.id)
        .join(CertificateProduct, CertificateProduct.certificate_id == Certificate.id)
        .join(Product, Product.id == CertificateProduct.product_id)
        .filter(_verdict_expr() == PENDING)
        .distinct()
        .all()
    )
    return sorted(str(r[0]) for r in rows)


def queue_pending(db: Session) -> int:
    """Queue one check job for the certificates with pending links. Returns how many are covered.

    One job per distinct pending set (security review S3): the links stay `pending` until the job
    stamps them, so a second visit or a double click before then finds the same set and the job
    already waiting or running, and queues nothing new."""
    ids = pending_certificate_ids(db)
    if ids:
        import hashlib

        job_id = "certificate-link-check-" + hashlib.sha1(",".join(ids).encode()).hexdigest()[:16]
        if not _already_queued(job_id):
            from app.tasks.certificate_link_tasks import check_certificate_links

            enqueue_job(check_certificate_links, ids, queue_name=CHECK_QUEUE, job_timeout=3600, job_id=job_id)
    return len(ids)


def _already_queued(job_id: str) -> bool:
    """Whether the job is waiting or running. False when Redis cannot say (then it is queued)."""
    try:
        from rq.job import Job, JobStatus

        from app.services.queue_service import get_queue

        job = Job.fetch(job_id, connection=get_queue(CHECK_QUEUE).connection)
        return job.get_status() in {JobStatus.QUEUED, JobStatus.STARTED, JobStatus.DEFERRED, JobStatus.SCHEDULED}
    except Exception:  # noqa: BLE001 - no such job, or no Redis
        return False


def _read_current_text(db: Session, certificate, wanted: set[str]) -> Optional[dict]:
    revision: Optional[CertificateRevision] = certificate.current_revision
    attachment = revision.attachment if revision is not None else None
    if attachment is None:
        return None
    from app.services.resources_service import AttachmentService

    try:
        data = AttachmentService(db).get_file_content_for(attachment)
    except Exception:  # noqa: BLE001 - an unreadable file is the no_file verdict, not a failed job
        logger.info("certificate link check: file unreadable for certificate %s", certificate.id)
        return None
    return link_check.read_text(data, wanted)


def _set_codes_by_product(db: Session, product_ids) -> dict[str, set[str]]:
    """`{product_id: {normalised set code}}` for the product sets each product is a member of."""
    from app.models.product_set import ProductSet, ProductSetMember
    from app.services.certificate_pdf_service import normalise

    ids = [str(x) for x in product_ids]
    out: dict[str, set[str]] = {}
    if not ids:
        return out
    rows = (
        db.query(ProductSetMember.product_id, ProductSet.set_code)
        .join(ProductSet, ProductSet.id == ProductSetMember.product_set_id)
        .filter(ProductSetMember.product_id.in_(ids))
        .all()
    )
    for product_id, set_code in rows:
        out.setdefault(str(product_id), set()).add(normalise(set_code or ""))
    return out


def check_certificate(db: Session, certificate) -> int:
    """Read the certificate's current PDF once and stamp every link. Returns links stamped."""
    rev_id = certificate.current_revision_id
    now = datetime.utcnow()
    links = (
        db.query(CertificateProduct, Product.product_code)
        .join(Product, Product.id == CertificateProduct.product_id)
        .filter(CertificateProduct.certificate_id == certificate.id)
        .all()
    )
    wanted = link_check.wanted_for_links((cp.model_code, product_code) for cp, product_code in links)
    text = _read_current_text(db, certificate, wanted)
    sets_of = _set_codes_by_product(db, [cp.product_id for cp, _code in links])
    for cp, product_code in links:
        value, code = link_check.verdict(
            text,
            model_code=cp.model_code,
            model_code_source=cp.model_code_source,
            product_code=product_code,
            set_codes=sets_of.get(str(cp.product_id), ()),
        )
        cp.check_verdict = value
        cp.check_code = (code or None) and str(code)[:60]
        cp.check_key = check_key(rev_id, cp.model_code_source, cp.model_code, product_code)
        cp.checked_at = now
    return len(links)


def check_certificates(db: Session, certificate_ids: Iterable[str]) -> dict:
    """Check exactly the given certificates (chosen in the requester's scope by `queue_pending`).
    Commits per certificate, so a long run keeps what it has done if it is stopped. An empty list
    checks nothing: the worker runs with the scope off, so it never widens to "every pending"."""
    ids = [str(x) for x in (certificate_ids or [])]
    # A later job queued while an earlier one was still running carries ids it has since done:
    # read only the ones still pending (reviewer round 2), so a long backfill is not repeated.
    still = set(pending_certificate_ids(db)) if ids else set()
    ids = [x for x in ids if x in still]
    checked = links = 0
    for certificate_id in ids:
        certificate = db.query(Certificate).filter(Certificate.id == certificate_id).first()
        if certificate is None:
            continue
        try:
            links += check_certificate(db, certificate)
            db.commit()
            checked += 1
        except Exception:  # noqa: BLE001 - one bad file must not stop the backfill
            db.rollback()
            logger.warning("certificate link check failed for %s", certificate_id, exc_info=True)
    return {"certificates": checked, "links": links}


# ----------------------------------------------------------------------------- confirm / remove


def _scoped_links(db: Session, ids: Sequence[str]) -> list[tuple[CertificateProduct, Certificate]]:
    """The links, each THROUGH its scoped certificate. 404 when any id is unknown or out of scope."""
    wanted = list(dict.fromkeys(str(x) for x in ids))
    rows = (
        db.query(CertificateProduct, Certificate)
        .join(Certificate, Certificate.id == CertificateProduct.certificate_id)
        .filter(CertificateProduct.id.in_(wanted))
        .all()
    )
    found = {str(cp.id) for cp, _cert in rows}
    missing = [x for x in wanted if x not in found]
    if missing:
        raise handle_not_found("Certificate link", missing[0])
    return rows


def assert_link_visible(db: Session, link_id: str) -> None:
    """Park-time check of `certificate_link.remove`: a valid id of a link in the caller's scope."""
    from app.services.uuid_path_param import validate_uuid_path

    validate_uuid_path(link_id, resource="Certificate link")
    _scoped_links(db, [link_id])


def _product_company(db: Session, product_id) -> Optional[str]:
    value = db.query(Product.company_id).filter(Product.id == str(product_id)).scalar()
    return str(value) if value else None


def confirm_links(db: Session, ids: Sequence[str], user_id: Optional[str]) -> int:
    """Q3 (a): a person stands behind these links. `source` -> manual, one audit row per link on the
    product's Audit Trail ("was AI"). Already-manual links are left alone and not counted."""
    if not ids:
        return 0
    confirmed = 0
    for cp, cert in _scoped_links(db, ids):
        if cp.source == "manual":
            continue
        previous = cp.source
        cp.source = "manual"
        confirmed += 1
        log_audit(
            db,
            "certificate_products",
            str(cp.id),
            "UPDATE",
            old_values={"source": previous},
            new_values={
                "source": "manual",
                "product_id": str(cp.product_id),
                "certificate_id": str(cert.id),
                "certificate_number": cert.certificate_number,
                "check_verdict": cp.check_verdict,
            },
            user_id=str(user_id) if user_id else None,
            description=f"Certificate link confirmed: {cert.scheme} {cert.certificate_number} (was AI)",
            event="certificate_link_confirmed",
            company_id=_product_company(db, cp.product_id),
            root_entity_type="product",
            root_entity_id=str(cp.product_id),
        )
    db.commit()
    return confirmed


def remove_link(db: Session, link_id: str, user_id: Optional[str]) -> dict:
    """The `certificate_link.remove` handler: hard-delete one link and its projection, audited the
    way the detail page's Remove is (PRODUCT-ATTACH-AUDIT, one UNLINK row on the product)."""
    from app.services import product_link_audit
    from app.services.certificate_service import CertificateService
    from app.services.uuid_path_param import validate_uuid_path

    validate_uuid_path(link_id, resource="Certificate link")
    ((cp, cert),) = _scoped_links(db, [link_id])
    service = CertificateService(db)
    revision = service.get_current_revision(cert)
    product_link_audit.log_product_file_link(
        db,
        product_link_audit.UNLINK,
        product_id=str(cp.product_id),
        attachment_id=str(revision.attachment_id) if revision and revision.attachment_id else None,
        entity_type="certificate_products",
        entity_id=str(cp.id),
        user_id=user_id,
        extra={
            "certificate_id": str(cert.id),
            "certificate_number": cert.certificate_number,
            "source": cp.source,
            "check_verdict": cp.check_verdict,
        },
    )
    service.remove_coverage(str(cert.id), [str(cp.product_id)])
    return {"removed": True}
