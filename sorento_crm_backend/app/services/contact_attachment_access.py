"""Which document types a given contact may retrieve.

`attachment_types.is_direct_access` is a single global boolean: a type is
dealer-downloadable or it is unreachable. That is the only axis today, and it is
too blunt for a document like the Container Status workbook, which the office
needs and dealers must not have.

This adds the second axis - a per-contact grant - and defines the visible set as
a UNION, never a subtraction:

    visible = types flagged is_direct_access      (the baseline, unchanged)
            ∪ types granted to this contact       (new)

Two consequences worth stating, because both are deliberate:

* **No contact can lose a document to this code.** The baseline is a floor. A
  contact with zero grants sees exactly what they saw before, so the feature is
  inert until an admin grants something.
* **It is type-level, not file-level.** Within a visible type the contact still
  receives every file regardless of `access_levels`. For Container Status the
  whole type is sensitive so the granularity fits; for a mixed type it does not,
  and per-file enforcement remains a separate, still-open problem.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def granted_type_ids(db: Session, internal_contact_id: str) -> set[str]:
    """Types explicitly granted to this contact. Empty set on any failure."""
    try:
        from app.models.access import ContactAttachmentType

        rows = (
            db.query(ContactAttachmentType.attachment_type_id)
            .filter(ContactAttachmentType.contact_id == str(internal_contact_id))
            .all()
        )
        return {str(r[0]) for r in rows}
    except Exception:  # noqa: BLE001 - fail closed to the baseline, never open
        logger.warning(
            "Attachment-type grant lookup failed for contact %s",
            internal_contact_id,
            exc_info=True,
        )
        return set()


def list_grants(db: Session, contact_id: str) -> dict:
    """Every attachment type plus whether this contact holds it.

    Returns the full catalog, not just the grants: an admin opening the dialog
    needs to see what CAN be granted, and `is_direct_access` types are shown
    already-on and non-removable because the baseline is not ours to withdraw.
    """
    from app.models.access import ContactAttachmentType
    from app.models.resources import AttachmentType

    granted = granted_type_ids(db, contact_id)
    types = (
        db.query(AttachmentType)
        .order_by(AttachmentType.type_name.asc())
        .all()
    )
    return {
        "data": [
            {
                "id": str(t.id),
                "type_name": t.type_name,
                "code": getattr(t, "code", None),
                # Baseline types reach every contact already; the tick is shown
                # on and locked rather than hidden, so the dialog explains why a
                # contact can see something it was never granted.
                "is_direct_access": bool(t.is_direct_access),
                "granted": str(t.id) in granted,
            }
            for t in types
        ],
        "granted_ids": sorted(granted),
    }


def set_grants(
    db: Session,
    contact_id: str,
    attachment_type_ids: list[str],
    actor: Optional[str] = None,
) -> dict:
    """Replace this contact's grants with the supplied set."""
    from app.models.access import ContactAttachmentType, RespondContact

    if not db.query(RespondContact.id).filter(RespondContact.id == contact_id).first():
        from app.services.error_handler import AppException

        raise AppException(status_code=404, message="Contact not found")

    wanted = {str(t) for t in (attachment_type_ids or []) if t}
    existing = {
        str(r.attachment_type_id): r
        for r in db.query(ContactAttachmentType).filter(
            ContactAttachmentType.contact_id == contact_id
        )
    }

    for type_id in wanted - existing.keys():
        db.add(
            ContactAttachmentType(
                contact_id=contact_id,
                attachment_type_id=type_id,
                created_by=actor,
            )
        )
    for type_id in existing.keys() - wanted:
        db.delete(existing[type_id])

    db.commit()
    return list_grants(db, contact_id)


def visible_type_ids(
    db: Session, contact_id: Optional[str], space_id: Optional[str] = None
) -> Optional[set[str]]:
    """Resolve the caller to the set of attachment types it may see.

    Returns ``None`` when there is nothing to widen - no contact supplied, or the
    contact resolved to nobody. ``None`` means "leave the existing filter alone",
    so an unresolvable contact falls back to the baseline rather than to
    everything.
    """
    if not contact_id:
        return None

    from app.services.field_access import resolve_contact_id
    from app.models.resources import AttachmentType

    internal_id = resolve_contact_id(db, contact_id, space_id)
    if not internal_id:
        logger.info(
            "Attachment-type grants: contact %s (space %s) did not resolve; "
            "serving the direct-access baseline only",
            contact_id,
            space_id,
        )
        return None

    granted = granted_type_ids(db, internal_id)
    if not granted:
        return None

    baseline = {
        str(r[0])
        for r in db.query(AttachmentType.id)
        .filter(AttachmentType.is_direct_access.is_(True))
        .all()
    }
    return baseline | granted
