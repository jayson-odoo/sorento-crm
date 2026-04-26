"""Commercial tenders API."""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.modules.commercial_core.models import CommercialMasterQuotation
from app.modules.commercial_core.schemas.commercial import (
    CommercialMasterQuotationListRow,
    CommercialProjectSelectRow,
    CommercialTenderCloseRequest,
    CommercialTenderCreate,
    CommercialTenderDetail,
    CommercialTenderListRow,
    CommercialTenderMilestoneCreate,
    CommercialTenderMilestoneResponse,
    CommercialTenderMilestoneUpdate,
    CommercialTenderStageSelectRow,
    CommercialTenderSummaryResponse,
    CommercialTenderUpdate,
)
from app.schemas.common import ListResponse, PaginationResponse
from app.modules.commercial_core.services.commercial_tender_service import (
    close_tender,
    create_milestone,
    create_tender,
    delete_milestone,
    delete_tender,
    get_tender_by_code,
    list_milestones,
    list_tender_process_stages,
    list_tenders,
    owner_display,
    reopen_tender,
    tender_summary,
    update_milestone,
    update_tender,
)
from app.services.error_handler import handle_internal_error
from app.services.user_service import UserPermissionService

router = APIRouter()


def _require_tenders(perm: str):
    async def _inner(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
        svc = UserPermissionService(db)
        uid = current_user["id"]
        if svc.get_user_role_slugs(uid) & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}:
            return current_user
        if not svc.check_user_has_permission(uid, perm):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission required: {perm}")
        return current_user

    return _inner


def _parse_optional_date(s: Optional[str]) -> Optional[date]:
    if not s or not str(s).strip():
        return None
    try:
        return date.fromisoformat(str(s).strip()[:10])
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date format; use YYYY-MM-DD")


