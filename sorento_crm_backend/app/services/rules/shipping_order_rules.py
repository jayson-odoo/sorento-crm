"""Shipping-order (SPO) rules shared by every writer of `spo_allocations` (D6,
D7, S3): the SPO xlsx import (`app/tasks/import_tasks.process_spo_import` via
`SPOAllocationService.upsert_allocation`/`create_allocation`) and the ESB's
`ShippingOrderIngestService`. Lifted out rather than duplicated, so a
container number or a received-quantity guard cannot work on one writer and
not the other.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
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


def link_allocation_to_shipment(
    db: Session, allocation, container: Optional[str], *, company_id: Optional[str] = None
) -> bool:
    """Stores `container` on `allocation` and links `inbound_shipment_id` when
    a shipment with that container exists (D6). Returns whether it linked -
    the caller warns `container_unresolved` on `False` rather than failing:
    a shipping order can exist before anybody books a container for it.

    `container` is expected already cleaned (`extract_container_number`'s
    output) - this function does not clean it again, so a caller comparing
    its own copy against what landed sees the same value.

    `company_id` (security review, ingest-parity-standardisation, should-fix
    3): a container number is not globally unique, and the ESB push always
    knows its own company - passed here so the shipment lookup cannot bind an
    allocation to a DIFFERENT company's shipment sharing the same container.
    """
    allocation.container_number = container
    if not container:
        return False
    from app.api.v1.external.utils import get_inbound_shipment_by_container_number

    shipment = get_inbound_shipment_by_container_number(db, container, company_id=company_id)
    if shipment is None:
        return False
    allocation.inbound_shipment_id = shipment.id
    return True


def relink_allocations_for_container(
    db: Session, container: Optional[str], *, company_id: Optional[str] = None
) -> int:
    """Fills `inbound_shipment_id` on every allocation of `container` that has
    none yet (D6) - a nightly sweep or an on-shipment-create hook, for the
    allocation that was written before its shipment existed. Returns the
    count relinked.

    `company_id` (security review, should-fix 3): scopes BOTH the shipment
    lookup and the allocation query - the external packing-list route can run
    with scope `None` when the attachment names no company, and without this
    a container shared by two companies would relink company B's allocations
    to company A's shipment (or vice versa). Callers always know their own
    company (`_relink_allocations_for_shipment` passes `shipment.company_id`;
    the ESB write passes its own anchor), so this is never optional in
    practice even though the parameter itself stays optional for the pure
    xlsx / nightly-sweep callers that predate company scoping here.
    """
    if not container:
        return 0
    from app.api.v1.external.utils import get_inbound_shipment_by_container_number
    from app.models.procurement import SPOAllocation

    shipment = get_inbound_shipment_by_container_number(db, container, company_id=company_id)
    if shipment is None:
        return 0
    query = db.query(SPOAllocation).filter(
        SPOAllocation.container_number == container,
        SPOAllocation.inbound_shipment_id.is_(None),
    )
    if company_id:
        query = query.filter(SPOAllocation.company_id == company_id)
    rows = query.all()
    for row in rows:
        row.inbound_shipment_id = shipment.id
    if rows:
        db.flush()
    return len(rows)


def nightly_relink_all_containers(db: Session) -> int:
    """S5 (review re-check, 2026-09-06): the nightly sweep the docstring above
    already promised, actually built. Finds every (company, container) pair
    with at least one allocation still unlinked, and relinks it - a
    shipment created AFTER its allocations were pushed never otherwise gets
    picked up again. Per-pair, through the same company-scoped
    `relink_allocations_for_container` every other caller uses, so a
    container shared by two companies still cannot cross-link.
    """
    from app.models.procurement import SPOAllocation

    pairs = (
        db.query(SPOAllocation.company_id, SPOAllocation.container_number)
        .filter(
            SPOAllocation.inbound_shipment_id.is_(None),
            SPOAllocation.container_number.isnot(None),
        )
        .distinct()
        .all()
    )
    relinked = 0
    for company_id, container in pairs:
        relinked += relink_allocations_for_container(db, container, company_id=company_id)
    return relinked


def received_guard(
    allocation, new_allocated: int, new_received: Optional[int] = None
) -> str:
    """Whether `new_allocated`/`new_received` may be written onto `allocation` (D7).

    An allocation with `quantity_received > 0` may never be reduced below
    it - the receipt already happened, and shrinking the promise under it
    would make a real, already-drawn quantity read as never having been
    ordered. Same rule `SPOAllocationService.upsert_allocation`'s
    `AllocationReceivedGuardError` already enforces on the xlsx path; shared
    here so the ESB push cannot enforce a different one.

    `new_received` (security review, blocker 1): the xlsx path never writes
    `quantity_received` on update, so the original single-argument guard only
    ever needed to protect `allocated_quantity`. The ESB push DOES write
    `quantity_received` on every record, straight from the payload's own
    `qty_received` - so a re-push with `qty_received=0` against a row that
    already shows `quantity_received=5` erased the receipt outright even
    though `allocated_quantity` never moved. Optional and defaults to `None`
    so the xlsx caller (`procurement_service.upsert_allocation`), which never
    touches this column, is unaffected.
    """
    received = int(getattr(allocation, "quantity_received", 0) or 0)
    if new_allocated < received:
        return GUARD_RECEIVED_LOCKED
    if new_received is not None and new_received < received:
        return GUARD_RECEIVED_LOCKED
    return GUARD_OK


# ---------------------------------------------------------------------------
# D25/D26/D27 (spo-xlsx-supersede): the xlsx-era row set vs the AutoCount
# line-set on a document's FIRST push.
#
# ONE algorithm, two writers. The planning half is pure and lives here so the
# ESB push (`ShippingOrderIngestService._supersede_xlsx_rows`, which CREATES
# the incoming lines) and the one-off dedupe
# (`scripts/dedupe_spo_xlsx_superseded.py`, which UPDATES ref rows a push has
# already appended) cannot drift: the two differ only in whether the line each
# plan speaks for is a new row or an existing one.
# ---------------------------------------------------------------------------

#: `(product_id, upper(location_code))` - the pair the xlsx upload itself
#: dedups on (`outstanding_import_service._spo_line_plans`), and therefore the
#: only pair that can pair an xlsx AGGREGATE row with the N AutoCount lines it
#: stands for.
SupersedeKey = tuple[Optional[str], Optional[str]]


@dataclass(frozen=True)
class SupersedeLinePlan:
    """One incoming line of a superseded group.

    `index` is its position in the `incoming` sequence the caller passed, so
    the caller can map it back to whatever it holds there (a `values` dict on
    the push, an existing `SPOAllocation` on the dedupe).
    """

    index: int
    carried_received: int
    inbound_shipment_id: Optional[str]


@dataclass(frozen=True)
class SupersedeGroupPlan:
    """One `(product, location)` group that HAS an incoming counterpart.

    `lines` is in AutoCount Seq order, so `lines[0]` is the repoint target
    (D27) and the last entry is the one any receipt remainder lands on (D26).
    """

    key: SupersedeKey
    lines: tuple[SupersedeLinePlan, ...]
    superseded_row_ids: tuple[str, ...]


@dataclass(frozen=True)
class SupersedePlan:
    """`groups` are superseded (rows repointed then removed); `kept_row_ids`
    are the ref-less rows AutoCount names no line for at all, which D27
    leaves alone for the ordinary leftover sweep to close."""

    groups: tuple[SupersedeGroupPlan, ...]
    kept_row_ids: tuple[str, ...]


def supersede_group_key(product_id, location_code: Optional[str]) -> SupersedeKey:
    """The D26 grouping pair, normalised the same way `_adopt_lines` normalises
    its own coarse key - a location is compared upper-cased and a blank one is
    `None`, never `''`."""
    location = (location_code or "").strip().upper() or None
    return (str(product_id) if product_id else None, location)


def carried_received(
    allocated: int, incoming_received: Optional[int], carried: Optional[int]
) -> tuple[int, bool]:
    """`(quantity_received, is_closed)` for one line of a superseded group (D26).

    The receipt is whichever side states more - the carry off the xlsx row
    (a Sorento GRN that already happened) or what AutoCount itself reports
    (its own TransferedQty, which lags until the transfer is keyed there).
    `is_closed` is the single test both `line_status` and `receipt_status`
    hang off, so the two can never disagree.
    """
    received = max(int(incoming_received or 0), int(carried or 0))
    return received, received >= int(allocated or 0)


def plan_xlsx_supersede(incoming, refless_rows) -> SupersedePlan:
    """Plan D26/D27 for ONE document. Pure: reads, decides, writes nothing.

    `incoming` is a sequence of mappings carrying `product_id`,
    `location_code`, `allocated_quantity` and an optional `line_number`
    (AutoCount's Seq). `refless_rows` is the document's xlsx-era
    `SPOAllocation` rows (`source_ref IS NULL`), each read for `id`,
    `product_id`, `location_code`, `quantity_received`, `inbound_shipment_id`
    and `spo_line_number`.

    Per group with an incoming counterpart: the group's whole received
    quantity is distributed across its lines in Seq order, each line up to
    its own `allocated_quantity`, and any remainder onto the LAST line - a
    stale upload can state a smaller line-set than AutoCount does, and a
    receipt that physically arrived may not be dropped just because no line
    has room left for it.
    """
    ordered_rows = sorted(
        refless_rows,
        key=lambda r: (
            r.spo_line_number if r.spo_line_number is not None else 10**9,
            str(r.id),
        ),
    )
    incoming = list(incoming)
    # Same convention as `_adopt_lines._position`: Seq is authoritative only
    # when EVERY line of the document carries one, otherwise payload order is
    # the only order there is.
    all_have_seq = bool(incoming) and all(
        line.get("line_number") is not None for line in incoming
    )

    lines_by_key: dict[SupersedeKey, list[int]] = {}
    for index, values in enumerate(incoming):
        key = supersede_group_key(values.get("product_id"), values.get("location_code"))
        lines_by_key.setdefault(key, []).append(index)
    for indexes in lines_by_key.values():
        indexes.sort(key=lambda i: incoming[i]["line_number"] if all_have_seq else i)

    rows_by_key: dict[SupersedeKey, list] = {}
    for row in ordered_rows:
        key = supersede_group_key(row.product_id, row.location_code)
        rows_by_key.setdefault(key, []).append(row)

    groups: list[SupersedeGroupPlan] = []
    kept: list[str] = []
    for key, rows in rows_by_key.items():
        indexes = lines_by_key.get(key)
        if not indexes:
            # D27: AutoCount lists no line for this product + location, so
            # there is nothing to supersede it WITH. Kept, links untouched.
            kept.extend(str(row.id) for row in rows)
            continue
        group_received = sum(int(row.quantity_received or 0) for row in rows)
        group_shipment = next(
            (str(row.inbound_shipment_id) for row in rows if row.inbound_shipment_id), None
        )
        remaining = group_received
        line_plans: list[SupersedeLinePlan] = []
        for position, index in enumerate(indexes):
            allocated = int(incoming[index].get("allocated_quantity") or 0)
            is_last = position == len(indexes) - 1
            take = remaining if is_last else min(remaining, max(allocated, 0))
            take = max(take, 0)
            remaining -= take
            line_plans.append(
                SupersedeLinePlan(
                    index=index, carried_received=take, inbound_shipment_id=group_shipment
                )
            )
        groups.append(
            SupersedeGroupPlan(
                key=key,
                lines=tuple(line_plans),
                superseded_row_ids=tuple(str(row.id) for row in rows),
            )
        )
    return SupersedePlan(groups=tuple(groups), kept_row_ids=tuple(kept))


def repoint_allocation_dependants(
    db: Session,
    from_ids,
    to_id: str,
    *,
    company_id: Optional[str] = None,
    dry_run: bool = False,
) -> int:
    """Move every row pointing at `from_ids` onto `to_id` (D27), and say how many.

    The three tables that name an allocation - `picking_lines` (a GRN's pick),
    `scm.order_link_claim` (an SO<->SPO pairing) and
    `projects.order_inquiry_links` (a placement) - all carry
    `ON DELETE SET NULL`, so a superseded row that is simply deleted would
    silently strip a real receipt's pairing instead of moving it. Enumerated
    ONCE here rather than at each writer, and through the ORM models so the
    ambient company scope applies exactly as it does to every other read.

    `dry_run` counts what WOULD move without touching a row - the dedupe
    script's preview needs the same enumeration, and a second copy of it is
    how the two would come to disagree.
    """
    from app.models.procurement import PickingLine
    from app.models.project_so import OrderInquiryLink
    from app.models.scm import OrderLinkClaim

    ids = [str(value) for value in from_ids if value]
    if not ids:
        return 0
    moved = 0
    for model in (PickingLine, OrderLinkClaim, OrderInquiryLink):
        query = db.query(model).filter(model.spo_allocation_id.in_(ids))
        if company_id:
            query = query.filter(model.company_id == company_id)
        rows = query.all()
        for row in rows:
            if not dry_run:
                row.spo_allocation_id = to_id
            moved += 1
    if moved and not dry_run:
        # Flushed HERE, before the caller deletes the superseded rows: the
        # UPDATE has to reach the database ahead of the DELETE or the FK's
        # `SET NULL` wins the race and the pairing is lost anyway.
        db.flush()
    return moved
