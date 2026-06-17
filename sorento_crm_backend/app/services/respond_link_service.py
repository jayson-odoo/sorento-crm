"""Resolve a CRM user to the WhatsApp contact (respond_io_id) they're reachable on.

Resolution order (TCK-2026-000031):
  1. explicit link  -> users.respond_contact_id
  2. phone match    -> single RespondContact whose phone_number == normalised contact_number
  3. None

A successful phone match is cached onto users.respond_contact_id so later sends
are an O(1) FK lookup. Matching is via the single E.164 normaliser used on both
sides, so the link is deterministic. A non-unique match (0 or >1) returns None
rather than guessing.
"""
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.access import RespondContact
from app.services.phone_utils import normalize_msisdn

logger = logging.getLogger(__name__)


def resolve_user_respond_contact(db: Session, user: User, *, cache: bool = True) -> Optional[RespondContact]:
    """Return the linked RespondContact (explicit or phone-matched) or None."""
    if user is None:
        return None
    if getattr(user, "respond_contact_id", None):
        return db.query(RespondContact).filter(RespondContact.id == user.respond_contact_id).first()
    n = normalize_msisdn(getattr(user, "contact_number", None))
    if not n:
        return None
    matches = db.query(RespondContact).filter(RespondContact.phone_number == n).all()
    if len(matches) != 1:
        return None
    rc = matches[0]
    if cache:
        try:
            user.respond_contact_id = rc.id
            db.commit()
        except Exception as exc:  # best-effort cache; never block the caller
            logger.warning("Failed to cache respond_contact_id for user %s: %s", getattr(user, "id", "?"), exc)
            db.rollback()
    return rc


def resolve_user_respond_io_id(db: Session, user: User, *, cache: bool = True) -> Optional[str]:
    """Return the user's WhatsApp respond_io_id, or None if unreachable."""
    rc = resolve_user_respond_contact(db, user, cache=cache)
    return rc.respond_io_id if rc else None
