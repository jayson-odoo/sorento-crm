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

from sqlalchemy import or_
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
# D25/D25a/D26/D26a/D27 (spo-xlsx-supersede): the xlsx-era row set vs the
# AutoCount line-set, decided PER (product, location) GROUP.
#
# ONE algorithm, three writers. The planning half is pure and lives here so
# the ESB push (`ShippingOrderIngestService._supersede_xlsx_rows`, which
# CREATES the incoming lines), the one-off dedupe
# (`scripts/dedupe_spo_xlsx_superseded.py`, which UPDATES ref rows a push has
# already appended) and the D28a group recompute
# (`PickingHeaderService`, which redistributes a GRN total over the same
# group) cannot drift.
# ---------------------------------------------------------------------------

#: `(product_id, upper(location_code))` - the pair the xlsx upload itself
#: dedups on (`outstanding_import_service._spo_line_plans`), and therefore the
#: only pair that can pair an xlsx AGGREGATE row with the N AutoCount lines it
#: stands for.
SupersedeKey = tuple[Optional[str], Optional[str]]

#: D25a: the ONLY `source_system` a supersede candidate may carry. A ref-less
#: row written by the CRM UI or the n8n packing-list route carries NULL and is
#: never an xlsx-era aggregate, so it keeps the adoption path and is never
#: removed.
XLSX_SOURCE_SYSTEM = "scm_upload"

#: D28a: the `source_system` whose rows are recomputed as a GROUP rather than
#: one allocation at a time - an AutoCount line is one of N lines standing for
#: what used to be a single aggregated row, so the group's receipt is the only
#: figure a GRN draw against any of them measures.
AUTOCOUNT_SOURCE_SYSTEM = "autocount"


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
    `dropped_shipment_ids` (D26a) are the OTHER shipments the group's xlsx
    rows named: the supersede proceeds with the first and the writer warns
    `shipment_merged` and logs these, rather than silently picking one.
    """

    key: SupersedeKey
    lines: tuple[SupersedeLinePlan, ...]
    superseded_row_ids: tuple[str, ...]
    dropped_shipment_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SupersedeKeptGroup:
    """A ref-less group the supersede leaves alone, and why.

    `no_counterpart`: AutoCount lists no line for this product + location
    (D27) - kept and closed by the ordinary leftover rule.
    `received_locked`: D26a - the incoming lines' own allocated total is BELOW
    what this group already received, so replacing the rows with them would
    lose a receipt that physically arrived. The incoming lines are created as
    ordinary new rows instead and the record warns `received_locked`.
    """

    key: SupersedeKey
    row_ids: tuple[str, ...]
    reason: str


KEPT_NO_COUNTERPART = "no_counterpart"
KEPT_RECEIVED_LOCKED = "received_locked"


@dataclass(frozen=True)
class SupersedePlan:
    """`groups` are superseded (rows repointed, then removed or closed);
    `kept_groups` and `locked_groups` stay exactly where they are."""

    groups: tuple[SupersedeGroupPlan, ...]
    kept_groups: tuple[SupersedeKeptGroup, ...]
    locked_groups: tuple[SupersedeKeptGroup, ...]

    @property
    def kept_row_ids(self) -> tuple[str, ...]:
        """Every ref-less row this plan does NOT supersede, kept or locked."""
        return tuple(
            row_id
            for group in (*self.kept_groups, *self.locked_groups)
            for row_id in group.row_ids
        )

    @property
    def groups_kept(self) -> int:
        """GROUPS left alone, not rows (AC-X27) - the operator report's own unit."""
        return len(self.kept_groups) + len(self.locked_groups)


def supersede_group_key(product_id, location_code: Optional[str]) -> SupersedeKey:
    """The D26 grouping pair, normalised the same way `_adopt_lines` normalises
    its own coarse key - a location is compared upper-cased and a blank one is
    `None`, never `''`."""
    location = (location_code or "").strip().upper() or None
    return (str(product_id) if product_id else None, location)


def is_xlsx_era_row(row) -> bool:
    """D25a: whether `row` is an xlsx-era supersede candidate at all.

    A ref-less row alone is not enough: `source_system` NULL is the CRM UI /
    n8n packing-list shape, which states ONE line for one real line and has
    no aggregate to unpack, so it keeps the adoption path.
    """
    return not row.source_ref and (row.source_system or "") == XLSX_SOURCE_SYSTEM


