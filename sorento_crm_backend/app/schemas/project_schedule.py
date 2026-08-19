"""Delivery-schedule intake schemas (P6). Contract section 4.

Quantities are STRINGS here, not Decimals and never floats. They are `Numeric` in
Postgres, the service formats them once, and a float round trip would lose a unit on a
five-figure column total for no reason at all.

No UUID is ever the only identifier: a version carries its PO number and project code,
a phase its area group and label, a column the product code and the customer's own.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class DeliveryScheduleUploadResponse(BaseModel):
    """202. The document is stored and a version exists; reading it happens on the
    worker, because a browser held open for two minutes is an upload people stop doing."""

    delivery_schedule_id: str
    schedule_version_id: str
    version_no: int
    extraction_state: str
    page_count: Optional[int] = None


class SchedulePhaseResponse(BaseModel):
    id: Optional[str] = None
    area_group: Optional[str] = None
    sequence: Optional[int] = None
    label: Optional[str] = Field(
        None,
        description="The COMMON AREA rows carry no label at all; identity is (area_group, sequence).",
    )
    delivery_date: Optional[str] = Field(
        None, description="What THIS version says, which a revision changes."
    )
    promoted_delivery_date: Optional[str] = Field(
        None, description="What the project holds today, so the move is visible before it is agreed."
    )


class ScheduleProductResponse(BaseModel):
    product_index: int = Field(
        ..., description="Stable handle for PUT /products/{product_index}."
    )
    product_id: Optional[str] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    customer_code_raw: Optional[str] = None
    header_name: Optional[str] = None
    resolution_source: Optional[str] = Field(
        None, description="map | code | trigram | manual | null"
    )
    column_total: Optional[str] = None
    reported_total: Optional[str] = Field(
        None, description="The schedule's own TOTAL QTY row, transcribed and not computed."
    )
    po_qty: Optional[str] = Field(
        None, description="From the PO VERSION this schedule names, not the current state."
    )
    cancelled_qty: Optional[str] = Field(
        None, description="Part of po_qty that a later amendment cancelled (AC-E3a)."
    )
    qty_source: Optional[str] = Field(
        None, description="text_layer | vision | manual"
    )
    reconciled: bool = False
    reason: Optional[str] = Field(
        None, description="Why the column does NOT reconcile. Null when it does."
    )
    warning: Optional[str] = Field(
        None,
        description=(
            "Reconciled, and still worth saying. A schedule may be partial: asking for "
            "less than the PO ordered is expected and does not block the confirm."
        ),
    )
    note: Optional[str] = None
    dismissed: bool = Field(
        False,
        description=(
            "A person overruled this column's failing check as a false signal. It stops "
            "blocking the confirm; `reason` still says what the check found."
        ),
    )
    dismissed_reason: Optional[str] = None
    dismissed_by_name: Optional[str] = None
    dismissed_at: Optional[str] = None


class ScheduleCellResponse(BaseModel):
    phase_id: str
    product_index: Optional[int] = Field(
        None,
        description=(
            "Which COLUMN this cell belongs to. Present even when the column's product "
            "is still unidentified, which product_id cannot express."
        ),
    )
    product_id: Optional[str] = None
    customer_code_raw: Optional[str] = None
    qty: str
    highlight: Optional[str] = Field(
        None,
        description=(
            "`#rrggbb` when the document tints this cell (section 9.7a); geometry "
            "from the text layer where it parsed, else the vision pass's own flag."
        ),
    )
    delivery_date_override: Optional[str] = Field(
        None,
        description=(
            "Set only once a revision proposal covering this cell was accepted. "
            "Read ahead of the phase's own date by the revision-delta engine."
        ),
    )


class ScheduleReconciliation(BaseModel):
    reconciled_columns: int = 0
    total_columns: int = 0


class ScheduleNoteResponse(BaseModel):
    """A free-text remark the extractor found on the page but did not interpret.

    Some revisions arrive as PROSE in the margin rather than as a phase-column
    change (e.g. "ONLY FOR FLOOR TRAP TO BE DELIVER IN 2026, START FROM 23/7/2026").
    Verbatim, never turned into a date: that reading is a person's job.
    """

    page_no: Optional[int] = None
    text: str


class RevisionProposalCell(BaseModel):
    phase_id: Optional[str] = None
    phase_label: Optional[str] = None
    qty: Optional[str] = None
    old_date: Optional[str] = None
    new_date: Optional[str] = None


class RevisionProposalResponse(BaseModel):
    """Section 9.7(b): one product's re-date suggestion, built from its highlighted
    cells plus the page's own margin note. Nothing here is applied until Accept."""

    product_id: Optional[str] = None
    item_code: Optional[str] = None
    note_text: Optional[str] = None
    page_no: Optional[int] = None
    state: str = Field("proposed", description="proposed | accepted | rejected")
    decided_by: Optional[str] = None
    decided_at: Optional[str] = None
    cells: List[RevisionProposalCell] = []


class DeliveryScheduleVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    delivery_schedule_id: str
    purchase_order_id: Optional[str] = None
    version_no: int
    revision_label: Optional[str] = None
    issuer_party_label: Optional[str] = Field(
        None, description="A schedule may be issued by a party other than the buyer (AC-E6)."
    )
    po_version_id: Optional[str] = None
    po_version_no: Optional[int] = None
    po_number: Optional[str] = None
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    project_title: Optional[str] = None
    extraction_state: str = Field(
        ..., description="queued | running | done | partial | failed"
    )
    extraction_error: Optional[str] = None
    extraction_model: Optional[str] = None
    extraction_elapsed_ms: Optional[int] = Field(
        None,
        description=(
            "How long the model took, in milliseconds. Shown after a read so the wait "
            "is legible. Null on documents read before this was recorded."
        ),
    )
    extraction_started_at: Optional[str] = Field(
        None,
        description=(
            "When the reader actually picked this document up, so a wait can be reported "
            "as a length rather than as an unbounded spinner. Null on documents uploaded "
            "before this was recorded."
        ),
    )
    page_count: Optional[int] = Field(None, description="Pages in the document.")
    pages_extracted: int = Field(
        0, description="Pages that answered. Below page_count means the read was partial."
    )
    document_url: Optional[str] = None
    schedule_date: Optional[str] = None
    phases: List[SchedulePhaseResponse] = []
    products: List[ScheduleProductResponse] = []
    cells: List[ScheduleCellResponse] = []
    date_warnings: List[Dict[str, Any]] = Field(
        [], description="Dates that run backwards inside an area group (AC-E7)."
    )
    notes: List[ScheduleNoteResponse] = Field(
        [], description="Free-text remarks the extractor found but did not interpret."
    )
    revision_proposals: List[RevisionProposalResponse] = Field(
        [], description="Per-product re-date suggestions from highlighted cells + a dated note."
    )
    amendment_preview_url: Optional[str] = Field(
        None,
        description=(
            "Set once this version is confirmed and an authored order was built "
            "from an earlier version of the same schedule (section 9.2)."
        ),
    )
    acknowledgement: Optional[Dict[str, Any]] = None
    reconciliation: ScheduleReconciliation = ScheduleReconciliation()
    uploaded_by_name: Optional[str] = None
    confirmed_by_name: Optional[str] = None
    confirmed_at: Optional[str] = None
    created_at: Optional[str] = None


class DeliveryScheduleListRow(BaseModel):
    """One schedule on a project, headed by its latest version."""

    id: str
    project_id: str
    purchase_order_id: str
    po_number: Optional[str] = None
    issuer_party_label: Optional[str] = None
    label: Optional[str] = None
    version_count: int = 0
    latest_version_id: Optional[str] = None
    latest_version_no: Optional[int] = None
    latest_revision_label: Optional[str] = None
    extraction_state: Optional[str] = None
    reconciled_columns: int = 0
    total_columns: int = 0
    confirmed_at: Optional[str] = None
    created_at: Optional[str] = None


class DeliveryScheduleVersionListRow(BaseModel):
    """One document in a schedule's revision history. R1 and R2 are separate rows."""

    id: str
    delivery_schedule_id: str
    purchase_order_id: str
    po_number: Optional[str] = None
    version_no: int
    revision_label: Optional[str] = None
    po_version_no: Optional[int] = None
    schedule_date: Optional[str] = None
    extraction_state: str
    extraction_error: Optional[str] = None
    page_count: Optional[int] = None
    pages_extracted: int = 0
    reconciled_columns: int = 0
    total_columns: int = 0
    uploaded_by_name: Optional[str] = None
    confirmed_by_name: Optional[str] = None
    confirmed_at: Optional[str] = None
    created_at: Optional[str] = None


class ScheduleCellInput(BaseModel):
    phase_id: str
    product_index: Optional[int] = Field(
        None,
        description=(
            "The column being edited. Required where the column's product is still "
            "unidentified; otherwise either this or product_id will do."
        ),
    )
    product_id: Optional[str] = None
    customer_code_raw: Optional[str] = Field(
        None,
        description="Alternative to product_index for an unidentified column.",
    )
    qty: str = Field(..., description='A quantity of "0" deletes the cell: a blank is not a zero.')


class ScheduleCellsUpdate(BaseModel):
    cells: List[ScheduleCellInput] = Field(..., min_length=1)


class ScheduleProductResolve(BaseModel):
    product_id: str


class ScheduleColumnDismiss(BaseModel):
    """Overrule one column's failing check, or put it back under it."""

    dismissed: bool = True
    reason: Optional[str] = Field(
        None, description="Required when dismissing: why the check is wrong here."
    )


class ScheduleConfirmRequest(BaseModel):
    acknowledge_unreconciled: bool = False
    reason: Optional[str] = None
