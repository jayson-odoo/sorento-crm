"""Quotations, versions and the two guardrail alerts (UAC Group E).

The version model is defined by what it does NOT have. There is no
``current_version_id`` and no ``is_frozen`` column: **current is MAX(version_no)** and
everything below it is frozen (AC-E3a). Two facts that must agree is one too many -- a
pointer and a flag drift the first time a write half-fails, and after that nobody can
say which version the customer is holding.

Editing the current version saves IN PLACE (AC-E2). Revise freezes it and opens the
next (AC-E3). That split is what makes "which document did we send" answerable.

Two alerts, computed on save and STORED on the line:

- **non-standard SKU** -- off-catalog, or a product outside the nominated series.
- **below minimum price** -- fires to management on the TRANSITION into breach only
  (AC-E6a). In-place editing is how the job is done, and an alert per save is an alert
  that gets filtered into a folder nobody opens.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Set

from sqlalchemy import Integer, func
from sqlalchemy.orm import Session

from app.models.lookup import LookupOption, LookupSet
from app.models.product import Product
from app.models.projects import (
    OUTCOME_LOST,
    OUTCOME_OPEN,
    OUTCOME_WON,
    QUOTATION_LOSS_REASON_SET_KEY,
    QUOTATION_OUTCOME_LOST,
    QUOTATION_OUTCOME_OPEN,
    QUOTATION_OUTCOME_WON,
    UNIT_TYPES,
    Project,
    ProjectQuotation,
    ProjectQuotationIssueScope,
    ProjectQuotationLine,
    ProjectQuotationVersion,
)
from app.services import project_pricing_service as pricing
from app.services.error_handler import AppException

OUTCOME_OPEN_Q = QUOTATION_OUTCOME_OPEN
OUTCOME_WON_Q = QUOTATION_OUTCOME_WON
OUTCOME_LOST_Q = QUOTATION_OUTCOME_LOST
QUOTATION_OUTCOMES = (OUTCOME_OPEN_Q, OUTCOME_WON_Q, OUTCOME_LOST_Q)

# Re-exported so callers read one name for "open" rather than importing from two places.
OUTCOME_OPEN = QUOTATION_OUTCOME_OPEN

_CENTS = Decimal("0.01")

# Where a just-computed breach is parked for the caller to notify on. An instance attr
# rather than a return value because ``upsert_line`` returns the line, and the marker
# dies on re-query -- the same smuggling pattern the SLA services use, and for the same
# reason: the route needs it, the row must not carry it.
_BREACH_ATTR = "_breach_events"

LINE_FIELDS = (
    "product_id",
    "product_code_snapshot",
    "description_snapshot",
    "image_attachment_id",
    "unit_price",
    "quantity",
    "uom",
    "unit_type",
    "sort_order",
    "notes",
    # The columns the printed quotation carries but the screen did not: the A / B / C item letter
    # that groups a fitting with its valve and hose, the band heading off the customer's own bill
    # of quantities, and the alternate that is quoted at a rate WITHOUT being added up.
    "item_label",
    "brand_snapshot",
    "technical_spec",
    "complete_set",
    "band_label",
    "is_rate_only",
)

_NUMERIC_LINE_FIELDS = ("unit_price", "quantity")


# ------------------------------------------------------------------- versions


def get_quotation_or_404(db: Session, project_id: str, quotation_id: str) -> ProjectQuotation:
    quotation = (
        db.query(ProjectQuotation)
        .filter(
            ProjectQuotation.id == quotation_id,
            ProjectQuotation.project_id == project_id,
        )
        .first()
    )
    if not quotation:
        raise AppException(
            status_code=404, message="Quotation not found.", code="quotation_not_found"
        )
    return quotation


def list_versions(db: Session, quotation_id: str) -> List[ProjectQuotationVersion]:
    """Newest first: the current version is what people open."""
    return (
        db.query(ProjectQuotationVersion)
        .filter(ProjectQuotationVersion.quotation_id == quotation_id)
        .order_by(ProjectQuotationVersion.version_no.desc())
        .all()
    )


def current_version(db: Session, quotation_id: str) -> ProjectQuotationVersion:
    """MAX(version_no). The single fact the whole model rests on (AC-E3a)."""
    version = (
        db.query(ProjectQuotationVersion)
        .filter(ProjectQuotationVersion.quotation_id == quotation_id)
        .order_by(ProjectQuotationVersion.version_no.desc())
        .first()
    )
    if not version:
        raise AppException(
            status_code=404,
            message="This quotation has no versions.",
            code="quotation_version_missing",
        )
    return version


def is_frozen(db: Session, version: ProjectQuotationVersion) -> bool:
    """Derived, never read from a column. Two ways a version stops being editable:

    1. A later version exists, so this one was superseded.
    2. An ISSUE points at it, so the customer already holds these rows.

    The second clause is what stops an issue rewriting itself. ``issue_scopes`` records the exact
    version each scope contributed to R1, but the highest-numbered version stays editable under
    the first clause alone - so editing a line after issuing would have changed the very rows R1
    claims to have contained, and the PDF on file would quietly stop matching the record behind it.

    Extended rather than replaced by a ``frozen`` column ON PURPOSE: this function is the single
    definition, and a stamped flag would be a second fact that has to agree with it. The model
    comment on ``ProjectQuotationVersion`` says why - two facts that must agree drift the first
    time a write half-fails, and then nobody can say which version the customer holds.
    """
    highest = (
        db.query(func.max(ProjectQuotationVersion.version_no))
        .filter(ProjectQuotationVersion.quotation_id == version.quotation_id)
        .scalar()
    )
    if highest is not None and version.version_no < highest:
        return True
    return is_issued(db, version)


def is_issued(db: Session, version: ProjectQuotationVersion) -> bool:
    """Whether any issue of the parent document went out carrying this version."""
    return (
        db.query(ProjectQuotationIssueScope.id)
        .filter(ProjectQuotationIssueScope.version_id == version.id)
        .first()
        is not None
    )


def assert_editable(db: Session, version: ProjectQuotationVersion) -> None:
    if not is_frozen(db, version):
        return
    # The two reasons read differently to a person: one says somebody moved on, the other says the
    # customer is holding this paper. "Superseded" on a version you just issued would be baffling.
    if is_issued(db, version):
        raise AppException(
            status_code=422,
            message=(
                f"Version {version.version_no} has been issued to the customer and cannot be "
                "changed. Open a revision instead."
            ),
            code="quotation_version_issued",
        )
    raise AppException(
        status_code=422,
        message=(
            f"Version {version.version_no} was superseded and cannot be changed. "
            "Edit the current version instead."
        ),
        code="quotation_version_frozen",
    )


def get_version_or_404(
    db: Session, quotation_id: str, version_id: str
) -> ProjectQuotationVersion:
    version = (
        db.query(ProjectQuotationVersion)
        .filter(
            ProjectQuotationVersion.id == version_id,
            ProjectQuotationVersion.quotation_id == quotation_id,
        )
        .first()
    )
    if not version:
        raise AppException(
            status_code=404,
            message="Quotation version not found.",
            code="quotation_version_not_found",
        )
    return version


# -------------------------------------------------------------------- create


def create_quotation(
    db: Session,
    *,
    project: Project,
    actor_user_id: str,
    payload: Dict[str, Any],
) -> ProjectQuotation:
    """A scope of the project, with version 1 opened immediately.

    Opened rather than deferred: a quotation with no version has nowhere to put a line,
    and every caller would have to remember to create one.
    """
    scope_label = " ".join((payload.get("scope_label") or "").split())
    if not scope_label:
        raise AppException(
            status_code=422,
            message="A quotation needs a scope, e.g. House Units or Common Area.",
            code="quotation_scope_required",
        )

    quotation = ProjectQuotation(
        company_id=project.company_id,
        project_id=project.id,
        scope_label=scope_label,
        series_id=payload.get("series_id"),
        notes=payload.get("notes"),
        outcome=OUTCOME_OPEN_Q,
        created_by=actor_user_id,
    )
    db.add(quotation)
    db.flush()

    db.add(
        ProjectQuotationVersion(
            company_id=project.company_id,
            quotation_id=quotation.id,
            version_no=1,
            issued_by=actor_user_id,
            total_amount=Decimal("0.00"),
        )
    )
    db.flush()

    from app.services import project_activity_service as activity

    activity.record_project_event(
        db,
        project=project,
        template="quotation_created",
        payload={"quotation_id": str(quotation.id), "scope_label": quotation.scope_label},
        actor_id=actor_user_id,
    )
    db.flush()
    return quotation


def update_quotation(
    db: Session, *, quotation: ProjectQuotation, payload: Dict[str, Any]
) -> ProjectQuotation:
    """Scope label, series and notes. Outcome has its own action, so it is not here:
    losing a quotation needs a reason and a decided-at stamp."""
    if "scope_label" in payload:
        scope_label = " ".join((payload.get("scope_label") or "").split())
        if not scope_label:
            raise AppException(
                status_code=422,
                message="A quotation needs a scope.",
                code="quotation_scope_required",
            )
        quotation.scope_label = scope_label
    if "series_id" in payload:
        quotation.series_id = payload["series_id"] or None
    if "notes" in payload:
        quotation.notes = payload["notes"]
    db.flush()
    return quotation


def revise(
    db: Session, *, quotation: ProjectQuotation, actor_user_id: str
) -> ProjectQuotationVersion:
    """Freeze the current version and open the next one, carrying the lines (AC-E3).

    Carrying the lines rather than starting blank: a revision is almost always "the same
    quotation with three prices moved", and re-keying forty lines is how people end up
    editing the frozen one in a spreadsheet instead.
    """
    live = current_version(db, quotation.id)
    live.frozen_at = datetime.utcnow()

    nxt = ProjectQuotationVersion(
        company_id=quotation.company_id,
        quotation_id=quotation.id,
        version_no=live.version_no + 1,
        issued_by=actor_user_id,
        total_amount=live.total_amount,
        notes=live.notes,
    )
    db.add(nxt)
    db.flush()

    for line in list_lines(db, live.id):
        db.add(
            ProjectQuotationLine(
                company_id=quotation.company_id,
                version_id=nxt.id,
                product_id=line.product_id,
                product_code_snapshot=line.product_code_snapshot,
                description_snapshot=line.description_snapshot,
                list_price_snapshot=line.list_price_snapshot,
                image_attachment_id=line.image_attachment_id,
                unit_price=line.unit_price,
                quantity=line.quantity,
                uom=line.uom,
                unit_type=line.unit_type,
                line_total=line.line_total,
                is_non_standard=line.is_non_standard,
                floor_value_applied=line.floor_value_applied,
                floor_level_applied=line.floor_level_applied,
                is_below_floor=line.is_below_floor,
                sort_order=line.sort_order,
                notes=line.notes,
            )
        )
    db.flush()
    _recalculate_total(db, nxt)

    project = db.query(Project).filter(Project.id == quotation.project_id).first()
    if project is not None:
        from app.services import project_activity_service as activity

        activity.record_project_event(
            db,
            project=project,
            template="quotation_revised",
            payload={
                "quotation_id": str(quotation.id),
                "version_no": nxt.version_no,
            },
            actor_id=actor_user_id,
        )
        db.flush()
    return nxt


def delete_quotation(db: Session, quotation: ProjectQuotation) -> None:
    """Hard delete, cascading to versions and lines. The project's derived outcome is
    recomputed, because removing the only lost scope reopens the project."""
    project = db.query(Project).filter(Project.id == quotation.project_id).first()
    db.delete(quotation)
    db.flush()
    if project:
        sync_project_outcome(db, project)


# ---------------------------------------------------------------------- lines


def list_lines(db: Session, version_id: str) -> List[ProjectQuotationLine]:
    return (
        db.query(ProjectQuotationLine)
        .filter(ProjectQuotationLine.version_id == version_id)
        .order_by(
            ProjectQuotationLine.sort_order.asc(), ProjectQuotationLine.created_at.asc()
        )
        .all()
    )


def _recalculate_total(db: Session, version: ProjectQuotationVersion) -> None:
    """The version's money, with rate-only lines EXCLUDED.

    A rate-only line keeps its `line_total` (the rate is what the customer is being shown), so
    summing the column blindly would make `total_amount` disagree with what the document footer
    and the PDF print. The sample quotation's five alternates would have added RM 235,075 that
    nobody quoted.
    """
    total = (
        db.query(func.coalesce(func.sum(ProjectQuotationLine.line_total), 0))
        .filter(
            ProjectQuotationLine.version_id == version.id,
            ProjectQuotationLine.is_rate_only.is_(False),
        )
        .scalar()
    )
    version.total_amount = Decimal(total or 0).quantize(_CENTS)
    db.flush()


def _snapshot_product(db: Session, line: ProjectQuotationLine, product: Product) -> None:
    """Freeze what the product looked like when it was quoted (AC-E4).

    A catalogue rename or re-price next month must not rewrite what the customer was
    sent, and a discontinued SKU must still print on last year's quotation.
    """
    line.product_code_snapshot = product.product_code
    line.description_snapshot = (
        line.description_snapshot or product.description or product.product_name
    )
    line.list_price_snapshot = product.list_price
    if line.uom is None:
        line.uom = _uom_code(db, product.base_uom_id)
    if line.image_attachment_id is None:
        line.image_attachment_id = resolve_product_image(db, product.id)


def _uom_code(db: Session, uom_id: Optional[str]) -> Optional[str]:
    if not uom_id:
        return None
    from app.models.product import UnitOfMeasure

    row = db.query(UnitOfMeasure.uom_code).filter(UnitOfMeasure.id == uom_id).first()
    return row[0] if row else None


def resolve_product_image(db: Session, product_id: str) -> Optional[str]:
    """The product's image attachment, lowest sort order (AC-E8).

    Driven by ``attachment_types.is_image_class`` rather than by a filename check or a
    hardcoded type name, so an admin adding a second image-ish type gets it for free.
    Returns None when the flag or the tables are not present, because a missing image is
    a cosmetic gap and must never fail a save.
    """
    try:
        from app.models.product import ProductAttachment
        from app.models.resources import AttachmentType

        row = (
            db.query(ProductAttachment.attachment_id)
            .join(
                AttachmentType,
                AttachmentType.id == ProductAttachment.attachment_type_id,
            )
            .filter(
                ProductAttachment.product_id == product_id,
                AttachmentType.is_image_class.is_(True),
            )
            .order_by(ProductAttachment.sort_order.asc().nullslast())
            .first()
        )
        return row[0] if row else None
    except Exception:  # noqa: BLE001 -- cosmetic, never fatal to a quotation save
        return None


def _apply_guardrails(
    db: Session,
    *,
    line: ProjectQuotationLine,
    quotation: ProjectQuotation,
    product: Optional[Product],
    covered_categories: Optional[Set[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Recompute both alerts for one line. Returns a breach event, or None.

    An event is returned ONLY on the transition into breach (AC-E6a): the previous state
    is read before the new one is written, and a line that was already breaching stays
    silent no matter how many times it is saved.
    """
    was_below = bool(line.is_below_floor)

    # Off-catalog is ALWAYS non-standard (AC-E5), series or no series: "we quoted
    # something that is not in our catalogue" is the case the alert exists for, and a
    # project that never nominated a series must not silently excuse it.
    line.is_non_standard = product is None or not pricing.is_in_series(
        db,
        series_id=quotation.series_id,
        product=product,
        covered=covered_categories,
    )

    floor = pricing.resolve_floor(
        db,
        company_id=quotation.company_id,
        product=product,
        list_price=line.list_price_snapshot,
    )
    if floor is None:
        line.floor_value_applied = None
        line.floor_level_applied = None
        line.is_below_floor = False
        return None

    line.floor_value_applied = floor.value
    line.floor_level_applied = floor.level
    line.is_below_floor = Decimal(line.unit_price or 0) < floor.value

    if line.is_below_floor and not was_below:
        return {
            "line_id": line.id,
            "quotation_id": quotation.id,
            "unit_price": Decimal(line.unit_price or 0),
            "floor_value": floor.value,
            "floor_level": floor.level,
            "product_code": line.product_code_snapshot,
        }
    return None


