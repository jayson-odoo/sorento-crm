"""Spare part requests and their row photos (SPARE-PART-ORDER-REQUEST).

    GET    /project-sales/spare-part-requests                      (own, decidable, admin: G3)
    POST   /project-sales/spare-part-requests                      (create grant)
    GET    /project-sales/spare-part-requests/{id}                 (whoever can see it)
    PUT    /project-sales/spare-part-requests/{id}                 (requester, draft / pending /
                                                                    rejected; pending restarts
                                                                    approval, G5)
    POST   /project-sales/spare-part-requests/{id}/submit          (requester)
    PATCH  /project-sales/spare-part-requests/{id}/lines/{row_id}  (current approver)
    POST   /project-sales/spare-part-requests/{id}/approve         (current approver)
    POST   /project-sales/spare-part-requests/{id}/reject          (current approver)
    POST   /project-sales/spare-part-requests/{id}/revise          (requester)
    POST   /project-sales/order-inquiry-rows/attachments/lookup    (whoever can see the inquiry)
    POST   /project-sales/order-inquiry-rows/{row_id}/attachments  (requester while draft /
                                                                    rejected, approver while pending)
    DELETE /project-sales/order-inquiry-rows/{row_id}/attachments/{link_id}  (same)

The request IS an order inquiry; the OI page reads it through `/order-inquiry-headers`. Who may
decide is the current Form SLA stage's team (or an admin), never the requester, checked in
`spare_part_request_service` on every call, so a direct API call gets the same 403 the screen
implies (UAC A2).
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_any_permission, require_permission
from app.models.project_so import OrderInquiry, OrderInquiryRow
from app.schemas.common import MAX_PAGE_LIMIT, ListResponse
from app.schemas.spare_part_request import (
    OrderInquiryRowAttachmentLookupRequest,
    SparePartApproveIn,
    SparePartLineEditIn,
    SparePartRejectIn,
    SparePartRequestIn,
    SparePartRequestListItem,
    SparePartRequestOut,
)
from app.services import so_line_attachments
from app.services import spare_part_request_service as spr
from app.services.error_handler import AppException
from app.services.stock_read_scope import SPARE_PART_READ
from app.services.user_service import UserPermissionService
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()

VIEW = "projects.projects.view"
CREATE = spr.CREATE_PERMISSION
_READ = require_any_permission([VIEW, *SPARE_PART_READ])


def _has_view(db: Session, user_id: str) -> bool:
    return UserPermissionService(db).check_user_has_permission(user_id, VIEW)


def _visible(db: Session, inquiry_id: str, user: dict) -> OrderInquiry:
    """The request, or the same 404 an unknown id gets when this user may not see it."""
    inquiry_id = validate_uuid_path(inquiry_id, resource="Order request")
    inquiry = spr.get(db, inquiry_id)
    uid = str(user.get("id"))
    if not spr.can_view(db, inquiry, uid, has_view=_has_view(db, uid)):
        raise AppException(404, "This order request no longer exists.", code="spr_not_found")
    return inquiry


def _to_decide(inquiry_id: str, db: Session) -> OrderInquiry:
    """A decision route answers 403 to anyone who is not the current approver (UAC A2, "also
    by direct API call"), so it reads the request without the visibility 404 and leaves the
    refusal to the service."""
    return spr.get(db, validate_uuid_path(inquiry_id, resource="Order request"))


def _out(db: Session, inquiry: OrderInquiry, user: dict) -> dict:
    db.refresh(inquiry)
    return spr.detail(db, inquiry, str(user.get("id")))


# ai: not-for-assistant deferred, not excluded: the Order Inquiry assistant reader incl. spare part requests (list mine / pending my approval / status of one) lands in follow-up slice SPARE-PART-ORDER-REQUEST-B (crew ruling); Order Inquiries had no assistant reader before this lane
@router.get("/spare-part-requests", response_model=ListResponse[SparePartRequestListItem])
def list_spare_part_requests(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None, max_length=200),
    state: Optional[List[str]] = Query(None, description="draft, pending_approval, rejected, raised"),
    sort: Optional[str] = Query("submitted_at"),
    dir: Optional[str] = Query("desc"),
    current_user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    return spr.list_requests(
        db, str(current_user["id"]), page=page, limit=limit, query=query, states=state,
        sort=sort, direction=dir,
    )


@router.post("/spare-part-requests", response_model=SparePartRequestOut, status_code=201)
def create_spare_part_request(
    payload: SparePartRequestIn,
    current_user: dict = Depends(require_permission(CREATE)),
    db: Session = Depends(get_db),
):
    inquiry = spr.create(db, payload.model_dump(mode="json"), str(current_user["id"]))
    db.commit()
    return _out(db, inquiry, current_user)


@router.get("/spare-part-requests/{inquiry_id}", response_model=SparePartRequestOut)
def get_spare_part_request(
    inquiry_id: str,
    current_user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    return spr.detail(db, _visible(db, inquiry_id, current_user), str(current_user["id"]))


@router.put("/spare-part-requests/{inquiry_id}", response_model=SparePartRequestOut)
def update_spare_part_request(
    inquiry_id: str,
    payload: SparePartRequestIn,
    current_user: dict = Depends(require_permission(CREATE)),
    db: Session = Depends(get_db),
):
    inquiry = _visible(db, inquiry_id, current_user)
    spr.update(db, inquiry, payload.model_dump(mode="json"), str(current_user["id"]))
    db.commit()
    return _out(db, inquiry, current_user)


@router.post("/spare-part-requests/{inquiry_id}/submit", response_model=SparePartRequestOut)
def submit_spare_part_request(
    inquiry_id: str,
    current_user: dict = Depends(require_permission(CREATE)),
    db: Session = Depends(get_db),
):
    inquiry = _visible(db, inquiry_id, current_user)
    spr.submit(db, inquiry, str(current_user["id"]))
    db.commit()
    return _out(db, inquiry, current_user)


@router.patch(
    "/spare-part-requests/{inquiry_id}/lines/{row_id}", response_model=SparePartRequestOut
)
def edit_spare_part_request_line(
    inquiry_id: str,
    row_id: str,
    payload: SparePartLineEditIn,
    current_user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    inquiry = _to_decide(inquiry_id, db)
    row_id = validate_uuid_path(row_id, resource="Line")
    uid = str(current_user["id"])
    # SPARE-PART-OR-B (U4.3): the requester's own qty change on a revision is a requester's
    # write, so it needs the create grant like every other one (edit, submit, revise).
    if spr.in_revision(inquiry) and spr.is_requester(inquiry, uid):
        if not UserPermissionService(db).check_user_has_permission(uid, CREATE):
            raise AppException(403, "You cannot change this request.", code="FORBIDDEN")
    body = payload.model_dump(mode="json")
    spr.edit_line(
        db, inquiry, row_id, str(current_user["id"]), qty=body.get("qty"),
        unit_price=body.get("unit_price"),
    )
    db.commit()
    return _out(db, inquiry, current_user)


@router.post("/spare-part-requests/{inquiry_id}/approve", response_model=SparePartRequestOut)
def approve_spare_part_request(
    inquiry_id: str,
    payload: SparePartApproveIn,
    current_user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    inquiry = _to_decide(inquiry_id, db)
    spr.approve(
        db, inquiry, str(current_user["id"]), note=payload.note,
        seen_submitted_at=payload.submitted_at,
    )
    db.commit()
    return _out(db, inquiry, current_user)


@router.post("/spare-part-requests/{inquiry_id}/reject", response_model=SparePartRequestOut)
def reject_spare_part_request(
    inquiry_id: str,
    payload: SparePartRejectIn,
    current_user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    inquiry = _to_decide(inquiry_id, db)
    spr.reject(
        db, inquiry, str(current_user["id"]), payload.reason,
        seen_submitted_at=payload.submitted_at,
    )
    db.commit()
    return _out(db, inquiry, current_user)


@router.post("/spare-part-requests/{inquiry_id}/revise", response_model=SparePartRequestOut)
def revise_spare_part_request(
    inquiry_id: str,
    current_user: dict = Depends(require_permission(CREATE)),
    db: Session = Depends(get_db),
):
    inquiry = _visible(db, inquiry_id, current_user)
    spr.revise(db, inquiry, str(current_user["id"]))
    db.commit()
    return _out(db, inquiry, current_user)


# ------------------------------------------------------------------ row photos


def assert_can_write_row_photos(db: Session, row_id: str, user_id: str) -> str:
    row_id = validate_uuid_path(row_id, resource="Order inquiry row")
    spr.assert_can_write_row_photos(db, row_id, user_id)
    return row_id


@router.post("/order-inquiry-rows/attachments/lookup")
def lookup_order_inquiry_row_attachments(
    payload: OrderInquiryRowAttachmentLookupRequest,
    current_user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """Every listed row's files, keyed by row id, for the rows whose inquiry this user can
    see - one call for a whole Lines tab."""
    uid = str(current_user["id"])
    ids = [str(i) for i in payload.row_ids if i]
    if not ids:
        return {}
    clause = spr.visibility_clause(db, uid, has_view=_has_view(db, uid))
    visible = [
        str(r[0])
        for r in db.query(OrderInquiryRow.id)
        .join(OrderInquiry, OrderInquiry.id == OrderInquiryRow.order_inquiry_id)
        .filter(OrderInquiryRow.id.in_(ids), clause)
        .all()
    ]
    return so_line_attachments.lookup(db, visible, so_line_attachments.OI_ROW)


@router.post("/order-inquiry-rows/{row_id}/attachments")
async def upload_order_inquiry_row_attachments(
    row_id: str,
    files: List[UploadFile] = File(..., description="One or more files"),
    current_user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    row_id = assert_can_write_row_photos(db, row_id, str(current_user["id"]))
    return await so_line_attachments.upload(
        db,
        line_id=row_id,
        files=files,
        actor_id=current_user.get("id"),
        target=so_line_attachments.OI_ROW,
    )


@router.delete("/order-inquiry-rows/{row_id}/attachments/{link_id}")
def delete_order_inquiry_row_attachment(
    row_id: str,
    link_id: str,
    current_user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """Immediate delete - the FE's x goes through the deferred
    `order_inquiry_row_attachment.delete` record action (D7), which runs the same check."""
    row_id = assert_can_write_row_photos(db, row_id, str(current_user["id"]))
    link_id = validate_uuid_path(link_id, resource="Attachment")
    so_line_attachments.delete(
        db, row_id, link_id, current_user.get("id"), so_line_attachments.OI_ROW
    )
    return {"message": "Attachment deleted"}
