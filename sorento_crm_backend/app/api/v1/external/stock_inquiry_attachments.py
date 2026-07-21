"""External API for stock inquiry-attachment linking."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.external.attachments import (
    StockInquiryAttachmentLinkRequest,
    StockInquiryAttachmentLinkResponse,
)
from app.models.procurement import StockInquiry
from app.services.entity_attachment_service import EntityAttachmentService

router = APIRouter()


@router.post("/", response_model=StockInquiryAttachmentLinkResponse)
def link_stock_inquiry_attachment(
    payload: StockInquiryAttachmentLinkRequest,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """
    Create an attachment and link it to the stock inquiry.
    Pass inquiry_id and file_url (required); file_name and file_size_bytes are optional.
    """
    inquiry = db.query(StockInquiry).filter(StockInquiry.id == payload.inquiry_id).first()
    if not inquiry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stock inquiry not found",
        )

    # The integration's principal is a real users row, so attribution is recorded.
    created_by = current_user.get("id")

    service = EntityAttachmentService(db)
    link = service.create_attachment_and_link(
        entity_type="stock_inquiry",
        entity_id=payload.inquiry_id,
        file_url=payload.file_url,
        file_name=payload.file_name,
        file_size_bytes=payload.file_size_bytes,
        attachment_type_code="complaint_document",
        created_by=created_by,
    )
    db.commit()
    db.refresh(link)

    return StockInquiryAttachmentLinkResponse(
        attachment_id=str(link.attachment_id),
        stock_inquiry_attachment_id=str(link.id),
        message="Attachment created and linked to stock inquiry.",
    )