def pop_breach_events(line: ProjectQuotationLine) -> List[Dict[str, Any]]:
    """Read and clear the breach events smuggled onto the line by the last save.

    Popped rather than read so a caller cannot notify twice, and so the marker cannot
    survive into a later request.
    """
    events = list(getattr(line, _BREACH_ATTR, []) or [])
    try:
        setattr(line, _BREACH_ATTR, [])
    except Exception:  # noqa: BLE001 -- detached instance; nothing to clear
        pass
    return events


def upsert_line(
    db: Session,
    *,
    version: ProjectQuotationVersion,
    actor_user_id: str,
    payload: Dict[str, Any],
    line: Optional[ProjectQuotationLine] = None,
) -> ProjectQuotationLine:
    """Add or edit one line on the CURRENT version, in place (AC-E2).

    Both alerts are recomputed here rather than on read, so the values stored on the
    line are the ones that were true when it was priced (AC-E7).
    """
    assert_editable(db, version)

    quotation = (
        db.query(ProjectQuotation)
        .filter(ProjectQuotation.id == version.quotation_id)
        .first()
    )
    if not quotation:
        raise AppException(
            status_code=404, message="Quotation not found.", code="quotation_not_found"
        )

    unit_type = payload.get("unit_type")
    if unit_type and unit_type not in UNIT_TYPES:
        raise AppException(
            status_code=422,
            message=f"Unknown unit type '{unit_type}'.",
            code="quotation_unit_type_invalid",
        )

    if line is None:
        line = ProjectQuotationLine(
            company_id=quotation.company_id, version_id=version.id
        )
        db.add(line)

    for field in LINE_FIELDS:
        if field in payload:
            value = payload[field]
            # Coerced on the way in, so the in-session value matches what a re-read would give.
            # Left as the caller's string, `line.unit_price` stays a str until the session is
            # expired, and any Python arithmetic on it downstream breaks on a type nobody expected.
            if field in _NUMERIC_LINE_FIELDS and value is not None and not isinstance(value, Decimal):
                value = Decimal(str(value))
            setattr(line, field, value)

    if line.unit_price is None:
        line.unit_price = Decimal("0.00")
    if line.quantity is None:
        line.quantity = Decimal("1")

    product = (
        db.query(Product).filter(Product.id == line.product_id).first()
        if line.product_id
        else None
    )
    if product is not None:
        _snapshot_product(db, line, product)
    elif not line.description_snapshot:
        raise AppException(
            status_code=422,
            message=(
                "An off-catalog line needs a description -- it is what the customer "
                "reads, and there is no product to fall back on."
            ),
            code="quotation_line_description_required",
        )

    line.line_total = (
        Decimal(line.unit_price or 0) * Decimal(line.quantity or 0)
    ).quantize(_CENTS)

    db.flush()
    event = _apply_guardrails(db, line=line, quotation=quotation, product=product)
    setattr(line, _BREACH_ATTR, [event] if event else [])

    db.flush()
    _recalculate_total(db, version)
    return line


