"""One audit row when a PERSON links or unlinks a product's file (PRODUCT-ATTACH-AUDIT).

``product_attachments`` and ``certificate_products`` carry ``__audit_skip__``: the n8n intake,
the certificate reconcile and the company twin copy write 259 to 4,399 link rows a day
(review B3). A staff screen writes a handful, and those are the ones an owner asks about
("who removed the drawing from this product?"). So the staff routes call this explicitly and
the bulk paths stay silent. Plan: ``documentation/plans/products/PLAN-product-attach-audit-28oct.md``.

The row is rooted on the product, so the product's Audit Trail lists it, and its description
is the line the trail prints for a non-UPDATE row: "File unlinked: drawing.pdf (Drawing)".
"""
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.product import Product, ProductAttachment
from app.models.resources import Attachment, AttachmentType
from app.services.audit_service import log_audit

LINK = "LINK"
UNLINK = "UNLINK"


def link_exists(db: Session, product_id: str, attachment_id: str) -> bool:
    """Whether the product already carries this file (a re-POST refreshes, it does not link)."""
    return (
        db.query(ProductAttachment.id)
        .filter(
            ProductAttachment.product_id == str(product_id),
            ProductAttachment.attachment_id == str(attachment_id),
        )
        .first()
        is not None
    )


def log_product_file_link(
    db: Session,
    action: str,
    *,
    product_id: str,
    attachment_id: Optional[str],
    entity_type: str,
    entity_id: str,
    user_id: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    """Write the LINK / UNLINK row. Flushed, not committed: the caller's write commits it, so
    a refused unlink leaves no row claiming it happened."""
    filename = type_name = None
    if attachment_id:
        found = (
            db.query(Attachment.original_filename, AttachmentType.type_name)
            .outerjoin(AttachmentType, AttachmentType.id == Attachment.attachment_type_id)
            .filter(Attachment.id == str(attachment_id))
            .first()
        )
        if found is not None:
            filename, type_name = found
    values: dict[str, Any] = {
        "product_id": str(product_id),
        "attachment_id": str(attachment_id) if attachment_id else None,
        "original_filename": filename,
        "attachment_type": type_name,
        **(extra or {}),
    }
    name = filename or (extra or {}).get("certificate_number") or "a file"
    verb = "linked" if action == LINK else "unlinked"
    description = f"File {verb}: {name}" + (f" ({type_name})" if type_name else "")
    company_id = db.query(Product.company_id).filter(Product.id == str(product_id)).scalar()
    log_audit(
        db,
        entity_type,
        str(entity_id),
        action,
        old_values=values if action == UNLINK else None,
        new_values=values if action == LINK else None,
        user_id=str(user_id) if user_id else None,
        description=description,
        company_id=str(company_id) if company_id else None,
        root_entity_type="product",
        root_entity_id=str(product_id),
    )