def _tender_to_list_row(db: Session, t) -> CommercialTenderListRow:
    return CommercialTenderListRow(
        tender_code=t.tender_code,
        title=t.title,
        project_id=str(t.project_id),
        owner_name=owner_display(db, t.owner_user_id),
        forecast_amount=t.forecast_amount,
        forecast_currency=t.forecast_currency,
        pipeline_stage=t.pipeline_stage,
        expected_close_on=t.expected_close_on.isoformat() if t.expected_close_on else None,
        tender_lifecycle=t.tender_lifecycle,
        tender_outcome=t.tender_outcome,
        closed_at=t.closed_at,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


def _tender_to_detail(db: Session, t) -> CommercialTenderDetail:
    base = _tender_to_list_row(db, t)
    return CommercialTenderDetail(
        **base.model_dump(),
        outcome_notes=t.outcome_notes,
    )


@router.get("/projects/select", response_model=List[CommercialProjectSelectRow])
async def projects_select(
    query: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=300),
    _user: dict = Depends(_require_tenders("commercial_core.tenders.view")),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialProjectService(db)
        rows = svc.list_projects_select(search_query=query, limit=limit)
        return [CommercialProjectSelectRow(**r) for r in rows]
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/stages/select", response_model=List[CommercialTenderStageSelectRow])
async def tender_stages_select(
    _user: dict = Depends(_require_tenders("commercial_core.tenders.view")),
    db: Session = Depends(get_db),
):
    try:
        rows = list_tender_process_stages(db, active_only=True)
        return [
            CommercialTenderStageSelectRow(
                stage_code=r.code,
                stage_name=r.label,
                sort_order=r.sort_order,
                is_terminal=r.is_terminal,
            )
            for r in rows
        ]
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/", response_model=ListResponse[CommercialTenderListRow])
async def list_tenders_api(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    project_id: Optional[str] = Query(None),
    _user: dict = Depends(_require_tenders("commercial_core.tenders.view")),
    db: Session = Depends(get_db),
):
    try:
        rows, total = list_tenders(db, project_id=project_id, page=page, limit=limit)
        data = [_tender_to_list_row(db, t) for t in rows]
        return ListResponse(
            data=data,
            pagination=PaginationResponse(total=total, page=page, limit=limit),
            empty=total == 0,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/by-code/{tender_code}", response_model=CommercialTenderDetail)
async def get_tender(
    tender_code: str,
    _user: dict = Depends(_require_tenders("commercial_core.tenders.view")),
    db: Session = Depends(get_db),
):
    try:
        t = get_tender_by_code(db, tender_code)
        return _tender_to_detail(db, t)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=CommercialTenderDetail, status_code=status.HTTP_201_CREATED)
async def create_tender_api(
    body: CommercialTenderCreate,
    _user: dict = Depends(_require_tenders("commercial_core.tenders.add")),
    db: Session = Depends(get_db),
):
    try:
        t = create_tender(
            db,
            project_id=body.project_id,
            tender_code=body.tender_code,
            title=body.title,
            owner_user_id=body.owner_user_id,
            forecast_amount=body.forecast_amount,
            forecast_currency=body.forecast_currency,
            pipeline_stage=body.pipeline_stage,
            expected_close_on=_parse_optional_date(body.expected_close_on),
        )
        return _tender_to_detail(db, t)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/by-code/{tender_code}", response_model=CommercialTenderDetail)
async def patch_tender(
    tender_code: str,
    body: CommercialTenderUpdate,
    _user: dict = Depends(_require_tenders("commercial_core.tenders.edit")),
    db: Session = Depends(get_db),
):
    try:
        raw = body.model_dump(exclude_unset=True)
        if "expected_close_on" in raw:
            raw["expected_close_on"] = _parse_optional_date(raw.get("expected_close_on"))
        t = update_tender(db, tender_code, raw)
        return _tender_to_detail(db, t)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/by-code/{tender_code}", status_code=status.HTTP_200_OK)
async def delete_tender_api(
    tender_code: str,
    _user: dict = Depends(_require_tenders("commercial_core.tenders.delete")),
    db: Session = Depends(get_db),
):
    try:
        delete_tender(db, tender_code)
        return {"message": "Tender deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/by-code/{tender_code}/close", response_model=CommercialTenderDetail)
async def close_tender_api(
    tender_code: str,
    body: CommercialTenderCloseRequest,
    _user: dict = Depends(_require_tenders("commercial_core.tenders.edit")),
    db: Session = Depends(get_db),
):
    try:
        t = close_tender(
            db,
            tender_code,
            outcome=body.outcome,
            winning_master_quotation_id=body.winning_master_quotation_id,
            outcome_notes=body.outcome_notes,
        )
        return _tender_to_detail(db, t)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/by-code/{tender_code}/reopen", response_model=CommercialTenderDetail)
async def reopen_tender_api(
    tender_code: str,
    _user: dict = Depends(_require_tenders("commercial_core.tenders.edit")),
    db: Session = Depends(get_db),
):
    try:
        t = reopen_tender(db, tender_code)
        return _tender_to_detail(db, t)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/by-code/{tender_code}/summary", response_model=CommercialTenderSummaryResponse)
async def tender_summary_api(
    tender_code: str,
    _user: dict = Depends(_require_tenders("commercial_core.tenders.view")),
    db: Session = Depends(get_db),
):
    try:
        s = tender_summary(db, tender_code)
        return CommercialTenderSummaryResponse(**s)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/by-code/{tender_code}/quotations", response_model=List[CommercialMasterQuotationListRow])
async def list_tender_quotations(
    tender_code: str,
    _user: dict = Depends(_require_tenders("commercial_core.tenders.view")),
    db: Session = Depends(get_db),
):
    try:
        t = get_tender_by_code(db, tender_code)
        mqs = (
            db.query(CommercialMasterQuotation)
            .filter(CommercialMasterQuotation.tender_id == t.id)
            .order_by(CommercialMasterQuotation.quotation_code.asc())
            .all()
        )
        return [
            CommercialMasterQuotationListRow(
                id=str(m.id),
                quotation_code=m.quotation_code,
                title=m.title,
                path_role=m.path_role,
                quotation_stage_id=str(m.quotation_stage_id),
                quoted_amount=m.quoted_amount,
                quoted_currency=m.quoted_currency,
            )
            for m in mqs
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/by-code/{tender_code}/milestones", response_model=List[CommercialTenderMilestoneResponse])
async def list_milestones_api(
    tender_code: str,
    _user: dict = Depends(_require_tenders("commercial_core.tender_milestones.view")),
    db: Session = Depends(get_db),
):
    try:
        rows = list_milestones(db, tender_code)
        return [
            CommercialTenderMilestoneResponse(
                id=str(m.id),
                tender_id=str(m.tender_id),
                milestone_code=m.milestone_code,
                due_on=m.due_on.isoformat() if m.due_on else None,
                achieved_at=m.achieved_at,
                sort_order=m.sort_order,
                created_at=m.created_at,
            )
            for m in rows
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/by-code/{tender_code}/milestones", response_model=CommercialTenderMilestoneResponse, status_code=status.HTTP_201_CREATED)
async def create_milestone_api(
    tender_code: str,
    body: CommercialTenderMilestoneCreate,
    _user: dict = Depends(_require_tenders("commercial_core.tender_milestones.add")),
    db: Session = Depends(get_db),
):
    try:
        m = create_milestone(
            db,
            tender_code,
            milestone_code=body.milestone_code,
            due_on=_parse_optional_date(body.due_on),
            sort_order=body.sort_order,
        )
        return CommercialTenderMilestoneResponse(
            id=str(m.id),
            tender_id=str(m.tender_id),
            milestone_code=m.milestone_code,
            due_on=m.due_on.isoformat() if m.due_on else None,
            achieved_at=m.achieved_at,
            sort_order=m.sort_order,
            created_at=m.created_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/milestones/{milestone_id}", response_model=CommercialTenderMilestoneResponse)
async def update_milestone_api(
    milestone_id: str,
    body: CommercialTenderMilestoneUpdate,
    _user: dict = Depends(_require_tenders("commercial_core.tender_milestones.edit")),
    db: Session = Depends(get_db),
):
    try:
        m = update_milestone(
            db,
            milestone_id,
            milestone_code=body.milestone_code,
            due_on=_parse_optional_date(body.due_on) if body.due_on is not None else None,
            achieved_at=body.achieved_at,
            sort_order=body.sort_order,
        )
        return CommercialTenderMilestoneResponse(
            id=str(m.id),
            tender_id=str(m.tender_id),
            milestone_code=m.milestone_code,
            due_on=m.due_on.isoformat() if m.due_on else None,
            achieved_at=m.achieved_at,
            sort_order=m.sort_order,
            created_at=m.created_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/milestones/{milestone_id}", status_code=status.HTTP_200_OK)
async def delete_milestone_api(
    milestone_id: str,
    _user: dict = Depends(_require_tenders("commercial_core.tender_milestones.delete")),
    db: Session = Depends(get_db),
):
    try:
        delete_milestone(db, milestone_id)
        return {"message": "Milestone deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
