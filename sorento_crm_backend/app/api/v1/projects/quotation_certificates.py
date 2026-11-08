"""Certification tab routes of a quotation document (QUOTE-CERT-TAB).

Reads take the quotation's read permission; writes take the same right as editing the quotation
(edit + write access to the project). Writing the per-product DEFAULT boxes also needs
`master_data.certificates.edit`. Remove is a pending action (`quotation_certificate.remove`).
Plan: ``documentation/plans/certificates/PLAN-quote-cert-tab-08nov.md``.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.projects._common import permission_slugs
from app.api.v1.projects.quotation_documents import EDIT, READ, _editable_project, _issue_or_404
from app.database import get_db
from app.dependencies import require_any_permission_with_api_key, require_permission
from app.services import project_quotation_document_service as qdocs
from app.services import project_service as projects
from app.services import quotation_certificate_service as certs
from app.services.error_handler import AppException, handle_internal_error
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()

BASE = "/projects/{project_id}/quotation-documents/{document_id}/certificates"
DEFAULTS_SLUG = "master_data.certificates.edit"


class BoxIn(BaseModel):
    page: int
    x: float
    y: float
    w: float
    h: float
    product_id: Optional[str] = None


class AddIn(BaseModel):
    certificate_id: str


class BoxesIn(BaseModel):
    scope: Literal["quote", "default"]
    boxes: List[BoxIn] = Field(default_factory=list, max_length=certs.MAX_BOXES)


class PatchIn(BaseModel):
    send_to_customer: Optional[bool] = None


class ExportIn(BaseModel):
    issue_id: Optional[str] = None


def _document(db: Session, project_id: str, document_id: str):
    validate_uuid_path(project_id, resource="Project")
    validate_uuid_path(document_id, resource="Quotation")
    projects.get_project_or_404(db, project_id)
    return qdocs.get_document_or_404(db, project_id, document_id)


def _certificate_id(value: str) -> str:
    validate_uuid_path(value, resource="Certificate")
    return value


def _can_edit(db: Session, project_id: str, user: dict) -> bool:
    if EDIT not in permission_slugs(db, user["id"]):
        return False
    try:
        _editable_project(db, project_id, user)
    except AppException:
        return False
    return True


def _can_defaults(db: Session, user: dict) -> bool:
    return DEFAULTS_SLUG in permission_slugs(db, user["id"])


def _fail(exc: Exception):
    return exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


def _with_rights(db: Session, project_id: str, user: dict, body: dict) -> dict:
    return {**body, "can_edit": _can_edit(db, project_id, user), "can_edit_defaults": _can_defaults(db, user)}


@router.get(BASE)
def list_certificates(
    project_id: str,
    document_id: str,
    user: dict = Depends(require_any_permission_with_api_key(READ)),
    db: Session = Depends(get_db),
):
    try:
        document = _document(db, project_id, document_id)
        items = certs.list_rows(db, document)
        db.commit()
        return {
            "can_edit": _can_edit(db, project_id, user),
            "can_edit_defaults": _can_defaults(db, user),
            "items": items,
        }
    except Exception as exc:
        raise _fail(exc)


@router.post(BASE, status_code=201)
def add_certificate(
    project_id: str,
    document_id: str,
    payload: AddIn,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        _editable_project(db, project_id, current_user)
        document = _document(db, project_id, document_id)
        try:
            validate_uuid_path(payload.certificate_id, resource="Certificate")
        except AppException:
            raise AppException(status_code=404, message="Certificate not found.", code="certificate_not_found")
        row = certs.add(db, document, payload.certificate_id, str(current_user["id"]))
        db.commit()
        return row
    except Exception as exc:
        raise _fail(exc)


@router.post(f"{BASE}/export", status_code=202)
def export_certificates(
    project_id: str,
    document_id: str,
    payload: ExportIn,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Queue the merged "Certificates.pdf"; it appears in My Downloads when it is ready."""
    from app.services.company_scope import get_company_scope
    from app.services.download_service import DownloadService
    from app.services.queue_service import enqueue_job
    from app.tasks.export_tasks import generate_quotation_certificates_pdf

    try:
        document = _document(db, project_id, document_id)
        issue = None
        if payload.issue_id:
            validate_uuid_path(payload.issue_id, resource="Revision")
            issue = _issue_or_404(db, document, payload.issue_id)
        if certs.export_count(db, document, issue) == 0:
            db.commit()
            raise AppException(
                status_code=422,
                message="There are no certificates to export.",
                code="quotation_certificates_empty",
            )
        db.commit()
        downloads = DownloadService(db)
        download = downloads.create(
            user_id=str(current_user["id"]),
            kind="quotation_certificates",
            source_entity_type="quotation_document",
            source_entity_id=str(document.id),
            filename=certs.export_filename(document, issue),
        )
        scope = get_company_scope(db)
        company_id = next(iter(scope)) if isinstance(scope, frozenset) and len(scope) == 1 else None
        try:
            enqueue_job(
                generate_quotation_certificates_pdf,
                str(download.id),
                str(document.id),
                str(issue.id) if issue is not None else None,
                str(current_user["id"]),
                company_id=company_id,
            )
        except Exception as e:  # noqa: BLE001
            downloads.mark_failed(str(download.id), f"Could not queue the export: {e}")
            raise handle_internal_error("Could not queue the export. Please try again.")
        return {"download_id": str(download.id)}
    except Exception as exc:
        raise _fail(exc)


