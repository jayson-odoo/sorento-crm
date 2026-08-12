"""Customer PO document intake and handwriting review cards (P4, P5).

Shapes are fixed by ``documentation/plans/CONTRACT-project-lead-to-so.md`` sections 2
and 3. Two conventions from that file drive every model below:

- **Money and quantities are Decimal here and strings on the wire.** Pydantic
  serialises ``Decimal`` as a JSON string, which is the point: a float round trip
  loses cents on a 1.8 million ringgit PO, and the one number that proves this whole
  extraction correct is a cent-exact total.
- **No id travels alone.** Every response carrying a UUID also carries the label the
  screen shows (``po_number``, ``project_title``, ``*_name``), because the frontend is
  forbidden from rendering a UUID.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

# ------------------------------------------------------------------------- upload


class POVersionUploadResponse(BaseModel):
    """202. The document is stored and a version row exists; reading it has not started.

    ``extraction_state`` is always ``queued`` here. The UI polls the version until it
    reaches a terminal state, which is why the state is part of the upload answer
    rather than something the caller has to infer.
    """

    purchase_order_id: str
    po_number: str = Field(
        description=(
            "Empty when nothing named the PO yet: extraction proposes the number and a "
            "human agrees to it on the confirm screen."
        )
    )
    project_id: str
    project_title: Optional[str] = None
    po_version_id: str
    version_no: int
    extraction_state: str = "queued"
    page_count: Optional[int] = None


# -------------------------------------------------------------------- version read


class POVersionHeader(BaseModel):
    """The printed header, as extracted. Every field is nullable: a scan can be short
    of any of them, and inventing a value would be worse than showing a gap."""

    po_number: Optional[str] = None
    po_date: Optional[date] = None
    term_days: Optional[int] = None
    sales_person: Optional[str] = None
    customer_order_ref: Optional[str] = None
    admin_ref: Optional[str] = None
    remark: Optional[str] = None


class POVersionTotals(BaseModel):
    """The reconciliation that proves the extraction, in four numbers.

    ``extracted_total`` is what the DOCUMENT says (its printed total where it has one,
    otherwise the sum of the amounts the model transcribed). ``lines_total`` is OUR sum
    of ``qty * unit_price`` over the lines that still stand. They agree exactly when
    every line's arithmetic holds and nothing is cancelled, which is why the difference
    is the single best signal that a page was misread.
    """

    extracted_total: Optional[Decimal] = None
    lines_total: Decimal = Decimal("0")
    cancelled_total: Decimal = Field(
        Decimal("0"),
        description=(
            "Amount on lines cancelled by an accepted annotation. Excluded from "
            "lines_total, and reported separately so the gap against extracted_total "
            "reads as the cancellation it is rather than as a misread page."
        ),
    )
    arithmetic_passed: int = 0
    arithmetic_total: int = 0
    reconciles: bool = Field(
        True,
        description=(
            "lines_total + cancelled_total == extracted_total, compared exactly and not "
            "with a tolerance. False is the signal that a page was misread; a gap that "
            "is exactly the cancelled amount is a fact and leaves this true."
        ),
    )


class POLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    line_no: int
    page_no: Optional[int] = Field(
        None,
        description=(
            "The page this line was printed on, so selecting it turns the side-by-side "
            "viewer to the right page."
        ),
    )
    stock_code_raw: Optional[str] = None
    description_raw: Optional[str] = None
    qty: Optional[Decimal] = None
    uom_raw: Optional[str] = None
    unit_price: Optional[Decimal] = None
    amount: Optional[Decimal] = None
    arithmetic_ok: Optional[bool] = Field(
        None,
        description=(
            "qty * unit_price == amount to two decimals, computed by us and never by "
            "the model. Null when the page did not yield all three numbers, which is a "
            "different problem from a wrong one."
        ),
    )
    is_cancelled: bool = False
    resolved_product_id: Optional[str] = None
    resolved_product_code: Optional[str] = None
    resolved_product_name: Optional[str] = None
    resolution_source: Optional[str] = Field(
        None, description="code | description | map | manual"
    )


class POAnnotationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    page_no: Optional[int] = None
    crop_url: Optional[str] = Field(
        None,
        description=(
            "Null until the extractor reports a region for the note. The page number "
            "always resolves, so the viewer can still put the reader on the right page."
        ),
    )
    raw_text: Optional[str] = None
    written_date: Optional[str] = None
    refers_to_lines: List[int] = Field(default_factory=list)
    interpretation: Optional[str] = Field(
        None,
        description=(
            "cancel_line | amend_code | amend_description | successor_po | signature | other"
        ),
    )
    interpretation_json: Dict[str, Any] = Field(default_factory=dict)
    state: str = "proposed"
    actioned_by_name: Optional[str] = None
    actioned_at: Optional[datetime] = None
    action_note: Optional[str] = None


class POApprovalStamps(BaseModel):
    """The approval handshake, which lives on the PO row but is read on this screen."""

    po_number: str = ""
    status: Optional[str] = None
    approved_by_name: Optional[str] = None
    approved_at: Optional[datetime] = None
    countersigned_by_name: Optional[str] = None
    countersigned_at: Optional[datetime] = None


class POVersionConfirmResult(BaseModel):
    """What the confirm wrote onto the phase-1 PO. Present only on a confirm response."""

    line_count: int = Field(
        description="Lines written onto the phase-1 PO. Cancelled lines are not among them."
    )
    po_amount: Decimal = Decimal("0")
    model_mismatch_count: int = 0
    price_mismatch_count: int = 0


class POVersionDetailResponse(BaseModel):
    id: str
    purchase_order_id: str
    po_number: str
    project_id: str
    project_title: Optional[str] = None
    version_no: int
    extraction_state: str
    extraction_error: Optional[str] = None
    extraction_model: Optional[str] = None
    extraction_elapsed_ms: Optional[int] = Field(
        None,
        description=(
            "How long the model took, in milliseconds. Shown after a read so the wait "
            "is legible. Null on documents read before this was recorded."
        ),
    )
    extraction_started_at: Optional[datetime] = Field(
        None,
        description=(
            "When the reader actually picked this document up. Present so a wait can be "
            "reported as a length ('4 minutes so far') rather than as an unbounded "
            "spinner. Null on documents uploaded before this was recorded."
        ),
    )
    page_count: Optional[int] = None
    pages_extracted: int = Field(
        0,
        description=(
            "Pages that yielded a reading. With page_count this is what lets the screen "
            "say 'only 7 of 10 pages were read' instead of a generic warning."
        ),
    )
    failed_pages: List[int] = Field(default_factory=list)
    document_url: Optional[str] = None
    source_filename: Optional[str] = None
    header: POVersionHeader
    totals: POVersionTotals
    lines: List[POLineResponse] = Field(default_factory=list)
    annotations: List[POAnnotationResponse] = Field(default_factory=list)
    purchase_order: POApprovalStamps = Field(default_factory=POApprovalStamps)
    confirmed_at: Optional[datetime] = None
    confirmed_by_name: Optional[str] = None
    created_at: Optional[datetime] = None
    confirm_result: Optional[POVersionConfirmResult] = None


# ------------------------------------------------------------------- line editing


class POLineUpdate(BaseModel):
    """Everything a person can correct on a transcribed line.

    ``is_cancelled`` is here because a human may cancel a line directly; extraction
    never sets it (D11). Nothing else on the version is editable: the extracted JSON is
    the record of what the paper said.
    """

    stock_code_raw: Optional[str] = Field(None, max_length=180)
    description_raw: Optional[str] = None
    qty: Optional[Decimal] = None
    uom_raw: Optional[str] = Field(None, max_length=40)
    unit_price: Optional[Decimal] = None
    amount: Optional[Decimal] = None
    resolved_product_id: Optional[str] = None
    is_cancelled: Optional[bool] = None


class POVersionHeaderUpdate(BaseModel):
    """AC-D3: every extracted field is editable before approval, the header included.

    Corrections land on the version's extracted header, which is what the confirm adopts
    onto the PO, so a header value reaches the purchase order by exactly one path.
    ``admin_ref`` is the exception: the PS filing reference is ours (D24) and goes
    straight to the PO row, because it was never printed on the customer's paper.
    """

    po_number: Optional[str] = Field(None, max_length=100)
    po_date: Optional[date] = None
    term_days: Optional[int] = None
    sales_person: Optional[str] = Field(None, max_length=120)
    customer_order_ref: Optional[str] = Field(None, max_length=180)
    admin_ref: Optional[str] = Field(None, max_length=64)
    remark: Optional[str] = None


# -------------------------------------------------------------- approval handshake


class POApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    po_number: str
    project_id: str
    status: str
    approved_by_name: Optional[str] = None
    approved_at: Optional[datetime] = None
    countersigned_by_name: Optional[str] = None
    countersigned_at: Optional[datetime] = None


# ------------------------------------------------------------- annotation actions


class AnnotationAcceptRequest(BaseModel):
    note: Optional[str] = None


class AnnotationEditRequest(BaseModel):
    """The human's reading wins, then applies exactly as an accept does."""

    interpretation: str = Field(
        min_length=1,
        description=(
            "cancel_line | amend_code | amend_description | successor_po | signature | other"
        ),
    )
    interpretation_json: Dict[str, Any] = Field(default_factory=dict)
    note: Optional[str] = None


class AnnotationRejectRequest(BaseModel):
    note: str = Field(
        min_length=1,
        description=(
            "Required. A rejected card is recorded as rejected, never deleted, and the "
            "reason is the only thing that explains later why the pencil was ignored."
        ),
    )


class AnnotationApplied(BaseModel):
    """What accepting the card actually changed, so the screen can say so plainly."""

    cancelled_line_nos: List[int] = Field(default_factory=list)
    amended_line_nos: List[int] = Field(default_factory=list)
    successor_po_number: Optional[str] = None
    successor_po_linked: bool = False


class AnnotationActionResponse(BaseModel):
    annotation: POAnnotationResponse
    applied: AnnotationApplied
    totals: POVersionTotals
