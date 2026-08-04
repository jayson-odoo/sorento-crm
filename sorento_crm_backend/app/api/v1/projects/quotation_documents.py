"""Quotation DOCUMENT API (S2 of the quotation rework).

The document is the letterhead the customer receives; the scopes under it are the tabs. URLs say
so: ``/projects/{id}/quotation-documents`` for the documents of one project, and
``/quotation-documents/{id}/scopes`` for its tabs. Lines keep hanging off a VERSION through the
existing ``quotations`` router, unchanged - "which version was this line on" is still the question
the model exists to answer, and an issue is a set of those versions.

Every rule lives in the service, not here: the 422 on editing an issued version, the refusal to
delete an issued document, and the exclusion of rate-only lines from every total. The route does
not second-guess any of them, so there is one place each is stated.
"""
from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.v1.projects._common import permission_slugs
from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.common import ListResponse
from app.schemas.projects import (
    ProjectQuotationDocumentCreate,
    ProjectQuotationDocumentResponse,
    ProjectQuotationDocumentUpdate,
    ProjectQuotationIssueResponse,
    ProjectQuotationScopeCreate,
    ProjectQuotationScopeSummary,
    ProjectQuotationScopeUpdate,
)
from app.services import project_quotation_document_service as svc
from app.services import project_service as projects
from app.services.error_handler import handle_internal_error
from app.services.uuid_path_param import validate_uuid_path

logger = logging.getLogger(__name__)

router = APIRouter()

VIEW = "projects.projects.view"
EDIT = "projects.projects.edit"
DELETE = "projects.projects.delete"


def _envelope(data: List[dict]):
    return {
        "data": data,
        "pagination": {"total": len(data), "page": 1, "limit": max(len(data), 1)},
        "empty": not data,
    }


def _editable_project(db: Session, project_id: str, current_user: dict):
    validate_uuid_path(project_id, resource="Project")
    project = projects.get_project_or_404(db, project_id)
    projects.assert_can_edit_project(
        db, project, current_user["id"], permission_slugs(db, current_user["id"])
    )
    return project


# ------------------------------------------------------------------ documents


