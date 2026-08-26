"""The supplier's read-only view of a container request, reached by a tokenised link.

Public on purpose, and narrow on purpose - the same shape as `quotation_sign.py`, which is
the pattern this follows. The token identifies ONE notice, expires after thirty days, and is
the only credential; nothing here takes an id from the caller, so a leaked link exposes
exactly the one request it was minted for and nothing else about the supplier, the plan or
the price.

An unknown token, an expired one and one retired by a resend get the SAME answer.
Distinguishing them would confirm to anybody guessing that a token exists.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.error_handler import handle_internal_error
from app.services.scm import supplier_notice_service as svc

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{token}")
async def read_supplier_request(token: str, db: Session = Depends(get_db)):
    """What we asked this supplier to pack, as it was asked (AC-C6)."""
    try:
        return svc.public_request_page(db, token)
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/{token}/document/{kind}")
async def read_supplier_request_document(
    token: str,
    kind: str = Path(..., pattern="^(pdf|xlsx)$"),
    db: Session = Depends(get_db),
):
    """A short-lived link to the PDF, or to their own stock list with the quantity to load.

    `kind` is constrained in the path rather than validated in the service so an unknown value
    never reaches a storage lookup at all.
    """
    try:
        return svc.public_document_url(db, token, kind)
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))
