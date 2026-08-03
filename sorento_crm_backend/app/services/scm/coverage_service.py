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
transfer proposal a person accepts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models.inventory import Stock, Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import (
    InboundShipment,
    InboundShipmentLine,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
)
from app.models.product import Product
from app.services.scm.coverage_timeline import (
    DEMAND,
    SUPPLY,
    SUPPLY_IN_TRANSIT,
    SUPPLY_ON_ORDER,
    SourceAvailability,
    TimelineEvent,
    TimelineResult,
    build_timeline,
    resolve_sources,
)

# PO statuses that represent real placed supply. Drafts are NOT supply: a draft PO is a
# recommendation nobody has committed to, and counting it would suppress the buy that
# creates it. Mirrors scm.on_order_v.
_PLACED_PO_STATUSES = ("active", "received", "partial", "closed")

# Shipment states whose lines are still inbound. Once received they are on-hand and would
# otherwise be counted twice.
_INBOUND_SHIPMENT_STATUSES = ("in_transit", "pending", "booked", "loaded", "arrived")


@dataclass(frozen=True)
class UndatedDemand:
    """A commitment with no date anywhere. Reported, never guessed at."""

    so_number: str
    item_code: str
    qty: float
    location: str


@dataclass(frozen=True)
class Coverage:
    product_id: str
    product_code: str
    pool_id: Optional[str]
    pool_code: str
    locations: tuple[str, ...]
    timeline: TimelineResult
    availability: SourceAvailability
    undated_demand: tuple[UndatedDemand, ...]


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

    def pool_for_location(self, warehouse_id: str) -> Optional[str]:
        w = self.db.query(Warehouse).filter(Warehouse.id == warehouse_id).one_or_none()
        if w is None:
            return None
        # A location with no pointer is its own pool, which is the no-suffix case.
        return w.pool_warehouse_id or w.id

    # -- events ---------------------------------------------------------------

    def _opening(self, product_id: str, wh_ids: Iterable[str]) -> float:
        total = (
            self.db.query(func.coalesce(func.sum(Stock.quantity_on_hand), 0))
            .filter(Stock.product_id == product_id, Stock.warehouse_id.in_(list(wh_ids)))
            .scalar()
        )
        return float(total or 0)

    def _demand_events(
        self, product_id: str, wh_ids: list[str]
    ) -> tuple[list[TimelineEvent], list[UndatedDemand]]:
        rows = (
            self.db.query(
                SalesOrderLine.qty_ordered,
                SalesOrderLine.qty_delivered,
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
                SalesOrderLine.product_id == product_id,
                SalesOrderLine.warehouse_id.in_(wh_ids),
                SalesOrder.status == "open",
                SalesOrderLine.line_status == "open",
                SalesOrderLine.qty_ordered > SalesOrderLine.qty_delivered,
            )
            .all()
        )

        events: list[TimelineEvent] = []
        undated: list[UndatedDemand] = []
        for r in rows:
            outstanding = float(r.qty_ordered or 0) - float(r.qty_delivered or 0)
            if outstanding <= 0:
                continue
            when = r.required_date or r.requested_delivery_date
            if when is None:
                # An undated commitment cannot be planned. Dating it "today" would fabricate
                # a shortfall, and dropping it would hide real demand, so it is surfaced.
                undated.append(
                    UndatedDemand(
                        so_number=r.so_number or "",
                        item_code=r.product_code or "",
                        qty=outstanding,
                        location=r.warehouse_code or "",
                    )
                )
                continue
            events.append(
                TimelineEvent(
                    at=when,
                    qty=-outstanding,
                    kind=DEMAND,
                    ref=r.so_number or "",
                    label=r.customer_name or (r.demand_class or ""),
                    location=r.warehouse_code or "",
                )
            )
        return events, undated

    def _supply_events(self, product_id: str, wh_ids: list[str]) -> list[TimelineEvent]:
        events: list[TimelineEvent] = []

        po_rows = (
            self.db.query(
                PurchaseOrderLine.qty_ordered,
                PurchaseOrderLine.qty_received,
                PurchaseOrderLine.expected_date,
                PurchaseOrder.expected_date.label("po_expected"),
                PurchaseOrder.po_number,
                Supplier.supplier_name,
                Warehouse.warehouse_code,
            )
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
            .outerjoin(Supplier, Supplier.id == PurchaseOrder.supplier_id)
            .outerjoin(Warehouse, Warehouse.id == PurchaseOrderLine.warehouse_id)
            .filter(
                PurchaseOrderLine.product_id == product_id,
                PurchaseOrderLine.warehouse_id.in_(wh_ids),
                PurchaseOrder.status.in_(_PLACED_PO_STATUSES),
                PurchaseOrderLine.qty_ordered > PurchaseOrderLine.qty_received,
            )
            .all()
        )
        for r in po_rows:
            incoming = float(r.qty_ordered or 0) - float(r.qty_received or 0)
            if incoming <= 0:
                continue
            events.append(
                TimelineEvent(
                    at=r.expected_date or r.po_expected,
                    qty=incoming,
                    kind=SUPPLY,
                    ref=r.po_number or "",
                    label=r.supplier_name or "",
                    location=r.warehouse_code or "",
                    supply_stage=SUPPLY_ON_ORDER,
                )
            )

        ship_rows = (
            self.db.query(
                InboundShipmentLine.quantity_shipped,
                InboundShipmentLine.quantity_received,
                InboundShipment.estimated_arrival_date,
                InboundShipment.shipment_number,
                Supplier.supplier_name,
            )
            .join(InboundShipment, InboundShipment.id == InboundShipmentLine.shipment_id)
            .outerjoin(Supplier, Supplier.id == InboundShipment.supplier_id)
            .filter(
                InboundShipmentLine.product_id == product_id,
                InboundShipment.shipment_status.in_(_INBOUND_SHIPMENT_STATUSES),
                InboundShipmentLine.quantity_shipped > InboundShipmentLine.quantity_received,
            )
            .all()
        )
        for r in ship_rows:
            incoming = float(r.quantity_shipped or 0) - float(r.quantity_received or 0)
            if incoming <= 0:
                continue
            events.append(
                TimelineEvent(
                    at=r.estimated_arrival_date,
                    qty=incoming,
                    kind=SUPPLY,
                    ref=r.shipment_number or "",
                    label=r.supplier_name or "",
                    supply_stage=SUPPLY_IN_TRANSIT,
                )
            )

        # An undated supply line cannot be placed on the axis. It is dropped from the balance
        # rather than assumed imminent, because assuming it arrives in time is exactly the
        # optimism that produces a stockout.
        return [e for e in events if e.at is not None]

    # -- availability ---------------------------------------------------------

    def availability(
        self, product_id: str, *, own_warehouse_id: Optional[str], pool_id: Optional[str]
    ) -> SourceAvailability:
        """What could cover a line right now, split by source.

        Computed live and never cached: somebody else's on-hand is stale the moment they
        ship, and acting on a stale figure is the failure this prevents.
        """
        if pool_id is None:
            return SourceAvailability()

        members = self.pool_members(pool_id)
        by_id = {w.id: w for w in members}
        rows = (
            self.db.query(Stock.warehouse_id, Stock.quantity_available)
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
            if wh_id == own_warehouse_id:
                own += q
            elif wh_id == pool_id:
                pool += q
                pool_code = by_id[wh_id].warehouse_code
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

    # -- the public entry point ----------------------------------------------

    def coverage_for(
        self,
        product_id: str,
        *,
        pool_id: str,
        floor: float = 0.0,
        horizon_end: Optional[date] = None,
    ) -> Coverage:
        members = self.pool_members(pool_id)
        wh_ids = [w.id for w in members]
        product = self.db.query(Product).filter(Product.id == product_id).one_or_none()

        demand, undated = self._demand_events(product_id, wh_ids)
        supply = self._supply_events(product_id, wh_ids)

        return Coverage(
            product_id=product_id,
            product_code=(product.product_code if product else ""),
            pool_id=pool_id,
            pool_code=next((w.warehouse_code for w in members if w.id == pool_id), ""),
            locations=tuple(w.warehouse_code for w in members),
            timeline=build_timeline(
                self._opening(product_id, wh_ids),
                demand + supply,
                floor=floor,
                horizon_end=horizon_end,
            ),
            availability=self.availability(
                product_id, own_warehouse_id=None, pool_id=pool_id
            ),
            undated_demand=tuple(undated),
        )

    def resolve_line(
        self, product_id: str, *, warehouse_id: str, qty: float, allow_borrow: bool = True
    ):
        """Where ONE demand line's stock should come from. Mr Loo's buy-or-use-pool call."""
        pool_id = self.pool_for_location(warehouse_id)
        avail = self.availability(product_id, own_warehouse_id=warehouse_id, pool_id=pool_id)
        return resolve_sources(qty, avail, allow_borrow=allow_borrow)
