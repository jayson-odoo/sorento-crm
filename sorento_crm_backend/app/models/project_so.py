"""Customer PO to Sales Order (phase 2 of the `projects` module).

Every table here is MODULE side. `sales_orders` / `sales_order_lines` are CORE and SCM
owns them: they learn nothing about projects (finding G5). The link runs the other way,
from `project_sales_orders.so_id`, and committed demand still reaches the reorder engine
through the core lines exactly as it does today.

Three ideas shape the whole file:

* **Documents are versioned, never overwritten** (D14). A revised PO or schedule is a new
  version of the same commitment, and the amendment is the computed DIFFERENCE between two
  versions. That is what purchasing consumes, and it is why `so_amendments.delta_json`
  exists rather than a mutated line.
* **The AI proposes, arithmetic decides** (measured 2026-08-01/02). Extraction lands in
  `extracted_json` with per-line values; nothing is trusted until `qty * unit_price ==
  amount` and the schedule column reconciles to the PO. Findings that fail are rows in
  `so_draft_findings`, and five of them block a publish.
* **The project is the anchor, not the customer** (D18). A pre-order parked under another
  debtor still belongs to this project, so joins go through `project_id`.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.database import Base
from app.models.base import CompanyScopedMixin


def _uuid_str() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------------------- customer PO
#
# The customer PO ROW is phase 1's ``project_purchase_orders`` (see
# ``app.models.projects``). Phase 2 does not fork it: it hangs versioned documents,
# extracted lines and handwriting cards off that same row, so a PO recorded by hand
# and a PO arriving as a scan are one PO with one number, not two.
#
# These constants describe columns phase 2 adds to that table.

PO_STATUS_DRAFT = "draft"
PO_STATUS_APPROVED = "approved"
PO_STATUS_SUPERSEDED = "superseded"

ANNOTATION_PROPOSED = "proposed"
ANNOTATION_ACCEPTED = "accepted"
ANNOTATION_EDITED = "edited"
ANNOTATION_REJECTED = "rejected"


class ProjectPOVersion(Base, CompanyScopedMixin):
    """One uploaded document. Immutable once confirmed: a revision is a NEW version."""

    __tablename__ = "project_po_versions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    purchase_order_id = Column(
        UUID(as_uuid=False),
        ForeignKey("project_purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_no = Column(Integer, nullable=False)
    attachment_id = Column(
        UUID(as_uuid=False), ForeignKey("attachments.id", ondelete="SET NULL"), nullable=True
    )
    source_filename = Column(Text, nullable=True)
    page_count = Column(Integer, nullable=True)

    # Raw model output, kept verbatim so a later prompt change can be re-scored against it.
    extracted_json = Column(JSONB, nullable=True)
    extraction_model = Column(String(80), nullable=True)
    extraction_tokens_in = Column(Integer, nullable=True)
    extraction_tokens_out = Column(Integer, nullable=True)
    # qty * unit_price == amount, per line. Measured, not assumed.
    arithmetic_passed = Column(Integer, nullable=True)
    arithmetic_total = Column(Integer, nullable=True)
    extracted_total = Column(Numeric(15, 2), nullable=True)

    confirmed_by = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("purchase_order_id", "version_no", name="uq_project_po_versions_no"),
    )


class ProjectPOLine(Base, CompanyScopedMixin):
    """A printed line, as printed.

    ``stock_code_raw`` is deliberately the customer's own truncated column
    (`SRTWC86`, `2155-BLUE`) because that is what the paper says. The real code is
    recovered from the description into ``resolved_product_id`` (AC-M1b, measured).
    """

    __tablename__ = "project_po_lines"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    po_version_id = Column(
        UUID(as_uuid=False), ForeignKey("project_po_versions.id", ondelete="CASCADE"), nullable=False
    )
    line_no = Column(Integer, nullable=False)
    stock_code_raw = Column(String(180), nullable=True)
    description_raw = Column(Text, nullable=True)
    qty = Column(Numeric(15, 4), nullable=True)
    uom_raw = Column(String(40), nullable=True)
    unit_price = Column(Numeric(15, 5), nullable=True)
    amount = Column(Numeric(15, 2), nullable=True)
    # Set by a handwritten strike-through, only ever after a human accepts the card (D11).
    is_cancelled = Column(Boolean, nullable=False, server_default="false", default=False)
    resolved_product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    resolution_source = Column(String(32), nullable=True)  # code | description | map | manual
    arithmetic_ok = Column(Boolean, nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("po_version_id", "line_no", name="uq_project_po_lines_no"),
        Index("ix_project_po_lines_version", "po_version_id"),
    )


class ProjectPOAnnotation(Base, CompanyScopedMixin):
    """A handwritten note on the scan, as its own reviewable card (D11).

    ``dedup_key`` is what makes re-uploading an annotated scan safe: the same pencil note
    on a later scan is the SAME annotation and must not be proposed twice.
    """

    __tablename__ = "project_po_annotations"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    po_version_id = Column(
        UUID(as_uuid=False), ForeignKey("project_po_versions.id", ondelete="CASCADE"), nullable=False
    )
    dedup_key = Column(String(180), nullable=False)
    page_no = Column(Integer, nullable=True)
    crop_attachment_id = Column(
        UUID(as_uuid=False), ForeignKey("attachments.id", ondelete="SET NULL"), nullable=True
    )
    raw_text = Column(Text, nullable=True)
    written_date = Column(String(40), nullable=True)
    refers_to_lines = Column(JSONB, nullable=True)
    interpretation = Column(String(64), nullable=True)  # cancel_line | amend_code | amend_description | signature | other
    interpretation_json = Column(JSONB, nullable=True)
    state = Column(String(16), nullable=False, server_default=ANNOTATION_PROPOSED)
    actioned_by = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actioned_at = Column(DateTime(timezone=False), nullable=True)
    action_note = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("po_version_id", "dedup_key", name="uq_po_annotations_dedup"),
    )


# ----------------------------------------------------------------- delivery schedule


class DeliverySchedule(Base, CompanyScopedMixin):
    """The customer's delivery programme for one PO.

    ``issuer_party_id`` matters: R2 came from SLG Construction while the PO came from
    Buimaco. The issuer is recorded rather than assumed to be the buyer.
    """

    __tablename__ = "delivery_schedules"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    project_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    purchase_order_id = Column(
        UUID(as_uuid=False),
        ForeignKey("project_purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    issuer_party_id = Column(
        UUID(as_uuid=False), ForeignKey("project_parties.id", ondelete="SET NULL"), nullable=True
    )
    label = Column(String(180), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_delivery_schedules_po", "purchase_order_id"),)


class DeliveryScheduleVersion(Base, CompanyScopedMixin):
    """One uploaded schedule document.

    ``po_version_id`` is the version the checksum reconciles AGAINST (finding G1): a
    schedule issued before a handwritten cancellation still reconciles to the PO as it
    stood, and rejecting it would reject a document the customer considers correct.
    """

    __tablename__ = "delivery_schedule_versions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    delivery_schedule_id = Column(
        UUID(as_uuid=False), ForeignKey("delivery_schedules.id", ondelete="CASCADE"), nullable=False
    )
    version_no = Column(Integer, nullable=False)
    revision_label = Column(String(80), nullable=True)  # "REVISED 1 - 23/7/2026"
    po_version_id = Column(
        UUID(as_uuid=False), ForeignKey("project_po_versions.id", ondelete="SET NULL"), nullable=True
    )
    attachment_id = Column(
        UUID(as_uuid=False), ForeignKey("attachments.id", ondelete="SET NULL"), nullable=True
    )
    source_filename = Column(Text, nullable=True)
    schedule_date = Column(Date, nullable=True)

    extracted_json = Column(JSONB, nullable=True)
    extraction_model = Column(String(80), nullable=True)
    # Per COLUMN, never per document (schedule spike, 2026-08-02): a wholesale reject
    # would reject nearly every real schedule.
    reconciled_columns = Column(Integer, nullable=True)
    total_columns = Column(Integer, nullable=True)
    reconciliation_json = Column(JSONB, nullable=True)

    confirmed_by = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("delivery_schedule_id", "version_no", name="uq_schedule_versions_no"),
    )


class ProjectDeliveryPhase(Base, CompanyScopedMixin):
    """A row of the schedule matrix, promoted to a first class phase on the project (D12).

    Identity is ``(area_group, sequence)`` and NOT the label: the COMMON AREA rows carry no
    label at all, which collapsed three phases into one when matching by label was tried
    (finding G6, confirmed by measurement).
    """

    __tablename__ = "project_delivery_phases"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    project_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    area_group = Column(String(80), nullable=False)  # TOWER | COMMON AREA | ...
    sequence = Column(Integer, nullable=False)
    label = Column(String(180), nullable=True)
    delivery_date = Column(Date, nullable=True)
    source_version_id = Column(
        UUID(as_uuid=False), ForeignKey("delivery_schedule_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("project_id", "area_group", "sequence", name="uq_delivery_phase_identity"),
        Index("ix_delivery_phases_project", "project_id"),
    )


class DeliveryScheduleCell(Base, CompanyScopedMixin):
    """One quantity in the matrix: this phase, this product, this many."""

    __tablename__ = "delivery_schedule_cells"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    version_id = Column(
        UUID(as_uuid=False), ForeignKey("delivery_schedule_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    phase_id = Column(
        UUID(as_uuid=False), ForeignKey("project_delivery_phases.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="RESTRICT"), nullable=True
    )
    customer_code_raw = Column(String(180), nullable=True)
    qty = Column(Numeric(15, 4), nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_schedule_cells_version", "version_id"),
        Index("ix_schedule_cells_phase", "phase_id"),
    )


class CustomerItemCodeMap(Base, CompanyScopedMixin):
    """`BUI-HB-SRTWC8613-RL` means `SRTWC8613-RL`, learned once per customer (AC-E4)."""

    __tablename__ = "customer_item_code_map"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    customer_id = Column(
        UUID(as_uuid=False), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    customer_code = Column(String(180), nullable=False)
    product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    confirmed_by = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("company_id", "customer_id", "customer_code", name="uq_customer_code_map"),
    )


# ------------------------------------------------------------------- sales order draft

SO_STATUS_DRAFT = "draft"
SO_STATUS_BLOCKED = "blocked"
SO_STATUS_READY = "ready"
SO_STATUS_PUBLISHED = "published"
SO_STATUS_AMENDED = "amended"

SEVERITY_HARD = "hard"
SEVERITY_WARN = "warn"
SEVERITY_INFO = "info"


class ProjectSalesOrder(Base, CompanyScopedMixin):
    """A Sales Order this system authored (D1).

    ``so_id`` points at the CORE `sales_orders` row created on publish, which is what SCM
    reads as committed demand. Everything project-shaped lives here so the core table
    stays ignorant of the module (finding G5).
    """

    __tablename__ = "project_sales_orders"
    __audit_track__ = True

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    project_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    purchase_order_id = Column(
        UUID(as_uuid=False),
        ForeignKey("project_purchase_orders.id", ondelete="SET NULL"),
        nullable=True,
    )
    schedule_version_id = Column(
        UUID(as_uuid=False), ForeignKey("delivery_schedule_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    so_id = Column(
        UUID(as_uuid=False), ForeignKey("sales_orders.id", ondelete="SET NULL"), nullable=True
    )

    area_group = Column(String(80), nullable=True)
    provisional_ref = Column(String(80), nullable=False)
    autocount_doc_no = Column(String(80), nullable=True)
    status = Column(String(24), nullable=False, server_default=SO_STATUS_DRAFT)

    # A parking route: the customer on the document is a convenience, the project is the
    # fact (D18). Excluded from customer analytics and credit.
    is_pre_order = Column(Boolean, nullable=False, server_default="false", default=False)
    is_sponsorship = Column(Boolean, nullable=False, server_default="false", default=False)
    sponsorship_form_id = Column(
        UUID(as_uuid=False), ForeignKey("purchase_requests.id", ondelete="SET NULL"), nullable=True
    )
    # How the lines were grouped, so the next PO from this customer proposes what CS did (G2).
    grouping_origin = Column(String(32), nullable=True)  # area | manual | learned

    total_amount = Column(Numeric(15, 2), nullable=True)
    published_by = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    published_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("company_id", "provisional_ref", name="uq_project_so_provisional_ref"),
        Index("ix_project_so_project", "project_id"),
        Index("ix_project_so_status", "status"),
    )


class ProjectSalesOrderLine(Base, CompanyScopedMixin):
    """One SO line: a COMPONENT, at its own delivery date.

    The PO says `927 SETS`; this is one of the four component lines that come out of it,
    three of them at 0.00, exactly as the quotation and the real SO are written.
    """

    __tablename__ = "project_sales_order_lines"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    project_sales_order_id = Column(
        UUID(as_uuid=False), ForeignKey("project_sales_orders.id", ondelete="CASCADE"), nullable=False
    )
    line_no = Column(Integer, nullable=False)
    product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="RESTRICT"), nullable=True
    )
    description = Column(Text, nullable=True)
    qty = Column(Numeric(15, 4), nullable=False)
    uom = Column(String(40), nullable=True)
    unit_price = Column(Numeric(15, 5), nullable=False, server_default="0")
    amount = Column(Numeric(15, 2), nullable=False, server_default="0")
    delivery_date = Column(Date, nullable=True)

    phase_id = Column(
        UUID(as_uuid=False), ForeignKey("project_delivery_phases.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_po_line_id = Column(
        UUID(as_uuid=False), ForeignKey("project_po_lines.id", ondelete="SET NULL"), nullable=True
    )
    # Which quotation line this consumed balance from, shown on screen always (G3).
    quotation_line_id = Column(
        UUID(as_uuid=False), ForeignKey("project_quotation_lines.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Where the stock is coming from, once Eling confirms (D17).
    stock_location = Column(String(80), nullable=True)
    explosion_source = Column(String(32), nullable=True)  # package | quotation | direct
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_project_so_lines_order", "project_sales_order_id"),
    )


class SODraftFinding(Base, CompanyScopedMixin):
    """A cross-check result. Five codes are hard stops; the rest are cleared with a reason (D9)."""

    __tablename__ = "so_draft_findings"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    project_sales_order_id = Column(
        UUID(as_uuid=False), ForeignKey("project_sales_orders.id", ondelete="CASCADE"), nullable=False
    )
    line_id = Column(
        UUID(as_uuid=False), ForeignKey("project_sales_order_lines.id", ondelete="CASCADE"),
        nullable=True,
    )
    severity = Column(String(8), nullable=False)  # hard | warn | info
    code = Column(String(64), nullable=False)
    detail = Column(Text, nullable=True)
    detail_json = Column(JSONB, nullable=True)
    acknowledged_by = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    acknowledged_at = Column(DateTime(timezone=False), nullable=True)
    acknowledged_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_so_findings_order", "project_sales_order_id"),
        Index("ix_so_findings_severity", "severity"),
    )


# ----------------------------------------------------------------------- amendments

AMENDMENT_PROPOSED = "proposed"
AMENDMENT_APPROVED = "approved"
AMENDMENT_PUBLISHED = "published"
AMENDMENT_REJECTED = "rejected"

VERB_ADVANCE = "ADVANCE"
VERB_DELAY = "DELAY"
VERB_QTY_CHANGE = "QTY_CHANGE"
VERB_ADD_LINE = "ADD_LINE"
VERB_REMOVE_LINE = "REMOVE_LINE"
VERB_CANCEL_BALANCE = "CANCEL_BALANCE"
VERB_REPOINT_SO = "REPOINT_SO"
VERB_MODEL_CHANGE = "MODEL_CHANGE"


class OrderChangeNotice(Base, CompanyScopedMixin):
    """The client's only trusted hard gate (D15), auto drafted from the computed delta.

    Required for every amendment to a PUBLISHED SO. Editing an unpublished draft is not an
    amendment and raises none (finding G9).
    """

    __tablename__ = "order_change_notices"
    __audit_track__ = True

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    ocn_number = Column(String(64), nullable=False)
    project_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    purchase_order_id = Column(
        UUID(as_uuid=False),
        ForeignKey("project_purchase_orders.id", ondelete="SET NULL"),
        nullable=True,
    )
    project_sales_order_id = Column(
        UUID(as_uuid=False), ForeignKey("project_sales_orders.id", ondelete="SET NULL"), nullable=True
    )
    reason = Column(Text, nullable=True)
    source_document_kind = Column(String(32), nullable=True)  # revised_po | revised_schedule | none
    source_document_id = Column(UUID(as_uuid=False), nullable=True)
    change_table_json = Column(JSONB, nullable=True)
    approver_id = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=False), nullable=True)
    created_by = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("company_id", "ocn_number", name="uq_ocn_number"),
    )


class SOAmendment(Base, CompanyScopedMixin):
    """The difference between two document versions, in purchasing's own verbs (D14)."""

    __tablename__ = "so_amendments"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    project_sales_order_id = Column(
        UUID(as_uuid=False), ForeignKey("project_sales_orders.id", ondelete="CASCADE"), nullable=False
    )
    ocn_id = Column(
        UUID(as_uuid=False), ForeignKey("order_change_notices.id", ondelete="SET NULL"), nullable=True
    )
    from_version_kind = Column(String(32), nullable=True)  # po | schedule
    from_version_id = Column(UUID(as_uuid=False), nullable=True)
    to_version_id = Column(UUID(as_uuid=False), nullable=True)
    verb_summary = Column(JSONB, nullable=True)  # {"DELAY": 12, "CANCEL_BALANCE": 1}
    delta_json = Column(JSONB, nullable=True)
    status = Column(String(16), nullable=False, server_default=AMENDMENT_PROPOSED)
    published_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_so_amendments_order", "project_sales_order_id"),)


