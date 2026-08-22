"""SCM S3b - Summary Order Report response schemas (UAC Groups C2, C3).

Field for field the wire contract in
``sorento_crm_frontend/app/(protected)/scm/reorder/types/summaryOrder.types.ts``, which the
frontend was built against before this endpoint existed. That file wins on any disagreement.

Three rules are baked into the shapes, all of them hard:

* **No identifiers.** Everything is addressed by human code - product code, supplier code, SO
  number, pool code - so a UUID cannot reach a screen a planner reads aloud to a supplier.
  ``run_id`` is the single exception and it is opaque: it says which week is being read and is
  never rendered.
* **On order and in transit stay separate.** Their sum drives the balance; the split is
  displayed because only the on-order half is still negotiable.
* **A missing input is NULL, never 0.** ``avg_daily_demand`` is absent for roughly 38% of the
  book and ``unit_volume_cbm`` for 84%. A zero would read as "already out of stock" and "no
  space needed", both of which are decisions taken on a figure nobody measured, so the field
  is Optional and the screen names the gap.

Dates serialise as ``YYYY-MM-DD`` and timestamps as NAIVE Malaysia wall-clock strings: an
offset-aware value gets re-normalised to UTC downstream and renders eight hours out, a bug
this repo has already shipped once.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class OrderSummaryLocationAllocationOut(BaseModel):
    """One location's share of a Product-grain chosen quantity (AC-F08).

    The stored shares sum exactly to `chosen_qty`: the allocator apportions integer minor
    units of the row's frozen UOM precision, so there is no rescaling residue to explain
    away. Exact in the persisted decimals - adding these floats back up at a non-zero
    precision can still land an ulp away, which is binary floating point and not a split
    that lost a unit.
    """

    warehouse_code: Optional[str] = None
    warehouse_name: Optional[str] = None
    allocated_qty: float = 0.0


class OrderSummaryRowOut(BaseModel):
    """One product, network wide (AC-C2.1).

    Channel is analysis INSIDE this row (front planning 5.3): Project, Retail and
    unclassified are separate demand readings, while stock, incoming, the PO book and the
    reorder level stay single shared facts. Nothing here keys on channel.
    """

    product_code: str
    product_name: Optional[str] = None
    uom: Optional[str] = None

    # The run's stamp, repeated per row so a row is self-describing. NULL grain +
    # `is_legacy` true is a run created before the front-planning contract: its channel
    # fields below are NULL and are never inferred (AC-F10).
    decision_grain: Optional[str] = None
    is_legacy: bool = False

    on_hand: float = 0.0
    project_demand: float = 0.0
    dealer_outstanding: float = 0.0
    # The same stored column under the name every screen uses (AC-E03).
    retail_outstanding: float = 0.0

    # Front planning. Every one of these is NULL on a legacy run.
    project_buy_qty: Optional[float] = None
    retail_replenishment_qty: Optional[float] = None
    unclassified_demand_qty: Optional[float] = None
    earliest_project_need_date: Optional[str] = None
    uom_decimal_places: Optional[int] = None
    # No `channel_calculation_basis` here on purpose: the row's per-location evidence is a
    # drill, and the report is unpaginated, so shipping it per row sent thousands of
    # location entries to every reader for a panel most of them never open. It is served
    # per product by `GET /order-summary/{code}/locations`; the stored column is unchanged.
    location_allocations: Optional[List[OrderSummaryLocationAllocationOut]] = None
    # Separate columns (AC-C2.2): only the on-order half can still be re-dated or cancelled.
    qty_on_order: float = 0.0
    qty_in_transit: float = 0.0

    # The DATED shortfall from the Coverage Timeline, not `on hand + on order - demand`: a
    # positive net position is still short when the supply that lifts it is dated after the
    # demand it is read as covering.
    shortfall: float = 0.0
    suggested_qty: float = 0.0

    chosen_qty: Optional[float] = None
    chosen_supplier_code: Optional[str] = None
    chosen_supplier_name: Optional[str] = None
    decided_by: Optional[str] = None
    decided_at: Optional[str] = None

    avg_daily_demand: Optional[float] = None
    unit_volume_cbm: Optional[float] = None
    spare_lands_at: Optional[str] = None

    project_demand_line_count: int = 0
    dealer_outstanding_line_count: int = 0
    retail_outstanding_line_count: int = 0
    # How many open SO lines carry no persisted demand class, so the exception can be
    # opened rather than only counted (AC-E02).
    unclassified_line_count: int = 0
    # NULL when nothing is outstanding, which is not the same fact as 0 days outstanding.
    max_days_outstanding: Optional[int] = None


class OrderSummaryReportOut(BaseModel):
    """The whole frozen report for one run (AC-C2.9)."""

    run_id: str
    # The grain STAMPED on the run at creation, never the live policy setting (AC-F01).
    decision_grain: Optional[str] = None
    is_legacy: bool = False
    # Both are NULL for a run that froze no rows: inventing today's date would label a book
    # that was never built.
    as_of: Optional[str] = None
    generated_at: Optional[str] = None
    rows: List[OrderSummaryRowOut] = Field(default_factory=list)


class ProjectDemandLineOut(BaseModel):
    """One contributing project line (AC-C2.3 / AC-E07)."""

    project_name: str
    so_number: str
    qty: float
    required_date: Optional[str] = None
    # The human line number and the decision this Buy came from, so Purchasing can trace
    # it without a UUID crossing the wire. Both NULL on a line the AutoCount upload has
    # not reconciled to a project line, and `decision_ref` NULL on one whose SO has no
    # confirmed decision - it is counted through the sheet leg instead.
    line_no: Optional[int] = None
    warehouse_code: Optional[str] = None
    decision_ref: Optional[str] = None


class DealerDemandLineOut(BaseModel):
    """One contributing dealer or retail line (AC-C2.4)."""

    dealer_name: str
    so_number: str
    qty: float
    # The column the printed sheet has no room for, and the reason two units can outrank two
    # hundred.
    days_outstanding: int
    ordered_date: Optional[str] = None


class UnclassifiedDemandLineOut(BaseModel):
    """One SO line whose demand class is missing, shown as an exception (AC-E02)."""

    customer_name: str
    so_number: str
    line_no: Optional[int] = None
    qty: float
    ordered_date: Optional[str] = None
    # In the words the exception is recorded with, so the screen states the data-quality
    # job rather than inventing a third channel.
    exception: str


class OrderSummaryDemandDrillOut(BaseModel):
    """What one aggregate opens to. SERVER-sorted, so the client never re-sorts."""

    product_code: str
    kind: str
    total_qty: float
    project_lines: List[ProjectDemandLineOut] = Field(default_factory=list)
    retail_lines: List[DealerDemandLineOut] = Field(default_factory=list)
    # The same lines under the legacy name, so a caller written against the older payload
    # keeps rendering.
    dealer_lines: List[DealerDemandLineOut] = Field(default_factory=list)
    unclassified_lines: List[UnclassifiedDemandLineOut] = Field(default_factory=list)
    # Trailing-window historical order context (captain, 20 Aug follow-up): "for project
    # here, you need to show the past year project order for this item; for retail, the
    # last 3 months, for user to judge whether to top up the quantity ordered." Distinct
    # from `total_qty` (still-open demand): this is the flow of orders PLACED, whatever
    # their status today.
    project_12m_qty: float = 0.0
    retail_3m_qty: float = 0.0
    project_window_months: Optional[int] = None
    retail_window_months: Optional[int] = None
    demand_context_as_of: Optional[str] = None


class SupplierCandidateOut(BaseModel):
    """One supplier the item could be bought from (AC-C2.5).

    Every cost is EX-WORKS in ``currency`` (AC-C3.4). Neither figure is a landed cost:
    freight and duty are not in the purchase order.
    """

    supplier_code: str
    supplier_name: str
    currency: Optional[str] = None
    last_po_cost: Optional[float] = None
    last_po_date: Optional[str] = None
    last_po_number: Optional[str] = None
    last_incoming_cost: Optional[float] = None
    # What `last_incoming_cost` is quoted in, from the shipment line itself. Separate from
    # ``currency`` on purpose: the packing-list ingest stores a supplier's own currency
    # (often CNY) and the PO may be in another, so one code cannot label both figures.
    last_incoming_currency: Optional[str] = None
    last_incoming_date: Optional[str] = None
    # Incoming minus ordered. A positive number means the supplier repriced upward after we
    # committed (AC-C3.3). NULL when the two sides are not comparable.
    cost_variance: Optional[float] = None
    on_time_rate: Optional[float] = None
    lead_time_days: Optional[int] = None
    # 0 means they have never delivered THIS item, and must be SENT as 0 rather than omitted
    # so the screen can say so instead of letting a low cost make them look merely cheap.
    delivered_line_count: int = 0
    is_stale: bool = False
    stale_days: Optional[int] = None
    moq: Optional[float] = None
    order_multiple: Optional[float] = None


class OrderSummarySuppliersOut(BaseModel):
    product_code: str
    # The threshold behind `is_stale`, so the screen can say what stale means.
    stale_after_days: int
    candidates: List[SupplierCandidateOut] = Field(default_factory=list)


class OrderSummaryDecisionIn(BaseModel):
    """What a decision writes (AC-C2.7, AC-C2.8).

    ``chosen_qty`` ABOVE the shortfall is valid and is not warned on. Zero is valid too: it is
    the "use the pool, do not buy" answer, and it has to be recordable so the PO worklist
    reconciles one-for-one against the decisions. Negative is refused by the service.
    """

    run_id: str
    # At most the row's FROZEN `uom_decimal_places` fractional digits (AC-F12). Finer is
    # refused with 422 `chosen_qty_precision`; a write against the other grain or a legacy
    # run is refused with 409.
    chosen_qty: float
    supplier_code: str


class OrderSummaryDecisionOut(BaseModel):
    product_code: str
    chosen_qty: float
    # Kept beside the chosen figure, never replaced by it (AC-C2.8).
    suggested_qty: float
    chosen_supplier_code: str
    chosen_supplier_name: str
    decided_by: str
    decided_at: str
    # The allocator rerun's split of the accepted quantity back to the frozen location
    # inputs, summing exactly to `chosen_qty` (AC-F12). Empty on a use-pool decision of 0.
    location_allocations: List[OrderSummaryLocationAllocationOut] = Field(
        default_factory=list)


class OrderSummaryLocationRowOut(BaseModel):
    """One member location behind a product row (AC-F08).

    Demand is split by channel; supply is NOT. Stock, incoming SPO, the PO book and the
    reorder level are single shared facts of the product-location, counted once (AC-F07).
    A NULL `reorder_level` means nobody has set one, which is not a level of zero.
    """

    warehouse_code: Optional[str] = None
    warehouse_name: Optional[str] = None
    project_need: Optional[float] = None
    retail_need: Optional[float] = None
    # The unconfirmed sheet-origin project leg. Already NETTED inside `retail_need`, so it
    # is a reading and never an addend: `project_need` (confirmed Buy) plus `retail_need`
    # is still the whole actionable need. NULL on a run frozen before the split.
    project_sheet_need: Optional[float] = None
    unclassified_need: Optional[float] = None
    on_hand: float = 0.0
    incoming_spo: float = 0.0
    on_order_po: float = 0.0
    reorder_level: Optional[float] = None
    avg_daily_demand: Optional[float] = None
    allocated_qty: Optional[float] = None


class OrderSummaryLocationsOut(BaseModel):
    """What a product row's Locations drill opens to."""

    product_code: str
    decision_grain: Optional[str] = None
    is_legacy: bool = False
    uom: Optional[str] = None
    uom_decimal_places: Optional[int] = None
    # Repeated from the row so the drill reconciles against the figure it opened.
    suggested_qty: float = 0.0
    chosen_qty: Optional[float] = None
    locations: List[OrderSummaryLocationRowOut] = Field(default_factory=list)


