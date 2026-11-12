"""After-sales P1: raising, moving and listing service jobs.

A job is one visit to one complaint's site. Rules live here (UAC B, C, D, E, H3); the router only
gates permissions and shapes HTTP.

* Raise is idempotent per complaint. The complaint row is locked FOR UPDATE for the check and the
  insert, so two concurrent raises leave one live job. (A partial unique index cannot name the
  status because the status is an FK.) "Live" means any status except cancelled and verified.
* Every move goes through the status graph; an illegal move is 409 and changes nothing.
* ``scheduled_from`` is stored as naive UTC. The board's day is the Malaysian day (UTC+8).
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import and_, asc, desc, false, func, or_
from sqlalchemy.orm import Session

from app.models.base import get_company_scope
from app.models.complaints import Complaint
from app.models.service_jobs import ServiceJob, Technician
from app.models.status import Status
from app.services import own_scope
from app.services.error_handler import AppException, handle_not_found
from app.services.service_job_status_graph import SERVICE_JOB_ENTITY_TYPE

logger = logging.getLogger(__name__)

JOB_NUMBER_DOC_TYPE = "service_job"
DEAD_KEYS = ("cancelled", "verified")
MYT = timedelta(hours=8)
REASON_REQUIRED = ("proposed", "cancelled")


def _now() -> datetime:
    return datetime.utcnow()


def to_naive_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def myt_day_bounds(day: date) -> Tuple[datetime, datetime]:
    """[start, end) of a Malaysian calendar day, as naive UTC."""
    start = datetime(day.year, day.month, day.day) - MYT
    return start, start + timedelta(days=1)


# ------------------------------------------------------------------ scope (H3)


class Limit:
    """A user who holds complaints view_own and not view: only complaints of their contact."""

    def __init__(self, contact_id: Optional[str]):
        self.contact_id = contact_id

    def clause(self):
        if not self.contact_id:
            return false()
        return Complaint.contact_id == self.contact_id


def limit_for(db: Session, user_id: str, *, strict: bool = True) -> Optional[Limit]:
    """None = no limit (admin, or complaints ``view``). A reader with no complaints access at all
    matches nothing (``strict``); a dispatcher's writes keep working without it (``strict=False``)."""
    from app.services.user_service import UserPermissionService

    service = UserPermissionService(db)
    if service.get_user_role_slugs(user_id) & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}:
        return None
    perms = service.get_user_permission_slugs(user_id)
    access = own_scope.request_access(perms, "complaint")
    if access == "all":
        return None
    if access == "own":
        return Limit(own_scope.me(db, user_id).contact_id)
    return Limit(None) if strict else None


def brand_clauses(db: Session) -> list:
    """The complaints list's brand scope (a contact limited to some brands), on the job's complaint."""
    from app.services.contact_brand_scope import complaint_in_scope_clauses

    return list(complaint_in_scope_clauses(db))


def job_brand_clauses(db: Session) -> list:
    """The same scope stated on ``ServiceJob`` itself, for the assistant's query."""
    from sqlalchemy import select

    clauses = brand_clauses(db)
    if not clauses:
        return []
    return [ServiceJob.complaint_id.in_(select(Complaint.id).where(*clauses))]


def stamp_actor(db: Session, user: dict) -> None:
    """Attribute the audited writes to the acting user when the auth dependency has not."""
    from app.audit_context import AuditActor, get_actor
    from app.audit_context import stamp_actor as _stamp

    user_id = user.get("id")
    if not user_id:
        return
    actor = get_actor(db)
    if actor is not None and str(user_id) in (actor.user_id, actor.real_user_id):
        return
    _stamp(AuditActor(actor_type="user", user_id=str(user_id), real_user_id=str(user_id)), db=db)


# ------------------------------------------------------------------ queries


def _valid_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (TypeError, ValueError):
        return False


def status_by_key(db: Session, key: str) -> Optional[Status]:
    return (
        db.query(Status)
        .filter(
            Status.entity_type == SERVICE_JOB_ENTITY_TYPE,
            Status.scope_id.is_(None),
            Status.key == key,
        )
        .first()
    )


def _base_query(db: Session, limit: Optional[Limit]):
    q = (
        db.query(ServiceJob, Status, Technician, Complaint)
        .join(Complaint, Complaint.id == ServiceJob.complaint_id)
        .outerjoin(Status, Status.id == ServiceJob.status_id)
        .outerjoin(Technician, Technician.id == ServiceJob.technician_id)
    )
    if limit is not None:
        q = q.filter(limit.clause())
    q = q.filter(*brand_clauses(db))
    return q


