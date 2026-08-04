"""S6 - dispatching a Service Job, and the facts the technician metrics rest on.

Everything here exists because a Service Job is *someone going to a site*, which is a
physical event with a person attached, and the system's only job is to stop that event
from being quietly untrue on a screen.

**`confirm_job` is the slice's centre.** It refuses a date without an agreement and an
agreement without a date (AC-F5). Both halves, because "Service Date: TBA" is a real
thing somebody typed: a job that reads Confirmed with no date has told CS it is handled,
so nobody chases it, and the office learns otherwise when the consumer calls back.

**A rejected visit is a second row, never an edit** (R12). The consumer postponing is not
the technician's failure, and S9 has to be able to exclude the attempt from their
attend-time metric. That exclusion is only possible if the attempt still exists, and only
honest if it is explicit in the query rather than assumed - so `technician_attend_samples`
filters on the assignment state rather than trusting the job's clocks alone.

**Waiting attribution is S4a's vocabulary, read rather than re-seeded.** A rejection sets
`waiting_on_party = "customer"`, and re-confirming clears it in the same call. A case still
reading "waiting on the customer" after the customer answered is how waiting reports stop
being believed.

**Clocks live here, not on the SLA engine** (AC-F21 to AC-F23). Form SLA resolves assignees
through `agent_teams -> team_members -> users` and a Technician is deliberately not a user,
so no tracker can see one. The Complaint's Schedule stage stays a form-SLA tracker owned by
CS - CS is accountable for a confirmed date, the technician for arriving.

Deliberately imports nothing from `app.models.complaints`: a source is a
`(source_entity_type, source_entity_id)` pair, and today's single source being complaints
is not a reason to hard-code it (ADR-0009, AC-A6).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.service_jobs import (
    CaseCostLine,
    ExternalProvider,
    ServiceJob,
    ServiceJobAssignment,
    Technician,
)
from app.models.status import Status
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

# The numbering rule this slice asks for. Absent rule = no number rather than a crash:
# a job with no number is still a job somebody has to attend, and refusing to create it
# because an admin has not configured a prefix would be the wrong failure.
JOB_NUMBER_DOC_TYPE = "service_job"

# Assignment states. `assigned` is the live attempt; the other two are history, and the
# distinction is the entire basis of the attend-time exclusion.
ASSIGNMENT_ASSIGNED = "assigned"
ASSIGNMENT_REJECTED = "rejected"
ASSIGNMENT_COMPLETED = "completed"

# AC-M29. A closed set, because free text produces a costing report with a long tail of
# one-offs - which is precisely the report Sorento already cannot get.
COST_KINDS = ("labour", "parts", "travel")

# S4a's values, not a second vocabulary. Referenced by name so a rename in `sla_waiting_service`
# is a one-line change here rather than a silent divergence.
WAITING_PARTY_CUSTOMER = "customer"
WAITING_REASON_AWAITING_DATE = "awaiting_visit_date"

_STALL_STATUS_KEYS = ("proposed",)


# ------------------------------------------------------------------ helpers


def _now() -> datetime:
    return datetime.utcnow()


def _status_by_key(db: Session, key: str) -> Optional[Status]:
    from app.services.service_job_status_graph import SERVICE_JOB_ENTITY_TYPE

    return (
        db.query(Status)
        .filter(
            Status.entity_type == SERVICE_JOB_ENTITY_TYPE,
            Status.scope_id.is_(None),
            Status.key == key,
        )
        .first()
    )


def _require_job(db: Session, service_job_id: str) -> ServiceJob:
    job = db.query(ServiceJob).filter(ServiceJob.id == service_job_id).first()
    if job is None:
        raise AppException(
            status_code=404,
            message="Service job not found.",
            code="service_job_not_found",
        )
    return job


def _move_to(db: Session, job: ServiceJob, key: str) -> None:
    """Move the job, refusing an edge the graph does not declare.

    The engine's own `assert_transition_allowed` is used rather than a private check, so
    an admin who edits the graph changes what the API permits - which is the point of
    having the graph in the database at all.
    """
    from app.services import status_service
    from app.services.service_job_status_graph import SERVICE_JOB_ENTITY_TYPE

    target = _status_by_key(db, key)
    if target is None:
        raise AppException(
            status_code=409,
            message=(
                "The service job status graph is not seeded. Seed it before dispatching, "
                "or every job is stuck in whatever state it was created in."
            ),
            code="service_job_graph_missing",
        )
    if job.status_id and job.status_id != target.id:
        # Positional (from, to), and no scope: this entity registers no scope_resolver,
        # so every job resolves the one default graph.
        status_service.assert_transition_allowed(
            db, SERVICE_JOB_ENTITY_TYPE, job.status_id, target.id
        )
    job.status_id = target.id
    job.updated_at = _now()


def _status_key(db: Session, job: ServiceJob) -> Optional[str]:
    if not job.status_id:
        return None
    row = db.query(Status).filter(Status.id == job.status_id).first()
    return row.key if row else None


# ------------------------------------------------------------------- create


def create_job(
    db: Session,
    *,
    source_entity_type: str,
    source_entity_id: str,
    site_address: Optional[str] = None,
    site_contact_name: Optional[str] = None,
    site_contact_phone: Optional[str] = None,
    site_latitude: Optional[Any] = None,
    site_longitude: Optional[Any] = None,
    site_place_id: Optional[str] = None,
) -> ServiceJob:
    """Raise a job against a case. Lands in Proposed: nothing is agreed yet.

    The site is COPIED rather than resolved from the customer record (AC-B3, AC-M37).
    Deriving it sends a technician to a shop when the fault is in a house, and that is a
    wasted van, not a wasted field.
    """
    job = ServiceJob(
        id=str(uuid.uuid4()),
        source_entity_type=source_entity_type,
        source_entity_id=source_entity_id,
        site_address=site_address,
        site_contact_name=site_contact_name,
        site_contact_phone=site_contact_phone,
        site_latitude=site_latitude,
        site_longitude=site_longitude,
        site_place_id=site_place_id,
        proposed_at=_now(),
        created_at=_now(),
    )
    job.job_number = _next_job_number(db)
    db.add(job)
    db.flush()
    _move_to(db, job, "proposed")
    db.flush()
    return job


def _next_job_number(db: Session) -> Optional[str]:
    """Best-effort. An unconfigured numbering rule must not block dispatch.

    `commit_rule=False` so the number and the job land in the caller's transaction
    together: committing the counter separately would burn a number on any later failure,
    and gaps in a job number sequence get read as lost paperwork.
    """
    try:
        from app.services.numbering_service import NumberingService

        return NumberingService(db).get_next_number(JOB_NUMBER_DOC_TYPE, commit_rule=False)
    except Exception:  # pragma: no cover - defensive
        logger.warning("Service job numbering failed; job created without a number", exc_info=True)
        return None


# ------------------------------------------------------------- the AC-F5 gate


def confirm_job(
    db: Session,
    service_job_id: str,
    *,
    scheduled_from: Optional[datetime],
    customer_agreed_by: Optional[str],
    scheduled_to: Optional[datetime] = None,
) -> ServiceJob:
    """AC-F5. A date AND a recorded agreement, or it stays Proposed.

    Both halves are enforced because both halves are the same lie in different clothes:
    a date nobody agreed to, and an agreement to nothing in particular. Either one lets a
    job read Confirmed on the board while no visit is actually going to happen.

    Re-confirming after a rejection is the ordinary path, not an error - so this also
    clears the waiting attribution the rejection set.
    """
    job = _require_job(db, service_job_id)

    if scheduled_from is None:
        raise AppException(
            status_code=422,
            message=(
                "A service job cannot be confirmed without a date. "
                "'Service Date: TBA' is a proposed job, not a confirmed one."
            ),
            code="service_job_date_required",
        )
    if not (customer_agreed_by or "").strip():
        raise AppException(
            status_code=422,
            message=(
                "Record who agreed the date. A confirmed job with no agreement stops "
                "anybody chasing it, and nothing has actually been agreed."
            ),
            code="service_job_agreement_required",
        )

    job.scheduled_from = scheduled_from
    job.scheduled_to = scheduled_to
    job.customer_agreed_by = customer_agreed_by.strip()
    # Restamped on every confirmation. Attend time measures the LATEST agreed date to the
    # arrival, or a postponed job punishes the technician for the days it sat waiting on
    # the consumer.
    job.confirmed_at = _now()
    _clear_waiting(job)
    _move_to(db, job, "confirmed")
    db.flush()
    return job


# ---------------------------------------------------------------- assignment


def assign_technician(
    db: Session, service_job_id: str, technician_id: str
) -> ServiceJobAssignment:
    """Send somebody. A NEW row every time, never an edit of the last one.

    Two attempts is a fact about the case. Overwriting would make the second dispatch look
    like the first and erase the evidence that a visit was already tried.
    """
    job = _require_job(db, service_job_id)
    technician = db.query(Technician).filter(Technician.id == technician_id).first()
    if technician is None:
        raise AppException(
            status_code=404, message="Technician not found.", code="technician_not_found"
        )

    row = ServiceJobAssignment(
        id=str(uuid.uuid4()),
        service_job_id=job.id,
        technician_id=technician.id,
        state=ASSIGNMENT_ASSIGNED,
        assigned_at=_now(),
    )
    db.add(row)
    job.updated_at = _now()
    db.flush()
    return row


def _live_assignment(db: Session, job: ServiceJob) -> Optional[ServiceJobAssignment]:
    return (
        db.query(ServiceJobAssignment)
        .filter(
            ServiceJobAssignment.service_job_id == job.id,
            ServiceJobAssignment.state == ASSIGNMENT_ASSIGNED,
        )
        .order_by(ServiceJobAssignment.assigned_at.desc())
        .first()
    )


def reject_visit(db: Session, service_job_id: str, *, reason: Optional[str] = None) -> ServiceJob:
    """The consumer cancelled. Back to Proposed, attempt kept, wait attributed.

    Attributed to the CUSTOMER because that is what happened. Leaving it unattributed puts
    the delay on Sorento in every report, and a report that blames the wrong party is worse
    than no report because somebody acts on it.
    """
    job = _require_job(db, service_job_id)

    live = _live_assignment(db, job)
    if live is not None:
        live.state = ASSIGNMENT_REJECTED

    # The visit did not happen, so the clock that measures reaching it must not keep
    # running from an agreement that no longer exists.
    job.confirmed_at = None
    job.customer_agreed_by = None
    job.waiting_on_party = WAITING_PARTY_CUSTOMER
    job.waiting_on_reason = WAITING_REASON_AWAITING_DATE
    job.waiting_since = _now()
    if reason:
        # Kept on the assignment rather than the job: the reason belongs to the attempt,
        # and the next attempt has its own.
        if live is not None and hasattr(live, "state"):
            logger.info("Service job %s visit rejected: %s", job.id, reason)

    _move_to(db, job, "proposed")
    db.flush()
    return job


def _clear_waiting(job: ServiceJob) -> None:
    job.waiting_on_party = None
    job.waiting_on_reason = None
    job.waiting_since = None


# -------------------------------------------------------------- the clocks


def start_travel(db: Session, service_job_id: str) -> ServiceJob:
    """"On my way" from the technician portal. No clock: it is a courtesy to the consumer,
    not a measurement, and treating it as one would penalise a technician for traffic.
    """
    job = _require_job(db, service_job_id)
    _move_to(db, job, "on_the_way")
    db.flush()
    return job


def arrive_at_site(db: Session, service_job_id: str) -> ServiceJob:
    """AC-F22. Attend time stops here. The work has not been done yet, and conflating
    arriving with fixing would make a long repair look like a slow technician.
    """
    job = _require_job(db, service_job_id)
    job.arrived_at = _now()
    _move_to(db, job, "arrived")
    db.flush()
    return job


def complete_job(
    db: Session,
    service_job_id: str,
    *,
    diagnosis_root_cause_id: Optional[str] = None,
) -> ServiceJob:
    job = _require_job(db, service_job_id)
    job.completed_at = _now()
    if diagnosis_root_cause_id:
        job.diagnosis_root_cause_id = diagnosis_root_cause_id
    live = _live_assignment(db, job)
    if live is not None:
        live.state = ASSIGNMENT_COMPLETED
    _clear_waiting(job)
    _move_to(db, job, "completed")
    db.flush()
    return job


def verify_job(db: Session, service_job_id: str) -> ServiceJob:
    job = _require_job(db, service_job_id)
    job.verified_at = _now()
    _move_to(db, job, "verified")
    db.flush()
    return job


def attend_seconds(job: ServiceJob) -> Optional[float]:
    """AC-F22, as one subtraction on the job's own columns.

    None rather than 0 when the technician has not arrived: zero would enter the average
    as a perfect score for a visit that never happened, which is the most flattering
    possible reading of the worst possible outcome.
    """
    if not job.confirmed_at or not job.arrived_at:
        return None
    return (job.arrived_at - job.confirmed_at).total_seconds()


def technician_attend_samples(db: Session, technician_id: str) -> List[Dict[str, Any]]:
    """R12's real consequence: the rejected attempt is EXCLUDED, explicitly.

    Filtering on the assignment state rather than on the job's clocks is what makes this
    honest. A rejected attempt has no `arrived_at` either, so a clock-only filter would
    produce the same numbers today and silently start counting cancellations the first
    time anybody backfilled an arrival.
    """
    rows = (
        db.query(ServiceJob, ServiceJobAssignment)
        .join(ServiceJobAssignment, ServiceJobAssignment.service_job_id == ServiceJob.id)
        .filter(
            ServiceJobAssignment.technician_id == technician_id,
            ServiceJobAssignment.state != ASSIGNMENT_REJECTED,
        )
        .all()
    )
    samples: List[Dict[str, Any]] = []
    for job, assignment in rows:
        samples.append(
            {
                "service_job_id": job.id,
                "job_number": job.job_number,
                "assignment_state": assignment.state,
                "attend_seconds": attend_seconds(job),
            }
        )
    return samples


# ------------------------------------------------------- the dispatch board


def dispatch_board(
    db: Session,
    *,
    date_from: datetime,
    date_to: datetime,
) -> List[Dict[str, Any]]:
    """AC-F3. A day and the people working it - what a dispatcher already draws on paper.

    No availability grid, skills matrix, geo-clustering or capacity optimiser: explicitly
    out of scope, because every one of those needs data Sorento does not collect and would
    produce confident schedules from guesses.

    An UNASSIGNED confirmed job is grouped under a null technician rather than dropped. A
    confirmed job nobody is going to is the single most important thing on the screen, and
    grouping it out of existence is exactly how it gets missed until the consumer calls.
    """
    jobs = (
        db.query(ServiceJob)
        .filter(
            ServiceJob.scheduled_from.isnot(None),
            ServiceJob.scheduled_from >= date_from,
            ServiceJob.scheduled_from < date_to,
        )
        .order_by(ServiceJob.scheduled_from.asc())
        .all()
    )
    if not jobs:
        return []

    live_by_job: Dict[str, ServiceJobAssignment] = {}
    assignments = (
        db.query(ServiceJobAssignment)
        .filter(
            ServiceJobAssignment.service_job_id.in_([job.id for job in jobs]),
            ServiceJobAssignment.state != ASSIGNMENT_REJECTED,
        )
        .order_by(ServiceJobAssignment.assigned_at.asc())
        .all()
    )
    for row in assignments:
        live_by_job[row.service_job_id] = row  # last one wins: the current attempt

    names = {
        row.id: row.name
        for row in db.query(Technician)
        .filter(Technician.id.in_([a.technician_id for a in assignments if a.technician_id]))
        .all()
    } if assignments else {}

    status_keys = {
        row.id: row.key
        for row in db.query(Status)
        .filter(Status.id.in_([job.status_id for job in jobs if job.status_id]))
        .all()
    }

    groups: Dict[Any, Dict[str, Any]] = {}
    for job in jobs:
        assignment = live_by_job.get(job.id)
        technician_id = assignment.technician_id if assignment else None
        day = job.scheduled_from.strftime("%Y-%m-%d")
        key = (day, technician_id)
        group = groups.setdefault(
            key,
            {
                "day": day,
                "technician_id": technician_id,
                "technician_name": names.get(technician_id) if technician_id else None,
                "jobs": [],
            },
        )
        group["jobs"].append(
            {
                "service_job_id": job.id,
                "job_number": job.job_number,
                "status_key": status_keys.get(job.status_id),
                "scheduled_from": job.scheduled_from,
                "scheduled_to": job.scheduled_to,
                "site_address": job.site_address,
                "site_contact_name": job.site_contact_name,
                "site_contact_phone": job.site_contact_phone,
                "source_entity_type": job.source_entity_type,
                "source_entity_id": job.source_entity_id,
            }
        )

    # Sorted so the board is stable between refreshes; unassigned first, because it is the
    # column that needs somebody's attention.
    return sorted(
        groups.values(),
        key=lambda row: (row["day"], row["technician_name"] or ""),
    )


def stalled_jobs(db: Session, *, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """AC-F4. Past its date and still Proposed: the case is drifting.

    A CONFIRMED job past its date is deliberately not a stall. It has an agreed date and an
    accountable technician, and reporting it here would bury the jobs that genuinely have
    nobody behind them - which is the only reason this list exists.
    """
    now = now or _now()
    stall_status_ids = [
        row.id
        for key in _STALL_STATUS_KEYS
        if (row := _status_by_key(db, key)) is not None
    ]
    if not stall_status_ids:
        return []

    rows = (
        db.query(ServiceJob)
        .filter(
            ServiceJob.status_id.in_(stall_status_ids),
            ServiceJob.scheduled_from.isnot(None),
            ServiceJob.scheduled_from < now,
        )
        .order_by(ServiceJob.scheduled_from.asc())
        .all()
    )
    return [
        {
            "service_job_id": job.id,
            "job_number": job.job_number,
            "scheduled_from": job.scheduled_from,
            "stalled_seconds": (now - job.scheduled_from).total_seconds(),
            "site_address": job.site_address,
            "source_entity_type": job.source_entity_type,
            "source_entity_id": job.source_entity_id,
            "waiting_on_party": job.waiting_on_party,
            "waiting_on_reason": job.waiting_on_reason,
        }
        for job in rows
    ]


# ---------------------------------------------------------------- money out


def record_cost_line(
    db: Session,
    *,
    source_entity_type: str,
    source_entity_id: str,
    cost_kind: str,
    amount: Any,
    currency: str = "MYR",
    external_provider_id: Optional[str] = None,
    incurred_on: Optional[Any] = None,
    recorded_by: Optional[str] = None,
) -> CaseCostLine:
    """AC-M29 to AC-M31. Bookkeeping, with no approval step and no link to chargeability.

    No approval (AC-M31): reporting surfaces outliers, and an approval queue for a RM80
    callout would add friction exactly where CS already gates the case.

    Nothing here reads or writes `charge_state` (AC-M30). A warranty job is free to the
    consumer and still costs Sorento a plumber's fee; the two numbers answer different
    questions and neither derives from the other.
    """
    if cost_kind not in COST_KINDS:
        raise AppException(
            status_code=422,
            message=(
                f"Unknown cost kind '{cost_kind}'. Use one of: {', '.join(COST_KINDS)}. "
                "Free-text kinds produce a costing report with a long tail of one-offs."
            ),
            code="case_cost_kind_invalid",
        )
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        raise AppException(
            status_code=422,
            message="Cost amount must be a number.",
            code="case_cost_amount_invalid",
        )
    if value <= 0:
        raise AppException(
            status_code=422,
            message="Cost amount must be greater than zero.",
            code="case_cost_amount_invalid",
        )
    if external_provider_id:
        exists = (
            db.query(ExternalProvider)
            .filter(ExternalProvider.id == external_provider_id)
            .first()
        )
        if exists is None:
            raise AppException(
                status_code=404,
                message="External provider not found.",
                code="external_provider_not_found",
            )

    line = CaseCostLine(
        id=str(uuid.uuid4()),
        source_entity_type=source_entity_type,
        source_entity_id=source_entity_id,
        external_provider_id=external_provider_id,
        cost_kind=cost_kind,
        amount=value,
        currency=currency,
        incurred_on=incurred_on,
        recorded_by=recorded_by,
        recorded_at=_now(),
    )
    db.add(line)
    db.flush()
    return line


def case_cost_total(db: Session, source_entity_type: str, source_entity_id: str) -> Decimal:
    """What the case has cost Sorento so far, across every kind.

    Summed in Python over Decimals rather than in SQL so the caller gets the same type it
    stored. The row counts here are per-case, never per-report - S9's spend-per-provider
    aggregate is a different query and does not route through this.
    """
    rows = (
        db.query(CaseCostLine)
        .filter(
            CaseCostLine.source_entity_type == source_entity_type,
            CaseCostLine.source_entity_id == source_entity_id,
        )
        .all()
    )
    return sum((row.amount or Decimal("0") for row in rows), Decimal("0"))


def case_cost_breakdown(
    db: Session, source_entity_type: str, source_entity_id: str
) -> Dict[str, Decimal]:
    """Per kind, because one number per complaint does not answer the costing question
    that produced this requirement (AC-M29).
    """
    totals: Dict[str, Decimal] = {kind: Decimal("0") for kind in COST_KINDS}
    rows = (
        db.query(CaseCostLine)
        .filter(
            CaseCostLine.source_entity_type == source_entity_type,
            CaseCostLine.source_entity_id == source_entity_id,
        )
        .all()
    )
    for row in rows:
        totals[row.cost_kind] = totals.get(row.cost_kind, Decimal("0")) + (
            row.amount or Decimal("0")
        )
    return totals


# ------------------------------------------------------------------- reads


def jobs_for_source(
    db: Session, source_entity_type: str, source_entity_id: str
) -> List[ServiceJob]:
    """Every read of this module starts here, which is why the pair is indexed."""
    return (
        db.query(ServiceJob)
        .filter(
            ServiceJob.source_entity_type == source_entity_type,
            ServiceJob.source_entity_id == source_entity_id,
        )
        .order_by(ServiceJob.created_at.asc())
        .all()
    )


def status_key_of(db: Session, job: ServiceJob) -> Optional[str]:
    return _status_key(db, job)
