"""Customer PO to Sales Order (phase 2 of the `projects` module).

Every table here is MODULE side and lives in the `projects` schema (ADR-0011; see the
header of ``app.models.projects`` for the full rules on qualified FKs, pinned audit entity
types and raw SQL). `public.sales_orders` / `public.sales_order_lines` are CORE and SCM
owns them: they learn nothing about projects (finding G5). The link runs the other way,
from `projects.sales_orders.so_id`, and committed demand still reaches the reorder engine
through the core lines exactly as it does today.

**`projects.sales_orders` and `public.sales_orders` are different tables with the same bare
name.** So is the `_lines` pair. `ForeignKey("sales_orders.id")` below is the CORE one,
unqualified on purpose; every FK naming a module table is written `projects.<table>.<col>`.

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
    text,
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

    __tablename__ = "po_versions"
    # Audit entity type pinned to the pre-move table name (ADR-0011).
    __audit_entity_type__ = "project_po_versions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    purchase_order_id = Column(
        UUID(as_uuid=False),
        ForeignKey("projects.purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_no = Column(Integer, nullable=False)
    attachment_id = Column(
        UUID(as_uuid=False), ForeignKey("attachments.id", ondelete="SET NULL"), nullable=True
    )
    source_filename = Column(Text, nullable=True)
    page_count = Column(Integer, nullable=True)

    # Raw model output, kept verbatim so a later prompt change can be re-scored against it.
    # Extraction runs on the worker, so the row carries its own progress. A version
    # stuck on "queued" reads as a hung system, which is why every exit path writes a
    # terminal state and a sentence a person can act on.
    extraction_state = Column(String(16), nullable=False, server_default="queued")
    extraction_error = Column(Text, nullable=True)
    # Which RQ job is reading this, and when it picked the document up.
    #
    # Both exist for one reason: a work-horse that is KILLED does not run the task's own
    # error handling, so nothing inside the dying process can report the death. Something
    # outside has to, and the only honest way to tell a dead read from a slow one is to ask
    # RQ about the job itself. `extraction_started_at` is the fallback for rows that carry
    # no job id (uploaded before this was recorded), and it is what lets the screen say
    # "4 minutes so far" instead of showing an unbounded spinner. See
    # ``app.services.project_extraction_recovery_service``.
    extraction_job_id = Column(String(64), nullable=True)
    extraction_started_at = Column(DateTime(timezone=False), nullable=True)
    extracted_json = Column(JSONB, nullable=True)
    extraction_model = Column(String(80), nullable=True)
    extraction_tokens_in = Column(Integer, nullable=True)
    extraction_tokens_out = Column(Integer, nullable=True)
    # How long the model actually took. Reading a ten page scan is minutes of waiting,
    # and a person told "took 2m 14s" once stops wondering whether it hung.
    extraction_elapsed_ms = Column(Integer, nullable=True)
    # qty * unit_price == amount, per line. Measured, not assumed.
    arithmetic_passed = Column(Integer, nullable=True)
    arithmetic_total = Column(Integer, nullable=True)
    extracted_total = Column(Numeric(15, 2), nullable=True)

    confirmed_by = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("purchase_order_id", "version_no", name="uq_project_po_versions_no"),
        {"schema": "projects"},
    )


class ProjectPOLine(Base, CompanyScopedMixin):
    """A printed line, as printed.

    ``stock_code_raw`` is deliberately the customer's own truncated column
    (`SRTWC86`, `2155-BLUE`) because that is what the paper says. The real code is
    recovered from the description into ``resolved_product_id`` (AC-M1b, measured).
    """

    __tablename__ = "po_lines"
    # Audit entity type pinned to the pre-move table name (ADR-0011).
    __audit_entity_type__ = "project_po_lines"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    po_version_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.po_versions.id", ondelete="CASCADE"), nullable=False
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
        {"schema": "projects"},
    )


class ProjectPOAnnotation(Base, CompanyScopedMixin):
    """A handwritten note on the scan, as its own reviewable card (D11).

    ``dedup_key`` is what makes re-uploading an annotated scan safe: the same pencil note
    on a later scan is the SAME annotation and must not be proposed twice.
    """

    __tablename__ = "po_annotations"
    # Audit entity type pinned to the pre-move table name (ADR-0011).
    __audit_entity_type__ = "project_po_annotations"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    po_version_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.po_versions.id", ondelete="CASCADE"), nullable=False
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
        {"schema": "projects"},
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
        UUID(as_uuid=False), ForeignKey("projects.projects.id", ondelete="CASCADE"), nullable=False
    )
    purchase_order_id = Column(
        UUID(as_uuid=False),
        ForeignKey("projects.purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    issuer_party_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.parties.id", ondelete="SET NULL"), nullable=True
    )
    label = Column(String(180), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_delivery_schedules_po", "purchase_order_id"),
        {"schema": "projects"},
    )


class DeliveryScheduleVersion(Base, CompanyScopedMixin):
    """One uploaded schedule document.

    ``po_version_id`` is the version the checksum reconciles AGAINST (finding G1): a
    schedule issued before a handwritten cancellation still reconciles to the PO as it
    stood, and rejecting it would reject a document the customer considers correct.
    """

    __tablename__ = "delivery_schedule_versions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    delivery_schedule_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.delivery_schedules.id", ondelete="CASCADE"), nullable=False
    )
    version_no = Column(Integer, nullable=False)
    revision_label = Column(String(80), nullable=True)  # "REVISED 1 - 23/7/2026"
    po_version_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.po_versions.id", ondelete="SET NULL"), nullable=True
    )
    attachment_id = Column(
        UUID(as_uuid=False), ForeignKey("attachments.id", ondelete="SET NULL"), nullable=True
    )
    source_filename = Column(Text, nullable=True)
    schedule_date = Column(Date, nullable=True)

    extraction_state = Column(String(16), nullable=False, server_default="queued")
    extraction_error = Column(Text, nullable=True)
    # Same pair, same reason, as ProjectPOVersion above: the schedule task has the identical
    # shape and the identical hole, so it gets the identical fix.
    extraction_job_id = Column(String(64), nullable=True)
    extraction_started_at = Column(DateTime(timezone=False), nullable=True)
    extracted_json = Column(JSONB, nullable=True)
    extraction_model = Column(String(80), nullable=True)
    extraction_elapsed_ms = Column(Integer, nullable=True)
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
        {"schema": "projects"},
    )


class ProjectDeliveryPhase(Base, CompanyScopedMixin):
    """A row of the schedule matrix, promoted to a first class phase on the project (D12).

    Identity is ``(area_group, sequence)`` and NOT the label: the COMMON AREA rows carry no
    label at all, which collapsed three phases into one when matching by label was tried
    (finding G6, confirmed by measurement).
    """

    __tablename__ = "delivery_phases"
    # Audit entity type pinned to the pre-move table name (ADR-0011).
    __audit_entity_type__ = "project_delivery_phases"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    project_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.projects.id", ondelete="CASCADE"), nullable=False
    )
    area_group = Column(String(80), nullable=False)  # TOWER | COMMON AREA | ...
    sequence = Column(Integer, nullable=False)
    label = Column(String(180), nullable=True)
    delivery_date = Column(Date, nullable=True)
    source_version_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.delivery_schedule_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("project_id", "area_group", "sequence", name="uq_delivery_phase_identity"),
        Index("ix_delivery_phases_project", "project_id"),
        {"schema": "projects"},
    )


class DeliveryScheduleCell(Base, CompanyScopedMixin):
    """One quantity in the matrix: this phase, this product, this many."""

    __tablename__ = "delivery_schedule_cells"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    version_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.delivery_schedule_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    phase_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.delivery_phases.id", ondelete="CASCADE"),
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
        {"schema": "projects"},
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
        {"schema": "projects"},
    )


# ------------------------------------------------------------------- sales order draft

SO_STATUS_DRAFT = "draft"
SO_STATUS_BLOCKED = "blocked"
SO_STATUS_READY = "ready"
SO_STATUS_PUBLISHED = "published"
SO_STATUS_AMENDED = "amended"
# Sponsorship only (AC-K3, D28). A giveaway is drafted at price zero and Accounts has to
# attend to it before it reaches AutoCount, so this status GATES the publish rather than
# merely labelling the row. A commercial draft never enters it.
SO_STATUS_AWAITING_COSTING = "awaiting_costing"

SEVERITY_HARD = "hard"
SEVERITY_WARN = "warn"
SEVERITY_INFO = "info"


class ProjectSalesOrder(Base, CompanyScopedMixin):
    """A Sales Order this system authored (D1).

    ``so_id`` points at the CORE `sales_orders` row created on publish, which is what SCM
    reads as committed demand. Everything project-shaped lives here so the core table
    stays ignorant of the module (finding G5).
    """

    __tablename__ = "sales_orders"
    # Audit entity type pinned to the pre-move table name (ADR-0011).
    __audit_entity_type__ = "project_sales_orders"
    __audit_track__ = True

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    project_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.projects.id", ondelete="RESTRICT"), nullable=False
    )
    purchase_order_id = Column(
        UUID(as_uuid=False),
        ForeignKey("projects.purchase_orders.id", ondelete="SET NULL"),
        nullable=True,
    )
    schedule_version_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.delivery_schedule_versions.id", ondelete="SET NULL"),
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
        {"schema": "projects"},
    )


class ProjectSalesOrderLine(Base, CompanyScopedMixin):
    """One SO line: a COMPONENT, at its own delivery date.

    The PO says `927 SETS`; this is one of the four component lines that come out of it,
    three of them at 0.00, exactly as the quotation and the real SO are written.
    """

    __tablename__ = "sales_order_lines"
    # Audit entity type pinned to the pre-move table name (ADR-0011).
    __audit_entity_type__ = "project_sales_order_lines"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    project_sales_order_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.sales_orders.id", ondelete="CASCADE"), nullable=False
    )
    # The reconciled CORE line (PLAN-scm-front-planning.md 6.1). Unqualified on purpose,
    # so this is `public.sales_order_lines`, not the module table of the same bare name.
    #
    # Nullable, because reconciliation is a later step: the AutoCount upload in stage 1B is
    # what fills it, and a line with no link is simply not confirmable yet. `SET NULL`
    # rather than CASCADE because losing the core line loses the LINK, never the project
    # record of what was committed.
    core_sales_order_line_id = Column(
        UUID(as_uuid=False), ForeignKey("sales_order_lines.id", ondelete="SET NULL"), nullable=True
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
        UUID(as_uuid=False), ForeignKey("projects.delivery_phases.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_po_line_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.po_lines.id", ondelete="SET NULL"), nullable=True
    )
    # Which quotation line this consumed balance from, shown on screen always (G3).
    quotation_line_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.quotation_lines.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Where the stock is coming from, once Eling confirms (D17).
    stock_location = Column(String(80), nullable=True)
    explosion_source = Column(String(32), nullable=True)  # package | quotation | direct
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_project_so_lines_order", "project_sales_order_id"),
        # One Project line per core line: the "unique reconciled link" the atomic SO
        # confirmation is written against. Partial, because NULL is the normal state for
        # every unreconciled line and there is no reason to index them.
        Index(
            "uq_projects_so_line_core_line",
            "core_sales_order_line_id",
            unique=True,
            postgresql_where=text("core_sales_order_line_id IS NOT NULL"),
        ),
        {"schema": "projects"},
    )


class SODraftFinding(Base, CompanyScopedMixin):
    """A cross-check result. Five codes are hard stops; the rest are cleared with a reason (D9)."""

    __tablename__ = "so_draft_findings"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    project_sales_order_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.sales_orders.id", ondelete="CASCADE"), nullable=False
    )
    line_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.sales_order_lines.id", ondelete="CASCADE"),
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
        {"schema": "projects"},
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
        UUID(as_uuid=False), ForeignKey("projects.projects.id", ondelete="CASCADE"), nullable=False
    )
    purchase_order_id = Column(
        UUID(as_uuid=False),
        ForeignKey("projects.purchase_orders.id", ondelete="SET NULL"),
        nullable=True,
    )
    project_sales_order_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.sales_orders.id", ondelete="SET NULL"), nullable=True
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
        {"schema": "projects"},
    )


class SOAmendment(Base, CompanyScopedMixin):
    """The difference between two document versions, in purchasing's own verbs (D14)."""

    __tablename__ = "so_amendments"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    project_sales_order_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.sales_orders.id", ondelete="CASCADE"), nullable=False
    )
    ocn_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.order_change_notices.id", ondelete="SET NULL"), nullable=True
    )
    from_version_kind = Column(String(32), nullable=True)  # po | schedule
    from_version_id = Column(UUID(as_uuid=False), nullable=True)
    to_version_id = Column(UUID(as_uuid=False), nullable=True)
    verb_summary = Column(JSONB, nullable=True)  # {"DELAY": 12, "CANCEL_BALANCE": 1}
    delta_json = Column(JSONB, nullable=True)
    status = Column(String(16), nullable=False, server_default=AMENDMENT_PROPOSED)
    published_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_so_amendments_order", "project_sales_order_id"),
        {"schema": "projects"},
    )


