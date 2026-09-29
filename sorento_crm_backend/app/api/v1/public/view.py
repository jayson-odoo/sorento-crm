"""Public view endpoints (no auth): token-based read-only views and optional revise actions."""
import logging

from fastapi import APIRouter, Depends, Query, HTTPException, Body, Response
from pydantic import BaseModel

from app.database import get_db
from app.services.complaints_service import ComplaintService
from app.services.procurement_service import PurchaseRequestService, StockInquiryService
from app.services.error_handler import handle_internal_error, handle_not_found
from app.modules.runtime.guards import ensure_public_view_links_allowed
from app.services.portal_service import PortalService
from app.services.entity_attachment_service import EntityAttachmentService
from app.models.complaints import Complaint
from app.models.procurement import StockInquiry, PurchaseRequestHeader, ViewToken
from app.models.resources import Attachment
from app.utils.http import content_disposition

logger = logging.getLogger(__name__)

router = APIRouter()

# entity path segment -> ViewToken.entity_type / EntityAttachmentLink.entity_type.
# Only the two pages that preview attachments inline are wired here; `request`
# has no attachment preview today (see POIntakeDocumentViewer/AttachmentPreviewModal
# review, PR #1256) and its token lookup also falls back to approval tokens, which
# this narrow byte route does not need to replicate.
_ATTACHMENT_ENTITY_TYPES = {
    "complaint": "complaint",
    "stock-inquiry": "stock_inquiry",
}


class ViewRevisePayload(BaseModel):
    token: str


def _get_summary_by_entity(db, entity: str, token: str):
    if entity == "request":
        return PurchaseRequestService(db).get_view_summary_by_token(token)
    if entity == "stock-inquiry":
        return StockInquiryService(db).get_inquiry_summary_by_token(token)
    if entity == "complaint":
        return ComplaintService(db).get_complaint_summary_by_token(token)
    raise HTTPException(status_code=404, detail="Unsupported public view entity.")


def _request_revision_by_entity(db, entity: str, token: str):
    if entity == "request":
        return PurchaseRequestService(db).request_revision_by_token(token)
    if entity == "stock-inquiry":
        return StockInquiryService(db).request_inquiry_revision_by_token(token)
    raise HTTPException(status_code=404, detail="Revision endpoint not available for this entity.")


def _portal_url_for_view(db, entity: str, summary: dict) -> str | None:
    entity_id = summary.get("entity_id") if isinstance(summary, dict) else None
    if not entity_id:
        return None
    if entity == "complaint":
        row = db.query(Complaint.contact_id, Complaint.space_id).filter(Complaint.id == entity_id).first()
    elif entity == "stock-inquiry":
        row = db.query(StockInquiry.contact_id, StockInquiry.space_id).filter(StockInquiry.id == entity_id).first()
    elif entity == "request":
        row = (
            db.query(PurchaseRequestHeader.contact_id, PurchaseRequestHeader.space_id)
            .filter(PurchaseRequestHeader.id == entity_id)
            .first()
        )
    else:
        return None
    if not row:
        return None
    contact_id, space_id = row
    if not contact_id or not space_id:
        return None
    try:
        token = PortalService(db).mint_token(contact_id, space_id)
        return PortalService(db).build_portal_url(token.token)
    except Exception:  # noqa: BLE001
        return None


@router.get("/{entity}")
async def get_public_view(
    entity: str,
    token: str = Query(..., description="View token (shareable link)"),
    db=Depends(get_db),
):
    """Return read-only entity summary for the given view token. No auth required."""
    try:
        ensure_public_view_links_allowed(db, current_user_id=None)
        summary = _get_summary_by_entity(db, entity, token)
        if isinstance(summary, dict):
            summary["portal_url"] = _portal_url_for_view(db, entity, summary)
        return summary
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{entity}/revise")
async def request_public_view_revision(
    entity: str,
    payload: ViewRevisePayload = Body(...),
    db=Depends(get_db),
):
    """Trigger revise webhook for supported public views."""
    try:
        ensure_public_view_links_allowed(db, current_user_id=None)
        return _request_revision_by_entity(db, entity, payload.token)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{entity}/attachments/{attachment_id}/download")
async def get_public_view_attachment(
    entity: str,
    attachment_id: str,
    token: str = Query(..., description="View token (shareable link)"),
    db=Depends(get_db),
):
    """Attachment bytes for a public /view page, authenticated by the same view
    token the page itself reads with.

    Same-origin so pdf.js can fetch it: `file_url` on the summary is a signed
    storage URL (R2/S3/CloudFront) with no CORS headers, so the browser cannot
    read its bytes directly (PR #1256 review, blocking finding 1).

    Ownership before existence, same gate shape as the portal's attachment
    route: the token must resolve to an entity, and the attachment must be
    linked to THAT entity, or this 404s exactly like an unknown attachment id
    would - never confirming a guessed id belongs to someone else's record.
    """
    try:
        ensure_public_view_links_allowed(db, current_user_id=None)
        link_entity_type = _ATTACHMENT_ENTITY_TYPES.get(entity)
        if not link_entity_type:
            raise HTTPException(status_code=404, detail="Unsupported public view entity.")

        view_token = (
            db.query(ViewToken)
            .filter(ViewToken.token == token, ViewToken.entity_type == link_entity_type)
            .first()
        )
        if not view_token or not view_token.entity_id:
            raise handle_not_found("View link", "(invalid token)")

        links = EntityAttachmentService(db).list_links(link_entity_type, str(view_token.entity_id))
        if not any(str(link.attachment_id) == attachment_id for link in links):
            raise handle_not_found("Attachment", attachment_id)

        attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
        if attachment is None:
            raise handle_not_found("Attachment", attachment_id)

        from app.services.resources_service import AttachmentService

        try:
            content = AttachmentService(db).get_file_content(attachment_id)
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning("Public view attachment download failed for %s: %s", attachment_id, e)
            raise HTTPException(status_code=502, detail="File download failed. Please try again.") from e

        filename = attachment.original_filename or attachment.stored_filename or "attachment"
        return Response(
            content=content,
            media_type=str(getattr(attachment, "mime_type", None) or "application/octet-stream"),
            headers={
                "Content-Disposition": content_disposition(filename),
                "Content-Length": str(len(content)),
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
