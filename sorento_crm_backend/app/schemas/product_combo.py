"""Product combo schemas (PLAN-price-tag-combos D1, slice S1).

Wire shapes match the contract comment at the top of
`sorento_crm_frontend/.../products/services/productComboService.ts` (Phase 1,
committed) exactly - that file is the contract this was built to satisfy.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class ProductComboPartOut(BaseModel):
    id: str
    combo_id: str
    product_id: str
    #: The part's own product code. The reader never sees an id (AC-X-2).
    code: str
    product_name: str
    #: `800 x 500 x 220 mm`, or null when the product records no measurement.
    dimensions: Optional[str] = None
    #: Null = fixed part. A label = one of the options for that label.
    choice_group: Optional[str] = None
    sort_order: int


class ProductComboImageOut(BaseModel):
    attachment_id: str
    url: str


class ProductComboOut(BaseModel):
    id: str
    host_product_id: str
    name: str
    sort_order: int
    parts: List[ProductComboPartOut] = []
    #: The combo's own cover picture (S5), null with none uploaded yet.
    image: Optional[ProductComboImageOut] = None
    created_at: datetime
    updated_at: datetime


class ProductComboListOut(BaseModel):
    data: List[ProductComboOut] = []


class ProductSoldWithOut(BaseModel):
    host_product_id: str
    host_code: str
    host_name: str
    combo_id: str
    combo_name: str


class ProductSoldWithListOut(BaseModel):
    data: List[ProductSoldWithOut] = []


class ProductComboCreate(BaseModel):
    name: str


class ProductComboUpdate(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None


class ProductComboPartCreate(BaseModel):
    part_product_id: str
    choice_group: Optional[str] = None


class ProductComboPartUpdate(BaseModel):
    """`choice_group` is optional-but-nullable on purpose.

    Clearing a group back to "fixed part" sends `{"choice_group": null}`, which is
    NOT the same as "leave it alone" - `model_fields_set` is what tells the two
    apart in the service.
    """

    choice_group: Optional[str] = None
    sort_order: Optional[int] = None
