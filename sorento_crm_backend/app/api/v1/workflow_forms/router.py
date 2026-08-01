"""Workflow forms: definitions, publish, submissions, transitions."""
from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Body, Depends, Query, status
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
    WorkflowLineDispositionOptionsOut,
    WorkflowLineDispositionRequest,
    WorkflowLineTransitionRequest,
    WorkflowPreviewOut,
    WorkflowPublishedDefinitionOut,
    WorkflowSubmissionCreate,
    WorkflowSubmissionLineOut,
    WorkflowSubmissionOut,
    WorkflowSubmissionUpdate,
    WorkflowTransitionRequest,
)
from app.form_engine.schemas import validate_form_doc
from app.services.error_handler import AppException
from app.services.workflow_forms_service import WorkflowFormsService
from app.services.workflow_submission_line_disposition import (
    active_disposition_options,
)
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
            joinedload(WorkflowSubmission.status),
        )
        .filter(WorkflowSubmission.id == sub_id)
        .first()
    )
    if not s:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Submission not found.",
            code="not_found",
        )
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
        # Turning line-derived status on is a definition edit, not a separate endpoint:
        # the two keys and the flag are one configuration and validating them apart would
        # let a half-saved pair through. A refused pair is 422
        # `status_derivation_misconfigured` and the row is left exactly as it was.
        derives_status_from_lines=body.derives_status_from_lines,
        derived_open_status_key=body.derived_open_status_key,
        derived_resolved_status_key=body.derived_resolved_status_key,
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
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission_with_api_key("workflow_forms.definitions.view")),
):
    """The status graph in force for this definition.

    Read from the status engine, not from the document: the document no longer carries
    states, so there is no draft-versus-published distinction to make here. A definition
    that has not forked reports the default graph with ``is_fork: false``.
    """
    return WorkflowFormsService(db).status_graph(definition_id)


@router.post("/definitions/validate-schema")
def validate_schema_body(
    schema: Dict[str, Any] = Body(...),
    _user: dict = Depends(require_permission("workflow_forms.definitions.edit")),
):
    """The publish gate, run without publishing. Reports every problem, not the first."""
    errs = validate_form_doc(schema)
    return {"valid": len(errs) == 0, "errors": errs}


# --- submissions ---


@router.get("/submissions", response_model=ListResponse[WorkflowSubmissionOut])
def list_submissions(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    definition_id: Optional[str] = Query(None),
    status_key: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission_with_api_key("workflow_forms.submissions.view")),
):
    svc = WorkflowFormsService(db)
    result = svc.list_submissions(page=page, limit=limit, definition_id=definition_id, status_key=status_key)
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
        body.to_status_id,
        body.remark,
        current_user.get("id") or "",
    )
    return _serialize_submission(svc, str(getattr(s, "id", "") or ""))


# --- submission lines ---
#
# Both writes answer with the whole SUBMISSION, not with the line. Deciding a line can
# move the header (that is the entire point of a derived status), so a line-shaped
# response would leave the caller holding a header it has to guess is stale. One payload,
# one refresh, and the line is in ``lines`` where the caller already reads it.
#
# The disposition options live at ``/line-dispositions`` rather than under ``/lines/``
# on purpose: a literal segment sharing a prefix with ``/lines/{line_id}`` is exactly
# how a fixed path gets captured as an id (the /integration/escalate case), and moving
# it out of the way costs nothing.


@router.get("/line-dispositions", response_model=WorkflowLineDispositionOptionsOut)
def list_line_dispositions(
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission_with_api_key("workflow_forms.submissions.view")),
):
    """The dispositions a line may be given, from the bound lookup set.

    Never a hardcoded list in the client: a disposition is admin-editable master data,
    so the picker has to read whatever the deployment currently offers or it will offer
    a value the write path refuses.
    """
    set_key, options = active_disposition_options(db)
    return {"set_key": set_key, "options": options}


@router.get("/lines/{line_id}", response_model=WorkflowSubmissionLineOut)
def get_line(
    line_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission_with_api_key("workflow_forms.submissions.view")),
):
    svc = WorkflowFormsService(db)
    return svc._line_out(svc.get_line(line_id))


@router.get("/lines/{line_id}/allowed-transitions")
def allowed_line_transitions(
    line_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission_with_api_key("workflow_forms.submissions.view")),
):
    """The decisions to offer on this line. Empty for a form without line statuses."""
    return {"transitions": WorkflowFormsService(db).allowed_line_transitions(line_id)}


@router.post("/lines/{line_id}/transition", response_model=WorkflowSubmissionOut)
def apply_line_transition(
    line_id: str,
    body: WorkflowLineTransitionRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("workflow_forms.submissions.transition")),
):
    """Decide one line, then re-derive the header.

    The same permission as a header move: this IS a status move, on the graph a line
    answers to, and a reviewer who may not move a submission must not be able to move it
    indirectly by deciding its lines.
    """
    svc = WorkflowFormsService(db)
    line = svc.apply_line_transition(line_id, body.to_status_id, current_user.get("id") or "")
    return _serialize_submission(svc, str(getattr(line, "submission_id", "") or ""))


@router.patch("/lines/{line_id}/disposition", response_model=WorkflowSubmissionOut)
def set_line_disposition(
    line_id: str,
    body: WorkflowLineDispositionRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("workflow_forms.submissions.edit")),
):
    """Record how a line will be settled, or clear it.

    The EDIT permission, not the transition one: a disposition is orthogonal to the
    line's status and recording it decides nothing, so it must not need the authority to
    move a submission (and must not move one).
    """
    svc = WorkflowFormsService(db)
    line = svc.set_line_disposition(
        line_id,
        body.disposition,
        current_user.get("id") or "",
        disposition_reason=body.disposition_reason,
    )
    return _serialize_submission(svc, str(getattr(line, "submission_id", "") or ""))
