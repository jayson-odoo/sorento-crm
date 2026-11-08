"""New product application write payloads (NEW-PRODUCT-APP). Staff and portal share them.

Every field is optional on a draft; the submit rules live in
`new_product_application_service`. Number fields accept null (a cleared box is NULL, never 0).
The write body is the v4 paper layout only (`extra="forbid"`): the applicant never writes cost.
"""
from __future__ import annotations

from datetime import date as Date
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class NewProductApplicationLineIn(BaseModel):
    """The paper form's product block. Any other key is refused (422 names it)."""

    model_config = ConfigDict(extra="forbid")

    id: Optional[str] = None
    proposed_code: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    dimension: Optional[str] = Field(None, max_length=2000)
    material: Optional[str] = Field(None, max_length=2000)
    thickness: Optional[str] = Field(None, max_length=2000)
    packing: Optional[str] = Field(None, max_length=2000)
    brand_id: Optional[str] = None
    expected_qty: Optional[Decimal] = Field(None, gt=0, max_digits=12, decimal_places=3)


class NewProductApplicationWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stock_inquiry_id: Optional[str] = None
    customer_id: Optional[str] = None
    customer_name: Optional[str] = Field(None, max_length=255)
    #: Text, as on the stock inquiry it is copied from (crew pass 8 Nov: SI26-0139 is 586 characters).
    project_name: Optional[str] = None
    needed_by: Optional[Date] = None
    remark: Optional[str] = Field(None, max_length=2000)
    #: NPA-FROM-SI (mock v3): PRODUCT CODES, the CURRENT catalogue codes the new code is built from,
    #: in the order picked. Left out keeps the saved ones; [] clears.
    current_product_ids: Optional[List[str]] = Field(None, max_length=20)
    lines: Optional[List[NewProductApplicationLineIn]] = Field(None, max_length=100)


class FeedbackLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    cost_price: Optional[Decimal] = Field(None, ge=0, max_digits=12, decimal_places=2)


class FeedbackIn(BaseModel):
    """PURCHASING FEEDBACK: one lead time, one cost per product. A key left out is not touched."""

    model_config = ConfigDict(extra="forbid")

    lead_time: Optional[str] = Field(None, max_length=2000)
    lines: Optional[List[FeedbackLineIn]] = Field(None, max_length=100)


class PurchasingResponseIn(BaseModel):
    """Owner 8 Nov: purchasing's ONE dialog, like the stock inquiry's "Edit purchasing response".
    ``outcome`` link | new (ending it is the Reject button); sent as null clears it. A key left out is not changed."""

    model_config = ConfigDict(extra="forbid")

    #: The stock inquiry's "Purchasing response" text (owner 8 Nov 15:10).
    purchasing_response: Optional[str] = Field(None, max_length=4000)
    outcome: Optional[Literal["link", "new"]] = None
    product_id: Optional[str] = None
    new_code: Optional[str] = Field(None, max_length=100)
    reason: Optional[str] = Field(None, max_length=2000)
    lead_time: Optional[str] = Field(None, max_length=2000)
    cost_price: Optional[Decimal] = Field(None, ge=0, max_digits=12, decimal_places=2)
    lines: Optional[List[FeedbackLineIn]] = Field(None, max_length=100)


class AttachmentLinkIn(BaseModel):
    attachment_id: str


class ReasonIn(BaseModel):
    reason: Optional[str] = Field(None, max_length=2000)


class LinkIn(BaseModel):
    product_id: str