def delete_line(
    db: Session, *, version: ProjectQuotationVersion, line: ProjectQuotationLine
) -> None:
    assert_editable(db, version)
    db.delete(line)
    db.flush()
    _recalculate_total(db, version)


# ------------------------------------------------------------------- outcomes


def loss_reasons(db: Session) -> List[Dict[str, str]]:
    """Active options of the configurable loss-reason set (AC-E9)."""
    lookup_set = (
        db.query(LookupSet)
        .filter(LookupSet.set_key == QUOTATION_LOSS_REASON_SET_KEY)
        .first()
    )
    if not lookup_set:
        return []
    rows = (
        db.query(LookupOption)
        .filter(LookupOption.set_id == lookup_set.id, LookupOption.is_active.is_(True))
        .order_by(LookupOption.sort_order.asc(), LookupOption.label.asc())
        .all()
    )
    return [{"value": row.value, "label": row.label} for row in rows]


def _assert_loss_reason(db: Session, reason: Optional[str]) -> str:
    options = {row["value"] for row in loss_reasons(db)}
    if not options:
        raise AppException(
            status_code=422,
            message=(
                "No loss reasons are configured. Add options to the "
                f"'{QUOTATION_LOSS_REASON_SET_KEY}' lookup set first."
            ),
            code="quotation_loss_reasons_unconfigured",
        )
    if not reason:
        raise AppException(
            status_code=422,
            message="A lost quotation needs a reason -- it is the report management reads.",
            code="quotation_loss_reason_required",
        )
    if reason not in options:
        raise AppException(
            status_code=422,
            message=f"'{reason}' is not a configured loss reason.",
            code="quotation_loss_reason_invalid",
        )
    return reason


