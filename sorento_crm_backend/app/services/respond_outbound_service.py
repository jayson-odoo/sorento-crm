"""The per-contact outbound kill switch (`respond_contacts.outbound_enabled`).

One place owns both halves of the switch: the guard every outbound Respond.io
send passes through, and the enable/disable operations that flip it. Keeping
them together means the write side can never drift from what the read side
enforces.

Scope: OUTBOUND ONLY. Reads (fetching a contact, listing messages, closing a
conversation) are never gated - the switch governs what we say, not what we can
see. The three gated paths are `RespondClient.send_message`,
`.send_attachment` and `.send_template_message`.
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple

from fastapi import status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.access import RespondContact
from app.services.error_handler import AppException
from app.services.respond_identifier import contact_for_identifier

logger = logging.getLogger(__name__)


def assert_outbound_enabled(identifier: Optional[str], db: Optional[Session] = None) -> None:
    """Raise when `identifier` addresses a contact whose outbound is switched off.

    Resolution is `respond_identifier.contact_for_identifier`, i.e. exactly the
    lookup `_resolve_workspace_credentials` performs for the same identifier.

    **Unresolvable identifiers fail OPEN** (the send proceeds, logged at
    WARNING). Failing closed would break first-contact sends, where no
    `respond_contacts` row exists yet, and would silently disable an entire
    integration on a naming mismatch. The kill switch is about known contacts;
    an unknown identifier is a gap in our records, not a decision to mute.

    A database failure during the check is logged and RE-RAISED, never
    swallowed: "we could not tell" must not be read as "allowed".

    Owns a short-lived Session when `db` is not supplied - the same pattern
    `_resolve_workspace_credentials` uses, since `RespondClient` methods take no
    session.
    """
    own_session = False
    try:
        if db is None:
            from app.database import SessionLocal

            db = SessionLocal()
            own_session = True
        contact = contact_for_identifier(db, identifier)
        # Read what is needed BEFORE the session closes below; a detached
        # instance keeps loaded attributes, but do not rely on that.
        enabled = True if contact is None else bool(contact.outbound_enabled)
        label = None if contact is None else (contact.name or contact.phone_number or contact.id)
    except Exception:
        logger.error(
            "Outbound guard could not resolve contact for identifier %r; refusing "
            "to send rather than assume it is allowed.",
            identifier,
            exc_info=True,
        )
        raise
    finally:
        if own_session and db is not None:
            db.close()

    if contact is None:
        logger.warning(
            "Outbound Respond.io send to unresolved identifier %r - no respond_contacts "
            "row matched, so the per-contact outbound switch could not be checked.",
            identifier,
        )
        return

    if not enabled:
        logger.error(
            "Outbound Respond.io send BLOCKED: outbound messaging is switched off for "
            "contact %s (identifier %r).",
            label,
            identifier,
        )
        raise AppException(
            status_code=status.HTTP_403_FORBIDDEN,
            message=f"Outbound messaging is switched off for {label}.",
            detail=(
                "This contact's outbound switch (respond_contacts.outbound_enabled) is "
                "off, so no WhatsApp message was sent. Re-enable it with "
                "scripts/set_contact_outbound.py."
            ),
            code="OUTBOUND_DISABLED",
        )


def find_contact(db: Session, reference: str) -> Optional[RespondContact]:
    """Resolve a CLI-supplied contact reference: respond_io_id, phone or internal id."""
    if not reference:
        return None
    value = str(reference).strip()
    if not value:
        return None
    if ":" in value:
        value = value.split(":", 1)[1]
    return (
        db.query(RespondContact)
        .filter(
            or_(
                RespondContact.id == value,
                RespondContact.respond_io_id == value,
                RespondContact.phone_number == value,
            )
        )
        .first()
    )


def status_counts(db: Session) -> dict:
    """How many contacts can currently be messaged, and how many cannot."""
    total = db.query(RespondContact).count()
    disabled = (
        db.query(RespondContact)
        .filter(RespondContact.outbound_enabled.is_(False))
        .count()
    )
    return {"enabled": total - disabled, "disabled": disabled, "total": total}


def set_all_outbound(db: Session, *, enabled: bool, dry_run: bool = False) -> int:
    """Switch every contact on or off. Returns the number of rows that CHANGE.

    Already-correct rows are not counted and not written, so a second run
    reports zero - the same "set where mismatch" shape the backfill scripts use.
    A dry run reports the count and writes nothing.
    """
    pending = db.query(RespondContact).filter(
        RespondContact.outbound_enabled.is_(not enabled)
    )
    affected = pending.count()
    if dry_run or affected == 0:
        return affected
    pending.update({RespondContact.outbound_enabled: enabled}, synchronize_session=False)
    db.commit()
    return affected


def set_contact_outbound(
    db: Session, reference: str, *, enabled: bool, dry_run: bool = False
) -> Tuple[RespondContact, bool]:
    """Switch one contact on or off.

    Returns `(contact, changed)` where `changed` says whether this call altered
    (or, on a dry run, WOULD alter) the stored value. Raises when the reference
    matches no contact - silently doing nothing is the wrong answer for a tool
    that can silence a customer.
    """
    contact = find_contact(db, reference)
    if contact is None:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            message=f"No Respond contact matches {reference!r}.",
            detail="Pass a respond_io_id, a phone number, or the internal contact id.",
            code="CONTACT_NOT_FOUND",
        )
    changed = bool(contact.outbound_enabled) != enabled
    if changed and not dry_run:
        contact.outbound_enabled = enabled
        db.commit()
        db.refresh(contact)
    return contact, changed
