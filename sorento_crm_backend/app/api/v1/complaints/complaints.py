"""Complaints API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import Optional, List
from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key
from app.services.complaints_service import ComplaintService
from app.services.integration_service import IntegrationLogService
from app.schemas.complaints import (
    ComplaintCreate,
    ComplaintUpdate,
    ComplaintResponse,
    ComplaintManualAttachmentCreate,
    ComplaintManualAttachmentResponse,
)
from app.schemas.integration import IntegrationLogCreate
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


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
    current_user: dict = Depends(get_current_user_or_api_key),  # Support both JWT and API key
    db: Session = Depends(get_db)
):
    """Create a new complaint with attachments.
    
    Supports both authenticated users (via JWT Bearer token) and external parties (via X-API-Key header).
    """
    try:
        service = ComplaintService(db)
        complaint = service.create_complaint(complaint_data)
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


@router.post("/manual-attachments", response_model=ComplaintManualAttachmentResponse, status_code=status.HTTP_201_CREATED)
async def create_complaint_manual_attachment(
    attachment_data: ComplaintManualAttachmentCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a manual complaint attachment entry from integration."""
    try:
        service = ComplaintService(db)
        link, attachment = service.create_manual_attachment(attachment_data)

        log_service = IntegrationLogService(db)
        log_service.create_integration_log(
            IntegrationLogCreate(
                integration_channel="complaints_api",
                business_table="complaint_manual_attachments",
                business_id=link.id,
                external_reference=link.complaint_id,
                direction="inbound",
                endpoint=str(request.url),
                http_method="POST",
                status="success"
            ),
            request_payload_dict=attachment_data.model_dump()
        )

        return {
            "id": link.id,
            "complaint_id": link.complaint_id,
            "attachment_id": link.attachment_id,
            "created_at": link.created_at,
            "attachment": attachment,
        }
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get(
    "/{complaint_id}/manual-attachments",
    response_model=List[ComplaintManualAttachmentResponse],
)
async def list_complaint_manual_attachments(
    complaint_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List manual attachments linked to a complaint."""
    try:
        service = ComplaintService(db)
        return service.list_manual_attachments(complaint_id)
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/manual-attachments/{manual_attachment_id}", status_code=status.HTTP_200_OK)
async def delete_complaint_manual_attachment(
    manual_attachment_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Unlink a manual attachment from a complaint."""
    try:
        service = ComplaintService(db)
        service.delete_manual_attachment(manual_attachment_id)
        return {"message": "Attachment unlinked successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{complaint_id}", response_model=ComplaintResponse)
async def update_complaint(
    complaint_id: str,
    complaint_data: ComplaintUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a complaint."""
    try:
        service = ComplaintService(db)
        complaint = service.update_complaint(complaint_id, complaint_data)
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
