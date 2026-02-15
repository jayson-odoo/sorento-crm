"""Complaints API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key
from app.services.complaints_service import ComplaintService
from app.services.integration_service import IntegrationLogService
from app.schemas.complaints import (
    ComplaintCreate,
    ComplaintUpdate,
    ComplaintResponse,
    ComplaintAttachmentLinkRequest,
)
from app.schemas.integration import IntegrationLogCreate
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


def _respond_user_id_from_current_user(current_user: dict) -> str:
    """Get respond_user_id for SLA/response tracking; fallback to user id."""
    rid = (current_user or {}).get("respond_user_id") or (current_user or {}).get("respondUserId")
    if rid and str(rid).strip():
        return str(rid).strip()
    uid = (current_user or {}).get("id")
    if uid and str(uid).strip():
        return str(uid).strip()
    raise HTTPException(status_code=400, detail="User respond_user_id or id is required for Update & Reply.")


@router.get("/", response_model=ListResponse[ComplaintResponse])
async def get_complaints(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query("complaint_date"),
    dir: Optional[str] = Query("asc"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get complaints with pagination, search, and sorting."""
    try:
        service = ComplaintService(db)
        result = service.list_complaints(
            page=page,
            limit=limit,
            query=query,
            sort_field=sort or "complaint_date",
            sort_dir=dir or "asc"
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/attachments/{link_id}", status_code=status.HTTP_200_OK)
async def delete_complaint_attachment(
    link_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Unlink an attachment from a complaint (complaint_attachments link)."""
    try:
        service = ComplaintService(db)
        service.delete_complaint_attachment(link_id)
        return {"message": "Attachment unlinked successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{complaint_id}/attachments", status_code=status.HTTP_201_CREATED)
async def link_attachment_to_complaint(
    complaint_id: str,
    body: ComplaintAttachmentLinkRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Link an existing attachment to a complaint (complaint_attachments table)."""
    try:
        service = ComplaintService(db)
        created_by = (current_user.get("id") or None) if isinstance(current_user.get("id"), str) and len(str(current_user.get("id"))) == 36 else None
        link = service.link_attachment_to_complaint(
            complaint_id=complaint_id,
            attachment_id=body.attachment_id,
            created_by=created_by,
        )
        return {"message": "Attachment linked successfully", "link_id": link.id}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{complaint_id}", response_model=ComplaintResponse)
async def get_complaint(
    complaint_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single complaint by ID."""
    try:
        service = ComplaintService(db)
        complaint = service.get_complaint_with_attachments(complaint_id)
        return complaint
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=ComplaintResponse, status_code=status.HTTP_201_CREATED)
async def create_complaint(
    complaint_data: ComplaintCreate,
    request: Request,
    current_user: dict = Depends(get_current_user_or_api_key),  # Support both JWT and API key
    db: Session = Depends(get_db)
):
    """Create a new complaint with attachments.
    
    Supports both authenticated users (via JWT Bearer token) and external parties (via X-API-Key header).
    """
    try:
        service = ComplaintService(db)
        complaint = service.create_complaint(complaint_data)
        db.commit()
        return complaint
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/integration", status_code=status.HTTP_200_OK)
async def create_complaint_integration(
    complaint_data: ComplaintCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a complaint from integration and log the request."""
    try:
        service = ComplaintService(db)
        complaint = service.create_complaint(complaint_data)

        log_service = IntegrationLogService(db)
        log_service.create_integration_log(
            IntegrationLogCreate(
                integration_channel="complaints_api",
                business_table="complaints",
                business_id=complaint.id,
                external_reference=complaint.delivery_order_number,
                direction="inbound",
                endpoint=str(request.url),
                http_method="POST",
                status="success"
            ),
            request_payload_dict=complaint_data.model_dump()
        )

        return {"status": "success", "message": "Complaint created successfully.", "complaint_id": complaint.id}
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{complaint_id}", response_model=ComplaintResponse)
async def update_complaint(
    complaint_id: str,
    complaint_data: ComplaintUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a complaint."""
    try:
        service = ComplaintService(db)
        complaint = service.update_complaint(complaint_id, complaint_data)
        db.commit()
        return complaint
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{complaint_id}/update-and-reply", response_model=ComplaintResponse)
async def update_complaint_and_reply(
    complaint_id: str,
    complaint_data: ComplaintUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update complaint, send technical team response to customer via Respond.io, and mark SLA as responded."""
    try:
        respond_user_id = _respond_user_id_from_current_user(current_user)
        service = ComplaintService(db)
        complaint = service.update_complaint_and_reply(
            complaint_id,
            complaint_data,
            respond_user_id=respond_user_id,
            request_url=str(request.url) if request else "",
        )
        db.commit()
        return complaint
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{complaint_id}", status_code=status.HTTP_200_OK)
async def delete_complaint(
    complaint_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a complaint."""
    try:
        service = ComplaintService(db)
        service.delete_complaint(complaint_id)
        return {"message": "Complaint deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
