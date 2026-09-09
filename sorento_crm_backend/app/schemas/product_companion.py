""""Supplied with" companion rule schemas (PLAN-scm-supplied-with-companions.md S4).

Wire shapes match `sorento_crm_frontend/.../products/services/productCompanionService.ts`
(Phase 1, committed) exactly - that file is the contract this was built to satisfy.
"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel


class ProductCompanionHostOut(BaseModel):
    product_id: str
    item_code: Optional[str] = None
    product_name: Optional[str] = None


class ProductCompanionRuleOut(BaseModel):
    id: str
    companion_product_id: str
    companion_item_code: Optional[str] = None
    companion_product_name: Optional[str] = None
    supplier_id: Optional[str] = None
    supplier_code: Optional[str] = None
    supplier_name: Optional[str] = None
    ratio: Decimal
    is_active: bool
    hosts: List[ProductCompanionHostOut] = []
    created_at: datetime
    updated_at: datetime


class ProductCompanionRuleCreate(BaseModel):
    companion_product_id: str
    host_product_ids: List[str]
    supplier_id: Optional[str] = None
    ratio: Decimal = Decimal("1")