# NOTE (merge, Stage 1C + Stage 2): `SOSupplyDecision` used to be declared HERE too.
# Both stages needed `projects.so_supply_decisions` and, with neither merged, each wrote
# its own copy of the class and its own DDL. Stage 2's own docstring named the owner
# ("Stage 1C owns the atomic confirmation that writes it; nothing in SCM writes it"), so
# the Stage 1C declaration further down is the one that survives and Stage 2's duplicate
# is gone. Two mappers on one `__tablename__` is an import-time error, not a style
# problem. Stage 2 still only READS the table, through raw SQL in `scm.committed_v`, and
# that view needs `id` / `project_sales_order_id` / `state`, all of which 1C's table has.


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
    # Audit entity type pinned to the pre-move table name (ADR-0011).
    __audit_entity_type__ = "project_order_inquiries"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    project_sales_order_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.sales_orders.id", ondelete="CASCADE"), nullable=False
    )
    amendment_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.so_amendments.id", ondelete="SET NULL"), nullable=True
    )
    state = Column(String(16), nullable=False, server_default=INQUIRY_RAISED)
    raised_by = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    raised_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_project_order_inquiries_order", "project_sales_order_id"),
        # One inquiry per publish, enforced by the database rather than by remembering
        # to check: republishing must not double what purchasing is told to buy.
        # Postgres treats NULLs as distinct, so the sales-order case needs its own
        # predicate rather than a plain unique on the pair.
        Index(
            "uq_project_order_inquiry_per_sales_order",
            "project_sales_order_id",
            unique=True,
            postgresql_where=text("amendment_id IS NULL"),
        ),
        Index(
            "uq_project_order_inquiry_per_amendment",
            "amendment_id",
            unique=True,
            postgresql_where=text("amendment_id IS NOT NULL"),
        ),
        {"schema": "projects"},
    )


