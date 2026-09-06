"""Shipping-order (SPO) rules shared by every writer of `spo_allocations` (D6,
D7, S3): the SPO xlsx import (`app/tasks/import_tasks.process_spo_import` via
`SPOAllocationService.upsert_allocation`/`create_allocation`) and the ESB's
`ShippingOrderIngestService`. Lifted out rather than duplicated, so a
container number or a received-quantity guard cannot work on one writer and
not the other.
"""
from __future__ import annotations

import re
from typing import Optional

from sqlalchemy.orm import Session

#: A real ISO 6346 container number: four letters, seven digits. Preferred
#: over "the text after the first space" (the SPO xlsx Loading Date cell's
#: own original rule) because that rule is wrong on both real shapes it has
#: to handle: "F-WHSU8488069 (MOCHA)" (the token is not after the first
#: space at all - it is prefixed and trailed by other text) and a bare
#: "TRHU4104785" (no space, so the old rule returns nothing).
_CONTAINER_RE = re.compile(r"\b([A-Za-z]{4}\d{7})\b")

#: Received-quantity guard verdicts (D7). A string rather than a bool/exception
#: because the two writers react to it differently: the xlsx path raises
#: `AllocationReceivedGuardError`, the ESB push instead leaves the line
#: unchanged and carries a `received_locked` warning on the record.
GUARD_OK = "ok"
GUARD_RECEIVED_LOCKED = "received_locked"


def extract_container_number(text: Optional[str]) -> Optional[str]:
    """The container number inside a free-text cell, or `None`.

    Handles every real shape the captain's own files carry: a leading `F-`
    marker, a trailing `(...)` note (a vessel/voyage name), and a container
    number that is not simply "the text after the first space" - the SPO
    xlsx Loading Date cell's own original rule, which this supersedes.
    """
    if not text:
        return None
    cleaned = text.strip()
    if not cleaned:
        return None
    if cleaned.upper().startswith("F-"):
        cleaned = cleaned[2:].strip()
    # Strip one trailing "(...)" group - a vessel/voyage note, never part of
    # the container number itself.
    cleaned = re.sub(r"\s*\([^)]*\)\s*$", "", cleaned).strip()
    if not cleaned:
        return None
    match = _CONTAINER_RE.search(cleaned)
    if match:
        return match.group(1).upper()
    # No token looks like a container - fall back to the original rule (text
    # after the first space) rather than giving up, since a format this
    # golden set has not seen yet still deserves a best-effort answer.
    if " " in cleaned:
        rest = cleaned.split(" ", 1)[1].strip()
        return rest.upper() or None
    return cleaned.upper() or None


def link_allocation_to_shipment(db: Session, allocation, container: Optional[str]) -> bool:
    """Stores `container` on `allocation` and links `inbound_shipment_id` when
    a shipment with that container exists (D6). Returns whether it linked -
    the caller warns `container_unresolved` on `False` rather than failing:
    a shipping order can exist before anybody books a container for it.

    `container` is expected already cleaned (`extract_container_number`'s
    output) - this function does not clean it again, so a caller comparing
    its own copy against what landed sees the same value.
    """
    allocation.container_number = container
    if not container:
        return False
    from app.api.v1.external.utils import get_inbound_shipment_by_container_number

    shipment = get_inbound_shipment_by_container_number(db, container)
    if shipment is None:
        return False
    allocation.inbound_shipment_id = shipment.id
    return True


def relink_allocations_for_container(db: Session, container: Optional[str]) -> int:
    """Fills `inbound_shipment_id` on every allocation of `container` that has
    none yet (D6) - a nightly sweep or an on-shipment-create hook, for the
    allocation that was written before its shipment existed. Returns the
    count relinked.
    """
    if not container:
        return 0
    from app.api.v1.external.utils import get_inbound_shipment_by_container_number
    from app.models.procurement import SPOAllocation

    shipment = get_inbound_shipment_by_container_number(db, container)
    if shipment is None:
        return 0
    rows = (
        db.query(SPOAllocation)
        .filter(
            SPOAllocation.container_number == container,
            SPOAllocation.inbound_shipment_id.is_(None),
        )
        .all()
    )
    for row in rows:
        row.inbound_shipment_id = shipment.id
    if rows:
        db.flush()
    return len(rows)


def received_guard(allocation, new_allocated: int) -> str:
    """Whether `new_allocated` may be written onto `allocation` (D7).

    An allocation with `quantity_received > 0` may never be reduced below
    it - the receipt already happened, and shrinking the promise under it
    would make a real, already-drawn quantity read as never having been
    ordered. Same rule `SPOAllocationService.upsert_allocation`'s
    `AllocationReceivedGuardError` already enforces on the xlsx path; shared
    here so the ESB push cannot enforce a different one.
    """
    received = int(getattr(allocation, "quantity_received", 0) or 0)
    if new_allocated < received:
        return GUARD_RECEIVED_LOCKED
    return GUARD_OK
