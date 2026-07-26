"""Lead API (S2c, UAC Group O).

Three actions get their own endpoints rather than riding the generic PUT, because each
does work the field alone cannot express:

- **qualify** runs the registration clash check and creates a project (AC-O4). It is
  the only place a lead touches the exclusivity lock.
- **disqualify** validates its reason against a lookup set, so the conversion report
  has buckets rather than free text (AC-O6).
- **status** refuses the two terminal rungs, which belong to the two actions above.

A blocked qualify returns 409 and leaves the lead OPEN: the recourse is join-or-dispute
on the incumbent project, and the lead is the user's record of why they were asking.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.v1.projects._common import acting_company_id, permission_slugs
from app.database import get_db
from app.dependencies import require_permission
from app.schemas.common import MAX_PAGE_LIMIT, ListResponse
from app.schemas.projects import (
    ClashPreviewResponse,
    CustomerPortfolioResponse,
    ProjectLeadConversionMetrics,
    ProjectLeadCreate,
    ProjectLeadDisqualifyRequest,
    ProjectLeadQualifyRequest,
    ProjectLeadReasonOption,
    ProjectLeadResponse,
    ProjectLeadStatusChangeRequest,
    ProjectLeadUpdate,
    ProjectResponse,
)
from app.services import project_lead_service as svc
from app.services import project_service as projects
from app.services.error_handler import handle_internal_error
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()

VIEW = "projects.projects.view"
CREATE = "projects.projects.create"
EDIT = "projects.projects.edit"
DELETE = "projects.projects.delete"


def _one(db: Session, lead, current_user: dict) -> dict:
    return svc.serialize_leads(
        db,
        [lead],
        actor_user_id=current_user["id"],
        permissions=permission_slugs(db, current_user["id"]),
    )[0]


# --------------------------------------------------------------------- read


@router.get("", response_model=ListResponse[ProjectLeadResponse])
async def list_leads(
    query: Optional[str] = Query(None, description="Matches the title or the lead code."),
    outcome: Optional[List[str]] = Query(None),
    status_id: Optional[List[str]] = Query(None),
    owner_user_id: Optional[List[str]] = Query(None),
    customer_id: Optional[List[str]] = Query(None),
    source: Optional[List[str]] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    sort: str = Query("created_at"),
    dir: str = Query("desc", pattern="^(asc|desc)$"),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """Every lead in the company. Rows carry informational duplicate hints (AC-O3)."""
    try:
        result = svc.list_leads(
            db,
            company_id=acting_company_id(db),
            actor_user_id=current_user["id"],
            permissions=permission_slugs(db, current_user["id"]),
            query=query,
            outcome=outcome,
            status_id=status_id,
            owner_user_id=owner_user_id,
            customer_id=customer_id,
            source=source,
            page=page,
            limit=limit,
            sort=sort,
            dir=dir,
        )
        return {
            "data": result["data"],
            "pagination": {
                "total": result["total"],
                "page": result["page"],
                "limit": result["limit"],
            },
            "empty": result["total"] == 0,
        }
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/disqualify-reasons", response_model=List[ProjectLeadReasonOption])
async def list_disqualify_reasons(
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """The configured reasons (AC-O6). Empty means an admin has not set any up, and
    disqualify will refuse until they do."""
    try:
        return svc.disqualify_reasons(db)
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/metrics", response_model=ProjectLeadConversionMetrics)
async def lead_conversion_metrics(
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        return svc.conversion_metrics(db, company_id=acting_company_id(db))
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get(
    "/by-customer/{customer_id}/portfolio", response_model=CustomerPortfolioResponse
)
async def customer_portfolio(
    customer_id: str,
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """The account view (AC-O9): what this customer has told us about, and what it
    turned into.

    Declared BEFORE /{lead_id} so "by-customer" is not swallowed as a lead id.
    """
    try:
        validate_uuid_path(customer_id, resource="Customer")
        return svc.customer_portfolio(db, customer_id=customer_id)
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/{lead_id}", response_model=ProjectLeadResponse)
async def get_lead(
    lead_id: str,
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(lead_id, resource="Lead")
        return _one(db, svc.get_lead(db, lead_id), current_user)
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


# -------------------------------------------------------------------- write


@router.post("", response_model=ProjectLeadResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(
    payload: ProjectLeadCreate,
    current_user: dict = Depends(require_permission(CREATE)),
    db: Session = Depends(get_db),
):
    """Record a sighting. No clash check, deliberately (AC-O3).

    Accepts either an existing ``customer_id`` or a ``new_customer`` block, which is
    step 1 of the wizard: the informant is frequently an architect or contractor who
    has never bought anything.
    """
    try:
        company_id = acting_company_id(db)
        body = payload.model_dump(exclude_unset=True)
        new_customer = body.pop("new_customer", None)
        customer = svc.select_or_create_customer(
            db,
            company_id=company_id,
            actor_user_id=current_user["id"],
            customer_id=body.get("customer_id"),
            new_customer=new_customer,
        )
        body["customer_id"] = customer.id
        lead = svc.create_lead(
            db,
            company_id=company_id,
            actor_user_id=current_user["id"],
            payload=body,
        )
        db.commit()
        db.refresh(lead)
        return _one(db, lead, current_user)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.put("/{lead_id}", response_model=ProjectLeadResponse)
async def update_lead(
    lead_id: str,
    payload: ProjectLeadUpdate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(lead_id, resource="Lead")
        lead = svc.get_lead(db, lead_id)
        svc.assert_can_edit_lead(
            lead, current_user["id"], permission_slugs(db, current_user["id"])
        )
        svc.update_lead(db, lead, payload.model_dump(exclude_unset=True))
        db.commit()
        db.refresh(lead)
        return _one(db, lead, current_user)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post("/{lead_id}/status", response_model=ProjectLeadResponse)
async def change_lead_status(
    lead_id: str,
    payload: ProjectLeadStatusChangeRequest,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Move a rung. Qualified and Disqualified are refused here (422) and pointed at
    their own actions, which do the work those rungs mean."""
    try:
        validate_uuid_path(lead_id, resource="Lead")
        lead = svc.get_lead(db, lead_id)
        svc.assert_can_edit_lead(
            lead, current_user["id"], permission_slugs(db, current_user["id"])
        )
        svc.change_lead_status(db, lead, payload.to_status_id)
        db.commit()
        db.refresh(lead)
        return _one(db, lead, current_user)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/{lead_id}/qualify-preview", response_model=ClashPreviewResponse)
