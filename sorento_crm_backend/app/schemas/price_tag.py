"""Pydantic schemas for price tag requests and tag templates."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Price tag request line schemas
# ---------------------------------------------------------------------------


class PriceTagRequestLineCreate(BaseModel):
    line_type: str = Field(..., pattern=r"^(product|product_set)$")
    product_id: Optional[str] = None
    product_set_id: Optional[str] = None
    show_promo_price: bool = True
    quantity: int = Field(default=1, ge=1)
    alternatives: list[dict] = Field(default_factory=list)
    included_accessories: Optional[str] = None
    sort_order: int = 0


class PriceTagRequestLineUpdate(BaseModel):
    marketing_price_override: Optional[Decimal] = None
    marketing_override_reason: Optional[str] = None


class PriceTagRequestLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    request_id: str
    line_type: str
    product_id: Optional[str] = None
    product_set_id: Optional[str] = None
    show_promo_price: bool
    quantity: int
    alternatives: list[Any] = []
    included_accessories: Optional[str] = None
    sort_order: int
    marketing_price_override: Optional[Decimal] = None
    marketing_override_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Price tag request schemas
# ---------------------------------------------------------------------------


class PriceTagRequestCreate(BaseModel):
    debtor_code: Optional[str] = None
    debtor_name: str
    promotion_id: Optional[str] = None
    needed_by_date: date
    notes: Optional[str] = None
    lines: list[PriceTagRequestLineCreate] = Field(default_factory=list)


class PriceTagRequestUpdate(BaseModel):
    debtor_code: Optional[str] = None
    debtor_name: Optional[str] = None
    promotion_id: Optional[str] = None
    needed_by_date: Optional[date] = None
    notes: Optional[str] = None


class PriceTagRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    contact_id: str
    company_id: Optional[str] = None
    debtor_code: Optional[str] = None
    debtor_name: str
    promotion_id: Optional[str] = None
    needed_by_date: date
    notes: Optional[str] = None
    status: str
    doc_number: str
    page_id: Optional[str] = None
    portal_draft_at: Optional[datetime] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    lines: list[PriceTagRequestLineResponse] = []


class PriceTagRequestListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    contact_id: str
    debtor_code: Optional[str] = None
    debtor_name: str
    status: str
    doc_number: str
    needed_by_date: date
    created_at: datetime


# ---------------------------------------------------------------------------
# Status transition
# ---------------------------------------------------------------------------


class TransitionPayload(BaseModel):
    status: str
    note: Optional[str] = None


# ---------------------------------------------------------------------------
# Tag template schemas
# ---------------------------------------------------------------------------


class TagTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    family: str = Field(..., min_length=1, max_length=50)
    doc: dict = Field(default_factory=dict)
    print_size: dict = Field(default_factory=dict)


class TagTemplateUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    family: Optional[str] = Field(default=None, max_length=50)
    doc: Optional[dict] = None
    print_size: Optional[dict] = None


class TagTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    family: str
    doc: dict
    print_size: dict
    company_id: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Tag sheet design doc
# ---------------------------------------------------------------------------


class TagSheetDocPayload(BaseModel):
    """Payload for saving a tag sheet design version."""
    doc: dict
    commit_message: Optional[str] = None


class TagSheetDocResponse(BaseModel):
    """Response for getting/saving a tag sheet design."""
    page_id: str
    version: int
    doc: Optional[dict] = None


# ---------------------------------------------------------------------------
# Portal form visibility
# ---------------------------------------------------------------------------


class PortalFormVisibilityResponse(BaseModel):
    visible_types: list[str]


# ---------------------------------------------------------------------------
# Debtor lookup
# ---------------------------------------------------------------------------


class DebtorForAgentItem(BaseModel):
    customer_id: Optional[str] = None
    customer_code: Optional[str] = None
    customer_name: Optional[str] = None
    debtor_code: Optional[str] = None
    debtor_name: Optional[str] = None
    source: str


# ---------------------------------------------------------------------------
# Tag sheet export
# ---------------------------------------------------------------------------


class TagSheetExportIn(BaseModel):
    """Body for POST /price-tag-requests/{id}/export."""
    sheet_ids: Optional[list[str]] = Field(
        default=None,
        description="Optional filter: only render these sheet ids. None = all sheets.",
    )


class TagSheetExportOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    download_id: str = Field(serialization_alias="downloadId")
    status: str
    filename: Optional[str] = None