class OrderInquiryRow(Base, CompanyScopedMixin):
    """One instruction.

    ``covered_by`` is why an ORDER row was NOT emitted (AC-I3a, FIFO): the pre-order or
    the inbound SPO that already covers this quantity.

    ``note`` is the other half of an amendment instruction. A verb on its own is not
    actionable: DELAY without the date it moved from, or CHANGE SO without the sales
    order it moves to, sends purchasing back to a person to ask. Coverage and
    explanation are separate fields because they answer separate questions.
    """

    __tablename__ = "order_inquiry_rows"
    # Audit entity type pinned to the pre-move table name (ADR-0011).
    __audit_entity_type__ = "project_order_inquiry_rows"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    order_inquiry_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.order_inquiries.id", ondelete="CASCADE"), nullable=False
    )
    so_line_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.sales_order_lines.id", ondelete="SET NULL"),
        nullable=True,
    )
    item_code = Column(String(120), nullable=True)
    qty = Column(Numeric(15, 4), nullable=False)
    delivery_date = Column(Date, nullable=True)
    stock_location = Column(String(80), nullable=True)
    verb = Column(String(32), nullable=False)
    spo_ref = Column(String(80), nullable=True)
    # The confirmed supply decision this Buy residual came from (front planning 6.3).
    # Nullable, because amendment exception rows and every row raised before Stage 1C
    # belong to no decision. SET NULL rather than CASCADE: a decision that is deleted
    # must not take purchasing's ledger with it.
    #
    # Stage 2 reads it: SCM counts Project demand as the qty on rows pointing at an ACTIVE
    # decision, which is what stops a superseded revision's Buy being bought again.
    supply_decision_id = Column(
        UUID(as_uuid=False),
        ForeignKey("projects.so_supply_decisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    covered_by = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    state = Column(String(16), nullable=False, server_default=INQUIRY_RAISED)
    # "Did purchasing act on this" (AC-I7) is only half answered by a state. A state
    # with nobody's name and no time on it cannot say when, or who to ask.
    actioned_by = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actioned_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_project_order_inquiry_rows_inquiry", "order_inquiry_id"),
        Index("ix_project_order_inquiry_rows_state", "state"),
        # Stage 1C's name, because 1C's `374_so_supply_decisions` is the migration that
        # creates this index; Stage 2 proposed `..._supply_decision` for the same column
        # and its duplicate DDL is dropped with the duplicate model above.
        Index("ix_project_order_inquiry_rows_decision", "supply_decision_id"),
        {"schema": "projects"},
    )


# ------------------------------------------------------------------------ allocation

ALLOC_SOURCE_BRW = "brw"
ALLOC_SOURCE_OWN = "own"
ALLOC_SOURCE_OTHER_PROJECT = "other_project"
ALLOC_SOURCE_ORDER = "order"
#: Free stock at a location outside the Reserve pool (front planning 6.1). Borrow like
#: `other_project`, but there is no donor project to ask, so it carries no claim row.
#: A model constant, not a database enum: `source_type` is a plain String(16).
ALLOC_SOURCE_OTHER_LOCATION = "other_location"

#: UI mapping, stated once: `own`/`brw` are Reserve, `other_project`/`other_location` are
#: Borrow, `order` is Buy.
ALLOC_RESERVE_SOURCES = (ALLOC_SOURCE_OWN, ALLOC_SOURCE_BRW)
ALLOC_BORROW_SOURCES = (ALLOC_SOURCE_OTHER_PROJECT, ALLOC_SOURCE_OTHER_LOCATION)

CLAIM_REQUESTED = "requested"
CLAIM_ACCEPTED = "accepted"
CLAIM_REFUSED = "refused"

# ------------------------------------------------------- the SO supply decision (1C)

DECISION_ACTIVE = "active"
DECISION_SUPERSEDED = "superseded"
DECISION_CHALLENGED = "challenged"


class SOSupplyDecision(Base, CompanyScopedMixin):
    """One atomic promise about a whole Project SO (PLAN-scm-front-planning.md 3.1, 6.2).

    Confirmation is at SO level and never per line. The sheet is line-oriented because CS
    inspects each line's composition, but no line carries a durable partial state: one
    revision covers every line or none of them does, so a stale line rolls back the lot.

    ``line_snapshots`` freezes what was decided, in the words it was decided in: line
    number, the Project and core line ids, product, location, required date, open quantity,
    each component's quantity AND the deterministic reason string that produced it
    (section 3.2), the suggestion basis, the lifecycle warning, and the reasons CS typed.
    The normalized `so_line_allocations` rows remain the components; this is the header
    that groups them and the evidence that survives a later fact change.

    Two uniqueness rules, both in the database rather than in a remembered check: a partial
    unique index makes ONE active revision per Project SO (so the second racer's insert
    fails and it loses cleanly instead of double-claiming stock), and `(order, revision_no)`
    makes the revision chain a chain.
    """

    __tablename__ = "so_supply_decisions"
    __audit_entity_type__ = "project_so_supply_decisions"
    __audit_track__ = True

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    project_sales_order_id = Column(
        UUID(as_uuid=False),
        ForeignKey("projects.sales_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    revision_no = Column(Integer, nullable=False)
    state = Column(String(16), nullable=False, server_default=DECISION_ACTIVE)
    #: The order's status and `updated_at` at confirmation, as text. Display evidence
    #: only: what the revision was decided against, in a form a person can read.
    source_revision = Column(String(120), nullable=True)
    line_snapshots = Column(JSONB, nullable=False)

    confirmed_by = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_at = Column(DateTime(timezone=False), nullable=True)

    supersedes_id = Column(
        UUID(as_uuid=False),
        ForeignKey("projects.so_supply_decisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    superseded_at = Column(DateTime(timezone=False), nullable=True)
    superseded_reason = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_so_supply_decisions_order", "project_sales_order_id"),
        Index(
            "uq_so_supply_decisions_active",
            "project_sales_order_id",
            unique=True,
            postgresql_where=text("state = 'active'"),
        ),
        UniqueConstraint(
            "project_sales_order_id", "revision_no", name="uq_so_supply_decisions_revision"
        ),
        {"schema": "projects"},
    )


class SOLineAllocation(Base, CompanyScopedMixin):
    """Where one sales-order line's stock is coming from, once a person has said so (D17).

    Ranked candidates are computed live from `stock`, never stored: a snapshot of somebody
    else's on-hand goes stale the moment they ship, and acting on a stale figure is the
    failure this slice exists to stop. Only the DECISION is persisted here.

    `source_type = "order"` is the honest fourth option: no existing stock covers the line
    and it has to be bought. It carries no warehouse, which is what makes it different from
    a location that happens to hold zero.
    """

    __tablename__ = "so_line_allocations"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    so_line_id = Column(
        UUID(as_uuid=False),
        ForeignKey("projects.sales_order_lines.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_type = Column(String(16), nullable=False)
    warehouse_id = Column(
        UUID(as_uuid=False), ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True
    )
    # The project the stock is being taken FROM, when it is held for someone else.
    source_project_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.projects.id", ondelete="SET NULL"), nullable=True
    )
    qty = Column(Numeric(15, 4), nullable=False)
    claim_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.allocation_claims.id", ondelete="SET NULL"), nullable=True
    )
    # Which atomic SO decision wrote this component (front planning 6.1/6.2). NULL on
    # every row written before Stage 1C, which is why the free-stock reader treats a NULL
    # decision as a live hold: a legacy confirmed allocation still holds its stock.
    decision_id = Column(
        UUID(as_uuid=False),
        ForeignKey("projects.so_supply_decisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    #: What CS typed. Required on Borrow, which is the one component nobody may write in
    #: silence (AC-B09), and carried here beside the quantity it justifies.
    reason = Column(Text, nullable=True)
    #: The donor's position at the moment the Borrow was confirmed: free before, free
    #: after the whole borrow, and what was already committed there. Frozen because the
    #: live figure a month later cannot say what the decision was taken against.
    donor_impact_snapshot = Column(JSONB, nullable=True)
    confirmed_by = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_so_line_allocations_line", "so_line_id"),
        Index("ix_so_line_allocations_decision", "decision_id"),
        {"schema": "projects"},
    )


class AllocationClaim(Base, CompanyScopedMixin):
    """One project asking another for stock it is holding (AC-H4).

    Nothing moves on silence. A claim sits in `requested` until the other project's CS
    accepts or refuses it, and a refusal must carry a reason: "no" without one sends the
    asker back to a person rather than to another source.
    """

    __tablename__ = "allocation_claims"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    from_project_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.projects.id", ondelete="CASCADE"), nullable=False
    )
    to_project_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.projects.id", ondelete="CASCADE"), nullable=False
    )
    so_line_id = Column(
        UUID(as_uuid=False),
        ForeignKey("projects.sales_order_lines.id", ondelete="SET NULL"),
        nullable=True,
    )
    product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    warehouse_id = Column(
        UUID(as_uuid=False), ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True
    )
    qty = Column(Numeric(15, 4), nullable=False)
    state = Column(String(16), nullable=False, server_default=CLAIM_REQUESTED)
    reason = Column(Text, nullable=True)
    requested_by = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_by = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_allocation_claims_to_project", "to_project_id", "state"),
        Index("ix_allocation_claims_line", "so_line_id"),
        {"schema": "projects"},
    )


# --------------------------------------------------------------------------- #
# P8a: divergence between our record and AutoCount's copy of it (D25, Group N) #
# --------------------------------------------------------------------------- #

DIVERGENCE_OPEN = "open"
DIVERGENCE_RESOLVED = "resolved"

DIVERGENCE_SOURCE_UPLOAD = "upload"
DIVERGENCE_SOURCE_ESB = "esb"

RESOLUTION_ACCEPT_THEIRS = "accept_theirs"
RESOLUTION_KEEP_OURS = "keep_ours"


class ProjectSODivergence(Base, CompanyScopedMixin):
    """One inbound comparison that found something (AC-N2).

    Our values are NOT overwritten. Theirs are held beside them until a person answers
    line by line, and while this row is `open` the sales order cannot be amended (AC-N5):
    amending a record we already know is wrong is how two systems drift apart for good.

    At most one open row per sales order, enforced by a partial unique index. A CS
    uploading the same export twice gets one reconciliation, recomputed, not a stack.
    """

    __tablename__ = "so_divergences"
    # Audit entity type pinned to the pre-move table name (ADR-0011).
    __audit_entity_type__ = "project_so_divergences"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    project_sales_order_id = Column(
        UUID(as_uuid=False),
        ForeignKey("projects.sales_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    autocount_doc_no = Column(String(80), nullable=True)
    ingest_source = Column(String(16), nullable=False, server_default=DIVERGENCE_SOURCE_UPLOAD)
    status = Column(String(16), nullable=False, server_default=DIVERGENCE_OPEN)

    compared_count = Column(Integer, nullable=False, server_default="0")
    agreeing_count = Column(Integer, nullable=False, server_default="0")
    differing_count = Column(Integer, nullable=False, server_default="0")

    # Set the moment any row is answered KEEP OURS: AutoCount is holding a value we have
    # decided is wrong, so a corrective document has to go back. Generated on request,
    # never stored, exactly as the original import file is.
    corrective_publish_required = Column(Boolean, nullable=False, server_default="false")
    corrective_publish_taken_at = Column(DateTime(timezone=False), nullable=True)

    detected_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    resolved_at = Column(DateTime(timezone=False), nullable=True)
    resolved_by = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_project_so_divergences_order", "project_sales_order_id"),
        Index("ix_project_so_divergences_status", "status", "detected_at"),
        {"schema": "projects"},
    )


class ProjectSODivergenceLine(Base, CompanyScopedMixin):
    """One compared row: ours, theirs, and which fields disagree (AC-N3).

    Rows that AGREE are stored too. The screen collapses them behind a count, and "47
    lines agree" is only worth reading if the 47 were written down.

    `ours_json` / `theirs_json` hold the compared values as strings at the scale the
    columns store, so the reconciliation screen renders exactly what was compared rather
    than re-deriving it from rows that may since have moved.
    """

    __tablename__ = "so_divergence_lines"
    # Audit entity type pinned to the pre-move table name (ADR-0011).
    __audit_entity_type__ = "project_so_divergence_lines"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    divergence_id = Column(
        UUID(as_uuid=False),
        ForeignKey("projects.so_divergences.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope = Column(String(8), nullable=False)  # header | line
    presence = Column(String(16), nullable=False)  # both | ours_only | theirs_only
    so_line_id = Column(
        UUID(as_uuid=False),
        ForeignKey("projects.sales_order_lines.id", ondelete="SET NULL"),
        nullable=True,
    )
    line_no = Column(Integer, nullable=True)
    product_code = Column(String(80), nullable=True)
    ours_json = Column(JSONB, nullable=True)
    theirs_json = Column(JSONB, nullable=True)
    differing_fields = Column(JSONB, nullable=True)

    resolution = Column(String(16), nullable=True)  # accept_theirs | keep_ours
    reason = Column(Text, nullable=True)
    resolved_by = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_project_so_divergence_lines_divergence", "divergence_id"),
        Index("ix_project_so_divergence_lines_so_line", "so_line_id"),
        {"schema": "projects"},
    )
