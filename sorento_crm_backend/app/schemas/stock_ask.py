"""Chatbot stock ask v2 S5/S6: the asks record as the CRM Asks tab and the portal's Customer
asks page read and edit it. Names, never bare ids: the row id is the only id on the wire,
and it is what a PATCH addresses."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class StockAskResponse(BaseModel):
    id: str
    customer_name: Optional[str] = None
    contact_name: Optional[str] = None
    product_code: str
    product_name: Optional[str] = None
    quantity: int
    branch: str
    answer_summary: str
    notified_agent: bool
    notify_skip_reason: Optional[str] = None
    state: str
    note: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class StockAskUpdate(BaseModel):
    """What the office (and the sales agent on the portal) edits: state and note only.
    A field left out is left alone."""

    state: Optional[Literal["open", "done"]] = None
    note: Optional[str] = Field(None, max_length=4000)
