"""Purchase requests / sponsorship forms API routes."""
import html
from fastapi import APIRouter, Depends, Query, HTTPException, status, Request, Body
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key, require_permission
from app.services.procurement_service import PurchaseRequestService
from app.schemas.procurement import (
    PurchaseRequestHeaderCreate,
    PurchaseRequestHeaderUpdate,
    PurchaseRequestUpdateAndReply,
    PurchaseRequestHeaderResponse,
    PurchaseRequestHeaderListResponse,
    PurchaseRequestAttachmentLinkRequest,
    SendApprovalLinkRequest,
    SendApprovalLinkResponse,
    RejectSubmittedRequest,
    ViewLinkRequest,
    ViewLinkResponse,
    BulkDeletePurchaseRequestsRequest,
)
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error
from app.config import settings
from app.modules.runtime.guards import require_public_view_links_enabled

router = APIRouter()


def _is_external_api_key_request(request: Optional[Request]) -> bool:
    key = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
    valid = getattr(settings, "external_api_key", None)
    if not key or not valid:
        return False
    return key.strip() == str(valid).strip()


def _require_contact_scope_for_external(
    *,
    request: Request,
    contact_id: Optional[str],
    space_id: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    c = (contact_id or "").strip() or None
    s = (space_id or "").strip() or None
    if _is_external_api_key_request(request) and (not c or not s):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="contact_id and space_id are required for external purchase request list/get requests.",
        )
    return c, s


def _respond_user_id_from_current_user(current_user: dict) -> str:
    """Get respond_user_id for update-and-reply; fallback to user id."""
    rid = (current_user or {}).get("respond_user_id") or (current_user or {}).get("respondUserId")
    if rid and str(rid).strip():
        return str(rid).strip()
    uid = (current_user or {}).get("id")
    if uid and str(uid).strip():
        return str(uid).strip()
    raise HTTPException(status_code=400, detail="User respond_user_id or id is required for Update & Reply.")


