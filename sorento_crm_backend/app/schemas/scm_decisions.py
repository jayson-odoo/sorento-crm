"""SCM M4 Slice B — decision + PO-flow request/response schemas.

Mirror the FE contract at the top of ``reorder/services/decisionService.ts`` /
``services/purchaseOrderService.ts`` + ``reorder/types/decisions.types.ts``. No
UUIDs surface in display fields — suppliers by code, POs by number.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class AcceptResult(BaseModel):
    # Accept/Adjust are STAGED — no PO exists until Confirm decisions, so the PO
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
