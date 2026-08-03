"""Revision delta, amendment and order change notice (P11, AC-G1 to AC-G7).

A revision is a NEW VERSION, and the amendment is the computed DIFFERENCE between two
versions (D14). Nothing is ever mutated in place to represent a change: the delta is what
purchasing consumes, and it only means something if both sides of it still exist.

Four rules carry the file.

**Phases match on ``(area_group, sequence)``, never on the label.** The COMMON AREA rows on
the client's own schedule carry no label at all, and matching by label collapsed three
phases into one (finding G6, confirmed by measurement).

**``unmatched`` is never silently empty.** A phase or a product that cannot be matched
between two versions is REPORTED. Dropping it is how a delta lies: the reviewer sees a
tidy change table and the quantity quietly vanishes.

**A revision that moves dates must leave quantities alone**, and the preview has to make
that plain, because "did anything other than the dates change?" is the only question the
reviewer actually has. ``verb_summary`` therefore always carries every verb, zeros
included, and ``quantities_changed`` answers it in one word.

**Verbs are the client's own vocabulary**, spelled as they spell them in the order inquiry
they send today: ``ORDER``, ``RESERVE & ORDER``, ``ADVANCE``, ``DELAY``, ``CHANGE SO NO``,
``CANCEL BALANCE``. A price move has no verb because purchasing does not act on a price, so
it is reported in ``unmatched`` rather than dressed up as an instruction.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.project_so import (
    AMENDMENT_PROPOSED,
    AMENDMENT_PUBLISHED,
    SO_STATUS_AMENDED,
    SO_STATUS_PUBLISHED,
    DeliverySchedule,
    DeliveryScheduleCell,
    DeliveryScheduleVersion,
    OrderChangeNotice,
    ProjectDeliveryPhase,
    ProjectPOLine,
    ProjectPOVersion,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    SOAmendment,
)
from app.models.projects import ProjectPurchaseOrder
from app.models.user import User
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

_CENTS = Decimal("0.01")
_ZERO = Decimal("0")

VERB_ORDER = "ORDER"
VERB_RESERVE_AND_ORDER = "RESERVE & ORDER"
VERB_ADVANCE = "ADVANCE"
VERB_DELAY = "DELAY"
VERB_CHANGE_SO_NO = "CHANGE SO NO"
VERB_CANCEL_BALANCE = "CANCEL BALANCE"

# Always reported, zeros included: "nothing but the dates moved" has to be readable at a
# glance rather than inferred from which keys are absent.
ALL_VERBS = (
    VERB_ORDER,
    VERB_RESERVE_AND_ORDER,
    VERB_ADVANCE,
    VERB_DELAY,
    VERB_CHANGE_SO_NO,
    VERB_CANCEL_BALANCE,
)

# New demand landing inside this window is RESERVE & ORDER rather than plain ORDER:
# purchasing has to hold what is on the shelf as well as order the balance, because the
# order will not land before the delivery date. Arithmetic on dates, no judgement.
RESERVE_WINDOW_DAYS = 60

OCN_NUMBERING_DOC_TYPE = "order_change_notice"
_OCN_PREFIX = "OCN-"
_OCN_DIGITS = 6


def _dec(value: Any, default: Decimal = _ZERO) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001 - a malformed extracted number is data, not a crash
        return default


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENTS)


def _qty_str(value: Decimal) -> str:
    """A quantity as purchasing writes it: `CANCEL BALANCE 30 NOS`, not `30.0000 NOS`.

    ``format(..., "f")`` rather than ``str(normalize())`` because ``Decimal("100.0000")``
    normalises to ``1E+2``, which in a change table reads as anything but a hundred.
    """
    return format(value.normalize(), "f")


def _as_date(value: Any) -> Optional[date]:
    """Dates arrive as `date`, as an ISO string, or not at all.

    Deliberately strict about the format: a schedule's ambiguous `8/3/2026` is resolved
    upstream at intake (AC-E7), and guessing again here would give two answers for one
    document.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _iso(value: Optional[date]) -> Optional[str]:
    return value.isoformat() if value else None


@dataclass
class _PhaseFact:
    area_group: str
    sequence: int
    label: Optional[str]
    delivery_date: Optional[date]
    phase_id: Optional[str] = None
    qty: Dict[str, Decimal] = field(default_factory=dict)

    @property
    def key(self) -> Tuple[str, int]:
        return (self.area_group, self.sequence)


