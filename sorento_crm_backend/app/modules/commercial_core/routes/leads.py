"""Commercial leads, notes, and conversion."""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import get_current_user
from app.modules.commercial_core.schemas.commercial import (
    CommercialLeadConvertRequest,
    CommercialLeadConvertResponse,
    CommercialLeadCreate,
    CommercialLeadNoteCreate,
    CommercialLeadNoteResponse,
    CommercialLeadResponse,
    CommercialLeadUpdate,
    LeadRelatedResponse,
)
from app.schemas.common import ListResponse, PaginationResponse
from app.modules.commercial_core.models import CommercialLeadNote
from app.modules.commercial_core.services.commercial_lead_service import CommercialLeadService
from app.services.error_handler import handle_internal_error
from app.services.user_service import UserPermissionService

router = APIRouter()


def _client_ip(request: Request) -> Optional[str]:
    if request.client:
        return request.client.host
    return None


def _require_leads_view(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    svc = UserPermissionService(db)
    uid = current_user["id"]
    if svc.get_user_role_slugs(uid) & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}:
        return current_user
    if not svc.check_user_has_permission(uid, "commercial_core.leads.view"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission required: commercial_core.leads.view")
    return current_user


def _require_leads_add(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    svc = UserPermissionService(db)
    uid = current_user["id"]
    if svc.get_user_role_slugs(uid) & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}:
        return current_user
    if not svc.check_user_has_permission(uid, "commercial_core.leads.add"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission required: commercial_core.leads.add")
    return current_user


def _require_leads_edit(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    svc = UserPermissionService(db)
    uid = current_user["id"]
    if svc.get_user_role_slugs(uid) & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}:
        return current_user
    if not svc.check_user_has_permission(uid, "commercial_core.leads.edit"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission required: commercial_core.leads.edit")
    return current_user


def _require_leads_delete(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    svc = UserPermissionService(db)
    uid = current_user["id"]
    if svc.get_user_role_slugs(uid) & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}:
        return current_user
    if not svc.check_user_has_permission(uid, "commercial_core.leads.delete"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission required: commercial_core.leads.delete")
    return current_user


def _require_convert(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    svc = UserPermissionService(db)
    uid = current_user["id"]
    if svc.get_user_role_slugs(uid) & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}:
        return current_user
    if not svc.check_user_has_permission(uid, "commercial_core.projects.add"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission required: commercial_core.projects.add")
    if not svc.check_user_has_permission(uid, "commercial_core.tenders.add"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission required: commercial_core.tenders.add")
    return current_user


@router.get("/", response_model=ListResponse[CommercialLeadResponse])
async def list_leads(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=300),
    customer_id: Optional[str] = Query(None),
    owner_user_id: Optional[str] = Query(None),
    lead_stage_id: Optional[str] = Query(None),
    stage_code: Optional[str] = Query(None, description="Filter by lead stage code (e.g. qualified)"),
    without_project: bool = Query(False, description="Only leads with no project yet"),
    query: Optional[str] = Query(None, description="Search lead code, title, customer"),
    sort: Optional[str] = Query(None, description="created_at, updated_at, lead_code, title, customer_name, stage_name"),
    dir: Optional[str] = Query("desc", description="asc or desc"),
    open_pipeline_only: bool = Query(False, description="Exclude leads in terminal stages"),
    terminal_pipeline_only: bool = Query(False, description="Only leads in terminal stages"),
    terminal_conversion_eligible_only: bool = Query(
        False,
        description="Terminal lead stages that allow conversion (is_terminal + allows_conversion), e.g. Won",
    ),
    customer_active_only: bool = Query(False, description="Only leads whose customer account is active"),
    created_from: Optional[date] = Query(None, description="Created on or after (date)"),
    created_to: Optional[date] = Query(None, description="Created on or before (date)"),
    _user: dict = Depends(_require_leads_view),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialLeadService(db)
        items, total = svc.list_leads(
            page=page,
            limit=limit,
            customer_id=customer_id,
            owner_user_id=owner_user_id,
            lead_stage_id=lead_stage_id,
            stage_code=stage_code,
            without_project=without_project,
            search_query=query,
            sort_field=sort,
            sort_dir=dir,
            open_pipeline_only=open_pipeline_only,
            terminal_pipeline_only=terminal_pipeline_only,
            terminal_conversion_eligible_only=terminal_conversion_eligible_only,
            customer_active_only=customer_active_only,
            created_from=created_from,
            created_to=created_to,
        )
        data = [CommercialLeadResponse.model_validate(x) for x in items]
        return ListResponse(
            data=data,
            pagination=PaginationResponse(total=total, page=page, limit=limit),
            empty=total == 0,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{lead_id}/related", response_model=LeadRelatedResponse)
async def get_lead_related(
    lead_id: str,
    _user: dict = Depends(_require_leads_view),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialLeadService(db)
        raw = svc.get_lead_related(lead_id)
        return LeadRelatedResponse.model_validate(raw)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{lead_id}", response_model=CommercialLeadResponse)
async def get_lead(
    lead_id: str,
    _user: dict = Depends(_require_leads_view),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialLeadService(db)
        return CommercialLeadResponse.model_validate(svc.get_lead(lead_id))
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=CommercialLeadResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(
    data: CommercialLeadCreate,
    request: Request,
    current_user: dict = Depends(_require_leads_add),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialLeadService(db)
        out = svc.create_lead(
            data,
            actor_user_id=current_user["id"],
            ip_address=_client_ip(request),
        )
        return CommercialLeadResponse.model_validate(out)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{lead_id}/duplicate", response_model=CommercialLeadResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_lead(
    lead_id: str,
    request: Request,
    current_user: dict = Depends(_require_leads_add),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialLeadService(db)
        out = svc.duplicate_lead(
            lead_id,
            actor_user_id=current_user["id"],
            ip_address=_client_ip(request),
        )
        return CommercialLeadResponse.model_validate(out)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/{lead_id}", response_model=CommercialLeadResponse)
async def update_lead(
    lead_id: str,
    data: CommercialLeadUpdate,
    request: Request,
    current_user: dict = Depends(_require_leads_edit),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialLeadService(db)
        out = svc.update_lead(
            lead_id,
            data,
            actor_user_id=current_user["id"],
            ip_address=_client_ip(request),
        )
        return CommercialLeadResponse.model_validate(out)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(
    lead_id: str,
    request: Request,
    current_user: dict = Depends(_require_leads_delete),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialLeadService(db)
        svc.delete_lead(lead_id, actor_user_id=current_user["id"], ip_address=_client_ip(request))
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{lead_id}/notes", response_model=List[CommercialLeadNoteResponse])
async def list_lead_notes(
    lead_id: str,
    _user: dict = Depends(_require_leads_view),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialLeadService(db)
        notes = svc.list_notes(lead_id)
        out: List[CommercialLeadNoteResponse] = []
        for n in notes:
            name = None
            if n.created_by:
                name = (n.created_by.name or "").strip() or n.created_by.email
            out.append(
                CommercialLeadNoteResponse(
                    id=str(n.id),
                    lead_id=str(n.lead_id),
                    body=n.body,
                    created_by_user_id=n.created_by_user_id,
                    created_by_name=name,
                    created_at=n.created_at,
                )
            )
        return out
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{lead_id}/notes", response_model=CommercialLeadNoteResponse, status_code=status.HTTP_201_CREATED)
async def add_lead_note(
    lead_id: str,
    data: CommercialLeadNoteCreate,
    current_user: dict = Depends(_require_leads_edit),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialLeadService(db)
        n = svc.add_note(lead_id, data, actor_user_id=current_user["id"])
        row = (
            db.query(CommercialLeadNote)
            .options(joinedload(CommercialLeadNote.created_by))
            .filter(CommercialLeadNote.id == n.id)
            .first()
        ) or n
        name = None
        if getattr(row, "created_by", None):
            name = (row.created_by.name or "").strip() or row.created_by.email
        return CommercialLeadNoteResponse(
            id=str(row.id),
            lead_id=str(row.lead_id),
            body=row.body,
            created_by_user_id=row.created_by_user_id,
            created_by_name=name,
            created_at=row.created_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{lead_id}/convert", response_model=CommercialLeadConvertResponse)
async def convert_lead(
    lead_id: str,
    data: CommercialLeadConvertRequest,
    request: Request,
    current_user: dict = Depends(_require_convert),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialLeadService(db)
        project_id, tender_id, tender_code = svc.convert_lead(
            lead_id,
            data,
            actor_user_id=current_user["id"],
            ip_address=_client_ip(request),
        )
        return CommercialLeadConvertResponse(
            lead_id=lead_id,
            project_id=project_id,
            tender_id=tender_id,
            tender_code=tender_code,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
