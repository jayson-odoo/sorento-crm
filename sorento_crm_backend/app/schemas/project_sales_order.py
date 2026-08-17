"""Project sales order draft, findings and revision-delta schemas (P7, P11).

Contract: `documentation/plans/CONTRACT-project-lead-to-so.md` sections 5 and 6.

Money and quantities are typed ``Decimal`` on purpose. Pydantic v2 renders a Decimal as a
JSON **string**, which is what the contract requires: a float round trip loses cents on a
1.8 million ringgit purchase order, and this engine's whole claim is that the arithmetic
agrees to the cent.

Every id-bearing row also carries the human label the screen shows (phase label, product
code, provisional ref), so no UUID is ever the only identifier in a response.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _require_reason(value: str) -> str:
    cleaned = (value or "").strip()
    if len(cleaned) < 3:
        raise ValueError("A reason of at least 3 characters is required.")
    return cleaned


# -------------------------------------------------------------- version picker


class ScheduleVersionOption(BaseModel):
    id: str
    delivery_schedule_id: str
    version_no: int
    label: str
    revision_label: Optional[str] = None
    extraction_state: str
    schedule_date: Optional[date] = None
    confirmed_at: Optional[datetime] = None
    po_version_no: Optional[int] = None
    reconciled_columns: Optional[int] = None
    total_columns: Optional[int] = None


# ------------------------------------------------------------------------- build


class BuildSalesOrdersRequest(BaseModel):
    schedule_version_id: str = Field(
        ...,
        description=(
            "The confirmed delivery schedule version to spread quantities across. It "
            "also names the PO version the build reads, which is what makes the build "
            "idempotent per (po_version, schedule_version)."
        ),
    )


class BuildSalesOrdersResponse(BaseModel):
    """The proposal, plus what it replaced and what it refused to touch.

    ``skipped_published`` exists because a rebuild must leave published sales orders
    alone: silently ignoring them would let a user believe a rebuild had corrected an
    order that is already in AutoCount.
    """

    data: List["ProjectSalesOrderRow"]
    replaced_drafts: int
    skipped_published: int


# -------------------------------------------------------------------- list + detail


class ProjectSalesOrderRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provisional_ref: str
    autocount_doc_no: Optional[str] = None
    area_group: Optional[str] = None
    status: str
    grouping_origin: Optional[str] = None
    purchase_order_id: Optional[str] = None
    # Present only once the order is committed: nothing uncommitted should be importable
    # into AutoCount, and a published order the user comes back to still needs its file.
    import_file_url: Optional[str] = None
    line_count: int = 0
    total_amount: Optional[Decimal] = None
    hard_findings: int = 0
    warn_findings: int = 0
    is_pre_order: bool = False
    is_sponsorship: bool = False
    customer_name: Optional[str] = None
    po_number: Optional[str] = None
    project_code: Optional[str] = None
    project_title: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProjectSalesOrderLineRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    line_no: int
    product_id: Optional[str] = None
    product_code: Optional[str] = None
    description: Optional[str] = None
    qty: Decimal
    uom: Optional[str] = None
    unit_price: Decimal
    amount: Decimal
    delivery_date: Optional[date] = None
    phase_id: Optional[str] = None
    phase_label: Optional[str] = None
    explosion_source: Optional[str] = None
    source_po_line_no: Optional[int] = None
    quotation_line_id: Optional[str] = None
    stock_location: Optional[str] = None
    # The set this line belongs to, stated rather than inferred: a companion detached from
    # its parent is an unfulfillable printed order. Null on a line that is not part of a set.
    parent_line_id: Optional[str] = None
    is_companion: bool = False


class SODraftFindingRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    severity: str
    code: str
    detail: Optional[str] = None
    detail_json: Optional[Dict[str, Any]] = None
    line_id: Optional[str] = None
    line_no: Optional[int] = None
    acknowledged_by_name: Optional[str] = None
    acknowledged_reason: Optional[str] = None
    acknowledged_at: Optional[datetime] = None


class ProjectSalesOrderDetail(ProjectSalesOrderRow):
    project_id: str
    purchase_order_id: Optional[str] = None
    schedule_version_id: Optional[str] = None
    schedule_revision_label: Optional[str] = None
    quotation_ref: Optional[str] = None
    term_days: Optional[int] = None
    published_at: Optional[datetime] = None
    lines: List[ProjectSalesOrderLineRow] = []
    findings: List[SODraftFindingRow] = []


BuildSalesOrdersResponse.model_rebuild()


# ------------------------------------------------------------------- draft edits


class AcknowledgeFindingRequest(BaseModel):
    reason: str = Field(..., description="Recorded on the sales order forever.")

    _clean = field_validator("reason")(_require_reason)


class SalesOrderLineUpdate(BaseModel):
    """A hand correction on a drafted line.

    ``amount`` is deliberately absent: it is always ``qty * unit_price`` and letting a
    human type a third number would create a line that fails our own arithmetic check.
    """

    qty: Optional[Decimal] = Field(None, gt=0)
    unit_price: Optional[Decimal] = Field(None, ge=0)
    uom: Optional[str] = Field(None, max_length=40)
    description: Optional[str] = None
    delivery_date: Optional[date] = None
    product_id: Optional[str] = None
    stock_location: Optional[str] = Field(None, max_length=80)


class RegroupGroup(BaseModel):
    area_group: Optional[str] = Field(None, max_length=80)
    line_ids: List[str] = Field(..., min_length=1)


class RegroupRequest(BaseModel):
    groups: List[RegroupGroup] = Field(..., min_length=1)


class PublishResponse(BaseModel):
    status: str
    provisional_ref: str
    import_file_url: str
    total_amount: Optional[Decimal] = None
    line_count: int = 0
    # P10: publishing raises the order inquiry in the same transaction, so the caller
    # can go straight to what purchasing has just been told to do.
    order_inquiry_id: Optional[str] = None


# ------------------------------------------------------------------------ delta


class AmendmentPreviewRequest(BaseModel):
    """Exactly one of the two version pointers. Both would be two questions at once."""

    po_version_id: Optional[str] = None
    schedule_version_id: Optional[str] = None


class AmendmentCreateRequest(AmendmentPreviewRequest):
    reason: str = Field(..., description="Why the customer changed their mind.")

    _clean = field_validator("reason")(_require_reason)


class DeltaVersionRef(BaseModel):
    kind: str
    id: str
    version_no: Optional[int] = None
    label: Optional[str] = None


class DeltaRow(BaseModel):
    """One change, at the granularity of the fact that changed.

    A date move is a PHASE fact and every line under the phase moves with it, so each
    line gets its own row carrying the same dates -- that is the contract's shape, and
    ``phase_summary`` below is the phase-level view of the same change.
    """

    so_line_id: Optional[str] = None
    line_no: Optional[int] = None
    product_id: Optional[str] = None
    product_code: Optional[str] = None
    description: Optional[str] = None
    verb: str
    field: str
    from_value: Optional[str] = None
    to_value: Optional[str] = None
    qty: Optional[Decimal] = None
    area_group: Optional[str] = None
    sequence: Optional[int] = None
    phase_id: Optional[str] = None
    phase_label_from: Optional[str] = None
    phase_label_to: Optional[str] = None
    unit_price: Optional[Decimal] = None


class DeltaPhaseSummary(BaseModel):
    """The client's own DELAY table: one line per phase, which is how they read it."""

    area_group: Optional[str] = None
    sequence: Optional[int] = None
    phase_label_from: Optional[str] = None
    phase_label_to: Optional[str] = None
    verb: Optional[str] = None
    delivery_date_from: Optional[str] = None
    delivery_date_to: Optional[str] = None
    line_count: int = 0
    qty_changed: bool = False


