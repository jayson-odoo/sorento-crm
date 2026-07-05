"""Market-segment catalog + assignment schemas."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class MarketSegmentBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True
    sort_order: Optional[int] = None


class MarketSegmentCreate(MarketSegmentBase):
    code: str


class MarketSegmentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class MarketSegmentResponse(MarketSegmentBase):
    model_config = ConfigDict(from_attributes=True)
    code: str


class MarketSegmentCodesUpdate(BaseModel):
    """Replace a contact's / member's segment assignment with this exact set."""
    codes: List[str] = []


class MarketSegmentCodesResponse(BaseModel):
    codes: List[str] = []