def set_outcome(
    db: Session,
    *,
    quotation: ProjectQuotation,
    outcome: str,
    loss_reason: Optional[str] = None,
) -> ProjectQuotation:
    """Win, lose or reopen ONE scope, then re-derive the project's outcome (AC-E10).

    The project's STATUS is deliberately untouched (AC-E10a): status is a funnel
    position and outcome is the commercial result, and a service that moved both would
    make the board disagree with the pipeline.
    """
    if outcome not in QUOTATION_OUTCOMES:
        raise AppException(
            status_code=422,
            message=f"Unknown outcome '{outcome}'.",
            code="quotation_outcome_invalid",
        )

    if outcome == OUTCOME_LOST_Q:
        quotation.loss_reason = _assert_loss_reason(db, loss_reason)
    else:
        quotation.loss_reason = None

    quotation.outcome = outcome
    quotation.decided_at = (
        datetime.utcnow() if outcome != OUTCOME_OPEN_Q else None
    )
    db.flush()

    project = db.query(Project).filter(Project.id == quotation.project_id).first()
    if project:
        sync_project_outcome(db, project)
    return quotation


def derive_project_outcome(db: Session, project: Project) -> str:
    """Won if ANY quotation is won; lost only when ALL are lost; otherwise open.

    No quotations at all is OPEN, not lost: nothing has been decided yet, and a project
    registered this morning is not a loss.
    """
    rows = (
        db.query(ProjectQuotation.outcome, func.count(ProjectQuotation.id))
        .filter(ProjectQuotation.project_id == project.id)
        .group_by(ProjectQuotation.outcome)
        .all()
    )
    counts = {row[0]: row[1] for row in rows}
    if counts.get(OUTCOME_WON_Q):
        return OUTCOME_WON
    total = sum(counts.values())
    if total and counts.get(OUTCOME_LOST_Q, 0) == total:
        return OUTCOME_LOST
    return OUTCOME_OPEN


