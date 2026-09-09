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


class ProductCompanionRuleListOut(BaseModel):
    """The GET envelope, declared so `ratio` serializes the SAME way POST's does -

    a `Decimal` field goes over the wire as a STRING (`"1.5000"`, the qty style every
    other quantity on this codebase uses). Undeclared, FastAPI falls back to
    `jsonable_encoder` on a plain dict, which turns `Decimal("1.5000")` into the bare
    JSON number `1.5` - a different type AND a different value (review round 1 item 7).
    """

    data: List[ProductCompanionRuleOut] = []
