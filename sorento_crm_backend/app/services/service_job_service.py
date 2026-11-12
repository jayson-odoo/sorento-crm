"""After-sales P1: creating, moving and listing service jobs.

A job carries its own customer, contact, site and problem. It may name a complaint as a plain
reference (owner ruling 12 Nov 2026: the live Complaints module is untouched), read-only here.
Rules live here; the router only gates permissions and shapes HTTP.

* One live job per related complaint (any status except cancelled and verified); an advisory lock
  makes two simultaneous creates leave one.
* Every move goes through the status graph; an illegal move is 409 and changes nothing.
* ``scheduled_from`` is stored as naive UTC. The board's day is the Malaysian day (UTC+8).
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import asc, desc, false, or_, text
from sqlalchemy.orm import Session

from app.models.base import get_company_scope
from app.models.complaints import Complaint
from app.models.service_jobs import ServiceJob, Technician
from app.models.status import Status
from app.services.error_handler import AppException, handle_not_found
from app.services.project_party_contact_service import clean_phone, display_phone
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


def _base_query(db: Session):
    """Jobs with their status, technician and (optional) related complaint. Visibility is the module's
    permissions and the company filter only: a related complaint is a plain reference, read-only."""
    return (
        db.query(ServiceJob, Status, Technician, Complaint)
        .outerjoin(Complaint, Complaint.id == ServiceJob.complaint_id)
        .outerjoin(Status, Status.id == ServiceJob.status_id)
        .outerjoin(Technician, Technician.id == ServiceJob.technician_id)
    )


def serialize(row: Tuple[ServiceJob, Optional[Status], Optional[Technician], Optional[Complaint]]) -> Dict[str, Any]:
    job, status, tech, complaint = row
    return {
        "id": job.id,
        "job_number": job.job_number,
        "complaint_id": job.complaint_id,
        "complaint_number": complaint.complaint_number if complaint is not None else None,
        "customer_name": job.customer_name,
        "contact_name": job.contact_name,
        "contact_phone": job.contact_phone,
        "contact_phone_display": display_phone(job.contact_phone),
        "city": job.site_city,
        "site_address_line1": job.site_address_line1,
        "site_address_line2": job.site_address_line2,
        "site_postcode": job.site_postcode,
        "site_state": job.site_state,
        "site_country": job.site_country,
        "problem": job.problem,
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


def get_row(db: Session, job_id: str):
    if not _valid_uuid(job_id):
        raise handle_not_found("Service job", str(job_id))
    row = _base_query(db).filter(ServiceJob.id == str(job_id)).first()
    if row is None:
        raise handle_not_found("Service job", str(job_id))
    return row


def get_job(db: Session, job_id: str) -> Dict[str, Any]:
    db.expire_all()
    return serialize(get_row(db, job_id))


SORTS = {
    "job_number": lambda: ServiceJob.job_number,
    "complaint_number": lambda: Complaint.complaint_number,
    "status": lambda: Status.sort_order,
    "scheduled_from": lambda: ServiceJob.scheduled_from,
    "technician": lambda: Technician.name,
    "city": lambda: ServiceJob.site_city,
    "customer": lambda: ServiceJob.customer_name,
}


def list_jobs(
    db: Session,
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
    q = _base_query(db)
    if query and query.strip():
        like = f"%{query.strip()}%"
        q = q.filter(
            or_(
                ServiceJob.job_number.ilike(like),
                Complaint.complaint_number.ilike(like),
                ServiceJob.customer_name.ilike(like),
                ServiceJob.site_city.ilike(like),
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


def board(db: Session, day: date) -> Dict[str, Any]:
    start, end = myt_day_bounds(day)
    # Every Proposed job is waiting for a date, whatever day is picked: oldest raised first.
    waiting_rows = (
        _base_query(db)
        .filter(Status.key == "proposed")
        .order_by(ServiceJob.created_at.asc(), ServiceJob.id)
        .limit(500)
        .all()
    )

    day_rows = (
        _base_query(db)
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
        if tech is None:
            unassigned.append(data)
            continue
        col = by_tech.setdefault(
            tech.id, {"technician_id": tech.id, "technician_name": tech.name, "jobs": []}
        )
        col["jobs"].append(data)

    columns = [{"technician_id": None, "technician_name": "Unassigned", "jobs": unassigned}]
    columns += sorted(by_tech.values(), key=lambda c: (c["technician_name"] or "").lower())
    return {"day": day.isoformat(), "waiting": [serialize(r) for r in waiting_rows], "columns": columns}


# ------------------------------------------------------------------ create and edit

DETAIL_FIELDS = (
    "customer_name",
    "contact_name",
    "contact_phone",
    "site_address_line1",
    "site_address_line2",
    "site_postcode",
    "site_city",
    "site_state",
    "site_country",
    "problem",
)


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


def _clean_details(values: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key in DETAIL_FIELDS:
        if key not in values:
            continue
        value = values[key]
        if key == "contact_phone":
            out[key] = clean_phone(value)  # E.164, or a 422 naming a valid example
        else:
            text = " ".join(str(value).split()) if key != "problem" and value is not None else value
            out[key] = (str(text).strip() or None) if text is not None else None
    return out


def _live_job_for_complaint(db: Session, complaint_id: str, *, except_job_id: Optional[str] = None) -> bool:
    """A live job (any company: a complaint is company-global) already names this complaint."""
    row = db.execute(
        text(
            "select 1 from service_jobs j join statuses s on s.id = j.status_id "
            "where j.complaint_id = :c and s.key not in ('cancelled', 'verified') "
            "and (cast(:skip as text) is null or j.id::text <> :skip) limit 1"
        ),
        {"c": str(complaint_id), "skip": except_job_id},
    ).first()
    return row is not None


def _check_related_complaint(db: Session, complaint_id: Optional[str], *, except_job_id: Optional[str] = None) -> None:
    if not complaint_id:
        return
    exists = _valid_uuid(complaint_id) and db.execute(
        text("select 1 from complaints where id::text = :c"), {"c": str(complaint_id)}
    ).first()
    if not exists:
        raise AppException(status_code=422, message="complaint_id: complaint not found.", code="complaint_not_found")
    # One at a time per complaint; the advisory lock makes two simultaneous creates leave one.
    db.execute(text("select pg_advisory_xact_lock(hashtext(:c))"), {"c": str(complaint_id)})
    if _live_job_for_complaint(db, complaint_id, except_job_id=except_job_id):
        raise AppException(
            status_code=409,
            message="This complaint already has a live service job.",
            code="service_job_live_exists",
        )


def create_job(db: Session, values: Dict[str, Any], actor_id: Optional[str]) -> Dict[str, Any]:
    """Create a job in Proposed, numbered, with its own customer, contact, site and problem."""
    details = _clean_details(values)
    if not details.get("customer_name"):
        raise AppException(status_code=422, message="customer_name is required.", code="service_job_customer_required")
    complaint_id = values.get("complaint_id") or None
    _check_related_complaint(db, complaint_id)
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
        complaint_id=complaint_id,
        status_id=proposed.id,
        created_by=str(actor_id) if actor_id else None,
        created_at=_now(),
        **details,
    )
    db.add(job)
    db.flush()
    job_id = job.id
    db.commit()
    return get_job(db, job_id)


def update_job(db: Session, job_id: str, values: Dict[str, Any]) -> Dict[str, Any]:
    """Edit a job's own details (the same fields as create). Status and schedule move through their actions."""
    job = _lock_job(db, job_id)
    details = _clean_details(values)
    if "customer_name" in details and not details["customer_name"]:
        raise AppException(status_code=422, message="customer_name is required.", code="service_job_customer_required")
    if "complaint_id" in values:
        complaint_id = values.get("complaint_id") or None
        if complaint_id != job.complaint_id:
            _check_related_complaint(db, complaint_id, except_job_id=job.id)
        job.complaint_id = complaint_id
    for key, value in details.items():
        setattr(job, key, value)
    job.updated_at = _now()
    db.commit()
    return get_job(db, job_id)


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


def _lock_job(db: Session, job_id: str) -> ServiceJob:
    row = get_row(db, job_id)
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
) -> Dict[str, Any]:
    start, end = to_naive_utc(scheduled_from), to_naive_utc(scheduled_to)
    if end is not None and end < start:
        raise AppException(
            status_code=422,
            message="scheduled_to must not be before scheduled_from.",
            code="service_job_schedule_invalid",
        )
    job = _lock_job(db, job_id)
    _move_to(db, job, "confirmed")
    job.scheduled_from = start
    job.scheduled_to = end
    job.customer_agreed_by = customer_agreed_by.strip()
    job.rejection_reason = None
    db.commit()
    return get_job(db, job_id)


def assign(db: Session, job_id: str, technician_id: str) -> Dict[str, Any]:
    job = _lock_job(db, job_id)
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
    return get_job(db, job_id)


def transition(
    db: Session, job_id: str, to: str, reason: Optional[str]
) -> Dict[str, Any]:
    if to == "confirmed":
        raise AppException(
            status_code=422,
            message="to: use the confirm action to confirm a date.",
            code="service_job_use_confirm",
        )
    job = _lock_job(db, job_id)
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
    return get_job(db, job_id)
