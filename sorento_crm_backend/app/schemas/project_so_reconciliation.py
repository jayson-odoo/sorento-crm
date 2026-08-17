"""Fulfilment Planning and reconciliation wire shapes (Stage 1B).

Contract: `documentation/plans/scm/STAGE1B-scm-front-planning-reconciliation.md` section 3,
which the frontend was built against in Phase 1. Field names and optionality here match
`app/(protected)/project-sales/_shared/types/fulfilmentPlanning.types.ts` exactly.

Two things are load bearing:

* **Quantities are ``Decimal``**, which pydantic renders as a JSON string. A float round
  trip loses the tail of a quantity the customer signed for.
* **An exception's ``message`` carries the reason alone.** The screen prints the subject
  from ``line_no`` and ``item_code`` ("Line 2, SRT501-CP"), so a message that repeats the
  subject renders the same fact twice.

Nothing here is a per-line workflow state: the whole SO has exactly one pre-confirmation
state (AC-A03), so no line ever reads confirmed, partially confirmed or purchasing-ready.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class FulfilmentPlanningRow(BaseModel):
    """One published or amended Project SO on the cross-project worklist."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    provisional_ref: str
    autocount_doc_no: Optional[str] = None
    project_id: str
    project_code: Optional[str] = None
    project_name: Optional[str] = None
    customer_name: Optional[str] = None
    po_number: Optional[str] = None
    area_group: Optional[str] = None
    #: The existing sales-order status (published, amended), never a review state.
    status: str
    line_count: int = 0
    lines_linked: int = 0
    exception_count: int = 0
    review_state: str
    updated_at: Optional[datetime] = None


class ReconciliationHeader(BaseModel):
    outcome: str
    #: The AutoCount number the core order carries. Never its id.
    core_so_number: Optional[str] = None
    reason: str


class ReconciliationLine(BaseModel):
    id: str
    line_no: int
    product_code: Optional[str] = None
    description: Optional[str] = None
    qty: Decimal
    uom: Optional[str] = None
    delivery_date: Optional[date] = None
    stock_location: Optional[str] = None
    #: `linked`, `missing`, `ambiguous` or `duplicate` (the core line this line would take
    #: is already held by another Project SO).
    link: str
    #: How many core lines could still be this one: 1 on a linked line, the number of core
    #: candidates at that product and date on an ambiguous one, 0 otherwise.
    candidate_count: int = 0
    reason: str


class ReconciliationException(BaseModel):
    #: Absent on a surplus core line, which no Project line claims.
    line_no: Optional[int] = None
    item_code: Optional[str] = None
    #: `header`, `missing`, `ambiguous`, `duplicate` or `surplus`.
    kind: str
    message: str


class ReconciliationSummary(BaseModel):
    project_sales_order_id: str
    provisional_ref: str
    autocount_doc_no: Optional[str] = None
    project_id: str
    project_code: Optional[str] = None
    project_name: Optional[str] = None
    customer_name: Optional[str] = None
    po_number: Optional[str] = None
    area_group: Optional[str] = None
    status: str
    #: None on an order that is not published or amended: it is reconciled against
    #: nothing, so it carries no state rather than one it has not earned (AC-A03).
    review_state: Optional[str] = None
    header: ReconciliationHeader
    lines: List[ReconciliationLine] = []
    exceptions: List[ReconciliationException] = []
    lines_total: int = 0
    lines_linked: int = 0
