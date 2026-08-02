"""Customer PO document intake and handwriting review (P4, P5). Contract sections 2 and 3.

Routes live at the module root rather than under `/projects/{project_id}` because they
are addressed both ways: nested for listing, and directly by id for everything else.
See `documentation/plans/CONTRACT-project-lead-to-so.md`.

Every rule lives in ``app.services.project_po_extraction_service``; these handlers
resolve the row, check who is asking, and commit. In particular the two refusals that
matter -- "a handwritten note still needs a decision" before a confirm, and "a
countersignature comes from a second person" -- are service refusals, so the worker and
anything else that reaches the same code is held to them too.

Rights are checked on the PROJECT, exactly as samples and phase-1 POs do it: whoever may
work the pursuit may record what arrived against it. Approval and countersignature reuse
the same edit right until `projects.customer_po.approve` (AC-L1) exists in the permission
registry, which is not this slice's file to change.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.api.v1.projects._common import permission_slugs
from app.database import get_db
from app.dependencies import require_permission
from app.schemas.project_po_intake import (
    AnnotationAcceptRequest,
    AnnotationActionResponse,
    AnnotationEditRequest,
    AnnotationRejectRequest,
    POApprovalResponse,
    POLineUpdate,
    POVersionDetailResponse,
    POVersionHeaderUpdate,
    POVersionUploadResponse,
)
from app.services import project_service as projects
from app.services.error_handler import AppException, handle_internal_error
from app.models.project_so import ProjectPOVersion
from app.services.project_po_extraction_service import ProjectPOExtractionService
from app.services.uuid_path_param import validate_uuid_path

logger = logging.getLogger(__name__)

router = APIRouter()

VIEW = "projects.projects.view"
EDIT = "projects.projects.edit"

# There is deliberately no `GET /purchase-orders/{po_id}/versions` here. The sales-order
# slice already serves that path (`sales_orders.py`, `POVersionOption`) with a richer row
# and the same permission, and two routes on one path means the OpenAPI describes one
# while FastAPI serves the other.

# 50 MB. A ten page colour scan at the resolution these actually arrive in runs to
# about 15, so this refuses a mistake rather than a document.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _project_for_edit(db: Session, project_id: str, current_user: dict):
    validate_uuid_path(project_id, resource="Project")
    project = projects.get_project_or_404(db, project_id)
    projects.assert_can_edit_project(
        db, project, current_user["id"], permission_slugs(db, current_user["id"])
    )
    return project


def _version_for_edit(db: Session, po_version_id: str, current_user: dict):
    validate_uuid_path(po_version_id, resource="PO document")
    service = ProjectPOExtractionService(db)
    version = service.get_version(po_version_id)
    po = service.get_po(version.purchase_order_id)
    _project_for_edit(db, po.project_id, current_user)
    return service, version


def _annotation_for_edit(db: Session, annotation_id: str, current_user: dict):
    validate_uuid_path(annotation_id, resource="Review card")
    service = ProjectPOExtractionService(db)
    annotation = service.get_annotation(annotation_id)
    version = service.get_version(annotation.po_version_id)
    po = service.get_po(version.purchase_order_id)
    _project_for_edit(db, po.project_id, current_user)
    return service, annotation


def _action_body(service: ProjectPOExtractionService, result: dict) -> dict:
    return {
        "annotation": service.serialize_annotation(result["annotation"]),
        "applied": result["applied"],
        "totals": result["totals"],
    }


# ------------------------------------------------------------------------- upload


@router.post(
    "/projects/{project_id}/purchase-orders/upload",
    response_model=POVersionUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_purchase_order_document(
    project_id: str,
    file: UploadFile = File(..., description="The customer PO as a PDF, JPEG or PNG"),
    po_number: Optional[str] = Form(None),
    purchase_order_id: Optional[str] = Form(None),
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """202. The document is stored and a version row exists; reading it runs on a worker.

    Committed BEFORE the job is enqueued, deliberately: a worker that starts on an
    uncommitted row reads nothing and marks a perfectly good document as failed.
    """
    try:
        project = _project_for_edit(db, project_id, current_user)
        if purchase_order_id:
            validate_uuid_path(purchase_order_id, resource="Purchase order")
        content = await file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise AppException(
                status_code=413,
                message="That file is larger than 50 MB. Re-scan it at a lower resolution.",
                code="po_upload_too_large",
            )

        service = ProjectPOExtractionService(db)
        version = service.create_version_from_upload(
            project=project,
            actor_user_id=current_user["id"],
            filename=file.filename,
            mime=file.content_type,
            content=content,
            po_number=po_number,
            purchase_order_id=purchase_order_id,
        )
        po = service.get_po(version.purchase_order_id)
        body = {
            "purchase_order_id": str(po.id),
            "po_number": po.po_number or "",
            "project_id": str(project.id),
            "project_title": project.title,
            "po_version_id": str(version.id),
            "version_no": version.version_no,
            "extraction_state": version.extraction_state,
            "page_count": version.page_count,
        }
        db.commit()
        service.enqueue_extraction(version)
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


# -------------------------------------------------------------------- version read


@router.get("/purchase-orders/{po_id}/versions")
async def list_purchase_order_versions(
    po_id: str,
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """Every document uploaded against this PO, newest first.

    A revision is a new version of the same commitment rather than a new PO, so the
    history is the only way to see what the customer sent and when. Deliberately a
    thin row: the confirm screen fetches the version it opens, and this list exists to
    reach it, not to duplicate it.
    """
    try:
        validate_uuid_path(po_id, resource="purchase order")
        service = ProjectPOExtractionService(db)
        po = service.get_po(po_id)
        projects.get_project_or_404(db, po.project_id)
        rows = (
            db.query(ProjectPOVersion)
            .filter(ProjectPOVersion.purchase_order_id == po.id)
            .order_by(ProjectPOVersion.version_no.desc())
            .all()
        )
        return {
            "data": [
                {
                    "id": str(row.id),
                    "version_no": row.version_no,
                    "extraction_state": row.extraction_state,
                    "page_count": row.page_count,
                    "source_filename": row.source_filename,
                    "confirmed_at": row.confirmed_at,
                    "created_at": row.created_at,
                }
                for row in rows
            ]
        }
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get(
    "/purchase-order-versions/{po_version_id}", response_model=POVersionDetailResponse
)
async def get_purchase_order_version(
    po_version_id: str,
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """Everything the side-by-side confirm screen renders: the page, the transcription,
    the four totals and the handwriting cards."""
    try:
        validate_uuid_path(po_version_id, resource="PO document")
        service = ProjectPOExtractionService(db)
        version = service.get_version(po_version_id)
        po = service.get_po(version.purchase_order_id)
        projects.get_project_or_404(db, po.project_id)
        body = service.serialize_version(version)
        # The read recomputes the totals off the current lines, so a stale counter on
        # the row is corrected rather than served. Cheap, and it means a read can never
        # disagree with what the same screen would compute for itself.
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.put(
    "/purchase-order-versions/{po_version_id}", response_model=POVersionDetailResponse
)
async def update_purchase_order_version_header(
    po_version_id: str,
    payload: POVersionHeaderUpdate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """AC-D3. The header carries the PO number, date, term and filing reference, and
    nothing extracted is accepted silently."""
    try:
        service, version = _version_for_edit(db, po_version_id, current_user)
        version = service.update_header(
            version=version, payload=payload.model_dump(exclude_unset=True)
        )
        body = service.serialize_version(version)
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.put(
    "/purchase-order-versions/{po_version_id}/lines/{line_id}",
    response_model=POVersionDetailResponse,
)
async def update_purchase_order_version_line(
    po_version_id: str,
    line_id: str,
    payload: POLineUpdate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Correct a transcribed line.

    Returns the whole recomputed version rather than the line: one edited line moves the
    four totals and can move the reconciliation, so returning the line alone would have
    the screen showing a corrected line beside stale totals until it refetched.
    """
    try:
        validate_uuid_path(line_id, resource="PO line")
        service, version = _version_for_edit(db, po_version_id, current_user)
        line = service.get_line(str(version.id), line_id)
        service.update_line(
            version=version, line=line, payload=payload.model_dump(exclude_unset=True)
        )
        body = service.serialize_version(version)
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/purchase-order-versions/{po_version_id}/confirm",
    response_model=POVersionDetailResponse,
)
async def confirm_purchase_order_version(
    po_version_id: str,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """409 while any handwriting card is still proposed: a person must have looked at
    the pencil before we write down what the PO commits us to.

    Returns the recomputed version with ``confirm_result`` naming what was written onto
    the phase-1 PO, so the screen does not have to refetch to show the outcome.
    """
    try:
        service, version = _version_for_edit(db, po_version_id, current_user)
        result = service.confirm_version(
            version=version, actor_user_id=current_user["id"]
        )
        body = service.serialize_version(version)
        body["confirm_result"] = {
            "line_count": result["line_count"],
            "po_amount": result["po_amount"],
            "model_mismatch_count": result["model_mismatch_count"],
            "price_mismatch_count": result["price_mismatch_count"],
        }
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


# --------------------------------------------------------------------- approvals


@router.post("/purchase-orders/{po_id}/approve", response_model=POApprovalResponse)
async def approve_purchase_order(
    po_id: str,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """AC-D8. CS cannot open the SO draft until this has happened (D21)."""
    try:
        validate_uuid_path(po_id, resource="Purchase order")
        service = ProjectPOExtractionService(db)
        po = service.get_po(po_id)
        _project_for_edit(db, po.project_id, current_user)
        po = service.approve_po(po=po, actor_user_id=current_user["id"])
        body = service.serialize_po_approval(po)
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post("/purchase-orders/{po_id}/countersign", response_model=POApprovalResponse)
async def countersign_purchase_order(
    po_id: str,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Requires an approved PO and a different person."""
    try:
        validate_uuid_path(po_id, resource="Purchase order")
        service = ProjectPOExtractionService(db)
        po = service.get_po(po_id)
        _project_for_edit(db, po.project_id, current_user)
        po = service.countersign_po(po=po, actor_user_id=current_user["id"])
        body = service.serialize_po_approval(po)
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


# ------------------------------------------------------- handwriting review cards


@router.post(
    "/po-annotations/{annotation_id}/accept", response_model=AnnotationActionResponse
)
async def accept_po_annotation(
    annotation_id: str,
    payload: Optional[AnnotationAcceptRequest] = None,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """The only path by which a strike-through ever cancels a line (D11)."""
    try:
        service, annotation = _annotation_for_edit(db, annotation_id, current_user)
        result = service.accept_annotation(
            annotation=annotation,
            actor_user_id=current_user["id"],
            note=(payload.note if payload else None),
        )
        body = _action_body(service, result)
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/po-annotations/{annotation_id}/edit", response_model=AnnotationActionResponse
)
async def edit_po_annotation(
    annotation_id: str,
    payload: AnnotationEditRequest,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """The person's reading wins, then applies exactly as an accept does."""
    try:
        service, annotation = _annotation_for_edit(db, annotation_id, current_user)
        result = service.edit_annotation(
            annotation=annotation,
            actor_user_id=current_user["id"],
            interpretation=payload.interpretation,
            interpretation_json=payload.interpretation_json,
            note=payload.note,
        )
        body = _action_body(service, result)
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/po-annotations/{annotation_id}/reject", response_model=AnnotationActionResponse
)
async def reject_po_annotation(
    annotation_id: str,
    payload: AnnotationRejectRequest,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Recorded as rejected, never deleted: a rejected reading is evidence too (AC-D4)."""
    try:
        service, annotation = _annotation_for_edit(db, annotation_id, current_user)
        result = service.reject_annotation(
            annotation=annotation, actor_user_id=current_user["id"], note=payload.note
        )
        body = _action_body(service, result)
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))
