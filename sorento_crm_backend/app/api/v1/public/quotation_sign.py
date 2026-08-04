"""The customer's counter-sign page, reached by a tokenised link.

Public on purpose, and narrow on purpose. The token identifies ONE issue, expires, and is the only
credential; nothing here takes an id from the caller, so a leaked link exposes exactly the one
quotation it was minted for and nothing else in the project.

An unknown token and an expired token get the SAME answer. Distinguishing them would confirm to
anybody guessing that a token exists.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request, status
from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.projects import (
    QuotationSignAcceptRequest,
    QuotationSignPageResponse,
)
from app.services import project_quotation_document_service as svc
from app.services.error_handler import handle_internal_error

logger = logging.getLogger(__name__)

router = APIRouter()


def _client_ip(request: Request) -> str | None:
    """The caller's address as best we can tell behind a proxy.

    Recorded because a signature without any provenance is weaker evidence than one with it. The
    left-most XFF entry is the original client; the rest are hops.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.client.host if request.client else None


@router.get("/{token}", response_model=QuotationSignPageResponse)
async def read_quotation_for_signing(
    token: str,
    db: Session = Depends(get_db),
):
    """What the customer sees: the quotation as issued, read-only.

    Rendered from the ISSUE, not from live rows, so the page cannot show them something different
    from the PDF they were sent.
    """
    try:
        record = svc.get_issue_by_sign_token(db, token)
        return svc.serialize_sign_page(db, record)
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post("/{token}/accept", response_model=QuotationSignPageResponse)
async def accept_quotation(
    token: str,
    payload: QuotationSignAcceptRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """The customer signs, and that WINS the quotation.

    Client decision: a counter-signature is the commitment, so every scope the issue carried is
    marked won and the project's outcome follows. Idempotent, because a double-tap is not two
    agreements.
    """
    try:
        record = svc.get_issue_by_sign_token(db, token)
        svc.accept_issue(
            db,
            record=record,
            signer_name=payload.signer_name,
            mode=payload.mode,
            image_data_uri=payload.image_data_uri,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            gps_lat=payload.gps_lat,
            gps_lng=payload.gps_lng,
        )
        db.commit()
        return svc.serialize_sign_page(db, record)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))
