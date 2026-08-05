"""Who may see clearance dates, decided server-side.

`/incoming-stock/list` and the `crm_incoming_stock_list` MCP tool already answer
"what is arriving" for salesperson-facing agents. Adding ETA delay, inspection,
approval and gatepass to that response would expose all of it to **every existing
agent on deploy** - the day this ships, a dealer-facing assistant could answer
"when did CIDB approve it".

So the gate is here, not in n8n. An unentitled caller does not get nulls or empty
strings: the clearance keys are **absent from the payload entirely**. Absent means
"you may not see this"; null would mean "not reached yet", and the two must not be
confused by anything reading the response - including an LLM, which will happily
narrate a null as "no approval date yet" when the truth is "you are not allowed to
know".

Two kinds of caller:

* **A contact** (n8n passes ``contact_id``, resolved from the WhatsApp sender).
  Entitled only when they hold the ``container_status_enquiries`` agent, currently
  valid. This is the grant an admin manages per contact.
* **A staff user** (a session, or the API key acting as a user). Entitled when
  their role holds ``procurement.packing_lists.view_clearance``.

Fail closed: an unresolvable caller, an inactive agent, an expired grant, or any
error resolving the grant all mean "not entitled". n8n's own safeguard is a second
layer on top of this, never the mechanism.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

#: The agent a contact must hold to be told clearance dates.
CONTAINER_STATUS_AGENT_CODE = "container_status_enquiries"

#: The permission a staff user's role must hold for the same.
CLEARANCE_PERMISSION = "procurement.packing_lists.view_clearance"

#: Keys stripped from a shipment payload for an unentitled caller. Deliberately
#: explicit rather than "anything ending in _date": `estimated_arrival_date` is
#: today's public ETA and must keep flowing to the agents that already read it.
CLEARANCE_KEYS: tuple[str, ...] = (
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


def contact_is_entitled(db: Session, contact_id: Optional[str]) -> bool:
    """Does this contact hold a currently-valid container status grant?"""
    if not contact_id:
        return False
    try:
        from app.models.access import AccessAgent, ContactAgentAccess

        now = datetime.utcnow()
        row = (
            db.query(ContactAgentAccess.id)
            .join(AccessAgent, AccessAgent.id == ContactAgentAccess.agent_id)
            .filter(
                ContactAgentAccess.respond_contact_id == str(contact_id),
                ContactAgentAccess.is_allowed.is_(True),
                AccessAgent.code == CONTAINER_STATUS_AGENT_CODE,
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
            .first()
        )
        return row is not None
    except Exception:  # noqa: BLE001 - fail closed, never leak on an error
        logger.warning(
            "Clearance entitlement lookup failed for contact %s; treating as not "
            "entitled",
            contact_id,
            exc_info=True,
        )
        return False


def user_is_entitled(db: Session, user: Optional[Mapping[str, Any]]) -> bool:
    """Does this staff user's role hold the clearance permission?"""
    user_id = (user or {}).get("id")
    if not user_id:
        return False
    try:
        from app.services.user_service import UserPermissionService

        return bool(
            UserPermissionService(db).check_user_has_permission(
                str(user_id), CLEARANCE_PERMISSION
            )
        )
    except Exception:  # noqa: BLE001 - fail closed
        logger.warning(
            "Clearance permission lookup failed for user %s; treating as not "
            "entitled",
            user_id,
            exc_info=True,
        )
        return False


def is_entitled(
    db: Session,
    *,
    current_user: Optional[Mapping[str, Any]] = None,
    contact_id: Optional[str] = None,
) -> bool:
    """Entitlement for this call.

    When a ``contact_id`` is supplied the answer is ABOUT that contact, so the
    contact's grant decides it - the API key acting as a privileged user must not
    launder a contact's question into a privileged answer. Only with no contact in
    play does the staff permission apply.
    """
    if contact_id:
        return contact_is_entitled(db, contact_id)
    return user_is_entitled(db, current_user)


def strip_clearance(payload: Any) -> Any:
    """Remove every clearance key, recursively, in place-safe fashion.

    Returns a NEW structure; the caller's dicts are never mutated, because the
    same row objects can be shared with a cache or another response.
    """
    if isinstance(payload, dict):
        return {
            key: strip_clearance(value)
            for key, value in payload.items()
            if key not in CLEARANCE_KEYS
        }
    if isinstance(payload, list):
        return [strip_clearance(item) for item in payload]
    return payload


def apply_clearance_gate(
    db: Session,
    payload: Any,
    *,
    current_user: Optional[Mapping[str, Any]] = None,
    contact_id: Optional[str] = None,
) -> Any:
    """Return the payload as this caller is allowed to see it."""
    if is_entitled(db, current_user=current_user, contact_id=contact_id):
        return payload
    return strip_clearance(payload)
