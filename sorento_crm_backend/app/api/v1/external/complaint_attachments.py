"""External API for complaint-attachment linking."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.external.attachments import (
    ComplaintAttachmentLinkRequest,
    ComplaintAttachmentLinkResponse,
)
from app.models.complaints import Complaint
from app.services.entity_attachment_service import EntityAttachmentService

router = APIRouter()


@router.post("/", response_model=ComplaintAttachmentLinkResponse)
def link_complaint_attachment(
    payload: ComplaintAttachmentLinkRequest,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """
    Create an attachment with type complaint_document and link it to the complaint.
    Pass complaint_id and file_url (required); file_name and file_size_bytes are optional.
    """
    complaint = db.query(Complaint).filter(Complaint.id == payload.complaint_id).first()
    if not complaint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Complaint not found",
        )

    created_by = current_user.get("id")
    if created_by == "system" or not created_by:
        created_by = None

    service = EntityAttachmentService(db)
    link = service.create_attachment_and_link(
        entity_type="complaint",
        entity_id=payload.complaint_id,
        file_url=payload.file_url,
        file_name=payload.file_name,
        file_size_bytes=payload.file_size_bytes,
        attachment_type_code="complaint_document",
        created_by=created_by,
    )
    db.commit()
    db.refresh(link)

    return ComplaintAttachmentLinkResponse(
        attachment_id=str(link.attachment_id),
        complaint_attachment_id=str(link.id),
        message="Attachment created and linked to complaint.",
    )
