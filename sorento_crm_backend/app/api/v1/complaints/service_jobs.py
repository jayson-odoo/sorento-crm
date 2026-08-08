"""S6 - the dispatch board, the job actions, and what a case cost.

Three permission levels, and the split is about trust rather than screens. `view` reads
the board; `dispatch` commits a person to a place at a time; `case_costs.manage` records
money leaving the company. A CS agent reading a case to answer the phone should not be one
misclick from re-assigning somebody's afternoon.

Every guard on a job's own rules lives in `service_job_service`, never here. The route
layer's whole job is to turn a request into that call: AC-F5 must hold for the technician
portal and for n8n exactly as it does for this API, and a check written in the route would
be a check the other two callers do not get.

**Reads accept an API key, writes do not.** `require_permission_with_api_key` is documented
as read-oriented: it resolves the act-as principal, and the two write paths that use it
(complaint close, PR approve) re-check the real end user at the assistant layer. Nothing
here has that second gate, so every write takes `require_permission` and only a logged-in
person can commit a technician to a site. Cost reads take the same real-user path despite
being reads: the amounts are what Sorento pays, and there is no automation asking for them.

Technician photos deliberately have NO endpoint in this module. They upload through the
shared attachment path against `entity_attachment_links` (AC-M21) - a per-domain
`service-jobs/{id}/photos` route would re-create exactly the special case the R5 grill
removed, and the validator would then live in two places.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.services import service_job_service
from app.services.error_handler import handle_internal_error
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()

VIEW_PERMISSION = "complaint_management.service_jobs.view"
DISPATCH_PERMISSION = "complaint_management.service_jobs.dispatch"
COST_PERMISSION = "complaint_management.case_costs.manage"


# ------------------------------------------------------------------ schemas


class ServiceJobCreate(BaseModel):
    """The source is a polymorphic pair, not a complaint id (ADR-0009, AC-A6).

    Today every job comes from a complaint. Accepting `complaint_id` here would make the
    first job raised from anything else an API change rather than a different string.
    """

    source_entity_type: str = Field(..., min_length=1, max_length=40)
    source_entity_id: str = Field(..., min_length=1)
    site_address: Optional[str] = None
    site_contact_name: Optional[str] = None
    site_contact_phone: Optional[str] = None
    site_latitude: Optional[float] = None
    site_longitude: Optional[float] = None
    site_place_id: Optional[str] = None


class ServiceJobFromSource(BaseModel):
    """Name the case; the server reads the site off it.

    Deliberately carries NO site fields. See `raise_service_job_from_source` for why the
    client is not trusted with that copy.
    """

    source_entity_type: str = Field(..., min_length=1, max_length=40)
    source_entity_id: str = Field(..., min_length=1)


class ServiceJobConfirm(BaseModel):
    """Both fields are required by the service, not by pydantic.

    Deliberate: a 422 from `confirm_job` carries the sentence explaining WHY a date
    without an agreement is not a confirmation, and pydantic's "field required" does not.
    The people hitting this are dispatchers, and the message is the point.
    """

    scheduled_from: Optional[datetime] = None
    scheduled_to: Optional[datetime] = None
    customer_agreed_by: Optional[str] = None


class ServiceJobAssign(BaseModel):
    technician_id: str = Field(..., min_length=1)


class ServiceJobReject(BaseModel):
    reason: Optional[str] = None


class ServiceJobComplete(BaseModel):
    diagnosis_root_cause_id: Optional[str] = None


class CaseCostLineCreate(BaseModel):
    source_entity_type: str = Field(..., min_length=1, max_length=40)
    source_entity_id: str = Field(..., min_length=1)
    cost_kind: str = Field(..., min_length=1, max_length=24)
    amount: Decimal
    currency: str = Field("MYR", max_length=3)
    external_provider_id: Optional[str] = None
    incurred_on: Optional[datetime] = None
    recorded_by: Optional[str] = None


def _serialize(db: Session, job) -> Dict[str, Any]:
    return {
        "id": job.id,
        "job_number": job.job_number,
        "source_entity_type": job.source_entity_type,
        "source_entity_id": job.source_entity_id,
        "status_key": service_job_service.status_key_of(db, job),
        "site_address": job.site_address,
        "site_contact_name": job.site_contact_name,
        "site_contact_phone": job.site_contact_phone,
        "site_latitude": float(job.site_latitude) if job.site_latitude is not None else None,
        "site_longitude": float(job.site_longitude) if job.site_longitude is not None else None,
        "site_place_id": job.site_place_id,
        "scheduled_from": job.scheduled_from,
        "scheduled_to": job.scheduled_to,
        "proposed_at": job.proposed_at,
        "confirmed_at": job.confirmed_at,
        "customer_agreed_by": job.customer_agreed_by,
        "arrived_at": job.arrived_at,
        "completed_at": job.completed_at,
        "verified_at": job.verified_at,
        "diagnosis_root_cause_id": job.diagnosis_root_cause_id,
        "charge_state": job.charge_state,
        "charge_amount": float(job.charge_amount) if job.charge_amount is not None else None,
        "waiting_on_party": job.waiting_on_party,
        "waiting_on_reason": job.waiting_on_reason,
        "waiting_since": job.waiting_since,
        # Computed rather than stored: a column would drift the moment anybody
        # backfilled a clock (AC-F22).
        "attend_seconds": service_job_service.attend_seconds(job),
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


# -------------------------------------------------------------------- reads


@router.get("/")
async def list_service_jobs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    query: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="Comma-separated status keys."),
    sort: str = Query("created_at"),
    dir: str = Query("desc"),
    current_user: dict = Depends(require_permission_with_api_key(VIEW_PERMISSION)),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Every job, findable without knowing which day it sits on.

    The board answers "who is working today". A job proposed with no date yet - the state
    every job starts in - is on no day at all, and a job confirmed for last Tuesday leaves
    the board the moment it moves on. Both then look like they vanished.
    """
    try:
        keys = [part.strip() for part in (status or "").split(",") if part.strip()]
        result = service_job_service.list_jobs(
            db,
            page=page,
            limit=limit,
            query=query,
            status_keys=keys or None,
            sort_field=sort,
            sort_dir=(dir or "desc").lower(),
        )
        return {
            **result,
            "data": [_serialize(db, job) for job in result["data"]],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/board")
async def get_dispatch_board(
    date_from: datetime = Query(...),
    date_to: datetime = Query(...),
    current_user: dict = Depends(require_permission_with_api_key(VIEW_PERMISSION)),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """AC-F3. Grouped by day and technician; unassigned jobs group under a null
    technician rather than disappearing.
    """
    try:
        return service_job_service.dispatch_board(db, date_from=date_from, date_to=date_to)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/stalls")
async def get_stalled_jobs(
    current_user: dict = Depends(require_permission_with_api_key(VIEW_PERMISSION)),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """AC-F4. Past their date and still proposed, with the elapsed stall time."""
    try:
        return service_job_service.stalled_jobs(db)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/by-source")
async def get_jobs_for_source(
    source_entity_type: str = Query(...),
    source_entity_id: str = Query(...),
    current_user: dict = Depends(require_permission_with_api_key(VIEW_PERMISSION)),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """The jobs for one case. Every read of this module starts here, which is why the
    polymorphic pair carries an index.
    """
    try:
        jobs = service_job_service.jobs_for_source(db, source_entity_type, source_entity_id)
        return [_serialize(db, job) for job in jobs]
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{service_job_id}")
async def get_service_job(
    service_job_id: str,
    current_user: dict = Depends(require_permission_with_api_key(VIEW_PERMISSION)),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        service_job_id = validate_uuid_path(service_job_id, resource="Service job")
        job = service_job_service._require_job(db, service_job_id)
        return _serialize(db, job)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


# ------------------------------------------------------------------ writes


@router.post("/")
async def create_service_job(
    payload: ServiceJobCreate,
    current_user: dict = Depends(require_permission(DISPATCH_PERMISSION)),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        job = service_job_service.create_job(db, **payload.model_dump())
        db.commit()
        return _serialize(db, job)
    except HTTPException:
        # AppException subclasses HTTPException, so a bare `except Exception` would
        # turn every domain 422 (AC-F5's refusal above all) into an opaque 500.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.post("/from-source")
async def raise_service_job_from_source(
    payload: ServiceJobFromSource,
    current_user: dict = Depends(require_permission(DISPATCH_PERMISSION)),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Raise a job for a case, with the server reading the Site off the case.

    The client names the case and nothing else. The Site is whatever was REPORTED (AC-B3),
    and a complaint routinely holds a dealer's shop in `customer_address` alongside the house
    the fault is in - letting the client post the address it had on screen would make that
    decision in a second place, and the second place is always the one that is wrong.
    """
    try:
        from app.services.service_job_intake import raise_job_for_source

        job = raise_job_for_source(
            db,
            source_entity_type=payload.source_entity_type,
            source_entity_id=payload.source_entity_id,
        )
        db.commit()
        return _serialize(db, job)
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.post("/{service_job_id}/confirm")
async def confirm_service_job(
    payload: ServiceJobConfirm,
    service_job_id: str,
    current_user: dict = Depends(require_permission(DISPATCH_PERMISSION)),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """AC-F5. Refused without BOTH a date and a recorded agreement."""
    try:
        service_job_id = validate_uuid_path(service_job_id, resource="Service job")
        job = service_job_service.confirm_job(
            db,
            service_job_id,
            scheduled_from=payload.scheduled_from,
            scheduled_to=payload.scheduled_to,
            customer_agreed_by=payload.customer_agreed_by,
        )
        db.commit()
        return _serialize(db, job)
    except HTTPException:
        # AppException subclasses HTTPException, so a bare `except Exception` would
        # turn every domain 422 (AC-F5's refusal above all) into an opaque 500.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.post("/{service_job_id}/assign")
async def assign_service_job(
    payload: ServiceJobAssign,
    service_job_id: str,
    current_user: dict = Depends(require_permission(DISPATCH_PERMISSION)),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """A NEW attempt every time. Re-assigning after a rejection does not rewrite who was
    sent the first time.
    """
    try:
        service_job_id = validate_uuid_path(service_job_id, resource="Service job")
        service_job_service.assign_technician(db, service_job_id, payload.technician_id)
        job = service_job_service._require_job(db, service_job_id)
        db.commit()
        return _serialize(db, job)
    except HTTPException:
        # AppException subclasses HTTPException, so a bare `except Exception` would
        # turn every domain 422 (AC-F5's refusal above all) into an opaque 500.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.post("/{service_job_id}/reject")
async def reject_service_job_visit(
    payload: ServiceJobReject,
    service_job_id: str,
    current_user: dict = Depends(require_permission(DISPATCH_PERMISSION)),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """The consumer cancelled. Back to proposed, attempt kept, wait attributed to the
    customer (R12).
    """
    try:
        service_job_id = validate_uuid_path(service_job_id, resource="Service job")
        job = service_job_service.reject_visit(db, service_job_id, reason=payload.reason)
        db.commit()
        return _serialize(db, job)
    except HTTPException:
        # AppException subclasses HTTPException, so a bare `except Exception` would
        # turn every domain 422 (AC-F5's refusal above all) into an opaque 500.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.post("/{service_job_id}/on-the-way")
async def start_service_job_travel(
    service_job_id: str,
    current_user: dict = Depends(require_permission(DISPATCH_PERMISSION)),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        service_job_id = validate_uuid_path(service_job_id, resource="Service job")
        job = service_job_service.start_travel(db, service_job_id)
        db.commit()
        return _serialize(db, job)
    except HTTPException:
        # AppException subclasses HTTPException, so a bare `except Exception` would
        # turn every domain 422 (AC-F5's refusal above all) into an opaque 500.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.post("/{service_job_id}/arrive")
async def arrive_at_service_job(
    service_job_id: str,
    current_user: dict = Depends(require_permission(DISPATCH_PERMISSION)),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """AC-F22. Attend time stops here, not at completion: conflating arriving with fixing
    makes a long repair look like a slow technician.
    """
    try:
        service_job_id = validate_uuid_path(service_job_id, resource="Service job")
        job = service_job_service.arrive_at_site(db, service_job_id)
        db.commit()
        return _serialize(db, job)
    except HTTPException:
        # AppException subclasses HTTPException, so a bare `except Exception` would
        # turn every domain 422 (AC-F5's refusal above all) into an opaque 500.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.post("/{service_job_id}/complete")
async def complete_service_job(
    payload: ServiceJobComplete,
    service_job_id: str,
    current_user: dict = Depends(require_permission(DISPATCH_PERMISSION)),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        service_job_id = validate_uuid_path(service_job_id, resource="Service job")
        job = service_job_service.complete_job(
            db, service_job_id, diagnosis_root_cause_id=payload.diagnosis_root_cause_id
        )
        db.commit()
        return _serialize(db, job)
    except HTTPException:
        # AppException subclasses HTTPException, so a bare `except Exception` would
        # turn every domain 422 (AC-F5's refusal above all) into an opaque 500.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.post("/{service_job_id}/verify")
async def verify_service_job(
    service_job_id: str,
    current_user: dict = Depends(require_permission(DISPATCH_PERMISSION)),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        service_job_id = validate_uuid_path(service_job_id, resource="Service job")
        job = service_job_service.verify_job(db, service_job_id)
        db.commit()
        return _serialize(db, job)
    except HTTPException:
        # AppException subclasses HTTPException, so a bare `except Exception` would
        # turn every domain 422 (AC-F5's refusal above all) into an opaque 500.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


# ------------------------------------------------------ money out (AC-M29 to M31)


@router.get("/costs/by-source")
async def get_case_costs(
    source_entity_type: str = Query(...),
    source_entity_id: str = Query(...),
    current_user: dict = Depends(require_permission(COST_PERMISSION)),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Total AND breakdown. One number per case does not answer the costing question
    this requirement came from (AC-M29), so both ship together.
    """
    try:
        from app.models.service_jobs import CaseCostLine

        rows = (
            db.query(CaseCostLine)
            .filter(
                CaseCostLine.source_entity_type == source_entity_type,
                CaseCostLine.source_entity_id == source_entity_id,
            )
            .order_by(CaseCostLine.recorded_at.desc())
            .all()
        )
        breakdown = service_job_service.case_cost_breakdown(
            db, source_entity_type, source_entity_id
        )
        return {
            "total": float(service_job_service.case_cost_total(db, source_entity_type, source_entity_id)),
            "breakdown": {kind: float(value) for kind, value in breakdown.items()},
            "lines": [
                {
                    "id": row.id,
                    "cost_kind": row.cost_kind,
                    "amount": float(row.amount) if row.amount is not None else None,
                    "currency": row.currency,
                    "external_provider_id": row.external_provider_id,
                    "incurred_on": row.incurred_on,
                    "recorded_by": row.recorded_by,
                    "recorded_at": row.recorded_at,
                }
                for row in rows
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/costs")
async def create_case_cost(
    payload: CaseCostLineCreate,
    current_user: dict = Depends(require_permission(COST_PERMISSION)),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """AC-M31. No approval step: it is bookkeeping, and reporting surfaces the outliers."""
    try:
        values = payload.model_dump()
        incurred = values.pop("incurred_on", None)
        line = service_job_service.record_cost_line(
            db,
            incurred_on=incurred.date() if isinstance(incurred, datetime) else incurred,
            **values,
        )
        db.commit()
        return {
            "id": line.id,
            "cost_kind": line.cost_kind,
            "amount": float(line.amount) if line.amount is not None else None,
            "currency": line.currency,
            "recorded_at": line.recorded_at,
        }
    except HTTPException:
        # AppException subclasses HTTPException, so a bare `except Exception` would
        # turn every domain 422 (AC-F5's refusal above all) into an opaque 500.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))
