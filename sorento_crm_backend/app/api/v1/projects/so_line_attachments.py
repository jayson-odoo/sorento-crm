"""Clarification files on a core sales-order line (#1312,
PLAN-oi-line-attachments-27sep.md), shared by the fulfilment board's paperclip and
the order inquiry Lines tab.

    POST   /project-sales/sales-order-lines/attachments/lookup    (view)
    POST   /project-sales/sales-order-lines/{line_id}/attachments (edit, multipart)
    DELETE /project-sales/sales-order-lines/{line_id}/attachments/{link_id} (edit)

Root-mounted (not nested under `/sales-orders/{pso_id}`) because the line id here is
the CORE `sales_order_lines.id` (Q1), addressed directly the same way the board and
the OI Lines tab already carry it - never through a project sales order.

Rights follow the plan's Q6: anyone with `projects.projects.view` sees and opens the
files, `projects.projects.edit` (the same grant that confirms the board and writes OI
lines) may add or remove one.
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.schemas.so_line_attachment import SoLineAttachmentLookupRequest
from app.services import so_line_attachments

router = APIRouter()

VIEW = "projects.projects.view"
EDIT = "projects.projects.edit"


@router.post("/sales-order-lines/attachments/lookup")
def lookup_sales_order_line_attachments(
    payload: SoLineAttachmentLookupRequest,
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """Every listed line's files, keyed by line id (AC-A5) - one call for a whole
    grid, never one per row."""
    return so_line_attachments.lookup(db, payload.line_ids)


@router.post("/sales-order-lines/{line_id}/attachments")
async def upload_sales_order_line_attachments(
    line_id: str,
    files: List[UploadFile] = File(..., description="One or more files"),
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Add files to a line, in upload order (AC-A1). Returns the line's full list,
    this upload included."""
    return await so_line_attachments.upload(
        db,
        line_id=line_id,
        files=files,
        actor_id=current_user.get("id"),
    )


@router.delete("/sales-order-lines/{line_id}/attachments/{link_id}")
def delete_sales_order_line_attachment(
    line_id: str,
    link_id: str,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Immediate delete - same `so_line_attachments.delete` the deferred
    `sales_order_line_attachment.delete` record action calls (`record_actions.py`);
    the FE's own x goes through that deferred path (D7), never this route directly."""
    so_line_attachments.delete(db, line_id, link_id, current_user.get("id"))
    return {"message": "Attachment deleted"}
