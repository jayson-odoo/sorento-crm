"""External API for complaint-attachment linking (create attachment with type complaint_document and link to complaint)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.external import ComplaintAttachmentLinkRequest, ComplaintAttachmentLinkResponse
from app.models.complaints import Complaint, ComplaintAttachment
from app.models.resources import Attachment, AttachmentType

router = APIRouter()


@router.post("/", response_model=ComplaintAttachmentLinkResponse)
def link_complaint_attachment(
    payload: ComplaintAttachmentLinkRequest,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """
    Create an attachment with type complaint_document (by code) and link it to the complaint.
    Pass complaint_id and file_url (required); file_name and file_size_bytes are optional.
    """
    complaint = db.query(Complaint).filter(Complaint.id == payload.complaint_id).first()
    if not complaint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Complaint not found",
        )

    attachment_type = db.query(AttachmentType).filter(AttachmentType.code == "complaint_document").first()
    if not attachment_type:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Attachment type 'complaint_document' is not configured.",
        )

    file_url = (payload.file_url or "").strip()
    if not file_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="file_url is required",
        )

    file_name = (payload.file_name or file_url.split("/")[-1].split("?")[0] or "document").strip()[:255]
    stored_filename = file_name[:255] if len(file_name) > 255 else file_name
    file_path = file_url[:500] if len(file_url) > 500 else file_url

    attachment = Attachment(
        attachment_type_id=attachment_type.id,
        original_filename=file_name,
        stored_filename=stored_filename,
        file_path=file_path,
        file_size_bytes=payload.file_size_bytes,
    )
    db.add(attachment)
    db.flush()

    # Next sort_order for this complaint
    max_order = (
        db.query(ComplaintAttachment.sort_order)
        .filter(ComplaintAttachment.complaint_id == payload.complaint_id)
        .order_by(ComplaintAttachment.sort_order.desc())
        .limit(1)
        .scalar()
    )
    sort_order = (max_order + 1) if max_order is not None else 0
    is_primary = sort_order == 0

    created_by = current_user.get("id")
    if created_by == "system" or not created_by:
        created_by = None

    link = ComplaintAttachment(
        complaint_id=payload.complaint_id,
        attachment_id=attachment.id,
        is_primary=is_primary,
        sort_order=sort_order,
        created_by=created_by,
    )
    db.add(link)
    db.commit()
    db.refresh(attachment)
    db.refresh(link)

    return ComplaintAttachmentLinkResponse(
        attachment_id=attachment.id,
        complaint_attachment_id=link.id,
        message="Attachment created and linked to complaint.",
    )
