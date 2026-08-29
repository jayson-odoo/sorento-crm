"""Delivery schedule intake, reconciliation and phases (P6). Contract section 4.

Routes live at the module root rather than under `/projects/{project_id}` because they
are addressed both ways: nested for listing, and directly by id for everything else.
See `documentation/plans/CONTRACT-project-lead-to-so.md`.

Every rule lives in `ProjectScheduleService`, so the two things a reviewer might expect
to find here are deliberately not here: the reconciliation verdict, and the refusal to
confirm an unreconciled column. A second copy of either would be a second answer to
"did this schedule agree with the PO".
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.v1.projects._common import permission_slugs
from app.database import get_db
from app.dependencies import require_permission
from app.schemas.common import ListResponse
from app.schemas.project_schedule import (
    DeliveryScheduleDeleteResponse,
    DeliveryScheduleListRow,
    DeliveryScheduleUploadResponse,
    DeliveryScheduleVersionListRow,
    DeliveryScheduleVersionResponse,
    ScheduleCellsUpdate,
    ScheduleColumnDismiss,
    ScheduleConfirmRequest,
    ScheduleProductResolve,
)
from app.services import project_po_service as po_svc
from app.services import project_service as projects
from app.services.error_handler import AppException, handle_internal_error
from app.services.project_schedule_service import ProjectScheduleService
from app.services.uuid_path_param import validate_uuid_path

logger = logging.getLogger(__name__)

router = APIRouter()

VIEW = "projects.projects.view"
EDIT = "projects.projects.edit"

# A schedule is a PDF or a photograph of one. Anything else is a person uploading the
# wrong file, and saying so now beats a failed extraction twenty minutes later.
ALLOWED_MIMES = {"application/pdf", "image/png", "image/jpeg", "image/jpg"}
MAX_BYTES = 30 * 1024 * 1024


def _service(db: Session) -> ProjectScheduleService:
    return ProjectScheduleService(db)


def _envelope(data: list) -> dict:
    return {
        "data": data,
        "pagination": {"total": len(data), "page": 1, "limit": max(len(data), 1)},
        "empty": not data,
    }


def _schedule_for_edit(db: Session, schedule_id: str, current_user: dict):
    """Same rights as the version routes: whoever may work the pursuit may remove a
    schedule that came out of it."""
    validate_uuid_path(schedule_id, resource="Delivery schedule")
    service = _service(db)
    schedule = service.get_schedule(schedule_id)
    project = projects.get_project_or_404(db, schedule.project_id)
    projects.assert_can_edit_project(
        db, project, current_user["id"], permission_slugs(db, current_user["id"])
    )
    return schedule


def _version_for_edit(db: Session, version_id: str, current_user: dict):
    """Rights live on the PROJECT, exactly as they do for samples and POs: whoever may
    work the pursuit may bind the schedule that came out of it."""
    validate_uuid_path(version_id, resource="Delivery schedule version")
    service = _service(db)
    version = service.get_version(version_id)
    schedule = service.schedule_for(version)
    project = projects.get_project_or_404(db, schedule.project_id)
    projects.assert_can_edit_project(
        db, project, current_user["id"], permission_slugs(db, current_user["id"])
    )
    return version


@router.get(
    "/projects/{project_id}/delivery-schedules",
    response_model=ListResponse[DeliveryScheduleListRow],
)
async def list_project_delivery_schedules(
    project_id: str,
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """Where a person starts: the schedules on this project, each with its latest
    version and how much of it reconciled."""
    try:
        validate_uuid_path(project_id, resource="Project")
        projects.get_project_or_404(db, project_id)
        return _envelope(_service(db).list_schedules(project_id))
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get(
    "/delivery-schedules/{schedule_id}/versions",
    response_model=ListResponse[DeliveryScheduleVersionListRow],
)
async def list_delivery_schedule_versions(
    schedule_id: str,
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """The revision history, newest first. R1 and R2 are two documents of one
    commitment (AC-G1), never one grid that was edited."""
    try:
        validate_uuid_path(schedule_id, resource="Delivery schedule")
        return _envelope(_service(db).list_versions(schedule_id))
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/purchase-orders/{po_id}/delivery-schedules/upload",
    response_model=DeliveryScheduleUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_delivery_schedule(
    po_id: str,
    file: UploadFile = File(...),
    issuer_party_id: Optional[str] = Form(None),
    revision_label: Optional[str] = Form(None),
    delivery_schedule_id: Optional[str] = Form(None),
    po_version_id: Optional[str] = Form(None),
    force: bool = Form(False),
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Store the document, open a version, queue the read.

    `po_version_id` is what the checksum will reconcile AGAINST and defaults to the PO's
    latest confirmed version: a schedule issued before a handwritten cancellation
    reconciles to the PO as it stood, and rejecting it would reject a document the
    customer considers correct (finding G1).

    `force=true` overrides the duplicate-upload guard - the same bytes already stored
    against this schedule 409s by default (`schedule_version_duplicate`), naming the
    version that already holds them.
    """
    try:
        validate_uuid_path(po_id, resource="Purchase order")
        po = po_svc.get_po(db, po_id)
        project = projects.get_project_or_404(db, po.project_id)
        projects.assert_can_edit_project(
            db, project, current_user["id"], permission_slugs(db, current_user["id"])
        )

        content = await file.read()
        mime = (file.content_type or "").lower().split(";")[0].strip()
        if mime not in ALLOWED_MIMES:
            raise AppException(
                status_code=422,
                message="Upload the schedule as a PDF, a JPEG or a PNG.",
                code="schedule_unsupported_type",
            )
        if not content:
            raise AppException(
                status_code=422,
                message="That file is empty.",
                code="schedule_empty_file",
            )
        if len(content) > MAX_BYTES:
            raise AppException(
                status_code=422,
                message="That file is larger than 30 MB.",
                code="schedule_file_too_large",
            )

        pages = _page_count(content, mime)
        service = _service(db)
        version = service.create_version(
            purchase_order=po,
            content=content,
            filename=file.filename or "delivery-schedule.pdf",
            mime=mime,
            actor_user_id=current_user["id"],
            issuer_party_id=issuer_party_id,
            revision_label=revision_label,
            delivery_schedule_id=delivery_schedule_id,
            po_version_id=po_version_id,
            page_count=pages,
            force=force,
        )
        body = {
            "delivery_schedule_id": str(version.delivery_schedule_id),
            "schedule_version_id": str(version.id),
            "version_no": version.version_no,
            "extraction_state": version.extraction_state,
            "page_count": pages,
        }
        db.commit()

        # After the commit: the worker resolves the version by id, and a job enqueued
        # inside the transaction can be claimed before the row exists. The service records
        # which job is reading this version and reports its own enqueue failures on the
        # row, so a version can never sit on "queued" with nothing behind it (S20).
        service.enqueue_extraction(version)
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


