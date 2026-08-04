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

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.api.v1.projects._common import permission_slugs
from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.common import ListResponse
from app.schemas.projects import (
    ProjectQuotationDocumentCreate,
    QuotationSignatureRequest,
    QuotationSignatureResponse,
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


def _client_ip(request: Request) -> str | None:
    """The signer's address, recorded because a signature with provenance is stronger evidence."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.client.host if request.client else None


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


# --------------------------------------------------------------------- signing


@router.post(
    "/projects/{project_id}/quotation-documents/{document_id}/sign",
    response_model=QuotationSignatureResponse,
    status_code=status.HTTP_201_CREATED,
)
async def sign_quotation_document(
    project_id: str,
    document_id: str,
    payload: QuotationSignatureRequest,
    request: Request,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Sign the draft, which is what makes it issuable (AC-H1).

    Separate from issuing on purpose: a person signs, checks the document, then issues. Signing
    again before issuing simply replaces the signature on the draft; a signature already carried by
    an issue is a copy and is never touched.
    """
    try:
        validate_uuid_path(document_id, resource="Quotation")
        _editable_project(db, project_id, current_user)
        document = svc.get_document_or_404(db, project_id, document_id)
        body = payload.model_dump(exclude_unset=True)
        body["ip_address"] = _client_ip(request)
        body["user_agent"] = request.headers.get("user-agent")
        signature = svc.sign_as_sorento(
            db, document=document, actor_user_id=current_user["id"], payload=body
        )
        db.commit()
        db.refresh(signature)
        return svc._serialize_signature(signature)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/projects/{project_id}/quotation-documents/{document_id}/issues/{issue_id}/sign-link",
)
async def create_quotation_sign_link(
    project_id: str,
    document_id: str,
    issue_id: str,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """The tokenised link to send the customer.

    Reused while still valid, so re-sending a quotation does not invalidate the link already
    sitting in somebody's inbox.
    """
    try:
        validate_uuid_path(document_id, resource="Quotation")
        validate_uuid_path(issue_id, resource="Revision")
        _editable_project(db, project_id, current_user)
        document = svc.get_document_or_404(db, project_id, document_id)
        record = next(
            (row for row in svc.list_issues(db, document) if str(row.id) == issue_id), None
        )
        if record is None:
            from app.services.error_handler import AppException

            raise AppException(
                status_code=404, message="Revision not found.", code="quotation_issue_not_found"
            )
        token = svc.issue_sign_link(db, record=record)
        db.commit()
        return {
            "token": token,
            "path": f"/quotation-sign/{token}",
            "expires_at": record.sign_token_expires_at,
        }
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


# ------------------------------------------------------------------------ pdf


@router.get(
    "/projects/{project_id}/quotation-documents/{document_id}/issues/{issue_id}/pdf",
)
async def download_quotation_issue_pdf(
    project_id: str,
    document_id: str,
    issue_id: str,
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """The issued quotation, as the customer received it.

    Rendered from the ISSUE snapshot every time rather than from live rows, so a download next year
    is what was sent. Generated on demand rather than stored: the snapshot IS the source of truth,
    so a stored file would be a second copy of the same facts that could fall out of step with it.
    """
    from app.services.complaint_pdf_service import PDFRenderingUnavailable
    from app.services import project_quotation_pdf_service as pdf
    from app.services.error_handler import AppException

    try:
        validate_uuid_path(document_id, resource="Quotation")
        validate_uuid_path(issue_id, resource="Revision")
        validate_uuid_path(project_id, resource="Project")
        projects.get_project_or_404(db, project_id)
        document = svc.get_document_or_404(db, project_id, document_id)
        record = next(
            (row for row in svc.list_issues(db, document) if str(row.id) == issue_id), None
        )
        if record is None:
            raise AppException(
                status_code=404, message="Revision not found.", code="quotation_issue_not_found"
            )
        try:
            pdf_bytes, filename = pdf.render_issue_pdf(db, record)
        except PDFRenderingUnavailable as unavailable:
            # A missing native library is an operational fact, not a bug in the request. Say so,
            # rather than letting it surface as an unexplained 500.
            raise AppException(
                status_code=503,
                message=(
                    "PDF rendering is not available on this server. "
                    f"Ask an administrator to install the rendering libraries. ({unavailable})"
                ),
                code="pdf_rendering_unavailable",
            )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


# ---------------------------------------------------------------------- excel


@router.get(
    "/projects/{project_id}/quotation-documents/{document_id}/issues/{issue_id}/xlsx",
)
async def download_quotation_issue_xlsx(
    project_id: str,
    document_id: str,
    issue_id: str,
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """The same issued quotation as a workbook, one sheet per scope (AC-F2).

    Sent as an ATTACHMENT rather than inline: nobody previews a spreadsheet in a browser tab, and
    an inline disposition on a binary the browser cannot render turns a download into a blank page.
    Built from the ISSUE snapshot on demand, exactly as the PDF is, so the two artifacts of one
    revision can never quote different money.
    """
    from app.services import project_quotation_excel_service as excel
    from app.services.error_handler import AppException

    try:
        validate_uuid_path(document_id, resource="Quotation")
        validate_uuid_path(issue_id, resource="Revision")
        validate_uuid_path(project_id, resource="Project")
        projects.get_project_or_404(db, project_id)
        document = svc.get_document_or_404(db, project_id, document_id)
        # Checked against THIS document, not merely fetched by id: otherwise a known issue id
        # exports through any document the caller may view, handing over a price list they were
        # never shown in the one format that is already machine readable.
        record = next(
            (row for row in svc.list_issues(db, document) if str(row.id) == issue_id), None
        )
        if record is None:
            raise AppException(
                status_code=404, message="Revision not found.", code="quotation_issue_not_found"
            )
        payload, filename = excel.render_issue_xlsx(db, record)
        return Response(
            content=payload,
            media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))
