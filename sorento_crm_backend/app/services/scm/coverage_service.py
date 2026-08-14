"""Build a Coverage Timeline from the database. The resolver half of ADR-0011.

`coverage_timeline` holds the pure maths and knows nothing about tables. This module reads
the canonical rows and feeds it, which is the same split `reorder_engine` already uses (pure
top, resolver bottom) so the arithmetic stays golden-testable in isolation.

What it reads, and why each:

* ``stock`` filtered by ``warehouses.counts_as_available`` - opening on hand. The flag is
  config defaulting to true, so nothing is excluded unless an admin said so.
* ``sales_order_lines.required_date`` - dated demand. Lines with no required date fall back
  to the header's ``requested_delivery_date``, and a line with neither is reported rather
  than silently dated today: an undated commitment cannot be planned and pretending it is
  due now would fabricate a shortfall.
* ``purchase_order_lines`` on placed POs - dated supply, stage ``on_order``.
* ``inbound_shipment_lines`` on shipments not yet received - dated supply, stage
  ``in_transit``. Kept separate from on-order because only one of the two can still be
  cancelled or re-dated, and that split is what a person deciding a quantity reads.

**The pool is the unit of netting, not the warehouse.** A location's
``pool_warehouse_id`` says which shared pool it may draw on, so a shortage in ``BRW-BB`` is
covered from ``BRW`` before it is ever a purchase. Cross-site stock is deliberately not a
source: it needs a physical movement with a cost and a lead time, so it surfaces as a
transfer proposal a person accepts (``transfer_proposals``).

Three figures are configuration, resolved from ``scm.reorder_policy`` through the SAME
resolver the reorder engine uses (``resolve_policy_for_sku``) so the two can never disagree
about which policy row wins: ``planning_horizon_months`` (default 6 in code),
``transfer_lead_time_days`` and ``transfer_cost_per_unit``. The transfer pair stays NULL
when unconfigured, never 0.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models.inventory import Stock, Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import (
    InboundShipment,
    InboundShipmentLine,
    SPOAllocation,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
)
from app.models.product import Product
from app.models.scm import ReorderPolicy
from app.services.scm.coverage_timeline import (
    DEMAND,
    EPSILON,
    SUPPLY,
    SUPPLY_IN_TRANSIT,
    QTY_PRECISION,
    SOURCE_ORDER,
    SOURCE_OWN,
    SOURCE_POOL,
    SourceAllocation,
    SourceAvailability,
    TimelineEvent,
    TimelineResult,
    build_timeline,
    buy_quantity,
    is_use_stock,
    resolve_sources,
)
from app.services.scm.demand import (
    is_open_demand,
    is_plan_demand_order,
    qty_of as demand_qty_of,
)
from app.services.scm.reorder_engine import resolve_policy_for_sku
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime

# PO statuses that represent real placed supply. Drafts are NOT supply: a draft PO is a
# recommendation nobody has committed to, and counting it would suppress the buy that
# creates it. Mirrors scm.on_order_v.
# Still used, but for the ORDERED figure rather than for supply: these are the statuses
# under which a purchase order counts as really placed with the supplier.
_PLACED_PO_STATUSES = ("active", "received", "partial", "closed")

# Shipment states that mean the goods have LANDED or left the book, so their lines are no
# longer incoming and counting them would double real stock. Expressed as the excluded set,
# not an allowed set, because the rest of the repo does the same
# (`incoming_stock_service._still_incoming_filter`, `procurement_service._is_received_status`)
# and because an allowed list silently drops any status nobody thought of. A whitelist fails
# closed on real supply; a blacklist fails open on a state that does not exist yet, which is
# the safer direction for a figure that STOPS purchases.
#
# The column's vocabulary is fixed by the `inbound_shipments_shipment_status_check`
# constraint: in_transit, arrived_at_port, at_warehouse, partially_received, fully_received,
# closed. Two consequences that were both wrong here:
#
#   * `closed` was missing, so a shipment closed off the book still contributed cover. That
#     is the fail-open direction, and it suppresses a purchase silently.
#   * `partially_received` is deliberately NOT excluded: part has arrived and the rest is
#     still coming, and the per-line outstanding quantity is what the reader nets. Excluding
#     the whole shipment would drop the half still on the water.
#
# `received` / `completed` / `cancelled` cannot appear in this column - `received` is
# normalised to `fully_received` by `procurement_service._normalize_inbound_shipment_status`
# and the other two are not in the constraint at all. They are kept only so a legacy row
# written before the constraint, or an alias that stops being normalised, still fails in the
# safe direction.
_RECEIVED_SHIPMENT_STATUSES = (
    "fully_received",
    "closed",
    "received",
    "completed",
    "cancelled",
)

# Shipment LINE states that are no longer inbound. The purchase-order half of this same
# function filters `PurchaseOrderLine.line_status == "open"`, and one function disagreeing
# with itself about what "still open" means is the defect.
_CLOSED_SHIPMENT_LINE_STATUSES = ("closed", "cancelled", "received")

# How far ahead the dated axis runs when no policy configures it. Six months is long
# enough to cover a China lead time plus a review cycle and short enough that the report
# stays readable; the figure is config (`scm.reorder_policy.planning_horizon_months`) so
# a tenant that plans further ahead changes a row, not the code.
DEFAULT_PLANNING_HORIZON_MONTHS = 6


def _add_months(start: date, months: int) -> date:
    """Calendar-month addition, clamped to the target month's last day.

    Months rather than days because the horizon is stated in months by config and by the
    people who use it ("we plan half a year out"), and 6 x 30 days drifts off the month
    boundary they mean.
    """
    total = start.month - 1 + max(0, int(months))
    year = start.year + total // 12
    month = total % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


@dataclass(frozen=True)
class UndatedDemand:
    """A commitment with no date anywhere. Reported, never guessed at."""

    so_number: str
    item_code: str
    qty: float
    location: str


@dataclass(frozen=True)
class TransferProposal:
    """Cover held at ANOTHER site, offered rather than netted.

    Cross-site stock is real, but reaching it costs money and takes days, so silently
    netting it would produce a plan that is only true once a lorry nobody has booked
    arrives. It therefore stays out of the balance and surfaces here with its cost and
    lead time for a person to accept (AC-B1d).

    ``transfer_cost`` / ``lead_time_days`` stay None when the tenant has configured
    neither. They are never defaulted to 0: a free instant move would make the proposal
    look better than the truth, and ``arrives_at`` is likewise None with no lead time
    rather than reading as "today".
    """

    proposal_ref: str
    from_pool_code: str
    available_qty: float
    qty: float
    transfer_cost: Optional[float] = None
    lead_time_days: Optional[int] = None
    arrives_at: Optional[date] = None


@dataclass(frozen=True)
class CoverageConfig:
    """The three tenant-configurable figures the timeline needs, already resolved."""

    horizon_months: int
    transfer_lead_time_days: Optional[int]
    transfer_cost_per_unit: Optional[float]


@dataclass(frozen=True)
class NetworkPosition:
    """One product's DATED position over the whole network, for the Summary Order Report.

    Distinct from ``Coverage`` on purpose. ``Coverage`` answers "what should this pool do
    about this product", and carries the source split, the transfer proposals and the
    allocation advice that only make sense for one pool. This answers the narrower question
    the report row asks - how much is here, how much is coming in each stage, and how far
    below zero the dated balance ever gets - over every location that counts toward
    availability. Netting the whole network is right for a purchasing decision because a PO
    is raised once for the company, not once per pool.

    ``shortfall`` is ``peak_deficit``, not the first gap: a later event can dig deeper, and
    buying only the first gap leaves the plan short a second time.

    The three "could not place" figures travel with the position rather than being dropped,
    for the same reason they do on ``Coverage``: a quantity in none of the numbers is worse
    than one in the wrong number.
    """

    product_id: str
    on_hand: float
    qty_on_order: float
    qty_in_transit: float
    shortfall: float
    closing_balance: float
    shortfall_at: Optional[date]
    horizon_end: date
    undated_demand_qty: float = 0.0
    unattributed_in_transit_qty: float = 0.0
    unplaceable_demand_qty: float = 0.0
    unplaceable_on_order_qty: float = 0.0


@dataclass(frozen=True)
class Coverage:
    product_id: str
    product_code: str
    product_name: Optional[str]
    pool_id: Optional[str]
    pool_code: str
    locations: tuple[str, ...]
    floor: float
    opening_balance: float
    timeline: TimelineResult
    availability: SourceAvailability
    allocations: tuple[SourceAllocation, ...]
    buy_qty: float
    use_stock: bool
    undated_demand: tuple[UndatedDemand, ...]
    transfer_proposals: tuple[TransferProposal, ...]
    horizon_months: int
    horizon_end: date
    computed_at: datetime
    # In-transit quantity no allocation places, so it is counted for NO pool. Surfaced
    # rather than dropped in silence: supply set aside is a thing somebody has to chase.
    unattributed_in_transit_qty: float = 0.0
    # Committed demand, and placed on-order supply, carrying NO warehouse at all. Both
    # columns are nullable, and `warehouse_id.in_(...)` evaluates NULL to NULL, so these rows
    # reached no pool's timeline and no report: real commitments and real containers that
    # simply were not in any figure. Same treatment as the in-transit case above, for the same
    # reason - a quantity nobody can place is exactly what a planner has to be told about,
    # since the alternative is discovering it on a delivery date.
    unplaceable_demand_qty: float = 0.0
    unplaceable_on_order_qty: float = 0.0
    # Placed on a purchase order and allocated to this pool, with no shipment allocated
    # against it yet. Reported BESIDE the timeline and deliberately absent FROM it: an order
    # is not stock on the water. Without it the screen would show a shortfall and no hint
    # that a buyer already acted on it.
    qty_ordered_not_incoming: float = 0.0

    @property
    def excluded_event_count(self) -> int:
        """Events dropped for falling beyond the horizon.

        Read straight off the timeline rather than copied onto this dataclass, so the
        count a screen states and the rows it draws can never disagree.
        """
        return self.timeline.excluded_event_count


class CoverageService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # -- pool topology --------------------------------------------------------

    def pool_members(self, pool_id: str) -> list[Warehouse]:
        """Every location that draws on this pool, the pool itself included."""
        return (
            self.db.query(Warehouse)
            .filter(
                or_(Warehouse.pool_warehouse_id == pool_id, Warehouse.id == pool_id),
                Warehouse.counts_as_available.is_(True),
            )
            .order_by(Warehouse.warehouse_code)
            .all()
        )

    def availability_warehouse_ids(self) -> list[str]:
        """Every location whose stock and inbound supply count toward availability.

        The network is the union of every pool, so this is the location set a network-wide
        balance nets over. Read once per batch rather than per product.
        """
        return [
            str(wid)
            for (wid,) in self.db.query(Warehouse.id)
            .filter(Warehouse.counts_as_available.is_(True))
            .all()
        ]

    def pool_for_location(self, warehouse_id: str) -> Optional[str]:
        w = self.db.query(Warehouse).filter(Warehouse.id == warehouse_id).one_or_none()
        if w is None:
            return None
        # A location with no pointer is its own pool, which is the no-suffix case.
        return w.pool_warehouse_id or w.id

    # -- events ---------------------------------------------------------------

    def _opening(self, product_id: str, wh_ids: Iterable[str]) -> float:
        return self._opening_many([product_id], wh_ids).get(str(product_id), 0.0)

    def _opening_many(
        self, product_ids: Iterable[str], wh_ids: Iterable[str]
    ) -> dict[str, float]:
        """Opening on hand per product over the given locations.

        The batched form exists so a report over thousands of products pays ONE query rather
        than one per product; the single-product method is a wrapper over it so there is only
        ever one implementation of what "on hand for these locations" means.
        """
        pids = [str(p) for p in product_ids]
        if not pids:
            return {}
        rows = (
            self.db.query(
                Stock.product_id,
                func.coalesce(func.sum(Stock.quantity_on_hand), 0),
            )
            .filter(Stock.product_id.in_(pids), Stock.warehouse_id.in_(list(wh_ids)))
            .group_by(Stock.product_id)
            .all()
        )
        return {str(pid): float(total or 0) for pid, total in rows}

    def _demand_events(
        self, product_id: str, wh_ids: list[str]
    ) -> tuple[list[TimelineEvent], list[UndatedDemand], float]:
        """Dated demand for this pool, its undated rows, and the quantity carrying no
        location at all.

        The third figure exists because `warehouse_id` is nullable and `in_(wh_ids)` is NULL
        for such a row, so it belonged to no pool and appeared in no total. A commitment that
        is in none of the numbers is worse than one in the wrong number.
        """
        return self._demand_events_many([product_id], wh_ids).get(
            str(product_id), ([], [], 0.0)
        )

    def _demand_events_many(
        self, product_ids: Iterable[str], wh_ids: list[str]
    ) -> dict[str, tuple[list[TimelineEvent], list[UndatedDemand], float]]:
        """`_demand_events` for many products at once, keyed by product id.

        Deliberately the SAME body rather than a second reader: every predicate here is
        load-bearing (open order, open line, outstanding quantity, the nullable-location
        rows) and a parallel implementation would drift from it silently. Products with no
        demand are absent from the result; callers read with a default.
        """
        pids = [str(p) for p in product_ids]
        if not pids:
            return {}
        rows = (
            self.db.query(
                SalesOrderLine.product_id,
                SalesOrderLine.qty_ordered,
                SalesOrderLine.qty_delivered,
                SalesOrderLine.qty_required,
                SalesOrderLine.required_date,
                SalesOrder.requested_delivery_date,
                SalesOrder.so_number,
                SalesOrder.demand_class,
                Customer.customer_name,
                Warehouse.warehouse_code,
                Product.product_code,
            )
            .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
            .outerjoin(Customer, Customer.id == SalesOrder.customer_id)
            .outerjoin(Warehouse, Warehouse.id == SalesOrderLine.warehouse_id)
            .outerjoin(Product, Product.id == SalesOrderLine.product_id)
            .filter(
                SalesOrderLine.product_id.in_(pids),
                SalesOrderLine.warehouse_id.in_(wh_ids),
                SalesOrder.status == "open",
                is_open_demand(),
                # S13b: project demand exists only where the Order Inquiry created it. The
                # timeline must eat the same demand as scm.committed_v or the chart
                # contradicts the plan for reasons nobody can see.
                is_plan_demand_order(),
            )
            .all()
        )

        # Same predicates, but the rows the location filter cannot place.
        unplaceable_rows = (
            self.db.query(
                SalesOrderLine.product_id,
                SalesOrderLine.qty_ordered,
                SalesOrderLine.qty_delivered,
                SalesOrderLine.qty_required,
            )
            .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
            .filter(
                SalesOrderLine.product_id.in_(pids),
                SalesOrderLine.warehouse_id.is_(None),
                SalesOrder.status == "open",
                is_open_demand(),
                is_plan_demand_order(),
            )
            .all()
        )

        events: dict[str, list[TimelineEvent]] = {}
        undated: dict[str, list[UndatedDemand]] = {}
        for r in rows:
            pid = str(r.product_id)
            outstanding = demand_qty_of(r)
            if outstanding <= 0:
                continue
            when = r.required_date or r.requested_delivery_date
            if when is None:
                # An undated commitment cannot be planned. Dating it "today" would fabricate
                # a shortfall, and dropping it would hide real demand, so it is surfaced.
                undated.setdefault(pid, []).append(
                    UndatedDemand(
                        so_number=r.so_number or "",
                        item_code=r.product_code or "",
                        qty=outstanding,
                        location=r.warehouse_code or "",
                    )
                )
                continue
            events.setdefault(pid, []).append(
                TimelineEvent(
                    at=when,
                    qty=-outstanding,
                    kind=DEMAND,
                    ref=r.so_number or "",
                    label=r.customer_name or (r.demand_class or ""),
                    location=r.warehouse_code or "",
                )
            )
        unplaceable: dict[str, float] = {}
        for r in unplaceable_rows:
            pid = str(r.product_id)
            unplaceable[pid] = unplaceable.get(pid, 0.0) + demand_qty_of(r)

        keys = set(events) | set(undated) | set(unplaceable)
        return {
            pid: (
                events.get(pid, []),
                undated.get(pid, []),
                max(round(unplaceable.get(pid, 0.0), QTY_PRECISION), 0.0),
            )
            for pid in keys
        }

    def _supply_events(
        self, product_id: str, wh_ids: list[str]
    ) -> tuple[list[TimelineEvent], float, float, tuple[tuple[Optional[date], float], ...]]:
        """Four figures for this pool: dated SUPPLY events, the in-transit quantity nobody
        could place, the placed order quantity carrying no location at all, and the placed
        order quantity that IS placed here.

        Only the first drives the balance. A purchase order is ordered, not incoming, so its
        quantity travels beside the timeline rather than on it.

        These are returned rather than stashed on the instance: they are facts about THIS
        call, and a service attribute would quietly describe whichever product was asked
        about last.
        """
        return self._supply_events_many([product_id], wh_ids).get(
            str(product_id), ([], 0.0, 0.0, ())
        )

    def _supply_events_many(
        self, product_ids: Iterable[str], wh_ids: list[str]
    ) -> dict[
        str, tuple[list[TimelineEvent], float, float, tuple[tuple[Optional[date], float], ...]]
    ]:
        """`_supply_events` for many products at once, keyed by product id.

        One body, batched, for the same reason as the demand half: the in-transit attribution
        (destination through the allocation, per-allocation outstanding, cross-pool pro-rate)
        is subtle enough that a second copy of it would be wrong within a release.
        """
        pids = [str(p) for p in product_ids]
        if not pids:
            return {}
        events: dict[str, list[TimelineEvent]] = {}

        # Purchase orders are ORDERED, never SUPPLY. The chain is PO -> SPO -> GRN, and only
        # the SPO allocation is stock on its way in: a purchase order is an order PLACED,
        # which the supplier may not have shipped anything against. The live book made the
        # difference unmissable - 9 open PO lines against 842 in-transit allocations carrying
        # 203,115 units - so counting the PO half reported almost none of the real supply
        # while the allocations sat unread (decision, 6 Aug 2026; `scm.on_order_v` now reads
        # the same source).
        #
        # The two are NOT netted against each other because nothing links them:
        # `spo_allocations.po_line_id` is NULL on all 860 existing rows, so counting both
        # would double every shipped order. So the quantity is still READ and still reported,
        # under its own name, and it produces NO timeline event: the balance is unaffected,
        # and a buyer looking at a shortfall can still see that an order is already out for
        # it. Reporting it is the whole mitigation for the exposure this decision accepts -
        # between placing an order and its first allocation, the plan would otherwise
        # recommend buying it a second time with nothing on screen to say why.
        # Dated, because the caller bounds it by ITS horizon: this figure sits beside a
        # horizon-scoped shortfall, and an order landing after the window cannot inform the
        # decision that shortfall drives.
        po_ordered: dict[str, list[tuple[Optional[date], float]]] = {}
        for pid, a, b, line_when, po_when in (
            self.db.query(
                PurchaseOrderLine.product_id,
                PurchaseOrderLine.qty_ordered,
                PurchaseOrderLine.qty_received,
                PurchaseOrderLine.expected_date,
                PurchaseOrder.expected_date.label("po_expected"),
            )
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
            .filter(
                PurchaseOrderLine.product_id.in_(pids),
                PurchaseOrderLine.warehouse_id.in_(wh_ids),
                PurchaseOrder.status.in_(_PLACED_PO_STATUSES),
                # A line the importer has CLOSED left the supplier's order book, so nothing
                # is on order against it any more.
                PurchaseOrderLine.line_status == "open",
                PurchaseOrderLine.qty_ordered > PurchaseOrderLine.qty_received,
            )
            .all()
        ):
            qty = float(a or 0) - float(b or 0)
            if qty <= 0:
                continue
            po_ordered.setdefault(str(pid), []).append((line_when or po_when, qty))

        # In-transit supply, scoped to THIS pool through the allocation that names its
        # destination. Neither `inbound_shipments` nor `inbound_shipment_lines` carries a
        # destination warehouse, so without this join every container for a SKU lands on
        # EVERY pool's timeline: with two pools the same 60 units read as 120 units of cover
        # that does not exist, and the purchase that should have been raised is suppressed
        # invisibly, because each pool's screen looks internally consistent on its own.
        #
        # `spo_allocations.warehouse_id` is the destination, not `po_line_id`. The PO link is
        # nullable and 860 existing rows have none (stock can arrive against no PO), so
        # keying on it would drop legitimately allocated supply. One shipment line can be
        # split across warehouses, so the attribution is per allocation, not per line.
        # Which locations belong to SOME pool, read as a set rather than joined. An aliased
        # join onto `warehouses` cannot be used here: the company-isolation filter injects
        # `warehouses.company_id` into the ON clause under the unaliased table name, and
        # Postgres rejects the reference. One small set read is also cheaper than a join
        # repeated per allocation row.
        # Placed PO quantity the location filter cannot place, because
        # `purchase_order_lines.warehouse_id` is nullable. Not supply either way, but a real
        # order that reached no pool's ORDERED figure, so it is named rather than dropped.
        unplaceable_on_order: dict[str, float] = {}
        for pid, a, b in (
            self.db.query(
                PurchaseOrderLine.product_id,
                PurchaseOrderLine.qty_ordered,
                PurchaseOrderLine.qty_received,
            )
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
            .filter(
                PurchaseOrderLine.product_id.in_(pids),
                PurchaseOrderLine.warehouse_id.is_(None),
                PurchaseOrder.status.in_(_PLACED_PO_STATUSES),
                PurchaseOrderLine.line_status == "open",
                PurchaseOrderLine.qty_ordered > PurchaseOrderLine.qty_received,
            )
            .all()
        ):
            key = str(pid)
            unplaceable_on_order[key] = unplaceable_on_order.get(key, 0.0) + (
                float(a or 0) - float(b or 0)
            )

        placeable_ids = {
            wid
            for (wid,) in self.db.query(Warehouse.id)
            .filter(Warehouse.counts_as_available.is_(True))
            .all()
        }
        ship_rows = (
            self.db.query(
                InboundShipmentLine.id.label("line_id"),
                InboundShipmentLine.product_id,
                InboundShipmentLine.quantity_shipped,
                InboundShipmentLine.quantity_received,
                InboundShipment.estimated_arrival_date,
                InboundShipment.shipment_number,
                Supplier.supplier_name,
                SPOAllocation.warehouse_id,
                SPOAllocation.allocated_quantity,
                SPOAllocation.quantity_received.label("allocation_received"),
            )
            .join(InboundShipment, InboundShipment.id == InboundShipmentLine.shipment_id)
            .outerjoin(Supplier, Supplier.id == InboundShipment.supplier_id)
            .outerjoin(
                SPOAllocation,
                and_(
                    SPOAllocation.inbound_shipment_id == InboundShipmentLine.shipment_id,
                    SPOAllocation.product_id == InboundShipmentLine.product_id,
                ),
            )
            .filter(
                InboundShipmentLine.product_id.in_(pids),
                InboundShipment.shipment_status.notin_(_RECEIVED_SHIPMENT_STATUSES),
                InboundShipmentLine.line_status.notin_(_CLOSED_SHIPMENT_LINE_STATUSES),
                InboundShipmentLine.quantity_shipped > InboundShipmentLine.quantity_received,
            )
            .all()
        )

        wh_set = set(wh_ids)
        # line id -> (product, outstanding, arrival, ref, label, qty allocated anywhere, qty here)
        by_line: dict[str, dict] = {}
        for r in ship_rows:
            entry = by_line.setdefault(str(r.line_id), {
                "product_id": str(r.product_id),
                "outstanding": float(r.quantity_shipped or 0) - float(r.quantity_received or 0),
                "at": r.estimated_arrival_date,
                "ref": r.shipment_number or "",
                "label": r.supplier_name or "",
                "allocated": 0.0,
                "here": 0.0,
                "elsewhere": 0.0,
                "unplaceable": 0.0,
            })
            if r.warehouse_id is None:
                continue
            # Each allocation's OWN outstanding quantity. `allocated_quantity` is never
            # decremented as goods arrive (stated at incoming_stock_service.py:78-80), so the
            # only honest per-destination figure is allocated minus what that allocation has
            # itself received. Capping each pool at the LINE's outstanding instead handed the
            # same 40 units to two pools: 80 units of cover against 40 still on the water,
            # with each pool's screen internally consistent on its own.
            qty = max(
                float(r.allocated_quantity or 0) - float(r.allocation_received or 0), 0.0
            )
            entry["allocated"] += qty
            if r.warehouse_id in wh_set:
                entry["here"] += qty
            elif r.warehouse_id in placeable_ids:
                # Allocated to a location that belongs to SOME pool, just not this one. It is
                # placed: another pool's screen accounts for it, so it is neither cover here
                # nor missing.
                entry["elsewhere"] += qty
            else:
                # Allocated to a location that belongs to NO pool: a quarantine or damaged
                # bin excluded by `counts_as_available`. No pool's balance may count it, and
                # no pool's screen would otherwise mention it, so it is reported as
                # unattributed on EVERY pool - "which pool should have told me" has no
                # answer, and stock somebody paid for sitting where nobody looks is exactly
                # what a planning report exists to surface.
                entry["unplaceable"] += qty

        unattributed: dict[str, float] = {}
        for entry in by_line.values():
            pid = entry["product_id"]
            outstanding = entry["outstanding"]
            if outstanding <= 0:
                continue
            # Never more than is actually still coming. When the allocations CLAIM more than
            # the supplier is still sending (a real data error: 60 + 60 against 40 on the
            # water) each destination is pro-rated rather than each being capped at the
            # line's full outstanding, because capping per pool hands 40 to one pool and 40
            # to the other and invents 40 units of cover. Understating costs one visible
            # extra purchase; overstating suppresses purchases silently, which is the failure
            # nobody catches.
            claimed = entry["here"] + entry["elsewhere"] + entry["unplaceable"]
            scale = min(1.0, outstanding / claimed) if claimed > 0 else 0.0
            here = round(entry["here"] * scale, QTY_PRECISION)
            # Two ways a quantity ends up on nobody's timeline, both reported. What no
            # allocation claims has no derivable destination at all; what an allocation sends
            # to a location in no pool has a destination nobody can sell from. Excluding
            # either from every pool is right; leaving it unsaid is not, because the same
            # quantity added to N pools instead suppresses N purchases and nothing on screen
            # ever admits it.
            unattributed[pid] = unattributed.get(pid, 0.0) + (
                max(outstanding - min(entry["allocated"], outstanding), 0.0)
                + entry["unplaceable"]
            )
            if here <= 0:
                continue
            events.setdefault(pid, []).append(
                TimelineEvent(
                    at=entry["at"],
                    qty=here,
                    kind=SUPPLY,
                    ref=entry["ref"],
                    label=entry["label"],
                    supply_stage=SUPPLY_IN_TRANSIT,
                )
            )

        # An undated supply line cannot be placed on the axis. It is dropped from the balance
        # rather than assumed imminent, because assuming it arrives in time is exactly the
        # optimism that produces a stockout.
        keys = (
            set(events) | set(unattributed) | set(unplaceable_on_order) | set(po_ordered)
        )
        return {
            pid: (
                [e for e in events.get(pid, []) if e.at is not None],
                round(unattributed.get(pid, 0.0), QTY_PRECISION),
                max(unplaceable_on_order.get(pid, 0.0), 0.0),
                tuple(po_ordered.get(pid, ())),
            )
            for pid in keys
        }

    # -- availability ---------------------------------------------------------

    def availability(
        self,
        product_id: str,
        *,
        own_warehouse_id: Optional[str],
        pool_id: Optional[str],
        self_pool_bucket: str = SOURCE_POOL,
    ) -> SourceAvailability:
        """What could cover a line right now, split by source.

        Computed live and never cached: somebody else's on-hand is stale the moment they
        ship, and acting on a stale figure is the failure this prevents.

        ``self_pool_bucket`` decides ONE ambiguous case: the named location IS the pool,
        which happens both when a pool is asked about directly and when a location carries
        no pool pointer (it is then its own pool - the no-suffix case). The two callers need
        opposite answers, so this is stated by the caller rather than inferred:

        * ``SOURCE_POOL`` (default), for the coverage payload a person READS. The answer has
          to read "use the pool", so shared stock stays under ``pool``. Reporting the pool's
          own bin as ``own`` would lose the word "pool" on the one case this module exists
          for, and the panel that renders ``availability.pool`` would go blank.
        * ``SOURCE_OWN``, for ``resolve_line``, which RESOLVES a demand line. Stock in the
          line's own location is not borrowed, and ``resolve_sources`` persists this string
          into ``so_line_allocations.source_type`` - so ``brw`` on a site with no shared pool
          does not merely read oddly, it records a transfer that never happened.

        Inferring it from whether a bin was named does not work: the endpoint names one too
        (the frontend passes the row's own location), so the two cases are indistinguishable
        by argument shape.
        """
        if pool_id is None:
            return SourceAvailability()

        members = self.pool_members(pool_id)
        by_id = {w.id: w for w in members}
        # `quantity_on_hand`, deliberately NOT `quantity_available`. The generated
        # `quantity_available` column is on-hand minus reserved, and the sales-order lines
        # that did the reserving are ALREADY demand events on the timeline. Netting them
        # here as well counted the same reservation twice: 100 on hand fully reserved against
        # one open line for 100 showed "opening 100, own 0, pool 0, Buy 100" while the
        # timeline balance was exactly 0 and nothing was short. One basis for both halves.
        rows = (
            self.db.query(Stock.warehouse_id, Stock.quantity_on_hand)
            .filter(
                Stock.product_id == product_id,
                Stock.warehouse_id.in_(list(by_id)),
            )
            .all()
        )

        own = pool = other = 0.0
        other_locations: list[str] = []
        pool_code = ""
        for wh_id, qty in rows:
            q = float(qty or 0)
            if q <= 0:
                continue
            is_own = own_warehouse_id is not None and wh_id == own_warehouse_id
            if wh_id == pool_id:
                pool_code = by_id[wh_id].warehouse_code
                if is_own and self_pool_bucket == SOURCE_OWN:
                    own += q
                else:
                    pool += q
            elif is_own:
                own += q
            else:
                other += q
                other_locations.append(by_id[wh_id].warehouse_code)

        if not pool_code and pool_id in by_id:
            pool_code = by_id[pool_id].warehouse_code

        return SourceAvailability(
            own=own,
            pool=pool,
            other=other,
            pool_location=pool_code,
            other_locations=tuple(sorted(other_locations)),
        )

    # -- config ---------------------------------------------------------------

    def config_for(self, product_id: str, *, pool_id: Optional[str]) -> CoverageConfig:
        """Resolve the three tenant-configurable figures for this SKU.

        Delegated to ``resolve_policy_for_sku``, the resolver the reorder engine already
        uses, so the Coverage Timeline and the engine can never disagree about which
        policy row wins (sku > abc_xyz_cell > product_class > global). The winning row is
        then read through the ORM model, which is the source of truth for the three
        columns this slice added.

        Only the horizon carries a code default. The transfer figures stay None when
        nothing configures them: substituting 0 would advertise a free, instant move.
        """
        policy_id = None
        try:
            resolved = resolve_policy_for_sku(self.db, product_id, pool_id)
            policy_id = (resolved or {}).get("id")
        except Exception:  # noqa: BLE001
            # Config is an input to advice, not the advice itself. An install with no scm
            # policy tables yet must still get a timeline with the code defaults rather
            # than a 500 for the whole screen.
            policy_id = None

        row = None
        if policy_id:
            row = (
                self.db.query(ReorderPolicy)
                .filter(ReorderPolicy.id == policy_id)
                .one_or_none()
            )

        months = getattr(row, "planning_horizon_months", None)
        cost = getattr(row, "transfer_cost_per_unit", None)
        lead = getattr(row, "transfer_lead_time_days", None)
        return CoverageConfig(
            horizon_months=int(months) if months else DEFAULT_PLANNING_HORIZON_MONTHS,
            transfer_lead_time_days=int(lead) if lead is not None else None,
            transfer_cost_per_unit=float(cost) if cost is not None else None,
        )

    # -- cross-site cover ----------------------------------------------------

    def transfer_proposals(
        self,
        product_id: str,
        *,
        pool_id: str,
        pool_code: str,
        member_ids: Iterable[str],
        needed_qty: float,
        config: CoverageConfig,
        today: date,
    ) -> list[TransferProposal]:
        """Stock for this product held OUTSIDE the requested pool, offered as proposals.

        Real data, never netted: moving it is a physical transfer, so it is information a
        person acts on rather than a quantity the balance silently assumes. Nothing is
        offered when nothing has to be bought - a proposal against a fully covered pool is
        noise that competes with the answer "use the pool".
        """
        remaining = max(0.0, float(needed_qty))
        if remaining <= 1e-9:
            return []

        excluded = set(member_ids)
        rows = (
            self.db.query(
                Warehouse.id,
                Warehouse.pool_warehouse_id,
                Stock.quantity_available,
            )
            .join(Stock, Stock.warehouse_id == Warehouse.id)
            .filter(
                Stock.product_id == product_id,
                Warehouse.counts_as_available.is_(True),
                Stock.quantity_available > 0,
            )
            .all()
        )

        # Aggregate per HOLDING POOL, not per bin: a site is one place to send a lorry, so
        # three bins at one site is one proposal a person judges, not three.
        by_pool: dict[str, float] = {}
        for wh_id, holder_pool_id, qty in rows:
            if wh_id in excluded:
                continue
            holder_pool = holder_pool_id or wh_id
            if holder_pool == pool_id or holder_pool in excluded:
                continue
            by_pool[holder_pool] = by_pool.get(holder_pool, 0.0) + float(qty or 0)

        if not by_pool:
            return []

        codes = dict(
            self.db.query(Warehouse.id, Warehouse.warehouse_code)
            .filter(Warehouse.id.in_(list(by_pool)))
            .all()
        )

        cost_per_unit = config.transfer_cost_per_unit
        lead_days = config.transfer_lead_time_days
        arrives_at = today + timedelta(days=lead_days) if lead_days is not None else None

        out: list[TransferProposal] = []
        # Ordered by the holding pool's CODE so the same computation numbers the same
        # proposals the same way: `proposal_ref` has to be stable to be a key at all.
        for index, holder_pool in enumerate(
            sorted(by_pool, key=lambda pid: codes.get(pid) or ""), start=1
        ):
            if remaining <= 1e-9:
                break
            available = round(by_pool[holder_pool], 4)
            take = round(min(remaining, available), 4)
            out.append(
                TransferProposal(
                    # A human reference, never a UUID: the FE holds it to accept the
                    # proposal and a planner may end up reading it aloud.
                    proposal_ref=f"TP-{pool_code}-{index:04d}",
                    from_pool_code=codes.get(holder_pool) or "",
                    available_qty=available,
                    qty=take,
                    transfer_cost=(
                        round(cost_per_unit * take, 2) if cost_per_unit is not None else None
                    ),
                    lead_time_days=lead_days,
                    arrives_at=arrives_at,
                )
            )
            remaining -= take
        return out

    # -- the public entry point ----------------------------------------------

    def coverage_for(
        self,
        product_id: str,
        *,
        pool_id: str,
        floor: float = 0.0,
        horizon_end: Optional[date] = None,
        own_warehouse_id: Optional[str] = None,
    ) -> Coverage:
        """The whole coverage position for ONE product over ONE fulfilment pool.

        ``own_warehouse_id`` is the location the question was asked from - a customer bin
        on the results grid, or the pool itself. It only splits ``availability`` (own vs
        pool vs other members); the balance is always netted over the whole pool, because
        the pool is the unit of netting.

        ``horizon_end`` overrides the configured horizon for callers that state their own
        window; otherwise it is derived from ``planning_horizon_months``.
        """
        members = self.pool_members(pool_id)
        wh_ids = [w.id for w in members]
        product = self.db.query(Product).filter(Product.id == product_id).one_or_none()
        # Read off the pool row directly, NOT off `members`: `pool_members` filters
        # `counts_as_available`, so a pool bin flagged out of availability with sub-bins still
        # pointing at it returned an empty code, and the screen then printed "pool" followed
        # by a blank while the verdict lost the pool's name entirely.
        pool_code = next(
            (w.warehouse_code for w in members if w.id == pool_id),
            (
                self.db.query(Warehouse.warehouse_code)
                .filter(Warehouse.id == pool_id)
                .scalar()
                or ""
            ),
        )

        config = self.config_for(product_id, pool_id=pool_id)
        computed_at = to_naive_datetime(datetime.now(MALAYSIA_TZ))
        today = computed_at.date()
        resolved_horizon_end = horizon_end or _add_months(today, config.horizon_months)

        demand, undated, unplaceable_demand = self._demand_events(product_id, wh_ids)
        (
            supply,
            unattributed_in_transit,
            unplaceable_on_order,
            ordered_pairs,
        ) = self._supply_events(product_id, wh_ids)
        qty_ordered_not_incoming = round(
            sum(q for at, q in ordered_pairs if at is None or at <= resolved_horizon_end),
            QTY_PRECISION,
        )
        opening = self._opening(product_id, wh_ids)
        timeline = build_timeline(
            opening, demand + supply, floor=floor, horizon_end=resolved_horizon_end
        )

        # Passed through as-is, NOT defaulted to the pool. Unspecified means "no particular
        # bin", which is what the endpoint asks, and `availability` then reports own as 0
        # and the pool bin's stock under `pool`. Defaulting it to `pool_id` would relabel
        # shared stock as a private bin and make "use the pool" unsayable.
        availability = self.availability(
            product_id,
            own_warehouse_id=own_warehouse_id,
            pool_id=pool_id,
        )
        # The endpoint is addressed by product plus pool and has no line to resolve, so
        # the AGGREGATE demand the timeline reports is what gets resolved. Empty only when
        # there is no demand at all: a fully covered demand still resolves to own / brw
        # slices with `buy_qty` zero, which IS the "use the pool, do not buy" answer this
        # module exists to give.
        pool_demand = round(
            sum(-row.event.qty for row in timeline.rows if row.event.kind == DEMAND), 4
        )
        # WHERE today's cover comes from. This answers a different question from `buy_qty`
        # and must not be confused with it: it turns "you have cover" into an instruction
        # somebody can act on (own bin, shared pool, another holder's bin).
        allocations = resolve_sources(pool_demand, availability)
        # What must be BOUGHT is what DATED supply cannot cover, which the timeline has
        # already worked out. The residual of `resolve_sources` is a dateless figure: it
        # compares total demand against a snapshot of current stock and ignores every
        # arrival, so it recommended buying 100 units while 500 were already on the water
        # and due to land first - printed in an alarm colour two inches from a healthy
        # closing balance. A planner who acts on the loud number buys a second container;
        # one who learns to ignore it stops reading the panel. `peak_deficit` is the worst
        # the balance ever gets against the floor, so it is also right in the opposite
        # direction: supply dated AFTER the commitment it would cover still leaves the buy
        # standing, which netting on the closing balance would silently drop.
        buy_qty = timeline.peak_deficit
        # The `order` slice `resolve_sources` produces is that same dateless residual, so it
        # is replaced by the timeline's figure rather than left to contradict it two inches
        # away on the screen. The own / pool / other slices stand: they describe stock a
        # person can pick today, which is a different question and still worth answering.
        allocations = [a for a in allocations if a.source_type != SOURCE_ORDER]
        if buy_qty >= EPSILON:
            allocations.append(SourceAllocation(source_type=SOURCE_ORDER, qty=buy_qty))

        return Coverage(
            product_id=product_id,
            product_code=(product.product_code if product else ""),
            product_name=(product.product_name if product else None),
            pool_id=pool_id,
            pool_code=pool_code,
            locations=tuple(w.warehouse_code for w in members),
            floor=float(floor),
            opening_balance=opening,
            timeline=timeline,
            availability=availability,
            allocations=tuple(allocations),
            buy_qty=buy_qty,
            # Derived from the SAME figure as `buy_qty`, never from the allocations, or the
            # verdict sentence and the number beside it can disagree.
            use_stock=buy_qty < EPSILON,
            undated_demand=tuple(undated),
            transfer_proposals=tuple(
                self.transfer_proposals(
                    product_id,
                    pool_id=pool_id,
                    pool_code=pool_code,
                    member_ids=wh_ids,
                    needed_qty=buy_qty,
                    config=config,
                    today=today,
                )
            ),
            horizon_months=config.horizon_months,
            horizon_end=resolved_horizon_end,
            computed_at=computed_at,
            unattributed_in_transit_qty=unattributed_in_transit,
            unplaceable_demand_qty=unplaceable_demand,
            unplaceable_on_order_qty=unplaceable_on_order,
            qty_ordered_not_incoming=qty_ordered_not_incoming,
        )

    def network_positions(
        self,
        product_ids: Iterable[str],
        *,
        horizon_end: Optional[date] = None,
        horizon_months: Optional[int] = None,
    ) -> dict[str, NetworkPosition]:
        """Dated network positions for MANY products, keyed by product id.

        Three queries for the events plus one for the locations, then ``build_timeline`` per
        product over in-memory events. That ratio is the whole point: the Summary Order
        Report covers thousands of products, and calling ``coverage_for`` per product would
        be three queries each. The arithmetic is the SAME ``build_timeline`` the coverage
        panel uses, so the shortfall a report row states and the shortfall the panel draws
        for the same product cannot disagree - which is the one class of disagreement that
        ends trust in a planning tool.

        The horizon is a SINGLE window for the batch rather than resolved per product. A
        report is read as one book and a row-by-row horizon would mean two rows stating
        positions over different windows without saying so. ``horizon_months`` names the
        window; ``horizon_end`` overrides it outright for a caller reproducing a past run.

        Products with no events at all still get a position, from their opening stock. A
        product absent from the result would read as "not planned" when the truth is
        "nothing is happening to it", and the report has a row for it either way.
        """
        pids = [str(p) for p in product_ids]
        if not pids:
            return {}

        wh_ids = self.availability_warehouse_ids()
        today = to_naive_datetime(datetime.now(MALAYSIA_TZ)).date()
        months = horizon_months or DEFAULT_PLANNING_HORIZON_MONTHS
        resolved_horizon_end = horizon_end or _add_months(today, months)

        openings = self._opening_many(pids, wh_ids)
        demand = self._demand_events_many(pids, wh_ids)
        supply = self._supply_events_many(pids, wh_ids)

        out: dict[str, NetworkPosition] = {}
        for pid in pids:
            d_events, undated, unplaceable_demand = demand.get(pid, ([], [], 0.0))
            s_events, unattributed, unplaceable_on_order, ordered_pairs = supply.get(
                pid, ([], 0.0, 0.0, ())
            )
            opening = openings.get(pid, 0.0)
            timeline = build_timeline(
                opening,
                d_events + s_events,
                floor=0.0,
                horizon_end=resolved_horizon_end,
            )
            # Summed off the SAME events the balance used, never re-queried. A separate
            # aggregate would drift from the timeline the moment a predicate changed, and the
            # row would then show a quantity on order that the shortfall beside it did not
            # account for.
            # `qty_on_order` is the PLACED-order figure and is NOT summed off the events,
            # because a purchase order produces no event: it is reported, not counted. Only
            # `qty_in_transit` below comes off the same events the balance used.
            on_order = sum(
                q for at, q in ordered_pairs
                if at is None or at <= resolved_horizon_end
            )
            in_transit = sum(
                e.qty for e in s_events
                if e.supply_stage == SUPPLY_IN_TRANSIT
                and (e.at is None or e.at <= resolved_horizon_end)
            )
            out[pid] = NetworkPosition(
                product_id=pid,
                on_hand=round(opening, QTY_PRECISION),
                qty_on_order=round(on_order, QTY_PRECISION),
                qty_in_transit=round(in_transit, QTY_PRECISION),
                shortfall=timeline.peak_deficit,
                closing_balance=timeline.closing_balance,
                shortfall_at=timeline.shortfall.at if timeline.shortfall else None,
                horizon_end=resolved_horizon_end,
                undated_demand_qty=round(
                    sum(u.qty for u in undated), QTY_PRECISION
                ),
                unattributed_in_transit_qty=unattributed,
                unplaceable_demand_qty=unplaceable_demand,
                unplaceable_on_order_qty=unplaceable_on_order,
            )
        return out

    def resolve_line(
        self, product_id: str, *, warehouse_id: str, qty: float, allow_borrow: bool = True
    ):
        """Where ONE demand line's stock should come from. Mr Loo's buy-or-use-pool call."""
        pool_id = self.pool_for_location(warehouse_id)
        # SOURCE_OWN: a line standing in its own location is not borrowing from anyone, and
        # this string is persisted on the allocation.
        avail = self.availability(
            product_id,
            own_warehouse_id=warehouse_id,
            pool_id=pool_id,
            self_pool_bucket=SOURCE_OWN,
        )
        return resolve_sources(qty, avail, allow_borrow=allow_borrow)