@router.get(
    "/projects/{project_id}/quotation-documents",
    response_model=ListResponse[ProjectQuotationDocumentResponse],
)
async def list_quotation_documents(
    project_id: str,
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(project_id, resource="Project")
        projects.get_project_or_404(db, project_id)
        return _envelope(svc.serialize_documents(db, svc.list_documents(db, project_id)))
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/projects/{project_id}/quotation-documents",
    response_model=ProjectQuotationDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_quotation_document(
    project_id: str,
    payload: ProjectQuotationDocumentCreate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Arrives already filled in (AC-A2): reference, recipient and subject are all derived."""
    try:
        project = _editable_project(db, project_id, current_user)
        document = svc.create_document(
            db,
            project=project,
            actor_user_id=current_user["id"],
            payload=payload.model_dump(exclude_unset=True),
        )
        db.commit()
        db.refresh(document)
        return svc.serialize_document(db, document)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get(
    "/projects/{project_id}/quotation-documents/{document_id}",
    response_model=ProjectQuotationDocumentResponse,
)
async def get_quotation_document(
    project_id: str,
    document_id: str,
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(project_id, resource="Project")
        validate_uuid_path(document_id, resource="Quotation")
        projects.get_project_or_404(db, project_id)
        # Scoped to the project in the lookup, so a document belonging to another project 404s
        # rather than leaking its recipient and totals to whoever guessed the id.
        document = svc.get_document_or_404(db, project_id, document_id)
        return svc.serialize_document(db, document)
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.patch(
    "/projects/{project_id}/quotation-documents/{document_id}",
    response_model=ProjectQuotationDocumentResponse,
)
async def update_quotation_document(
    project_id: str,
    document_id: str,
    payload: ProjectQuotationDocumentUpdate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(document_id, resource="Quotation")
        _editable_project(db, project_id, current_user)
        document = svc.get_document_or_404(db, project_id, document_id)
        svc.update_document(db, document=document, payload=payload.model_dump(exclude_unset=True))
        db.commit()
        db.refresh(document)
        return svc.serialize_document(db, document)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.delete(
    "/projects/{project_id}/quotation-documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_quotation_document(
    project_id: str,
    document_id: str,
    current_user: dict = Depends(require_permission(DELETE)),
    db: Session = Depends(get_db),
):
    """Hard delete, and refused by the service once anything has been issued (AC-A6)."""
    try:
        validate_uuid_path(document_id, resource="Quotation")
        _editable_project(db, project_id, current_user)
        document = svc.get_document_or_404(db, project_id, document_id)
        svc.delete_document(db, document)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


# --------------------------------------------------------------------- scopes


@router.post(
    "/projects/{project_id}/quotation-documents/{document_id}/scopes",
    response_model=ProjectQuotationScopeSummary,
    status_code=status.HTTP_201_CREATED,
)
async def add_quotation_scope(
    project_id: str,
    document_id: str,
    payload: ProjectQuotationScopeCreate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """A tab, with its version 1 opened: a scope with no version has nowhere to put a line."""
    try:
        validate_uuid_path(document_id, resource="Quotation")
        _editable_project(db, project_id, current_user)
        document = svc.get_document_or_404(db, project_id, document_id)
        body = payload.model_dump(exclude_unset=True)
        scope = svc.add_scope(
            db,
            document=document,
            scope_label=body.pop("scope_label"),
            actor_user_id=current_user["id"],
            payload=body,
        )
        db.commit()
        db.refresh(scope)
        return svc._scope_summary(db, scope)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.patch(
    "/projects/{project_id}/quotation-documents/{document_id}/scopes/{quotation_id}",
    response_model=ProjectQuotationScopeSummary,
)
async def update_quotation_scope(
    project_id: str,
    document_id: str,
    quotation_id: str,
    payload: ProjectQuotationScopeUpdate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(document_id, resource="Quotation")
        validate_uuid_path(quotation_id, resource="Scope")
        _editable_project(db, project_id, current_user)
        document = svc.get_document_or_404(db, project_id, document_id)
        scope = svc.get_scope_or_404(db, document, quotation_id)
        svc.update_scope(db, scope=scope, payload=payload.model_dump(exclude_unset=True))
        db.commit()
        db.refresh(scope)
        return svc._scope_summary(db, scope)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


# --------------------------------------------------------------------- issues


@router.get(
    "/projects/{project_id}/quotation-documents/{document_id}/issues",
    response_model=ListResponse[ProjectQuotationIssueResponse],
)
async def list_quotation_issues(
    project_id: str,
    document_id: str,
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(document_id, resource="Quotation")
        validate_uuid_path(project_id, resource="Project")
        projects.get_project_or_404(db, project_id)
        document = svc.get_document_or_404(db, project_id, document_id)
        rows = svc.list_issues(db, document)
        return _envelope([svc.serialize_issue(db, row) for row in rows])
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/projects/{project_id}/quotation-documents/{document_id}/issue",
    response_model=ProjectQuotationIssueResponse,
    status_code=status.HTTP_201_CREATED,
)
async def issue_quotation_document(
    project_id: str,
    document_id: str,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Stamp R{n} and freeze what went out.

    After this, every version the issue names refuses line edits with 422
    ``quotation_version_issued`` - the customer is holding those rows, so a change opens the next
    revision instead of rewriting history under them.
    """
    try:
        validate_uuid_path(document_id, resource="Quotation")
        _editable_project(db, project_id, current_user)
        document = svc.get_document_or_404(db, project_id, document_id)
        record = svc.issue(db, document=document, actor_user_id=current_user["id"])
        db.commit()
        db.refresh(record)
        return svc.serialize_issue(db, record)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))
