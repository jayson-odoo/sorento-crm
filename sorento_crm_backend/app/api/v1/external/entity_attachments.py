"""External API for generic entity-attachment linking."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.external.attachments import (
    EntityAttachmentLinkRequest,
    EntityAttachmentLinkResponse,
)
from app.services.entity_attachment_service import EntityAttachmentService
from app.services.attachment_field_link_service import AttachmentFieldLinkService
from app.models.complaints import Complaint
from app.models.procurement import StockInquiry, PurchaseRequestHeader
from app.models.resources import Attachment

router = APIRouter()

DEFAULT_ATTACHMENT_TYPE_BY_ENTITY = {
    "complaint": "complaint_document",
    "stock_inquiry": "complaint_document",
    "purchase_request": "complaint_document",
}


def _assert_entity_exists(db: Session, entity_type: str, entity_id: str) -> None:
    """Check entity exists. Use entity_type 'purchase_request' for both purchase requests and sponsorship forms (same table)."""
    if entity_type == "complaint":
        exists = db.query(Complaint.id).filter(Complaint.id == entity_id).first()
    elif entity_type == "stock_inquiry":
        exists = db.query(StockInquiry.id).filter(StockInquiry.id == entity_id).first()
    elif entity_type == "purchase_request":
        exists = db.query(PurchaseRequestHeader.id).filter(PurchaseRequestHeader.id == entity_id).first()
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported entity_type '{entity_type}'.",
        )
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{entity_type} not found",
        )


@router.post("/", response_model=EntityAttachmentLinkResponse)
def link_entity_attachment(
    payload: EntityAttachmentLinkRequest,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """
    Create an attachment and link it to any supported entity.
    Supported entity_type: complaint, stock_inquiry, purchase_request.
    Use entity_type 'purchase_request' for both purchase requests and sponsorship forms (same table).
    """
    entity_type = (payload.entity_type or "").strip()
    entity_id = (payload.entity_id or "").strip()
    _assert_entity_exists(db, entity_type, entity_id)

    # The integration's principal is a real users row, so attribution is recorded.
    created_by = current_user.get("id")

    service = EntityAttachmentService(db)
    attachment_type_code = (
        (payload.attachment_type_code or "").strip()
        or DEFAULT_ATTACHMENT_TYPE_BY_ENTITY.get(entity_type, "complaint_document")
    )
    link = service.create_attachment_and_link(
        entity_type=entity_type,
        entity_id=entity_id,
        file_url=payload.file_url,
        file_name=payload.file_name,
        file_size_bytes=payload.file_size_bytes,
        attachment_type_code=attachment_type_code,
        created_by=created_by,
    )
    db.commit()
    db.refresh(link)

    # Fan attachment template (or explicit field_keys override) into per-row
    # attachment_field_links. Tolerated as best-effort — never fail the link.
    try:
        attachment_row = (
            db.query(Attachment).filter(Attachment.id == link.attachment_id).first()
        )
        AttachmentFieldLinkService(db).apply_template_to_row(
            attachment_row or str(link.attachment_id),
            entity_type,
            entity_id,
            override_keys=getattr(payload, "field_keys", None),
            created_by=created_by,
        )
        db.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "Field-link fan-out failed for attachment=%s entity=%s/%s: %s",
            link.attachment_id,
            entity_type,
            entity_id,
            e,
            exc_info=True,
        )
    return EntityAttachmentLinkResponse(
        attachment_id=str(link.attachment_id),
        link_id=str(link.id),
        entity_type=str(link.entity_type),
        entity_id=str(link.entity_id),
        message="Attachment created and linked successfully.",
    )

