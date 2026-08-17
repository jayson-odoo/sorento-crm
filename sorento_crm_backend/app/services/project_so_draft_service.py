"""Sales order drafting: explode, spread, split, cross check, gate (P7, AC-F1 to AC-F12).

Nothing here is a judgement call. Every number is arithmetic over rows other slices
produced, and where the arithmetic cannot be done the draft says so as a FINDING rather
than guessing. That is the whole design: the AI proposes upstream, and this engine either
agrees with countable evidence or blocks.

Four ideas carry the file.

**Set explosion.** The PO speaks in SETS; the quotation and the sales order speak in
components -- a priced parent plus zero-priced companions. ``item_packages`` (the AutoCount
PackageDTL mirror) is authoritative. The quotation grouping is the fallback and it must
reproduce the quoted quantities EXACTLY; where it cannot, the line is left unexploded and
``no_package_mapping`` is raised, because a guessed component split silently commits us to
stock nobody ordered.

**The phase spread is what makes the line count.** Measured on the client's own documents:
SO397450 carries 99 TOWER lines, and the driver is product MULTIPLIED BY delivery phase,
not the explosion. A product ordered once on the PO becomes one line per phase it is
scheduled in, each with its own delivery date.

**The area split is a PROPOSAL, never a rule.** One real PO produced three sales orders:
TOWER, COMMON AREA, and an early product subset with no area logic at all. So the split
records where each grouping came from in ``grouping_origin`` and a person can regroup.
What they regroup is remembered for that customer and proposed next time (AC-F4b), read
back off the sales orders they actually published rather than a preference table -- the
published shape IS the preference, and two records of one fact drift.

**Two tier gate (D9).** Five hard stops, all arithmetic, listed in the contract. A draft
carrying an unacknowledged hard finding cannot publish. Everything else is a warning that
publishes once acknowledged with a reason, and the reason stays on the order forever.
"""
from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
import calendar
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.order import Customer
from app.models.product import Product
from app.models.project_so import (
    SEVERITY_HARD,
    SEVERITY_INFO,
    SEVERITY_WARN,
    SO_STATUS_AMENDED,
    SO_STATUS_AWAITING_COSTING,
    SO_STATUS_BLOCKED,
    SO_STATUS_DRAFT,
    SO_STATUS_PUBLISHED,
    SO_STATUS_READY,
    DeliverySchedule,
    DeliveryScheduleCell,
    DeliveryScheduleVersion,
    ProjectDeliveryPhase,
    ProjectPOLine,
    ProjectPOVersion,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    SODraftFinding,
)
from app.models.procurement import PurchaseRequestHeader, PurchaseRequestLine
from app.models.projects import (
    Project,
    ProjectParty,
    ProjectPurchaseOrder,
    ProjectPurchaseOrderLine,
    ProjectQuotation,
    ProjectQuotationLine,
    ProjectQuotationVersion,
)
from app.models.user import User
from app.services.error_handler import AppException
from app.services.project_so_reconciliation_service import (
    ProjectSOReconciliationService,
)

logger = logging.getLogger(__name__)

_CENTS = Decimal("0.01")
_QTY = Decimal("0.0001")
_ZERO = Decimal("0")

# The five hard stops (contract section 5). Arithmetic, every one of them.
HARD_CODES = (
    "line_arithmetic",
    "total_mismatch",
    "schedule_short",
    "schedule_over",
    "unresolved_product",
)
WARN_CODES = (
    "price_vs_quotation",
    "code_vs_quotation",
    "missing_delivery_date",
    "phase_unmatched",
    "credit_exposure",
    "no_package_mapping",
    "pre_order_overlap",
)

GROUPING_AREA = "area"
GROUPING_LEARNED = "learned"
GROUPING_MANUAL = "manual"
GROUPING_SUBSET = "subset"

EXPLOSION_PACKAGE = "package"
EXPLOSION_QUOTATION = "quotation"
EXPLOSION_NONE = "none"

# The permission that may wave a hard stop through. AC-L1's dedicated
# `projects.sales_order.publish` slug is not registered yet, so the override rides on the
# sales-manager grant, which is who signs off an override in the room anyway.
OVERRIDE_PERMISSION = "projects.projects.manage"

NUMBERING_DOC_TYPE = "project_sales_order"
_REF_PREFIX = "PSO-"
_REF_DIGITS = 6

# UOM words that mean "this line is a set of components". Used only to decide whether a
# missing explosion is worth telling somebody about: raising `no_package_mapping` on every
# ordinary single-item line would bury the one line that genuinely needed exploding.
_SET_UOMS = {"SET", "SETS", "ST", "STS", "KIT", "KITS"}


# --------------------------------------------------------------------- value objects


@dataclass
class _SourceLine:
    """A PO line, normalised across the two places a PO line can live.

    Phase 2 extraction writes ``project_po_lines`` against an immutable document version;
    phase 1 lets someone key the PO in by hand into ``project_purchase_order_lines``. Both
    are real, both must build, and the rest of the engine should not have to care which
    one it got.
    """

    line_no: int
    code: Optional[str]
    description: Optional[str]
    qty: Decimal
    uom: Optional[str]
    unit_price: Decimal
    amount: Decimal
    product_id: Optional[str]
    is_cancelled: bool
    po_line_id: Optional[str]  # project_po_lines.id, or None for a hand-keyed line

    @property
    def label(self) -> str:
        return f"line {self.line_no} {self.code or self.description or 'unnamed item'}".strip()


@dataclass
class _Component:
    product_id: Optional[str]
    code: Optional[str]
    description: Optional[str]
    uom: Optional[str]
    unit_price: Decimal
    numerator: Decimal  # component quantity per `denominator` parent units
    denominator: Decimal
    quotation_line_id: Optional[str] = None


@dataclass
class _Explosion:
    components: List[_Component]
    source: str
    # Set when the fallback was found but could not reproduce the quoted quantities, so
    # the caller can say WHY it left the line whole instead of just that it did.
    refusal: Optional[str] = None


@dataclass
class _LineDraft:
    area_group: Optional[str]
    product_id: Optional[str]
    product_code: Optional[str]
    description: Optional[str]
    qty: Decimal
    uom: Optional[str]
    unit_price: Decimal
    amount: Decimal
    delivery_date: Optional[date]
    phase_id: Optional[str]
    phase_label: Optional[str]
    explosion_source: str
    source_po_line_id: Optional[str]
    source_po_line_no: int
    quotation_line_id: Optional[str]
    persisted_id: Optional[str] = None


@dataclass
class _PendingFinding:
    severity: str
    code: str
    detail: str
    detail_json: Dict[str, Any] = field(default_factory=dict)
    # Which PO line raised it. The finding lands on the first drafted line that came from
    # that PO line, so the screen can point at something the reader can see.
    source_po_line_no: Optional[int] = None
    area_group: Optional[str] = None


def _dec(value: Any, default: Decimal = _ZERO) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENTS)


def _qty_str(value: Decimal) -> str:
    """A quantity as a person writes it, with no scientific notation.

    ``Decimal("100.0000").normalize()`` is ``1E+2``, which on an AutoCount import line
    would read as a price list error rather than a hundred units. The ``f`` format spec is
    what keeps it plain.
    """
    return format(value.normalize(), "f")


def month_end(year: int, month: int) -> date:
    """The LAST day of a month (D29).

    A sponsorship form commits to a month, not a day. The last day is chosen over the first
    deliberately: netting is FIFO by delivery date (AC-I3a), so the last day is the latest
    date the commitment can be honoured and therefore never claims covering stock ahead of
    a dated commercial line in the same month.
    """
    return date(year, month, calendar.monthrange(year, month)[1])


def _norm_code(value: Optional[str]) -> str:
    return (value or "").strip().upper().replace(" ", "")


