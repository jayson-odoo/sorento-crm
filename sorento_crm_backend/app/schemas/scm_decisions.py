"""SCM M4 Slice B - decision + PO-flow request/response schemas.

Mirror the FE contract at the top of ``reorder/services/decisionService.ts`` /
``services/purchaseOrderService.ts`` + ``reorder/types/decisions.types.ts``. No
UUIDs surface in display fields - suppliers by code, POs by number.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class AcceptResult(BaseModel):
    # Accept/Adjust are STAGED - no PO exists until Confirm decisions, so the PO
    # fields are null on the decision response and populated only via list_decisions
    # after a confirm.
    draft_po_number: Optional[str] = None
    draft_po_id: Optional[str] = None
    supplier_name: str


class ConfirmDecisionsRequest(BaseModel):
    # Empty ids = confirm every staged decision in the run.
    ids: List[str] = Field(default_factory=list)


class ConfirmDecisionsResult(BaseModel):
    confirmed_count: int
    po_count: int


class AdjustRequest(BaseModel):
    override_qty: float = Field(..., gt=0)
    override_supplier_id: Optional[str] = None  # supplier CODE (never a UUID from the UI)
    reason_text: str


class RejectRequest(BaseModel):
    reason_text: str


class BulkAcceptRequest(BaseModel):
    run_id: str
    ids: List[str] = Field(default_factory=list)


class BulkAcceptResult(BaseModel):
    accepted_count: int
    po_count: int


class BulkRejectRequest(BaseModel):
    run_id: str
    ids: List[str] = Field(default_factory=list)
    reason_text: str


class BulkRejectResult(BaseModel):
    rejected_count: int


class RecDecision(BaseModel):
    recommendation_id: str
    status: str
    override_qty: Optional[float] = None
    override_supplier_code: Optional[str] = None
    override_supplier_name: Optional[str] = None
    reason_text: Optional[str] = None
    draft_po_number: Optional[str] = None
    draft_po_id: Optional[str] = None


class RecDecisionListResponse(BaseModel):
    data: List[RecDecision]


class BulkConfirmRequest(BaseModel):
    ids: List[str] = Field(default_factory=list)


class BulkConfirmResult(BaseModel):
    confirmed_count: int


class CreateGrResult(BaseModel):
    gr_reference: str


# ---------------------------------------------------------------------------
# S16 (captain 21 Aug) - the row decision: buy / use stock / use PO / skip, or a
# mixture. Mirrors the FE model at `reorder/lib/planDecisions.ts` (PlanDecision).
# ---------------------------------------------------------------------------

class StockTakeIn(BaseModel):
    location: str  # warehouse CODE - never a UUID from the UI
    qty: float = Field(..., gt=0)


class StockTakeOut(BaseModel):
    location: str
    location_name: Optional[str] = None
    qty: float


class RecordPlanRowDecisionRequest(BaseModel):
    kind: str  # buy | use_stock | use_po | skip | mixture
    buy_qty: Optional[float] = Field(None, ge=0)
    stock_takes: List[StockTakeIn] = Field(default_factory=list)
    po_qty: Optional[float] = Field(None, ge=0)
    po_refs: List[str] = Field(default_factory=list)  # existing PO numbers, display-only
    reason_text: Optional[str] = None


class PlanRowDecision(BaseModel):
    recommendation_id: str
    kind: str
    buy_qty: Optional[float] = None
    stock_takes: List[StockTakeOut] = Field(default_factory=list)
    po_qty: Optional[float] = None
    po_refs: List[str] = Field(default_factory=list)
    reason_text: Optional[str] = None
    # Staged like Accept/Adjust - populated only once Confirm decisions has drafted the
    # buy portion into a PO.
    draft_po_number: Optional[str] = None
    draft_po_id: Optional[str] = None


class PlanRowDecisionListResponse(BaseModel):
    data: List[PlanRowDecision]
    # The "N of Total made" header's numerator/denominator, counted server-side off what
    # is actually persisted (not client session state).
    decided_count: int
    total_count: int