class ProjectSODeltaService:
    """Computes, persists and publishes the difference between two document versions."""

    def __init__(self, db: Session):
        self.db = db

    # ---------------------------------------------------------------- preview

    def preview(
        self,
        pso_id: str,
        *,
        po_version_id: Optional[str] = None,
        schedule_version_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """The difference between the version the order was built from and the named one.

        Writes nothing. Called again by ``create`` so the stored delta and the reviewed
        one are the same computation rather than two that might drift.
        """
        order = self._order_or_404(pso_id)
        if bool(po_version_id) == bool(schedule_version_id):
            raise AppException(
                status_code=422,
                message=(
                    "Name exactly one revised document: a PO version or a delivery "
                    "schedule version."
                ),
                code="amendment_version_ambiguous",
            )
        if schedule_version_id:
            return self._schedule_delta(order, schedule_version_id)
        return self._po_delta(order, str(po_version_id))

    # -------------------------------------------------------- schedule delta

    def _schedule_delta(self, order: ProjectSalesOrder, to_version_id: str) -> Dict[str, Any]:
        if not order.schedule_version_id:
            raise AppException(
                status_code=422,
                message=(
                    f"{order.provisional_ref} was not built from a delivery schedule, so "
                    "there is no schedule version to compare against."
                ),
                code="amendment_no_schedule_baseline",
            )
        from_version = self._schedule_version_or_404(order.schedule_version_id)
        to_version = self._schedule_version_or_404(to_version_id)
        self._assert_same_po(order, from_version, to_version)

        before = self._schedule_snapshot(from_version)
        after = self._schedule_snapshot(to_version)
        lines = self._lines_by_phase_product(order)

        rows: List[Dict[str, Any]] = []
        phase_summary: List[Dict[str, Any]] = []
        unmatched: List[Dict[str, Any]] = []

        matched_keys = set(before) & set(after)
        only_before = set(before) - matched_keys
        only_after = set(after) - matched_keys

        for key in sorted(matched_keys):
            self._compare_phase(
                order=order,
                before=before[key],
                after=after[key],
                lines=lines,
                rows=rows,
                phase_summary=phase_summary,
            )

        self._report_unpaired_phases(
            order=order,
            before=before,
            after=after,
            only_before=only_before,
            only_after=only_after,
            lines=lines,
            rows=rows,
            unmatched=unmatched,
        )

        return self._envelope(
            from_ref={
                "kind": "schedule_version",
                "id": from_version.id,
                "version_no": from_version.version_no,
                "label": from_version.revision_label or f"version {from_version.version_no}",
            },
            to_ref={
                "kind": "schedule_version",
                "id": to_version.id,
                "version_no": to_version.version_no,
                "label": to_version.revision_label or f"version {to_version.version_no}",
            },
            rows=rows,
            phase_summary=phase_summary,
            unmatched=unmatched,
        )

    def _compare_phase(
        self,
        *,
        order: ProjectSalesOrder,
        before: _PhaseFact,
        after: _PhaseFact,
        lines: Dict[Tuple[str, int, str], ProjectSalesOrderLine],
        rows: List[Dict[str, Any]],
        phase_summary: List[Dict[str, Any]],
    ) -> None:
        phase_lines = [
            line
            for (area, sequence, _product), line in lines.items()
            if (area, sequence) == before.key
        ]
        relevant = bool(phase_lines) or before.area_group == order.area_group
        moved = before.delivery_date != after.delivery_date
        verb = None
        if moved and before.delivery_date and after.delivery_date:
            verb = VERB_DELAY if after.delivery_date > before.delivery_date else VERB_ADVANCE
        elif moved:
            # A date appearing or disappearing is still a move, and DELAY is the reading
            # purchasing acts on: a phase with no date cannot be ordered for.
            verb = VERB_DELAY if after.delivery_date else VERB_ADVANCE

        # A date move is a PHASE fact: every line under it moves by the same amount, and
        # each gets its own row so the amendment can be applied line by line.
        if verb:
            for line in sorted(phase_lines, key=lambda row: row.line_no):
                rows.append(
                    self._row(
                        order=order,
                        line=line,
                        product_id=line.product_id,
                        verb=verb,
                        field_name="delivery_date",
                        from_value=_iso(before.delivery_date),
                        to_value=_iso(after.delivery_date),
                        qty=_dec(line.qty),
                        before=before,
                        after=after,
                    )
                )

        qty_changed = False
        for product_id in sorted(set(before.qty) | set(after.qty)):
            from_qty = before.qty.get(product_id, _ZERO)
            to_qty = after.qty.get(product_id, _ZERO)
            if from_qty == to_qty:
                continue
            qty_changed = True
            line = lines.get((before.area_group, before.sequence, product_id))
            rows.append(
                self._row(
                    order=order,
                    line=line,
                    product_id=product_id,
                    verb=(
                        VERB_CANCEL_BALANCE
                        if to_qty < from_qty
                        else self._order_verb(after.delivery_date)
                    ),
                    field_name="qty",
                    from_value=_qty_str(from_qty),
                    to_value=_qty_str(to_qty),
                    qty=abs(to_qty - from_qty),
                    before=before,
                    after=after,
                )
            )

        if relevant and (moved or qty_changed):
            phase_summary.append(
                {
                    "area_group": before.area_group,
                    "sequence": before.sequence,
                    "phase_label_from": before.label,
                    "phase_label_to": after.label,
                    "verb": verb,
                    "delivery_date_from": _iso(before.delivery_date),
                    "delivery_date_to": _iso(after.delivery_date),
                    "line_count": len(phase_lines),
                    "qty_changed": qty_changed,
                }
            )

    def _report_unpaired_phases(
        self,
        *,
        order: ProjectSalesOrder,
        before: Dict[Tuple[str, int], _PhaseFact],
        after: Dict[Tuple[str, int], _PhaseFact],
        only_before: set,
        only_after: set,
        lines: Dict[Tuple[str, int, str], ProjectSalesOrderLine],
        rows: List[Dict[str, Any]],
        unmatched: List[Dict[str, Any]],
    ) -> None:
        """Unpaired phases: one re-match attempt, then reported rather than dropped.

        The single re-match is by SEQUENCE across area groups, corroborated by the
        quantity vector (AC-G3). That is the re-point case the client writes as
        ``CHANGE SO NO``: the same delivery, moved to another area's sales order. Anything
        that cannot be corroborated goes to ``unmatched`` for confirmation, never treated
        as new.
        """
        paired: set = set()
        for from_key in sorted(only_before):
            source = before[from_key]
            for to_key in sorted(only_after):
                if to_key in paired:
                    continue
                target = after[to_key]
                if target.sequence != source.sequence:
                    continue
                if not source.qty or source.qty != target.qty:
                    continue
                paired.add(to_key)
                for product_id in sorted(source.qty):
                    line = lines.get((source.area_group, source.sequence, product_id))
                    rows.append(
                        self._row(
                            order=order,
                            line=line,
                            product_id=product_id,
                            verb=VERB_CHANGE_SO_NO,
                            field_name="area_group",
                            from_value=source.area_group,
                            to_value=target.area_group,
                            qty=source.qty[product_id],
                            before=source,
                            after=target,
                        )
                    )
                break
            else:
                at_risk = sum(source.qty.values(), _ZERO)
                unmatched.append(
                    {
                        "reason": "phase not found in the new version",
                        "detail": (
                            f"{source.area_group} sequence {source.sequence} "
                            f"({source.label or 'no label'}) carried {at_risk} in the "
                            "version this sales order was built from and is absent from "
                            "the named one. Confirm whether it was cancelled or renamed."
                        ),
                        "area_group": source.area_group,
                        "sequence": source.sequence,
                    }
                )

        for to_key in sorted(only_after - paired):
            target = after[to_key]
            arriving = sum(target.qty.values(), _ZERO)
            unmatched.append(
                {
                    "reason": "phase is new in the named version",
                    "detail": (
                        f"{target.area_group} sequence {target.sequence} "
                        f"({target.label or 'no label'}) brings {arriving} that this sales "
                        "order has no line for. Confirm it before it becomes an "
                        "instruction to purchasing."
                    ),
                    "area_group": target.area_group,
                    "sequence": target.sequence,
                }
            )

    # ------------------------------------------------------------- PO delta

    def _po_delta(self, order: ProjectSalesOrder, to_version_id: str) -> Dict[str, Any]:
        """A revised PO changes quantities and prices, never dates: it carries none.

        A price move is reported in ``unmatched`` rather than given a verb. Purchasing does
        not act on a price, and inventing an instruction for one would put a row on Joey's
        task that he cannot do anything with.
        """
        to_version = self._po_version_or_404(to_version_id)
        from_version = self._baseline_po_version(order)
        if from_version is None:
            raise AppException(
                status_code=422,
                message=(
                    f"{order.provisional_ref} has no PO version behind it, so there is "
                    "nothing to compare the revision against."
                ),
                code="amendment_no_po_baseline",
            )
        if to_version.purchase_order_id != from_version.purchase_order_id:
            raise AppException(
                status_code=422,
                message="Those two PO versions belong to different purchase orders.",
                code="amendment_po_mismatch",
            )

        before = self._po_snapshot(from_version)
        after = self._po_snapshot(to_version)
        lines_by_product: Dict[str, List[ProjectSalesOrderLine]] = {}
        for line in self._lines_of(order.id):
            if line.product_id:
                lines_by_product.setdefault(line.product_id, []).append(line)

        rows: List[Dict[str, Any]] = []
        unmatched: List[Dict[str, Any]] = []
        for product_id in sorted(set(before) | set(after)):
            from_qty, from_price = before.get(product_id, (_ZERO, _ZERO))
            to_qty, to_price = after.get(product_id, (_ZERO, _ZERO))
            own_lines = lines_by_product.get(product_id, [])
            line = own_lines[0] if own_lines else None
            if product_id not in lines_by_product and to_qty > from_qty:
                unmatched.append(
                    {
                        "reason": "product is new in the named version",
                        "detail": (
                            f"{self._product_code(product_id)} appears on the revised PO "
                            f"at {to_qty} but this sales order has no line for it. Add it "
                            "to a draft rather than amending a line that does not exist."
                        ),
                    }
                )
                continue
            if to_qty != from_qty:
                if to_qty < from_qty:
                    rows.append(
                        self._row(
                            order=order,
                            line=line,
                            product_id=product_id,
                            verb=VERB_CANCEL_BALANCE,
                            field_name="qty",
                            from_value=_qty_str(from_qty),
                            to_value=_qty_str(to_qty),
                            qty=from_qty - to_qty,
                        )
                    )
                else:
                    rows.append(
                        self._row(
                            order=order,
                            line=line,
                            product_id=product_id,
                            verb=self._order_verb(line.delivery_date if line else None),
                            field_name="qty",
                            from_value=_qty_str(from_qty),
                            to_value=_qty_str(to_qty),
                            qty=to_qty - from_qty,
                        )
                    )
            if _money(from_price) != _money(to_price) and product_id in lines_by_product:
                unmatched.append(
                    {
                        "reason": "unit price changed and no purchasing verb applies",
                        "detail": (
                            f"{self._product_code(product_id)} moves from "
                            f"{_money(from_price)} to {_money(to_price)} on the revised "
                            "PO. Re-price the line and record it on the order change "
                            "notice; purchasing has nothing to do with a price."
                        ),
                    }
                )

        return self._envelope(
            from_ref={
                "kind": "po_version",
                "id": from_version.id,
                "version_no": from_version.version_no,
                "label": f"version {from_version.version_no}",
            },
            to_ref={
                "kind": "po_version",
                "id": to_version.id,
                "version_no": to_version.version_no,
                "label": f"version {to_version.version_no}",
            },
            rows=rows,
            phase_summary=[],
            unmatched=unmatched,
        )

    # ---------------------------------------------------------------- create

    def create(
        self,
        pso_id: str,
        *,
        po_version_id: Optional[str] = None,
        schedule_version_id: Optional[str] = None,
        reason: str,
        actor_user_id: str,
    ) -> Dict[str, Any]:
        """Persist the amendment and auto-draft its OCN from the SAME delta (D15).

        Both land in ``proposed``. Auto-drafting is what keeps the client's only trusted
        hard gate from becoming drag: nobody retypes the change table, they approve it.
        """
        order = self._order_or_404(pso_id)
        if order.status not in (SO_STATUS_PUBLISHED, SO_STATUS_AMENDED):
            raise AppException(
                status_code=409,
                message=(
                    f"{order.provisional_ref} is not published yet. Edit the draft "
                    "instead: nothing is committed, so there is nothing to amend."
                ),
                code="amendment_not_published",
            )
        # AC-N5: an unreconciled difference against AutoCount stops this here. Amending a
        # record we already know is wrong is how the two systems drift apart for good.
        from app.services.project_so_divergence_service import ProjectSODivergenceService

        ProjectSODivergenceService(self.db).assert_amendable(order.id)
        delta = self.preview(
            pso_id, po_version_id=po_version_id, schedule_version_id=schedule_version_id
        )
        if not delta["rows"] and not delta["unmatched"]:
            raise AppException(
                status_code=422,
                message=(
                    "That version is identical to the one this sales order was built "
                    "from. There is nothing to amend."
                ),
                code="amendment_empty",
            )

        kind = "schedule" if schedule_version_id else "po"
        amendment = SOAmendment(
            company_id=order.company_id,
            project_sales_order_id=order.id,
            from_version_kind=kind,
            from_version_id=delta["from"]["id"],
            to_version_id=delta["to"]["id"],
            verb_summary=delta["verb_summary"],
            delta_json=delta,
            status=AMENDMENT_PROPOSED,
        )
        self.db.add(amendment)
        self.db.flush()

        ocn = OrderChangeNotice(
            company_id=order.company_id,
            ocn_number=self._next_ocn_number(order.company_id),
            project_id=order.project_id,
            purchase_order_id=order.purchase_order_id,
            project_sales_order_id=order.id,
            reason=reason,
            source_document_kind="revised_schedule" if kind == "schedule" else "revised_po",
            source_document_id=delta["to"]["id"],
            change_table_json={
                "rows": delta["rows"],
                "phase_summary": delta["phase_summary"],
                "unmatched": delta["unmatched"],
                "verb_summary": delta["verb_summary"],
            },
            created_by=actor_user_id,
        )
        self.db.add(ocn)
        self.db.flush()
        amendment.ocn_id = ocn.id
        self.db.flush()
        return {
            "amendment_id": amendment.id,
            "ocn_id": ocn.id,
            "ocn_number": ocn.ocn_number,
            "verb_summary": delta["verb_summary"],
        }

    # --------------------------------------------------------------- publish

    def publish_amendment(self, amendment_id: str, *, actor_user_id: str) -> Dict[str, Any]:
        """Apply the delta, stamp the OCN, move the order to ``amended``.

        Refuses without an approver on the OCN (AC-G4). Refuses too when a row cannot be
        applied without inventing something -- a new product with no price, a re-point with
        no destination -- because an amendment that does not do what its own change table
        says is worse than one that stopped and asked.
        """
        amendment = (
            self.db.query(SOAmendment).filter(SOAmendment.id == amendment_id).first()
        )
        if amendment is None:
            raise AppException(
                status_code=404, message="Amendment not found.", code="amendment_not_found"
            )
        if amendment.status == AMENDMENT_PUBLISHED:
            raise AppException(
                status_code=409,
                message="That amendment is already published.",
                code="amendment_already_published",
            )
        # AC-N5 again, and not only on create: a divergence can land BETWEEN proposing an
        # amendment and publishing it, which is exactly when publishing it does the damage.
        from app.services.project_so_divergence_service import ProjectSODivergenceService

        ProjectSODivergenceService(self.db).assert_amendable(amendment.project_sales_order_id)
        ocn = (
            self.db.query(OrderChangeNotice)
            .filter(OrderChangeNotice.id == amendment.ocn_id)
            .first()
            if amendment.ocn_id
            else None
        )
        if ocn is None or not ocn.approver_id:
            raise AppException(
                status_code=409,
                message=(
                    "This amendment's order change notice has no approver yet. Every "
                    "amendment to a published sales order needs one."
                ),
                code="amendment_ocn_unapproved",
            )

        order = self._order_or_404(amendment.project_sales_order_id)
        delta = amendment.delta_json or {}
        applied = self._apply_rows(order, delta.get("rows") or [])

        amendment.status = AMENDMENT_PUBLISHED
        amendment.published_at = datetime.utcnow()
        if ocn.approved_at is None:
            ocn.approved_at = datetime.utcnow()
        order.status = SO_STATUS_AMENDED
        self._recompute(order)
        self.db.flush()

        # P10 (AC-I1): the amendment is derived into purchasing's own verbs AFTER the
        # delta has been applied, so each row carries the line as it now stands and says
        # what it moved from. Idempotent per amendment.
        from app.services.project_order_inquiry_service import ProjectOrderInquiryService

        inquiry = ProjectOrderInquiryService(self.db).derive_for_amendment(
            amendment, actor_user_id=actor_user_id
        )

        return {
            "status": amendment.status,
            "sales_order_status": order.status,
            "provisional_ref": order.provisional_ref,
            "applied_rows": applied,
            "ocn_number": ocn.ocn_number,
            "order_inquiry_id": inquiry.id,
        }

    def _apply_rows(
        self, order: ProjectSalesOrder, rows: Sequence[Dict[str, Any]]
    ) -> int:
        applied = 0
        touched: Dict[str, ProjectSalesOrder] = {order.id: order}
        for row in rows:
            verb = row.get("verb")
            line = self._line_or_none(row.get("so_line_id"))
            if verb in (VERB_DELAY, VERB_ADVANCE):
                if line is None:
                    continue
                line.delivery_date = _as_date(row.get("to_value"))
                applied += 1
            elif verb == VERB_CANCEL_BALANCE:
                if line is None:
                    continue
                # The line stays at its reduced quantity rather than being deleted: the
                # amendment and the OCN both point at it, and a deleted line makes the
                # history unreadable. A zero is a cancelled line, said plainly.
                line.qty = _dec(row.get("to_value"))
                line.amount = _money(_dec(line.qty) * _dec(line.unit_price))
                applied += 1
            elif verb in (VERB_ORDER, VERB_RESERVE_AND_ORDER):
                if line is None:
                    raise AppException(
                        status_code=409,
                        message=(
                            f"The change table adds {row.get('product_code') or 'a product'} "
                            "that this sales order has no line for. Add the line to a "
                            "draft and rebuild rather than publishing an amendment that "
                            "cannot be applied."
                        ),
                        code="amendment_row_unapplicable",
                    )
                line.qty = _dec(row.get("to_value"))
                line.amount = _money(_dec(line.qty) * _dec(line.unit_price))
                applied += 1
            elif verb == VERB_CHANGE_SO_NO:
                destination = self._destination_for(order, row.get("to_value"))
                if line is None or destination is None:
                    raise AppException(
                        status_code=409,
                        message=(
                            "The change table moves quantity to "
                            f"'{row.get('to_value')}', which has no sales order on this "
                            "purchase order yet. Create it first: a re-point with no "
                            "destination is not something we can apply."
                        ),
                        code="amendment_repoint_no_destination",
                    )
                line.project_sales_order_id = destination.id
                touched[destination.id] = destination
                applied += 1
        self.db.flush()
        for target in touched.values():
            self._renumber(target)
            self._recompute(target)
        return applied

    def _destination_for(
        self, order: ProjectSalesOrder, area_group: Optional[str]
    ) -> Optional[ProjectSalesOrder]:
        if not area_group:
            return None
        return (
            self.db.query(ProjectSalesOrder)
            .filter(
                ProjectSalesOrder.purchase_order_id == order.purchase_order_id,
                ProjectSalesOrder.area_group == area_group,
                ProjectSalesOrder.id != order.id,
            )
            .order_by(ProjectSalesOrder.created_at.asc())
            .first()
        )

    # ---------------------------------------------------------------- reading

    def get_amendment(self, amendment_id: str) -> Dict[str, Any]:
        amendment = (
            self.db.query(SOAmendment).filter(SOAmendment.id == amendment_id).first()
        )
        if amendment is None:
            raise AppException(
                status_code=404, message="Amendment not found.", code="amendment_not_found"
            )
        order = self._order_or_404(amendment.project_sales_order_id)
        ocn = (
            self.db.query(OrderChangeNotice)
            .filter(OrderChangeNotice.id == amendment.ocn_id)
            .first()
            if amendment.ocn_id
            else None
        )
        approver = (
            self.db.query(User).filter(User.id == ocn.approver_id).first()
            if ocn and ocn.approver_id
            else None
        )
        delta = amendment.delta_json or {}
        return {
            "id": amendment.id,
            "project_sales_order_id": order.id,
            "provisional_ref": order.provisional_ref,
            "autocount_doc_no": order.autocount_doc_no,
            "status": amendment.status,
            "from_version_kind": amendment.from_version_kind,
            "from_version_label": (delta.get("from") or {}).get("label"),
            "to_version_label": (delta.get("to") or {}).get("label"),
            "verb_summary": amendment.verb_summary or {},
            "delta": delta,
            "ocn_id": ocn.id if ocn else None,
            "ocn_number": ocn.ocn_number if ocn else None,
            "ocn_reason": ocn.reason if ocn else None,
            "ocn_approver_name": approver.name if approver else None,
            "ocn_approved_at": ocn.approved_at if ocn else None,
            "published_at": amendment.published_at,
            "created_at": amendment.created_at,
        }

    # ----------------------------------------------------------------- shared

    def _envelope(
        self,
        *,
        from_ref: Dict[str, Any],
        to_ref: Dict[str, Any],
        rows: List[Dict[str, Any]],
        phase_summary: List[Dict[str, Any]],
        unmatched: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        summary = {verb: 0 for verb in ALL_VERBS}
        for row in rows:
            summary[row["verb"]] = summary.get(row["verb"], 0) + 1
        return {
            "from": from_ref,
            "to": to_ref,
            "verb_summary": summary,
            # The reviewer's only real question, answered without reading the table.
            "quantities_changed": any(row["field"] == "qty" for row in rows),
            "rows": rows,
            "phase_summary": phase_summary,
            "unmatched": unmatched,
        }

    def _row(
        self,
        *,
        order: ProjectSalesOrder,
        line: Optional[ProjectSalesOrderLine],
        product_id: Optional[str],
        verb: str,
        field_name: str,
        from_value: Optional[str],
        to_value: Optional[str],
        qty: Decimal,
        before: Optional[_PhaseFact] = None,
        after: Optional[_PhaseFact] = None,
    ) -> Dict[str, Any]:
        return {
            "so_line_id": line.id if line else None,
            "line_no": line.line_no if line else None,
            "product_id": product_id,
            "product_code": self._product_code(product_id),
            "description": line.description if line else None,
            "verb": verb,
            "field": field_name,
            "from_value": from_value,
            "to_value": to_value,
            "qty": _qty_str(qty),
            "area_group": before.area_group if before else order.area_group,
            "sequence": before.sequence if before else None,
            "phase_id": (before.phase_id if before else None) or (line.phase_id if line else None),
            "phase_label_from": before.label if before else None,
            "phase_label_to": after.label if after else None,
            "unit_price": str(_money(_dec(line.unit_price))) if line else None,
        }

    def _order_verb(self, delivery_date: Optional[date]) -> str:
        if delivery_date and delivery_date <= date.today() + timedelta(days=RESERVE_WINDOW_DAYS):
            return VERB_RESERVE_AND_ORDER
        return VERB_ORDER

    def _schedule_snapshot(
        self, version: DeliveryScheduleVersion
    ) -> Dict[Tuple[str, int], _PhaseFact]:
        """What one version of the schedule SAID, from its own immutable record.

        Phase dates come from ``extracted_json`` because ``project_delivery_phases`` is
        keyed on ``(project, area_group, sequence)`` and a confirmed revision UPDATES that
        row in place -- reading the date off it would compare a version against itself.
        The phase rows are still used for identity and as the fallback for a version whose
        extraction is not on hand.
        """
        facts: Dict[Tuple[str, int], _PhaseFact] = {}
        for entry in self._extracted_phases(version):
            area_group = str(entry.get("area_group") or "").strip()
            sequence = entry.get("sequence")
            if not area_group or sequence is None:
                continue
            fact = _PhaseFact(
                area_group=area_group,
                sequence=int(sequence),
                label=(entry.get("label") or None),
                delivery_date=_as_date(entry.get("delivery_date")),
                phase_id=entry.get("id"),
            )
            facts[fact.key] = fact

        rows = (
            self.db.query(DeliveryScheduleCell, ProjectDeliveryPhase)
            .join(
                ProjectDeliveryPhase, ProjectDeliveryPhase.id == DeliveryScheduleCell.phase_id
            )
            .filter(DeliveryScheduleCell.version_id == version.id)
            .all()
        )
        for cell, phase in rows:
            key = (phase.area_group, phase.sequence)
            fact = facts.get(key)
            if fact is None:
                fact = _PhaseFact(
                    area_group=phase.area_group,
                    sequence=phase.sequence,
                    label=phase.label,
                    delivery_date=phase.delivery_date,
                    phase_id=phase.id,
                )
                facts[key] = fact
            fact.phase_id = fact.phase_id or phase.id
            if cell.product_id:
                fact.qty[cell.product_id] = fact.qty.get(cell.product_id, _ZERO) + _dec(cell.qty)
        return facts

    def _extracted_phases(self, version: DeliveryScheduleVersion) -> List[Dict[str, Any]]:
        payload = version.extracted_json
        if isinstance(payload, dict):
            phases = payload.get("phases")
            if isinstance(phases, list):
                return [entry for entry in phases if isinstance(entry, dict)]
        if isinstance(payload, list):
            return [entry for entry in payload if isinstance(entry, dict)]
        return []

    def _po_snapshot(self, version: ProjectPOVersion) -> Dict[str, Tuple[Decimal, Decimal]]:
        """Quantity and price per product on one PO version. Cancelled lines count as zero."""
        out: Dict[str, Tuple[Decimal, Decimal]] = {}
        rows = (
            self.db.query(ProjectPOLine)
            .filter(ProjectPOLine.po_version_id == version.id)
            .order_by(ProjectPOLine.line_no.asc())
            .all()
        )
        for row in rows:
            if not row.resolved_product_id:
                continue
            qty = _ZERO if row.is_cancelled else _dec(row.qty)
            existing_qty, _price = out.get(row.resolved_product_id, (_ZERO, _ZERO))
            out[row.resolved_product_id] = (existing_qty + qty, _dec(row.unit_price))
        return out

    def _baseline_po_version(self, order: ProjectSalesOrder) -> Optional[ProjectPOVersion]:
        if order.schedule_version_id:
            schedule_version = (
                self.db.query(DeliveryScheduleVersion)
                .filter(DeliveryScheduleVersion.id == order.schedule_version_id)
                .first()
            )
            if schedule_version is not None and schedule_version.po_version_id:
                return (
                    self.db.query(ProjectPOVersion)
                    .filter(ProjectPOVersion.id == schedule_version.po_version_id)
                    .first()
                )
        if not order.purchase_order_id:
            return None
        return (
            self.db.query(ProjectPOVersion)
            .filter(ProjectPOVersion.purchase_order_id == order.purchase_order_id)
            .order_by(ProjectPOVersion.version_no.asc())
            .first()
        )

    def _lines_by_phase_product(
        self, order: ProjectSalesOrder
    ) -> Dict[Tuple[str, int, str], ProjectSalesOrderLine]:
        phases = {
            phase.id: phase
            for phase in self.db.query(ProjectDeliveryPhase)
            .filter(ProjectDeliveryPhase.project_id == order.project_id)
            .all()
        }
        out: Dict[Tuple[str, int, str], ProjectSalesOrderLine] = {}
        for line in self._lines_of(order.id):
            phase = phases.get(line.phase_id or "")
            if phase is None or not line.product_id:
                continue
            out[(phase.area_group, phase.sequence, line.product_id)] = line
        return out

    def _assert_same_po(
        self,
        order: ProjectSalesOrder,
        from_version: DeliveryScheduleVersion,
        to_version: DeliveryScheduleVersion,
    ) -> None:
        """Both versions must belong to the same purchase order, not the same schedule.

        R2 arrived from SLG Construction while the PO came from Buimaco, which makes it a
        different ``delivery_schedules`` row for the same commitment. Requiring one
        schedule row would have refused the client's own revision.
        """
        pos = set()
        for version in (from_version, to_version):
            schedule = (
                self.db.query(DeliverySchedule)
                .filter(DeliverySchedule.id == version.delivery_schedule_id)
                .first()
            )
            pos.add(schedule.purchase_order_id if schedule else None)
        if len(pos) != 1 or (order.purchase_order_id and order.purchase_order_id not in pos):
            raise AppException(
                status_code=422,
                message=(
                    "That schedule version belongs to a different purchase order, so it "
                    "is not a revision of this sales order's schedule."
                ),
                code="amendment_schedule_foreign",
            )

    def _order_or_404(self, pso_id: str) -> ProjectSalesOrder:
        order = (
            self.db.query(ProjectSalesOrder).filter(ProjectSalesOrder.id == pso_id).first()
        )
        if order is None:
            raise AppException(
                status_code=404, message="Sales order not found.", code="so_not_found"
            )
        return order

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

    def _po_version_or_404(self, version_id: str) -> ProjectPOVersion:
        version = (
            self.db.query(ProjectPOVersion).filter(ProjectPOVersion.id == version_id).first()
        )
        if version is None:
            raise AppException(
                status_code=404,
                message="Purchase order version not found.",
                code="po_version_not_found",
            )
        return version

    def _line_or_none(self, line_id: Optional[str]) -> Optional[ProjectSalesOrderLine]:
        if not line_id:
            return None
        return (
            self.db.query(ProjectSalesOrderLine)
            .filter(ProjectSalesOrderLine.id == line_id)
            .first()
        )

    def _lines_of(self, pso_id: str) -> List[ProjectSalesOrderLine]:
        return (
            self.db.query(ProjectSalesOrderLine)
            .filter(ProjectSalesOrderLine.project_sales_order_id == pso_id)
            .order_by(ProjectSalesOrderLine.line_no.asc())
            .all()
        )

    def _renumber(self, order: ProjectSalesOrder) -> None:
        lines = sorted(
            self._lines_of(order.id),
            key=lambda line: (line.delivery_date or date.max, line.line_no),
        )
        for index, line in enumerate(lines, start=1):
            line.line_no = index
        self.db.flush()

    def _recompute(self, order: ProjectSalesOrder) -> None:
        total = sum((_dec(line.amount) for line in self._lines_of(order.id)), _ZERO)
        order.total_amount = _money(total)
        self.db.flush()

    def _product_code(self, product_id: Optional[str]) -> Optional[str]:
        if not product_id:
            return None
        row = self.db.query(Product.product_code).filter(Product.id == product_id).first()
        return row[0] if row else None

    def _next_ocn_number(self, company_id: str) -> str:
        from app.services.numbering_service import NumberingService

        configured = NumberingService(self.db).get_next_number(
            OCN_NUMBERING_DOC_TYPE, commit_rule=False
        )
        if configured:
            return configured
        highest = 0
        rows = (
            self.db.query(OrderChangeNotice.ocn_number)
            .filter(
                OrderChangeNotice.company_id == company_id,
                OrderChangeNotice.ocn_number.like(f"{_OCN_PREFIX}%"),
            )
            .all()
        )
        for (number,) in rows:
            tail = (number or "")[len(_OCN_PREFIX) :]
            if tail.isdigit():
                highest = max(highest, int(tail))
        return f"{_OCN_PREFIX}{highest + 1:0{_OCN_DIGITS}d}"
