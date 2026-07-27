"""Project pipeline API (UAC Groups A, C, G, J).

Reading is open to anyone with ``projects.projects.view``; every write re-checks
ownership in the service, so a user who can reach the endpoint still cannot edit
someone else's project.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.v1.projects._common import acting_company_id, permission_slugs
from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.schemas.projects import (
    ClashPreviewRequest,
    ClashPreviewResponse,
    ProjectCollaboratorResponse,
    ProjectRegisterRequest,
    ProjectResponse,
    ProjectStakeholderCreate,
    ProjectStakeholderResponse,
    ProjectStakeholderUpdate,
    ProjectStatusChangeRequest,
    ProjectUpdateRequest,
    TakeoverRequestCreate,
    TakeoverRequestDecision,
    TakeoverRequestResponse,
)
from app.services import project_reference_service as refs
from app.services import project_service as svc
from app.services.error_handler import handle_internal_error
from app.services.uuid_list_param import parse_uuid_list
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()

# The MCP server presents X-API-Key with an act-as user, never a JWT, so the routes its
# read-only tools call use `require_permission_with_api_key` (AC-K1/AC-K4). The permission is
# still enforced -- against the resolved act-as user -- and every WRITE route deliberately
# keeps plain `require_permission`, so AC-K2's "no write-capable project tools" is a property
# of the API surface and not just of the tool catalog.
VIEW = "projects.projects.view"
EDIT = "projects.projects.edit"
DELETE = "projects.projects.delete"
MANAGE = "projects.projects.manage"

_PROFILE_KEYS = (
    "registered_company_name",
    "location",
    "address",
    "architect_party_id",
    "main_contractor_party_id",
    "estimated_sales_value",
    "launch_date",
    "expected_delivery_from",
    "expected_delivery_to",
    "type_id",
    "template_id",
)


@router.post("/clash-preview", response_model=ClashPreviewResponse)
async def preview_clashes(
    payload: ClashPreviewRequest,
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """Check a title BEFORE the user fills the rest of the form.

    The point is to warn while the decision is still cheap. Discovering the clash on
    submit, after ten fields, is what makes people work around the system.
    """
    try:
        company_id = acting_company_id(db)
        candidates = svc.find_clashes(
            db,
            company_id=company_id,
            developer_party_id=payload.developer_party_id,
            title=payload.title,
            # Widen to every developer: the title is typed before the developer is
            # chosen, and a silent check until then misses the common path. Those
            # extra rows come back as context and can never block.
            include_other_developers=True,
        )
        return {
            "candidates": svc.serialize_clash_candidates(db, candidates),
            "would_block": any(c.blocks for c in candidates),
        }
    except Exception as exc:
        raise handle_internal_error(str(exc))


def _merge(*groups: Optional[List[str]]) -> Optional[List[str]]:
    """Union of the FE's singular filter and the MCP's `<entity>_ids` filter.

    Union rather than "one wins": both name the same axis, and a caller that passes both
    means both. Returns None when nothing was passed, which the service reads as no filter.
    """
    out: list[str] = []
    for group in groups:
        for value in group or []:
            if value and value not in out:
                out.append(str(value))
    return out or None


@router.get("/", response_model=ListResponse[ProjectResponse])
async def list_projects(
    query: Optional[str] = Query(None, description="Matches title or project code"),
    status_id: Optional[List[str]] = Query(None),
    outcome: Optional[List[str]] = Query(None),
    owner_user_id: Optional[List[str]] = Query(None),
    developer_party_id: Optional[List[str]] = Query(None),
    type_id: Optional[List[str]] = Query(None),
    brand_id: Optional[List[str]] = Query(None),
    only_critical: bool = Query(False),
    # UUID-first filters for the MCP / AI surface (AC-K1). Named `<entity>_ids` and parsed
    # with the shared `parse_uuid_list`, so they accept CSV, a JSON array or repeated params
    # exactly like every other list route -- and reject an unparseable value with a 400
    # rather than ignoring the filter, which would answer "Damai Land has 47 projects" after
    # quietly listing the whole company.
    #
    # Additive: the singular FE params above are untouched. Both sets AND together, so a
    # caller can combine them without a surprise.
    project_ids: Optional[List[str]] = Query(
        None, description="Canonical project UUIDs (csv / JSON list / repeated)."
    ),
    owner_user_ids: Optional[List[str]] = Query(
        None, description="Owner user UUIDs. 'My pipeline' is this filter."
    ),
    developer_party_ids: Optional[List[str]] = Query(
        None, description="Developer project-party UUIDs."
    ),
    status_key: Optional[List[str]] = Query(
        None,
        description=(
            "Funnel rung by stable KEY (identified, registered, specified, quoted, "
            "tendering, po_received, lost, dormant). Unknown keys are a 422 naming the "
            "valid ones."
        ),
    ),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    sort: str = Query("created_at"),
    dir: str = Query("desc"),
    current_user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        company_id = acting_company_id(db)
        status_ids = list(status_id or [])
        if status_key:
            status_ids.extend(svc.status_ids_for_keys(db, status_key))
        rows, total = svc.list_projects(
            db,
            company_id=company_id,
            search=query,
            status_ids=status_ids or None,
            outcomes=outcome,
            owner_user_ids=_merge(
                owner_user_id,
                parse_uuid_list(owner_user_ids, param_name="owner_user_ids"),
            ),
            developer_party_ids=_merge(
                developer_party_id,
                parse_uuid_list(developer_party_ids, param_name="developer_party_ids"),
            ),
            project_ids=parse_uuid_list(project_ids, param_name="project_ids"),
            type_ids=type_id,
            brand_ids=brand_id,
            only_critical=only_critical,
            page=page,
            limit=limit,
            sort=sort,
            direction=dir,
        )
        data = svc.serialize_projects(
            db,
            rows,
            actor_user_id=current_user["id"],
            permissions=permission_slugs(db, current_user["id"]),
        )
        return {
            "data": data,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
        }
    except Exception as exc:
        # A rejected filter is the CALLER's answer, not a server fault: an unparseable
        # `developer_party_ids` (400) and an unknown `status_key` (422) both have to reach
        # the client as themselves. Wrapping them in a 500 would tell an agent the server is
        # broken when the fix is in its own argument.
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def register_project(
    payload: ProjectRegisterRequest,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        company_id = acting_company_id(db)
        permissions = permission_slugs(db, current_user["id"])

        owner = payload.owner_user_id
        if owner and owner != current_user["id"] and MANAGE not in permissions:
            from app.services.error_handler import AppException

            raise AppException(
                status_code=403,
                message="Only a sales manager can register a project for someone else.",
                code="project_owner_assign_forbidden",
            )

        body = payload.model_dump(exclude_unset=True)
        details = {k: v for k, v in body.items() if k in _PROFILE_KEYS}

        project = svc.register_project(
            db,
            company_id=company_id,
            actor_user_id=current_user["id"],
            developer_party_id=payload.developer_party_id,
            title=payload.title,
            type_id=payload.type_id,
            template_id=payload.template_id,
            owner_user_id=owner,
            details=details,
            brand_ids=payload.brand_ids,
        )
        db.commit()
        db.refresh(project)
        return svc.serialize_project(
            db, project, actor_user_id=current_user["id"], permissions=permissions
        )
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    current_user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(project_id, resource="Project")
        project = svc.get_project_or_404(db, project_id)
        return svc.serialize_project(
            db,
            project,
            actor_user_id=current_user["id"],
            permissions=permission_slugs(db, current_user["id"]),
        )
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    payload: ProjectUpdateRequest,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(project_id, resource="Project")
        project = svc.get_project_or_404(db, project_id)
        permissions = permission_slugs(db, current_user["id"])
        svc.update_project(
            db,
            project,
            payload.model_dump(exclude_unset=True),
            actor_user_id=current_user["id"],
            permissions=permissions,
        )
        db.commit()
        db.refresh(project)
        return svc.serialize_project(
            db, project, actor_user_id=current_user["id"], permissions=permissions
        )
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post("/{project_id}/status", response_model=ProjectResponse)
async def change_project_status(
    project_id: str,
    payload: ProjectStatusChangeRequest,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Board drag lands here. An edge that is not in the graph is rejected (AC-B4)."""
    try:
        validate_uuid_path(project_id, resource="Project")
        project = svc.get_project_or_404(db, project_id)
        permissions = permission_slugs(db, current_user["id"])
        svc.change_status(
            db,
            project,
            to_status_id=payload.to_status_id,
            actor_user_id=current_user["id"],
            permissions=permissions,
        )
        db.commit()
        db.refresh(project)
        return svc.serialize_project(
            db, project, actor_user_id=current_user["id"], permissions=permissions
        )
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.delete("/{project_id}", status_code=status.HTTP_200_OK)
async def delete_project(
    project_id: str,
    current_user: dict = Depends(require_permission(DELETE)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(project_id, resource="Project")
        project = svc.get_project_or_404(db, project_id)
        code = project.project_code
        svc.delete_project(
            db,
            project,
            actor_user_id=current_user["id"],
            permissions=permission_slugs(db, current_user["id"]),
        )
        db.commit()
        return {"message": f"{code} deleted"}
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


# ------------------------------------------------------------- stakeholders


@router.get(
    "/{project_id}/stakeholders",
    response_model=ListResponse[ProjectStakeholderResponse],
)
async def list_stakeholders(
    project_id: str,
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(project_id, resource="Project")
        svc.get_project_or_404(db, project_id)
        rows = refs.list_stakeholders(db, project_id)
        data = refs.serialize_stakeholders(db, rows)
        return {
            "data": data,
            "pagination": {"total": len(data), "page": 1, "limit": max(len(data), 1)},
            "empty": not data,
        }
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/{project_id}/stakeholders",
    response_model=ProjectStakeholderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_stakeholder(
    project_id: str,
    payload: ProjectStakeholderCreate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(project_id, resource="Project")
        project = svc.get_project_or_404(db, project_id)
        svc.assert_can_edit_project(
            db,
            project,
            current_user["id"],
            permission_slugs(db, current_user["id"]),
        )
        stakeholder = refs.add_stakeholder(
            db, project=project, payload=payload.model_dump(exclude_unset=True)
        )
        db.commit()
        db.refresh(stakeholder)
        return refs.serialize_stakeholders(db, [stakeholder])[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.put(
    "/{project_id}/stakeholders/{stakeholder_id}",
    response_model=ProjectStakeholderResponse,
)
async def update_stakeholder(
    project_id: str,
    stakeholder_id: str,
    payload: ProjectStakeholderUpdate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(project_id, resource="Project")
        validate_uuid_path(stakeholder_id, resource="Stakeholder")
        project = svc.get_project_or_404(db, project_id)
        svc.assert_can_edit_project(
            db, project, current_user["id"], permission_slugs(db, current_user["id"])
        )
        stakeholder = refs.get_stakeholder_or_404(db, project_id, stakeholder_id)
        refs.update_stakeholder(
            db, stakeholder, payload.model_dump(exclude_unset=True)
        )
        db.commit()
        db.refresh(stakeholder)
        return refs.serialize_stakeholders(db, [stakeholder])[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.delete("/{project_id}/stakeholders/{stakeholder_id}")
async def remove_stakeholder(
    project_id: str,
    stakeholder_id: str,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(project_id, resource="Project")
        validate_uuid_path(stakeholder_id, resource="Stakeholder")
        project = svc.get_project_or_404(db, project_id)
        svc.assert_can_edit_project(
            db, project, current_user["id"], permission_slugs(db, current_user["id"])
        )
        stakeholder = refs.get_stakeholder_or_404(db, project_id, stakeholder_id)
        name = stakeholder.person_name
        refs.remove_stakeholder(db, stakeholder)
        db.commit()
        return {"message": f"{name} removed from this project"}
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


# --------------------------------------------------- join / dispute requests


@router.get(
    "/{project_id}/collaborators",
    response_model=ListResponse[ProjectCollaboratorResponse],
)
async def list_collaborators(
    project_id: str,
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(project_id, resource="Project")
        svc.get_project_or_404(db, project_id)
        from app.models.projects import ProjectCollaborator

        rows = (
            db.query(ProjectCollaborator)
            .filter(ProjectCollaborator.project_id == project_id)
            .all()
        )
        names = svc.resolve_user_names(db, [r.user_id for r in rows])
        data = [
            {
                "project_id": r.project_id,
                "user_id": r.user_id,
                "user_name": names.get(r.user_id),
                "granted_by": r.granted_by,
                "granted_at": r.granted_at,
            }
            for r in rows
        ]
        return {
            "data": data,
            "pagination": {"total": len(data), "page": 1, "limit": max(len(data), 1)},
            "empty": not data,
        }
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


def _takeover_payload(db: Session, requests) -> List[dict]:
    if not requests:
        return []
    from app.models.projects import Project

    projects = {
        p.id: p
        for p in db.query(Project)
        .filter(Project.id.in_({r.project_id for r in requests}))
        .all()
    }
    names = svc.resolve_user_names(
        db,
        [r.requester_user_id for r in requests] + [r.decided_by for r in requests],
    )
    return [
        {
            "id": r.id,
            "project_id": r.project_id,
            "project_code": getattr(projects.get(r.project_id), "project_code", None),
            "project_title": getattr(projects.get(r.project_id), "title", None),
            "kind": r.kind,
            "reason": r.reason,
            "status": r.status,
            "requester_user_id": r.requester_user_id,
            "requester_name": names.get(r.requester_user_id),
            "decided_by": r.decided_by,
            "decided_by_name": names.get(r.decided_by),
            "decided_at": r.decided_at,
            "decision_note": r.decision_note,
            "created_at": r.created_at,
        }
        for r in requests
    ]


@router.get(
    "/{project_id}/takeover-requests",
    response_model=ListResponse[TakeoverRequestResponse],
)
async def list_takeover_requests(
    project_id: str,
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(project_id, resource="Project")
        svc.get_project_or_404(db, project_id)
        from app.models.projects import ProjectTakeoverRequest

        rows = (
            db.query(ProjectTakeoverRequest)
            .filter(ProjectTakeoverRequest.project_id == project_id)
            .order_by(ProjectTakeoverRequest.created_at.desc())
            .all()
        )
        data = _takeover_payload(db, rows)
        return {
            "data": data,
            "pagination": {"total": len(data), "page": 1, "limit": max(len(data), 1)},
            "empty": not data,
        }
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/{project_id}/takeover-requests",
    response_model=TakeoverRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_takeover_request(
    project_id: str,
    payload: TakeoverRequestCreate,
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """Guarded by VIEW, not EDIT, deliberately.

    The whole point is that someone who CANNOT edit the project asks for access. An
    EDIT guard would let only the people who already have it apply.
    """
    try:
        validate_uuid_path(project_id, resource="Project")
        project = svc.get_project_or_404(db, project_id)
        request = svc.create_takeover_request(
            db,
            project=project,
            requester_user_id=current_user["id"],
            kind=payload.kind,
            reason=payload.reason,
        )
        db.commit()
        db.refresh(request)
        return _takeover_payload(db, [request])[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/{project_id}/takeover-requests/{request_id}/decide",
    response_model=TakeoverRequestResponse,
)
async def decide_takeover_request(
    project_id: str,
    request_id: str,
    payload: TakeoverRequestDecision,
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """Also VIEW-guarded: the service decides who may rule on this specific request
    (owner for a join, manager for a dispute), which is a per-record question a route
    guard cannot answer."""
    try:
        validate_uuid_path(project_id, resource="Project")
        validate_uuid_path(request_id, resource="Request")
        from app.models.projects import ProjectTakeoverRequest
        from app.services.error_handler import AppException

        request = (
            db.query(ProjectTakeoverRequest)
            .filter(
                ProjectTakeoverRequest.id == request_id,
                ProjectTakeoverRequest.project_id == project_id,
            )
            .first()
        )
        if request is None:
            raise AppException(
                status_code=404,
                message="Request not found on this project.",
                code="project_takeover_not_found",
            )
        svc.decide_takeover_request(
            db,
            request=request,
            decider_user_id=current_user["id"],
            decider_permissions=permission_slugs(db, current_user["id"]),
            approve=payload.approve,
            decision_note=payload.decision_note,
        )
        db.commit()
        db.refresh(request)
        return _takeover_payload(db, [request])[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))