def serialize(row: Tuple[ServiceJob, Optional[Status], Optional[Technician], Complaint]) -> Dict[str, Any]:
    job, status, tech, complaint = row
    return {
        "id": job.id,
        "job_number": job.job_number,
        "complaint_id": job.complaint_id,
        "complaint_number": complaint.complaint_number,
        "customer_name": complaint.customer_name,
        "city": complaint.site_city,
        "site_address_line1": complaint.site_address_line1,
        "site_address_line2": complaint.site_address_line2,
        "site_postcode": complaint.site_postcode,
        "site_state": complaint.site_state,
        "site_country": complaint.site_country,
        "site_contact_name": complaint.site_contact_name,
        "site_contact_phone": complaint.site_contact_phone,
        "status": status.key if status else None,
        "status_label": status.label if status else None,
        "status_color": status.color_hex if status else None,
        "technician_id": job.technician_id,
        "technician_name": tech.name if tech else None,
        "scheduled_from": job.scheduled_from,
        "scheduled_to": job.scheduled_to,
        "customer_agreed_by": job.customer_agreed_by,
        "rejection_reason": job.rejection_reason,
        "cancel_reason": job.cancel_reason,
        "arrived_at": job.arrived_at,
        "completed_at": job.completed_at,
        "verified_at": job.verified_at,
        "created_at": job.created_at,
    }


def get_row(db: Session, job_id: str, limit: Optional[Limit] = None):
    if not _valid_uuid(job_id):
        raise handle_not_found("Service job", str(job_id))
    row = _base_query(db, limit).filter(ServiceJob.id == str(job_id)).first()
    if row is None:
        raise handle_not_found("Service job", str(job_id))
    return row


def get_job(db: Session, job_id: str, limit: Optional[Limit] = None) -> Dict[str, Any]:
    db.expire_all()
    return serialize(get_row(db, job_id, limit))


def _get_complaint(db: Session, complaint_id: str, limit: Optional[Limit], *, lock: bool = False) -> Complaint:
    if not _valid_uuid(complaint_id):
        raise handle_not_found("Complaint", str(complaint_id))
    q = db.query(Complaint).filter(Complaint.id == str(complaint_id))
    if limit is not None:
        q = q.filter(limit.clause())
    q = q.filter(*brand_clauses(db))
    if lock:
        q = q.with_for_update()
    row = q.first()
    if row is None:
        raise handle_not_found("Complaint", str(complaint_id))
    return row


def list_for_complaint(db: Session, complaint_id: str, limit: Optional[Limit]) -> List[Dict[str, Any]]:
    _get_complaint(db, complaint_id, limit)
    rows = (
        _base_query(db, limit)
        .filter(ServiceJob.complaint_id == str(complaint_id))
        .order_by(ServiceJob.created_at.desc(), ServiceJob.id)
        .all()
    )
    return [serialize(r) for r in rows]


SORTS = {
    "job_number": lambda: ServiceJob.job_number,
    "complaint_number": lambda: Complaint.complaint_number,
    "status": lambda: Status.sort_order,
    "scheduled_from": lambda: ServiceJob.scheduled_from,
    "technician": lambda: Technician.name,
    "city": lambda: Complaint.site_city,
    "customer": lambda: Complaint.customer_name,
}


def list_jobs(
    db: Session,
    limit_scope: Optional[Limit],
    *,
    page: int,
    limit: int,
    query: Optional[str],
    sort: Optional[str],
    direction: str,
    statuses: Optional[Sequence[str]],
    technician_ids: Optional[Sequence[str]],
    date_from: Optional[date],
    date_to: Optional[date],
) -> Dict[str, Any]:
    q = _base_query(db, limit_scope)
    if query and query.strip():
        like = f"%{query.strip()}%"
        q = q.filter(
            or_(
                ServiceJob.job_number.ilike(like),
                Complaint.complaint_number.ilike(like),
                Complaint.customer_name.ilike(like),
                Complaint.site_city.ilike(like),
            )
        )
    if statuses:
        q = q.filter(Status.key.in_(list(statuses)))
    if technician_ids:
        valid = [t for t in technician_ids if _valid_uuid(t)]
        q = q.filter(ServiceJob.technician_id.in_(valid)) if valid else q.filter(false())
    if date_from:
        q = q.filter(ServiceJob.scheduled_from >= myt_day_bounds(date_from)[0])
    if date_to:
        q = q.filter(ServiceJob.scheduled_from < myt_day_bounds(date_to)[1])

    total = q.count()
    column = SORTS.get(sort or "", SORTS["job_number"])()
    order = asc(column) if (direction or "desc").lower() == "asc" else desc(column)
    if not sort:
        order = desc(ServiceJob.created_at)
    rows = q.order_by(order.nulls_last(), ServiceJob.id).offset((page - 1) * limit).limit(limit).all()
    return {
        "data": [serialize(r) for r in rows],
        "pagination": {"total": total, "page": page, "limit": limit},
        "empty": total == 0,
    }


