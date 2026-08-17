"""Allocation schemas (P9, AC-H1 to AC-H5).

Quantities are typed ``Decimal`` and therefore render as JSON STRINGS, matching every
other project-sales response: a float round trip on a 5,950 piece pre-order is a rounding
argument nobody can win.

Ranked candidates are NOT modelled as anything storable on purpose. They are recomputed on
every request from the live `stock` rows, so no response here is ever written back.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

ALLOWED_SOURCE_TYPES = ("brw", "own", "other_project", "order")


# ------------------------------------------------------------------- candidates


class CandidateHolder(BaseModel):
    """The project a pile is held for, and the CS to ask (AC-H2)."""

    project_id: str
    project_code: str
    project_title: Optional[str] = None
    cs_user_id: Optional[str] = None
    cs_name: Optional[str] = None
    qty: Decimal


class AllocationCandidate(BaseModel):
    rank: int
    source_type: str
    warehouse_id: Optional[str] = None
    warehouse_code: Optional[str] = None
    warehouse_name: Optional[str] = None
    on_hand: Decimal
    reserved: Decimal
    held_for_this_project: Decimal
    held_for_other_projects: Decimal
    committed: Decimal
    available: Decimal
    allocatable: Decimal
    claimable: Decimal
    requires_claim: bool
    is_project_location: bool
    holders: List[CandidateHolder] = Field(default_factory=list)
    #: An open claim this project already raised for this location, when there is one.
    open_claim_id: Optional[str] = None
    open_claim_state: Optional[str] = None


class PlannedSource(BaseModel):
    """One leg of the proposal, free stock only. Held stock is never planned."""

    warehouse_id: str
    warehouse_code: Optional[str] = None
    qty: Decimal


class AllocationCandidateList(BaseModel):
    line_id: str
    line_no: int
    product_code: Optional[str] = None
    description: Optional[str] = None
    qty: Decimal
    uom: Optional[str] = None
    delivery_date: Optional[date] = None
    project_code: str
    brw_warehouse_code: Optional[str] = None
    candidates: List[AllocationCandidate]
    plan: List[PlannedSource]
    shortfall: Decimal
    covered: bool


# ------------------------------------------------------------ the decision itself


class AllocationSourceInput(BaseModel):
    source_type: str
    warehouse_id: Optional[str] = None
    #: Required for `other_project`: whose stock is being taken.
    source_project_id: Optional[str] = None
    qty: Decimal

    @field_validator("source_type")
    @classmethod
    def _known_source(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if cleaned not in ALLOWED_SOURCE_TYPES:
            raise ValueError(
                f"Unknown source. Use one of: {', '.join(ALLOWED_SOURCE_TYPES)}."
            )
        return cleaned

    @field_validator("qty")
    @classmethod
    def _positive(cls, value: Decimal) -> Decimal:
        if value is None or value <= 0:
            raise ValueError("A source must carry a quantity above zero.")
        return value


class AllocationConfirmRequest(BaseModel):
    sources: List[AllocationSourceInput]

    @field_validator("sources")
    @classmethod
    def _at_least_one(cls, value: List[AllocationSourceInput]):
        if not value:
            raise ValueError("Name at least one source, or clear the allocation instead.")
        return value


class AllocationSourceRow(BaseModel):
    id: str
    source_type: str
    warehouse_id: Optional[str] = None
    warehouse_code: Optional[str] = None
    warehouse_name: Optional[str] = None
    source_project_id: Optional[str] = None
    source_project_code: Optional[str] = None
    source_project_cs_name: Optional[str] = None
    qty: Decimal
    confirmed: bool
    confirmed_by_name: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    claim_id: Optional[str] = None
    claim_state: Optional[str] = None
    claim_reason: Optional[str] = None


class SalesOrderLineAllocationRow(BaseModel):
    """One SO line and where it is coming from, for the allocation surface."""

    line_id: str
    line_no: int
    product_id: Optional[str] = None
    product_code: Optional[str] = None
    description: Optional[str] = None
    qty: Decimal
    uom: Optional[str] = None
    delivery_date: Optional[date] = None
    #: unallocated | pending_claim | refused | partial | confirmed
    state: str
    stock_location: Optional[str] = None
    allocated_qty: Decimal
    outstanding_qty: Decimal
    sources: List[AllocationSourceRow] = Field(default_factory=list)


# ------------------------------------------------------------------------ claims


class AllocationClaimRequest(BaseModel):
    warehouse_id: str
    to_project_id: str
    qty: Decimal

    @field_validator("qty")
    @classmethod
    def _positive(cls, value: Decimal) -> Decimal:
        if value is None or value <= 0:
            raise ValueError("Ask for a quantity above zero.")
        return value


class AllocationRefuseRequest(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def _reason_required(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if len(cleaned) < 3:
            raise ValueError(
                "Say why the stock cannot be released. A refusal without a reason "
                "sends the asker back to a phone call."
            )
        return cleaned


class AllocationClaimRow(BaseModel):
    id: str
    state: str
    # Whether THIS viewer may accept or refuse it, decided by the same authority that
    # gates the endpoints. The UI must never offer an answer the server would reject.
    can_answer: bool = False
    qty: Decimal
    reason: Optional[str] = None
    from_project_id: str
    from_project_code: str
    from_project_title: Optional[str] = None
    from_project_cs_name: Optional[str] = None
    to_project_id: str
    to_project_code: str
    to_project_title: Optional[str] = None
    to_project_cs_name: Optional[str] = None
    product_id: Optional[str] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    warehouse_id: Optional[str] = None
    warehouse_code: Optional[str] = None
    so_line_id: Optional[str] = None
    sales_order_id: Optional[str] = None
    sales_order_ref: Optional[str] = None
    line_no: Optional[int] = None
    delivery_date: Optional[date] = None
    requested_by_name: Optional[str] = None
    decided_by_name: Optional[str] = None
    decided_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
