"""Workflow forms: definitions, publish, submissions, transitions."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import (
    get_current_user,
    require_any_permission,
    require_any_permission_with_api_key,
    require_permission,
    require_permission_with_api_key,
)
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT, PaginationResponse
from app.schemas.workflow_forms import (
    WorkflowFormDefinitionCreate,
    WorkflowFormDefinitionOut,
    WorkflowFormDefinitionUpdate,
    WorkflowPreviewOut,
    WorkflowPublishedDefinitionOut,
    WorkflowSubmissionCreate,
    WorkflowSubmissionOut,
    WorkflowSubmissionUpdate,
    WorkflowTransitionRequest,
)
from app.services.workflow_forms_service import WorkflowFormsService, validate_schema
from app.models.workflow_forms import WorkflowSubmission

router = APIRouter()


def _serialize_submission(
    svc: WorkflowFormsService,
    sub_id: str,
    *,
    include_form_schema: bool = True,
) -> Dict[str, Any]:
    s = (
        svc.db.query(WorkflowSubmission)
        .options(
            joinedload(WorkflowSubmission.lines),
            joinedload(WorkflowSubmission.transition_logs),
            joinedload(WorkflowSubmission.definition),
        )
        .filter(WorkflowSubmission.id == sub_id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found.")
    return svc._submission_out(s, include_logs=True, include_form_schema=include_form_schema)


@router.get("/definitions", response_model=ListResponse[WorkflowFormDefinitionOut])
def list_definitions(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    q: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission_with_api_key("workflow_forms.definitions.view")),
):
    svc = WorkflowFormsService(db)
    result = svc.list_definitions(page=page, limit=limit, query=q, is_active=is_active)
    return ListResponse(
        data=result["data"],
        pagination=PaginationResponse(total=result["total"], page=result["page"], limit=result["limit"]),
        empty=result["total"] == 0,
    )


_RUNTIME_DEF_PERMS = (
    "workflow_forms.submissions.add",
    "workflow_forms.submissions.view",
    "workflow_forms.definitions.view",
)


@router.get(
    "/definitions/published-for-submission",
    response_model=ListResponse[WorkflowPublishedDefinitionOut],
)
def list_published_definitions_for_submission(
    db: Session = Depends(get_db),
    _user: dict = Depends(require_any_permission_with_api_key(list(_RUNTIME_DEF_PERMS))),
):
    """Published workflow forms only — for sidebar menus and users who can submit but cannot list all definitions."""
    svc = WorkflowFormsService(db)
    rows = svc.list_published_definitions_for_submission()
    return ListResponse(
        data=rows,
        pagination=PaginationResponse(total=len(rows), page=1, limit=max(len(rows), 1)),
        empty=len(rows) == 0,
    )


@router.post("/definitions", response_model=WorkflowFormDefinitionOut, status_code=status.HTTP_201_CREATED)
def create_definition(
    body: WorkflowFormDefinitionCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("workflow_forms.definitions.add")),
):
    svc = WorkflowFormsService(db)
    d = svc.create_definition(body.code, body.name, body.description, current_user.get("id") or "")
    return svc._def_out(d)


@router.get("/definitions/{definition_id}", response_model=WorkflowFormDefinitionOut)
def get_definition(
    definition_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission_with_api_key("workflow_forms.definitions.view")),
):
    svc = WorkflowFormsService(db)
    d = svc.get_definition(definition_id)
    return svc._def_out(d)


@router.patch("/definitions/{definition_id}", response_model=WorkflowFormDefinitionOut)
def update_definition(
    definition_id: str,
    body: WorkflowFormDefinitionUpdate,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission("workflow_forms.definitions.edit")),
):
    svc = WorkflowFormsService(db)
    d = svc.update_definition(
        definition_id,
        name=body.name,
        description=body.description,
        is_active=body.is_active,
        draft_schema=body.draft_schema,
    )
    return svc._def_out(d)


@router.post("/definitions/{definition_id}/publish", status_code=status.HTTP_201_CREATED)
def publish_definition(
    definition_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("workflow_forms.definitions.edit")),
):
    svc = WorkflowFormsService(db)
    v = svc.publish_definition(definition_id, current_user.get("id") or "")
    return {"id": v.id, "version_number": v.version_number, "definition_id": v.definition_id}


@router.delete("/definitions/{definition_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_definition(
    definition_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission("workflow_forms.definitions.delete")),
):
    WorkflowFormsService(db).delete_definition(definition_id)


@router.get("/definitions/{definition_id}/preview", response_model=WorkflowPreviewOut)
def preview_definition(
    definition_id: str,
    source: Literal["draft", "published"] = Query("draft"),
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission_with_api_key("workflow_forms.definitions.view")),
):
    svc = WorkflowFormsService(db)
    schema, src = svc.preview(definition_id, source=source)
    return WorkflowPreviewOut(schema=schema, source=src)


@router.get("/definitions/{definition_id}/published-schema", response_model=WorkflowPreviewOut)
def published_schema_for_submission(
    definition_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_any_permission_with_api_key(list(_RUNTIME_DEF_PERMS))),
):
    """Published schema for creating/viewing submissions (no definitions.view required)."""
    svc = WorkflowFormsService(db)
    schema, src = svc.preview(definition_id, source="published")
    return WorkflowPreviewOut(schema=schema, source=src)


@router.get("/definitions/{definition_id}/flow-graph")
def flow_graph(
    definition_id: str,
    source: Literal["draft", "published"] = Query("draft"),
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission_with_api_key("workflow_forms.definitions.view")),
):
    svc = WorkflowFormsService(db)
    schema, _src = svc.preview(definition_id, source=source)
    nodes: List[Dict[str, Any]] = []
    for s in schema.get("states") or []:
        if isinstance(s, dict):
            nodes.append(
                {
                    "id": s.get("id"),
                    "code": s.get("code"),
                    "name": s.get("name"),
                    "is_initial": bool(s.get("is_initial")),
                    "is_terminal": bool(s.get("is_terminal")),
                }
            )
    edges: List[Dict[str, Any]] = []
    for t in schema.get("transitions") or []:
        if isinstance(t, dict):
            edges.append(
                {
                    "id": t.get("id"),
                    "from_state_id": t.get("from_state_id"),
                    "to_state_id": t.get("to_state_id"),
                    "label": t.get("label"),
                    "direction": t.get("direction") or "forward",
                }
            )
    return {"nodes": nodes, "edges": edges}


@router.post("/definitions/validate-schema")
def validate_schema_body(
    schema: Dict[str, Any] = Body(...),
    _user: dict = Depends(require_permission("workflow_forms.definitions.edit")),
):
    errs = validate_schema(schema)
    return {"valid": len(errs) == 0, "errors": errs}


# --- submissions ---


@router.get("/submissions", response_model=ListResponse[WorkflowSubmissionOut])
def list_submissions(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    definition_id: Optional[str] = Query(None),
    state_code: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission_with_api_key("workflow_forms.submissions.view")),
):
    svc = WorkflowFormsService(db)
    result = svc.list_submissions(page=page, limit=limit, definition_id=definition_id, state_code=state_code)
    return ListResponse(
        data=result["data"],
        pagination=PaginationResponse(total=result["total"], page=result["page"], limit=result["limit"]),
        empty=result["total"] == 0,
    )


@router.post("/submissions", response_model=WorkflowSubmissionOut, status_code=status.HTTP_201_CREATED)
def create_submission(
    body: WorkflowSubmissionCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("workflow_forms.submissions.add")),
):
    svc = WorkflowFormsService(db)
    s = svc.create_submission(
        body.definition_id,
        body.header_data,
        [ln.model_dump() for ln in body.lines],
        current_user.get("id") or "",
    )
    return _serialize_submission(svc, str(getattr(s, "id", "") or ""))


@router.get("/submissions/{submission_id}", response_model=WorkflowSubmissionOut)
def get_submission(
    submission_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission_with_api_key("workflow_forms.submissions.view")),
):
    svc = WorkflowFormsService(db)
    return _serialize_submission(svc, submission_id)


@router.patch("/submissions/{submission_id}", response_model=WorkflowSubmissionOut)
def update_submission(
    submission_id: str,
    body: WorkflowSubmissionUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("workflow_forms.submissions.edit")),
):
    svc = WorkflowFormsService(db)
    lines = None
    if body.lines is not None:
        lines = [ln.model_dump() for ln in body.lines]
    s = svc.update_submission(
        submission_id,
        header_data=body.header_data,
        lines=lines,
        user_id=current_user.get("id") or "",
    )
    return _serialize_submission(svc, str(getattr(s, "id", "") or ""))


@router.delete("/submissions/{submission_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_submission(
    submission_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission("workflow_forms.submissions.delete")),
):
    WorkflowFormsService(db).delete_submission(submission_id)


@router.get("/submissions/{submission_id}/allowed-transitions")
def allowed_transitions(
    submission_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission_with_api_key("workflow_forms.submissions.view")),
):
    svc = WorkflowFormsService(db)
    return {"transitions": svc.allowed_transitions_for_user(submission_id, current_user.get("id") or "")}


@router.post("/submissions/{submission_id}/transition", response_model=WorkflowSubmissionOut)
def apply_transition(
    submission_id: str,
    body: WorkflowTransitionRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("workflow_forms.submissions.transition")),
):
    svc = WorkflowFormsService(db)
    s = svc.apply_transition(
        submission_id,
        body.transition_id,
        body.remark,
        current_user.get("id") or "",
    )
    return _serialize_submission(svc, str(getattr(s, "id", "") or ""))
