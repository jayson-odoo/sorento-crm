"""Wire shapes for divergence reconciliation (P8a). Contract section 6d."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class IngestLinePayload(BaseModel):
    """One line of an AutoCount sales order, as the ESB will send it in stage 2."""

    line_no: Optional[int] = None
    product_code: Optional[str] = None
    description: Optional[str] = None
    qty: Decimal = Decimal("0")
    unit_price: Decimal = Decimal("0")
    uom: Optional[str] = None
    delivery_date: Optional[date] = None


class IngestDocumentPayload(BaseModel):
    doc_no: Optional[str] = None
    customer_code: Optional[str] = None
    customer_po_no: Optional[str] = None
    area_group: Optional[str] = None
    terms: Optional[str] = None
    total_amount: Optional[Decimal] = None
    lines: List[IngestLinePayload] = Field(default_factory=list)


class IngestResponse(BaseModel):
    outcome: str = Field(description="matched | divergent | ambiguous | unmatched")
    project_sales_order_id: Optional[str] = None
    divergence_id: Optional[str] = None
    differing_count: int = 0
    candidate_ids: List[str] = Field(default_factory=list)
    message: str = ""


class DivergenceRow(BaseModel):
    id: str
    scope: str
    presence: str
    so_line_id: Optional[str] = None
    line_no: Optional[int] = None
    product_code: Optional[str] = None
    ours: Dict[str, Any] = Field(default_factory=dict)
    theirs: Dict[str, Any] = Field(default_factory=dict)
    differing_fields: List[str] = Field(default_factory=list)
    needs_answer: bool = False
    resolution: Optional[str] = None
    reason: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None


class DivergenceDetail(BaseModel):
    id: str
    project_sales_order_id: str
    project_id: Optional[str] = None
    project_title: Optional[str] = None
    provisional_ref: Optional[str] = None
    autocount_doc_no: Optional[str] = None
    status: str
    ingest_source: Optional[str] = None
    compared_count: int = 0
    agreeing_count: int = 0
    differing_count: int = 0
    unresolved_count: int = 0
    corrective_publish_required: bool = False
    corrective_publish_taken_at: Optional[datetime] = None
    detected_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    rows: List[DivergenceRow] = Field(default_factory=list)


class DivergenceRowSummary(BaseModel):
    id: str
    project_sales_order_id: str
    project_id: Optional[str] = None
    project_title: Optional[str] = None
    sales_order_ref: Optional[str] = None
    provisional_ref: Optional[str] = None
    autocount_doc_no: Optional[str] = None
    status: str
    compared_count: int = 0
    agreeing_count: int = 0
    differing_count: int = 0
    unresolved_count: int = 0
    corrective_publish_required: bool = False
    detected_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    age_days: int = 0


class ResolveRowRequest(BaseModel):
    resolution: str = Field(description="accept_theirs | keep_ours")
    reason: str = Field(min_length=1)
