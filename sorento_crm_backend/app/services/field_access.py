"""Which fields an agent may be told, as data rather than as code.

Replaces the first design, which invented a whole access agent
(`container_status_enquiries`) just to unlock a hardcoded list of clearance
fields. That does not scale: a contact asking "when does my container arrive" is
already routed to `incoming_stock_enquiries` (53 contacts hold it), so gating on a
second agent means every one of them needs a second grant, n8n has to know about
an agent it never routes to, and every future sensitive field means another agent.

Here the agent stays the FUNCTION ("incoming stock enquiries") and the fields it
may reveal are rows.

**Three-way answer, not a boolean.** A denial has a reason and the reason matters
to the caller, because "you were never given this function" and "you have the
function but not this field" are different admin actions:

    ALLOWED             visible
    AGENT_NOT_ASSIGNED  the contact does not hold the agent that owns this field
    FIELD_NOT_ALLOWED   the contact holds the agent, but not this field

**Only registered fields are gated.** `GATED_FIELDS` lists what is protectable per
resource; anything absent from it is always visible. That is what keeps every
existing response byte-identical - the gate can only ever take away fields that
were added deliberately to the registry.

**Default deny for gated fields.** A newly registered sensitive field is invisible
to everyone until an admin adds a row. The alternative - visible until someone
remembers to restrict it - is how the ETA delay ends up in a dealer's chat on
deploy day.

**Enforcement lives in the data endpoint**, not in a check the caller must
remember to make. `check_attributes` exists so n8n can phrase a refusal without
fetching ("I can't share the gatepass date"), but it is a convenience: forgetting
to call it must never be the difference between safe and leaking.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------- the registry

#: resource -> the fields that CAN be gated on it. A field not listed here is
#: never stripped, which is what guarantees existing responses are unchanged.
#: The agent named alongside is the function that owns the field: it is the agent
#: an admin grants, and the one reported in an AGENT_NOT_ASSIGNED denial.
GATED_FIELDS: dict[str, dict[str, str]] = {
    "incoming_stock": {
        field: "incoming_stock_enquiries"
        for field in (
            "eta_date",
            "eta_delay_date",
            "inspection_date",
            "approval_date",
            "gatepass_date",
            "warehouse_arrival_date",
            "informed_collection_date",
            "collection_date",
            "loading_date",
            "etc_date",
            "etd_date",
            "liner_code",
            "china_forwarder",
            "malaysia_forwarder",
            "consignee",
            "delivery_warehouse",
            "free_days_available",
            "loc",
            "stacked",
            "coa_permit_no",
            "source_sheet",
        )
    }
}

#: Deliberately NOT gated on `incoming_stock`, and worth naming so nobody adds it
#: by reflex: `estimated_arrival_date` is the public ETA those 53 contacts already
#: receive, and `shipment_number` / `shipping_container_number` / `lines` /
#: `attachment` are the answer itself.

#: Admin-facing labels. The column name is not what an admin deciding "may a
#: dealer be told this" is thinking in, and `loc` / `etc_date` / `coa_permit_no`
#: are unguessable. Falls back to a title-cased key.
FIELD_LABELS: dict[str, str] = {
    "eta_date": "ETA",
    "eta_delay_date": "ETA delay",
    "inspection_date": "CIDB inspection",
    "approval_date": "CIDB approval",
    "gatepass_date": "Gatepass",
    "warehouse_arrival_date": "Warehouse arrival",
    "informed_collection_date": "Collection informed",
    "collection_date": "Collection",
    "loading_date": "Loading",
    "etc_date": "ETC (estimated time of container closing)",
    "etd_date": "ETD (estimated time of departure)",
    "liner_code": "Liner",
    "china_forwarder": "China forwarder",
    "malaysia_forwarder": "Malaysia forwarder",
    "consignee": "Consignee",
    "delivery_warehouse": "Delivery warehouse",
    "free_days_available": "Free days available",
    "loc": "Location",
    "stacked": "Stacked",
    "coa_permit_no": "COA permit no.",
    "source_sheet": "Source sheet",
}


def field_label(field_key: str) -> str:
    return FIELD_LABELS.get(field_key) or field_key.replace("_", " ").capitalize()


#: What a STAFF caller needs instead. Agent grants govern contacts asking through
#: WhatsApp; a logged-in user is governed by RBAC like everything else.
CLEARANCE_PERMISSION = "procurement.packing_lists.view_clearance"

ALLOWED = "allowed"
AGENT_NOT_ASSIGNED = "agent_not_assigned"
FIELD_NOT_ALLOWED = "field_not_allowed"
NOT_GATED = "not_gated"


@dataclass(frozen=True)
class FieldDecision:
    field: str
    #: The agent that owns this field, so an admin knows what to grant.
    agent_code: Optional[str]
    outcome: str

    @property
    def allowed(self) -> bool:
        return self.outcome in (ALLOWED, NOT_GATED)

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "agent_code": self.agent_code,
            "outcome": self.outcome,
            "reason": _REASONS.get(self.outcome),
        }


_REASONS = {
    ALLOWED: None,
    NOT_GATED: None,
    AGENT_NOT_ASSIGNED: (
        "This contact does not hold the agent that owns this field. Assign the "
        "agent to the contact, then allow the field on it."
    ),
    FIELD_NOT_ALLOWED: (
        "This contact holds the agent, but this field is not allowed on it. Tick "
        "the field on the agent, or add a per-contact override."
    ),
}


# ------------------------------------------------------------------- resolution


def resolve_contact_id(
    db: Session, contact_id: str, space_id: Optional[str] = None
) -> Optional[str]:
    """Accept either id space and return the internal `respond_contacts.id`.

    Grants key on the internal id, but n8n thinks in Respond.io ids and different
    callers reach here having resolved a different amount. Guessing wrong denies a
    contact who is in fact entitled, which reads as a broken feature rather than a
    lookup mismatch, so try both.

    `space_id` disambiguates the Respond.io branch: the same `respond_io_id` can
    exist in two workspaces, and resolving to the wrong one would answer with a
    stranger's grants. Without it, an ambiguous id resolves to nothing rather than
    to a coin flip.
    """
    try:
        from app.models.access import RespondContact
        from app.models.respond_workspace import RespondWorkspace

        key = str(contact_id)
        if db.query(RespondContact.id).filter(RespondContact.id == key).first():
            return key

        q = db.query(RespondContact.id).filter(RespondContact.respond_io_id == key)
        if space_id:
            q = q.join(
                RespondWorkspace, RespondWorkspace.id == RespondContact.workspace_id
            ).filter(RespondWorkspace.space_id == str(space_id))

        rows = q.limit(2).all()
        if len(rows) != 1:
            if len(rows) > 1:
                logger.warning(
                    "respond_io_id %s matches %s contacts and no space_id was given; "
                    "denying rather than picking one",
                    key,
                    len(rows),
                )
            return None
        return rows[0][0]
    except Exception:  # noqa: BLE001 - fail closed
        logger.warning("Contact resolution failed for %s", contact_id, exc_info=True)
        return None


def contact_agent_codes(db: Session, contact_id: str) -> set[str]:
    """Agent codes this contact currently holds. Fails closed to an empty set."""
    try:
        from app.models.access import AccessAgent, ContactAgentAccess

        now = datetime.utcnow()
        rows = (
            db.query(AccessAgent.code)
            .join(ContactAgentAccess, ContactAgentAccess.agent_id == AccessAgent.id)
            .filter(
                ContactAgentAccess.respond_contact_id == str(contact_id),
                ContactAgentAccess.is_allowed.is_(True),
                AccessAgent.is_active.is_(True),
                or_(
                    ContactAgentAccess.valid_from.is_(None),
                    ContactAgentAccess.valid_from <= now,
                ),
                or_(
                    ContactAgentAccess.valid_to.is_(None),
                    ContactAgentAccess.valid_to >= now,
                ),
            )
            .all()
        )
        return {code for (code,) in rows}
    except Exception:  # noqa: BLE001 - fail closed
        logger.warning(
            "Agent lookup failed for contact %s; treating as holding none",
            contact_id,
            exc_info=True,
        )
        return set()


def allowed_fields_for(
    db: Session, *, contact_id: str, resource: str, agent_codes: Iterable[str]
) -> set[str]:
    """Fields these agents may reveal to this contact.

    A row with a NULL `contact_id` applies to everyone holding the agent - that is
    the normal case. A row WITH this contact's id overrides it, allowing or denying
    that one field for that one contact without disturbing the other 52.
    """
    try:
        from app.models.access import AgentFieldAccess

        codes = list(agent_codes)
        if not codes:
            return set()

        rows = (
            db.query(
                AgentFieldAccess.field_key,
                AgentFieldAccess.contact_id,
                AgentFieldAccess.is_allowed,
            )
            .filter(
                AgentFieldAccess.resource == resource,
                AgentFieldAccess.agent_code.in_(codes),
                or_(
                    AgentFieldAccess.contact_id.is_(None),
                    AgentFieldAccess.contact_id == str(contact_id),
                ),
            )
            .all()
        )
    except Exception:  # noqa: BLE001 - fail closed
        logger.warning("Field-access lookup failed; denying all", exc_info=True)
        return set()

    # Per-contact rows win over the agent-wide default, in either direction.
    default: dict[str, bool] = {}
    override: dict[str, bool] = {}
    for field_key, row_contact_id, is_allowed in rows:
        (override if row_contact_id else default)[field_key] = bool(is_allowed)

    resolved = {**default, **override}
    return {field for field, allowed in resolved.items() if allowed}


def decide(
    db: Session,
    *,
    resource: str,
    fields: Iterable[str],
    contact_id: Optional[str],
    space_id: Optional[str] = None,
) -> list[FieldDecision]:
    """One decision per requested field, each carrying WHY."""
    registry = GATED_FIELDS.get(resource, {})
    requested = list(fields)

    if not contact_id:
        # No contact in play: nothing to resolve a grant against, so every gated
        # field is denied for the reason an admin can act on.
        return [
            FieldDecision(f, registry.get(f), NOT_GATED if f not in registry else AGENT_NOT_ASSIGNED)
            for f in requested
        ]

    resolved = resolve_contact_id(db, contact_id, space_id)
    if resolved is None:
        # An unknown contact holds nothing. Same shape as holding no agent, which
        # is also the right advice: assign the agent (to a contact that exists).
        return [
            FieldDecision(f, registry.get(f), NOT_GATED if f not in registry else AGENT_NOT_ASSIGNED)
            for f in requested
        ]

    held = contact_agent_codes(db, resolved)
    allowed = allowed_fields_for(
        db, contact_id=resolved, resource=resource, agent_codes=held
    )

    decisions: list[FieldDecision] = []
    for field in requested:
        owner = registry.get(field)
        if owner is None:
            decisions.append(FieldDecision(field, None, NOT_GATED))
        elif owner not in held:
            decisions.append(FieldDecision(field, owner, AGENT_NOT_ASSIGNED))
        elif field not in allowed:
            decisions.append(FieldDecision(field, owner, FIELD_NOT_ALLOWED))
        else:
            decisions.append(FieldDecision(field, owner, ALLOWED))
    return decisions


def check_attributes(
    db: Session,
    *,
    resource: str,
    attributes: Iterable[str],
    contact_id: Optional[str],
    space_id: Optional[str] = None,
) -> dict[str, Any]:
    """Answer "may this contact be told X?" without returning any data.

    For n8n, so it can refuse in words rather than fetch and find a hole. This is a
    convenience: the data endpoint enforces the same rules independently.
    """
    decisions = decide(
        db,
        resource=resource,
        fields=attributes,
        contact_id=contact_id,
        space_id=space_id,
    )
    return {
        "contact_id": contact_id,
        "resource": resource,
        "all_allowed": all(d.allowed for d in decisions),
        "attributes": [d.as_dict() for d in decisions],
    }


# --------------------------------------------------------------- payload gating


def _strip(payload: Any, drop: set[str]) -> Any:
    if isinstance(payload, dict):
        return {k: _strip(v, drop) for k, v in payload.items() if k not in drop}
    if isinstance(payload, list):
        return [_strip(item, drop) for item in payload]
    return payload


def apply_field_access(
    db: Session,
    payload: Any,
    *,
    resource: str,
    contact_id: Optional[str] = None,
    space_id: Optional[str] = None,
    current_user: Optional[Mapping[str, Any]] = None,
    staff_permission: Optional[str] = None,
) -> Any:
    """Return the payload as this caller may see it, plus why anything is missing.

    Denied fields are ABSENT from the rows - absent means "not permitted", null
    would mean "not reached yet", and an LLM will narrate a null as the second.
    The reason lives in a sibling `field_access` block instead, so the caller can
    say "I can't share that" rather than "that hasn't happened yet".
    """
    registry = GATED_FIELDS.get(resource, {})
    if not registry:
        return payload

    if contact_id:
        decisions = decide(
            db,
            resource=resource,
            fields=registry.keys(),
            contact_id=contact_id,
            space_id=space_id,
        )
    else:
        # A staff caller (a session, or the API key with no contact in play) is
        # governed by an RBAC permission, not by an agent grant.
        entitled = _staff_entitled(db, current_user, staff_permission)
        decisions = [
            FieldDecision(f, registry[f], ALLOWED if entitled else FIELD_NOT_ALLOWED)
            for f in registry
        ]

    denied = [d for d in decisions if not d.allowed]
    if not denied:
        return payload

    gated = _strip(payload, {d.field for d in denied})
    if isinstance(gated, dict):
        gated["field_access"] = {
            "denied": [d.as_dict() for d in denied],
            "note": (
                "These fields are omitted because this caller may not see them. "
                "Absent does NOT mean the value is unknown or not yet reached."
            ),
        }
    return gated


def _staff_entitled(
    db: Session,
    current_user: Optional[Mapping[str, Any]],
    permission: Optional[str],
) -> bool:
    user_id = (current_user or {}).get("id")
    if not user_id or not permission:
        return False
    try:
        from app.services.user_service import UserPermissionService

        return bool(
            UserPermissionService(db).check_user_has_permission(str(user_id), permission)
        )
    except Exception:  # noqa: BLE001 - fail closed
        logger.warning("Permission lookup failed for %s; denying", user_id, exc_info=True)
        return False
