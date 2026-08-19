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
from typing import Any, Dict, List, Literal, Optional

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
    # When this version was uploaded - two uploads of the same document (same version_no
    # scheme, same/blank revision_label) are otherwise indistinguishable in a picker.
    created_at: Optional[datetime] = None


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
    split_by: Literal["area", "delivery_date", "delivery_month"] = Field(
        "area",
        description=(
            "The key the drafted lines are cut into sales orders on. The schedule area "
            "is the default; the two date keys give one sales order per delivery date or "
            "per delivery month, with undated lines in a group of their own."
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
    # Whether that url may be fetched. Not the same question: a published order carrying an
    # unacknowledged hard finding keeps the address of its file and loses permission to
    # take it, so the screens gate the download on this rather than on the url's presence.
    can_export: bool = False
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
    # Stage 1B. The whole order's one pre-confirmation state and how many exceptions stand
    # between it and Needs CS review (AC-A03). Derived from the AutoCount reconciliation
    # rather than stored, so the project's SO list, the SO detail header and Fulfilment
    # Planning read the same answer.
    review_state: Optional[str] = None
    exception_count: int = 0


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
    # None for an order adopted from the AutoCount book, which has no project by design.
    project_id: Optional[str] = None
    purchase_order_id: Optional[str] = None
    schedule_version_id: Optional[str] = None
    schedule_revision_label: Optional[str] = None
    quotation_ref: Optional[str] = None
    term_days: Optional[int] = None
    published_at: Optional[datetime] = None
    lines: List[ProjectSalesOrderLineRow] = []
    findings: List[SODraftFindingRow] = []


BuildSalesOrdersResponse.model_rebuild()


# ------------------------------------------------------------ AutoCount worksheet


class SalesOrderWorksheetHeader(BaseModel):
    """The six refs AutoCount prints above the lines (SO397450).

    `Provisional Ref` is the order's own and is not repeated here. A ref the document does
    not carry is null rather than an empty string: the screen says "Not recorded", and the
    CSV renders the same absence as its blank cell.
    """

    debtor: Optional[str] = None
    your_ref_no: Optional[str] = None
    our_ref_no: Optional[str] = None
    our_qt_ref_no: Optional[str] = None
    terms: Optional[str] = None


class SalesOrderWorksheetLine(BaseModel):
    """One worksheet row, in AutoCount's own column order.

    Quantities and money are ``str``, not ``Decimal``, which is the one place in this module
    that is true. They are the CSV's own cells: ``_qty_str`` writes 927 where a Decimal
    renders 927.0000, and the screen and the file have to be the same document to the
    character. ``reserve_qty`` is "0" on every row until a confirmed supply decision names a
    source (Stage 1C).
    """

    line_no: int
    item_code: Optional[str] = None
    description: Optional[str] = None
    reserve_qty: str
    qty: str
    delivery_date: Optional[date] = None
    uom: Optional[str] = None
    unit_price: str
    discount: Optional[str] = None
    total: str


class SalesOrderWorksheet(BaseModel):
    """`GET /sales-orders/{pso_id}/worksheet`: the document before it leaves the building."""

    id: str
    provisional_ref: str
    autocount_doc_no: Optional[str] = None
    status: str
    area_group: Optional[str] = None
    po_number: Optional[str] = None
    customer_name: Optional[str] = None
    header: SalesOrderWorksheetHeader
    lines: List[SalesOrderWorksheetLine] = []
    total_amount: str
    findings: List[SODraftFindingRow] = []
    # The server's own answer on whether this worksheet may leave the building, so the
    # frontend never re-derives the publish gate.
    can_export: bool = False
    import_file_url: Optional[str] = None


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


class SalesOrderLineWrite(SalesOrderLineUpdate):
    """One line inside a whole-document save.

    ``id`` is what tells a stored line from a new one: a line already stored carries the id
    the API gave it, a new one arrives without one, and an id that is not on this order is
    refused rather than treated as new (which would duplicate the row the caller meant to
    move). ``line_no`` is not a field at all -- position in the array is the order.

    ``qty`` and ``unit_price`` are REQUIRED here, unlike on the per-line correction above: a
    whole-set write states each line in full, and a line arriving without a quantity would be
    silently stored as whatever the row happened to hold.
    """

    id: Optional[str] = None
    qty: Decimal = Field(..., gt=0)
    unit_price: Decimal = Field(Decimal("0"), ge=0)


class SalesOrderDocumentSave(BaseModel):
    """`PUT /sales-orders/{pso_id}`: the header, and optionally the whole line set.

    ``lines`` ABSENT leaves the lines exactly as they are, which is what a header-only save
    sends. An empty ARRAY is a different intent (every line removed) and is refused rather
    than obeyed: a sales order with no lines is not a proposal, and that is the same answer
    the builder gives when every line on a purchase order is cancelled.

    The route reads this with ``exclude_unset=True``, so an absent ``area_group`` leaves the
    stored group alone while an explicit ``null`` clears it. The two are different asks and
    a schema default cannot tell them apart.
    """

    area_group: Optional[str] = Field(None, max_length=80)
    lines: Optional[List[SalesOrderLineWrite]] = None


class SalesOrderDeleteResponse(BaseModel):
    """What a hard delete actually removed, keyed by ``schema.table``.

    The counts are reported rather than swallowed for the same reason the module purge
    reports them: an operator (or a test) reading the result needs to see what was
    CONSIDERED, not only that something happened.
    """

    success: bool = True
    provisional_ref: str
    deleted: Dict[str, int] = {}


#: The most sales orders one bulk delete may name.
#:
#: Far above any page of the list (which shows 25), so a real selection never meets it. It
#: exists so one crafted payload cannot ask for a delete that walks thousands of orders and
#: their children inside a single request, holding a worker for minutes.
MAX_BULK_DELETE = 200


class SalesOrderBulkDeleteRequest(BaseModel):
    """`POST /sales-orders/bulk-delete`: several drafts in ONE call.

    One call rather than N, and it is not an optimisation: N round trips half-apply. The
    first refusal would leave the reviewer looking at a selection that is partly gone, with
    no way to say which part. This is all-or-nothing (see the route).

    Every id must belong to the SAME project - they came from one project's list, and the
    edit right being checked is that project's.
    """

    ids: List[str] = Field(..., min_length=1, max_length=MAX_BULK_DELETE)


class SalesOrderDeleteRefusal(BaseModel):
    """One order the batch would not delete, and why, in the words a person reads.

    ``provisional_ref`` is what the message names: no id ever reaches the screen, and the
    reviewer corrects the selection by the reference printed in the list.
    """

    id: str
    provisional_ref: str
    code: str
    message: str


class SalesOrderBulkDeleteResponse(BaseModel):
    """Mirrors the single delete, plus the count and the (always empty here) refusals.

    ``refused`` is present on success so the shape is stable: a client reads one body
    whether it deleted two orders or none. A batch that WOULD refuse never reaches this
    schema - it is answered 409 before anything is deleted.
    """

    success: bool = True
    deleted_count: int = 0
    deleted: Dict[str, int] = {}
    refused: List[SalesOrderDeleteRefusal] = []


class RegroupGroup(BaseModel):
    area_group: Optional[str] = Field(None, max_length=80)
    line_ids: List[str] = Field(..., min_length=1)


class RegroupRequest(BaseModel):
    groups: List[RegroupGroup] = Field(..., min_length=1)


class PublishRequest(BaseModel):
    """The body is optional: publishing an order with nothing outstanding sends none of it.

    ``acknowledge_blocking`` is the one-decision form of the per-finding override (D9). It
    needs the same sales-manager grant and the same reason, and the reason is recorded on
    every hard finding it clears. The service decides; this only carries the ask.
    """

    acknowledge_blocking: bool = False
    reason: Optional[str] = None


class PublishResponse(BaseModel):
    """No `order_inquiry_id` (PLAN-scm-front-planning.md section 4, AC-D01).

    Publish used to raise the inquiry in the same transaction and return its id. It no
    longer raises one at all: the handoff to purchasing happens inside the atomic Project
    SO confirmation, and carries the confirmed Buy residual only.
    """

    status: str
    provisional_ref: str
    import_file_url: str
    # The same answer the row and the worksheet carry, so the publish dialog's download
    # button reads the server's gate rather than the presence of the url beside it.
    can_export: bool = False
    total_amount: Optional[Decimal] = None
    line_count: int = 0
    # How many hard findings this publish waved through. Zero on the ordinary path, so an
    # existing caller reading the response is unaffected.
    acknowledged_findings: int = 0


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
    # `delta["rows"]` items carry, on top of `DeltaRow` above: `row_key` (str, the
    # row's stable identity - its index within the immutable list), `decision`
    # ("accepted" | "declined", accepted is the default for a row nobody touched)
    # and `declined_reason` (str | null). Left as a loose dict rather than typed:
    # `delta` already was one, and the shape of the rest of the envelope is
    # documented on `DeltaRow` / `DeltaPhaseSummary` / `DeltaUnmatched` above.
    delta: Optional[Dict[str, Any]] = None
    accepted_count: int = 0
    declined_count: int = 0
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


class AmendmentRowDecision(BaseModel):
    """One row's verdict: accept the suggestion, or decline it with a reason."""

    decision: str = Field(..., description="accepted | declined")
    reason: Optional[str] = Field(
        None, description="Required when decision is 'declined'."
    )


class AmendmentRowDecisionsRequest(BaseModel):
    """Merged into the amendment's stored map; rows not named here are untouched."""

    decisions: Dict[str, AmendmentRowDecision]


class AutocountChangeListRow(BaseModel):
    """One accepted amendment row, in the shape a person keys into AutoCount."""

    so_number: Optional[str] = None
    line_no: Optional[int] = None
    item_code: Optional[str] = None
    product: Optional[str] = None
    verb: str
    old_qty: Optional[str] = None
    new_qty: Optional[str] = None
    old_date: Optional[str] = None
    new_date: Optional[str] = None
    new_so_number: Optional[str] = Field(
        None, description="Set only for a CHANGE SO NO row."
    )


class AutocountChangeListResponse(BaseModel):
    amendment_id: str
    ocn_number: Optional[str] = None
    rows: List[AutocountChangeListRow]
    declined_count: int = 0
