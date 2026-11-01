"""Document Access routes: who the AI may read each document type for (DOC-ACCESS-SIMPLE)."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.schemas.document_access import DocumentAccessDocumentsResponse, DocumentAccessResponse
from app.services import document_access_service
from app.services.company_scope_resolver import widen_if_requested
from app.services.error_handler import AppException
from app.services.user_service import UserPermissionService
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()

VIEW = "resource.attachment_types.view"
CONTACTS_VIEW = "user_management.contacts.view"


def _check_contact_permission(db: Session, current_user: dict, contact_id: Optional[str]) -> None:
    if contact_id and not UserPermissionService(db).check_user_has_permission(current_user["id"], CONTACTS_VIEW):
        raise AppException(status_code=403, message=f"Permission required: {CONTACTS_VIEW}", code="FORBIDDEN")


@router.get("", response_model=DocumentAccessResponse)
def get_document_access(
    request: Request,
    contact_id: Optional[str] = Query(None),
    company_scope: Optional[Literal["grants"]] = Query(None),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """The matrix: one row per document type, with the previewed contact's verdicts when `contact_id` is given."""
    _check_contact_permission(db, current_user, contact_id)
    with widen_if_requested(db, request, current_user, company_scope):
        return document_access_service.build_matrix(db, contact_id=contact_id)


@router.get("/{type_id}/documents", response_model=DocumentAccessDocumentsResponse)
def get_document_access_documents(
    type_id: str,
    request: Request,
    contact_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    company_scope: Optional[Literal["grants"]] = Query(None),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """The type's readable documents, with a verdict per document for the previewed contact."""
    _check_contact_permission(db, current_user, contact_id)
    validate_uuid_path(type_id, resource="Attachment Type")
    with widen_if_requested(db, request, current_user, company_scope):
        return document_access_service.list_documents(db, type_id, contact_id=contact_id, page=page, limit=limit)
