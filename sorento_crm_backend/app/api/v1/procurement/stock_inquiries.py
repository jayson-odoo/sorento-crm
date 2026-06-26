"""Stock inquiries API routes."""
import logging

from fastapi import APIRouter, Depends, Query, HTTPException, status, Request, Body, Response
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key, require_permission
from app.services.procurement_service import StockInquiryService
from app.schemas.procurement import (
    StockInquiryCreate,
    StockInquiryUpdate,
    StockInquiryResponse,
    StockInquiryRejectReopenRequest,
    ViewLinkRequest,
    ViewLinkResponse,
)
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error
from app.config import settings as app_settings
from app.modules.runtime.guards import require_public_view_links_enabled

logger = logging.getLogger(__name__)

router = APIRouter()


class BulkDeleteStockInquiriesRequest(BaseModel):
    ids: list[str]


class StockInquiryAttachmentLinkRequest(BaseModel):
    attachment_id: str


def _respond_user_id_from_current_user(current_user: dict) -> str:
    """Get respond_user_id for SLA/response tracking; fallback to user id."""
    rid = (current_user or {}).get("respond_user_id") or (current_user or {}).get("respondUserId")
    if rid and str(rid).strip():
        return str(rid).strip()
    uid = (current_user or {}).get("id")
    if uid and str(uid).strip():
        return str(uid).strip()
    raise HTTPException(status_code=400, detail="User respond_user_id or id is required for Update & Reply.")