async def preview_qualify(
    lead_id: str,
    title: Optional[str] = Query(None, description="Defaults to the lead's title."),
    developer_party_id: Optional[str] = Query(None),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """What qualifying would hit, before the user commits (AC-O4).

    Same matcher and thresholds as registration, so the preview cannot disagree with
    the decision that follows it.
    """
    try:
        validate_uuid_path(lead_id, resource="Lead")
        lead = svc.get_lead(db, lead_id)
        preview = svc.preview_qualify_clashes(
            db,
            lead=lead,
            company_id=acting_company_id(db),
            title=title,
            developer_party_id=developer_party_id,
        )
        return {
            "candidates": projects.serialize_clash_candidates(
                db, preview["candidates"]
            ),
            "would_block": preview["would_block"],
        }
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/{lead_id}/qualify",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def qualify_lead(
    lead_id: str,
    payload: ProjectLeadQualifyRequest,
    current_user: dict = Depends(require_permission(CREATE)),
    db: Session = Depends(get_db),
):
    """Convert to a project. 409 when somebody already holds the development.

    Requires ``.create`` and not just ``.edit``: this is a registration, and it is the
    same grant that registering directly needs.
    """
    try:
        validate_uuid_path(lead_id, resource="Lead")
        lead = svc.get_lead(db, lead_id)
        svc.assert_can_edit_lead(
            lead, current_user["id"], permission_slugs(db, current_user["id"])
        )
        project = svc.qualify_lead(
            db,
            lead=lead,
            actor_user_id=current_user["id"],
            company_id=acting_company_id(db),
            project_payload=payload.model_dump(exclude_unset=True),
        )
        db.commit()
        db.refresh(project)
        return projects.serialize_projects(
            db,
            [project],
            actor_user_id=current_user["id"],
            permissions=permission_slugs(db, current_user["id"]),
        )[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post("/{lead_id}/disqualify", response_model=ProjectLeadResponse)
async def disqualify_lead(
    lead_id: str,
    payload: ProjectLeadDisqualifyRequest,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(lead_id, resource="Lead")
        lead = svc.get_lead(db, lead_id)
        svc.assert_can_edit_lead(
            lead, current_user["id"], permission_slugs(db, current_user["id"])
        )
        svc.disqualify_lead(db, lead=lead, reason=payload.reason)
        db.commit()
        db.refresh(lead)
        return _one(db, lead, current_user)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post("/{lead_id}/reopen", response_model=ProjectLeadResponse)
async def reopen_lead(
    lead_id: str,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Undo a disqualification. Refused on a qualified lead, which has a project
    behind it that reopening would orphan."""
    try:
        validate_uuid_path(lead_id, resource="Lead")
        lead = svc.get_lead(db, lead_id)
        svc.assert_can_edit_lead(
            lead, current_user["id"], permission_slugs(db, current_user["id"])
        )
        svc.reopen_lead(db, lead)
        db.commit()
        db.refresh(lead)
        return _one(db, lead, current_user)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.delete("/{lead_id}")
async def delete_lead(
    lead_id: str,
    current_user: dict = Depends(require_permission(DELETE)),
    db: Session = Depends(get_db),
):
    """Hard delete, per the CRUD standard. Any project qualified out of it survives:
    ``projects.lead_id`` is ON DELETE SET NULL."""
    try:
        validate_uuid_path(lead_id, resource="Lead")
        lead = svc.get_lead(db, lead_id)
        svc.assert_can_edit_lead(
            lead, current_user["id"], permission_slugs(db, current_user["id"])
        )
        svc.delete_lead(db, lead)
        db.commit()
        return {"success": True}
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))
