"""ESCALATION-CONTROL (owner, 30 Sep 2026): may a contact be offered, or force, a
hand-off to customer service.

"We need to be able to control each contact that they cannot access the escalation:
cannot force escalate, won't be offered escalation; this is for dealer."

Resolved the way `stock_visibility.resolve_policy` resolves its policy: the contact's own
override (`respond_contacts.escalation_allowed`, NULL = inherit) wins, else the contact's
access types merged most-restrictive-first (any type that bars escalation bars it, the
same direction `stock_visibility._merge_access_type_rows` ranks its modes), else allowed.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

SOURCE_CONTACT = "contact"
SOURCE_ACCESS_TYPE = "access_type"
SOURCE_DEFAULT = "default"


@dataclass(frozen=True)
class EscalationPolicy:
    allowed: bool
    source: str
    # The access type that decided an inherited value, for the contact screen's
    # "Inherited: blocked (Sorento Dealer)" line; None for an override or the default.
    source_label: str | None = None


def inherited_policy(db: Session, contact_pk: str) -> EscalationPolicy:
    """What the contact's access types say, ignoring the contact's own override."""
    from app.models.access import ContactAccessType, respond_contact_access_types

    rows = (
        db.query(ContactAccessType.name, ContactAccessType.escalation_allowed)
        .join(
            respond_contact_access_types,
            respond_contact_access_types.c.access_type_code == ContactAccessType.code,
        )
        .filter(respond_contact_access_types.c.contact_id == contact_pk)
        .all()
    )
    if not rows:
        return EscalationPolicy(allowed=True, source=SOURCE_DEFAULT)
    barring = sorted(str(name) for name, allowed in rows if allowed is False)
    if barring:
        return EscalationPolicy(allowed=False, source=SOURCE_ACCESS_TYPE, source_label=barring[0])
    return EscalationPolicy(
        allowed=True, source=SOURCE_ACCESS_TYPE, source_label=sorted(str(n) for n, _ in rows)[0]
    )


def resolve(db: Session, contact_pk: str) -> EscalationPolicy:
    """The policy that applies to one contact (internal `respond_contacts.id`)."""
    from app.models.access import RespondContact

    override = (
        db.query(RespondContact.escalation_allowed)
        .filter(RespondContact.id == contact_pk)
        .scalar()
    )
    if override is not None:
        return EscalationPolicy(allowed=bool(override), source=SOURCE_CONTACT)
    return inherited_policy(db, contact_pk)
