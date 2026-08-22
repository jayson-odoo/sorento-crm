"""Customer purchase orders against a project (UAC Group F, AC-F8 to AC-F10).

Three rules carry this service:

- **Mismatches are FLAGGED, never blocked** (AC-F9). A PO that arrived is a fact. A
  system that refuses to record it because a model code differs does not prevent the
  mismatch, it just moves the PO into somebody's spreadsheet where nobody can see it.
- **The comparison is against the BOUND version**, which is the price the contractor was
  actually last shown. Comparing against v1 after three revisions would flag every
  legitimate PO, and an alert that always fires is an alert nobody reads.
- **Drift from v1 is a separate, visible number** (AC-F9a), not a flag: total erosion
  across a negotiation is what management wants to see, and it is not an exception.

Plus AC-F10, the single auto edge in v1: the FIRST PO moves the project's status to
PO Received, THROUGH the engine's legality check rather than around it. When the
configured graph has no such edge from where the project sits, the PO is still recorded
and the caller is told the status did not move -- refusing the PO would lose a fact, and
bypassing the engine would defeat the thing it exists for.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.projects import (
    PO_SOURCES,
    Project,
    ProjectParty,
    ProjectPurchaseOrder,
    ProjectPurchaseOrderLine,
    ProjectQuotation,
    ProjectQuotationLine,
    ProjectQuotationVersion,
)
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

_CENTS = Decimal("0.01")

PO_FIELDS = (
    "quotation_version_id",
    "po_source",
    "issuing_party_id",
    "po_number",
    "po_date",
    "po_amount",
    "notes",
)

LINE_FIELDS = (
    "product_id",
    "product_code",
    "description",
    "unit_price",
    "quantity",
    "uom",
    "sort_order",
    "notes",
)

# Smuggled to the route so it can report whether AC-F10's auto edge actually fired.
# An instance attr rather than a return value because create_po returns the PO, and the
# marker dies on re-query -- the same pattern the SLA services use.
_STATUS_MOVED_ATTR = "_status_moved"

PO_RECEIVED_KEY = "po_received"


# --------------------------------------------------------------------- creation


def _assert_source(source: Optional[str]) -> str:
    if source not in PO_SOURCES:
        raise AppException(
            status_code=422,
            message=(
                f"Unknown PO source '{source}'. Expected one of: {', '.join(PO_SOURCES)}."
            ),
            code="po_source_invalid",
        )
    return source


def _version_or_422(
    db: Session, *, project: Project, version_id: Optional[str]
) -> Optional[ProjectQuotationVersion]:
    """A PO with no bound version is allowed: some arrive before anything was quoted
    formally, and refusing to record one would lose the revenue entirely. It simply gets
    no mismatch check, which the UI states rather than implying everything matched."""
    if not version_id:
        return None
    version = (
        db.query(ProjectQuotationVersion)
        .filter(ProjectQuotationVersion.id == version_id)
        .first()
    )
    if not version:
        raise AppException(
            status_code=404,
            message="Quotation version not found.",
            code="quotation_version_not_found",
        )
    quotation = (
        db.query(ProjectQuotation)
        .filter(ProjectQuotation.id == version.quotation_id)
        .first()
    )
    if quotation is None or quotation.project_id != project.id:
        raise AppException(
            status_code=422,
            message="That quotation version belongs to a different project.",
            code="po_version_foreign_project",
        )
    return version


def create_po(
    db: Session, *, project: Project, actor_user_id: str, payload: Dict[str, Any]
) -> ProjectPurchaseOrder:
    if not (payload.get("po_number") or "").strip():
        raise AppException(
            status_code=422,
            message="A PO needs its number -- it is how the contractor refers to it.",
            code="po_number_required",
        )
    _assert_source(payload.get("po_source"))
    version = _version_or_422(
        db, project=project, version_id=payload.get("quotation_version_id")
    )

    is_first = (
        db.query(func.count(ProjectPurchaseOrder.id))
        .filter(ProjectPurchaseOrder.project_id == project.id)
        .scalar()
        or 0
    ) == 0

    po = ProjectPurchaseOrder(
        company_id=project.company_id,
        project_id=project.id,
        created_by=actor_user_id,
    )
    for field in PO_FIELDS:
        if field in payload:
            setattr(po, field, payload[field])
    po.quotation_version_id = version.id if version else None
    db.add(po)
    db.flush()

    setattr(po, _STATUS_MOVED_ATTR, _advance_to_po_received(db, project) if is_first else False)

    from app.services import project_activity_service as activity

    activity.record_project_event(
        db,
        project=project,
        template="po_recorded",
        payload={"po_id": str(po.id), "po_number": po.po_number},
        actor_id=actor_user_id,
    )
    db.flush()
    return po


def update_po(
    db: Session, *, po: ProjectPurchaseOrder, payload: Dict[str, Any]
) -> ProjectPurchaseOrder:
    if "po_source" in payload:
        _assert_source(payload["po_source"])
    if "quotation_version_id" in payload and payload["quotation_version_id"] != (
        po.quotation_version_id
    ):
        project = db.query(Project).filter(Project.id == po.project_id).first()
        version = _version_or_422(
            db, project=project, version_id=payload["quotation_version_id"]
        )
        po.quotation_version_id = version.id if version else None
        # Re-binding changes what the lines should have been compared against, so every
        # flag on the PO is stale. Recheck them all rather than leaving a mixed picture.
        for line in list_lines(db, po_id=po.id):
            _apply_match_flags(db, line=line, version=version)

    for field in PO_FIELDS:
        if field == "quotation_version_id":
            continue
        if field in payload:
            setattr(po, field, payload[field])
    db.flush()
    return po


def delete_po(db: Session, *, po: ProjectPurchaseOrder) -> None:
    """Hard delete. The status this PO may have triggered is NOT rolled back: the project
    genuinely passed through PO Received, and silently reversing a funnel position because
    a mistyped PO was removed would hide the correction from everybody watching the board.
    """
    db.delete(po)
    db.flush()


# ------------------------------------------------------------ the auto status edge


def _advance_to_po_received(db: Session, project: Project) -> bool:
    """AC-F10. Returns whether the status actually moved.

    Outcome is deliberately untouched: it is derived from quotations (AC-E10), and a PO
    against a lost scope is a data problem somebody should see rather than something to
    paper over by flipping the outcome.
    """
    from app.models.status import Status
    from app.services import status_service
    from app.status_engine.registry import get_status_entity

    entity_type = "project"
    entity = get_status_entity(entity_type)
    scope_id = entity.scope_for(project) if entity is not None else None

    target = (
        db.query(Status)
        .filter(
            Status.entity_type == entity_type,
            Status.key == PO_RECEIVED_KEY,
            Status.scope_id.is_(scope_id) if scope_id is None else Status.scope_id == scope_id,
        )
        .first()
    )
    if target is None and scope_id is not None:
        # A forked graph that did not redefine the rung falls back to the default scope.
        target = (
            db.query(Status)
            .filter(
                Status.entity_type == entity_type,
                Status.key == PO_RECEIVED_KEY,
                Status.scope_id.is_(None),
            )
            .first()
        )
    if target is None:
        logger.warning(
            "project %s: no '%s' status configured, PO recorded without a status move",
            project.id,
            PO_RECEIVED_KEY,
        )
        return False
    if project.status_id == target.id:
        return False

    try:
        if project.status_id is not None:
            status_service.assert_transition_allowed(
                db, entity_type, project.status_id, target.id, scope_id=scope_id
            )
        project.status_id = target.id
        db.flush()
        return True
    except AppException:
        # The graph says this move is not legal from here. The PO stays recorded; the
        # recourse is to add the edge or move the project by hand, both of which leave a
        # trace, whereas forcing the write would leave none.
        logger.warning(
            "project %s: PO recorded but the graph has no legal edge to '%s' from its "
            "current status; status left unchanged",
            project.id,
            PO_RECEIVED_KEY,
        )
        return False


# ------------------------------------------------------------------------ lines


def _quoted_line_for(
    db: Session,
    *,
    version: Optional[ProjectQuotationVersion],
    product_id: Optional[str],
    product_code: Optional[str],
) -> Optional[ProjectQuotationLine]:
    if version is None:
        return None
    query = db.query(ProjectQuotationLine).filter(
        ProjectQuotationLine.version_id == version.id
    )
    if product_id:
        return query.filter(ProjectQuotationLine.product_id == product_id).first()
    if product_code:
        # Off-catalog on both sides: match on the code the quotation printed, which is the
        # only thing the two documents share.
        return query.filter(
            func.upper(ProjectQuotationLine.product_code_snapshot)
            == product_code.strip().upper()
        ).first()
    return None


def _apply_match_flags(
    db: Session,
    *,
    line: ProjectPurchaseOrderLine,
    version: Optional[ProjectQuotationVersion],
) -> None:
    """AC-F9. Quantity is never compared: contractors order in stages, and flagging that
    would bury the two differences that matter.

    A model mismatch does NOT also raise a price mismatch. There is nothing to compare
    the price against, and two alerts for one problem is how people learn to ignore both.
    """
    quoted = _quoted_line_for(
        db, version=version, product_id=line.product_id, product_code=line.product_code
    )
    if quoted is None:
        line.model_mismatch = True
        line.price_mismatch = False
        line.quoted_unit_price = None
        return

    line.model_mismatch = False
    line.quoted_unit_price = quoted.unit_price
    line.price_mismatch = Decimal(line.unit_price or 0) != Decimal(quoted.unit_price or 0)


def upsert_line(
    db: Session,
    *,
    po: ProjectPurchaseOrder,
    payload: Dict[str, Any],
    line: Optional[ProjectPurchaseOrderLine] = None,
) -> ProjectPurchaseOrderLine:
    if line is None:
        line = ProjectPurchaseOrderLine(company_id=po.company_id, po_id=po.id)
        db.add(line)

    for field in LINE_FIELDS:
        if field in payload:
            setattr(line, field, payload[field])
    if line.unit_price is None:
        line.unit_price = Decimal("0.00")
    if line.quantity is None:
        line.quantity = Decimal("1")
    if line.product_id:
        # Fill from the product, but never OVERWRITE what the PO printed: their code is
        # evidence, and "WC-BLK-01 for our SRT-WC-01" IS the mismatch somebody needs to
        # see. Snapshotted rather than joined on read, like the quotation line (AC-E4),
        # so a catalogue rename cannot rewrite what this PO was checked against.
        from app.models.product import Product

        product = db.query(Product).filter(Product.id == line.product_id).first()
        if product is not None:
            if not (line.product_code or "").strip():
                line.product_code = product.product_code
            if not (line.description or "").strip():
                line.description = product.description or product.product_name
    if not line.product_id and not (line.product_code or "").strip():
        raise AppException(
            status_code=422,
            message="A PO line needs either a product or the code the PO printed.",
            code="po_line_identity_required",
        )

    line.line_total = (
        Decimal(line.unit_price or 0) * Decimal(line.quantity or 0)
    ).quantize(_CENTS)

    version = (
        db.query(ProjectQuotationVersion)
        .filter(ProjectQuotationVersion.id == po.quotation_version_id)
        .first()
        if po.quotation_version_id
        else None
    )
    _apply_match_flags(db, line=line, version=version)
    db.flush()
    return line


def replace_lines(
    db: Session, *, po: ProjectPurchaseOrder, lines: Sequence[Dict[str, Any]]
) -> List[ProjectPurchaseOrderLine]:
    """The whole desired line set of one PO, written in ONE transaction.

    **Why this exists.** The lines used to be written per row, so entering a ten-line PO was
    ten requests, each with its own confirmation on the way out, and a sequence that
    half-failed left a PO in a state nobody typed. The screen is an edit view now: one Save
    covers the header and every line, so either the arrangement the user made is what is
    stored or nothing moved.

    **This is a REPLACE, not a merge.** ``lines`` is the full desired set, and a stored line
    whose id is absent from it is DELETED. A caller that sends only the rows it happened to
    touch will therefore wipe every row it left out, so it must always send the whole set it
    is showing the user.

    **Identity.** A line already stored carries its ``id``; a new one arrives without one. An
    id that is not on this PO is refused rather than treated as new -- treating it as new
    would duplicate the row the caller meant to move.

    **Order** is array position, so reordering is just sending a different order and any
    ``sort_order`` in the payload is ignored.

    Every line still goes through ``upsert_line``, so the product snapshot and the two
    mismatch flags are computed by the one implementation the per-row path uses. The refusals
    all fire before any row is touched or on the row that is wrong, and the route's rollback
    is what makes the whole save atomic.
    """
    # Keyed by the id as a STRING, which is what the payload carries: the column is a
    # `UUID(as_uuid=False)`, so this is a no-op at runtime and stops the two sides of the
    # comparison being different types on paper.
    stored = {str(row.id): row for row in list_lines(db, po_id=str(po.id))}
    kept: set = set()
    written: List[ProjectPurchaseOrderLine] = []

    for index, incoming in enumerate(lines):
        payload = dict(incoming)
        line_id = payload.pop("id", None)
        target: Optional[ProjectPurchaseOrderLine] = None
        if line_id:
            line_id = str(line_id)
            if line_id in kept:
                raise AppException(
                    status_code=422,
                    message="The same line appears twice in this save.",
                    code="po_line_duplicate",
                )
            target = stored.get(line_id)
            if target is None:
                raise AppException(
                    status_code=404,
                    message="One of these lines is not on this purchase order.",
                    code="po_line_not_found",
                )
            kept.add(line_id)
        payload["sort_order"] = index
        written.append(upsert_line(db, po=po, payload=payload, line=target))

    for line_id, row in stored.items():
        if line_id not in kept:
            db.delete(row)

    db.flush()
    return written


def save_po_document(
    db: Session, *, po: ProjectPurchaseOrder, payload: Dict[str, Any]
) -> List[ProjectPurchaseOrderLine]:
    """The header and, when the payload carries them, the whole line set.

    The order is the point, and it is why this is a service function rather than two calls
    from the route: the quotation binding decides what every line is compared against, so it
    has to be applied BEFORE the lines are written or the flags would answer for the version
    that was bound a moment ago.

    ``lines`` absent leaves the lines exactly as they are -- the record-a-PO modal sends only
    header fields, and reading that as "an empty set" would wipe the PO. An empty ARRAY is a
    real intent (the user removed every line) and does clear them.
    """
    header = {key: value for key, value in payload.items() if key != "lines"}
    update_po(db, po=po, payload=header)
    if payload.get("lines") is None:
        return list_lines(db, po_id=str(po.id))
    return replace_lines(db, po=po, lines=payload["lines"])


def delete_line(db: Session, *, line: ProjectPurchaseOrderLine) -> None:
    db.delete(line)
    db.flush()


def list_lines(db: Session, *, po_id: str) -> List[ProjectPurchaseOrderLine]:
    return (
        db.query(ProjectPurchaseOrderLine)
        .filter(ProjectPurchaseOrderLine.po_id == po_id)
        .order_by(
            ProjectPurchaseOrderLine.sort_order.asc(),
            ProjectPurchaseOrderLine.created_at.asc(),
        )
        .all()
    )


# ------------------------------------------------------------------- drift vs v1


def po_total(db: Session, *, po: ProjectPurchaseOrder) -> Decimal:
    """The lines when there are any, else the header amount.

    A PO recorded as a single figure with no line detail is common early on, and reading
    it as zero would understate the pipeline.
    """
    total = (
        db.query(func.coalesce(func.sum(ProjectPurchaseOrderLine.line_total), 0))
        .filter(ProjectPurchaseOrderLine.po_id == po.id)
        .scalar()
    ) or Decimal("0")
    if Decimal(total) == 0 and po.po_amount is not None:
        return Decimal(po.po_amount).quantize(_CENTS)
    return Decimal(total).quantize(_CENTS)


def drift_from_first_version(
    db: Session, *, po: ProjectPurchaseOrder
) -> Dict[str, Optional[Decimal]]:
    """AC-F9a. Total price erosion from where the negotiation STARTED.

    Deliberately not a flag. It is the expected outcome of a negotiation, and management
    wants the size of it, not an exception report.

    ``percent`` is None when v1 priced nothing: a percentage against zero is not a
    number, and reporting 0% would read as "no erosion" when the truth is "no baseline".
    """
    v1_total = Decimal("0")
    if po.quotation_version_id:
        version = (
            db.query(ProjectQuotationVersion)
            .filter(ProjectQuotationVersion.id == po.quotation_version_id)
            .first()
        )
        if version is not None:
            first = (
                db.query(ProjectQuotationVersion)
                .filter(
                    ProjectQuotationVersion.quotation_id == version.quotation_id,
                    ProjectQuotationVersion.version_no == 1,
                )
                .first()
            )
            if first is not None:
                v1_total = Decimal(first.total_amount or 0).quantize(_CENTS)

    current = po_total(db, po=po)
    has_po_figure = current != 0 or po.po_amount is not None
    # A PO recorded as a header with nothing on it yet has NO figure to compare, and
    # reporting -100% would say we gave the whole thing away. Both numbers are withheld
    # rather than just the percentage: a delta of -RM 35,000 is the same lie in currency.
    if not has_po_figure or v1_total == 0:
        return {
            "v1_total": v1_total,
            "po_total": current,
            "delta": None,
            "percent": None,
        }
    delta = (current - v1_total).quantize(_CENTS)
    return {
        "v1_total": v1_total,
        "po_total": current,
        "delta": delta,
        "percent": (delta / v1_total * Decimal("100")).quantize(_CENTS),
    }


# ----------------------------------------------------------------------- reading


def list_pos(db: Session, *, project_id: str) -> List[ProjectPurchaseOrder]:
    return (
        db.query(ProjectPurchaseOrder)
        .filter(ProjectPurchaseOrder.project_id == project_id)
        .order_by(
            ProjectPurchaseOrder.po_date.desc().nullslast(),
            ProjectPurchaseOrder.created_at.desc(),
            # The number breaks the tie, so two POs imported in one pass cannot come back
            # in a different order each time - the detail pager
            # (project_record_navigation.purchase_order_neighbours) carries the same
            # tie-breaker and has to walk the list it came from.
            ProjectPurchaseOrder.po_number.asc(),
        )
        .all()
    )


def get_po(db: Session, po_id: str) -> ProjectPurchaseOrder:
    po = db.query(ProjectPurchaseOrder).filter(ProjectPurchaseOrder.id == po_id).first()
    if not po:
        raise AppException(
            status_code=404, message="Purchase order not found.", code="po_not_found"
        )
    return po


def serialize_pos(
    db: Session, purchase_orders: Sequence[ProjectPurchaseOrder]
) -> List[Dict[str, Any]]:
    """Bulk, with the issuer, the scope it was quoted under, and the flag counts folded
    in so the list is readable without opening a row."""
    if not purchase_orders:
        return []

    ids = [po.id for po in purchase_orders]
    flag_rows = (
        db.query(
            ProjectPurchaseOrderLine.po_id,
            func.count(ProjectPurchaseOrderLine.id),
            func.coalesce(func.sum(ProjectPurchaseOrderLine.line_total), 0),
        )
        .filter(ProjectPurchaseOrderLine.po_id.in_(ids))
        .group_by(ProjectPurchaseOrderLine.po_id)
        .all()
    )
    totals = {row[0]: (int(row[1]), Decimal(row[2] or 0)) for row in flag_rows}

    def _flag_count(column) -> Dict[str, int]:
        rows = (
            db.query(ProjectPurchaseOrderLine.po_id, func.count(ProjectPurchaseOrderLine.id))
            .filter(ProjectPurchaseOrderLine.po_id.in_(ids), column.is_(True))
            .group_by(ProjectPurchaseOrderLine.po_id)
            .all()
        )
        return {row[0]: int(row[1]) for row in rows}

    model_flags = _flag_count(ProjectPurchaseOrderLine.model_mismatch)
    price_flags = _flag_count(ProjectPurchaseOrderLine.price_mismatch)

    # Which POs have been agreed, and which have a delivery programme agreed too. Two
    # set lookups rather than a query per row: this list renders every PO on a project.
    confirmed_po_ids: set = set()
    scheduled_po_ids: set = set()
    # How many sales orders are already OUT of each PO. Editing a PO stays allowed -- a
    # correction is the normal case -- but the screen has to be able to say this before
    # somebody saves over it, because the orders already published do not follow the change.
    published_so_counts: Dict[str, int] = {}
    if ids:
        from app.models.project_so import (
            SO_STATUS_AMENDED,
            SO_STATUS_PUBLISHED,
            DeliverySchedule,
            DeliveryScheduleVersion,
            ProjectPOVersion,
            ProjectSalesOrder,
        )

        confirmed_po_ids = {
            row[0]
            for row in db.query(ProjectPOVersion.purchase_order_id)
            .filter(
                ProjectPOVersion.purchase_order_id.in_(ids),
                ProjectPOVersion.confirmed_at.isnot(None),
            )
            .all()
        }
        scheduled_po_ids = {
            row[0]
            for row in db.query(DeliverySchedule.purchase_order_id)
            .join(
                DeliveryScheduleVersion,
                DeliveryScheduleVersion.delivery_schedule_id == DeliverySchedule.id,
            )
            .filter(
                DeliverySchedule.purchase_order_id.in_(ids),
                DeliveryScheduleVersion.confirmed_at.isnot(None),
            )
            .all()
        }
        published_so_counts = {
            str(row[0]): int(row[1])
            for row in db.query(
                ProjectSalesOrder.purchase_order_id, func.count(ProjectSalesOrder.id)
            )
            .filter(
                ProjectSalesOrder.purchase_order_id.in_(ids),
                # Amended counts too: it was published and then changed, so it is still out.
                ProjectSalesOrder.status.in_((SO_STATUS_PUBLISHED, SO_STATUS_AMENDED)),
            )
            .group_by(ProjectSalesOrder.purchase_order_id)
            .all()
        }

    party_ids = {po.issuing_party_id for po in purchase_orders if po.issuing_party_id}
    parties: Dict[str, str] = {}
    if party_ids:
        parties = {
            row.id: row.name
            for row in db.query(ProjectParty).filter(ProjectParty.id.in_(party_ids)).all()
        }

    version_ids = {po.quotation_version_id for po in purchase_orders if po.quotation_version_id}
    versions = {
        v.id: v
        for v in db.query(ProjectQuotationVersion)
        .filter(ProjectQuotationVersion.id.in_(version_ids))
        .all()
    } if version_ids else {}
    quotation_ids = {v.quotation_id for v in versions.values()}
    quotations = {
        q.id: q
        for q in db.query(ProjectQuotation)
        .filter(ProjectQuotation.id.in_(quotation_ids))
        .all()
    } if quotation_ids else {}

    out: List[Dict[str, Any]] = []
    for po in purchase_orders:
        version = versions.get(po.quotation_version_id or "")
        quotation = quotations.get(version.quotation_id) if version else None
        line_count, line_total = totals.get(po.id, (0, Decimal("0")))
        drift = drift_from_first_version(db, po=po)
        out.append(
            {
                "id": po.id,
                "project_id": po.project_id,
                "quotation_version_id": po.quotation_version_id,
                "quotation_id": version.quotation_id if version else None,
                "scope_label": quotation.scope_label if quotation else None,
                "version_no": version.version_no if version else None,
                "po_source": po.po_source,
                "issuing_party_id": po.issuing_party_id,
                "issuing_party_name": parties.get(po.issuing_party_id or ""),
                "po_number": po.po_number,
                "po_date": po.po_date,
                "po_amount": po.po_amount,
                "notes": po.notes,
                "line_count": line_count,
                "line_total": line_total,
                # What the PO still needs before it can become sales orders. Sent from
                # here rather than inferred on the screen, because the screen would
                # have to load every version and every schedule of every PO to work it
                # out, and a next step that is wrong is worse than none.
                "status": po.status,
                "po_confirmed": bool(confirmed_po_ids and po.id in confirmed_po_ids),
                "schedule_confirmed": bool(scheduled_po_ids and po.id in scheduled_po_ids),
                "published_sales_order_count": published_so_counts.get(str(po.id), 0),
                "model_mismatch_count": model_flags.get(po.id, 0),
                "price_mismatch_count": price_flags.get(po.id, 0),
                "v1_total": drift["v1_total"],
                "drift_delta": drift["delta"],
                "drift_percent": drift["percent"],
                "created_at": po.created_at,
                "updated_at": po.updated_at,
            }
        )
    return out


def serialize_lines(
    db: Session, lines: Sequence[ProjectPurchaseOrderLine]
) -> List[Dict[str, Any]]:
    return [
        {
            "id": line.id,
            "po_id": line.po_id,
            "product_id": line.product_id,
            "product_code": line.product_code,
            "description": line.description,
            "unit_price": line.unit_price,
            "quantity": line.quantity,
            "uom": line.uom,
            "line_total": line.line_total,
            "quoted_unit_price": line.quoted_unit_price,
            "model_mismatch": line.model_mismatch,
            "price_mismatch": line.price_mismatch,
            "sort_order": line.sort_order,
            "notes": line.notes,
        }
        for line in lines
    ]
