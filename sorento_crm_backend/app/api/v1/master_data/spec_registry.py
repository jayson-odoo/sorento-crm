"""Spec Registry read API.

The n8n semantic parser reads this to build its spec-extraction prompt, and the CRM
ranker reads the same rows to weight a match. One vocabulary, two consumers, so this
endpoint is the thing that stops them drifting.

Read-only by design: the vocabulary is changed by a seeded deploy or by an admin
editing a row, never by the caller.
"""
import hashlib
import json

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.services.error_handler import handle_internal_error
from app.services.product_spec_registry import active_registry

router = APIRouter()


def _serialise(row) -> dict:
    return {
        "spec_key": row.spec_key,
        "label": row.label,
        "data_type": row.data_type,
        "unit": row.unit,
        "allowed_values": row.allowed_values or [],
        "synonyms": row.synonyms or {},
        "applies_to_classes": row.applies_to_classes or [],
        "applies_when": row.applies_when or {},
        "rank_weight": float(row.rank_weight) if row.rank_weight is not None else None,
        "measured_coverage": row.measured_coverage,
    }


@router.get("")
@router.get("/")
async def get_spec_registry(
    request: Request,
    response: Response,
    current_user: dict = Depends(
        # Reuses the product-master read permission rather than minting a new one:
        # a new permission needs a grant sweep across provisioned roles, and this is
        # product vocabulary that anyone who may read products may read.
        require_permission_with_api_key("master_data.products.view")
    ),
    db: Session = Depends(get_db),
):
    """The active spec vocabulary, with an ETag so the parser can skip re-reading it."""
    try:
        rows = active_registry(db)
        keys = [_serialise(row) for row in rows]
        stamps = [r.updated_at or r.created_at for r in rows]
        updated_at = max(stamps).isoformat() if stamps else None

        payload = {"keys": keys, "updated_at": updated_at}

        # Hash the payload itself rather than the max timestamp: an admin edit that
        # lands in the same second still changes the body, and a stale prompt is
        # worse than a re-read.
        etag = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()[:32]
        etag_header = f'"{etag}"'

        if request.headers.get("if-none-match") == etag_header:
            return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag_header})

        response.headers["ETag"] = etag_header
        response.headers["Cache-Control"] = "private, max-age=60"
        return payload
    except Exception as e:
        raise handle_internal_error(str(e))
