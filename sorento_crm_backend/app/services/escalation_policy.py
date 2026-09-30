"""ESCALATION-CONTROL (owner, 30 Sep 2026): may a contact be offered, or force, a
hand-off to customer service.

"We need to be able to control each contact that they cannot access the escalation:
cannot force escalate, won't be offered escalation; this is for dealer."

The contact's own override (`respond_contacts.escalation_allowed`, NULL = inherit) wins,
else the contact's access types merged PERMISSIVELY (`merge`): allowed when ANY type
allows it, blocked only when EVERY type blocks. Owner hand test, 30 Sep 2026: a contact
holding Sorento Office AND Sorento Dealer (Mr Loo) is staff and may escalate. This is
deliberately NOT `stock_visibility._merge_access_type_rows`'s most-restrictive rule,
which the first cut copied and which barred him. No types at all = allowed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

#: A dealer access type: a name whose last word is "Dealer", any case. The seed migration
#: (`esc1_0001_escalation_allowed.DEALER_NAME_SQL`) applies the same rule in SQL; the
#: access-type editor applies it too (`contactAccessTypeService.isDealerTypeName`).
_DEALER_NAME = re.compile(r"(^|\s)dealer\s*$", re.IGNORECASE)


def is_dealer_type_name(name: str | None) -> bool:
    """Owner ruling 30 Sep 2026: every dealer type blocks escalation by default."""
    return bool(_DEALER_NAME.search(name or ""))

SOURCE_CONTACT = "contact"
SOURCE_ACCESS_TYPE = "access_type"
SOURCE_DEFAULT = "default"


@dataclass(frozen=True)
class EscalationPolicy:
    allowed: bool
    source: str
    # The access type that decided an inherited value, for the contact screen's
    # "Inherited: allowed via Sorento Office" line; None for an override or no types.
    source_label: str | None = None


def merge(rows: list[tuple[str, bool, int | None]]) -> EscalationPolicy:
    """`(name, escalation_allowed, sort_order)` per access type, merged: allowed when any
    type allows, blocked only when every type blocks. `source_label` names the type that
    decided it, the first in catalogue order (sort_order, then name) among the allowing
    types, or among all of them when every one blocks."""
    if not rows:
        return EscalationPolicy(allowed=True, source=SOURCE_DEFAULT)
    ordered = sorted(rows, key=lambda r: (r[2] is None, r[2] if r[2] is not None else 0, str(r[0])))
    allowing = [r for r in ordered if r[1] is not False]
    decider = (allowing or ordered)[0]
    return EscalationPolicy(allowed=bool(allowing), source=SOURCE_ACCESS_TYPE, source_label=str(decider[0]))


def inherited_policy(db: Session, contact_pk: str) -> EscalationPolicy:
    """What the contact's access types say, ignoring the contact's own override."""
    from app.models.access import ContactAccessType, respond_contact_access_types

    rows = (
        db.query(ContactAccessType.name, ContactAccessType.escalation_allowed, ContactAccessType.sort_order)
        .join(
            respond_contact_access_types,
            respond_contact_access_types.c.access_type_code == ContactAccessType.code,
        )
        .filter(respond_contact_access_types.c.contact_id == contact_pk)
        .all()
    )
    return merge([(name, allowed, order) for name, allowed, order in rows])


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
