"""`inbound_shipment` as a status entity - the first adopter in this repo.

**This is a timeline of checkpoints, not a single current status.**

A container does not walk a straight line. The real workbook has containers with a
gatepass and no inspection, an ETA delay and no ETA, a collection with no warehouse
arrival. Forcing them onto one `status_id` would mean either inventing a position
the sheet never recorded, or silently implying that every earlier stage completed.
So there is deliberately **no `status_id` column on `inbound_shipments`**: each
checkpoint is reached, or it is not, independently, and the UI shows all of them.

What the status engine is used for, then, is the CONFIGURATION - which checkpoints
exist, what they are called, what order they appear in, what colour they are, and
whether they are shown at all. All of that becomes admin-editable rows in
`statuses` (System Management -> Status Graphs) instead of a hardcoded array in a
React component.

The mapping needs no new schema:

    statuses.key         the `inbound_shipments` date column this checkpoint reads
    statuses.label       what the timeline shows
    statuses.description the muted caption ("48h after gatepass")
    statuses.category    which group it belongs to (origin / sea / clearance / delivery)
    statuses.sort_order  timeline order
    statuses.color_hex   the dot colour once reached
    statuses.is_active   uncheck to hide a checkpoint entirely

`key` is frozen on update by the statuses API, which is what makes it safe to use
as the column contract: an admin can rename "Gatepass" to "Released from port"
without breaking the link to `gatepass_date`.

`migrate_records` is meaningless here - a checkpoint cannot be migrated, only
deleted once no container has reached it - so it reports 0 and the admin's
block-delete-if-referenced flow does the rest.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.procurement import InboundShipment
from app.status_engine.registry import StatusEntity, register_status_entity

logger = logging.getLogger(__name__)

ENTITY_TYPE = "inbound_shipment"

#: Checkpoint groups, in timeline order. Mirrors the sheet's own chain.
CATEGORIES = ("origin", "sea", "clearance", "delivery")


def _date_column_for(db: Session, status_id: str) -> Optional[str]:
    """The `inbound_shipments` column a checkpoint reads, via its frozen key."""
    from app.models.status import Status

    row = (
        db.query(Status)
        .filter(Status.id == status_id, Status.entity_type == ENTITY_TYPE)
        .first()
    )
    key = getattr(row, "key", None)
    if not key:
        return None
    return key if key in InboundShipment.__table__.columns else None


def count_records(db: Session, status_id: str) -> int:
    """How many containers have REACHED this checkpoint.

    Not "how many are at this status" - there is no such thing here. This is what
    the admin sees before deleting a checkpoint, and a non-zero count is what stops
    them deleting one that containers have already passed.
    """
    column = _date_column_for(db, status_id)
    if column is None:
        return 0
    return (
        db.query(InboundShipment)
        .filter(getattr(InboundShipment, column).isnot(None))
        .count()
    )


def migrate_records(db: Session, from_status_id: str, to_status_id: str) -> int:
    """No-op by design.

    Migrating records between statuses assumes a record HAS one status. Moving
    every container's gatepass date onto an inspection date would be data
    corruption, not a migration, so this reports 0 and the admin is left with
    "delete only when nothing has reached it".
    """
    return 0


def register() -> None:
    register_status_entity(
        StatusEntity(
            entity_type=ENTITY_TYPE,
            label="Container checkpoint",
            module="procurement",
            count_records=count_records,
            migrate_records=migrate_records,
            model=InboundShipment,
            record_label_attr="shipping_container_number",
            # Deliberately no `fact_attrs` and no transitions: nothing auto-advances
            # a checkpoint. A checkpoint is reached because its date is filled, which
            # the import writes directly, so there is no edge to evaluate.
        )
    )
    logger.info("Status entity registered: %s (checkpoint timeline)", ENTITY_TYPE)
