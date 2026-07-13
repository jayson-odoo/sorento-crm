"""Public approval endpoints (no auth): validate token, get summary, submit approve/reject."""
from fastapi import APIRouter, Depends, Query, HTTPException, Request

from app.database import get_db
from app.services.procurement_service import PurchaseRequestService
from app.schemas.procurement import (
    PublicApprovalSummaryResponse,
    PublicApprovalSubmitRequest,
)
from app.services.error_handler import handle_internal_error
from app.services.audit_service import log_audit, _model_to_audit_dict

router = APIRouter()


@router.get("/summary", response_model=PublicApprovalSummaryResponse)
async def get_approval_summary(
    token: str = Query(..., description="One-time approval token"),
    db=Depends(get_db),
):
    """Return request summary for the given token (for public approval page). No auth required."""
    try:
        service = PurchaseRequestService(db)
        summary = service.get_approval_summary_by_token(token)
        return summary
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/submit")
async def submit_approval(
    data: PublicApprovalSubmitRequest,
    request: Request,
    token: str = Query(..., description="One-time approval token"),
    db=Depends(get_db),
):
    """Submit approval or rejection. No auth required. Token is consumed."""
    try:
        service = PurchaseRequestService(db)
        header_before = None
        entity_id_for_skip = None
        try:
            summary = service.get_approval_summary_by_token(token)
            entity_id_for_skip = summary["entity_id"]
            header_before = service.get_request(entity_id_for_skip)
        except Exception:
            pass
        # Skip automatic UPDATE audit for this entity so we log once with custom description below
        if entity_id_for_skip:
            db.info.setdefault("skip_audit_for", []).append(("purchase_request", entity_id_for_skip))
        header = service.submit_approval(
            token_value=token,
            action=data.action,
            approved_by=data.approved_by,
            approval_signature_ref=data.approval_signature_ref,
            approval_comments=data.approval_comments,
        )
        old_values = _model_to_audit_dict(header_before) if header_before else None
        # Attribute to the request's contact (WS2a) rather than "System".
        contact_id = getattr(header, "contact_id", None)
        log_audit(
            db,
            "purchase_request",
            str(header.id),
            "UPDATE",
            old_values=old_values,
            new_values=_model_to_audit_dict(header),
            user_id=None,
            contact_id=str(contact_id) if contact_id else None,
            description=f"Approval {data.action} via public link",
            ip_address=request.client.host if request and request.client else None,
        )
        db.commit()
        return {"status": "ok", "approval_status": header.approval_status}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
