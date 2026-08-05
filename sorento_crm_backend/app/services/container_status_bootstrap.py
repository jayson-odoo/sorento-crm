"""Container-status startup bootstrap.

Seeds the ``container_status_enquiries`` access agent so an admin has something to
grant on the day this ships. Without it the entitlement gate is a permission
nobody can hold, which is indistinguishable from a broken feature - and the
implementer, not the admin, owns getting it there.

Deliberately seeded **inactive-by-default in effect**: the agent row exists and is
active, but NO contact holds it. Nothing becomes visible until an admin grants it
per contact, which is the point of the gate.

No `agent_mcp_tools` wiring is needed here. `crm_incoming_stock_list` is an
existing tool that existing agents already own; this slice adds fields to its
response and gates them server-side, rather than adding a new tool that would need
assigning. See `app.services.clearance_entitlement`.

Idempotent: an existing row is left exactly as the admin last edited it.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from app.models.access import AccessAgent
from app.services.clearance_entitlement import CONTAINER_STATUS_AGENT_CODE

logger = logging.getLogger(__name__)

AGENT_NAME = "Container status enquiries"
AGENT_DESCRIPTION = (
    "Lets a contact be told container clearance dates - ETA delay, CIDB "
    "inspection and approval, gatepass. Without this grant those fields are "
    "absent from the answer entirely, not blank."
)


def run(db: Session) -> dict:
    summary = {"agent_seeded": False}
    try:
        existing = (
            db.query(AccessAgent)
            .filter(AccessAgent.code == CONTAINER_STATUS_AGENT_CODE)
            .one_or_none()
        )
        if existing is not None:
            return summary

        db.add(
            AccessAgent(
                id=str(uuid.uuid4()),
                code=CONTAINER_STATUS_AGENT_CODE,
                name=AGENT_NAME,
                description=AGENT_DESCRIPTION,
                is_active=True,
                # NOT auto-assigned to new internal contacts. Clearance dates are
                # opt-in per contact; a default-on grant would defeat the gate.
                assign_to_new_internal_contacts=False,
            )
        )
        db.commit()
        summary["agent_seeded"] = True
        logger.info("Seeded access agent %s", CONTAINER_STATUS_AGENT_CODE)
    except Exception:  # noqa: BLE001 - a failed bootstrap must not stop startup
        db.rollback()
        logger.exception("Container status bootstrap failed; will retry next startup")
    return summary
