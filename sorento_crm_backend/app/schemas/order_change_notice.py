"""Request bodies of the order change notice API (OCN-ORDER-CHANGE-NOTICE).

The responses are plain dicts built by `order_change_notice_service.serialize_detail` /
`serialize_summary`, like the new product application's.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class OrderChangeNoticeLineIn(BaseModel):
    """One changed product. A catalogue product is required: there is no free-text line."""

    product_id: str
    qty_before: Optional[Decimal] = None
    qty_after: Optional[Decimal] = None
    date_before: Optional[date] = None
    date_after: Optional[date] = None
    delivered_qty: Optional[Decimal] = None
    remark: Optional[str] = Field(None, max_length=2000)


class OrderChangeNoticeWrite(BaseModel):
    """Create and edit share one body; a field left out of an edit is kept."""

    change_type_id: Optional[str] = None
    customer_id: Optional[str] = None
    customer_name: Optional[str] = Field(None, max_length=255)
    customer_po_no: Optional[str] = Field(None, max_length=128)
    so_no_text: Optional[str] = Field(None, max_length=128)
    project_id: Optional[str] = None
    #: "Requested by" (UAC I7): an eligible requestor contact; left out on create it defaults to
    #: the raiser's linked contact, an explicit null clears it.
    requested_by_contact_id: Optional[str] = None
    cs_in_charge_user_id: Optional[str] = None
    description: Optional[str] = Field(None, max_length=4000)
    ocn_date: Optional[date] = None
    #: Capped like the new product application's (security review L3).
    lines: Optional[List[OrderChangeNoticeLineIn]] = Field(None, max_length=100)


class ReasonIn(BaseModel):
    reason: Optional[str] = Field(None, max_length=4000)


class DecisionIn(BaseModel):
    """The purchase request's approval-decision body."""

    action: str  # "approved" | "rejected"
    comments: Optional[str] = Field(None, max_length=4000)


class DoneIn(BaseModel):
    cs_comment: Optional[str] = Field(None, max_length=4000)
