"""Commercial projects API."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.modules.commercial_activity.services.commercial_project_task_service import (
    CommercialProjectTaskError,
    CommercialProjectTaskService,
)
from app.modules.commercial_core.schemas.commercial import (
    CommercialProjectCreate,
    CommercialProjectDetail,
    CommercialProjectListRow,
    CommercialProjectTaskTemplateRow,
    TaskBoardSchedulePreviewRequest,
    TaskBoardSchedulePreviewResponse,
    CommercialProjectUpdate,
)
from app.schemas.common import ListResponse, PaginationResponse
from app.modules.commercial_core.services.commercial_project_service import CommercialProjectService
from app.services.error_handler import handle_internal_error
from app.services.user_service import UserPermissionService

router = APIRouter()


def _require_projects(perm: str):
    async def _inner(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
        svc = UserPermissionService(db)
        uid = current_user["id"]
        if svc.get_user_role_slugs(uid) & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}:
            return current_user
        if not svc.check_user_has_permission(uid, perm):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission required: {perm}")
        return current_user

    return _inner


@router.get("/", response_model=ListResponse[CommercialProjectListRow])
async def list_projects(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=300),
    query: Optional[str] = Query(None),
    owner_user_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    project_stage_id: Optional[str] = Query(None, description="Filter by commercial project workflow stage id"),
    lead_id: Optional[str] = Query(None, description="Filter by commercial lead id"),
    customer_id: Optional[str] = Query(None, description="Filter by linked customer id"),
    _user: dict = Depends(_require_projects("commercial_core.projects.view")),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialProjectService(db)
        rows, total = svc.list_projects(
            page=page,
            limit=limit,
            owner_user_id=owner_user_id,
            status=status,
            search_query=query,
            lead_id=lead_id,
            project_stage_id=project_stage_id,
            customer_id=customer_id,
        )
        return ListResponse(
            data=[CommercialProjectListRow(**r) for r in rows],
            pagination=PaginationResponse(total=total, page=page, limit=limit),
            empty=total == 0,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/task-templates/select", response_model=list[CommercialProjectTaskTemplateRow])
async def list_task_templates(
    _user: dict = Depends(_require_projects("commercial_core.projects.view")),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialProjectService(db)
        return [CommercialProjectTaskTemplateRow(**r) for r in svc.list_task_templates()]
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{project_id}", response_model=CommercialProjectDetail)
async def get_project(
    project_id: str,
    _user: dict = Depends(_require_projects("commercial_core.projects.view")),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialProjectService(db)
        raw = svc.get_project(project_id)
        return CommercialProjectDetail(**raw)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=CommercialProjectDetail, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: CommercialProjectCreate,
    request: Request,
    current_user: dict = Depends(_require_projects("commercial_core.projects.add")),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialProjectService(db)
        raw = svc.create_from_lead(
            body,
            actor_user_id=current_user["id"],
            ip_address=request.client.host if request.client else None,
        )
        return CommercialProjectDetail(**raw)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{project_id}/duplicate", response_model=CommercialProjectDetail, status_code=status.HTTP_201_CREATED)
async def duplicate_project(
    project_id: str,
    request: Request,
    current_user: dict = Depends(_require_projects("commercial_core.projects.add")),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialProjectService(db)
        raw = svc.duplicate_project(
            project_id,
            actor_user_id=current_user["id"],
            ip_address=request.client.host if request.client else None,
        )
        return CommercialProjectDetail(**raw)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{project_id}/share-ownership", response_model=CommercialProjectDetail)
async def share_project_ownership(
    project_id: str,
    request: Request,
    current_user: dict = Depends(_require_projects("commercial_core.projects.share_ownership")),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialProjectService(db)
        raw = svc.share_ownership(
            project_id,
            actor_user_id=current_user["id"],
            ip_address=request.client.host if request.client else None,
        )
        return CommercialProjectDetail(**raw)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{project_id}/disown", response_model=CommercialProjectDetail)
async def disown_project(
    project_id: str,
    request: Request,
    current_user: dict = Depends(_require_projects("commercial_core.projects.share_ownership")),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialProjectService(db)
        raw = svc.disown(
            project_id,
            actor_user_id=current_user["id"],
            ip_address=request.client.host if request.client else None,
        )
        return CommercialProjectDetail(**raw)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    request: Request,
    current_user: dict = Depends(_require_projects("commercial_core.projects.edit")),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialProjectService(db)
        svc.delete_project(
            project_id,
            actor_user_id=current_user["id"],
            ip_address=request.client.host if request.client else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/{project_id}", response_model=CommercialProjectDetail)
async def update_project(
    project_id: str,
    body: CommercialProjectUpdate,
    request: Request,
    current_user: dict = Depends(_require_projects("commercial_core.projects.edit")),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialProjectService(db)
        raw = svc.update_project(
            project_id,
            body,
            actor_user_id=current_user["id"],
            ip_address=request.client.host if request.client else None,
        )
        return CommercialProjectDetail(**raw)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post(
    "/{project_id}/task-board/schedule/preview",
    response_model=TaskBoardSchedulePreviewResponse,
)
async def preview_project_task_board_schedule(
    project_id: str,
    body: TaskBoardSchedulePreviewRequest,
    _user: dict = Depends(_require_projects("commercial_core.projects.edit")),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialProjectService(db)
        out = svc.preview_task_board_schedule(
            task_board=body.task_board,
            baseline_start_date=body.baseline_start_date,
            changed_task_id=body.changed_task_id,
        )
        return TaskBoardSchedulePreviewResponse(**out)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


class _ProjectTasksKanbanRequest(BaseModel):
    quick_search: Optional[str] = None
    project_id: Optional[str] = None
    assignee_user_id: Optional[str] = None


class _ProjectTaskStatusUpdate(BaseModel):
    status_code: str


@router.post("/tasks/kanban")
async def project_tasks_kanban(
    body: _ProjectTasksKanbanRequest = Body(default_factory=_ProjectTasksKanbanRequest),
    _user: dict = Depends(_require_projects("commercial_core.projects.view")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        svc = CommercialProjectTaskService(db)
        return svc.list_tasks_kanban(
            quick_search=body.quick_search,
            project_id=(body.project_id or "").strip() or None,
            assignee_user_id=(body.assignee_user_id or "").strip() or None,
        )
    except CommercialProjectTaskError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/tasks/{task_id}/status")
async def update_project_task_status(
    task_id: str,
    body: _ProjectTaskStatusUpdate,
    _user: dict = Depends(_require_projects("commercial_core.projects.edit")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        svc = CommercialProjectTaskService(db)
        row = svc.update_task_status(task_id, body.status_code.strip())
        return {"id": str(row.id), "status_id": str(row.status_id)}
    except CommercialProjectTaskError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post(
    "/{project_id}/task-board/schedule/apply",
    response_model=TaskBoardSchedulePreviewResponse,
)
async def apply_project_task_board_schedule(
    project_id: str,
    body: TaskBoardSchedulePreviewRequest,
    _user: dict = Depends(_require_projects("commercial_core.projects.edit")),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialProjectService(db)
        out = svc.apply_task_board_schedule(
            project_id,
            task_board=body.task_board,
            baseline_start_date=body.baseline_start_date,
            changed_task_id=body.changed_task_id,
        )
        return TaskBoardSchedulePreviewResponse(**out)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


# ----------------------------------------------------------------------------
# Smart create — resolves "developer" (Customer) by fuzzy match against the
# customers catalog. Supports MCP/n8n callers that have a developer name but
# may or may not know if they exist in the system. Returns 409 with a list of
# near-matches when fuzzy candidates exist and the caller did not pass force=true.
# ----------------------------------------------------------------------------
import difflib
from sqlalchemy import or_

from app.modules.commercial_core.models import CommercialProject as _CommercialProject
from app.models.order import Customer as _Customer


class SmartProjectCreateDeveloperPayload(BaseModel):
    customer_code: str
    customer_name: str
    email: Optional[str] = None
    phone_number: Optional[str] = None
    registered_name: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None


class SmartProjectCreateRequest(BaseModel):
    developer_query: Optional[str] = Field(
        default=None,
        description="Free-text developer/customer name or code. Used to fuzzy-match existing customers.",
    )
    developer_id: Optional[str] = Field(
        default=None,
        description="Existing customer id. When set, skips fuzzy match and is used as the project developer.",
    )
    developer_create: Optional[SmartProjectCreateDeveloperPayload] = Field(
        default=None,
        description="When the caller has confirmed the developer is new, supply this payload to create the customer in the same call.",
    )
    project: CommercialProjectCreate = Field(
        ...,
        description="Project payload. `developer_customer_id` may be omitted; this endpoint fills it.",
    )
    force: bool = Field(
        default=False,
        description="When true, skip the near-match handshake even if fuzzy matches exist.",
    )


class SmartProjectCreateNearMatch(BaseModel):
    id: str
    customer_code: str
    customer_name: str
    similarity: float


class SmartProjectCreateResponse(BaseModel):
    project: CommercialProjectDetail
    developer_id: str
    status: str  # "matched_existing" | "created_new"
    matched_via: str  # "id" | "fuzzy_unique" | "developer_create" | "force"


def _fuzzy_match_customers(db: Session, query: str, limit: int = 8) -> list[tuple[_Customer, float]]:
    """Pre-filter customers via ILIKE on name/code, then score by SequenceMatcher.

    Returns rows ordered by similarity desc. Avoids needing pg_trgm extension.
    """
    q = (query or "").strip()
    if not q:
        return []
    needle = f"%{q}%"
    rows = (
        db.query(_Customer)
        .filter(
            or_(
                _Customer.customer_name.ilike(needle),
                _Customer.customer_code.ilike(needle),
                _Customer.registered_name.ilike(needle),
                _Customer.trading_name.ilike(needle),
            )
        )
        .limit(50)
        .all()
    )
    needle_lower = q.lower()
    scored: list[tuple[_Customer, float]] = []
    for r in rows:
        candidates = [
            (r.customer_name or "").lower(),
            (r.customer_code or "").lower(),
            (r.registered_name or "").lower(),
            (r.trading_name or "").lower(),
        ]
        best = max(
            (difflib.SequenceMatcher(None, needle_lower, c).ratio() for c in candidates if c),
            default=0.0,
        )
        scored.append((r, best))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:limit]


@router.post(
    "/smart-create",
    response_model=SmartProjectCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def smart_create_project(
    body: SmartProjectCreateRequest,
    current_user: dict = Depends(_require_projects("commercial_core.projects.add")),
    db: Session = Depends(get_db),
):
    """Create a project with a developer (customer) resolved by id, fuzzy match, or new-customer payload.

    Resolution order:
    1. If `developer_id` set → use it.
    2. Else if `developer_create` set → create new customer.
    3. Else if `developer_query` set → fuzzy match.
       - 1 unique high-confidence match (>=0.9) and `force=false` → use it.
       - Multiple matches (or any match below 0.9) and `force=false` → return 409 with `near_matches`.
       - `force=true` and matches exist → use the top match.
       - `force=true` and no matches → require `developer_create` (else 422).
    4. Else 422.
    """
    project_payload = body.project
    developer_id: Optional[str] = body.developer_id
    matched_via = "id" if developer_id else ""

    if not developer_id and body.developer_create is not None:
        existing = (
            db.query(_Customer.id)
            .filter(_Customer.customer_code == body.developer_create.customer_code)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"customer_code '{body.developer_create.customer_code}' already exists",
            )
        cust = _Customer(
            customer_code=body.developer_create.customer_code,
            customer_name=body.developer_create.customer_name,
            email=body.developer_create.email,
            phone_number=body.developer_create.phone_number,
            registered_name=body.developer_create.registered_name,
            industry=body.developer_create.industry,
            country=body.developer_create.country,
            customer_type="company",
            is_active=True,
            created_by=current_user.get("id"),
        )
        db.add(cust)
        db.flush()
        developer_id = str(cust.id)
        matched_via = "developer_create"

    if not developer_id and body.developer_query:
        matches = _fuzzy_match_customers(db, body.developer_query)
        if matches:
            top, top_score = matches[0]
            if body.force:
                developer_id = str(top.id)
                matched_via = "force"
            elif top_score >= 0.9 and (len(matches) == 1 or matches[1][1] < 0.7):
                developer_id = str(top.id)
                matched_via = "fuzzy_unique"
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "message": "Multiple or low-confidence developer matches. Confirm one of the candidates or supply `developer_create`.",
                        "needs_decision": True,
                        "near_matches": [
                            {
                                "id": str(c.id),
                                "customer_code": c.customer_code,
                                "customer_name": c.customer_name,
                                "similarity": round(s, 3),
                            }
                            for c, s in matches
                        ],
                        "missing_developer_fields": [
                            "customer_code",
                            "customer_name",
                            "email",
                            "phone_number",
                            "registered_name",
                            "industry",
                            "country",
                        ],
                    },
                )
        elif body.force and body.developer_create is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No customers matched developer_query. Supply `developer_create` to create one.",
            )

    if not developer_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide one of: developer_id, developer_create, or developer_query (with possible fuzzy match).",
        )

    project_payload_dict = project_payload.model_dump()
    project_payload_dict["developer_customer_id"] = developer_id
    final_payload = CommercialProjectCreate(**project_payload_dict)

    try:
        svc = CommercialProjectService(db)
        detail = svc.create(final_payload, current_user.get("id"))
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))

    return SmartProjectCreateResponse(
        project=detail,
        developer_id=developer_id,
        status="created_new" if matched_via == "developer_create" else "matched_existing",
        matched_via=matched_via,
    )
