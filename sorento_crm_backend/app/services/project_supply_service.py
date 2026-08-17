"""Order promising: the supply composition sheet, and the one atomic confirmation.

Contract: `PLAN-scm-front-planning.md` sections 3.1 to 3.5 and 4,
`documentation/plans/scm/STAGE1C-scm-front-planning-promising.md` section 5, UAC groups B
and C.

The arithmetic is NOT here. It is the pure engine next door
(`app.services.scm.front_planning_engine`), so the rules can be tested without a database
and so the sheet and the commit cannot drift into two different opinions about the same
line. This file is everything around it: which facts are read, how the one location pile is
shared, what is rechecked at commit, and what is written.

Four ideas run through the whole file.

**Confirmation is at SO level and never per line** (3.1). The sheet is line-oriented
because CS inspects each line's composition, but there is no durable partial state: one
stale, unbalanced or unmapped line rolls back the whole transaction, and the refusal names
every failing line by line number and item code. No UUID ever appears in a message.

**Every fact is re-read at commit** (AC-C03). The sheet may have been open for an hour, and
the stock behind it moves. The payload is a proposal, not an instruction: open quantity, the
line's share of timely SPO, Reserve eligibility, the BRW cap, donor availability and product
lifecycle are all recomputed from authoritative rows before anything is written.

**Confirmed cover is not free** (AC-B13). Free stock is on hand, minus reserved, minus what
active decisions (and legacy confirmed allocations, which belong to no decision) already
hold. The order being composed is excluded from that subtraction, or its own previous
revision would compete with the one replacing it.

**One pile, one order of consumption** (3.5). Several lines can want the same product at the
same location, and which of them gets the stock and which gets the incoming is decided by
`attribute_sources`, once, for every outstanding line at that product and location - not by
whichever line the database happened to return first.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.inventory import Stock, Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.procurement import InboundShipment, SPOAllocation
from app.models.product import Product
from app.models.project_so import (
    ALLOC_SOURCE_BRW,
    ALLOC_SOURCE_ORDER,
    ALLOC_SOURCE_OTHER_LOCATION,
    ALLOC_SOURCE_OTHER_PROJECT,
    ALLOC_SOURCE_OWN,
    CLAIM_ACCEPTED,
    DECISION_ACTIVE,
    DECISION_CHALLENGED,
    DECISION_SUPERSEDED,
    SO_STATUS_AMENDED,
    SO_STATUS_PUBLISHED,
    AllocationClaim,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    SOLineAllocation,
    SOSupplyDecision,
)
from app.models.projects import Project
from app.models.scm import ItemClassification, ReorderLevel
from app.models.user import User
from app.services.error_handler import AppException
from app.services.scm.demand import is_open_demand
from app.services.scm.front_planning_engine import (
    BUY,
    RESERVE,
    TIMELY_SPO,
    Component,
    attribute_sources,
    propose_line,
    qty_text,
    reserve_capacity,
)

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")

#: The statuses a Project SO may be confirmed in. A draft has not left the building and a
#: blocked one has findings in the way.
CONFIRMABLE_STATUSES = (SO_STATUS_PUBLISHED, SO_STATUS_AMENDED)

#: The warehouse segment the hot-selling test is about (PLAN 3.3). Stored on the warehouse
#: row, never parsed out of a code.
DEALER_SEGMENT = "dealer"


def _dec(value: Any, default: Decimal = _ZERO) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


def _open_of(core: Optional[SalesOrderLine]) -> Decimal:
    """AC-B01: the core line's CURRENT open fulfilment quantity, floored at zero.

    Not the original customer quantity, and not a figure a downstream reader has already
    netted: what is still owed, in the line's own UOM.
    """
    if core is None:
        return _ZERO
    return max(_dec(core.qty_ordered) - _dec(core.qty_delivered), _ZERO)


class SupplyLinesRefused(AppException):
    """A refusal that names its lines (AC-C02).

    The envelope stays the shared one - `message` is what `extractApiError` reads - and
    `failing_lines` travels beside it, because a sentence cannot tell the sheet WHICH row
    to mark and a list of rows cannot be read out as a sentence.
    """

    def __init__(
        self,
        status_code: int,
        message: str,
        failing_lines: Sequence[Dict[str, Any]],
        code: str = "supply_lines_failed",
    ):
        super().__init__(status_code=status_code, message=message, code=code)
        self.detail["failing_lines"] = list(failing_lines)


@dataclass
class _SpoRow:
    spo_number: str
    spo_line_no: Optional[int]
    allocation_id: str
    arrival_date: Optional[date]
    qty: Decimal


@dataclass
class _LineFacts:
    """Everything one line is judged against, read live (AC-C03)."""

    line: ProjectSalesOrderLine
    core: Optional[SalesOrderLine]
    item_code: Optional[str] = None
    product_id: Optional[str] = None
    open_qty: Decimal = _ZERO
    required_date: Optional[date] = None
    warehouse: Optional[Warehouse] = None
    pool: Optional[Warehouse] = None
    #: This line's share of the fulfilment location's free stock, from the shared
    #: projection - NOT the whole pile, or two lines would each be offered all of it.
    own_free: Decimal = _ZERO
    pool_free: Decimal = _ZERO
    pool_reorder_level: Decimal = _ZERO
    is_hot_selling: bool = False
    classification_unavailable: bool = False
    is_discontinued: bool = False
    timely_qty: Decimal = _ZERO
    timely_refs: List[_SpoRow] = field(default_factory=list)
    advisory_refs: List[_SpoRow] = field(default_factory=list)

    @property
    def own_code(self) -> Optional[str]:
        return self.warehouse.warehouse_code if self.warehouse else None

    @property
    def pool_code(self) -> Optional[str]:
        return self.pool.warehouse_code if self.pool else None

    @property
    def pool_cap(self) -> Decimal:
        return max(self.pool_free - self.pool_reorder_level, _ZERO)


class _BorrowLedger:
    """What is still borrowable as one confirmation's lines are checked in turn.

    Two lines of the same Project SO can both name the same donor location, and each of
    them is checked against live figures - so without a running ledger both would pass and
    the same units would be promised twice inside one transaction. Seeded lazily from the
    live readers so nothing is queried for a location nobody borrows from.
    """

    def __init__(self) -> None:
        self._free: Dict[Tuple[str, str], Decimal] = {}
        self._held: Dict[Tuple[str, str, str], Decimal] = {}

    def free(self, product_id: Optional[str], warehouse_id: str, read) -> Decimal:
        key = (product_id or "", warehouse_id)
        if key not in self._free:
            self._free[key] = read(product_id, warehouse_id)
        return self._free[key]

    def take_free(self, product_id: Optional[str], warehouse_id: str, qty: Decimal) -> None:
        key = (product_id or "", warehouse_id)
        self._free[key] = max(self._free.get(key, _ZERO) - qty, _ZERO)

    def held(
        self, product_id: Optional[str], warehouse_id: str, donor_id: str, read
    ) -> Decimal:
        key = (product_id or "", warehouse_id, donor_id)
        if key not in self._held:
            self._held[key] = read(product_id, warehouse_id, donor_id)
        return self._held[key]

    def take_held(
        self, product_id: Optional[str], warehouse_id: str, donor_id: str, qty: Decimal
    ) -> None:
        key = (product_id or "", warehouse_id, donor_id)
        self._held[key] = max(self._held.get(key, _ZERO) - qty, _ZERO)


class ProjectSupplyService:
    """The supply sheet (`proposal_for`) and the atomic commit (`confirm`)."""

    def __init__(self, db: Session):
        self.db = db
        # Facts about THIS request, filled by `_facts_for` and read by the helpers below.
        # Per-request rather than per-call because one proposal asks the same "what is
        # free at that location" question once per line and once per borrow candidate.
        self._free_cache: Dict[Tuple[str, str], Decimal] = {}
        self._holds_cache: Dict[Tuple[str, str, str], Decimal] = {}

    # ------------------------------------------------------------------ lookups

    def get_order(self, pso_id: str) -> ProjectSalesOrder:
        order = (
            self.db.query(ProjectSalesOrder)
            .filter(ProjectSalesOrder.id == pso_id)
            .first()
        )
        if order is None:
            raise AppException(
                status_code=404, message="Sales order not found.", code="so_not_found"
            )
        return order

    def lines_of(self, pso_id: str) -> List[ProjectSalesOrderLine]:
        return (
            self.db.query(ProjectSalesOrderLine)
            .filter(ProjectSalesOrderLine.project_sales_order_id == pso_id)
            .order_by(ProjectSalesOrderLine.line_no.asc())
            .all()
        )

    def active_decision(self, pso_id: str) -> Optional[SOSupplyDecision]:
        return (
            self.db.query(SOSupplyDecision)
            .filter(
                SOSupplyDecision.project_sales_order_id == pso_id,
                SOSupplyDecision.state == DECISION_ACTIVE,
            )
            .first()
        )

    def latest_decision(self, pso_id: str) -> Optional[SOSupplyDecision]:
        return (
            self.db.query(SOSupplyDecision)
            .filter(SOSupplyDecision.project_sales_order_id == pso_id)
            .order_by(SOSupplyDecision.revision_no.desc())
            .first()
        )

    # -------------------------------------------------------------- the sheet

    def proposal_for(self, order: ProjectSalesOrder) -> Dict[str, Any]:
        """The Supply composition section for one Project SO (J04).

        Reads live facts, challenges an active revision that no longer matches them, and
        proposes a composition per line with the reason beside every quantity.
        """
        lines = self.lines_of(str(order.id))
        self.challenge_if_drifted(order, lines=lines)
        decision = self.active_decision(str(order.id))
        facts = self._facts_for(order, lines)

        frozen = self._frozen_by_line(decision)
        pool_left: Dict[str, Decimal] = {}
        payload_lines: List[Dict[str, Any]] = []
        for line in lines:
            fact = facts[str(line.id)]
            pool_key = str(fact.pool.id) if fact.pool else ""
            if pool_key and pool_key not in pool_left:
                pool_left[pool_key] = fact.pool_free
            free_stock: Dict[str, Decimal] = {}
            if fact.own_code:
                free_stock[fact.own_code] = fact.own_free
            if fact.pool_code:
                free_stock[fact.pool_code] = pool_left.get(pool_key, _ZERO)

            components = propose_line(
                open_qty=fact.open_qty,
                line_no=line.line_no,
                required_date=fact.required_date,
                fulfilment_location=fact.own_code,
                is_dealer_hot_selling=fact.is_hot_selling,
                free_stock=free_stock,
                pool_location=fact.pool_code,
                reorder_levels=(
                    {fact.pool_code: fact.pool_reorder_level} if fact.pool_code else {}
                ),
                timely_spo_qty=fact.timely_qty,
                timely_spo_refs=[
                    {
                        "spo_number": ref.spo_number,
                        "spo_line_no": ref.spo_line_no,
                        "arrival_date": ref.arrival_date,
                        "qty": ref.qty,
                    }
                    for ref in fact.timely_refs
                ],
                is_discontinued=fact.is_discontinued,
            )
            if pool_key and fact.pool_code:
                drawn = sum(
                    (
                        c.qty
                        for c in components
                        if c.kind == RESERVE and c.source_location == fact.pool_code
                    ),
                    _ZERO,
                )
                pool_left[pool_key] = max(pool_left.get(pool_key, _ZERO) - drawn, _ZERO)

            payload_lines.append(
                self._serialize_line(fact, components, frozen.get(str(line.id)))
            )

        header = self._header_fields(order)
        return {
            "project_sales_order_id": str(order.id),
            "provisional_ref": order.provisional_ref,
            "autocount_doc_no": order.autocount_doc_no,
            "project_id": str(order.project_id),
            "project_code": header.get("project_code"),
            "project_name": header.get("project_name"),
            "status": order.status,
            "review_state": self._review_state(order),
            "decision": self._serialize_decision(decision or self.latest_decision(str(order.id))),
            "lines": payload_lines,
        }

    def _serialize_line(
        self,
        fact: _LineFacts,
        components: Sequence[Component],
        frozen: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        line = fact.line
        return {
            "project_line_id": str(line.id),
            "line_no": line.line_no,
            "item_code": fact.item_code,
            "description": line.description,
            "uom": line.uom,
            "open_qty": qty_text(fact.open_qty),
            "required_date": fact.required_date,
            "fulfilment_location": fact.own_code,
            "is_dealer_hot_selling": fact.is_hot_selling,
            "classification_unavailable": fact.classification_unavailable,
            "is_discontinued": fact.is_discontinued,
            "pool_location": fact.pool_code,
            "pool_cap": qty_text(fact.pool_cap) if fact.pool_code else None,
            "pool_reorder_level": (
                qty_text(fact.pool_reorder_level) if fact.pool_code else None
            ),
            "components": [
                self._serialize_component(component, fact) for component in components
            ],
            "timely_spo": [self._serialize_spo(ref) for ref in fact.timely_refs],
            "advisory_spo": [self._serialize_spo(ref) for ref in fact.advisory_refs],
            "borrow_candidates": self._borrow_candidates(fact),
            "frozen": frozen,
        }

    def _serialize_component(
        self, component: Component, fact: _LineFacts
    ) -> Dict[str, Any]:
        warehouse_id = None
        if component.source_location:
            if fact.own_code == component.source_location and fact.warehouse:
                warehouse_id = str(fact.warehouse.id)
            elif fact.pool_code == component.source_location and fact.pool:
                warehouse_id = str(fact.pool.id)
        return {
            "kind": component.kind,
            "qty": qty_text(component.qty),
            "reason": component.reason,
            "source_location": component.source_location,
            "source_warehouse_id": warehouse_id,
        }

    def _serialize_spo(self, ref: _SpoRow) -> Dict[str, Any]:
        return {
            "spo_number": ref.spo_number,
            "arrival_date": ref.arrival_date,
            "qty": qty_text(ref.qty),
        }

    def _frozen_by_line(
        self, decision: Optional[SOSupplyDecision]
    ) -> Dict[str, Dict[str, Any]]:
        """What the active revision froze, so a confirmed line states what it was balanced
        against rather than the quantity that is live now."""
        if decision is None:
            return {}
        out: Dict[str, Dict[str, Any]] = {}
        for snapshot in decision.line_snapshots or []:
            line_id = str(snapshot.get("project_line_id") or "")
            if not line_id:
                continue
            out[line_id] = {
                "open_qty": str(snapshot.get("open_qty") or "0"),
                "components": list(snapshot.get("components") or []),
            }
        return out

    def _serialize_decision(
        self, decision: Optional[SOSupplyDecision]
    ) -> Optional[Dict[str, Any]]:
        if decision is None:
            return None
        name = None
        if decision.confirmed_by:
            user = (
                self.db.query(User.name).filter(User.id == decision.confirmed_by).first()
            )
            name = user[0] if user else None
        return {
            "revision_no": decision.revision_no,
            "state": decision.state,
            "confirmed_by_name": name,
            "confirmed_at": decision.confirmed_at,
            "challenged_reason": (
                decision.superseded_reason
                if decision.state == DECISION_CHALLENGED
                else None
            ),
        }

    def _review_state(self, order: ProjectSalesOrder) -> Optional[str]:
        from app.services.project_so_reconciliation_service import (
            ProjectSOReconciliationService,
        )

        states = ProjectSOReconciliationService(self.db).review_states_for([str(order.id)])
        return (states.get(str(order.id)) or {}).get("review_state")

    def _header_fields(self, order: ProjectSalesOrder) -> Dict[str, Any]:
        row = (
            self.db.query(Project.project_code, Project.title)
            .filter(Project.id == order.project_id)
            .first()
        )
        return {
            "project_code": row[0] if row else None,
            "project_name": row[1] if row else None,
        }

    # ------------------------------------------------------- supersede / challenge

    def supersede_for_material_change(
        self, order: ProjectSalesOrder, reason: str
    ) -> bool:
        """AC-C06: a material change retires the active revision, with no replacement.

        The whole SO goes back to Needs CS review. Nothing about the components is
        deleted: the superseded revision and its allocations stay for audit, and any Buy
        already placed stays in purchasing's ledger.
        """
        decision = self.active_decision(str(order.id))
        if decision is None:
            return False
        decision.state = DECISION_SUPERSEDED
        decision.superseded_at = datetime.utcnow()
        decision.superseded_reason = reason
        self.db.flush()
        return True

    def challenge_if_drifted(
        self,
        order: ProjectSalesOrder,
        *,
        lines: Optional[Sequence[ProjectSalesOrderLine]] = None,
    ) -> Optional[str]:
        """Compare the active revision's snapshots against live facts (PLAN 5.3).

        A revision is a statement about quantities, links and dates that were true when CS
        pressed Confirm. When one of them moves the revision is no longer a promise anybody
        can keep, so it is flipped to `challenged` and the SO reads Needs CS review again -
        rather than staying Confirmed against facts that have gone.
        """
        decision = self.active_decision(str(order.id))
        if decision is None:
            return None
        rows = list(lines if lines is not None else self.lines_of(str(order.id)))
        by_id = {str(line.id): line for line in rows}
        core_ids = [
            str(line.core_sales_order_line_id)
            for line in rows
            if line.core_sales_order_line_id
        ]
        cores = {
            str(core.id): core
            for core in (
                self.db.query(SalesOrderLine)
                .filter(SalesOrderLine.id.in_(core_ids))
                .all()
                if core_ids
                else []
            )
        }

        reason = None
        snapshots = decision.line_snapshots or []
        for snapshot in snapshots:
            line = by_id.get(str(snapshot.get("project_line_id") or ""))
            if line is None:
                reason = "A line the confirmed revision covered is no longer on this sales order."
                break
            frozen_core = snapshot.get("core_line_id")
            live_core = (
                str(line.core_sales_order_line_id)
                if line.core_sales_order_line_id
                else None
            )
            if frozen_core is not None and str(frozen_core) != (live_core or ""):
                reason = (
                    f"Line {line.line_no} now points at a different AutoCount line than "
                    "the confirmed revision did."
                )
                break
            core = cores.get(live_core or "")
            frozen_open = snapshot.get("open_qty")
            if frozen_open is not None and _dec(frozen_open) != _open_of(core):
                reason = (
                    f"Line {line.line_no} is now open for "
                    f"{qty_text(_open_of(core))}, and the confirmed revision was balanced "
                    f"against {qty_text(_dec(frozen_open))}."
                )
                break
            frozen_date = snapshot.get("required_date")
            live_date = core.required_date if core is not None else None
            if frozen_date is not None and str(frozen_date) != (
                live_date.isoformat() if live_date else ""
            ):
                reason = f"Line {line.line_no}'s required date has changed."
                break
        if len(snapshots) != len(rows) and reason is None:
            reason = (
                "This sales order no longer has the same lines the confirmed revision "
                "covered."
            )
        if reason is None:
            return None

        decision.state = DECISION_CHALLENGED
        decision.superseded_at = datetime.utcnow()
        decision.superseded_reason = reason
        self.db.flush()
        return reason

    # ---------------------------------------------------------------- the commit

    def confirm(
        self,
        order: ProjectSalesOrder,
        payload: Any,
        *,
        actor_user_id: str,
    ) -> Dict[str, Any]:
        """One transaction, every line, or nothing (PLAN 3.1, AC-C01).

        The caller owns the commit. Everything here runs inside it, including the Order
        Inquiry refresh, so purchasing can never be told to buy something that was not
        also promised.
        """
        locked = (
            self.db.query(ProjectSalesOrder)
            .filter(ProjectSalesOrder.id == order.id)
            .with_for_update()
            .first()
        )
        order = locked or order
        if order.status not in CONFIRMABLE_STATUSES:
            raise AppException(
                status_code=409,
                message=(
                    "This sales order is not published yet, so there is nothing to promise "
                    "supply against."
                ),
                code="supply_order_not_published",
            )

        lines = self.lines_of(str(order.id))
        by_id = {str(line.id): line for line in lines}
        payload_lines = list(getattr(payload, "lines", []) or [])
        self._lock_stock(payload_lines, lines)

        facts = self._facts_for(order, lines)
        item_codes = {
            str(line.id): facts[str(line.id)].item_code for line in lines
        }

        stale: List[Dict[str, Any]] = []
        invalid: List[Dict[str, Any]] = []
        seen: set = set()
        checked: List[Tuple[ProjectSalesOrderLine, Any, _LineFacts]] = []
        # What is still available as the payload is walked, so two lines of the SAME
        # confirmation cannot each be sold the whole pile. The per-line facts say what was
        # free when the sheet was read; these say what is left after the lines before it.
        pool_left: Dict[str, Decimal] = {}
        borrow_left: _BorrowLedger = _BorrowLedger()

        for entry in payload_lines:
            line = by_id.get(str(entry.project_line_id))
            if line is None:
                invalid.append(
                    {
                        "line_no": None,
                        "item_code": None,
                        "reason": "That line is not on this sales order any more.",
                    }
                )
                continue
            seen.add(str(line.id))
            fact = facts[str(line.id)]
            checked.append((line, entry, fact))
            self._check_line(entry, fact, pool_left, borrow_left, stale, invalid)

        for line in lines:
            if str(line.id) not in seen:
                invalid.append(
                    {
                        "line_no": line.line_no,
                        "item_code": item_codes.get(str(line.id)),
                        "reason": (
                            "This line has no composition. Every line is confirmed "
                            "together or none of them is."
                        ),
                    }
                )

        if invalid or stale:
            failing = invalid + stale
            raise SupplyLinesRefused(
                status_code=422 if invalid else 409,
                message=(
                    f"{len(failing)} line{'' if len(failing) == 1 else 's'} cannot be "
                    "confirmed. Nothing was written."
                ),
                failing_lines=failing,
            )

        return self._write_decision(order, checked, actor_user_id=actor_user_id)

    def _lock_stock(
        self,
        payload_lines: Sequence[Any],
        lines: Sequence[ProjectSalesOrderLine],
    ) -> None:
        """Lock every stock row the payload touches, in a deterministic order.

        Deterministic because two confirmations touching the same two locations in
        opposite orders deadlock, and a deadlock reads to CS as the button doing nothing.
        """
        product_ids = {str(line.product_id) for line in lines if line.product_id}
        warehouse_ids: set = set()
        for entry in payload_lines:
            for source in list(entry.reserve or []) + list(entry.borrow or []):
                if getattr(source, "warehouse_id", None):
                    warehouse_ids.add(str(source.warehouse_id))
        if not product_ids or not warehouse_ids:
            return
        (
            self.db.query(Stock)
            .filter(
                Stock.product_id.in_(list(product_ids)),
                Stock.warehouse_id.in_(list(warehouse_ids)),
            )
            .order_by(Stock.product_id.asc(), Stock.warehouse_id.asc())
            .with_for_update()
            .all()
        )

    def _check_line(
        self,
        entry: Any,
        fact: _LineFacts,
        pool_left: Dict[str, Decimal],
        borrow_left: "_BorrowLedger",
        stale: List[Dict[str, Any]],
        invalid: List[Dict[str, Any]],
    ) -> None:
        """Recheck one line against authoritative facts (PLAN 3.1 steps 3 to 5)."""
        line = fact.line
        subject = {"line_no": line.line_no, "item_code": fact.item_code}

        def refuse(bucket: List[Dict[str, Any]], reason: str) -> None:
            bucket.append({**subject, "reason": reason})

        if fact.core is None:
            refuse(
                invalid,
                "This line has no reconciled AutoCount line, so there is no open "
                "quantity to promise against.",
            )
            return

        timely = _dec(entry.timely_spo_qty)
        reserve_total = sum((_dec(item.qty) for item in entry.reserve or []), _ZERO)
        borrow_total = sum((_dec(item.qty) for item in entry.borrow or []), _ZERO)
        buy = _dec(entry.buy_qty)
        if min(timely, reserve_total, borrow_total, buy) < _ZERO:
            refuse(invalid, "A component quantity is negative.")
            return

        if timely > fact.timely_qty:
            refuse(
                stale,
                f"Timely SPO cover is now {qty_text(fact.timely_qty)}, not "
                f"{qty_text(timely)}.",
            )

        capacity = {
            location: qty
            for location, qty, _reason in reserve_capacity(
                is_dealer_hot_selling=fact.is_hot_selling,
                fulfilment_location=fact.own_code,
                pool_location=fact.pool_code,
                free_stock=self._free_for(fact, pool_left),
                reorder_levels=(
                    {fact.pool_code: fact.pool_reorder_level} if fact.pool_code else {}
                ),
            )
        }
        for item in entry.reserve or []:
            warehouse = self._warehouse_of(fact, str(item.warehouse_id))
            qty = _dec(item.qty)
            if warehouse is None or warehouse not in capacity:
                refuse(
                    invalid,
                    "Reserve may only come from this line's own location or the shared "
                    "pool. Move that quantity to Borrow.",
                )
                continue
            if qty > capacity[warehouse]:
                refuse(
                    stale,
                    f"{warehouse} now has {qty_text(capacity[warehouse])} free for this "
                    f"line, and {qty_text(qty)} was asked for.",
                )
                continue
            capacity[warehouse] -= qty
            if fact.pool_code and warehouse == fact.pool_code and fact.pool:
                pool_left[str(fact.pool.id)] = max(
                    pool_left.get(str(fact.pool.id), fact.pool_free) - qty, _ZERO
                )

        for item in entry.borrow or []:
            self._check_borrow(item, fact, borrow_left, refuse, stale, invalid)

        if fact.is_discontinued and buy > _ZERO and not (entry.buy_reason or "").strip():
            refuse(
                invalid,
                "This product is discontinued. Say why it is still being bought before "
                "confirming.",
            )

        total = timely + reserve_total + borrow_total + buy
        if total != fact.open_qty:
            refuse(
                invalid,
                f"The components add up to {qty_text(total)} and the line is open for "
                f"{qty_text(fact.open_qty)}.",
            )

    def _free_for(
        self, fact: _LineFacts, pool_left: Dict[str, Decimal]
    ) -> Dict[str, Decimal]:
        free: Dict[str, Decimal] = {}
        if fact.own_code:
            free[fact.own_code] = fact.own_free
        if fact.pool_code and fact.pool:
            free[fact.pool_code] = pool_left.get(str(fact.pool.id), fact.pool_free)
        return free

    def _warehouse_of(self, fact: _LineFacts, warehouse_id: str) -> Optional[str]:
        if fact.warehouse and str(fact.warehouse.id) == warehouse_id:
            return fact.own_code
        if fact.pool and str(fact.pool.id) == warehouse_id:
            return fact.pool_code
        return None

    def _check_borrow(
        self,
        item: Any,
        fact: _LineFacts,
        borrow_left: "_BorrowLedger",
        refuse,
        stale: List[Dict[str, Any]],
        invalid: List[Dict[str, Any]],
    ) -> None:
        qty = _dec(item.qty)
        if not (item.reason or "").strip():
            refuse(
                invalid,
                "Borrowing takes a reason. Say why this line is taking somebody else's "
                "stock.",
            )
            return
        warehouse = self._warehouse_row(str(item.warehouse_id))
        if warehouse is None:
            refuse(invalid, "That location no longer exists.")
            return
        if item.source == ALLOC_SOURCE_OTHER_LOCATION:
            if self._warehouse_of(fact, str(item.warehouse_id)) is not None:
                refuse(
                    invalid,
                    f"{warehouse.warehouse_code} is inside this line's Reserve pool. "
                    "Reserve it rather than borrowing it.",
                )
                return
            available = borrow_left.free(
                fact.product_id, str(warehouse.id), self._free_at
            )
            if qty > available:
                refuse(
                    stale,
                    f"{warehouse.warehouse_code} has {qty_text(available)} free, and "
                    f"{qty_text(qty)} was asked for.",
                )
                return
            borrow_left.take_free(fact.product_id, str(warehouse.id), qty)
            return

        if not item.donor_project_id:
            refuse(invalid, "Name the project this stock is being borrowed from.")
            return
        donor = (
            self.db.query(Project).filter(Project.id == item.donor_project_id).first()
        )
        if donor is None:
            refuse(invalid, "The project holding that stock no longer exists.")
            return
        # The donor's own hold first, then whatever is free at that location: both are
        # stock that exists, and neither may be handed to two lines of one confirmation.
        held = borrow_left.held(
            fact.product_id, str(warehouse.id), str(donor.id), self._held_at
        )
        free = borrow_left.free(fact.product_id, str(warehouse.id), self._free_at)
        if qty > held + free:
            refuse(
                stale,
                f"{donor.project_code} has {qty_text(held + free)} at "
                f"{warehouse.warehouse_code}, and {qty_text(qty)} was asked for.",
            )
            return
        from_hold = min(qty, held)
        borrow_left.take_held(fact.product_id, str(warehouse.id), str(donor.id), from_hold)
        borrow_left.take_free(fact.product_id, str(warehouse.id), qty - from_hold)

    # ------------------------------------------------------------------- writing

    def _write_decision(
        self,
        order: ProjectSalesOrder,
        checked: Sequence[Tuple[ProjectSalesOrderLine, Any, _LineFacts]],
        *,
        actor_user_id: str,
    ) -> Dict[str, Any]:
        previous = self.active_decision(str(order.id))
        if previous is not None:
            previous.state = DECISION_SUPERSEDED
            previous.superseded_at = datetime.utcnow()
            previous.superseded_reason = "Reconfirmed by CS."
            # Flushed on its own: the partial unique index allows one active revision, so
            # the new row cannot be inserted while the old one still says it is active.
            self.db.flush()

        latest = self.latest_decision(str(order.id))
        revision_no = (latest.revision_no if latest else 0) + 1
        now = datetime.utcnow()
        snapshots = [
            self._snapshot(line, entry, fact) for line, entry, fact in checked
        ]

        decision = SOSupplyDecision(
            company_id=order.company_id,
            project_sales_order_id=order.id,
            revision_no=revision_no,
            state=DECISION_ACTIVE,
            source_revision=(
                f"{order.status} @ "
                f"{order.updated_at.isoformat() if order.updated_at else ''}"
            )[:120],
            line_snapshots=snapshots,
            confirmed_by=actor_user_id,
            confirmed_at=now,
            supersedes_id=previous.id if previous else None,
        )
        self.db.add(decision)
        try:
            self.db.flush()
        except IntegrityError as exc:
            # The DB-level singleton did its job: somebody else confirmed this order
            # between our read and our write, so this attempt loses whole (AC-C05).
            self.db.rollback()
            raise AppException(
                status_code=409,
                message=(
                    "Somebody else confirmed this sales order while this composition was "
                    "open. Reload it and check the composition before confirming again."
                ),
                code="supply_decision_conflict",
            ) from exc

        buy_lines: List[Dict[str, Any]] = []
        for line, entry, fact in checked:
            self._write_allocations(decision, line, entry, fact, actor_user_id=actor_user_id)
            self._restamp_stock_location(line, entry, fact)
            buy_lines.append(
                {
                    "line": line,
                    "line_no": line.line_no,
                    "item_code": fact.item_code,
                    "buy_qty": _dec(entry.buy_qty),
                    "required_date": fact.required_date or line.delivery_date,
                    "stock_location": line.stock_location,
                }
            )
        self.db.flush()

        from app.services.project_order_inquiry_service import (
            ProjectOrderInquiryService,
        )

        handoff = ProjectOrderInquiryService(self.db).refresh_for_decision(
            order, decision, buy_lines, actor_user_id=actor_user_id
        )
        return {
            "revision_no": decision.revision_no,
            "confirmed_at": decision.confirmed_at,
            "review_state": "confirmed",
            "inquiry_rows_created": handoff["created"],
            "exceptions": handoff["exceptions"],
        }

    def _snapshot(
        self, line: ProjectSalesOrderLine, entry: Any, fact: _LineFacts
    ) -> Dict[str, Any]:
        """Freeze the line as it was decided, in the words it was decided in (AC-G01)."""
        components: List[Dict[str, Any]] = []
        for item in entry.reserve or []:
            qty = _dec(item.qty)
            if qty <= _ZERO:
                continue
            location = self._warehouse_of(fact, str(item.warehouse_id))
            components.append(
                {
                    "kind": RESERVE,
                    "qty": qty_text(qty),
                    "source_location": location,
                    "source_warehouse_id": str(item.warehouse_id),
                    "reason": self._reserve_reason(fact, location),
                }
            )
        if _dec(entry.timely_spo_qty) > _ZERO:
            components.append(
                {
                    "kind": TIMELY_SPO,
                    "qty": qty_text(_dec(entry.timely_spo_qty)),
                    "source_location": fact.own_code,
                    "reason": self._timely_reason(fact),
                }
            )
        for item in entry.borrow or []:
            qty = _dec(item.qty)
            if qty <= _ZERO:
                continue
            warehouse = self._warehouse_row(str(item.warehouse_id))
            donor = (
                self.db.query(Project).filter(Project.id == item.donor_project_id).first()
                if item.donor_project_id
                else None
            )
            components.append(
                {
                    "kind": "borrow",
                    "qty": qty_text(qty),
                    "source": item.source,
                    "source_location": warehouse.warehouse_code if warehouse else None,
                    "source_warehouse_id": str(item.warehouse_id),
                    "donor_project_ref": donor.project_code if donor else None,
                    "donor_project_id": str(donor.id) if donor else None,
                    "reason": self._borrow_reason(item, warehouse, donor),
                    "cs_reason": (item.reason or "").strip(),
                }
            )
        if _dec(entry.buy_qty) > _ZERO:
            components.append(
                {
                    "kind": BUY,
                    "qty": qty_text(_dec(entry.buy_qty)),
                    "reason": "remaining uncovered need",
                    "cs_reason": (entry.buy_reason or "").strip() or None,
                }
            )

        return {
            "line_no": line.line_no,
            "project_line_id": str(line.id),
            "core_line_id": str(line.core_sales_order_line_id)
            if line.core_sales_order_line_id
            else None,
            "product_id": fact.product_id,
            "item_code": fact.item_code,
            "location": fact.own_code,
            "required_date": (
                fact.required_date.isoformat() if fact.required_date else None
            ),
            "open_qty": qty_text(fact.open_qty),
            "timely_spo_qty": qty_text(_dec(entry.timely_spo_qty)),
            "timely_spo_refs": [
                {
                    "spo_number": ref.spo_number,
                    "arrival_date": (
                        ref.arrival_date.isoformat() if ref.arrival_date else None
                    ),
                    "qty": qty_text(ref.qty),
                }
                for ref in fact.timely_refs
            ],
            "reserve_qty": qty_text(
                sum((_dec(item.qty) for item in entry.reserve or []), _ZERO)
            ),
            "borrow_qty": qty_text(
                sum((_dec(item.qty) for item in entry.borrow or []), _ZERO)
            ),
            "buy_qty": qty_text(_dec(entry.buy_qty)),
            "components": components,
            "suggestion_basis": {
                "is_dealer_hot_selling": fact.is_hot_selling,
                "classification_unavailable": fact.classification_unavailable,
                "pool_location": fact.pool_code,
                "pool_cap": qty_text(fact.pool_cap) if fact.pool_code else None,
                "pool_reorder_level": (
                    qty_text(fact.pool_reorder_level) if fact.pool_code else None
                ),
            },
            "lifecycle_warning": (
                "This product is discontinued." if fact.is_discontinued else None
            ),
            "buy_reason": (entry.buy_reason or "").strip() or None,
        }

    def _reserve_reason(self, fact: _LineFacts, location: Optional[str]) -> str:
        for candidate, _qty, reason in reserve_capacity(
            is_dealer_hot_selling=fact.is_hot_selling,
            fulfilment_location=fact.own_code,
            pool_location=fact.pool_code,
            free_stock=self._free_for(fact, {}),
            reorder_levels=(
                {fact.pool_code: fact.pool_reorder_level} if fact.pool_code else {}
            ),
        ):
            if candidate == location:
                return reason
        return f"free stock at {location} covers the need by the required date"

    def _timely_reason(self, fact: _LineFacts) -> str:
        if not fact.timely_refs:
            return "incoming supply arrives by the required date"
        first = fact.timely_refs[0]
        when = first.arrival_date.isoformat() if first.arrival_date else "an unstated date"
        return f"SPO {first.spo_number} arrives on {when}, by the required date"

    def _borrow_reason(
        self, item: Any, warehouse: Optional[Warehouse], donor: Optional[Project]
    ) -> str:
        where = warehouse.warehouse_code if warehouse else "another location"
        if item.source == ALLOC_SOURCE_OTHER_PROJECT and donor is not None:
            return f"borrowed from {donor.project_code} at {where}"
        return f"borrowed from free stock at {where}"

    def _write_allocations(
        self,
        decision: SOSupplyDecision,
        line: ProjectSalesOrderLine,
        entry: Any,
        fact: _LineFacts,
        *,
        actor_user_id: str,
    ) -> None:
        """The components of THIS revision, grouped by `decision_id`.

        The previous revision's rows are left exactly where they are: they are the record
        of what was promised then, and the audit trail is the only thing that can answer
        "what did we tell the customer in March".
        """
        now = datetime.utcnow()
        for item in entry.reserve or []:
            qty = _dec(item.qty)
            if qty <= _ZERO:
                continue
            location = self._warehouse_of(fact, str(item.warehouse_id))
            source = (
                ALLOC_SOURCE_BRW
                if fact.pool_code and location == fact.pool_code
                else ALLOC_SOURCE_OWN
            )
            self.db.add(
                SOLineAllocation(
                    company_id=line.company_id,
                    so_line_id=line.id,
                    source_type=source,
                    warehouse_id=str(item.warehouse_id),
                    qty=qty,
                    decision_id=decision.id,
                    confirmed_by=actor_user_id,
                    confirmed_at=now,
                )
            )

        for item in entry.borrow or []:
            qty = _dec(item.qty)
            if qty <= _ZERO:
                continue
            claim_id = None
            donor_project_id = None
            if item.source == ALLOC_SOURCE_OTHER_PROJECT and item.donor_project_id:
                donor_project_id = str(item.donor_project_id)
                claim = AllocationClaim(
                    company_id=line.company_id,
                    from_project_id=self._project_id_of(line),
                    to_project_id=donor_project_id,
                    so_line_id=line.id,
                    product_id=fact.product_id,
                    warehouse_id=str(item.warehouse_id),
                    qty=qty,
                    # Straight to the terminal state (AC-B10): the confirming CS actor IS
                    # the approval, so there is no requested step for a donor to answer.
                    state=CLAIM_ACCEPTED,
                    reason=(item.reason or "").strip(),
                    requested_by=actor_user_id,
                    decided_by=actor_user_id,
                    decided_at=now,
                )
                self.db.add(claim)
                self.db.flush()
                claim_id = claim.id
            self.db.add(
                SOLineAllocation(
                    company_id=line.company_id,
                    so_line_id=line.id,
                    source_type=item.source,
                    warehouse_id=str(item.warehouse_id),
                    source_project_id=donor_project_id,
                    qty=qty,
                    claim_id=claim_id,
                    decision_id=decision.id,
                    reason=(item.reason or "").strip(),
                    donor_impact_snapshot=self._donor_impact(item, fact, qty),
                    confirmed_by=actor_user_id,
                    confirmed_at=now,
                )
            )

        buy = _dec(entry.buy_qty)
        if buy > _ZERO:
            self.db.add(
                SOLineAllocation(
                    company_id=line.company_id,
                    so_line_id=line.id,
                    source_type=ALLOC_SOURCE_ORDER,
                    warehouse_id=None,
                    qty=buy,
                    decision_id=decision.id,
                    reason=(entry.buy_reason or "").strip() or None,
                    confirmed_by=actor_user_id,
                    confirmed_at=now,
                )
            )

    def _project_id_of(self, line: ProjectSalesOrderLine) -> str:
        order = (
            self.db.query(ProjectSalesOrder.project_id)
            .filter(ProjectSalesOrder.id == line.project_sales_order_id)
            .first()
        )
        return str(order[0]) if order else ""

    def _donor_impact(self, item: Any, fact: _LineFacts, qty: Decimal) -> Dict[str, Any]:
        free = self._free_at(fact.product_id, str(item.warehouse_id))
        held = (
            self._held_at(fact.product_id, str(item.warehouse_id), str(item.donor_project_id))
            if item.donor_project_id
            else _ZERO
        )
        return {
            "free_before": qty_text(free + held),
            "free_after_full_borrow": qty_text(max(free + held - qty, _ZERO)),
            "committed_qty": qty_text(held),
        }

    def _restamp_stock_location(
        self, line: ProjectSalesOrderLine, entry: Any, fact: _LineFacts
    ) -> None:
        """AC-H5, from this revision's components: what the inquiry row quotes."""
        codes: List[str] = []
        for item in list(entry.reserve or []) + list(entry.borrow or []):
            if _dec(item.qty) <= _ZERO:
                continue
            warehouse = self._warehouse_row(str(item.warehouse_id))
            code = warehouse.warehouse_code if warehouse else None
            if code and code not in codes:
                codes.append(code)
        line.stock_location = " + ".join(codes) if codes else None

    # ------------------------------------------------------------------- facts

    def _facts_for(
        self, order: ProjectSalesOrder, lines: Sequence[ProjectSalesOrderLine]
    ) -> Dict[str, _LineFacts]:
        """Read every fact the sheet and the commit judge a line against.

        Refuses the whole order when a line has no reconciled core line: without it there
        is no current open quantity, and promising supply against the ORIGINAL customer
        quantity is exactly the double-count this contract exists to stop (PLAN 3.1 step 2).
        """
        unmapped = [line for line in lines if not line.core_sales_order_line_id]
        core_ids = [
            str(line.core_sales_order_line_id)
            for line in lines
            if line.core_sales_order_line_id
        ]
        cores = {
            str(row.id): row
            for row in (
                self.db.query(SalesOrderLine)
                .filter(SalesOrderLine.id.in_(core_ids))
                .all()
                if core_ids
                else []
            )
        }
        product_ids = {
            str(core.product_id)
            for core in cores.values()
            if core.product_id
        } | {str(line.product_id) for line in lines if line.product_id}
        codes = self._product_codes(product_ids)

        if unmapped:
            raise SupplyLinesRefused(
                status_code=422,
                message=(
                    f"{len(unmapped)} line{'' if len(unmapped) == 1 else 's'} "
                    "still has no AutoCount line. Reconcile the sales order first."
                ),
                failing_lines=[
                    {
                        "line_no": line.line_no,
                        "item_code": codes.get(str(line.product_id or "")),
                        "reason": "No reconciled AutoCount line.",
                    }
                    for line in unmapped
                ],
                code="supply_lines_unreconciled",
            )

        warehouse_ids = {
            str(core.warehouse_id) for core in cores.values() if core.warehouse_id
        }
        warehouses = self._warehouses(warehouse_ids)
        pool_ids = {
            str(w.pool_warehouse_id) for w in warehouses.values() if w.pool_warehouse_id
        }
        warehouses.update(self._warehouses(pool_ids - set(warehouses)))

        self._free_cache = self._free_stock(product_ids, exclude_order_id=str(order.id))
        self._holds_cache = self._holds_by_project(
            product_ids, exclude_order_id=str(order.id)
        )
        hot, unavailable = self._classification(product_ids)
        levels = self._reorder_levels(product_ids, pool_ids)
        discontinued = self._discontinued(product_ids)
        spo = self._spo_rows(product_ids, warehouse_ids)
        attribution = self._attribution(product_ids, warehouse_ids, warehouses, spo)

        facts: Dict[str, _LineFacts] = {}
        for line in lines:
            core = cores.get(str(line.core_sales_order_line_id or ""))
            product_id = str(core.product_id) if core and core.product_id else (
                str(line.product_id) if line.product_id else None
            )
            warehouse = (
                warehouses.get(str(core.warehouse_id))
                if core and core.warehouse_id
                else None
            )
            pool = (
                warehouses.get(str(warehouse.pool_warehouse_id))
                if warehouse and warehouse.pool_warehouse_id
                else None
            )
            key = (product_id or "", str(warehouse.id) if warehouse else "")
            shares = attribution.get(key, {}).get(str(core.id) if core else "", {})
            required_date = (core.required_date if core else None) or line.delivery_date
            timely_refs = [
                row
                for row in spo.get(key, [])
                if required_date is None
                or (row.arrival_date is not None and row.arrival_date <= required_date)
            ]
            facts[str(line.id)] = _LineFacts(
                line=line,
                core=core,
                item_code=codes.get(product_id or ""),
                product_id=product_id,
                open_qty=_open_of(core),
                required_date=required_date,
                warehouse=warehouse,
                pool=pool,
                own_free=shares.get(RESERVE, _ZERO),
                pool_free=(
                    self._free_at(product_id, str(pool.id)) if pool else _ZERO
                ),
                pool_reorder_level=levels.get(
                    (product_id or "", str(pool.id) if pool else ""), _ZERO
                ),
                is_hot_selling=(product_id or "") in hot,
                classification_unavailable=(product_id or "") in unavailable,
                is_discontinued=(product_id or "") in discontinued,
                timely_qty=shares.get(TIMELY_SPO, _ZERO),
                timely_refs=timely_refs,
                advisory_refs=[
                    row for row in spo.get(key, []) if row not in timely_refs
                ],
            )
        return facts

    # -------------------------------------------------------------- fact readers

    def _product_codes(self, product_ids: Iterable[str]) -> Dict[str, str]:
        ids = [pid for pid in product_ids if pid]
        if not ids:
            return {}
        return {
            str(row[0]): row[1] or ""
            for row in self.db.query(Product.id, Product.product_code)
            .filter(Product.id.in_(ids))
            .all()
        }

    def _discontinued(self, product_ids: Iterable[str]) -> set:
        ids = [pid for pid in product_ids if pid]
        if not ids:
            return set()
        return {
            str(row[0])
            for row in self.db.query(Product.id)
            .filter(Product.id.in_(ids), Product.is_discontinued.is_(True))
            .all()
        }

    def _warehouses(self, warehouse_ids: Iterable[str]) -> Dict[str, Warehouse]:
        ids = [wid for wid in warehouse_ids if wid]
        if not ids:
            return {}
        return {
            str(row.id): row
            for row in self.db.query(Warehouse).filter(Warehouse.id.in_(ids)).all()
        }

    def _warehouse_row(self, warehouse_id: str) -> Optional[Warehouse]:
        return (
            self.db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
            if warehouse_id
            else None
        )

    def _free_stock(
        self, product_ids: Iterable[str], *, exclude_order_id: Optional[str]
    ) -> Dict[Tuple[str, str], Decimal]:
        """On hand, minus reserved, minus what confirmed decisions already hold.

        A hold counts when its allocation belongs to no decision (every row written before
        Stage 1C) or to an ACTIVE one. A superseded revision's rows are history and hold
        nothing, and the order being composed is excluded so its own previous revision does
        not compete with the one replacing it.
        """
        ids = [pid for pid in product_ids if pid]
        if not ids:
            return {}
        rows = (
            self.db.query(Stock, Warehouse)
            .join(Warehouse, Warehouse.id == Stock.warehouse_id)
            .filter(Stock.product_id.in_(ids), Warehouse.is_active.is_(True))
            .all()
        )
        free = {
            (str(stock.product_id), str(stock.warehouse_id)): max(
                _dec(stock.quantity_on_hand) - _dec(stock.quantity_reserved), _ZERO
            )
            for stock, _warehouse in rows
        }
        for (product_id, warehouse_id), _project_id, qty in self._hold_rows(
            ids, exclude_order_id=exclude_order_id
        ):
            key = (product_id, warehouse_id)
            if key in free:
                free[key] = max(free[key] - qty, _ZERO)
        return free

    def _hold_rows(
        self, product_ids: Sequence[str], *, exclude_order_id: Optional[str]
    ) -> List[Tuple[Tuple[str, str], str, Decimal]]:
        """Confirmed holds, per (product, warehouse) and holding project.

        Ported from `project_allocation_service._holds` and narrowed by decision state,
        because a superseded revision must stop holding stock the moment it is superseded.
        """
        query = (
            self.db.query(
                ProjectSalesOrderLine.product_id,
                SOLineAllocation.warehouse_id,
                ProjectSalesOrder.project_id,
                SOLineAllocation.qty,
            )
            .join(
                ProjectSalesOrderLine,
                ProjectSalesOrderLine.id == SOLineAllocation.so_line_id,
            )
            .join(
                ProjectSalesOrder,
                ProjectSalesOrder.id == ProjectSalesOrderLine.project_sales_order_id,
            )
            .outerjoin(
                SOSupplyDecision, SOSupplyDecision.id == SOLineAllocation.decision_id
            )
            .filter(
                ProjectSalesOrderLine.product_id.in_(list(product_ids)),
                SOLineAllocation.confirmed_at.isnot(None),
                SOLineAllocation.warehouse_id.isnot(None),
                SOLineAllocation.source_type != ALLOC_SOURCE_ORDER,
                or_(
                    SOLineAllocation.decision_id.is_(None),
                    SOSupplyDecision.state == DECISION_ACTIVE,
                ),
            )
        )
        if exclude_order_id:
            query = query.filter(
                ProjectSalesOrder.id != exclude_order_id
            )
        return [
            ((str(product_id), str(warehouse_id)), str(project_id), _dec(qty))
            for product_id, warehouse_id, project_id, qty in query.all()
        ]

    def _holds_by_project(
        self, product_ids: Iterable[str], *, exclude_order_id: Optional[str]
    ) -> Dict[Tuple[str, str, str], Decimal]:
        out: Dict[Tuple[str, str, str], Decimal] = {}
        ids = [pid for pid in product_ids if pid]
        if not ids:
            return out
        for (product_id, warehouse_id), project_id, qty in self._hold_rows(
            ids, exclude_order_id=exclude_order_id
        ):
            key = (product_id, warehouse_id, project_id)
            out[key] = out.get(key, _ZERO) + qty
        return out

    def _free_at(self, product_id: Optional[str], warehouse_id: str) -> Decimal:
        return self._free_cache.get(
            (product_id or "", warehouse_id), _ZERO
        )

    def _held_at(
        self, product_id: Optional[str], warehouse_id: str, project_id: str
    ) -> Decimal:
        return self._holds_cache.get(
            (product_id or "", warehouse_id, project_id), _ZERO
        )

    def _classification(self, product_ids: Iterable[str]) -> Tuple[set, set]:
        """PLAN 3.3's dealer hot-selling predicate, and the "no evidence" case.

        `computed_at` is display evidence, never a freshness gate: the existing ABC facts
        are the test, and adding an age threshold would be a new knob this contract forbids.
        """
        ids = [pid for pid in product_ids if pid]
        if not ids:
            return set(), set()
        rows = (
            self.db.query(ItemClassification.product_id, ItemClassification.abc_class)
            .join(Warehouse, Warehouse.id == ItemClassification.warehouse_id)
            .filter(
                ItemClassification.product_id.in_(ids),
                Warehouse.segment == DEALER_SEGMENT,
                Warehouse.is_active.is_(True),
                Warehouse.counts_as_available.is_(True),
            )
            .all()
        )
        seen = {str(product_id) for product_id, _abc in rows}
        hot = {str(product_id) for product_id, abc in rows if (abc or "").upper() == "A"}
        return hot, {pid for pid in ids if pid not in seen}

    def _reorder_levels(
        self, product_ids: Iterable[str], warehouse_ids: Iterable[str]
    ) -> Dict[Tuple[str, str], Decimal]:
        """Per-location levels. An absent row and a NULL level both contribute 0 (Q7)."""
        pids = [pid for pid in product_ids if pid]
        wids = [wid for wid in warehouse_ids if wid]
        if not pids or not wids:
            return {}
        return {
            (str(row.product_id), str(row.warehouse_id)): _dec(row.level)
            for row in self.db.query(ReorderLevel)
            .filter(
                ReorderLevel.product_id.in_(pids),
                ReorderLevel.warehouse_id.in_(wids),
            )
            .all()
        }

    def _spo_rows(
        self, product_ids: Iterable[str], warehouse_ids: Iterable[str]
    ) -> Dict[Tuple[str, str], List[_SpoRow]]:
        """Undelivered SPO allocations at these locations, with their current ETA.

        `eta_delay_date` wins over `estimated_arrival_date` because the revised date is
        the accurate one, and a line promised against a date that has already slipped is
        the promise this whole contract is trying not to make.
        """
        pids = [pid for pid in product_ids if pid]
        wids = [wid for wid in warehouse_ids if wid]
        if not pids or not wids:
            return {}
        rows = (
            self.db.query(
                SPOAllocation.id,
                SPOAllocation.spo_number,
                SPOAllocation.spo_line_number,
                SPOAllocation.product_id,
                SPOAllocation.warehouse_id,
                SPOAllocation.allocated_quantity,
                SPOAllocation.quantity_received,
                InboundShipment.eta_delay_date,
                InboundShipment.estimated_arrival_date,
            )
            .join(
                InboundShipment, InboundShipment.id == SPOAllocation.inbound_shipment_id
            )
            .filter(
                SPOAllocation.product_id.in_(pids),
                SPOAllocation.warehouse_id.in_(wids),
                InboundShipment.actual_arrival_date.is_(None),
                or_(
                    SPOAllocation.receipt_status.is_(None),
                    SPOAllocation.receipt_status != "received",
                ),
            )
            .all()
        )
        out: Dict[Tuple[str, str], List[_SpoRow]] = {}
        for row in rows:
            balance = _dec(row.allocated_quantity) - _dec(row.quantity_received)
            if balance <= _ZERO:
                continue
            out.setdefault((str(row.product_id), str(row.warehouse_id)), []).append(
                _SpoRow(
                    spo_number=str(row.spo_number or ""),
                    spo_line_no=row.spo_line_number,
                    allocation_id=str(row.id),
                    arrival_date=row.eta_delay_date or row.estimated_arrival_date,
                    qty=balance,
                )
            )
        return out

    def _attribution(
        self,
        product_ids: Iterable[str],
        warehouse_ids: Iterable[str],
        warehouses: Dict[str, Warehouse],
        spo: Dict[Tuple[str, str], List[_SpoRow]],
    ) -> Dict[Tuple[str, str], Dict[str, Dict[str, Decimal]]]:
        """Share each product-location pile across EVERY outstanding line wanting it.

        This is the section 3.5 projection, and it is why two lines never both count the
        same SPO: one run per (product, location), all competing lines in it, the answer
        read back per core line. Keyed by core line id rather than by the engine's own
        `(so_number, line_no)` so the caller cannot pick up a namesake's answer.
        """
        pids = [pid for pid in product_ids if pid]
        wids = [wid for wid in warehouse_ids if wid]
        if not pids or not wids:
            return {}
        rows = (
            self.db.query(
                SalesOrderLine.id,
                SalesOrderLine.product_id,
                SalesOrderLine.warehouse_id,
                SalesOrderLine.qty_ordered,
                SalesOrderLine.qty_delivered,
                SalesOrderLine.required_date,
                SalesOrder.so_number,
                SalesOrder.requested_delivery_date,
                ProjectSalesOrderLine.line_no,
            )
            .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
            .outerjoin(
                ProjectSalesOrderLine,
                ProjectSalesOrderLine.core_sales_order_line_id == SalesOrderLine.id,
            )
            .filter(
                SalesOrderLine.product_id.in_(pids),
                SalesOrderLine.warehouse_id.in_(wids),
                SalesOrder.status == "open",
                is_open_demand(),
            )
            .all()
        )

        grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        keys: Dict[Tuple[str, str], Dict[Tuple[str, Optional[int]], str]] = {}
        for row in rows:
            key = (str(row.product_id), str(row.warehouse_id))
            open_qty = max(_dec(row.qty_ordered) - _dec(row.qty_delivered), _ZERO)
            if open_qty <= _ZERO:
                continue
            grouped.setdefault(key, []).append(
                {
                    "so_number": row.so_number or "",
                    "line_no": row.line_no,
                    "line_id": str(row.id),
                    "open_qty": open_qty,
                    "required_date": row.required_date or row.requested_delivery_date,
                }
            )
            keys.setdefault(key, {})[(row.so_number or "", row.line_no)] = str(row.id)

        out: Dict[Tuple[str, str], Dict[str, Dict[str, Decimal]]] = {}
        for key, demand_lines in grouped.items():
            product_id, warehouse_id = key
            warehouse = warehouses.get(warehouse_id)
            attributed = attribute_sources(
                warehouse_code=(
                    warehouse.warehouse_code if warehouse else warehouse_id
                ),
                opening_stock=self._free_at(product_id, warehouse_id),
                supply_events=[
                    {
                        "spo_number": row.spo_number,
                        "spo_line_no": row.spo_line_no,
                        "allocation_id": row.allocation_id,
                        "arrival_date": row.arrival_date,
                        "qty": row.qty,
                    }
                    for row in spo.get(key, [])
                ],
                demand_lines=demand_lines,
            )
            per_line: Dict[str, Dict[str, Decimal]] = {}
            for engine_key, components in attributed.items():
                line_id = keys.get(key, {}).get(engine_key)
                if not line_id:
                    continue
                totals: Dict[str, Decimal] = {}
                for component in components:
                    totals[component.kind] = (
                        totals.get(component.kind, _ZERO) + component.qty
                    )
                per_line[line_id] = totals
            out[key] = per_line
        return out

    # ------------------------------------------------------------ borrow candidates

    def _borrow_candidates(self, fact: _LineFacts) -> List[Dict[str, Any]]:
        """Where else this line could be met from, with what it costs the holder.

        Two shapes, and they are answered differently: free stock at a location outside
        the Reserve pool has no donor to ask, so it carries no claim; stock another
        project is holding names that project and its impact, so CS is deciding with the
        donor's position in front of them (AC-B09).
        """
        if not fact.product_id:
            return []
        inside = {
            str(fact.warehouse.id) if fact.warehouse else "",
            str(fact.pool.id) if fact.pool else "",
        }
        out: List[Dict[str, Any]] = []

        free_cache = self._free_cache
        warehouse_ids = [
            warehouse_id
            for (product_id, warehouse_id), qty in free_cache.items()
            if product_id == fact.product_id and qty > _ZERO and warehouse_id not in inside
        ]
        warehouses = self._warehouses(warehouse_ids)
        for warehouse_id in sorted(warehouse_ids):
            warehouse = warehouses.get(warehouse_id)
            if warehouse is None:
                continue
            free = free_cache[(fact.product_id, warehouse_id)]
            committed = sum(
                (
                    qty
                    for (product_id, held_warehouse, _project), qty in self._holds_cache.items()
                    if product_id == fact.product_id and held_warehouse == warehouse_id
                ),
                _ZERO,
            )
            out.append(
                {
                    "source": ALLOC_SOURCE_OTHER_LOCATION,
                    "warehouse_code": warehouse.warehouse_code,
                    "warehouse_id": warehouse_id,
                    "free_qty": qty_text(free),
                    "donor_impact": {
                        "free_before": qty_text(free),
                        "free_after_full_borrow": qty_text(_ZERO),
                        "committed_qty": qty_text(committed),
                    },
                }
            )

        holds = [
            (warehouse_id, project_id, qty)
            for (product_id, warehouse_id, project_id), qty in self._holds_cache.items()
            if product_id == fact.product_id and qty > _ZERO
        ]
        if holds:
            projects = {
                str(row.id): row
                for row in self.db.query(Project)
                .filter(Project.id.in_([project_id for _w, project_id, _q in holds]))
                .all()
            }
            donor_warehouses = self._warehouses([w for w, _p, _q in holds])
            for warehouse_id, project_id, qty in sorted(holds):
                warehouse = donor_warehouses.get(warehouse_id)
                donor = projects.get(project_id)
                if warehouse is None or donor is None:
                    continue
                free = free_cache.get((fact.product_id, warehouse_id), _ZERO)
                out.append(
                    {
                        "source": ALLOC_SOURCE_OTHER_PROJECT,
                        "warehouse_code": warehouse.warehouse_code,
                        "warehouse_id": warehouse_id,
                        "donor_project_ref": donor.project_code,
                        "donor_project_id": project_id,
                        "free_qty": qty_text(qty),
                        "donor_impact": {
                            "free_before": qty_text(free + qty),
                            "free_after_full_borrow": qty_text(free),
                            "committed_qty": qty_text(qty),
                        },
                    }
                )
        return out