@router.get(f"{BASE}/{{certificate_id}}")
def read_certificate(
    project_id: str,
    document_id: str,
    certificate_id: str,
    user: dict = Depends(require_any_permission_with_api_key(READ)),
    db: Session = Depends(get_db),
):
    try:
        document = _document(db, project_id, document_id)
        body = certs.detail(db, document, _certificate_id(certificate_id))
        db.commit()
        return _with_rights(db, project_id, user, body)
    except Exception as exc:
        raise _fail(exc)


@router.get(f"{BASE}/{{certificate_id}}/file")
def read_certificate_file(
    project_id: str,
    document_id: str,
    certificate_id: str,
    _user: dict = Depends(require_any_permission_with_api_key(READ)),
    db: Session = Depends(get_db),
):
    try:
        document = _document(db, project_id, document_id)
        data = certs.file_for(db, document, _certificate_id(certificate_id))
        return Response(
            content=data,
            media_type="application/pdf",
            headers={"Content-Disposition": 'inline; filename="certificate.pdf"'},
        )
    except Exception as exc:
        raise _fail(exc)


@router.put(f"{BASE}/{{certificate_id}}/boxes")
def put_certificate_boxes(
    project_id: str,
    document_id: str,
    certificate_id: str,
    payload: BoxesIn,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        _editable_project(db, project_id, current_user)
        if payload.scope == certs.SCOPE_DEFAULT and not _can_defaults(db, current_user):
            raise AppException(
                status_code=403, message="You cannot change the default boxes.", code="permission_denied"
            )
        document = _document(db, project_id, document_id)
        body = certs.put_boxes(
            db,
            document,
            _certificate_id(certificate_id),
            payload.scope,
            [b.model_dump() for b in payload.boxes],
            str(current_user["id"]),
        )
        db.commit()
        return _with_rights(db, project_id, current_user, body)
    except Exception as exc:
        db.rollback()
        raise _fail(exc)


@router.delete(f"{BASE}/{{certificate_id}}/boxes")
def delete_certificate_boxes(
    project_id: str,
    document_id: str,
    certificate_id: str,
    scope: str = Query(certs.SCOPE_QUOTE),
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        _editable_project(db, project_id, current_user)
        if scope != certs.SCOPE_QUOTE:
            raise AppException(status_code=422, message="Unknown scope.", code="certificate_box_invalid")
        document = _document(db, project_id, document_id)
        body = certs.drop_quote_boxes(db, document, _certificate_id(certificate_id))
        db.commit()
        return _with_rights(db, project_id, current_user, body)
    except Exception as exc:
        db.rollback()
        raise _fail(exc)


@router.patch(f"{BASE}/{{certificate_id}}")
def patch_certificate(
    project_id: str,
    document_id: str,
    certificate_id: str,
    payload: PatchIn,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        _editable_project(db, project_id, current_user)
        document = _document(db, project_id, document_id)
        row = certs.set_send(
            db, document, _certificate_id(certificate_id), payload.send_to_customer, str(current_user["id"])
        )
        db.commit()
        return row
    except Exception as exc:
        db.rollback()
        raise _fail(exc)