class ProjectSODraftService:
    """Builds, gates and publishes project sales order drafts."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ build

    def build(
        self,
        purchase_order_id: str,
        schedule_version_id: str,
        *,
        actor_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Draft one or more sales orders from a PO version and a schedule version.

        Idempotent per ``(po_version, schedule_version)``: the schedule version names the
        PO version it reconciles against, so re-running replaces exactly the drafts this
        pair produced before. A PUBLISHED order is never touched -- it is already in
        AutoCount, and quietly rewriting it would make the two systems disagree without
        anybody being told.
        """
        po = self._po_or_404(purchase_order_id)
        project = self._project_or_404(po.project_id)
        schedule_version = self._schedule_version_or_404(schedule_version_id)
        self._assert_schedule_belongs_to_po(schedule_version, po)

        po_version = self._po_version_for(po, schedule_version)
        source_lines = self._source_lines(po, po_version)
        if not source_lines:
            raise AppException(
                status_code=422,
                message=(
                    "This purchase order has no lines yet. Confirm the extracted PO "
                    "version, or key the lines in, before drafting a sales order."
                ),
                code="po_has_no_lines",
            )

        replaced, skipped, committed_areas, reusable_refs = self._clear_previous_drafts(
            po, schedule_version
        )

        quotation_version = self._quotation_version(po)
        findings: List[_PendingFinding] = []
        findings.extend(self._document_findings(source_lines, po_version))

        slices = self._spread_across_phases(
            po=po, schedule_version=schedule_version, source_lines=source_lines, findings=findings
        )
        learned = self._learned_area_map(po)
        drafts = self._draft_lines(
            slices=slices,
            quotation_version=quotation_version,
            learned=learned,
            findings=findings,
        )

        used_learned = any(
            learned.get(_norm_code(draft.product_code)) is not None for draft in drafts
        )
        orders = self._persist(
            po=po,
            project=project,
            schedule_version=schedule_version,
            drafts=drafts,
            findings=findings,
            grouping_origin=GROUPING_LEARNED if used_learned else GROUPING_AREA,
            committed_areas=committed_areas,
            reusable_refs=reusable_refs,
        )
        self.db.flush()
        states = self.review_states_for(orders)
        return {
            "data": [
                self.serialize_row(order, review_states=states) for order in orders
            ],
            "replaced_drafts": replaced,
            "skipped_published": skipped,
        }

    # ------------------------------------------------------- reading the sources

    def _po_or_404(self, purchase_order_id: str) -> ProjectPurchaseOrder:
        po = (
            self.db.query(ProjectPurchaseOrder)
            .filter(ProjectPurchaseOrder.id == purchase_order_id)
            .first()
        )
        if po is None:
            raise AppException(
                status_code=404, message="Purchase order not found.", code="po_not_found"
            )
        return po

    def _project_or_404(self, project_id: str) -> Project:
        project = self.db.query(Project).filter(Project.id == project_id).first()
        if project is None:
            raise AppException(
                status_code=404, message="Project not found.", code="project_not_found"
            )
        return project

    def _schedule_version_or_404(self, version_id: str) -> DeliveryScheduleVersion:
        version = (
            self.db.query(DeliveryScheduleVersion)
            .filter(DeliveryScheduleVersion.id == version_id)
            .first()
        )
        if version is None:
            raise AppException(
                status_code=404,
                message="Delivery schedule version not found.",
                code="schedule_version_not_found",
            )
        return version

    def _assert_schedule_belongs_to_po(
        self, version: DeliveryScheduleVersion, po: ProjectPurchaseOrder
    ) -> None:
        schedule = (
            self.db.query(DeliverySchedule)
            .filter(DeliverySchedule.id == version.delivery_schedule_id)
            .first()
        )
        if schedule is None or schedule.purchase_order_id != po.id:
            raise AppException(
                status_code=422,
                message=(
                    "That delivery schedule belongs to a different purchase order. A "
                    "sales order is drafted from one PO and its own schedule."
                ),
                code="schedule_foreign_po",
            )

    def _po_version_for(
        self, po: ProjectPurchaseOrder, schedule_version: DeliveryScheduleVersion
    ) -> Optional[ProjectPOVersion]:
        """The PO version this build reads.

        The schedule names it (finding G1): a schedule issued before a handwritten
        cancellation reconciles against the PO as it stood. Falling back to the latest
        CONFIRMED version rather than the latest version is deliberate -- an unconfirmed
        extraction is a proposal nobody has read yet.
        """
        if schedule_version.po_version_id:
            named = (
                self.db.query(ProjectPOVersion)
                .filter(ProjectPOVersion.id == schedule_version.po_version_id)
                .first()
            )
            if named is not None:
                return named
        query = self.db.query(ProjectPOVersion).filter(
            ProjectPOVersion.purchase_order_id == po.id
        )
        confirmed = (
            query.filter(ProjectPOVersion.confirmed_at.isnot(None))
            .order_by(ProjectPOVersion.version_no.desc())
            .first()
        )
        return confirmed or query.order_by(ProjectPOVersion.version_no.desc()).first()

    def _source_lines(
        self, po: ProjectPurchaseOrder, po_version: Optional[ProjectPOVersion]
    ) -> List[_SourceLine]:
        if po_version is not None:
            rows = (
                self.db.query(ProjectPOLine)
                .filter(ProjectPOLine.po_version_id == po_version.id)
                .order_by(ProjectPOLine.line_no.asc())
                .all()
            )
            if rows:
                return [
                    _SourceLine(
                        line_no=row.line_no,
                        code=row.stock_code_raw,
                        description=row.description_raw,
                        qty=_dec(row.qty),
                        uom=row.uom_raw,
                        unit_price=_dec(row.unit_price),
                        amount=_dec(row.amount),
                        product_id=row.resolved_product_id,
                        is_cancelled=bool(row.is_cancelled),
                        po_line_id=row.id,
                    )
                    for row in rows
                ]

        hand_keyed = (
            self.db.query(ProjectPurchaseOrderLine)
            .filter(ProjectPurchaseOrderLine.po_id == po.id)
            .order_by(
                ProjectPurchaseOrderLine.sort_order.asc(),
                ProjectPurchaseOrderLine.created_at.asc(),
            )
            .all()
        )
        return [
            _SourceLine(
                line_no=index,
                code=row.product_code,
                description=row.description,
                qty=_dec(row.quantity),
                uom=row.uom,
                unit_price=_dec(row.unit_price),
                amount=_dec(row.line_total),
                product_id=row.product_id,
                is_cancelled=False,
                po_line_id=None,
            )
            for index, row in enumerate(hand_keyed, start=1)
        ]

    def _quotation_version(
        self, po: ProjectPurchaseOrder
    ) -> Optional[ProjectQuotationVersion]:
        if not po.quotation_version_id:
            return None
        return (
            self.db.query(ProjectQuotationVersion)
            .filter(ProjectQuotationVersion.id == po.quotation_version_id)
            .first()
        )

    # ------------------------------------------------------- document arithmetic

    def _document_findings(
        self, source_lines: Sequence[_SourceLine], po_version: Optional[ProjectPOVersion]
    ) -> List[_PendingFinding]:
        """`line_arithmetic`, `total_mismatch` and `unresolved_product`.

        The line sum includes CANCELLED lines on purpose: the printed total includes them
        too, and the cancellation is a handwritten note on top of the document. On the
        client's own PO that identity is exact -- 1,810,640.62 printed, minus the pencilled
        cancellation of 4,733.60, equals the quotation's 1,805,907.02.
        """
        out: List[_PendingFinding] = []
        lines_total = _ZERO
        for line in source_lines:
            lines_total += _money(line.amount)
            expected = _money(line.qty * line.unit_price)
            if expected != _money(line.amount):
                out.append(
                    _PendingFinding(
                        severity=SEVERITY_HARD,
                        code="line_arithmetic",
                        detail=(
                            f"PO {line.label}: {line.qty} x {line.unit_price} is "
                            f"{expected}, but the document says {_money(line.amount)}. "
                            "Correct the line on the PO version before drafting."
                        ),
                        detail_json={
                            "line_no": line.line_no,
                            "qty": str(line.qty),
                            "unit_price": str(line.unit_price),
                            "amount": str(_money(line.amount)),
                            "expected_amount": str(expected),
                        },
                        source_po_line_no=line.line_no,
                    )
                )
            if not line.is_cancelled and not line.product_id:
                out.append(
                    _PendingFinding(
                        severity=SEVERITY_HARD,
                        code="unresolved_product",
                        detail=(
                            f"PO {line.label} has no product. Resolve the code on the PO "
                            "version, or pick the product by hand, before publishing."
                        ),
                        detail_json={
                            "line_no": line.line_no,
                            "stock_code_raw": line.code,
                            "description_raw": line.description,
                        },
                        source_po_line_no=line.line_no,
                    )
                )

        if po_version is not None and po_version.extracted_total is not None:
            printed = _money(_dec(po_version.extracted_total))
            if _money(lines_total) != printed:
                out.append(
                    _PendingFinding(
                        severity=SEVERITY_HARD,
                        code="total_mismatch",
                        detail=(
                            f"The PO lines add up to {_money(lines_total)}, but the total "
                            f"printed on the document reads {printed}. A difference here "
                            "is the single best sign a page was misread."
                        ),
                        detail_json={
                            "lines_total": str(_money(lines_total)),
                            "extracted_total": str(printed),
                            "difference": str(_money(lines_total - printed)),
                        },
                    )
                )
        return out

    # --------------------------------------------------------- the phase spread

    def _spread_across_phases(
        self,
        *,
        po: ProjectPurchaseOrder,
        schedule_version: DeliveryScheduleVersion,
        source_lines: Sequence[_SourceLine],
        findings: List[_PendingFinding],
    ) -> List[Tuple[_SourceLine, Optional[ProjectDeliveryPhase], Decimal]]:
        """Cut each PO line into one slice per delivery phase.

        This is where 52 PO lines become 99 sales order lines: product MULTIPLIED BY
        phase, measured on SO397450. Allocation walks the phases in delivery order and
        consumes the PO lines in line order, so two PO lines for the same product share
        the schedule exactly once and the arithmetic still closes.
        """
        cells = (
            self.db.query(DeliveryScheduleCell, ProjectDeliveryPhase)
            .join(ProjectDeliveryPhase, ProjectDeliveryPhase.id == DeliveryScheduleCell.phase_id)
            .filter(DeliveryScheduleCell.version_id == schedule_version.id)
            .all()
        )
        cells.sort(
            key=lambda pair: (
                pair[1].delivery_date or date.max,
                pair[1].area_group or "",
                pair[1].sequence or 0,
            )
        )

        by_product: Dict[str, List[Tuple[DeliveryScheduleCell, ProjectDeliveryPhase]]] = {}
        for cell, phase in cells:
            if phase.project_id != po.project_id:
                findings.append(
                    _PendingFinding(
                        severity=SEVERITY_WARN,
                        code="phase_unmatched",
                        detail=(
                            f"Schedule phase '{phase.label or phase.area_group}' belongs "
                            "to another project, so its quantity was left out of this "
                            "draft."
                        ),
                        detail_json={"area_group": phase.area_group, "sequence": phase.sequence},
                    )
                )
                continue
            if not cell.product_id:
                findings.append(
                    _PendingFinding(
                        severity=SEVERITY_HARD,
                        code="unresolved_product",
                        detail=(
                            f"The schedule column '{cell.customer_code_raw or 'unnamed'}' "
                            f"carries {_dec(cell.qty)} against "
                            f"'{phase.label or phase.area_group}' but is not mapped to a "
                            "product. Map the customer's code before publishing."
                        ),
                        detail_json={
                            "customer_code_raw": cell.customer_code_raw,
                            "qty": str(_dec(cell.qty)),
                            "area_group": phase.area_group,
                            "sequence": phase.sequence,
                        },
                    )
                )
                continue
            by_product.setdefault(cell.product_id, []).append((cell, phase))

        live_lines = [line for line in source_lines if not line.is_cancelled]
        po_by_product: Dict[str, List[_SourceLine]] = {}
        for line in live_lines:
            if line.product_id:
                po_by_product.setdefault(line.product_id, []).append(line)

        self._reconcile_columns(
            po_by_product=po_by_product, by_product=by_product, findings=findings
        )

        slices: List[Tuple[_SourceLine, Optional[ProjectDeliveryPhase], Decimal]] = [
            # No product means no schedule column to spread across. The line still appears,
            # unphased, so the reader sees what is missing rather than a shorter order than
            # the PO. `unresolved_product` already blocks the publish.
            (line, None, line.qty)
            for line in live_lines
            if not line.product_id
        ]

        for product_id, lines in po_by_product.items():
            remaining = {id(line): line.qty for line in lines}
            for cell, phase in by_product.get(product_id, []):
                outstanding = _dec(cell.qty)
                for line in lines:
                    if outstanding <= _ZERO:
                        break
                    available = remaining[id(line)]
                    if available <= _ZERO:
                        continue
                    take = min(available, outstanding)
                    remaining[id(line)] = available - take
                    outstanding -= take
                    slices.append((line, phase, take))
                # Anything the PO cannot absorb is over-scheduled. It is reported by
                # _reconcile_columns as a hard stop and deliberately NOT drafted: never
                # commit more than the customer ordered.
            for line in lines:
                left = remaining[id(line)]
                if left > _ZERO:
                    slices.append((line, None, left))
                    findings.append(
                        _PendingFinding(
                            severity=SEVERITY_WARN,
                            code="missing_delivery_date",
                            detail=(
                                f"{left} of PO {line.label} is not on the delivery "
                                "schedule, so those units have no delivery date."
                            ),
                            detail_json={"line_no": line.line_no, "qty": str(left)},
                            source_po_line_no=line.line_no,
                        )
                    )

        # Schedule columns for products the PO never ordered.
        for product_id, entries in by_product.items():
            if product_id in po_by_product:
                continue
            total = sum((_dec(cell.qty) for cell, _phase in entries), _ZERO)
            code = self._product_code(product_id)
            findings.append(
                _PendingFinding(
                    severity=SEVERITY_HARD,
                    code="schedule_over",
                    detail=(
                        f"The schedule asks for {total} of {code}, which is not on this "
                        "purchase order at all. Fix the column or the PO before "
                        "publishing."
                    ),
                    detail_json={"product_code": code, "scheduled": str(total), "po_qty": "0"},
                )
            )

        slices.sort(
            key=lambda item: (
                item[1].delivery_date if item[1] and item[1].delivery_date else date.max,
                item[1].area_group if item[1] else "",
                item[1].sequence if item[1] else 0,
                item[0].line_no,
            )
        )
        return slices

    def _reconcile_columns(
        self,
        *,
        po_by_product: Dict[str, List[_SourceLine]],
        by_product: Dict[str, List[Tuple[DeliveryScheduleCell, ProjectDeliveryPhase]]],
        findings: List[_PendingFinding],
    ) -> None:
        """`schedule_short` / `schedule_over`, per product, never per document.

        Per column is the whole point (measured 2026-08-02: 29/37 columns reconciled on
        R1). A wholesale reject would reject nearly every real schedule; naming the column
        lets CS fix the one cell that is wrong.
        """
        for product_id, lines in po_by_product.items():
            po_qty = sum((line.qty for line in lines), _ZERO)
            scheduled = sum(
                (_dec(cell.qty) for cell, _phase in by_product.get(product_id, [])), _ZERO
            )
            if scheduled == po_qty:
                continue
            code = self._product_code(product_id)
            if scheduled < po_qty:
                findings.append(
                    _PendingFinding(
                        severity=SEVERITY_HARD,
                        code="schedule_short",
                        detail=(
                            f"{code}: the PO orders {po_qty} but the schedule only "
                            f"places {scheduled}. {po_qty - scheduled} has no delivery "
                            "date."
                        ),
                        detail_json={
                            "product_code": code,
                            "po_qty": str(po_qty),
                            "scheduled": str(scheduled),
                            "difference": str(po_qty - scheduled),
                        },
                        source_po_line_no=lines[0].line_no,
                    )
                )
            else:
                findings.append(
                    _PendingFinding(
                        severity=SEVERITY_HARD,
                        code="schedule_over",
                        detail=(
                            f"{code}: the schedule places {scheduled} but the PO only "
                            f"orders {po_qty}. The extra {scheduled - po_qty} was not "
                            "drafted."
                        ),
                        detail_json={
                            "product_code": code,
                            "po_qty": str(po_qty),
                            "scheduled": str(scheduled),
                            "difference": str(scheduled - po_qty),
                        },
                        source_po_line_no=lines[0].line_no,
                    )
                )

    # ------------------------------------------------------------- the explosion

    def _package_components(
        self,
        source: _SourceLine,
        *,
        parent_price: Decimal,
        quotation_line_id: Optional[str],
    ) -> Optional[_Explosion]:
        """``item_packages`` (the AutoCount PackageDTL mirror) is authoritative (D10).

        Read through raw SQL because the mirror's ORM model ships on the AutoCount branch
        and is not mapped here; the TABLE is the same table either way. ``to_regclass``
        answers "is the mirror installed" without an error that would poison the
        transaction, and a missing mirror simply falls through to the quotation.
        """
        code = _norm_code(source.code) or _norm_code(self._product_code(source.product_id))
        if not code:
            return None
        if self.db.execute(text("SELECT to_regclass('item_package_lines')")).scalar() is None:
            return None

        rows = self.db.execute(
            text(
                """
                SELECT l.product_id, l.qty, l.uom, l.unit_price, l.line_sequence,
                       p.product_code, p.product_name
                  FROM item_package_lines l
                  JOIN item_packages k ON k.id = l.item_package_id
                  LEFT JOIN products p ON p.id = l.product_id
                 WHERE upper(replace(k.package_code, ' ', '')) = :code
                 ORDER BY l.line_sequence
                """
            ),
            {"code": code},
        ).fetchall()
        if not rows:
            return None

        parent_index = 0
        for index, row in enumerate(rows):
            if source.product_id and str(row.product_id) == str(source.product_id):
                parent_index = index
                break
        else:
            # No component IS the ordered item, so the priced parent is the dearest line:
            # that is what the package is sold as, and the companions ride at zero.
            parent_index = max(
                range(len(rows)), key=lambda i: _dec(rows[i].unit_price), default=0
            )

        parent_qty = _dec(rows[parent_index].qty, Decimal("1")) or Decimal("1")
        components = [
            _Component(
                product_id=str(row.product_id) if row.product_id else None,
                code=row.product_code,
                description=row.product_name,
                uom=row.uom,
                unit_price=_ZERO,
                numerator=_dec(row.qty, Decimal("1")),
                denominator=parent_qty,
            )
            for row in rows
        ]
        # The parent carries the price and the companions ride at zero, exactly as the
        # quotation and the real sales order are written.
        components[parent_index].unit_price = parent_price
        components[parent_index].quotation_line_id = quotation_line_id
        return _Explosion(components=components, source=EXPLOSION_PACKAGE)

    def _quotation_components(
        self, source: _SourceLine, quotation_version: Optional[ProjectQuotationVersion]
    ) -> Optional[_Explosion]:
        """The fallback: a priced parent plus the zero-priced companions that follow it.

        Verified against QT-004188: 60 lines, 52 priced and 8 at zero, and a companion sits
        IMMEDIATELY after its parent at the SAME quantity. So the run is read in
        ``sort_order`` and the multiplier is the companion's quoted quantity over the
        parent's -- which is 1 on every real line, and is checked for exactness rather
        than assumed.
        """
        if quotation_version is None or not source.product_id:
            return None
        lines = (
            self.db.query(ProjectQuotationLine)
            .filter(ProjectQuotationLine.version_id == quotation_version.id)
            .order_by(ProjectQuotationLine.sort_order.asc(), ProjectQuotationLine.created_at.asc())
            .all()
        )
        if not lines:
            return None

        parent_index = None
        for index, line in enumerate(lines):
            if line.product_id == source.product_id and _dec(line.unit_price) > _ZERO:
                parent_index = index
                break
        if parent_index is None:
            return None

        parent = lines[parent_index]
        parent_qty = _dec(parent.quantity)
        run = [parent]
        for line in lines[parent_index + 1 :]:
            if _dec(line.unit_price) > _ZERO:
                break
            run.append(line)
        if len(run) == 1:
            # A priced line with no companions is not a set: nothing to explode.
            return None
        if parent_qty <= _ZERO:
            return _Explosion(
                components=[],
                source=EXPLOSION_QUOTATION,
                refusal=(
                    "the quotation prices this item at quantity zero, so the component "
                    "split cannot be worked out"
                ),
            )

        components = []
        for line in run:
            components.append(
                _Component(
                    product_id=line.product_id,
                    code=line.product_code_snapshot,
                    description=line.description_snapshot,
                    uom=line.uom,
                    unit_price=_dec(line.unit_price),
                    numerator=_dec(line.quantity),
                    denominator=parent_qty,
                    quotation_line_id=line.id,
                )
            )
        return _Explosion(components=components, source=EXPLOSION_QUOTATION)

    def _component_qty(self, slice_qty: Decimal, component: _Component) -> Optional[Decimal]:
        """Multiply THEN divide, so an exact ratio stays exact.

        ``slice_qty * numerator / denominator`` with the multiplication first means a
        companion quoted at the parent's own quantity reproduces it to the unit. A
        remainder means the quotation cannot reproduce the quantities and the caller must
        report it rather than round it away.
        """
        if component.denominator <= _ZERO:
            return None
        product = slice_qty * component.numerator
        if product % component.denominator != _ZERO:
            return None
        return (product / component.denominator).quantize(_QTY)

    # ----------------------------------------------------------- drafting lines

    def _draft_lines(
        self,
        *,
        slices: Sequence[Tuple[_SourceLine, Optional[ProjectDeliveryPhase], Decimal]],
        quotation_version: Optional[ProjectQuotationVersion],
        learned: Dict[str, str],
        findings: List[_PendingFinding],
    ) -> List[_LineDraft]:
        explosions: Dict[int, _Explosion] = {}
        priced_reported: set[int] = set()
        drafts: List[_LineDraft] = []

        for source, phase, qty in slices:
            if source.line_no not in explosions:
                explosions[source.line_no] = self._explosion_for(
                    source, quotation_version, findings
                )
                self._price_findings(source, quotation_version, findings, priced_reported)
            explosion = explosions[source.line_no]

            components = explosion.components or [
                self._direct_component(source, quotation_version)
            ]
            source_kind = explosion.source if explosion.components else EXPLOSION_NONE

            for component in components:
                component_qty = self._component_qty(qty, component)
                if component_qty is None:
                    component_qty = qty
                unit_price = component.unit_price
                area = (
                    learned.get(_norm_code(component.code))
                    or (phase.area_group if phase else None)
                )
                drafts.append(
                    _LineDraft(
                        area_group=area,
                        product_id=component.product_id,
                        product_code=component.code,
                        description=component.description or source.description,
                        qty=component_qty,
                        uom=component.uom or source.uom,
                        unit_price=unit_price,
                        amount=_money(component_qty * unit_price),
                        delivery_date=phase.delivery_date if phase else None,
                        phase_id=phase.id if phase else None,
                        phase_label=(phase.label or phase.area_group) if phase else None,
                        explosion_source=source_kind,
                        source_po_line_id=source.po_line_id,
                        source_po_line_no=source.line_no,
                        quotation_line_id=component.quotation_line_id,
                    )
                )
        return drafts

    def _explosion_for(
        self,
        source: _SourceLine,
        quotation_version: Optional[ProjectQuotationVersion],
        findings: List[_PendingFinding],
    ) -> _Explosion:
        # Priced from the QUOTATION where one exists, on either explosion path: the
        # quotation is what we committed to (D4), and the PO is a scan somebody read.
        quoted = self._quoted_line(source, quotation_version)
        parent_price = _dec(quoted.unit_price) if quoted else source.unit_price

        package = self._package_components(
            source,
            parent_price=parent_price,
            quotation_line_id=quoted.id if quoted else None,
        )
        if package is not None:
            return package

        fallback = self._quotation_components(source, quotation_version)
        if fallback is not None and fallback.components:
            unusable = [
                component
                for component in fallback.components
                if self._component_qty(source.qty, component) is None
            ]
            if not unusable:
                return fallback
            names = ", ".join(component.code or "unnamed" for component in unusable)
            findings.append(
                _PendingFinding(
                    severity=SEVERITY_WARN,
                    code="no_package_mapping",
                    detail=(
                        f"PO {source.label} is a set, but the quotation's grouping cannot "
                        f"reproduce the quoted quantities for {names} at {source.qty}. "
                        "The line was drafted whole; add an item package or fix the "
                        "quotation quantities."
                    ),
                    detail_json={"line_no": source.line_no, "components": names},
                    source_po_line_no=source.line_no,
                )
            )
            return _Explosion(components=[], source=EXPLOSION_NONE)

        if fallback is not None and fallback.refusal:
            findings.append(
                _PendingFinding(
                    severity=SEVERITY_WARN,
                    code="no_package_mapping",
                    detail=f"PO {source.label}: {fallback.refusal}. The line was drafted whole.",
                    detail_json={"line_no": source.line_no},
                    source_po_line_no=source.line_no,
                )
            )
            return _Explosion(components=[], source=EXPLOSION_NONE)

        if _norm_code(source.uom) in _SET_UOMS:
            findings.append(
                _PendingFinding(
                    severity=SEVERITY_WARN,
                    code="no_package_mapping",
                    detail=(
                        f"PO {source.label} is ordered in {source.uom} but there is no "
                        "item package and no quotation grouping to explode it with. It "
                        "was drafted as a single line."
                    ),
                    detail_json={"line_no": source.line_no, "uom": source.uom},
                    source_po_line_no=source.line_no,
                )
            )
        return _Explosion(components=[], source=EXPLOSION_NONE)

    def _direct_component(
        self, source: _SourceLine, quotation_version: Optional[ProjectQuotationVersion]
    ) -> _Component:
        quoted = self._quoted_line(source, quotation_version)
        return _Component(
            product_id=source.product_id,
            code=(quoted.product_code_snapshot if quoted else None) or source.code,
            description=(quoted.description_snapshot if quoted else None) or source.description,
            uom=source.uom or (quoted.uom if quoted else None),
            unit_price=_dec(quoted.unit_price) if quoted else source.unit_price,
            numerator=Decimal("1"),
            denominator=Decimal("1"),
            quotation_line_id=quoted.id if quoted else None,
        )

    def _quoted_line(
        self, source: _SourceLine, quotation_version: Optional[ProjectQuotationVersion]
    ) -> Optional[ProjectQuotationLine]:
        if quotation_version is None:
            return None
        query = self.db.query(ProjectQuotationLine).filter(
            ProjectQuotationLine.version_id == quotation_version.id
        )
        if source.product_id:
            return query.filter(ProjectQuotationLine.product_id == source.product_id).first()
        if source.code:
            return query.filter(
                func.upper(ProjectQuotationLine.product_code_snapshot) == _norm_code(source.code)
            ).first()
        return None

    def _price_findings(
        self,
        source: _SourceLine,
        quotation_version: Optional[ProjectQuotationVersion],
        findings: List[_PendingFinding],
        reported: set[int],
    ) -> None:
        """`price_vs_quotation` and `code_vs_quotation`, once per PO line.

        The draft is priced from the QUOTATION, not from the PO: the quotation is what we
        committed to (D4), and the PO is a scan somebody read. Where the two disagree the
        difference is put in front of CS with both figures rather than silently resolved.
        """
        if source.line_no in reported:
            return
        reported.add(source.line_no)
        quoted = self._quoted_line(source, quotation_version)
        if quoted is None:
            return
        if _money(_dec(quoted.unit_price)) != _money(source.unit_price):
            findings.append(
                _PendingFinding(
                    severity=SEVERITY_WARN,
                    code="price_vs_quotation",
                    detail=(
                        f"PO {source.label} is priced at {_money(source.unit_price)}; the "
                        f"quotation says {_money(_dec(quoted.unit_price))}. The draft uses "
                        "the quotation price."
                    ),
                    detail_json={
                        "line_no": source.line_no,
                        "po_unit_price": str(_money(source.unit_price)),
                        "quoted_unit_price": str(_money(_dec(quoted.unit_price))),
                    },
                    source_po_line_no=source.line_no,
                )
            )
        quoted_code = _norm_code(quoted.product_code_snapshot)
        if quoted_code and _norm_code(source.code) and _norm_code(source.code) != quoted_code:
            findings.append(
                _PendingFinding(
                    severity=SEVERITY_WARN,
                    code="code_vs_quotation",
                    detail=(
                        f"The PO prints '{source.code}' on line {source.line_no}; the "
                        f"quotation and catalogue say '{quoted.product_code_snapshot}'. "
                        "The customer's column truncates codes, so this is usually the "
                        "same item."
                    ),
                    detail_json={
                        "line_no": source.line_no,
                        "po_code": source.code,
                        "quoted_code": quoted.product_code_snapshot,
                    },
                    source_po_line_no=source.line_no,
                )
            )

    # --------------------------------------------------------------- the split

    def _learned_area_map(self, po: ProjectPurchaseOrder) -> Dict[str, str]:
        """What this customer's last hand-regrouped order looked like (AC-F4b).

        Read off the sales orders they actually published rather than a preference table.
        The published shape IS the preference, and holding the same fact twice means the
        two answers eventually disagree.
        """
        customer_key = self._customer_key(po)
        if not customer_key:
            return {}

        siblings = (
            self.db.query(ProjectSalesOrder)
            .join(
                ProjectPurchaseOrder,
                ProjectPurchaseOrder.id == ProjectSalesOrder.purchase_order_id,
            )
            .join(ProjectParty, ProjectParty.id == ProjectPurchaseOrder.issuing_party_id)
            .filter(
                ProjectSalesOrder.grouping_origin == GROUPING_MANUAL,
                ProjectSalesOrder.purchase_order_id != po.id,
                (ProjectParty.customer_id == customer_key) | (ProjectParty.id == customer_key),
            )
            .order_by(ProjectSalesOrder.updated_at.desc())
            .all()
        )
        learned: Dict[str, str] = {}
        for order in siblings:
            if not order.area_group:
                continue
            for line in self._lines_of(order.id):
                key = _norm_code(self._product_code(line.product_id))
                if key and key not in learned:
                    learned[key] = order.area_group
        return learned

    def _customer_key(self, po: ProjectPurchaseOrder) -> Optional[str]:
        if not po.issuing_party_id:
            return None
        party = (
            self.db.query(ProjectParty).filter(ProjectParty.id == po.issuing_party_id).first()
        )
        if party is None:
            return None
        return party.customer_id or party.id

    # ------------------------------------------------------------- persistence

    def _clear_previous_drafts(
        self, po: ProjectPurchaseOrder, schedule_version: DeliveryScheduleVersion
    ) -> Tuple[int, int, set, Dict[Optional[str], str]]:
        """Replace what this pair drafted before; leave anything committed alone.

        Returns the area groups that are already published as well as the counts. Those
        groups are then NOT re-drafted: a second TOWER draft beside a published TOWER order
        would be a duplicate commitment, and the way to change a published order is an
        amendment.

        Also returns the provisional ref each deleted draft was carrying, keyed by area
        group, so ``_persist`` can give the replacement the SAME reference. Re-uploading the
        same PO and schedule is meant to be a no-op, and it is not one if PSO-000123 comes
        back as PSO-000125: every note, email and printed worksheet quoting the old number
        now points at a row that no longer exists. The rows really are deleted and rebuilt,
        because that is what makes the rebuild correct when the schedule DID change, so the
        reference is carried across rather than the row kept.
        """
        existing = (
            self.db.query(ProjectSalesOrder)
            .filter(
                ProjectSalesOrder.purchase_order_id == po.id,
                ProjectSalesOrder.schedule_version_id == schedule_version.id,
            )
            .order_by(ProjectSalesOrder.provisional_ref.asc())
            .all()
        )
        replaced = 0
        skipped = 0
        committed: set = set()
        reusable_refs: Dict[Optional[str], str] = {}
        for order in existing:
            if order.status in (SO_STATUS_DRAFT, SO_STATUS_BLOCKED, SO_STATUS_READY):
                # Ordered by ref above, so two drafts sharing an area group hand on the
                # lower of the two rather than whichever the database returned first.
                reusable_refs.setdefault(order.area_group, order.provisional_ref)
                self.db.delete(order)
                replaced += 1
            else:
                skipped += 1
                committed.add(order.area_group)
        self.db.flush()
        return replaced, skipped, committed, reusable_refs

    def _persist(
        self,
        *,
        po: ProjectPurchaseOrder,
        project: Project,
        schedule_version: DeliveryScheduleVersion,
        drafts: Sequence[_LineDraft],
        findings: List[_PendingFinding],
        grouping_origin: str,
        committed_areas: set,
        reusable_refs: Optional[Dict[Optional[str], str]] = None,
    ) -> List[ProjectSalesOrder]:
        grouped: Dict[Optional[str], List[_LineDraft]] = {}
        for draft in drafts:
            if draft.area_group in committed_areas:
                continue
            grouped.setdefault(draft.area_group, []).append(draft)
        if not grouped and committed_areas:
            return []
        if not grouped:
            # Every line cancelled by handwriting, or nothing left to draft. Refusing is
            # the honest answer: a sales order with no lines is not a proposal, and a
            # findings list with no order to hang it on cannot be shown to anybody.
            raise AppException(
                status_code=422,
                message=(
                    "Nothing to draft: every line on this purchase order is cancelled or "
                    "carries no quantity."
                ),
                code="so_nothing_to_draft",
            )

        carried = dict(reusable_refs or {})
        orders: List[ProjectSalesOrder] = []
        for area_group in sorted(grouped, key=lambda value: (value is None, value or "")):
            # The ref this area group already had, when the rebuild replaced a draft
            # carrying one. A genuinely new area group takes the next number -- and must
            # be told which refs are still owed to the groups after it in this loop: the
            # drafts carrying them were deleted before this ran, so `_next_ref` cannot see
            # them, and the groups are minted in name order, so a new group sorting first
            # would otherwise be handed the very number the group after it takes back.
            provisional_ref = carried.pop(area_group, None) or self._next_ref(
                project.company_id, reserved=carried.values()
            )
            order = ProjectSalesOrder(
                company_id=project.company_id,
                project_id=project.id,
                purchase_order_id=po.id,
                schedule_version_id=schedule_version.id,
                area_group=area_group,
                provisional_ref=provisional_ref,
                status=SO_STATUS_DRAFT,
                grouping_origin=grouping_origin,
            )
            self.db.add(order)
            self.db.flush()
            self._write_lines(order, grouped[area_group])
            orders.append(order)

        # Totals BEFORE the findings that read them: the credit warning compares this
        # order's value against the limit, and a total of None reads as a free order.
        for order in orders:
            self._recompute_total(order)
        self._attach_findings(orders, findings)
        for order in orders:
            self._refresh_status(order)
        self.db.flush()
        return orders

    def _write_lines(self, order: ProjectSalesOrder, drafts: Sequence[_LineDraft]) -> None:
        ordered = sorted(
            drafts,
            key=lambda draft: (
                draft.delivery_date or date.max,
                draft.source_po_line_no,
                draft.product_code or "",
            ),
        )
        for index, draft in enumerate(ordered, start=1):
            row = ProjectSalesOrderLine(
                company_id=order.company_id,
                project_sales_order_id=order.id,
                line_no=index,
                product_id=draft.product_id,
                description=draft.description,
                qty=draft.qty,
                uom=draft.uom,
                unit_price=draft.unit_price,
                amount=draft.amount,
                delivery_date=draft.delivery_date,
                phase_id=draft.phase_id,
                source_po_line_id=draft.source_po_line_id,
                quotation_line_id=draft.quotation_line_id,
                explosion_source=draft.explosion_source,
            )
            self.db.add(row)
            self.db.flush()
            draft.persisted_id = row.id
            # Kept on the draft so a finding raised against a PO line can point at the
            # first sales order line that came out of it.
            setattr(row, "_source_po_line_no", draft.source_po_line_no)

    def _attach_findings(
        self, orders: Sequence[ProjectSalesOrder], findings: Sequence[_PendingFinding]
    ) -> None:
        """Point every finding at a line somebody can see, on every order it affects.

        A PO line that is short-scheduled or fails its own arithmetic reaches EVERY sales
        order that carries a slice of it, because each of those orders has its own publish
        gate: recording the problem on one sibling only would let the other one publish
        half a broken PO. A finding with no line at all lands on every order in the build,
        for the same reason.
        """
        if not orders:
            return
        first_line_by_po_line: Dict[int, List[Tuple[ProjectSalesOrder, ProjectSalesOrderLine]]] = {}
        for order in orders:
            seen: set = set()
            for line in self._lines_of(order.id):
                key = self._source_line_no(line)
                if key is None or key in seen:
                    continue
                seen.add(key)
                first_line_by_po_line.setdefault(key, []).append((order, line))

        for finding in findings:
            targets = first_line_by_po_line.get(finding.source_po_line_no or -1)
            if not targets:
                targets = [(order, None) for order in orders]
            for order, line in targets:
                self.db.add(
                    SODraftFinding(
                        company_id=order.company_id,
                        project_sales_order_id=order.id,
                        line_id=line.id if line is not None else None,
                        severity=finding.severity,
                        code=finding.code,
                        detail=finding.detail,
                        detail_json=finding.detail_json or None,
                    )
                )
        self.db.flush()

        for order in orders:
            self._credit_finding(order)
            self._pre_order_finding(order)
        self.db.flush()

    def _source_line_no(self, line: ProjectSalesOrderLine) -> Optional[int]:
        cached = getattr(line, "_source_po_line_no", None)
        if cached is not None:
            return int(cached)
        if not line.source_po_line_id:
            return None
        row = (
            self.db.query(ProjectPOLine.line_no)
            .filter(ProjectPOLine.id == line.source_po_line_id)
            .first()
        )
        return int(row[0]) if row else None

    def _next_ref(
        self, company_id: str, *, reserved: Optional[Iterable[str]] = None
    ) -> str:
        """A provisional reference, from the numbering rule when one is configured.

        Falls back to the highest existing reference plus one rather than refusing: this
        is an INTERNAL handle that the customer never sees, and blocking a whole build on
        an unseeded settings row would be a rule with no purpose behind it. Nothing seeds
        a `project_sales_order` rule today, so the fallback IS the path production takes.

        ``reserved`` are references that are NOT in the table but are already spoken for:
        the refs a rebuild is carrying from drafts it deleted a moment ago. Counted here
        as though they were still stored, because otherwise the fallback re-mints one of
        them and two orders claim the same reference.
        """
        from app.services.numbering_service import NumberingService

        taken = {ref for ref in (reserved or ()) if ref}
        configured = NumberingService(self.db).get_next_number(
            NUMBERING_DOC_TYPE, commit_rule=False
        )
        if configured and configured not in taken:
            return configured

        highest = 0
        rows = (
            self.db.query(ProjectSalesOrder.provisional_ref)
            .filter(
                ProjectSalesOrder.company_id == company_id,
                ProjectSalesOrder.provisional_ref.like(f"{_REF_PREFIX}%"),
            )
            .all()
        )
        for ref in [row[0] for row in rows] + sorted(taken):
            if not (ref or "").startswith(_REF_PREFIX):
                continue
            tail = ref[len(_REF_PREFIX) :]
            if tail.isdigit():
                highest = max(highest, int(tail))
        return f"{_REF_PREFIX}{highest + 1:0{_REF_DIGITS}d}"

    # ---------------------------------------------------------------- findings

    def _credit_finding(self, order: ProjectSalesOrder) -> None:
        """AC-F9 / AC-F9a. Re-evaluated at publish, not only at draft time.

        A pre-order is a parking route, not a commercial fact (D18), so it is excluded
        from credit entirely. Where AR has not been ingested yet the warning degrades to
        this order's value against the limit and SAYS so, rather than implying we checked
        something we did not.
        """
        self._drop_findings(order, "credit_exposure")
        if order.is_pre_order or order.is_sponsorship:
            return
        customer = self._customer_for(order)
        if customer is None:
            return
        limit = self._credit_limit(customer.id)
        if limit is None or limit <= _ZERO:
            return

        order_value = _money(_dec(order.total_amount))
        outstanding = _dec(customer.ar_outstanding) if customer.ar_outstanding is not None else None
        exposure = order_value + (outstanding or _ZERO)
        if exposure <= limit:
            return
        if outstanding is None:
            detail = (
                f"{customer.customer_name} has a credit limit of {_money(limit)} and this "
                f"order is {order_value}. Their outstanding balance has not been ingested "
                "yet, so only the order value was compared."
            )
        else:
            as_of = customer.ar_as_of.strftime("%d %b %Y") if customer.ar_as_of else "an unknown date"
            detail = (
                f"{customer.customer_name} owes {_money(outstanding)} as of {as_of}; with "
                f"this order at {order_value} that is {_money(exposure)} against a limit of "
                f"{_money(limit)}."
            )
        self.db.add(
            SODraftFinding(
                company_id=order.company_id,
                project_sales_order_id=order.id,
                severity=SEVERITY_WARN,
                code="credit_exposure",
                detail=detail,
                detail_json={
                    "customer_name": customer.customer_name,
                    "credit_limit": str(_money(limit)),
                    "ar_outstanding": str(_money(outstanding)) if outstanding is not None else None,
                    "order_value": str(order_value),
                    "exposure": str(_money(exposure)),
                },
            )
        )

    def _pre_order_finding(self, order: ProjectSalesOrder) -> None:
        """`pre_order_overlap`: this project already holds a pre-order for the product.

        Information with a warning's weight, not a block (D22): on a fifteen phase
        schedule every phase legitimately repeats the same products, and the pre-order is
        netted off later by the order inquiry rather than removed here.
        """
        self._drop_findings(order, "pre_order_overlap")
        product_ids = {
            line.product_id for line in self._lines_of(order.id) if line.product_id
        }
        if not product_ids:
            return
        overlapping = (
            self.db.query(ProjectSalesOrderLine.product_id, func.sum(ProjectSalesOrderLine.qty))
            .join(
                ProjectSalesOrder,
                ProjectSalesOrder.id == ProjectSalesOrderLine.project_sales_order_id,
            )
            .filter(
                ProjectSalesOrder.project_id == order.project_id,
                ProjectSalesOrder.id != order.id,
                ProjectSalesOrder.is_pre_order.is_(True),
                ProjectSalesOrderLine.product_id.in_(product_ids),
            )
            .group_by(ProjectSalesOrderLine.product_id)
            .all()
        )
        for product_id, qty in overlapping:
            code = self._product_code(product_id)
            self.db.add(
                SODraftFinding(
                    company_id=order.company_id,
                    project_sales_order_id=order.id,
                    severity=SEVERITY_WARN,
                    code="pre_order_overlap",
                    detail=(
                        f"{_dec(qty)} of {code} is already on a pre-order for this "
                        "project. Purchasing will net it off before ordering."
                    ),
                    detail_json={"product_code": code, "pre_ordered_qty": str(_dec(qty))},
                )
            )

    def _drop_findings(self, order: ProjectSalesOrder, code: str) -> None:
        for finding in (
            self.db.query(SODraftFinding)
            .filter(
                SODraftFinding.project_sales_order_id == order.id,
                SODraftFinding.code == code,
                SODraftFinding.acknowledged_at.is_(None),
            )
            .all()
        ):
            self.db.delete(finding)
        self.db.flush()

    def acknowledge_finding(
        self,
        finding_id: str,
        *,
        reason: str,
        actor_user_id: str,
        permissions: Iterable[str],
    ) -> SODraftFinding:
        """Clear a finding with a reason that stays on the order forever (D9).

        A hard stop can be acknowledged too -- there are real reasons to publish past one
        -- but only by somebody carrying the override, and never silently.
        """
        finding = (
            self.db.query(SODraftFinding).filter(SODraftFinding.id == finding_id).first()
        )
        if finding is None:
            raise AppException(
                status_code=404, message="Finding not found.", code="finding_not_found"
            )
        cleaned = (reason or "").strip()
        if len(cleaned) < 3:
            raise AppException(
                status_code=422,
                message="A reason of at least 3 characters is required.",
                code="finding_reason_required",
            )
        if finding.severity == SEVERITY_HARD and OVERRIDE_PERMISSION not in set(permissions):
            raise AppException(
                status_code=403,
                message=(
                    "This is a hard stop. Only a sales manager can acknowledge it, and "
                    "the reason stays on the sales order."
                ),
                code="finding_override_denied",
            )

        finding.acknowledged_by = actor_user_id
        finding.acknowledged_at = datetime.utcnow()
        finding.acknowledged_reason = cleaned
        self.db.flush()

        order = self._order_or_404(finding.project_sales_order_id)
        self._recompute(order)
        return finding

    def blocking_findings(self, order: ProjectSalesOrder) -> List[SODraftFinding]:
        return (
            self.db.query(SODraftFinding)
            .filter(
                SODraftFinding.project_sales_order_id == order.id,
                SODraftFinding.severity == SEVERITY_HARD,
                SODraftFinding.acknowledged_at.is_(None),
            )
            .order_by(SODraftFinding.code.asc())
            .all()
        )

    # ------------------------------------------------------------- line edits

    def update_line(
        self, order: ProjectSalesOrder, line_id: str, payload: Dict[str, Any]
    ) -> ProjectSalesOrderLine:
        self._assert_editable(order)
        line = (
            self.db.query(ProjectSalesOrderLine)
            .filter(
                ProjectSalesOrderLine.id == line_id,
                ProjectSalesOrderLine.project_sales_order_id == order.id,
            )
            .first()
        )
        if line is None:
            raise AppException(
                status_code=404, message="Sales order line not found.", code="so_line_not_found"
            )
        for field_name in ("qty", "unit_price", "uom", "description", "delivery_date", "stock_location"):
            if field_name in payload and payload[field_name] is not None:
                setattr(line, field_name, payload[field_name])
        if payload.get("product_id"):
            line.product_id = payload["product_id"]
        line.amount = _money(_dec(line.qty) * _dec(line.unit_price))
        self.db.flush()
        self._recompute(order)
        return line

    def regroup(
        self, order: ProjectSalesOrder, groups: Sequence[Dict[str, Any]]
    ) -> List[ProjectSalesOrder]:
        """Re-split this draft's lines, and remember the shape for the customer (G2).

        Area is a default, not a rule: one real PO produced THREE sales orders, one of
        them an early product subset with no area logic at all. Lines may also be pulled
        in from a sibling draft of the same build, which is how two proposed orders are
        merged into one.
        """
        self._assert_editable(order)
        siblings = self._build_siblings(order)
        by_id = {
            line.id: line
            for sibling in siblings
            for line in self._lines_of(sibling.id)
        }
        own_line_ids = {line.id for line in self._lines_of(order.id)}

        named: Dict[str, Optional[str]] = {}
        for group in groups:
            for line_id in group.get("line_ids") or []:
                if line_id not in by_id:
                    raise AppException(
                        status_code=422,
                        message=(
                            "One of the lines is not part of this draft. Regrouping can "
                            "only move lines between the sales orders this build "
                            "produced."
                        ),
                        code="regroup_line_foreign",
                    )
                if line_id in named:
                    raise AppException(
                        status_code=422,
                        message="A line was listed in two groups. Each line belongs to one sales order.",
                        code="regroup_line_duplicated",
                    )
                named[line_id] = (group.get("area_group") or None)

        missing = own_line_ids - set(named)
        if missing:
            raise AppException(
                status_code=422,
                message=(
                    f"{len(missing)} of this sales order's lines were not placed in a "
                    "group. Regrouping re-splits every line, so none is left behind."
                ),
                code="regroup_incomplete",
            )

        targets: Dict[Optional[str], ProjectSalesOrder] = {}
        for sibling in siblings:
            targets.setdefault(sibling.area_group, sibling)

        touched: Dict[str, ProjectSalesOrder] = {sibling.id: sibling for sibling in siblings}
        for line_id, area_group in named.items():
            target = targets.get(area_group)
            if target is None:
                target = ProjectSalesOrder(
                    company_id=order.company_id,
                    project_id=order.project_id,
                    purchase_order_id=order.purchase_order_id,
                    schedule_version_id=order.schedule_version_id,
                    area_group=area_group,
                    provisional_ref=self._next_ref(order.company_id),
                    status=SO_STATUS_DRAFT,
                    grouping_origin=GROUPING_MANUAL,
                )
                self.db.add(target)
                self.db.flush()
                targets[area_group] = target
                touched[target.id] = target
            line = by_id[line_id]
            if line.project_sales_order_id != target.id:
                self._move_line(line, target)
        self.db.flush()

        surviving: List[ProjectSalesOrder] = []
        for sibling in touched.values():
            lines = self._lines_of(sibling.id)
            if not lines:
                # An emptied proposal is not a record of anything. Deleting it is the
                # honest outcome of "merge these two into one".
                self.db.delete(sibling)
                continue
            sibling.grouping_origin = GROUPING_MANUAL
            self._renumber(sibling, lines)
            self._recompute(sibling)
            surviving.append(sibling)
        self.db.flush()
        return sorted(surviving, key=lambda row: row.provisional_ref)

    def _move_line(self, line: ProjectSalesOrderLine, target: ProjectSalesOrder) -> None:
        line.project_sales_order_id = target.id
        for finding in (
            self.db.query(SODraftFinding).filter(SODraftFinding.line_id == line.id).all()
        ):
            finding.project_sales_order_id = target.id
        self.db.flush()

    def _build_siblings(self, order: ProjectSalesOrder) -> List[ProjectSalesOrder]:
        return (
            self.db.query(ProjectSalesOrder)
            .filter(
                ProjectSalesOrder.purchase_order_id == order.purchase_order_id,
                ProjectSalesOrder.schedule_version_id == order.schedule_version_id,
                ProjectSalesOrder.status.in_(
                    (SO_STATUS_DRAFT, SO_STATUS_BLOCKED, SO_STATUS_READY)
                ),
            )
            .order_by(ProjectSalesOrder.provisional_ref.asc())
            .all()
        )

    def _renumber(
        self, order: ProjectSalesOrder, lines: Sequence[ProjectSalesOrderLine]
    ) -> None:
        ordered = sorted(
            lines,
            key=lambda line: (line.delivery_date or date.max, line.line_no),
        )
        for index, line in enumerate(ordered, start=1):
            line.line_no = index
        self.db.flush()

    # ---------------------------------------------------------------- publish

    def publish(
        self, order: ProjectSalesOrder, *, actor_user_id: str
    ) -> Dict[str, Any]:
        if order.status == SO_STATUS_PUBLISHED:
            raise AppException(
                status_code=409,
                message=f"{order.provisional_ref} is already published.",
                code="so_already_published",
            )
        # AC-K3 / D28: a giveaway does not reach AutoCount before Accounts has attended to
        # it. The status is the gate, not a label.
        if order.status == SO_STATUS_AWAITING_COSTING:
            raise AppException(
                status_code=409,
                message=(
                    f"{order.provisional_ref} is waiting on Accounts to cost it. Confirm "
                    "the costing before publishing."
                ),
                code="so_awaiting_costing",
            )
        lines = self._lines_of(order.id)
        if not lines:
            raise AppException(
                status_code=422,
                message="A sales order with no lines cannot be published.",
                code="so_has_no_lines",
            )

        # AC-F9a: the credit picture on Thursday, not the one from Monday's draft.
        self._recompute(order)
        self._credit_finding(order)
        self.db.flush()

        blocking = self.blocking_findings(order)
        if blocking:
            raise AppException(
                status_code=409,
                message=(
                    f"{order.provisional_ref} still carries "
                    f"{len(blocking)} unacknowledged hard "
                    f"{'finding' if len(blocking) == 1 else 'findings'}: "
                    + "; ".join(f"{f.code} - {f.detail}" for f in blocking)
                ),
                code="so_publish_blocked",
            )

        order.status = SO_STATUS_PUBLISHED
        order.published_by = actor_user_id
        order.published_at = datetime.utcnow()
        self.db.flush()

        # Publishing raises NO order inquiry (PLAN-scm-front-planning.md section 4,
        # AC-D01). It used to, on the reading that a published order is committed demand,
        # but a published order has not been reconciled to AutoCount and CS has not
        # composed its supply yet: Reserve, Borrow and timely SPO cover may account for all
        # of it, and telling purchasing to buy the whole quantity here is how the same
        # units get bought twice. The inquiry is created inside the atomic Project SO
        # confirmation, carrying the confirmed Buy residual only. Until then the whole SO
        # is Needs CS review and contributes zero purchase requirement.

        return {
            "status": order.status,
            "provisional_ref": order.provisional_ref,
            # Stage 1 (D3): an AutoCount import file carrying our own reference. The
            # returned document number is adopted later, and the ESB call replaces this
            # transport in stage 2 without changing a table or a status.
            "import_file_url": f"/api/v1/project-sales/sales-orders/{order.id}/import-file",
            "can_export": self.can_export(order),
            "total_amount": _money(_dec(order.total_amount)),
            "line_count": len(lines),
        }

    # ------------------------------------------------------------- sponsorship
    #
    # Group K (P12). A sponsorship form is not a purchase order, so it does not go through
    # `build`: there is no quotation to price against, no schedule to reconcile, and the
    # commitment is a giveaway rather than a sale. What it DOES share is everything that
    # protects the warehouse - product resolution and the discontinued check - because a
    # code nobody stocks cannot be shipped whether or not money changes hands (AC-K2).

    def build_from_sponsorship_form(
        self, form_id: str, *, actor_user_id: Optional[str] = None
    ) -> ProjectSalesOrder:
        """An approved sponsorship form becomes a draft at price zero (AC-K1).

        Idempotent per FORM: rebuilding replaces the draft this form produced before, the
        same rule `build` follows per (po_version, schedule_version). A published order is
        never rewritten - it is already in AutoCount.
        """
        form = (
            self.db.query(PurchaseRequestHeader)
            .filter(PurchaseRequestHeader.id == form_id)
            .first()
        )
        if form is None:
            raise AppException(
                status_code=404,
                message="Sponsorship form not found.",
                code="sponsorship_form_not_found",
            )
        if (form.request_type or "") != "sponsorship_form":
            raise AppException(
                status_code=422,
                message=(
                    "That form is a purchase request, not a sponsorship form. Only a "
                    "sponsorship produces a sales order at price zero."
                ),
                code="sponsorship_wrong_form_type",
            )
        if (form.approval_status or "") != "approved":
            raise AppException(
                status_code=409,
                message=(
                    "That sponsorship has not been approved yet. Stock is committed on "
                    "approval, not on submission."
                ),
                code="sponsorship_not_approved",
            )
        if not form.project_id:
            raise AppException(
                status_code=422,
                message=(
                    "Link this sponsorship to a project first: the project is what the "
                    "spend rolls up against, and a sales order has nothing to hang on "
                    "without it."
                ),
                code="sponsorship_no_project",
            )
        project = self._project_or_404(form.project_id)
        form_lines = (
            self.db.query(PurchaseRequestLine)
            .filter(PurchaseRequestLine.purchase_request_id == form.id)
            .order_by(PurchaseRequestLine.sort_order.asc().nullslast())
            .all()
        )
        if not form_lines:
            raise AppException(
                status_code=422,
                message="That sponsorship form has no items on it.",
                code="sponsorship_has_no_lines",
            )

        existing = (
            self.db.query(ProjectSalesOrder)
            .filter(
                ProjectSalesOrder.sponsorship_form_id == form.id,
                ProjectSalesOrder.status.notin_((SO_STATUS_PUBLISHED, SO_STATUS_AMENDED)),
            )
            .first()
        )
        if existing is None:
            order = ProjectSalesOrder(
                company_id=project.company_id,
                project_id=project.id,
                provisional_ref=self._sponsorship_ref(form, project),
                is_sponsorship=True,
                sponsorship_form_id=form.id,
                # Not an area split: a sponsorship has one destination and no schedule.
                grouping_origin="subset",
                status=SO_STATUS_AWAITING_COSTING,
            )
            self.db.add(order)
            self.db.flush()
        else:
            order = existing
            self.db.query(ProjectSalesOrderLine).filter(
                ProjectSalesOrderLine.project_sales_order_id == order.id
            ).delete(synchronize_session=False)
            self.db.query(SODraftFinding).filter(
                SODraftFinding.project_sales_order_id == order.id
            ).delete(synchronize_session=False)
            order.status = SO_STATUS_AWAITING_COSTING
            self.db.flush()

        delivery = form.expected_delivery_date
        for index, source in enumerate(form_lines, start=1):
            product = self._product_by_code(source.item_code)
            line = ProjectSalesOrderLine(
                company_id=order.company_id,
                project_sales_order_id=order.id,
                line_no=index,
                product_id=product.id if product else None,
                description=(source.item_code or "").strip() or None,
                qty=_dec(source.quantity),
                uom=None,
                # AC-K1: price zero, and the form's own indicative price is ignored. The
                # money on a sponsorship form is what it is WORTH, not what we charge.
                unit_price=_ZERO,
                amount=_ZERO,
                delivery_date=delivery,
                explosion_source="direct",
            )
            self.db.add(line)
            self.db.flush()
            self._sponsorship_findings(order, line, source, product)

        self._recompute_total(order)
        self.db.flush()
        return order

    def confirm_costing(
        self, order: ProjectSalesOrder, *, actor_user_id: Optional[str] = None
    ) -> ProjectSalesOrder:
        """Accounts has attended to it; hand it back to the normal gate (D28).

        This releases the costing hold ONLY. It is not a way past the arithmetic gate: the
        order lands on ``ready`` or ``blocked`` exactly as any other draft would, so a hard
        stop still refuses the publish afterwards.
        """
        if order.status != SO_STATUS_AWAITING_COSTING:
            raise AppException(
                status_code=409,
                message=(
                    f"{order.provisional_ref} is not waiting on costing, so there is "
                    "nothing to confirm."
                ),
                code="so_not_awaiting_costing",
            )
        order.status = SO_STATUS_DRAFT
        self.db.flush()
        self._refresh_status(order)
        return order

    def _sponsorship_ref(self, form: PurchaseRequestHeader, project: Project) -> str:
        """Carries the FORM number, because that is the document Accounts is holding."""
        number = (form.request_number or "").strip()
        base = f"SP-{number}" if number else self._next_ref(project.company_id)
        taken = (
            self.db.query(ProjectSalesOrder.id)
            .filter(
                ProjectSalesOrder.company_id == project.company_id,
                ProjectSalesOrder.provisional_ref == base,
            )
            .first()
        )
        return base if taken is None else f"{base}-{str(uuid.uuid4())[:4].upper()}"

    def _sponsorship_findings(
        self,
        order: ProjectSalesOrder,
        line: ProjectSalesOrderLine,
        source: PurchaseRequestLine,
        product: Optional[Product],
    ) -> None:
        """Only the checks that still MEAN something without a quotation (AC-K2)."""
        if product is None:
            self.db.add(
                SODraftFinding(
                    company_id=order.company_id,
                    project_sales_order_id=order.id,
                    line_id=line.id,
                    severity=SEVERITY_HARD,
                    code="unresolved_product",
                    detail=(
                        f"'{(source.item_code or '').strip() or 'blank'}' does not match a "
                        "product. Resolve it before this sponsorship is committed."
                    ),
                )
            )
        elif not bool(getattr(product, "is_active", True)):
            self.db.add(
                SODraftFinding(
                    company_id=order.company_id,
                    project_sales_order_id=order.id,
                    line_id=line.id,
                    severity=SEVERITY_WARN,
                    code="product_discontinued",
                    detail=(
                        f"{product.product_code} is discontinued. Confirm there is stock "
                        "to give away, or substitute it."
                    ),
                )
            )
        self.db.flush()

    def _product_by_code(self, code: Optional[str]) -> Optional[Product]:
        cleaned = (code or "").strip()
        if not cleaned:
            return None
        return (
            self.db.query(Product).filter(Product.product_code.ilike(cleaned)).first()
        )

    def worksheet(self, order: ProjectSalesOrder) -> Dict[str, Any]:
        """The AutoCount SO worksheet as data (Stage 1A, J02).

        The one place the document is assembled. ``import_file`` renders THIS into CSV and
        the worksheet screen renders it as a table, so the file CS downloads and the sheet
        they were looking at cannot describe different orders.

        The columns and header refs are the real document's (SO397450): `Your Ref No.` is
        the customer PO number, `Our Ref No.` is the project, the area prints as a section
        header, and `Reserve Qty` is a real column distinct from `Qty`. Reserve is zero
        until allocation confirms a source (P9), which is honest rather than blank.

        Quantities and money are the FORMATTED strings, not Decimals, because the CSV cell
        is the contract: ``_qty_str`` writes 927 where a Decimal would render 927.0000, and
        an import line reading 1E+2 would be taken for a price list error.
        """
        project = self._project_or_404(order.project_id)
        po = (
            self.db.query(ProjectPurchaseOrder)
            .filter(ProjectPurchaseOrder.id == order.purchase_order_id)
            .first()
            if order.purchase_order_id
            else None
        )
        customer = self._customer_for(order)
        published = order.status in (SO_STATUS_PUBLISHED, SO_STATUS_AMENDED)
        lines = self._lines_of(order.id)
        # One query for every code on the document. Asked per line, a 101-line order (the
        # real SO397450 shape) is 101 round trips to render one screen.
        codes = self._product_codes(line.product_id for line in lines)
        return {
            "id": order.id,
            "provisional_ref": order.provisional_ref,
            "autocount_doc_no": order.autocount_doc_no,
            "status": order.status,
            "area_group": order.area_group,
            "po_number": po.po_number if po else None,
            "customer_name": customer.customer_name if customer else None,
            "header": {
                "debtor": customer.customer_name if customer else None,
                "your_ref_no": po.po_number if po else None,
                "our_ref_no": project.title,
                "our_qt_ref_no": self._quotation_ref(po) or None,
                "terms": f"*Net {po.term_days} days" if po and po.term_days else None,
            },
            "lines": [
                {
                    "line_no": line.line_no,
                    "item_code": codes.get(line.product_id) or None,
                    "description": line.description,
                    "reserve_qty": "0",
                    "qty": _qty_str(_dec(line.qty)),
                    "delivery_date": line.delivery_date,
                    "uom": line.uom,
                    "unit_price": str(_money(_dec(line.unit_price))),
                    "discount": "",
                    "total": str(_money(_dec(line.amount))),
                }
                for line in lines
            ],
            "total_amount": str(_money(_dec(order.total_amount))),
            "findings": self.serialize_findings(order),
            "can_export": self.can_export(order),
            "import_file_url": (
                f"/api/v1/project-sales/sales-orders/{order.id}/import-file"
                if published
                else None
            ),
        }

    def can_export(self, order: ProjectSalesOrder) -> bool:
        """May this order's document leave the building (AC-A01)?

        The one owner of the rule: an unpublished order is not a document yet, and a
        published one still carrying an unacknowledged hard stop must not reach AutoCount.
        Read by the worksheet, by the sales order row the screens gate their buttons on,
        and by the import-file route, which refuses the fetch outright -- a frontend that
        respects the answer is not enforcement.
        """
        published = order.status in (SO_STATUS_PUBLISHED, SO_STATUS_AMENDED)
        return published and not self.blocking_findings(order)

    def assert_can_export(self, order: ProjectSalesOrder) -> None:
        if self.can_export(order):
            return
        if order.status not in (SO_STATUS_PUBLISHED, SO_STATUS_AMENDED):
            message = (
                f"{order.provisional_ref} is not published yet, so there is no import "
                "file to take. Publish it first."
            )
        else:
            message = (
                f"{order.provisional_ref} still carries an unacknowledged hard finding. "
                "Clear it with a reason before the import file leaves for AutoCount."
            )
        raise AppException(status_code=422, message=message, code="so_export_blocked")

    def import_file(self, order: ProjectSalesOrder) -> Tuple[str, str]:
        """The stage 1 AutoCount import file, as CSV. Returns (filename, body).

        Nothing but layout: every value comes from ``worksheet`` above. An absent value is
        CSV's blank cell, which is the only difference between the two renderings.
        """
        sheet = self.worksheet(order)
        header = sheet["header"]
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["Provisional Ref", sheet["provisional_ref"]])
        writer.writerow(["Debtor", header["debtor"] or ""])
        writer.writerow(["Your Ref No.", header["your_ref_no"] or ""])
        writer.writerow(["Our Ref No.", header["our_ref_no"] or ""])
        writer.writerow(["Our QT Ref No.", header["our_qt_ref_no"] or ""])
        writer.writerow(["Terms", header["terms"] or ""])
        writer.writerow([])
        if sheet["area_group"]:
            writer.writerow([f"***{sheet['area_group']}***"])
        writer.writerow(
            [
                "Item",
                "Description",
                "Reserve Qty",
                "Qty",
                "Delivery Date",
                "UOM",
                "U/Price",
                "Disc.",
                "Total",
            ]
        )
        for line in sheet["lines"]:
            writer.writerow(
                [
                    line["item_code"] or "",
                    line["description"] or "",
                    line["reserve_qty"],
                    line["qty"],
                    line["delivery_date"].isoformat() if line["delivery_date"] else "",
                    line["uom"] or "",
                    line["unit_price"],
                    line["discount"] or "",
                    line["total"],
                ]
            )
        writer.writerow([])
        writer.writerow(["Total", "", "", "", "", "", "", "", sheet["total_amount"]])
        return f"{sheet['provisional_ref']}.csv", buffer.getvalue()

    def _quotation_ref(self, po: Optional[ProjectPurchaseOrder]) -> str:
        if po is None or not po.quotation_version_id:
            return ""
        version = (
            self.db.query(ProjectQuotationVersion)
            .filter(ProjectQuotationVersion.id == po.quotation_version_id)
            .first()
        )
        if version is None:
            return ""
        quotation = (
            self.db.query(ProjectQuotation)
            .filter(ProjectQuotation.id == version.quotation_id)
            .first()
        )
        label = quotation.scope_label if quotation else ""
        return f"{label} v{version.version_no}".strip()

    # ------------------------------------------------------------------ shared

    def _assert_editable(self, order: ProjectSalesOrder) -> None:
        """A committed order is amended, never edited (finding G9).

        Editing an unpublished draft commits nothing and raises no order change notice.
        Once it is published, the change has to travel with an OCN or purchasing and
        AutoCount are looking at different documents.
        """
        if order.status in (SO_STATUS_PUBLISHED, SO_STATUS_AMENDED):
            raise AppException(
                status_code=409,
                message=(
                    f"{order.provisional_ref} is published. Raise an amendment with an "
                    "order change notice instead of editing it."
                ),
                code="so_not_editable",
            )

    def get_order(self, pso_id: str) -> ProjectSalesOrder:
        order = (
            self.db.query(ProjectSalesOrder).filter(ProjectSalesOrder.id == pso_id).first()
        )
        if order is None:
            raise AppException(
                status_code=404, message="Sales order not found.", code="so_not_found"
            )
        return order

    _order_or_404 = get_order

    def _lines_of(self, pso_id: str) -> List[ProjectSalesOrderLine]:
        return (
            self.db.query(ProjectSalesOrderLine)
            .filter(ProjectSalesOrderLine.project_sales_order_id == pso_id)
            .order_by(ProjectSalesOrderLine.line_no.asc())
            .all()
        )

    def _recompute(self, order: ProjectSalesOrder) -> None:
        self._recompute_total(order)
        self._refresh_status(order)

    def _recompute_total(self, order: ProjectSalesOrder) -> None:
        lines = self._lines_of(order.id)
        order.total_amount = _money(sum((_dec(line.amount) for line in lines), _ZERO))
        self.db.flush()

    def _refresh_status(self, order: ProjectSalesOrder) -> None:
        """The two tier gate, as a status somebody can read on a list (D9).

        ``blocked`` carries an unacknowledged hard stop and cannot publish. ``ready`` has
        nothing outstanding at all. ``draft`` sits between them: warnings remain, and per
        the contract they do NOT stop a publish -- but "reviewed" and "not yet reviewed"
        should still be distinguishable without opening the row.
        """
        if order.status not in (SO_STATUS_DRAFT, SO_STATUS_BLOCKED, SO_STATUS_READY):
            return
        if self.blocking_findings(order):
            order.status = SO_STATUS_BLOCKED
        elif self._open_findings(order):
            order.status = SO_STATUS_DRAFT
        else:
            order.status = SO_STATUS_READY
        self.db.flush()

    def _open_findings(self, order: ProjectSalesOrder) -> int:
        return (
            self.db.query(func.count(SODraftFinding.id))
            .filter(
                SODraftFinding.project_sales_order_id == order.id,
                SODraftFinding.acknowledged_at.is_(None),
            )
            .scalar()
            or 0
        )

    def _product_codes(self, product_ids: Iterable[Any]) -> Dict[str, str]:
        """Every code in one query, for a caller that needs a whole document's worth.

        ``Any`` because callers pass model attributes, which the type checker reads as
        ``Column[str]`` rather than ``str`` on this codebase's SQLAlchemy version.
        """
        wanted = {product_id for product_id in product_ids if product_id}
        if not wanted:
            return {}
        rows = (
            self.db.query(Product.id, Product.product_code)
            .filter(Product.id.in_(wanted))
            .all()
        )
        return {row[0]: row[1] or "" for row in rows}

    def _product_code(self, product_id: Optional[str]) -> str:
        if not product_id:
            return ""
        row = (
            self.db.query(Product.product_code).filter(Product.id == product_id).first()
        )
        return row[0] if row else ""

    def _customer_for(self, order: ProjectSalesOrder) -> Optional[Customer]:
        po = (
            self.db.query(ProjectPurchaseOrder)
            .filter(ProjectPurchaseOrder.id == order.purchase_order_id)
            .first()
            if order.purchase_order_id
            else None
        )
        if po is None or not po.issuing_party_id:
            return None
        party = (
            self.db.query(ProjectParty).filter(ProjectParty.id == po.issuing_party_id).first()
        )
        if party is None or not party.customer_id:
            return None
        return self.db.query(Customer).filter(Customer.id == party.customer_id).first()

    def _credit_limit(self, customer_id: str) -> Optional[Decimal]:
        """`customers.credit_limit` exists in the database but not on the ORM model.

        Asked for by name, and only after checking the column is there: a scratch schema
        built from the models alone does not have it, and a failed statement would poison
        the surrounding transaction rather than just returning nothing.
        """
        present = self.db.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = 'customers' "
                "AND column_name = 'credit_limit'"
            )
        ).first()
        if not present:
            return None
        value = self.db.execute(
            text("SELECT credit_limit FROM customers WHERE id = :id"), {"id": customer_id}
        ).scalar()
        return _dec(value) if value is not None else None

    # -------------------------------------------------------------- serializing

    def list_for_project(
        self,
        project_id: str,
        *,
        query: Optional[str] = None,
        status: Optional[Sequence[str]] = None,
        page: int = 1,
        limit: int = 50,
        sort: str = "created_at",
        direction: str = "desc",
    ) -> Tuple[List[ProjectSalesOrder], int]:
        rows = self.db.query(ProjectSalesOrder).filter(
            ProjectSalesOrder.project_id == project_id
        )
        if status:
            rows = rows.filter(ProjectSalesOrder.status.in_(list(status)))
        if query:
            needle = f"%{query.strip()}%"
            rows = rows.filter(
                ProjectSalesOrder.provisional_ref.ilike(needle)
                | ProjectSalesOrder.autocount_doc_no.ilike(needle)
                | ProjectSalesOrder.area_group.ilike(needle)
            )
        sortable = {
            "created_at": ProjectSalesOrder.created_at,
            "provisional_ref": ProjectSalesOrder.provisional_ref,
            "status": ProjectSalesOrder.status,
            "area_group": ProjectSalesOrder.area_group,
            "total_amount": ProjectSalesOrder.total_amount,
        }
        column = sortable.get(sort, ProjectSalesOrder.created_at)
        rows = rows.order_by(column.desc() if direction == "desc" else column.asc())
        total = rows.count()
        page = max(page, 1)
        return rows.offset((page - 1) * limit).limit(limit).all(), total

    def list_schedule_versions(self, po_id: str) -> List[Dict[str, Any]]:
        """Every schedule version for this PO, across schedules.

        Across schedules on purpose: R2 arrived from SLG Construction while the PO came
        from Buimaco, which makes it a different ``delivery_schedules`` row for the same
        commitment. A picker scoped to one schedule row would hide the revision.
        """
        rows = (
            self.db.query(DeliveryScheduleVersion, DeliverySchedule)
            .join(
                DeliverySchedule,
                DeliverySchedule.id == DeliveryScheduleVersion.delivery_schedule_id,
            )
            .filter(DeliverySchedule.purchase_order_id == po_id)
            .order_by(DeliveryScheduleVersion.version_no.desc())
            .all()
        )
        po_version_numbers = {
            row.id: row.version_no
            for row in self.db.query(ProjectPOVersion)
            .filter(ProjectPOVersion.purchase_order_id == po_id)
            .all()
        }
        return [
            {
                "id": version.id,
                "delivery_schedule_id": version.delivery_schedule_id,
                "version_no": version.version_no,
                "label": version.revision_label
                or (schedule.label or f"Version {version.version_no}"),
                "revision_label": version.revision_label,
                "extraction_state": version.extraction_state,
                "schedule_date": version.schedule_date,
                "confirmed_at": version.confirmed_at,
                "po_version_no": po_version_numbers.get(version.po_version_id or ""),
                "reconciled_columns": version.reconciled_columns,
                "total_columns": version.total_columns,
            }
            for version, schedule in rows
        ]

    def review_states_for(
        self, orders: Sequence[ProjectSalesOrder]
    ) -> Dict[str, Dict[str, Any]]:
        """The Stage 1B review state for a whole page, so a list is not N evaluations."""
        return ProjectSOReconciliationService(self.db).review_states_for(
            [order.id for order in orders]
        )

    def serialize_row(
        self,
        order: ProjectSalesOrder,
        *,
        review_states: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """``review_states`` is the caller's page-wide answer from ``review_states_for``.

        Passed in rather than derived per row because deriving it here for a 50-row list
        would run the line mapping fifty times over; omitted, one order derives its own.
        """
        lines = self._lines_of(order.id)
        findings = (
            self.db.query(SODraftFinding.severity, func.count(SODraftFinding.id))
            .filter(
                SODraftFinding.project_sales_order_id == order.id,
                SODraftFinding.acknowledged_at.is_(None),
            )
            .group_by(SODraftFinding.severity)
            .all()
        )
        counts = {severity: int(count) for severity, count in findings}
        project = self.db.query(Project).filter(Project.id == order.project_id).first()
        po = (
            self.db.query(ProjectPurchaseOrder)
            .filter(ProjectPurchaseOrder.id == order.purchase_order_id)
            .first()
            if order.purchase_order_id
            else None
        )
        customer = self._customer_for(order)
        party = (
            self.db.query(ProjectParty)
            .filter(ProjectParty.id == po.issuing_party_id)
            .first()
            if po and po.issuing_party_id
            else None
        )
        states = (
            review_states
            if review_states is not None
            else self.review_states_for([order])
        )
        # Absent from the map means the order has no review state at all: a draft or a
        # blocked order is reconciled against nothing, so it reads as no state rather
        # than an "awaiting reconciliation" it has not earned (AC-A03).
        state = states.get(str(order.id), {"review_state": None, "exception_count": 0})
        return {
            "id": order.id,
            "provisional_ref": order.provisional_ref,
            "autocount_doc_no": order.autocount_doc_no,
            "area_group": order.area_group,
            "status": order.status,
            "grouping_origin": order.grouping_origin,
            # The FK rather than a po_number string match, and the file a published order
            # can still be fetched from days later. A draft has no import file on purpose:
            # nothing uncommitted should be importable into AutoCount.
            "purchase_order_id": order.purchase_order_id,
            "import_file_url": (
                f"/api/v1/project-sales/sales-orders/{order.id}/import-file"
                if order.status in (SO_STATUS_PUBLISHED, SO_STATUS_AMENDED)
                else None
            ),
            # Whether that url may actually be fetched, which is NOT the same question:
            # a published order carrying an unacknowledged hard finding keeps its file's
            # address and loses permission to take it. The screens gate their download on
            # this; the route enforces it (`assert_can_export`).
            "can_export": self.can_export(order),
            "line_count": len(lines),
            "total_amount": _money(_dec(order.total_amount)),
            "hard_findings": counts.get(SEVERITY_HARD, 0),
            "warn_findings": counts.get(SEVERITY_WARN, 0) + counts.get(SEVERITY_INFO, 0),
            "is_pre_order": bool(order.is_pre_order),
            "is_sponsorship": bool(order.is_sponsorship),
            "customer_name": (
                customer.customer_name if customer else (party.name if party else None)
            ),
            "po_number": po.po_number if po else None,
            "project_code": project.project_code if project else None,
            "project_title": project.title if project else None,
            "created_at": order.created_at,
            # The frontend keys its divergence lookup on this, so an ingest that adopts a
            # document number or raises a difference makes the amend button re-evaluate.
            # Both this and the schema field are needed: a manual dict builder drops
            # anything not listed here, whatever the schema inherits.
            "updated_at": order.updated_at,
            # Stage 1B. Derived, never a column: the whole SO's one pre-confirmation state
            # (AC-A03) and how many exceptions stand between it and Needs CS review, so the
            # project's SO list and the SO detail header read what Fulfilment Planning does.
            # Null until the order is published or amended - see above.
            "review_state": state["review_state"],
            "exception_count": state["exception_count"],
        }

    def serialize_detail(
        self,
        order: ProjectSalesOrder,
        *,
        review_states: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        body = self.serialize_row(order, review_states=review_states)
        po = (
            self.db.query(ProjectPurchaseOrder)
            .filter(ProjectPurchaseOrder.id == order.purchase_order_id)
            .first()
            if order.purchase_order_id
            else None
        )
        schedule_version = (
            self.db.query(DeliveryScheduleVersion)
            .filter(DeliveryScheduleVersion.id == order.schedule_version_id)
            .first()
            if order.schedule_version_id
            else None
        )
        lines = self._lines_of(order.id)
        phases = {
            phase.id: phase
            for phase in self.db.query(ProjectDeliveryPhase)
            .filter(ProjectDeliveryPhase.project_id == order.project_id)
            .all()
        }
        products = {
            row.id: row
            for row in self.db.query(Product)
            .filter(Product.id.in_([line.product_id for line in lines if line.product_id]))
            .all()
        } if any(line.product_id for line in lines) else {}
        po_line_numbers = {
            row.id: row.line_no
            for row in self.db.query(ProjectPOLine)
            .filter(
                ProjectPOLine.id.in_(
                    [line.source_po_line_id for line in lines if line.source_po_line_id]
                )
            )
            .all()
        } if any(line.source_po_line_id for line in lines) else {}
        parents = self._parent_line_ids(lines)

        body.update(
            {
                "project_id": order.project_id,
                "purchase_order_id": order.purchase_order_id,
                "schedule_version_id": order.schedule_version_id,
                "schedule_revision_label": (
                    schedule_version.revision_label if schedule_version else None
                ),
                "quotation_ref": self._quotation_ref(po),
                "term_days": po.term_days if po else None,
                "published_at": order.published_at,
                "lines": [
                    {
                        "id": line.id,
                        "line_no": line.line_no,
                        "product_id": line.product_id,
                        "product_code": (
                            products[line.product_id].product_code
                            if line.product_id in products
                            else None
                        ),
                        "description": line.description,
                        "qty": _dec(line.qty),
                        "uom": line.uom,
                        "unit_price": _dec(line.unit_price),
                        "amount": _money(_dec(line.amount)),
                        "delivery_date": line.delivery_date,
                        "phase_id": line.phase_id,
                        "phase_label": (
                            (phases[line.phase_id].label or phases[line.phase_id].area_group)
                            if line.phase_id in phases
                            else None
                        ),
                        "explosion_source": line.explosion_source,
                        "source_po_line_no": po_line_numbers.get(line.source_po_line_id or ""),
                        "quotation_line_id": line.quotation_line_id,
                        "stock_location": line.stock_location,
                        "parent_line_id": parents.get(line.id),
                        "is_companion": parents.get(line.id) not in (None, line.id),
                    }
                    for line in lines
                ],
                "findings": self.serialize_findings(order),
            }
        )
        return body

    def _parent_line_ids(
        self, lines: Sequence[ProjectSalesOrderLine]
    ) -> Dict[str, Optional[str]]:
        """Which line is the SET's parent, per exploded group.

        Stated rather than inferred by the reader: a companion detached from its set is an
        unfulfillable printed order. There is no column for it on ``project_sales_order_lines``,
        so it is derived here with the SAME rule the explosion used -- the component that
        IS the ordered item, else the priced one, else the first line of the group -- which
        means the two can never disagree.

        A group is ``(source PO line, phase)``: the same set delivered in two phases is two
        groups, because the parent of each is its own line.
        """
        groups: Dict[Tuple[Optional[str], Optional[str]], List[ProjectSalesOrderLine]] = {}
        for line in lines:
            groups.setdefault((line.source_po_line_id, line.phase_id), []).append(line)

        ordered_products: Dict[str, Optional[str]] = {}
        po_line_ids = [key[0] for key in groups if key[0]]
        if po_line_ids:
            ordered_products = {
                row.id: row.resolved_product_id
                for row in self.db.query(ProjectPOLine)
                .filter(ProjectPOLine.id.in_(po_line_ids))
                .all()
            }

        out: Dict[str, Optional[str]] = {}
        for (po_line_id, _phase_id), members in groups.items():
            if len(members) == 1:
                out[members[0].id] = None  # not a set: nothing to hang under
                continue
            members = sorted(members, key=lambda row: row.line_no)
            wanted = ordered_products.get(po_line_id or "")
            parent = next(
                (row for row in members if wanted and row.product_id == wanted),
                None,
            )
            if parent is None:
                parent = next((row for row in members if _dec(row.unit_price) > _ZERO), None)
            if parent is None:
                parent = members[0]
            for row in members:
                out[row.id] = parent.id
        return out

    def serialize_findings(self, order: ProjectSalesOrder) -> List[Dict[str, Any]]:
        rows = (
            self.db.query(SODraftFinding)
            .filter(SODraftFinding.project_sales_order_id == order.id)
            .all()
        )
        # Hard stops first: the screen is a short list of exceptions, and the ones that
        # block a publish are the ones somebody has to deal with today.
        rank = {SEVERITY_HARD: 0, SEVERITY_WARN: 1, SEVERITY_INFO: 2}
        rows.sort(
            key=lambda row: (
                rank.get(row.severity, 3),
                row.code,
                row.created_at or datetime.min,
            )
        )
        line_numbers = {
            line.id: line.line_no for line in self._lines_of(order.id)
        }
        names = {
            user.id: user.name
            for user in self.db.query(User)
            .filter(User.id.in_([row.acknowledged_by for row in rows if row.acknowledged_by]))
            .all()
        } if any(row.acknowledged_by for row in rows) else {}
        return [
            {
                "id": row.id,
                "severity": row.severity,
                "code": row.code,
                "detail": row.detail,
                "detail_json": row.detail_json,
                "line_id": row.line_id,
                "line_no": line_numbers.get(row.line_id or ""),
                "acknowledged_by_name": names.get(row.acknowledged_by or ""),
                "acknowledged_reason": row.acknowledged_reason,
                "acknowledged_at": row.acknowledged_at,
            }
            for row in rows
        ]

