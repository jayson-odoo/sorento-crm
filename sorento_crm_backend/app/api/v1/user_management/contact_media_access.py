"""Per-contact chatbot media access, for the CRM operator.

`GET|PUT /api/v1/user-management/contacts/{contact_id}/media-access[/{modality}]`.

Ordinary JWT routes under `user_management`, not `/external/`, because the caller
is the CRM frontend. Authorisation is the contact-edit permission - no new
admin-only role, per the captain (UAC S1-06).

Two things in the response are load-bearing rather than cosmetic:

* `has_row` is separate from `is_allowed`, so the card can say "never configured"
  rather than "someone turned this off". Those are different support conversations.
* `resets_on` arrives already rendered ("1 September") and `updated_by_name` is a
  name, not an id. No caller does date arithmetic and no UUID reaches the UI.
"""
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models.access import RespondContact
from app.services.error_handler import handle_internal_error, handle_not_found
from app.services.media_access_service import build_access_view, upsert_access

logger = logging.getLogger(__name__)

router = APIRouter()

CONTACT_EDIT_PERMISSION = "user_management.contacts.edit"

MediaModality = Literal["image", "voice"]


class ContactMediaAccessUpdate(BaseModel):
    is_allowed: bool
    monthly_limit: Optional[int] = Field(
        None, ge=0, le=100000, description="null clears the override and inherits the default."
    )
    max_clip_seconds: Optional[int] = Field(
        None, ge=1, le=3600, description="Voice only; ignored for image."
    )


def _require_contact(db: Session, contact_id: str) -> RespondContact:
    contact = db.query(RespondContact).filter(RespondContact.id == contact_id).first()
    if contact is None:
        raise handle_not_found("Contact", contact_id)
    return contact


@router.get("/{contact_id}/media-access", status_code=status.HTTP_200_OK)
async def get_contact_media_access(
    contact_id: str,
    current_user: dict = Depends(require_permission(CONTACT_EDIT_PERMISSION)),
    db: Session = Depends(get_db),
):
    """The Media Access card: the period and both modalities, always."""
    _ = current_user
    try:
        _require_contact(db, contact_id)
        return build_access_view(db, contact_id)
    except Exception as exc:
        if hasattr(exc, "status_code"):
            raise
        logger.exception("failed to read media access for contact %s", contact_id)
        raise handle_internal_error(str(exc))


@router.put("/{contact_id}/media-access/{modality}", status_code=status.HTTP_200_OK)
async def update_contact_media_access(
    contact_id: str,
    modality: MediaModality,
    payload: ContactMediaAccessUpdate,
    current_user: dict = Depends(require_permission(CONTACT_EDIT_PERMISSION)),
    db: Session = Depends(get_db),
):
    """Upsert the gate row for one modality and return the recomputed item."""
    try:
        _require_contact(db, contact_id)
        item = upsert_access(
            db,
            contact_id,
            modality,
            is_allowed=payload.is_allowed,
            monthly_limit=payload.monthly_limit,
            max_clip_seconds=payload.max_clip_seconds,
            updated_by=str(current_user.get("id")) if current_user else None,
        )
        db.commit()
        return item
    except Exception as exc:
        if hasattr(exc, "status_code"):
            raise
        db.rollback()
        logger.exception("failed to update media access for contact %s", contact_id)
        raise handle_internal_error(str(exc))