# --------------------------------------------------------------------- order inquiry

INQUIRY_RAISED = "raised"
INQUIRY_ACTIONED = "actioned"
INQUIRY_CANCELLED = "cancelled"

IV_ORDER = "ORDER"
IV_RESERVE_AND_ORDER = "RESERVE_AND_ORDER"
IV_ADVANCE = "ADVANCE"
IV_DELAY = "DELAY"
IV_CHANGE_SO = "CHANGE_SO"
IV_CANCEL_BALANCE = "CANCEL_BALANCE"
IV_PRE_ORDERED = "PRE_ORDERED_DO_NOT_ORDER"
IV_ALREADY_INBOUND = "ALREADY_INBOUND"


class OrderInquiry(Base, CompanyScopedMixin):
    """What purchasing is told to do, derived from an SO or its amendment (D16).

    Never a second source of demand: committed quantity stays on `sales_order_lines`.
    """

    __tablename__ = "order_inquiries"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    project_sales_order_id = Column(
        UUID(as_uuid=False), ForeignKey("project_sales_orders.id", ondelete="CASCADE"), nullable=False
    )
    amendment_id = Column(
        UUID(as_uuid=False), ForeignKey("so_amendments.id", ondelete="SET NULL"), nullable=True
    )
    state = Column(String(16), nullable=False, server_default=INQUIRY_RAISED)
    raised_by = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    raised_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_order_inquiries_order", "project_sales_order_id"),)


class OrderInquiryRow(Base, CompanyScopedMixin):
    """One instruction. ``covered_by`` is why an ORDER row was NOT emitted (AC-I3a, FIFO)."""

    __tablename__ = "order_inquiry_rows"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    order_inquiry_id = Column(
        UUID(as_uuid=False), ForeignKey("order_inquiries.id", ondelete="CASCADE"), nullable=False
    )
    so_line_id = Column(
        UUID(as_uuid=False), ForeignKey("project_sales_order_lines.id", ondelete="SET NULL"),
        nullable=True,
    )
    item_code = Column(String(120), nullable=True)
    qty = Column(Numeric(15, 4), nullable=False)
    delivery_date = Column(Date, nullable=True)
    stock_location = Column(String(80), nullable=True)
    verb = Column(String(32), nullable=False)
    spo_ref = Column(String(80), nullable=True)
    covered_by = Column(Text, nullable=True)
    state = Column(String(16), nullable=False, server_default=INQUIRY_RAISED)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_order_inquiry_rows_inquiry", "order_inquiry_id"),)
