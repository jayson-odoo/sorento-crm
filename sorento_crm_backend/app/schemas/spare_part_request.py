"""Wire shapes of a spare part request (SPARE-PART-ORDER-REQUEST).

Plan: documentation/plans/purchasing/PLAN-spare-part-order-request-12nov.md. The request IS an
order inquiry of type `spare_part_request`; these are its form's body and its detail. Every
field the detail carries is declared here (`response_model` drops an undeclared one).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

#: A request is a handful of spare parts; this only stops an absurd body.
MAX_LINES = 200


class SparePartLineIn(BaseModel):
    #: An existing line's id keeps that line (and its photos) when the form is saved again.
    id: Optional[str] = Field(None, max_length=64)
    product_id: Optional[str] = Field(None, max_length=64)
    #: G1: what the requester calls this part; the product's name when omitted.
    description: Optional[str] = Field(None, max_length=4000)
    stock_location: Optional[str] = Field(None, max_length=80)
    qty: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None


class SparePartRequestIn(BaseModel):
    currency: Optional[str] = Field(None, max_length=3)
    needed_by: Optional[date] = None
    default_location: Optional[str] = Field(None, max_length=80)
    reason: Optional[str] = Field(None, max_length=4000)
    lines: List[SparePartLineIn] = Field(default_factory=list, max_length=MAX_LINES)


class SparePartLineEditIn(BaseModel):
    qty: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None


class SparePartApproveIn(BaseModel):
    note: Optional[str] = Field(None, max_length=2000)
    #: The submitted_at the approver's page rendered; a mismatch answers 409 (stale page).
    submitted_at: Optional[datetime] = None


class SparePartRejectIn(BaseModel):
    #: Required, checked by the service so the refusal reads as a sentence.
    reason: Optional[str] = Field(None, max_length=2000)
    #: The submitted_at the approver's page rendered; a mismatch answers 409 (stale page).
    submitted_at: Optional[datetime] = None


class SparePartLineOut(BaseModel):
    id: str
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    item_code: Optional[str] = None
    description: Optional[str] = None
    stock_location: Optional[str] = None
    qty: str = "0"
    #: The prices are the expected supplier COST: null for a reader who may not see them
    #: (`spare_part_request_service.prices_visible`).
    unit_price: Optional[str] = None
    total: Optional[str] = None
    requested_qty: Optional[str] = None
    requested_unit_price: Optional[str] = None
    state: str
    ack_state: Optional[str] = None
    #: Photos added / removed on this line since the request was last submitted.
    photo_changes: Dict[str, int] = Field(default_factory=lambda: {"added": 0, "removed": 0})


class SparePartRequestOut(BaseModel):
    id: str
    inquiry_no: Optional[str] = None
    inquiry_type: str
    state: str
    currency: Optional[str] = None
    needed_by: Optional[date] = None
    default_location: Optional[str] = None
    reason: Optional[str] = None
    requested_by: Optional[str] = None
    requested_by_name: Optional[str] = None
    submitted_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    approved_by_name: Optional[str] = None
    reject_reason: Optional[str] = None
    can_decide: bool = False
    can_edit: bool = False
    can_revise: bool = False
    total: Optional[str] = None
    lines: List[SparePartLineOut] = []


class SparePartRequestListItem(BaseModel):
    """G3: one row of the spare part requests list."""

    id: str
    inquiry_no: Optional[str] = None
    state: str
    currency: Optional[str] = None
    requested_by: Optional[str] = None
    requested_by_name: Optional[str] = None
    needed_by: Optional[date] = None
    line_count: int = 0
    #: Null for a reader who may not see the expected cost (as the detail's `total`).
    total: Optional[str] = None
    submitted_at: Optional[datetime] = None


class OrderInquiryRowAttachmentLookupRequest(BaseModel):
    row_ids: List[str] = Field(default_factory=list, max_length=1000)
