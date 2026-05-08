"""Per-attachment AI extract for master-data field tooltips.

Distinct from the portal extract endpoint at
``/api/v1/public/portal/ai-extract`` — this one is JWT-authenticated, takes an
existing ``attachment_id`` instead of multipart files, and runs the extract
pipeline against that doc only, narrowed to the requested ``field_keys``.

Used by the product-detail Specifications tooltip: click "AI Extract" next to
Weight / Dimensions / etc. and the FE posts here to get suggested values that
the user can review and apply.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.services.ai_extract.extract_service import AIExtractService, ExtractResult
from app.services.error_handler import handle_validation_error
from app.services.field_linkage import SUPPORTED_ENTITY_TYPES, validate_field_keys


router = APIRouter()
logger = logging.getLogger(__name__)


_ENTITY_TO_FORM_KEY: dict[str, str] = {
    "product": "master.product_fields",
    "promotion": "master.promotion_fields",
    "packing_list": "master.packing_list_fields",
    "form": "master.form_fields",
}


class AIExtractFieldRequest(BaseModel):
    attachment_id: str
    entity_type: str
    entity_id: str
    field_keys: list[str]

    @field_validator("attachment_id", "entity_type", "entity_id")
    @classmethod
    def _strip(cls, v: str) -> str:
        return (v or "").strip()

    @field_validator("field_keys")
    @classmethod
    def _at_least_one(cls, v: list[str]) -> list[str]:
        cleaned = [k.strip() for k in (v or []) if (k or "").strip()]
        if not cleaned:
            raise ValueError("field_keys must contain at least one key.")
        return cleaned


@router.post("/")
def ai_extract_field(
    payload: AIExtractFieldRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExtractResult:
    et = payload.entity_type
    if et not in SUPPORTED_ENTITY_TYPES:
        raise handle_validation_error(
            f"Unsupported entity_type '{et}'. "
            f"Expected one of: {', '.join(SUPPORTED_ENTITY_TYPES)}."
        )
    ok, unknown = validate_field_keys(et, payload.field_keys)
    if unknown:
        raise handle_validation_error(
            f"Unknown field_keys for {et}: {', '.join(unknown)}"
        )
    if not ok:
        raise handle_validation_error("field_keys is empty after validation.")

    form_key = _ENTITY_TO_FORM_KEY[et]
    service = AIExtractService(db)
    user_id: Optional[str] = current_user.get("id") if isinstance(current_user, dict) else None
    return service.extract_against_attachment(
        form_key,
        payload.attachment_id,
        field_subset=ok,
        user_id=user_id,
    )