def distribute_received(total: int, allocated: list[int]) -> list[int]:
    """Spread `total` across lines in order: each up to its own allocated
    quantity, any remainder onto the LAST line (D26, reused by D28a).

    The remainder rule is deliberate and shared by both callers: a stale
    upload can state a smaller line-set than AutoCount does, and a GRN can
    draw more than the lines it drew against are ordered for - a receipt that
    physically arrived may not be dropped just because no line has room left
    for it.
    """
    remaining = max(int(total or 0), 0)
    shares: list[int] = []
    for position, quantity in enumerate(allocated):
        is_last = position == len(allocated) - 1
        take = remaining if is_last else min(remaining, max(int(quantity or 0), 0))
        take = max(take, 0)
        remaining -= take
        shares.append(take)
    return shares


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
    """Plan D26/D26a/D27 for ONE document. Pure: reads, decides, writes nothing.

    `incoming` is a sequence of mappings carrying `product_id`,
    `location_code`, `allocated_quantity` and an optional `line_number`
    (AutoCount's Seq). `refless_rows` are the document's xlsx-era rows -
    already filtered to `is_xlsx_era_row` and to groups D25a still counts as
    xlsx-era by the caller, since only the caller can see which groups
    already hold a ref row.
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
    kept: list[SupersedeKeptGroup] = []
    locked: list[SupersedeKeptGroup] = []
    for key, rows in rows_by_key.items():
        row_ids = tuple(str(row.id) for row in rows)
        indexes = lines_by_key.get(key)
        if not indexes:
            # D27: AutoCount lists no line for this product + location, so
            # there is nothing to supersede it WITH. Kept, links untouched.
            kept.append(
                SupersedeKeptGroup(key=key, row_ids=row_ids, reason=KEPT_NO_COUNTERPART)
            )
            continue

        group_received = sum(int(row.quantity_received or 0) for row in rows)
        incoming_allocated = [
            int(incoming[index].get("allocated_quantity") or 0) for index in indexes
        ]
        if sum(incoming_allocated) < group_received:
            # D26a: the whole incoming line-set is smaller than what this
            # group already received. Replacing the rows with it would leave
            # the document reporting less than physically arrived, so the
            # group is refused and the caller warns `received_locked` - the
            # same verdict the by-ref and adoption paths already raise for
            # the same reason (`received_guard`).
            locked.append(
                SupersedeKeptGroup(key=key, row_ids=row_ids, reason=KEPT_RECEIVED_LOCKED)
            )
            continue

        shipment_ids: list[str] = []
        for row in rows:
            if row.inbound_shipment_id:
                value = str(row.inbound_shipment_id)
                if value not in shipment_ids:
                    shipment_ids.append(value)
        group_shipment = shipment_ids[0] if shipment_ids else None
        shares = distribute_received(group_received, incoming_allocated)
        line_plans = tuple(
            SupersedeLinePlan(
                index=index, carried_received=share, inbound_shipment_id=group_shipment
            )
            for index, share in zip(indexes, shares)
        )
        groups.append(
            SupersedeGroupPlan(
                key=key,
                lines=line_plans,
                superseded_row_ids=row_ids,
                # D26a: everything after the first is dropped, and saying so
                # is the point - a group whose rows named two containers
                # cannot keep both on one line.
                dropped_shipment_ids=tuple(shipment_ids[1:]),
            )
        )
    return SupersedePlan(
        groups=tuple(groups), kept_groups=tuple(kept), locked_groups=tuple(locked)
    )


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
    ONCE here rather than at each writer, and through the ORM models so a
    caller cannot reach the tables any other way.

    S4 (security review): a dependant's own `company_id` is NULLABLE on both
    link tables, and a NULL one belongs to this anchor's row just as much as a
    stamped one does. The read therefore runs under `company_scope(db, None)`
    with an EXPLICIT `company_id = anchor OR IS NULL` predicate: the ambient
    scope filter compiles to `company_id IN (anchor)`, which drops a NULL row
    silently, and an un-repointed `order_inquiry_links` row is not merely a
    lost pairing - `ck_order_inquiry_links_one_target` requires exactly one of
    its two targets to be set, so the FK's own `SET NULL` on the delete
    violates the CHECK and fails the whole push.

    `dry_run` counts what WOULD move without touching a row - the dedupe
    script's preview needs the same enumeration, and a second copy of it is
    how the two would come to disagree.
    """
    from app.models.base import company_scope
    from app.models.procurement import PickingLine
    from app.models.project_so import OrderInquiryLink
    from app.models.scm import OrderLinkClaim

    ids = [str(value) for value in from_ids if value]
    if not ids:
        return 0
    moved = 0
    with company_scope(db, None):
        for model in (PickingLine, OrderLinkClaim, OrderInquiryLink):
            query = db.query(model).filter(model.spo_allocation_id.in_(ids))
            if company_id:
                query = query.filter(
                    or_(model.company_id == company_id, model.company_id.is_(None))
                )
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
