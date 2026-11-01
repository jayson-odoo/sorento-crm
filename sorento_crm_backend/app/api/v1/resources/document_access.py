"""Document Access routes: who the AI may read each document type for (DOC-ACCESS-SIMPLE)."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_any_permission, require_permission
from app.schemas.document_access import DocumentAccessDocumentsResponse, DocumentAccessResponse
from app.services import document_access_service
from app.api.v1.resources.attachments import ATTACHMENT_CATALOGUE_READERS
from app.models.base import get_company_scope
from app.services.company_scope_resolver import widen_if_requested
from app.services.error_handler import AppException
from app.services.user_service import UserPermissionService
from app.services.uuid_path_param import UUID_PATTERN, validate_uuid_path

router = APIRouter()

VIEW = "resource.attachment_types.view"
CONTACTS_VIEW = "user_management.contacts.view"
UPLOAD = "resource.attachments.upload"


def _check_contact_permission(db: Session, current_user: dict, contact_id: Optional[str]) -> None:
    if contact_id and not UserPermissionService(db).check_user_has_permission(current_user["id"], CONTACTS_VIEW):
        raise AppException(status_code=403, message=f"Permission required: {CONTACTS_VIEW}", code="FORBIDDEN")


@router.get("", response_model=DocumentAccessResponse)
def get_document_access(
    request: Request,
    contact_id: Optional[str] = Query(None, pattern=UUID_PATTERN),
    company_scope: Optional[Literal["grants"]] = Query(None),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """The matrix: one row per document type, with the previewed contact's verdicts when `contact_id` is given."""
    _check_contact_permission(db, current_user, contact_id)
    with widen_if_requested(db, request, current_user, company_scope):
        return document_access_service.build_matrix(db, contact_id=contact_id, user_id=current_user["id"])


@router.get("/{type_id}/documents", response_model=DocumentAccessDocumentsResponse)
def get_document_access_documents(
    type_id: str,
    request: Request,
    contact_id: Optional[str] = Query(None, pattern=UUID_PATTERN),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    company_scope: Optional[Literal["grants"]] = Query(None),
    current_user: dict = Depends(require_permission(VIEW)),
    _readers: dict = Depends(require_any_permission(ATTACHMENT_CATALOGUE_READERS)),
    db: Session = Depends(get_db),
):
    """The type's readable documents, with a verdict per document for the previewed contact."""
    _check_contact_permission(db, current_user, contact_id)
    validate_uuid_path(type_id, resource="Attachment Type")
    active = get_company_scope(db)  # before any widening: the company an edit may still touch
    can_upload = bool(UserPermissionService(db).check_user_has_permission(current_user["id"], UPLOAD))
    with widen_if_requested(db, request, current_user, company_scope):
        return document_access_service.list_documents(
            db,
            type_id,
            contact_id=contact_id,
            page=page,
            limit=limit,
            user_id=current_user["id"],
            can_upload=can_upload,
            active_companies=None if active is None else {str(c) for c in active},
        )
