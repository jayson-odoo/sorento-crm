"""Container-status startup bootstrap.

Keeps `agent_field_access` in step with the code registry: every field in
`field_access.GATED_FIELDS` gets a row on the agent that owns it, so an admin
opens the screen to a complete checklist rather than a list that silently omits
whatever was added after migration 313 ran.

**Seeded DENIED, except `DEFAULT_ALLOWED`.** A field nobody has reviewed must
not be readable, and the 53 contacts holding `incoming_stock_enquiries` must not
gain ETA delay and CIDB dates the moment this deploys. The row exists so the
field is visible and tickable; the tick is the admin's.

The exception is `estimated_arrival_date`: those contacts already ask about it
every day, so shipping a deny would REMOVE an answer rather than withhold a new
one. It is gated (revocable) but seeded allowed, which makes the deploy inert.

Existing rows are never touched - this only ever inserts what is missing, so a
restart cannot undo a deliberate grant or a per-contact override.

Idempotent, and a failure here must not stop startup: a missing row means one
field is invisible until the next boot, which is the safe direction.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.field_access import DEFAULT_ALLOWED, GATED_FIELDS

logger = logging.getLogger(__name__)


def run(db: Session) -> dict:
    summary = {"field_rows_seeded": 0}
    try:
        for resource, fields in GATED_FIELDS.items():
            for field_key, agent_code in fields.items():
                # The owning agent may not exist yet on a fresh install, and the FK
                # would reject the row. Skip rather than fail: the next boot after
                # the agent is seeded picks it up.
                agent_exists = db.execute(
                    text("SELECT 1 FROM access_agents WHERE code = :code"),
                    {"code": agent_code},
                ).scalar()
                if not agent_exists:
                    continue

                inserted = db.execute(
                    text(
                        """
                        INSERT INTO agent_field_access
                            (id, agent_code, resource, field_key, contact_id, is_allowed)
                        VALUES (:id, :agent, :resource, :field, NULL, :allowed)
                        ON CONFLICT DO NOTHING
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "agent": agent_code,
                        "resource": resource,
                        "field": field_key,
                        # Denied unless the field is one people already read today
                        # - see DEFAULT_ALLOWED. Seeding ETA denied would take away
                        # an answer the 53 contacts get right now.
                        "allowed": field_key in DEFAULT_ALLOWED,
                    },
                ).rowcount
                summary["field_rows_seeded"] += inserted or 0

        db.commit()
        if summary["field_rows_seeded"]:
            logger.info(
                "Seeded %s denied field-access rows", summary["field_rows_seeded"]
            )
    except Exception:  # noqa: BLE001 - a failed bootstrap must not stop startup
        db.rollback()
        logger.exception("Container status bootstrap failed; will retry next startup")
    return summary
