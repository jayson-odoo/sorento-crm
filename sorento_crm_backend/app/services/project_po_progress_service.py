"""PM-SIMPLIFY: one PO's progress, line by line and area by area, and moving an area's date.

Plan `documentation/plans/projects/PLAN-pm-simplify-17oct.md` (AC-L1, AC-D1, AC-D2, AC-O3).

Everything here is read off rows that already exist; there is no new table:

* ordered: the PO line, from the latest CONFIRMED PO version (or the hand-keyed lines when
  the PO was never scanned), the same source the sales order build reads.
* scheduled: the latest CONFIRMED schedule version's cells, per product. One product can sit
  on several PO lines, so its units are shared out over those lines in line order.
* delivered: AutoCount's delivered quantity on the core line each project sales order line
  is linked to (`delivered_qty_of`). Read-only: AutoCount is the source of truth (Q4a).

An area's date belongs to the area (`delivery_phases.delivery_date`). Moving it moves every
sales order line on that area that is still a draft; a published order is AutoCount's, so it
gets an amendment proposed instead of being rewritten (Q2a, defect D6).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.models.project_so import (
    AUTHORED_LIVE_STATUSES,
    LIVE_SO_STATUSES,
    DeliverySchedule,
    DeliveryScheduleCell,
    DeliveryScheduleVersion,
    ProjectDeliveryPhase,
    ProjectPOLine,
    ProjectPOVersion,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.models.projects import ProjectPurchaseOrder, ProjectPurchaseOrderLine
from app.services.error_handler import AppException

_ZERO = Decimal("0")


def _dec(value: Any) -> Decimal:
    if value is None:
        return _ZERO
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass
class _Line:
    key: str
    po_line_id: Optional[str]
    line_no: int
    product_id: Optional[str]
    code: Optional[str]
    description: Optional[str]
    uom: Optional[str]
    ordered: Decimal


# ------------------------------------------------------------------ sources


def latest_confirmed_po_version(db: Session, po_id: str) -> Optional[ProjectPOVersion]:
    return (
        db.query(ProjectPOVersion)
        .filter(
            ProjectPOVersion.purchase_order_id == po_id,
            ProjectPOVersion.confirmed_at.isnot(None),
        )
        .order_by(ProjectPOVersion.version_no.desc())
        .first()
    )


def latest_confirmed_schedule_version(
    db: Session, po_id: str
) -> Optional[DeliveryScheduleVersion]:
    return (
        db.query(DeliveryScheduleVersion)
        .join(DeliverySchedule, DeliverySchedule.id == DeliveryScheduleVersion.delivery_schedule_id)
        .filter(
            DeliverySchedule.purchase_order_id == po_id,
            DeliveryScheduleVersion.confirmed_at.isnot(None),
        )
        .order_by(DeliveryScheduleVersion.confirmed_at.desc())
        .first()
    )


def _po_lines(db: Session, po_id: str) -> List[_Line]:
    version = latest_confirmed_po_version(db, po_id)
    if version is not None:
        rows = (
            db.query(ProjectPOLine)
            .filter(ProjectPOLine.po_version_id == version.id)
            .order_by(ProjectPOLine.line_no.asc())
            .all()
        )
        return [
            _Line(
                key=str(row.id),
                po_line_id=str(row.id),
                line_no=row.line_no,
                product_id=row.resolved_product_id,
                code=row.stock_code_raw,
                description=row.description_raw,
                uom=row.uom_raw,
                ordered=_dec(row.qty),
            )
            for row in rows
            if not row.is_cancelled
        ]
    rows = (
        db.query(ProjectPurchaseOrderLine)
        .filter(ProjectPurchaseOrderLine.po_id == po_id)
        .order_by(
            ProjectPurchaseOrderLine.sort_order.asc(),
            ProjectPurchaseOrderLine.created_at.asc(),
        )
        .all()
    )
    return [
        _Line(
            key=str(row.id),
            po_line_id=None,
            line_no=index,
            product_id=row.product_id,
            code=row.product_code,
            description=row.description,
            uom=row.uom,
            ordered=_dec(row.quantity),
        )
        for index, row in enumerate(rows, start=1)
    ]


def _delivered_by_core_line(db: Session, core_ids: Iterable[str]) -> Dict[str, Decimal]:
    ids = [str(core_id) for core_id in core_ids if core_id]
    if not ids:
        return {}
    from app.models.order import SalesOrderLine
    from app.services.project_supply_service import delivered_qty_of

    return {
        str(core.id): delivered_qty_of(core)
        for core in db.query(SalesOrderLine).filter(SalesOrderLine.id.in_(ids)).all()
    }


# ------------------------------------------------------------------ progress


def po_progress(db: Session, po: ProjectPurchaseOrder) -> Dict[str, Any]:
    """AC-L1 and AC-D1: every PO line's ordered / scheduled / delivered / outstanding, and
    every area of the confirmed schedule with its date, units and sales orders."""
    lines = _po_lines(db, po.id)
    schedule_version = latest_confirmed_schedule_version(db, po.id)
    today = date.today()

    phases: Dict[str, ProjectDeliveryPhase] = {}
    cells: List[DeliveryScheduleCell] = []
    if schedule_version is not None:
        cells = (
            db.query(DeliveryScheduleCell)
            .filter(DeliveryScheduleCell.version_id == schedule_version.id)
            .all()
        )
        phase_ids = {cell.phase_id for cell in cells}
        if phase_ids:
            phases = {
                str(phase.id): phase
                for phase in db.query(ProjectDeliveryPhase)
                .filter(ProjectDeliveryPhase.id.in_(phase_ids))
                .all()
            }

    orders = {
        str(order.id): order
        for order in db.query(ProjectSalesOrder)
        .filter(ProjectSalesOrder.purchase_order_id == po.id)
        .all()
    }
    so_lines: List[ProjectSalesOrderLine] = (
        db.query(ProjectSalesOrderLine)
        .filter(ProjectSalesOrderLine.project_sales_order_id.in_(list(orders)))
        .all()
        if orders
        else []
    )
    delivered_core = _delivered_by_core_line(
        db, (line.core_sales_order_line_id for line in so_lines)
    )

    def _delivered(line: ProjectSalesOrderLine) -> Decimal:
        order = orders.get(str(line.project_sales_order_id))
        if order is None or order.status not in LIVE_SO_STATUSES:
            return _ZERO
        return delivered_core.get(str(line.core_sales_order_line_id or ""), _ZERO)

    # Schedule units per product, then shared out over the PO lines carrying that product
    # in line order: the last line takes whatever is left, so an over-scheduled product
    # shows on the line the customer printed last.
    scheduled_by_product: Dict[str, Decimal] = defaultdict(lambda: _ZERO)
    for cell in cells:
        if cell.product_id:
            scheduled_by_product[str(cell.product_id)] += _dec(cell.qty)
    lines_by_product: Dict[str, List[_Line]] = defaultdict(list)
    for line in lines:
        if line.product_id:
            lines_by_product[str(line.product_id)].append(line)
    scheduled: Dict[str, Decimal] = {}
    for product_id, product_lines in lines_by_product.items():
        left = scheduled_by_product.get(product_id, _ZERO)
        for index, line in enumerate(product_lines):
            share = left if index == len(product_lines) - 1 else min(left, line.ordered)
            scheduled[line.key] = share
            left -= share

    # Which SO lines belong to which PO line. The build stamps `source_po_line_id`; a
    # set's companion lines carry it too but are another product, so only the PO line's
    # own product counts. A hand-keyed PO has no line ids, so its product is the match.
    so_by_line: Dict[str, List[ProjectSalesOrderLine]] = defaultdict(list)
    keys_by_po_line = {line.po_line_id: line for line in lines if line.po_line_id}
    hand_keyed_by_product = {
        str(line.product_id): line for line in lines if not line.po_line_id and line.product_id
    }
    for so_line in so_lines:
        owner: Optional[_Line] = None
        if so_line.source_po_line_id:
            owner = keys_by_po_line.get(str(so_line.source_po_line_id))
            if owner is not None and owner.product_id and str(so_line.product_id) != str(
                owner.product_id
            ):
                owner = None
        elif so_line.product_id:
            owner = hand_keyed_by_product.get(str(so_line.product_id))
        if owner is not None:
            so_by_line[owner.key].append(so_line)

    def _phase_bits(phase_id: Optional[str]) -> Dict[str, Any]:
        phase = phases.get(str(phase_id or "")) or (
            db.query(ProjectDeliveryPhase).filter(ProjectDeliveryPhase.id == phase_id).first()
            if phase_id
            else None
        )
        return {
            "phase_id": str(phase.id) if phase else None,
            "area_group": phase.area_group if phase else None,
            "label": phase.label if phase else None,
        }

    out_lines: List[Dict[str, Any]] = []
    for line in lines:
        deliveries: List[Dict[str, Any]] = []
        delivered = _ZERO
        for so_line in sorted(
            so_by_line.get(line.key, []),
            key=lambda row: (row.delivery_date or date.max, row.line_no),
        ):
            order = orders[str(so_line.project_sales_order_id)]
            got = _delivered(so_line)
            delivered += got
            deliveries.append(
                {
                    **_phase_bits(so_line.phase_id),
                    "delivery_date": so_line.delivery_date,
                    "units": _dec(so_line.qty),
                    "delivered": got,
                    "sales_order_id": str(order.id),
                    "provisional_ref": order.autocount_doc_no or order.provisional_ref,
                    "sales_order_status": order.status,
                }
            )
        outstanding = max(line.ordered - delivered, _ZERO)
        upcoming = [
            row["delivery_date"]
            for row in deliveries
            if row["delivery_date"] and row["delivery_date"] >= today
            and row["units"] > row["delivered"]
        ]
        line_scheduled = scheduled.get(line.key, _ZERO)
        out_lines.append(
            {
                "key": line.key,
                "po_line_id": line.po_line_id,
                "line_no": line.line_no,
                "product_id": line.product_id,
                "product_code": line.code,
                "description": line.description,
                "uom": line.uom,
                "ordered": line.ordered,
                "scheduled": line_scheduled,
                "schedule_gap": line_scheduled - line.ordered,
                "delivered": delivered,
                "outstanding": outstanding,
                "next_delivery_date": min(upcoming) if upcoming else None,
                "deliveries": deliveries,
            }
        )

    # Areas: units off the confirmed cells, delivered and orders off the SO lines on them.
    units_by_phase: Dict[str, Decimal] = defaultdict(lambda: _ZERO)
    products_by_phase: Dict[str, set] = defaultdict(set)
    for cell in cells:
        units_by_phase[str(cell.phase_id)] += _dec(cell.qty)
        if cell.product_id:
            products_by_phase[str(cell.phase_id)].add(str(cell.product_id))
    delivered_by_phase: Dict[str, Decimal] = defaultdict(lambda: _ZERO)
    orders_by_phase: Dict[str, Dict[str, ProjectSalesOrder]] = defaultdict(dict)
    for so_line in so_lines:
        phase_key = str(so_line.phase_id or "")
        if phase_key not in phases:
            continue
        order = orders[str(so_line.project_sales_order_id)]
        orders_by_phase[phase_key][str(order.id)] = order
        if str(so_line.product_id or "") in products_by_phase[phase_key]:
            delivered_by_phase[phase_key] += _delivered(so_line)

    areas = [
        {
            "phase_id": phase_id,
            "area_group": phase.area_group,
            "sequence": phase.sequence,
            "label": phase.label,
            "delivery_date": phase.delivery_date,
            "units": units_by_phase.get(phase_id, _ZERO),
            "delivered": delivered_by_phase.get(phase_id, _ZERO),
            "sales_orders": [
                {
                    "id": order_id,
                    "provisional_ref": order.autocount_doc_no or order.provisional_ref,
                    "status": order.status,
                }
                for order_id, order in sorted(
                    orders_by_phase.get(phase_id, {}).items(),
                    key=lambda item: item[1].provisional_ref,
                )
            ],
        }
        for phase_id, phase in sorted(
            phases.items(),
            key=lambda item: (
                item[1].delivery_date or date.max,
                item[1].area_group,
                item[1].sequence,
            ),
        )
    ]

    upcoming_areas = [
        area["delivery_date"]
        for area in areas
        if area["delivery_date"] and area["delivery_date"] >= today
        and area["units"] > area["delivered"]
    ]
    return {
        "purchase_order_id": str(po.id),
        "schedule_version_id": str(schedule_version.id) if schedule_version else None,
        "lines": out_lines,
        "areas": areas,
        "totals": {
            "ordered": sum((line["ordered"] for line in out_lines), _ZERO),
            "scheduled": sum((line["scheduled"] for line in out_lines), _ZERO),
            "delivered": sum((line["delivered"] for line in out_lines), _ZERO),
            "outstanding": sum((line["outstanding"] for line in out_lines), _ZERO),
            "next_delivery_date": min(upcoming_areas) if upcoming_areas else None,
            "schedule_short_lines": sum(
                1 for line in out_lines if line["schedule_gap"] < 0
            ),
            "schedule_over_lines": sum(1 for line in out_lines if line["schedule_gap"] > 0),
        },
    }


def po_totals(db: Session, purchase_orders: Sequence[ProjectPurchaseOrder]) -> Dict[str, Dict[str, Any]]:
    """AC-O3: ordered and delivered units and the next delivery date per PO, for the Orders
    tab. One `po_progress` per PO: a project carries a handful of POs, not hundreds."""
    out: Dict[str, Dict[str, Any]] = {}
    for po in purchase_orders:
        totals = po_progress(db, po)["totals"]
        out[str(po.id)] = {
            "ordered_units": totals["ordered"],
            "delivered_units": totals["delivered"],
            "next_delivery_date": totals["next_delivery_date"],
        }
    return out


# ------------------------------------------------------------------ area date


def get_phase(db: Session, phase_id: str) -> ProjectDeliveryPhase:
    phase = db.query(ProjectDeliveryPhase).filter(ProjectDeliveryPhase.id == phase_id).first()
    if phase is None:
        raise AppException(
            status_code=404, message="Delivery area not found.", code="delivery_phase_not_found"
        )
    return phase


def change_area_date(
    db: Session,
    phase: ProjectDeliveryPhase,
    *,
    delivery_date: date,
    actor_user_id: str,
    restore_lines: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """AC-D2: write the area's date and the date of every draft sales order line on it, in
    the caller's transaction. A published order is not rewritten: an amendment is proposed
    for it through the existing amendment flow, which is where AutoCount hears of it.

    ``restore_lines`` is Undo (AC-D3): the per-line dates this call returned last time, so
    lines that disagreed before the move get their own date back rather than the area's.
    Only draft lines on THIS area are accepted.
    """
    previous_date = phase.delivery_date
    phase.delivery_date = delivery_date

    rows = (
        db.query(ProjectSalesOrderLine, ProjectSalesOrder)
        .join(
            ProjectSalesOrder,
            ProjectSalesOrder.id == ProjectSalesOrderLine.project_sales_order_id,
        )
        .filter(ProjectSalesOrderLine.phase_id == phase.id)
        .all()
    )
    draft_rows = [(line, order) for line, order in rows if order.status not in LIVE_SO_STATUSES]
    live_orders: Dict[str, ProjectSalesOrder] = {
        str(order.id): order for _line, order in rows if order.status in AUTHORED_LIVE_STATUSES
    }
    # Adopted from the AutoCount book: never authored here, so it cannot be amended here
    # either. Named in the result so the move is not silently partial.
    adopted_orders: Dict[str, ProjectSalesOrder] = {
        str(order.id): order
        for _line, order in rows
        if order.status in LIVE_SO_STATUSES and order.status not in AUTHORED_LIVE_STATUSES
    }

    restore = {str(row["id"]): row.get("delivery_date") for row in (restore_lines or [])}
    draft_ids = {str(line.id) for line, _order in draft_rows}
    stray = set(restore) - draft_ids
    if stray:
        raise AppException(
            status_code=422,
            message="Undo names a line that is not a draft line on this area.",
            code="area_date_restore_foreign_line",
        )

    previous_lines: List[Dict[str, Any]] = []
    moved_orders: Dict[str, ProjectSalesOrder] = {}
    moved = 0
    for line, order in draft_rows:
        target = restore[str(line.id)] if str(line.id) in restore else delivery_date
        previous_lines.append({"id": str(line.id), "delivery_date": line.delivery_date})
        if line.delivery_date != target:
            line.delivery_date = target
            moved += 1
            moved_orders[str(order.id)] = order
    db.flush()

    amendments: List[Dict[str, Any]] = []
    if live_orders and previous_date != delivery_date:
        from app.services.project_so_delta_service import ProjectSODeltaService

        delta = ProjectSODeltaService(db)
        for order in sorted(live_orders.values(), key=lambda row: row.provisional_ref):
            entry: Dict[str, Any] = {
                "sales_order_id": str(order.id),
                "provisional_ref": order.autocount_doc_no or order.provisional_ref,
                "amendment_id": None,
                "refused": None,
            }
            savepoint = db.begin_nested()
            try:
                created = delta.create_area_date_amendment(
                    order.id,
                    phase=phase,
                    delivery_date=delivery_date,
                    actor_user_id=actor_user_id,
                )
                savepoint.commit()
                entry["amendment_id"] = created["amendment_id"] if created else None
            except AppException as exc:
                savepoint.rollback()
                entry["refused"] = exc.message
            amendments.append(entry)
    if previous_date != delivery_date:
        for order in sorted(adopted_orders.values(), key=lambda row: row.provisional_ref):
            amendments.append(
                {
                    "sales_order_id": str(order.id),
                    "provisional_ref": order.autocount_doc_no or order.provisional_ref,
                    "amendment_id": None,
                    "refused": "Taken from AutoCount, so change its date in AutoCount.",
                }
            )

    return {
        "phase_id": str(phase.id),
        "area_group": phase.area_group,
        "label": phase.label,
        "delivery_date": phase.delivery_date,
        "previous_date": previous_date,
        "moved_lines": moved,
        "moved_orders": [
            {
                "id": order_id,
                "provisional_ref": order.autocount_doc_no or order.provisional_ref,
            }
            for order_id, order in sorted(
                moved_orders.items(), key=lambda item: item[1].provisional_ref
            )
        ],
        "previous_lines": previous_lines,
        "amendments": amendments,
    }
