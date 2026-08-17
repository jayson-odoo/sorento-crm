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


class OrderSummaryRowOut(BaseModel):
    """One product, network wide (AC-C2.1)."""

    product_code: str
    product_name: Optional[str] = None
    uom: Optional[str] = None

    on_hand: float = 0.0
    project_demand: float = 0.0
    dealer_outstanding: float = 0.0
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
    # NULL when nothing is outstanding, which is not the same fact as 0 days outstanding.
    max_days_outstanding: Optional[int] = None


class OrderSummaryReportOut(BaseModel):
    """The whole frozen report for one run (AC-C2.9)."""

    run_id: str
    # Both are NULL for a run that froze no rows: inventing today's date would label a book
    # that was never built.
    as_of: Optional[str] = None
    generated_at: Optional[str] = None
    rows: List[OrderSummaryRowOut] = Field(default_factory=list)


class ProjectDemandLineOut(BaseModel):
    """One contributing project line (AC-C2.3)."""

    project_name: str
    so_number: str
    qty: float
    required_date: Optional[str] = None


class DealerDemandLineOut(BaseModel):
    """One contributing dealer or retail line (AC-C2.4)."""

    dealer_name: str
    so_number: str
    qty: float
    # The column the printed sheet has no room for, and the reason two units can outrank two
    # hundred.
    days_outstanding: int
    ordered_date: Optional[str] = None


class OrderSummaryDemandDrillOut(BaseModel):
    """What one aggregate opens to. SERVER-sorted, so the client never re-sorts."""

    product_code: str
    kind: str
    total_qty: float
    project_lines: List[ProjectDemandLineOut] = Field(default_factory=list)
    dealer_lines: List[DealerDemandLineOut] = Field(default_factory=list)


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
    rows: List[PoWorklistRowOut] = Field(default_factory=list)


class KeyedStatusIn(BaseModel):
    """Setting the keyed-into-AutoCount status (AC-E2.2).

    Any transition is allowed, including backwards: somebody who marked a row keyed by
    mistake has to be able to unmark it.
    """

    run_id: str
    keyed_status: str


class KeyedStatusOut(BaseModel):
    product_code: str
    keyed_status: str
    # A human NAME, never a user id: it is rendered beside the row.
    keyed_by: str
    keyed_at: str
