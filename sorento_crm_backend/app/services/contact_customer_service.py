"""Resolving a WhatsApp contact to the customer account they belong to.

The dealer kit needs this: a consumer arrives holding a portal token, and
whether their design becomes a quote against a real account depends on knowing
which account that is. It is deliberately NOT dealer-kit code - "who is this
phone number, commercially" is a question the whole CRM asks.

Two operations, kept apart on purpose:

- **Resolution** reads confirmed links only. It answers, or it declines.
- **Proposal** matches phone numbers and returns candidates. It never writes.

The split is the whole design. An automatic phone match that linked itself would
attach a quote to the wrong company the first time two people shared a landline,
and nobody would find out until the invoice.
"""
from __future__ import annotations

from typing import Sequence

from sqlalchemy.orm import Session

from app.models.access import RespondContact, RespondContactCustomer
from app.models.order import Customer
from app.utils.phone_normalize import normalize_phone

# Malaysian mobile numbers are written with and without the 60 country code and
# with or without the trunk 0, so exact equality misses the common case. Nine
# digits is enough to identify a subscriber and short enough to still match
# across those prefixes; below that the match is noise, not signal.
_SUFFIX_DIGITS = 9


def list_links(db: Session, contact_id: str) -> list[RespondContactCustomer]:
    """Every link for a contact, within the caller's company scope."""
    return (
        db.query(RespondContactCustomer)
        .filter(RespondContactCustomer.contact_id == contact_id)
        .order_by(RespondContactCustomer.created_at)
        .all()
    )


def resolve_customer(db: Session, contact_id: str) -> str | None:
    """The customer this contact acts for, or None.

    None has two meanings and both are correct: nobody has linked them, or they
    are linked to several accounts and no primary has been chosen. In the second
    case an answer exists in the data but not in the domain, and returning a
    guess is worse than returning nothing - the caller can ask.
    """
    links = list_links(db, contact_id)
    if not links:
        return None
    if len(links) == 1:
        return links[0].customer_id

    primary = [link for link in links if link.is_primary]
    return primary[0].customer_id if primary else None


def link_customer(
    db: Session,
    contact_id: str,
    customer_id: str,
    is_primary: bool = False,
    source: str = "manual",
    linked_by: str | None = None,
) -> RespondContactCustomer:
    """Create (or update) the link. Re-linking the same pair is not an error.

    Idempotent because the callers are a human clicking twice and a backfill
    re-running, and both deserve the same answer.
    """
    existing = (
        db.query(RespondContactCustomer)
        .filter(
            RespondContactCustomer.contact_id == contact_id,
            RespondContactCustomer.customer_id == customer_id,
        )
        .first()
    )

    if is_primary:
        _demote_other_primaries(db, contact_id, keep_customer_id=customer_id)

    if existing:
        if is_primary:
            existing.is_primary = True
        return existing

    link = RespondContactCustomer(
        contact_id=contact_id,
        customer_id=customer_id,
        is_primary=is_primary,
        source=source,
        linked_by=linked_by,
    )
    db.add(link)
    db.flush()
    return link


def unlink_customer(db: Session, contact_id: str, customer_id: str) -> bool:
    """Drop the link. The customer and the contact both survive it."""
    link = (
        db.query(RespondContactCustomer)
        .filter(
            RespondContactCustomer.contact_id == contact_id,
            RespondContactCustomer.customer_id == customer_id,
        )
        .first()
    )
    if not link:
        return False
    db.delete(link)
    return True


def _demote_other_primaries(db: Session, contact_id: str, keep_customer_id: str) -> None:
    """Only one primary per contact per company - the index enforces it too.

    Demoting here rather than letting the insert fail means "make this the
    primary" behaves like the sentence it is, instead of asking the caller to
    clear the old one first.
    """
    others = (
        db.query(RespondContactCustomer)
        .filter(
            RespondContactCustomer.contact_id == contact_id,
            RespondContactCustomer.customer_id != keep_customer_id,
            RespondContactCustomer.is_primary.is_(True),
        )
        .all()
    )
    for link in others:
        link.is_primary = False
    if others:
        # The partial unique index is checked per statement, so the demotion has
        # to reach the database before the new primary is inserted.
        db.flush()


def propose_customers(db: Session, contact_id: str) -> Sequence[Customer]:
    """Customers whose phone number looks like this contact's. Never writes.

    A proposal in the glossary sense: the system offers, a human confirms. The
    match is on the last nine digits so that 60123456789, 0123456789 and
    123456789 are recognised as one subscriber, and anything shorter than that
    is refused rather than matched loosely.
    """
    contact = db.query(RespondContact).filter(RespondContact.id == contact_id).first()
    if not contact:
        return []

    suffix = normalize_phone(contact.phone_number)[-_SUFFIX_DIGITS:]
    if len(suffix) < _SUFFIX_DIGITS:
        return []

    already_linked = {link.customer_id for link in list_links(db, contact_id)}

    # Normalising in SQL would need a per-row regexp on a column with no
    # functional index; the candidate set here is one company's customers with a
    # phone number at all, which is small enough to filter honestly in Python.
    candidates = (
        db.query(Customer)
        .filter(Customer.phone_number.isnot(None))
        .filter(Customer.phone_number != "")
        .all()
    )

    return [
        customer
        for customer in candidates
        if customer.id not in already_linked
        and normalize_phone(customer.phone_number).endswith(suffix)
    ]
