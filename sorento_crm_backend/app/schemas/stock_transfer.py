"""Stock transfers over the wire (`PLAN-scm-cs-planning-uat.md` section E).

Every field the screens read is declared here. `response_model` silently drops anything the
schema does not name, so a field added to the serializer and not to this file reaches the
frontend as `undefined` and the column renders blank with no error anywhere - see the
repo's lessons. The tests assert the fields ON THE WIRE for that reason.

No UUID reaches a screen: every id below is paired with the human-readable thing it names
(`product_id` / `item_code`, `from_warehouse_id` / `from_location`, ...), and the frontend
renders the words.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

TransferState = Literal["proposed", "approved", "moved", "cancelled"]
TransferKind = Literal["own_group", "pool", "borrow"]


class StockTransferOut(BaseModel):
    """One movement, as the list and the detail page both read it.

    ONE shape for both, deliberately: the detail page shows what the row holds and the
    list shows a subset of the same fields, so a second "detail" schema would be two
    places to add a column to.
    """

    id: str
    transfer_no: str
    state: TransferState
    kind: TransferKind
    qty: str

    product_id: Optional[str] = None
    item_code: Optional[str] = None
    product_name: Optional[str] = None

    from_warehouse_id: Optional[str] = None
    from_location: Optional[str] = None
    to_warehouse_id: Optional[str] = None
    to_location: Optional[str] = None

    #: The CORE sales order the line belongs to, so the SO detail page can ask for its own.
    sales_order_id: Optional[str] = None
    so_number: Optional[str] = None
    so_line_no: Optional[int] = None
    project_sales_order_id: Optional[str] = None
    customer_name: Optional[str] = None
    sales_agent_id: Optional[str] = None
    agent_code: Optional[str] = None
    agent_name: Optional[str] = None

    supply_decision_id: Optional[str] = None
    revision_no: Optional[int] = None

    proposed_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    approved_by_name: Optional[str] = None
    approved_at: Optional[datetime] = None
    moved_by: Optional[str] = None
    moved_by_name: Optional[str] = None
    moved_at: Optional[datetime] = None
    cancelled_reason: Optional[str] = None
    autocount_ref: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MarkMovedRequest(BaseModel):
    """`autocount_ref` is required: `moved` means a person keyed the movement into
    AutoCount, and a move with no document number cannot be checked against it."""

    autocount_ref: str = Field(..., description="The AutoCount transfer document number.")

    @field_validator("autocount_ref")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("The AutoCount transfer document number is required.")
        return cleaned


class CancelTransferRequest(BaseModel):
    """A reason is required, for the reason a Borrow's is: calling off a movement somebody
    else is waiting on, in silence, sends them back to a person to ask why."""

    reason: str = Field(..., description="Why the transfer is being called off.")

    @field_validator("reason")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if len(cleaned) < 3:
            raise ValueError("A reason of at least 3 characters is required.")
        return cleaned


class BulkApproveRequest(BaseModel):
    ids: List[str] = Field(..., min_length=1)


class BulkApproveSkipped(BaseModel):
    id: str
    transfer_no: Optional[str] = None
    reason: str


class BulkApproveResult(BaseModel):
    """What a bulk Approve actually did.

    Best-effort per row rather than all-or-nothing: a selection of eleven where one was
    cancelled a minute ago by somebody else is not a mistake worth refusing the other ten
    for, and the skipped list says exactly which and why.
    """

    approved: int
    skipped: List[BulkApproveSkipped] = []
