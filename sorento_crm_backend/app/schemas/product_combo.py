"""Product combo schemas (PLAN-price-tag-combos D1, slice S1).

Wire shapes match the contract comment at the top of
`sorento_crm_frontend/.../products/services/productComboService.ts` (Phase 1,
committed) exactly - that file is the contract this was built to satisfy.
"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.accessory import AccessoryOut


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
    sell_price: Optional[Decimal] = None
    topup_amount: Optional[Decimal] = None
    is_upgrade: bool = False


class ProductComboImageOut(BaseModel):
    attachment_id: str
    url: str
    file_name: Optional[str] = None
    mime_type: Optional[str] = None


class ProductComboOut(BaseModel):
    id: str
    host_product_id: str
    name: str
    sort_order: int
    description: Optional[str] = None
    list_price: Optional[Decimal] = None
    sell_price: Optional[Decimal] = None
    parts: List[ProductComboPartOut] = []
    #: PRICETAG-ACCESSORIES: the combo's own "Free items" list, in order (replaces the free text).
    accessories: List[AccessoryOut] = []
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


#: Raw input cap before sanitising (the 5000 limit applies to the stored value, in the service).
RAW_DESCRIPTION_LIMIT = 20000


class ProductComboCreate(BaseModel):
    name: str
    #: Sanitised and length-checked in the service (the limit applies to the stored value).
    description: Optional[str] = Field(default=None, max_length=RAW_DESCRIPTION_LIMIT)


class ProductComboUpdate(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None
    #: Omitted = left alone, explicit null = cleared (`model_fields_set`).
    #: Sanitised and length-checked in the service (the limit applies to the stored value).
    description: Optional[str] = Field(default=None, max_length=RAW_DESCRIPTION_LIMIT)
    list_price: Optional[Decimal] = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    sell_price: Optional[Decimal] = Field(default=None, ge=0, max_digits=12, decimal_places=2)


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
    sell_price: Optional[Decimal] = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    topup_amount: Optional[Decimal] = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    is_upgrade: Optional[bool] = None


class ProductComboCopyIn(BaseModel):
    """COMBO-COPY-TO-PRODUCTS: the hand-picked products to receive this combo."""

    target_product_ids: List[str] = Field(min_length=1, max_length=500)
    #: Targets whose same-named combo is replaced; every other conflict is skipped.
    overwrite_product_ids: List[str] = Field(default_factory=list, max_length=500)
    #: True = answer the same summary and write nothing (the confirm step).
    dry_run: bool = False


class ProductComboCopyTarget(BaseModel):
    product_id: str
    code: str
    name: str


class ProductComboCopySkipped(ProductComboCopyTarget):
    #: `exists`: has a combo of that name and was not picked to overwrite; `part`: is a part of it.
    reason: str


class ProductComboCopyOut(BaseModel):
    targets: int
    created: int
    overwritten: int
    skipped: List[ProductComboCopySkipped]
    #: Every target that already has a combo of that name (overwritten or not).
    conflicts: List[ProductComboCopyTarget]
    template_links_copied: bool
