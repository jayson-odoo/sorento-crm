"""SCM S3 - Coverage Timeline response schemas (UAC Group B).

Field for field the wire contract in
``sorento_crm_frontend/app/(protected)/scm/reorder/types/coverage.types.ts``, which the
frontend was built against before this endpoint existed. That file wins on any
disagreement.

Two deliberate omissions, both hard rules rather than tidiness:

* **No identifiers.** ``Coverage`` carries ``product_id`` / ``pool_id`` internally and this
  layer drops them, so a UUID cannot reach a screen a planner reads aloud to a supplier
  (AC-B2). Every reference on the wire is a human code: product code, warehouse code, SO /
  PO / shipment number, and a ``proposal_ref`` of the form ``TP-<POOLCODE>-0001``.
* **No stored timeline.** It is recomputed per request and never persisted (AC-B6), so
  ``computed_at`` is the only thing telling a planner how fresh the numbers are. It is a
  NAIVE Malaysia wall-clock string: an offset-aware value gets re-normalised to UTC
  downstream and renders eight hours out, a bug this repo has already shipped once.

Dates serialise as ``YYYY-MM-DD`` and quantities as JSON numbers (never Decimal-as-string),
because the panel does arithmetic and comparisons on them.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


class CoverageEventOut(BaseModel):
    """One dated movement. ``qty`` is signed: negative consumes, positive replenishes."""

    at: Optional[date] = Field(default=None, description="Null only on the opening row.")
    qty: float
    kind: str = Field(description="opening | demand | supply")
    ref: str = Field(description="Document number: SO / PO / shipment. Never a UUID.")
    label: str = Field(description="Human context: customer, project or supplier name.")
    location: str = Field(description="Bin or pool code the movement sits in.")
    supply_stage: Optional[str] = Field(
        default=None,
        description=(
            "on_order | in_transit, on supply rows only. Kept split because only one of "
            "the two can still be cancelled or re-dated."
        ),
    )


class CoverageRowOut(BaseModel):
    event: CoverageEventOut
    balance: float


class CoverageShortfallOut(BaseModel):
    """The first point the balance falls below the floor."""

    at: Optional[date] = None
    qty: float = Field(description="How much is missing at that point, positive.")
    ref: str = Field(description="The document that tipped it.")
    label: str = ""


class CoverageAvailabilityOut(BaseModel):
    """What could cover demand right now, split by source. Computed live, never cached."""

    own: float
    pool: float
    other: float
    pool_location: str
    other_locations: List[str] = Field(default_factory=list)


class CoverageAllocationOut(BaseModel):
    """One resolved slice of cover: own | brw | other_project | order."""

    source_type: str
    qty: float
    location: str = ""
    needs_claim: bool = Field(
        default=False, description="True when the holder has to agree first."
    )


class CoverageUndatedDemandOut(BaseModel):
    """A commitment with no date anywhere. Reported, never dated today, never dropped."""

    so_number: str
    item_code: str
    qty: float
    location: str


class CoverageTransferProposalOut(BaseModel):
    """Cover held at another site. Never netted into the balance (AC-B1d)."""

    proposal_ref: str = Field(
        description="Stable human key of the form TP-<POOLCODE>-0001. Never a UUID."
    )
    from_pool_code: str
    available_qty: float = Field(
        description="What that site holds, so the proposal can be judged, not just taken."
    )
    qty: float = Field(description="What the proposal moves.")
    transfer_cost: Optional[float] = Field(
        default=None,
        description=(
            "Cost of moving `qty`, or null when unconfigured. Never 0 by default: a free "
            "move would make the proposal look better than the truth."
        ),
    )
    lead_time_days: Optional[int] = Field(
        default=None, description="Null when unconfigured; never 0 by default."
    )
    arrives_at: Optional[date] = Field(
        default=None, description="Null whenever the lead time is null."
    )


class CoverageTimelineResult(BaseModel):
    """The whole Coverage Timeline for one product at one fulfilment pool."""

    product_code: str
    product_name: Optional[str] = None
    pool_code: str = Field(
        description="The shared pool the netting is done over, resolved from the requested "
        "location code. A location with no pool pointer is its own pool."
    )
    locations: List[str] = Field(
        default_factory=list, description="Every location drawing on that pool, code order."
    )
    floor: float = Field(
        description="The level the balance must not fall below. 0 for project demand, the "
        "reorder point for a continuous SKU."
    )
    opening_balance: float
    rows: List[CoverageRowOut] = Field(default_factory=list)
    closing_balance: float
    shortfall: Optional[CoverageShortfallOut] = None
    peak_deficit: float = Field(
        description="The worst the balance ever gets. A later event can dig deeper than "
        "the first, and buying only the first gap leaves the plan short twice."
    )
    availability: CoverageAvailabilityOut
    allocations: List[CoverageAllocationOut] = Field(
        default_factory=list,
        description="How the pool's demand resolves, cheapest source outward. Empty only "
        "when there is no demand at all, not merely when nothing is short.",
    )
    buy_qty: float = Field(description="Sum of the `order` allocations.")
    use_stock: bool = Field(description="True when `buy_qty` is zero: use the pool.")
    undated_demand: List[CoverageUndatedDemandOut] = Field(default_factory=list)
    transfer_proposals: List[CoverageTransferProposalOut] = Field(default_factory=list)
    horizon_months: int = Field(description="Planning horizon in months, from config.")
    horizon_end: date
    excluded_event_count: int = Field(
        description="Events dropped for falling beyond `horizon_end`. Stated so a bounded "
        "axis cannot read as 'nothing else is coming'."
    )
    unplaceable_demand_qty: float = Field(
        default=0.0,
        description="Committed demand carrying no warehouse at all, so it reached no pool's "
        "timeline. Stated rather than swallowed: a commitment in none of the figures is "
        "worse than one in the wrong figure.",
    )
    unplaceable_on_order_qty: float = Field(
        default=0.0,
        description="Placed on-order supply carrying no warehouse at all. Same treatment as "
        "the demand side, for the same reason.",
    )
    unattributed_in_transit_qty: float = Field(
        default=0.0,
        description="In-transit quantity no allocation places at a warehouse, so it counts "
        "for NO pool. Stated rather than dropped in silence: the same quantity added to "
        "every pool would overstate cover and suppress a purchase on each of them.",
    )
    computed_at: str = Field(
        description="Naive Malaysia wall-clock ISO timestamp, no offset and no trailing Z."
    )