def board(db: Session, limit_scope: Optional[Limit], day: date) -> Dict[str, Any]:
    start, end = myt_day_bounds(day)
    # Every Proposed job is waiting for a date, whatever day is picked: oldest raised first.
    waiting_rows = (
        _base_query(db, limit_scope)
        .filter(Status.key == "proposed")
        .order_by(ServiceJob.created_at.asc(), ServiceJob.id)
        .limit(500)
        .all()
    )

    day_rows = (
        _base_query(db, limit_scope)
        .filter(
            Status.key != "cancelled",
            ServiceJob.scheduled_from >= start,
            ServiceJob.scheduled_from < end,
        )
        .order_by(ServiceJob.scheduled_from.asc(), ServiceJob.id)
        .all()
    )

    unassigned: List[Dict[str, Any]] = []
    by_tech: Dict[str, Dict[str, Any]] = {}
    for row in day_rows:
        job, _status, tech, _complaint = row
        data = serialize(row)
        if tech is None or not tech.is_active:
            unassigned.append(data)
            continue
        col = by_tech.setdefault(
            tech.id, {"technician_id": tech.id, "technician_name": tech.name, "jobs": []}
        )
        col["jobs"].append(data)

    columns = [{"technician_id": None, "technician_name": "Unassigned", "jobs": unassigned}]
    columns += sorted(by_tech.values(), key=lambda c: (c["technician_name"] or "").lower())
    return {"day": day.isoformat(), "waiting": [serialize(r) for r in waiting_rows], "columns": columns}


# ------------------------------------------------------------------ raise


def _number(db: Session) -> str:
    from app.services import numbering_defaults
    from app.services.company_scope import resolve_write_company_id
    from app.services.numbering_service import NumberingService

    company_id = resolve_write_company_id(get_company_scope(db), ambiguous=None)
    service = NumberingService(db)
    today = (_now() + MYT).date()  # the Malaysian day, not the server's
    number = service.get_next_number(
        JOB_NUMBER_DOC_TYPE, reference_date=today, company_id=company_id, commit_rule=False
    )
    if not number and company_id:
        # A company that never had the rule (added after the migration) gets it on first use.
        numbering_defaults.seed_service_job_rule(db, company_id=company_id)
        db.flush()
        number = service.get_next_number(
            JOB_NUMBER_DOC_TYPE, reference_date=today, company_id=company_id, commit_rule=False
        )
    if not number:
        raise AppException(
            status_code=409,
            message="Service job numbering is not set up for this company.",
            code="service_job_numbering_missing",
        )
    return number


def live_job_row(db: Session, complaint_id: str):
    return (
        _base_query(db, None)
        .filter(ServiceJob.complaint_id == str(complaint_id), Status.key.notin_(DEAD_KEYS))
        .order_by(ServiceJob.created_at.desc())
        .first()
    )


def _live_job_elsewhere(db: Session, complaint_id: str) -> bool:
    """A live job in ANY company (raw SQL: the company filter must not hide it)."""
    from sqlalchemy import text

    row = db.execute(
        text(
            "select 1 from service_jobs j join statuses s on s.id = j.status_id "
            "where j.complaint_id = :c and s.key not in ('cancelled', 'verified') limit 1"
        ),
        {"c": str(complaint_id)},
    ).first()
    return row is not None


def raise_job(
    db: Session,
    complaint_id: str,
    actor_id: Optional[str],
    limit: Optional[Limit] = None,
    *,
    commit: bool = True,
) -> Tuple[Dict[str, Any], bool]:
    """Raise a job for a complaint (any complaint status). Returns ``(job, created)``.

    Commits on creation unless ``commit=False``. Idempotent: a live job is returned as is.
    """
    complaint = _get_complaint(db, complaint_id, limit, lock=True)
    existing = live_job_row(db, complaint.id)
    if existing is not None:
        return serialize(existing), False
    if _live_job_elsewhere(db, complaint.id):
        # Complaints are company-global, so one live job per complaint holds across companies.
        raise AppException(
            status_code=409,
            message="This complaint already has a live service job in another company.",
            code="service_job_live_elsewhere",
        )

    proposed = status_by_key(db, "proposed")
    if proposed is None:
        raise AppException(
            status_code=409,
            message="The service job status graph is not set up.",
            code="service_job_graph_missing",
        )
    job = ServiceJob(
        id=str(uuid.uuid4()),
        job_number=_number(db),
        complaint_id=complaint.id,
        status_id=proposed.id,
        created_by=str(actor_id) if actor_id else None,
        created_at=_now(),
    )
    db.add(job)
    db.flush()
    job_id = job.id
    if commit:
        db.commit()
    return get_job(db, job_id, limit), True