def _page_count(content: bytes, mime: str) -> Optional[int]:
    from app.services.document_extraction import page_count

    try:
        return page_count(content, mime)
    except Exception:  # noqa: BLE001 - a page count is information, not a gate
        logger.warning("could not count pages on the uploaded schedule", exc_info=True)
        return None


@router.get(
    "/delivery-schedule-versions/{version_id}",
    response_model=DeliveryScheduleVersionResponse,
)
async def get_delivery_schedule_version(
    version_id: str,
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """The whole grid plus its verdict, per column. Reconciliation is never per
    document: 29 of 37 columns reconciled on the first pass of the real R1, and a
    wholesale reject would have thrown the other 29 away with them."""
    try:
        validate_uuid_path(version_id, resource="Delivery schedule version")
        return _service(db).get_version_detail(version_id)
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/delivery-schedule-versions/{version_id}/retry-extraction",
    response_model=DeliveryScheduleVersionResponse,
)
async def retry_delivery_schedule_extraction(
    version_id: str,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Read this schedule again, on the same version (S20).

    Same endpoint, same reasoning as the customer PO: the commonest way a read ends with
    nothing on the row is a background work-horse killed part-way, which says nothing about
    the document. 409 when there is nothing to retry, with the reason in the message.
    """
    try:
        service = _service(db)
        version = _version_for_edit(db, version_id, current_user)
        service.retry_extraction(version)
        return service.get_version_detail(version_id)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.put(
    "/delivery-schedule-versions/{version_id}/cells",
    response_model=DeliveryScheduleVersionResponse,
)
async def update_delivery_schedule_cells(
    version_id: str,
    payload: ScheduleCellsUpdate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """The per-column correction path. Upsert by (phase, product); a quantity of "0"
    deletes the cell, because a blank means this phase does not take this product."""
    try:
        version = _version_for_edit(db, version_id, current_user)
        service = _service(db)
        service.update_cells(
            version.id, [cell.model_dump(exclude_unset=True) for cell in payload.cells]
        )
        db.commit()
        return service.get_version_detail(version_id)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.put(
    "/delivery-schedule-versions/{version_id}/products/{product_index}",
    response_model=DeliveryScheduleVersionResponse,
)
async def resolve_delivery_schedule_product(
    version_id: str,
    product_index: int,
    payload: ScheduleProductResolve,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Identify a column, once. The mapping is remembered for this customer, so the
    next schedule resolves the same code without asking anybody (AC-E4)."""
    try:
        version = _version_for_edit(db, version_id, current_user)
        service = _service(db)
        service.resolve_product_column(
            version.id,
            product_index,
            payload.product_id,
            actor_user_id=current_user["id"],
        )
        db.commit()
        return service.get_version_detail(version_id)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.put(
    "/delivery-schedule-versions/{version_id}/columns/{column_index}/dismissal",
    response_model=DeliveryScheduleVersionResponse,
)
async def dismiss_delivery_schedule_column(
    version_id: str,
    column_index: int,
    payload: ScheduleColumnDismiss,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Overrule ONE column's failing check as a false signal, with a reason.

    The whole-sheet acknowledgement at confirm stays and is unchanged; this is the same
    judgement taken per column, at the point a person is looking at that column. Sending
    `dismissed: false` puts it back under its verdict.
    """
    try:
        version = _version_for_edit(db, version_id, current_user)
        service = _service(db)
        service.dismiss_column_verdict(
            version.id,
            column_index,
            dismissed=payload.dismissed,
            reason=payload.reason,
            actor_user_id=current_user["id"],
        )
        db.commit()
        return service.get_version_detail(version_id)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/delivery-schedule-versions/{version_id}/confirm",
    response_model=DeliveryScheduleVersionResponse,
)
async def confirm_delivery_schedule_version(
    version_id: str,
    payload: Optional[ScheduleConfirmRequest] = None,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """409 while any column is unreconciled, unless it is acknowledged with a reason.

    Confirming promotes the phases this version carries onto the project, keyed on
    (area_group, sequence) and NOT the label: the COMMON AREA rows carry no label at
    all, and matching by label collapsed three real phases into one (finding G6).
    """
    try:
        version = _version_for_edit(db, version_id, current_user)
        body = payload or ScheduleConfirmRequest()
        service = _service(db)
        service.confirm(
            version.id,
            actor_user_id=current_user["id"],
            acknowledge_unreconciled=body.acknowledge_unreconciled,
            reason=body.reason,
        )
        db.commit()
        return service.get_version_detail(version_id)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/delivery-schedule-versions/{version_id}/revision-proposals/{index}/accept",
    response_model=DeliveryScheduleVersionResponse,
)
async def accept_revision_proposal(
    version_id: str,
    index: int,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Writes the override for every cell this proposal names (section 9.7c). 409
    when it was already decided, or the version is confirmed."""
    try:
        version = _version_for_edit(db, version_id, current_user)
        service = _service(db)
        service.accept_revision_proposal(
            version.id, index, actor_user_id=current_user["id"]
        )
        db.commit()
        return service.get_version_detail(version_id)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/delivery-schedule-versions/{version_id}/revision-proposals/{index}/reject",
    response_model=DeliveryScheduleVersionResponse,
)
async def reject_revision_proposal(
    version_id: str,
    index: int,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Marks the proposal rejected. Writes no override; the note and the tint show
    as-is. 409 when it was already decided, or the version is confirmed."""
    try:
        version = _version_for_edit(db, version_id, current_user)
        service = _service(db)
        service.reject_revision_proposal(
            version.id, index, actor_user_id=current_user["id"]
        )
        db.commit()
        return service.get_version_detail(version_id)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.delete(
    "/delivery-schedules/{schedule_id}",
    response_model=DeliveryScheduleDeleteResponse,
)
async def delete_delivery_schedule(
    schedule_id: str,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Hard delete: every version, its cells and its document, then the schedule. The
    purchase order it was checked against is untouched.

    409, naming the blocker, when a CONFIRMED version is a live commitment - built into a
    published/amended sales order, or named by a published amendment's delta. Everything
    else the client marks confirmed may still be deleted: this is still the experimental
    phase (captain's call).
    """
    try:
        service = _service(db)
        schedule = _schedule_for_edit(db, schedule_id, current_user)
        deleted = service.delete_schedule(schedule.id)
        db.commit()
        return {"success": True, "deleted": deleted}
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.delete(
    "/delivery-schedule-versions/{version_id}",
    response_model=DeliveryScheduleDeleteResponse,
)
async def delete_delivery_schedule_version(
    version_id: str,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """One version, and its cells and document.

    409 ``schedule_version_last`` on the LAST version of a schedule - delete the schedule
    instead, which is what actually removes it - and the same live-commitment refusal
    ``DELETE /delivery-schedules/{schedule_id}`` runs, scoped to this one version.
    """
    try:
        version = _version_for_edit(db, version_id, current_user)
        service = _service(db)
        deleted = service.delete_schedule_version(version.id)
        db.commit()
        return {"success": True, "deleted": deleted}
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))
