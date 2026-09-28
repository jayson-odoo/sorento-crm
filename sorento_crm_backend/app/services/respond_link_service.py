"""Resolve a CRM user to the WhatsApp contact (respond_io_id) they're reachable on.

The link is the only way from a user to a contact: ``users.respond_contact_id``,
set by the owner (create from a contact, Link existing user, Edit profile) or, once,
by the identity S0 migration for every exact unique phone match (AC-04). No link,
no contact.

Identity S3 fix round 2 (#1280, reviewer B1): this used to fall back to a unique
phone match between ``users.contact_number`` and ``respond_contacts.phone_number``
and cache it onto the user (TCK-2026-000031). That undid the owner's Unlink on the
next notification, SLA summary, banner or WhatsApp task, and sent to the contact
the owner had detached. Plan 6.5 and AC-43 say nothing links by itself, and the
owner ruled (Q3/Q4, 26 Sep 2026 23:45 MYT) that setting users up "should be
controlled by me", so the fallback is gone rather than made read-only.
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.access import RespondContact


def resolve_user_respond_contact(db: Session, user: User) -> Optional[RespondContact]:
    """Return the user's linked RespondContact, or None when there is no link."""
    if user is None:
        return None
    contact_id = getattr(user, "respond_contact_id", None)
    if not contact_id:
        return None
    return db.query(RespondContact).filter(RespondContact.id == contact_id).first()


def resolve_user_respond_io_id(db: Session, user: User) -> Optional[str]:
    """Return the user's WhatsApp respond_io_id, or None if unreachable."""
    rc = resolve_user_respond_contact(db, user)
    return rc.respond_io_id if rc else None