def sync_project_outcome(db: Session, project: Project) -> str:
    """Write the derived outcome onto the project.

    Stored rather than computed on read because the pipeline list, the forecast and the
    board all filter on it, and a correlated subquery per row would be the N+1 that
    makes the board slow.
    """
    outcome = derive_project_outcome(db, project)
    if project.outcome != outcome:
        project.outcome = outcome
        db.flush()
    return outcome


# ----------------------------------------------------------------- serialize


def serialize_quotations(
    db: Session, quotations: Sequence[ProjectQuotation]
) -> List[Dict[str, Any]]:
    """Bulk, with the current version and alert counts folded in.

    Alert counts come from the CURRENT version only: a breach on a superseded version is
    history, and counting it would make a fixed quotation look permanently broken.
    """
    if not quotations:
        return []

    ids = [q.id for q in quotations]
    version_rows = (
        db.query(ProjectQuotationVersion)
        .filter(ProjectQuotationVersion.quotation_id.in_(ids))
        .all()
    )
    highest: Dict[str, ProjectQuotationVersion] = {}
    counts: Dict[str, int] = {}
    for row in version_rows:
        counts[row.quotation_id] = counts.get(row.quotation_id, 0) + 1
        current = highest.get(row.quotation_id)
        if current is None or row.version_no > current.version_no:
            highest[row.quotation_id] = row

    current_ids = [v.id for v in highest.values()]
    alert_rows = (
        db.query(
            ProjectQuotationLine.version_id,
            func.sum(func.cast(ProjectQuotationLine.is_below_floor, Integer)),
            func.sum(func.cast(ProjectQuotationLine.is_non_standard, Integer)),
            func.count(ProjectQuotationLine.id),
        )
        .filter(ProjectQuotationLine.version_id.in_(current_ids))
        .group_by(ProjectQuotationLine.version_id)
        .all()
        if current_ids
        else []
    )
    alerts = {
        row[0]: {
            "below_floor": int(row[1] or 0),
            "non_standard": int(row[2] or 0),
            "line_count": int(row[3] or 0),
        }
        for row in alert_rows
    }

    series_ids = {q.series_id for q in quotations if q.series_id}
    series_names: Dict[str, str] = {}
    if series_ids:
        from app.models.projects import ProjectSeries

        series_names = {
            row.id: row.name
            for row in db.query(ProjectSeries).filter(ProjectSeries.id.in_(series_ids)).all()
        }

    labels = {row["value"]: row["label"] for row in loss_reasons(db)}

    out: List[Dict[str, Any]] = []
    for quotation in quotations:
        version = highest.get(quotation.id)
        stats = alerts.get(version.id if version else "", {})
        out.append(
            {
                "id": quotation.id,
                "project_id": quotation.project_id,
                "scope_label": quotation.scope_label,
                "series_id": quotation.series_id,
                "series_name": series_names.get(quotation.series_id or ""),
                "notes": quotation.notes,
                "outcome": quotation.outcome,
                "loss_reason": quotation.loss_reason,
                "loss_reason_label": labels.get(quotation.loss_reason or ""),
                "decided_at": quotation.decided_at,
                "version_count": counts.get(quotation.id, 0),
                "current_version_id": version.id if version else None,
                "current_version_no": version.version_no if version else None,
                "current_total": version.total_amount if version else None,
                "below_floor_count": stats.get("below_floor", 0),
                "non_standard_count": stats.get("non_standard", 0),
                "line_count": stats.get("line_count", 0),
                "created_at": quotation.created_at,
                "updated_at": quotation.updated_at,
            }
        )
    return out