class DeltaUnmatched(BaseModel):
    reason: str
    detail: str
    area_group: Optional[str] = None
    sequence: Optional[int] = None


class AmendmentPreviewResponse(BaseModel):
    from_: DeltaVersionRef = Field(..., alias="from")
    to: DeltaVersionRef
    verb_summary: Dict[str, int]
    quantities_changed: bool
    rows: List[DeltaRow]
    phase_summary: List[DeltaPhaseSummary]
    unmatched: List[DeltaUnmatched]

    model_config = ConfigDict(populate_by_name=True)


class AmendmentCreateResponse(BaseModel):
    amendment_id: str
    ocn_id: str
    ocn_number: str
    verb_summary: Dict[str, int]


class AmendmentDetail(BaseModel):
    id: str
    project_sales_order_id: str
    provisional_ref: Optional[str] = None
    autocount_doc_no: Optional[str] = None
    status: str
    from_version_kind: Optional[str] = None
    from_version_label: Optional[str] = None
    to_version_label: Optional[str] = None
    verb_summary: Dict[str, int] = {}
    delta: Optional[Dict[str, Any]] = None
    ocn_id: Optional[str] = None
    ocn_number: Optional[str] = None
    ocn_reason: Optional[str] = None
    ocn_approver_name: Optional[str] = None
    ocn_approved_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class AmendmentPublishResponse(BaseModel):
    status: str
    sales_order_status: str
    provisional_ref: str
    applied_rows: int
    ocn_number: Optional[str] = None
    order_inquiry_id: Optional[str] = None