# =========================================================================== #
# S4 - the PO creation worklist (UAC Group E2)
# =========================================================================== #


class PoWorklistRowOut(BaseModel):
    """One decided product, ready to be keyed.

    Three nullable fields are load-bearing. ``need_by`` is absent whenever nothing
    committed is uncovered, which is most of the book; ``place_by`` and ``lead_time_days``
    are absent when the lead time is unknown. A fabricated place-by date is worse than none
    because it is acted on.
    """

    product_code: str
    product_name: Optional[str] = None
    uom: Optional[str] = None
    # The run's grain, on the row as well as the response: which shape this row is
    # (product + split, or location) is not something to infer from which fields are null.
    decision_grain: Optional[str] = None
    # The precision the quantity was DECIDED at, so it is keyed at that precision.
    uom_decimal_places: Optional[int] = None
    # A LOCATION-grain row names its location; a PRODUCT-grain row names none and carries
    # its split instead. Never both: a row with both would invite keying the same units
    # twice (AC-F09).
    warehouse_code: Optional[str] = None
    warehouse_name: Optional[str] = None
    location_allocations: Optional[List[OrderSummaryLocationAllocationOut]] = None

    # Zero is the use-pool decision: no purchase order is needed (AC-E2.5).
    chosen_qty: float
    suggested_qty: float
    chosen_supplier_code: Optional[str] = None
    chosen_supplier_name: Optional[str] = None
    decided_by: str
    decided_at: Optional[str] = None

    need_by: Optional[str] = None
    place_by: Optional[str] = None
    lead_time_days: Optional[int] = None
    is_late: bool = False

    last_po_cost: Optional[float] = None
    last_po_currency: Optional[str] = None
    cash_committed: Optional[float] = None

    keyed_status: str = "not_keyed"
    keyed_by: Optional[str] = None
    keyed_at: Optional[str] = None