@router.get("/", response_model=ListResponse[PurchaseRequestHeaderListResponse])
async def get_purchase_requests(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    contact_id: Optional[str] = Query(None),
    space_id: Optional[str] = Query(None),
    request_type: Optional[str] = Query(None, description="purchase_request or sponsorship_form"),
    approval_status: Optional[str] = Query(None, description="draft, pending, approved, rejected"),
    sort: Optional[str] = Query("request_date"),
    dir: Optional[str] = Query("desc"),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """List purchase requests and sponsorship forms with pagination."""
    try:
        service = PurchaseRequestService(db)
        filter_contact_id, filter_space_id = _require_contact_scope_for_external(
            request=request,
            contact_id=contact_id,
            space_id=space_id,
        )
        result = service.list_requests(
            page=page,
            limit=limit,
            query=query,
            contact_id=filter_contact_id,
            space_id=filter_space_id,
            request_type=request_type,
            approval_status=approval_status,
            sort_field=sort or "request_date",
            sort_dir=dir or "desc",
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{request_id}", response_model=PurchaseRequestHeaderResponse)
async def get_purchase_request(
    request_id: str,
    request: Request,
    contact_id: Optional[str] = Query(None),
    space_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """Get a purchase request or sponsorship form by ID with lines and attachments."""
    try:
        from app.models.user import User

        service = PurchaseRequestService(db)
        filter_contact_id, filter_space_id = _require_contact_scope_for_external(
            request=request,
            contact_id=contact_id,
            space_id=space_id,
        )
        header = service.get_request(
            request_id,
            contact_id=filter_contact_id,
            space_id=filter_space_id,
        )
        if getattr(header, "approver_user_id", None):
            user = db.query(User).filter(User.id == header.approver_user_id).first()
            if user:
                setattr(
                    header,
                    "approver_display_name",
                    (user.name and user.name.strip()) or user.email or "",
                )
        links = service.entity_attachment_service.list_links("purchase_request", request_id)
        setattr(
            header,
            "attachments",
            [
                service.entity_attachment_service.serialize_link(
                    link,
                    entity_key="purchase_request_id",
                    link_type="purchase_request_attachment",
                )
                for link in links
            ],
        )
        if getattr(header, "request_type", None) == "sponsorship_form" and header.lines:
            from decimal import Decimal
            grand = Decimal("0")
            for line in header.lines:
                line_total = getattr(line, "total", None)
                if line_total is not None:
                    grand += line_total
                else:
                    qty = getattr(line, "quantity", None)
                    up = getattr(line, "unit_price", None)
                    if qty is not None and up is not None:
                        grand += Decimal(str(qty)) * Decimal(str(up))
            setattr(header, "grand_total", grand)
        return header
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{request_id}/conversation")
async def get_purchase_request_conversation(
    request_id: str,
    limit: int = Query(50, ge=1, le=50),
    cursor: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """Get Respond.io conversation messages for this purchase request or sponsorship form."""
    try:
        from app.services.integration_service import RespondClient
        from app.models.access import RespondContact
        service = PurchaseRequestService(db)
        header = service.get_request(request_id)
        identifier = service._identifier_from_respond_inbox_url(getattr(header, "respond_inbox_url", None))
        contact_meta: Optional[dict] = None
        contact_id_val = getattr(header, "contact_id", None)
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


@router.post("/", response_model=PurchaseRequestHeaderResponse, status_code=status.HTTP_201_CREATED)
async def create_purchase_request(
    data: PurchaseRequestHeaderCreate,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a purchase request or sponsorship form."""
    try:
        service = PurchaseRequestService(db)
        header = service.create_request(data)
        db.commit()
        return header
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{request_id}", response_model=PurchaseRequestHeaderResponse)
async def update_purchase_request(
    request_id: str,
    data: PurchaseRequestHeaderUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a purchase request or sponsorship form."""
    try:
        service = PurchaseRequestService(db)
        header = service.update_request(request_id, data)
        db.commit()
        return header
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{request_id}/update-and-reply", response_model=PurchaseRequestHeaderResponse)
async def update_purchase_request_and_reply(
    request_id: str,
    data: PurchaseRequestUpdateAndReply,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update purchase request (e.g. form number) and send a reply to the conversation via Respond.io.
    Either send reply_message or set request_number to auto-send 'Your request has been assigned form number: X'."""
    try:
        respond_user_id = _respond_user_id_from_current_user(current_user)
        service = PurchaseRequestService(db)
        header = service.update_request_and_reply(
            request_id,
            data,
            respond_user_id=respond_user_id,
            request_url=str(request.url) if request else "",
            crm_sender_user_id=current_user.get("id"),
        )
        db.commit()
        if getattr(header, "approver_user_id", None):
            from app.models.user import User
            user = db.query(User).filter(User.id == header.approver_user_id).first()
            if user:
                setattr(
                    header,
                    "approver_display_name",
                    (user.name and user.name.strip()) or user.email or "",
                )
        return header
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{request_id}/set-pending-approval", response_model=PurchaseRequestHeaderResponse)
async def set_pending_approval(
    request_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Set request to pending approval (e.g. from draft or to resend after approved). Clears previous approval data."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        service = PurchaseRequestService(db)
        header = service.set_pending_approval(request_id, requested_by_user_id=current_user.get("id"))
        if getattr(header, "approver_user_id", None):
            from app.models.user import User
            user = db.query(User).filter(User.id == header.approver_user_id).first()
            if user:
                setattr(
                    header,
                    "approver_display_name",
                    (user.name and user.name.strip()) or user.email or "",
                )
        return header
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in set_pending_approval for {request_id}: {type(e).__name__}: {str(e)}", exc_info=True)
        raise handle_internal_error(str(e))


@router.post("/{request_id}/reject-submitted", response_model=PurchaseRequestHeaderResponse)
async def reject_submitted_purchase_request(
    request_id: str,
    body: RejectSubmittedRequest,
    current_user: dict = Depends(require_permission("procurement.purchase_requests.send_for_approval")),
    db: Session = Depends(get_db),
):
    """Reject a submitted PR / sponsorship form before sending for approval. Sends a Respond.io update message to the contact with the rejection reason. Same permission as Send for Approval."""
    try:
        service = PurchaseRequestService(db)
        header = service.reject_submitted(
            request_id,
            rejection_reason=body.rejection_reason,
            actor_user_id=current_user.get("id"),
        )
        if getattr(header, "approver_user_id", None):
            from app.models.user import User
            user = db.query(User).filter(User.id == header.approver_user_id).first()
            if user:
                setattr(
                    header,
                    "approver_display_name",
                    (user.name and user.name.strip()) or user.email or "",
                )
        return header
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/bulk", status_code=status.HTTP_200_OK)
async def bulk_delete_purchase_requests(
    body: BulkDeletePurchaseRequestsRequest = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Bulk delete purchase requests and/or sponsorship forms by ID."""
    try:
        service = PurchaseRequestService(db)
        return service.bulk_delete_requests(body.ids)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{request_id}", status_code=status.HTTP_200_OK)
async def delete_purchase_request(
    request_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a purchase request or sponsorship form."""
    try:
        service = PurchaseRequestService(db)
        service.delete_request(request_id)
        return {"message": "Purchase request deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{request_id}/send-approval-link", response_model=SendApprovalLinkResponse)
async def send_approval_link(
    request_id: str,
    data: SendApprovalLinkRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create one-time approval token and return public approval URL; optionally send link by email to approver."""
    if not data.approver_email and not data.approver_user_id:
        raise HTTPException(status_code=400, detail="Provide approver_email or approver_user_id.")
    try:
        service = PurchaseRequestService(db)
        base_url = (data.base_url or getattr(settings, "frontend_base_url", None) or "").strip().rstrip("/")
        expires_hours = data.expires_hours or 24
        approval_token, approval_url = service.create_approval_token(
            request_id,
            approver_email=data.approver_email,
            approver_user_id=data.approver_user_id,
            requested_by_user_id=current_user.get("id"),
            expires_hours=expires_hours,
            base_url=base_url,
        )
        email_sent = None
        email_error = None
        if data.send_email:
            header_for_email = service.get_request(request_id)
            to_email = (data.approver_email or "").strip() or (
                getattr(header_for_email, "approver_email", None) or ""
            ).strip()
            if not to_email:
                email_sent = False
                email_error = "No approver email available to send to."
            else:
                from app.models.user import SystemSetting
                from app.services.notification_email import send_notification_email, _smtp_config_from_settings
                sys_settings = db.query(SystemSetting).first()
                smtp_config = _smtp_config_from_settings(sys_settings) if sys_settings else None
                header = service.get_request(request_id)
                type_label = "Purchase Request" if getattr(header, "request_type", None) == "purchase_request" else "Sponsorship Form"
                subject = f"{type_label} – Approval link"
                full_url = approval_url if approval_url.startswith("http") else f"{base_url.rstrip('/')}{approval_url if approval_url.startswith('/') else '/' + approval_url}"
                body_text = (
                    f"You have been sent a one-time approval link for a {type_label.lower()}.\n\n"
                    f"Form number: {getattr(header, 'request_number', None) or 'N/A'}\n"
                    f"Project: {getattr(header, 'project_title', None) or 'N/A'}\n\n"
                    f"Open this link to approve or reject (link expires after use or after the expiry time):\n{full_url}\n"
                )
                form_num = html.escape(str(getattr(header, "request_number", None) or "N/A"))
                project = html.escape(str(getattr(header, "project_title", None) or "N/A"))
                url_escaped = html.escape(full_url, quote=True)
                body_html = (
                    f"<p>You have been sent a one-time approval link for a {html.escape(type_label.lower())}.</p>"
                    f"<p><strong>Form number:</strong> {form_num}<br>"
                    f"<strong>Project:</strong> {project}</p>"
                    f"<p>Open the link below to approve or reject (link expires after use or after the expiry time):</p>"
                    f'<p><a href="{url_escaped}" style="color: #2563eb; text-decoration: underline;">{url_escaped}</a></p>'
                    f"<p>Or copy and paste into your browser if the link does not work.</p>"
                )
                err = send_notification_email(
                    to=to_email,
                    subject=subject,
                    body_text=body_text,
                    body_html=body_html,
                    smtp_config=smtp_config,
                )
                email_sent = err is None
                email_error = err
        expires_at = getattr(approval_token, "expires")
        return SendApprovalLinkResponse(
            approval_url=approval_url,
            expires_at=expires_at,
            token_id=str(approval_token.id),
            email_sent=email_sent,
            email_error=email_error,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/attachments/{link_id}", status_code=status.HTTP_200_OK)
async def delete_purchase_request_attachment(
    link_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Unlink an attachment from a purchase request or sponsorship form."""
    try:
        service = PurchaseRequestService(db)
        service.delete_request_attachment(link_id)
        return {"message": "Attachment unlinked successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{request_id}/attachments", status_code=status.HTTP_201_CREATED)
async def link_attachment_to_purchase_request(
    request_id: str,
    body: PurchaseRequestAttachmentLinkRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Link an existing attachment to a purchase request or sponsorship form."""
    try:
        service = PurchaseRequestService(db)
        created_by = (current_user.get("id") or None) if isinstance(current_user.get("id"), str) and len(str(current_user.get("id"))) == 36 else None
        link = service.link_attachment_to_request(
            request_id=request_id,
            attachment_id=body.attachment_id,
            created_by=created_by,
        )
        return {
            "id": str(link.id),
            "purchase_request_id": str(link.entity_id),
            "attachment_id": str(link.attachment_id),
            "message": "Attachment linked successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post(
    "/{request_id}/view-link",
    response_model=ViewLinkResponse,
    dependencies=[Depends(require_public_view_links_enabled())],
)
async def get_or_create_view_link(
    request_id: str,
    data: Optional[ViewLinkRequest] = Body(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get or create a shareable view link (no login required). Use in Update & Reply to send to Respond."""
    try:
        service = PurchaseRequestService(db)
        service.get_request(request_id)  # ensure exists and user can access
        token = service.get_or_create_view_token(request_id)
        db.commit()
        base = ((data.base_url if data else None) or getattr(settings, "frontend_base_url", "") or "").rstrip("/")
        view_url = f"{base}/view/request?token={token}" if base else f"/view/request?token={token}"
        return ViewLinkResponse(view_token=token, view_url=view_url)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
