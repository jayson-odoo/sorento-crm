"""Request bodies for the service job product lines (after-sales P2)."""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel


class ServiceJobProductCreate(BaseModel):
    product_id: str
    kind_id: Optional[str] = None
    purchase_date: Optional[date] = None
    defect_type_id: Optional[str] = None


class ServiceJobProductUpdate(BaseModel):
    kind_id: Optional[str] = None
    purchase_date: Optional[date] = None
    defect_type_id: Optional[str] = None