@router.get("/", response_model=ListResponse[StockInquiryResponse])
async def get_stock_inquiries(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="Comma-separated status values to filter by"),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("desc"),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get stock inquiries with pagination and search."""
    try:
        service = StockInquiryService(db)
        sort_field = (sort and sort.strip()) or "created_at"
        sort_dir = (dir and dir.strip()) or "desc"
        statuses = [s.strip() for s in status.split(",") if s and s.strip()] if status else None
        result = service.list_inquiries(
            page=page,
            limit=limit,
            query=query,
            sort_field=sort_field,
            sort_dir=sort_dir,
            contact_id=None,
            space_id=None,
            statuses=statuses,
        )
        return result
    except Exception as e:
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_stock_inquiries: {str(e)}")
        logger.error(traceback.format_exc())
        raise handle_internal_error(str(e))


@router.get("/neighbours")
async def get_stock_inquiry_neighbours(
    id: str = Query(..., description="Stock inquiry id to resolve neighbours for"),
    query: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="Comma-separated status values to filter by"),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("desc"),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """Prev/next neighbours of a stock inquiry within the active filtered+sorted list set.

    Accepts the same filter/sort/search params as the list GET (page/limit are
    irrelevant and ignored). Returns ``{total, index, prev_id, next_id}`` with the
    1-based ``index`` and circular wrap-around neighbours. If the record is not in
    the filtered set, falls back to the unfiltered, default-sorted set.
    """
    try:
        service = StockInquiryService(db)
        sort_field = (sort and sort.strip()) or "created_at"
        sort_dir = (dir and dir.strip()) or "desc"
        statuses = [s.strip() for s in status.split(",") if s and s.strip()] if status else None
        return service.neighbours(
            inquiry_id=id,
            query=query,
            sort_field=sort_field,
            sort_dir=sort_dir,
            statuses=statuses,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{inquiry_id}", response_model=StockInquiryResponse)
async def get_stock_inquiry(
    inquiry_id: str,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get a single stock inquiry by ID."""
    try:
        service = StockInquiryService(db)
        return service.get_inquiry_for_response(
            inquiry_id,
            contact_id=None,
            space_id=None,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{inquiry_id}/conversation")
async def get_stock_inquiry_conversation(
    inquiry_id: str,
    limit: int = Query(50, ge=1, le=50),
    cursor: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """Get Respond.io conversation messages for this stock inquiry (contact from respond_inbox_url)."""
    try:
        from app.services.integration_service import RespondClient
        from app.models.access import RespondContact
        service = StockInquiryService(db)
        inquiry = service.get_inquiry(inquiry_id)
        respond_inbox_url = getattr(inquiry, "respond_inbox_url", None)
        identifier = service._identifier_from_respond_inbox_url(
            str(respond_inbox_url) if respond_inbox_url is not None else None
        )
        contact_meta: Optional[dict] = None
        contact_id_val = getattr(inquiry, "contact_id", None)
        if contact_id_val:
            row = (
                db.query(RespondContact)
                .filter(
                    (RespondContact.id == contact_id_val)
                    | (RespondContact.respond_io_id == contact_id_val)
                )
                .first()
            )
            if row is not None:
                contact_meta = {"name": row.name, "phone": row.phone_number}
        if not identifier:
            return {
                "items": [],
                "pagination": {},
                "error": "No Respond.io contact linked",
                "contact": contact_meta,
            }
        client = RespondClient()
        data = client.list_messages(identifier, limit=limit, cursor=cursor)
        if isinstance(data, dict):
            data["contact"] = contact_meta
        return data
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/attachments/{link_id}", status_code=status.HTTP_200_OK)
async def delete_stock_inquiry_attachment(
    link_id: str,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Unlink an attachment from a stock inquiry."""
    try:
        service = StockInquiryService(db)
        service.delete_inquiry_attachment(link_id)
        return {"message": "Attachment unlinked successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{inquiry_id}/attachments", status_code=status.HTTP_201_CREATED)
async def link_attachment_to_stock_inquiry(
    inquiry_id: str,
    body: StockInquiryAttachmentLinkRequest,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Link an existing attachment to a stock inquiry."""
    try:
        service = StockInquiryService(db)
        created_by = (current_user.get("id") or None) if isinstance(current_user.get("id"), str) and len(str(current_user.get("id"))) == 36 else None
        link = service.link_attachment_to_inquiry(
            inquiry_id=inquiry_id,
            attachment_id=body.attachment_id,
            created_by=created_by,
        )
        return {"message": "Attachment linked successfully", "link_id": link.id}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post(
    "/{inquiry_id}/view-link",
    response_model=ViewLinkResponse,
    dependencies=[Depends(require_public_view_links_enabled())],
)
async def get_or_create_stock_inquiry_view_link(
    inquiry_id: str,
    data: Optional[ViewLinkRequest] = Body(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get or create a shareable view link for this stock inquiry (no login required to view)."""
    try:
        service = StockInquiryService(db)
        service.get_inquiry(inquiry_id)  # ensure exists and user can access
        token = service.get_or_create_view_token(inquiry_id)
        db.commit()
        base = ((data.base_url if data else None) or getattr(app_settings, "frontend_base_url", "") or "").rstrip("/")
        view_url = f"{base}/view/stock-inquiry?token={token}" if base else f"/view/stock-inquiry?token={token}"
        return ViewLinkResponse(view_token=token, view_url=view_url)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=StockInquiryResponse, status_code=status.HTTP_201_CREATED)
async def create_stock_inquiry(
    inquiry_data: StockInquiryCreate,
    request: Request,
    response: Response,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Create a new stock inquiry. If ``inquiry_number`` matches a rejected inquiry, that row is updated (200). Notifies project sales team when status is new or pending_project_sales."""
    try:
        service = StockInquiryService(db)
        inquiry, outcome = service.create_inquiry(inquiry_data)
        if outcome == "resubmitted":
            response.status_code = status.HTTP_200_OK
        db.commit()
        if getattr(inquiry, "status", None) in ("new", "pending_project_sales"):
            try:
                if outcome == "resubmitted":
                    service._notify_team_stock_inquiry(
                        inquiry_id=str(inquiry.id),
                        agent_code="lead_time_enquiries",
                        team_assignment_code="project_sales",
                        title="Stock Inquiry updated (resubmitted)",
                        intro_plain="Dear Project Sales Team,\n\nA previously rejected stock inquiry has been updated and resubmitted for your review.",
                        intro_html="Dear Project Sales Team,<br /><br />A previously rejected stock inquiry has been updated and resubmitted for your review.",
                        event_type="resubmitted",
                    )
                else:
                    service._notify_team_stock_inquiry(
                        inquiry_id=str(inquiry.id),
                        agent_code="lead_time_enquiries",
                        team_assignment_code="project_sales",
                        title="New Stock Inquiry created",
                        intro_plain="Dear Project Sales Team,\n\nA new stock inquiry has been created and requires your review.",
                        intro_html="Dear Project Sales Team,<br /><br />A new stock inquiry has been created and requires your review.",
                        event_type="created",
                    )
            except Exception as e:
                logger.warning(
                    "Stock inquiry project_sales notify failed for inquiry %s: %s",
                    getattr(inquiry, "id", None),
                    e,
                    exc_info=True,
                )
        return inquiry
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{inquiry_id}", response_model=StockInquiryResponse)
async def update_stock_inquiry(
    inquiry_id: str,
    inquiry_data: StockInquiryUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Update a stock inquiry."""
    try:
        service = StockInquiryService(db)
        inquiry = service.update_inquiry(inquiry_id, inquiry_data)
        db.commit()
        return inquiry
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{inquiry_id}/update-and-reply", response_model=StockInquiryResponse)
async def update_stock_inquiry_and_reply(
    inquiry_id: str,
    inquiry_data: StockInquiryUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Update inquiry and send message via Respond.io from Chat Records. SLA/status move to responded only when status is pending_purchasing or responded; other statuses only send and record last_responded."""
    try:
        respond_user_id = _respond_user_id_from_current_user(current_user)
        service = StockInquiryService(db)
        inquiry = service.update_inquiry_and_reply(
            inquiry_id,
            inquiry_data,
            respond_user_id=respond_user_id,
            request_url=str(request.url) if request else "",
            crm_sender_user_id=current_user.get("id"),
        )
        db.commit()
        return inquiry
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{inquiry_id}/submit-for-project-sales", response_model=StockInquiryResponse)
async def submit_stock_inquiry_for_project_sales(
    inquiry_id: str,
    current_user: dict = Depends(require_permission("procurement.stock_inquiries.submit_for_project_sales")),
    db: Session = Depends(get_db),
):
    """Move stock inquiry from new to pending_project_sales."""
    try:
        service = StockInquiryService(db)
        inquiry = service.submit_inquiry_for_project_sales(inquiry_id)
        return inquiry
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{inquiry_id}/project-sales-approve", response_model=StockInquiryResponse)
async def project_sales_approve_stock_inquiry(
    inquiry_id: str,
    current_user: dict = Depends(require_permission("procurement.stock_inquiries.project_sales_approve")),
    db: Session = Depends(get_db),
):
    """Move stock inquiry from pending_project_sales to pending_purchasing."""
    try:
        service = StockInquiryService(db)
        user_id = (current_user or {}).get("id")
        respond_user_id = (
            (current_user or {}).get("respond_user_id")
            or (current_user or {}).get("respondUserId")
            or user_id
        )
        inquiry = service.project_sales_approve_inquiry(
            inquiry_id,
            actor_user_id=user_id,
            crm_sender_user_id=user_id,
            respond_user_id_fallback=str(respond_user_id or ""),
        )
        return inquiry
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{inquiry_id}/project-sales-reject", response_model=StockInquiryResponse)
async def project_sales_reject_stock_inquiry(
    inquiry_id: str,
    body: Optional[StockInquiryRejectReopenRequest] = Body(None),
    current_user: dict = Depends(require_permission("procurement.stock_inquiries.project_sales_reject")),
    db: Session = Depends(get_db),
):
    """Move stock inquiry from pending_project_sales to rejected."""
    try:
        service = StockInquiryService(db)
        reason = body.reason if body else None
        user_id = (current_user or {}).get("id")
        respond_user_id = (
            (current_user or {}).get("respond_user_id")
            or (current_user or {}).get("respondUserId")
            or user_id
        )
        service.project_sales_reject_inquiry(
            inquiry_id,
            reason=reason,
            user_id=user_id,
            crm_sender_user_id=user_id,
            respond_user_id_fallback=str(respond_user_id or ""),
        )
        return service.get_inquiry_for_response(inquiry_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{inquiry_id}/purchasing-reject", response_model=StockInquiryResponse)
async def purchasing_reject_stock_inquiry(
    inquiry_id: str,
    body: Optional[StockInquiryRejectReopenRequest] = Body(None),
    current_user: dict = Depends(require_permission("procurement.stock_inquiries.purchasing_reject")),
    db: Session = Depends(get_db),
):
    """Move stock inquiry from pending_purchasing to rejected."""
    try:
        service = StockInquiryService(db)
        reason = body.reason if body else None
        user_id = (current_user or {}).get("id")
        respond_user_id = (
            (current_user or {}).get("respond_user_id")
            or (current_user or {}).get("respondUserId")
            or user_id
        )
        service.purchasing_reject_inquiry(
            inquiry_id,
            reason=reason,
            user_id=user_id,
            crm_sender_user_id=user_id,
            respond_user_id_fallback=str(respond_user_id or ""),
        )
        return service.get_inquiry_for_response(inquiry_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{inquiry_id}/reopen", response_model=StockInquiryResponse)
async def reopen_stock_inquiry(
    inquiry_id: str,
    body: Optional[StockInquiryRejectReopenRequest] = Body(None),
    current_user: dict = Depends(require_permission("procurement.stock_inquiries.reopen")),
    db: Session = Depends(get_db),
):
    """Move stock inquiry from rejected to pending_project_sales."""
    try:
        service = StockInquiryService(db)
        reason = body.reason if body else None
        user_id = (current_user or {}).get("id")
        service.reopen_inquiry(inquiry_id, reason=reason, user_id=user_id)
        return service.get_inquiry_for_response(inquiry_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/bulk", status_code=status.HTTP_200_OK)
async def bulk_delete_stock_inquiries(
    body: BulkDeleteStockInquiriesRequest = Body(...),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Bulk delete stock inquiries by ID."""
    try:
        service = StockInquiryService(db)
        return service.bulk_delete_inquiries(body.ids)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{inquiry_id}", status_code=status.HTTP_200_OK)
async def delete_stock_inquiry(
    inquiry_id: str,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Delete a stock inquiry."""
    try:
        service = StockInquiryService(db)
        return service.delete_inquiry(inquiry_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


def _resolve_stock_inquiry_chat_contact(db: Session, inquiry_id: str):
    """(respond_io identifier, internal respond_contact_id) for a stock inquiry."""
    service = StockInquiryService(db)
    inquiry = service.get_inquiry(inquiry_id)
    respond_inbox_url = getattr(inquiry, "respond_inbox_url", None)
    identifier = service._identifier_from_respond_inbox_url(
        str(respond_inbox_url) if respond_inbox_url is not None else None
    )
    return identifier, getattr(inquiry, "contact_id", None)


from app.api.v1._respond_chat_template_routes import build_chat_template_router

router.include_router(
    build_chat_template_router(
        business_table="stock_inquiries",
        resolver=_resolve_stock_inquiry_chat_contact,
    )
)
