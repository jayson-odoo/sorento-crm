"""Request/response schemas for commercial sales order progression."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class WinningPathProgressRequest(BaseModel):
    quotation_code: str = Field(..., min_length=1, max_length=64)
    revision_number: int = Field(..., ge=1)
    sales_order_number: Optional[str] = Field(None, max_length=100)


class WinningPathProgressResponse(BaseModel):
    tender_code: str
    tender_lifecycle: str
    tender_outcome: str
    sales_order_number: str
    quotation_code: str
    revision_number: int


class TenderCloseOutcomeRequest(BaseModel):
    tender_outcome: str = Field(..., description="lost | withdrawn | no_award")
    outcome_notes: Optional[str] = None


class TenderCloseOutcomeResponse(BaseModel):
    tender_code: str
    tender_lifecycle: str
    tender_outcome: str