class PoWorklistOut(BaseModel):
    run_id: str
    as_of: Optional[str] = None
    # The worklist reads ONE grain, the run's own (AC-F09). NULL on a legacy run, which
    # has no actionable grain and therefore no rows.
    decision_grain: Optional[str] = None
    # `1` on a front-planning run, NULL on a legacy one. A legacy run is identified by
    # THIS being null, not by a missing grain, so the reader gets the real value rather
    # than inferring one from the grain.
    front_planning_contract_version: Optional[int] = None
    rows: List[PoWorklistRowOut] = Field(default_factory=list)


class KeyedStatusIn(BaseModel):
    """Setting the keyed-into-AutoCount status (AC-E2.2).

    Any transition is allowed, including backwards: somebody who marked a row keyed by
    mistake has to be able to unmark it.
    """

    run_id: str
    keyed_status: str
    # Which location's order, on a run decided at LOCATION grain, where each location is
    # its own purchase order. Omitted on a product-grain run, which keys the product.
    warehouse_code: Optional[str] = None


class KeyedStatusOut(BaseModel):
    product_code: str
    # Echoed on a location-grain write; null when the product row was keyed.
    warehouse_code: Optional[str] = None
    keyed_status: str
    # A human NAME, never a user id: it is rendered beside the row.
    keyed_by: str
    keyed_at: str
