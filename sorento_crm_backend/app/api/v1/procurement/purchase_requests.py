"""Purchase requests / sponsorship forms API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.dependencies import get_current_user
from app.services.procurement_service import PurchaseRequestService
from app.schemas.procurement import (
    PurchaseRequestHeaderCreate,
    PurchaseRequestHeaderUpdate,
    PurchaseRequestHeaderResponse,
    PurchaseRequestHeaderListResponse,
    SendApprovalLinkRequest,
    SendApprovalLinkResponse,
)
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error
from app.config import settings

router = APIRouter()


@router.get("/", response_model=ListResponse[PurchaseRequestHeaderListResponse])
async def get_purchase_requests(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    request_type: Optional[str] = Query(None, description="purchase_request or sponsorship_form"),
    sort: Optional[str] = Query("request_date"),
    dir: Optional[str] = Query("desc"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List purchase requests and sponsorship forms with pagination."""
    try:
        service = PurchaseRequestService(db)
        result = service.list_requests(
            page=page,
            limit=limit,
            query=query,
            request_type=request_type,
            sort_field=sort or "request_date",
            sort_dir=dir or "desc",
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/neighbours")
async def get_purchase_request_neighbours(
    request_id: Optional[str] = Query(None, alias="id", description="Purchase request ID"),
    request_type: Optional[str] = Query(None, description="purchase_request or sponsorship_form"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return prev_id and next_id for navigation (order: request_date desc)."""
    if not request_id:
        return {"prev_id": None, "next_id": None}
    try:
        service = PurchaseRequestService(db)
        return service.get_neighbour_ids(request_id, request_type=request_type)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{request_id}", response_model=PurchaseRequestHeaderResponse)
async def get_purchase_request(
    request_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a purchase request or sponsorship form by ID with lines."""
    try:
        from app.models.user import User

        service = PurchaseRequestService(db)
        header = service.get_request(request_id)
        if getattr(header, "approver_user_id", None):
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
        header = service.set_pending_approval(request_id)
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
    """Create one-time approval token and return public approval URL (frontend may send email with it)."""
    if not data.approver_email and not data.approver_user_id:
        raise HTTPException(status_code=400, detail="Provide approver_email or approver_user_id.")
    try:
        service = PurchaseRequestService(db)
        base_url = getattr(settings, "frontend_base_url", "") or ""
        expires_hours = data.expires_hours or 24
        approval_token, approval_url = service.create_approval_token(
            request_id,
            approver_email=data.approver_email,
            approver_user_id=data.approver_user_id,
            expires_hours=expires_hours,
            base_url=base_url,
        )
        return SendApprovalLinkResponse(
            approval_url=approval_url,
            expires_at=approval_token.expires,
            token_id=str(approval_token.id),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