def serialize_versions(
    db: Session, versions: Sequence[ProjectQuotationVersion]
) -> List[Dict[str, Any]]:
    if not versions:
        return []
    highest_by_quotation: Dict[str, int] = {}
    for version in versions:
        highest_by_quotation[version.quotation_id] = max(
            highest_by_quotation.get(version.quotation_id, 0), version.version_no
        )
    # The set on screen may be one page of a longer history, so the real maximum has to
    # come from the DB rather than from what happens to be in this list.
    quotation_ids = list(highest_by_quotation)
    rows = (
        db.query(
            ProjectQuotationVersion.quotation_id,
            func.max(ProjectQuotationVersion.version_no),
        )
        .filter(ProjectQuotationVersion.quotation_id.in_(quotation_ids))
        .group_by(ProjectQuotationVersion.quotation_id)
        .all()
    )
    real_max = {row[0]: row[1] for row in rows}

    # Which of these versions has already gone out to a customer. Batched rather than asked per
    # row: the editor needs it for every version it renders, and `is_current` alone cannot answer
    # it - an issued version is still the HIGHEST version until somebody revises, so a screen
    # gated on `is_current` offers edits the server then refuses with 422.
    issued_ids = {
        row[0]
        for row in db.query(ProjectQuotationIssueScope.version_id)
        .filter(ProjectQuotationIssueScope.version_id.in_([v.id for v in versions]))
        .all()
    }

    issuer_ids = {v.issued_by for v in versions if v.issued_by}
    names: Dict[str, str] = {}
    if issuer_ids:
        from app.models.user import User

        names = {
            row.id: (row.name or row.email)
            for row in db.query(User).filter(User.id.in_(issuer_ids)).all()
        }

    return [
        {
            "id": version.id,
            "quotation_id": version.quotation_id,
            "version_no": version.version_no,
            "is_current": version.version_no == real_max.get(version.quotation_id),
            # Sent to the customer, so its rows are what they hold and cannot be rewritten.
            "is_issued": version.id in issued_ids,
            # The one flag the editor should gate on: superseded OR issued.
            "is_editable": (
                version.version_no == real_max.get(version.quotation_id)
                and version.id not in issued_ids
            ),
            "frozen_at": version.frozen_at,
            "issued_by": version.issued_by,
            "issued_by_name": names.get(version.issued_by or ""),
            "issued_on": version.issued_on,
            "total_amount": version.total_amount,
            "notes": version.notes,
            "created_at": version.created_at,
        }
        for version in versions
    ]


def serialize_lines(
    db: Session, lines: Sequence[ProjectQuotationLine]
) -> List[Dict[str, Any]]:
    return [
        {
            "id": line.id,
            "version_id": line.version_id,
            "product_id": line.product_id,
            "product_code": line.product_code_snapshot,
            "description": line.description_snapshot,
            "list_price": line.list_price_snapshot,
            "image_attachment_id": line.image_attachment_id,
            "unit_price": line.unit_price,
            "quantity": line.quantity,
            "uom": line.uom,
            "unit_type": line.unit_type,
            "line_total": line.line_total,
            "is_non_standard": line.is_non_standard,
            "floor_value_applied": line.floor_value_applied,
            "floor_level_applied": line.floor_level_applied,
            "is_below_floor": line.is_below_floor,
            "sort_order": line.sort_order,
            "notes": line.notes,
        }
        for line in lines
    ]