# ------------------------------------------------------------------ moves


def _check_edge(db: Session, job: ServiceJob, key: str) -> Status:
    """The target status when the graph declares the edge, else 409. Same-status is not an edge."""
    from app.services import status_service

    target = status_by_key(db, key)
    if target is None:
        raise AppException(
            status_code=409,
            message="The service job status graph is not set up.",
            code="service_job_graph_missing",
        )
    illegal = AppException(
        status_code=409,
        message="That move is not allowed from the job's current step.",
        code="service_job_move_not_allowed",
    )
    if job.status_id == target.id:
        raise illegal
    try:
        status_service.assert_transition_allowed(db, SERVICE_JOB_ENTITY_TYPE, job.status_id, target.id)
    except AppException:
        raise illegal
    return target


def _move_to(db: Session, job: ServiceJob, key: str) -> None:
    job.status_id = _check_edge(db, job, key).id
    job.updated_at = _now()


def _current_key(db: Session, job: ServiceJob) -> Optional[str]:
    if not job.status_id:
        return None
    return db.query(Status.key).filter(Status.id == job.status_id).scalar()


def _lock_job(db: Session, job_id: str, limit: Optional[Limit]) -> ServiceJob:
    row = get_row(db, job_id, limit)
    job = row[0]
    db.query(ServiceJob).filter(ServiceJob.id == job.id).with_for_update().first()
    db.refresh(job)
    return job


def confirm(
    db: Session,
    job_id: str,
    *,
    scheduled_from: datetime,
    scheduled_to: Optional[datetime],
    customer_agreed_by: str,
    limit: Optional[Limit] = None,
) -> Dict[str, Any]:
    start, end = to_naive_utc(scheduled_from), to_naive_utc(scheduled_to)
    if end is not None and end < start:
        raise AppException(
            status_code=422,
            message="scheduled_to must not be before scheduled_from.",
            code="service_job_schedule_invalid",
        )
    job = _lock_job(db, job_id, limit)
    _move_to(db, job, "confirmed")
    job.scheduled_from = start
    job.scheduled_to = end
    job.customer_agreed_by = customer_agreed_by.strip()
    job.rejection_reason = None
    db.commit()
    return get_job(db, job_id, limit)


def assign(db: Session, job_id: str, technician_id: str, limit: Optional[Limit] = None) -> Dict[str, Any]:
    job = _lock_job(db, job_id, limit)
    if _current_key(db, job) not in ("proposed", "confirmed"):
        raise AppException(
            status_code=409,
            message="A technician can only be assigned while the job is Proposed or Confirmed.",
            code="service_job_assign_not_allowed",
        )
    tech = (
        db.query(Technician)
        .filter(Technician.id == str(technician_id), Technician.company_id == job.company_id)
        .first()
        if _valid_uuid(technician_id)
        else None
    )
    if tech is None:
        raise AppException(status_code=422, message="technician_id: technician not found.", code="technician_not_found")
    if not tech.is_active:
        raise AppException(
            status_code=422,
            message="technician_id: that technician is inactive.",
            code="technician_inactive",
        )
    job.technician_id = tech.id
    job.updated_at = _now()
    db.commit()
    return get_job(db, job_id, limit)


def transition(
    db: Session, job_id: str, to: str, reason: Optional[str], limit: Optional[Limit] = None
) -> Dict[str, Any]:
    if to == "confirmed":
        raise AppException(
            status_code=422,
            message="to: use the confirm action to confirm a date.",
            code="service_job_use_confirm",
        )
    job = _lock_job(db, job_id, limit)
    target = _check_edge(db, job, to)
    if to in ("on_the_way", "arrived") and not job.technician_id:
        raise AppException(
            status_code=422,
            message="Assign a technician first.",
            code="service_job_technician_required",
        )
    reason = (reason or "").strip()
    if to in REASON_REQUIRED and not reason:
        raise AppException(status_code=422, message="reason is required for this move.", code="service_job_reason_required")
    job.status_id = target.id
    job.updated_at = _now()

    now = _now()
    if to == "arrived":
        job.arrived_at = now
        job.completed_at = None
    elif to == "completed":
        job.completed_at = now
    elif to == "verified":
        job.verified_at = now
    elif to == "proposed":
        job.scheduled_from = None
        job.scheduled_to = None
        job.customer_agreed_by = None
        job.arrived_at = None
        job.completed_at = None
        job.rejection_reason = reason
    elif to == "cancelled":
        job.cancel_reason = reason
    db.commit()
    return get_job(db, job_id, limit)
