"""NON-CANCELLABLE-ITEMS: which lines cannot be cancelled, and the one gate every cancel asks.

Plan: documentation/plans/project-sales/PLAN-non-cancellable-items-11nov.md.

The setting lives on the PROJECT SERIES (owner, 11 Nov 2026): a series marks whole categories
(a parent covers its children), a product row can say yes or no for its own model (model beats
category), and a set priced on the series can be marked. A line's answer is computed when the
line is saved and STORED on ``quotation_lines.is_non_cancellable``, like ``is_non_standard``:
changing the setting later never rewrites what a customer was quoted.

Every CRM path that cancels or reduces a CONFIRMED order line (amendment publish, the board's
Transfer to Cancel SO, removing a line from a won quotation) calls ``assert_may_reduce``. It
refuses with 409 ``non_cancellable_line`` unless the caller sends a reason AND holds
``projects.non_cancellable.override``; an override is written to the audit log, one EVENT row
per line. AutoCount owns cancels on its own side, so a cancel or qty cut it makes can only be
flagged after ingest: ``alert_autocount_reductions`` tells the override holders.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.projects import (
    ProjectSeriesCategory,
    ProjectSeriesProduct,
    ProjectSeriesSet,
    ProjectQuotationLine,
)
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

OVERRIDE_PERMISSION = "projects.non_cancellable.override"
AUDIT_EVENT = "non_cancellable_override"
ALERT_TYPE = "project_non_cancellable_reduced"

#: Owner-approved wording for the terms (card question b).
TERMS_SENTENCE = (
    "Items marked Non-cancellable are ordered specially for this project and cannot be "
    "cancelled or reduced once the order is confirmed."
)
#: The note printed under a line's description, on screen and in the PDF.
LINE_NOTE = "Non-cancellable"


# --------------------------------------------------------------------- the setting


@dataclass(frozen=True)
class SeriesNonCancellable:
    """One series' setting, read once and reused across a whole version's lines."""

    categories: Set[str] = field(default_factory=set)
    #: product id -> True / False (the model's own answer; absent = follow the category).
    products: Dict[str, bool] = field(default_factory=dict)
    sets: Set[str] = field(default_factory=set)

    @property
    def empty(self) -> bool:
        return not (self.categories or self.products or self.sets)


def series_setting(db: Session, series_id: Optional[str]) -> SeriesNonCancellable:
    if not series_id:
        return SeriesNonCancellable()
    categories = {
        str(cid)
        for (cid,) in db.query(ProjectSeriesCategory.category_id).filter(
            ProjectSeriesCategory.series_id == str(series_id),
            ProjectSeriesCategory.non_cancellable.is_(True),
        )
    }
    products = {
        str(pid): bool(flag)
        for pid, flag in db.query(
            ProjectSeriesProduct.product_id, ProjectSeriesProduct.non_cancellable
        ).filter(
            ProjectSeriesProduct.series_id == str(series_id),
            ProjectSeriesProduct.non_cancellable.isnot(None),
        )
    }
    sets = {
        str(sid)
        for (sid,) in db.query(ProjectSeriesSet.product_set_id).filter(
            ProjectSeriesSet.series_id == str(series_id),
            ProjectSeriesSet.non_cancellable.is_(True),
        )
    }
    return SeriesNonCancellable(categories=categories, products=products, sets=sets)


def product_is_non_cancellable(
    db: Session,
    *,
    product_id: Optional[str],
    category_id: Optional[str],
    setting: SeriesNonCancellable,
) -> bool:
    """Model beats category: the product row's own answer, else any marked ancestor category."""
    if not product_id or setting.empty:
        return False
    own = setting.products.get(str(product_id))
    if own is not None:
        return own
    if not setting.categories or not category_id:
        return False
    from app.services.project_pricing_service import category_ancestry

    return any(cid in setting.categories for cid in category_ancestry(db, str(category_id)))


def set_is_non_cancellable(
    db: Session,
    *,
    product_set_id: str,
    parts_snapshot: Optional[Sequence[Dict[str, Any]]],
    setting: SeriesNonCancellable,
) -> bool:
    """A set is non-cancellable when the series marks the set, or ANY part is non-cancellable
    by the product rules (a vanity combo holding a bathtub is still a bathtub)."""
    if setting.empty:
        return False
    if str(product_set_id) in setting.sets:
        return True
    part_ids = [str(p.get("product_id")) for p in (parts_snapshot or []) if p.get("product_id")]
    if not part_ids:
        return False
    categories = dict(
        db.query(Product.id, Product.category_id).filter(Product.id.in_(part_ids)).all()
    )
    return any(
        product_is_non_cancellable(
            db, product_id=pid, category_id=categories.get(pid), setting=setting
        )
        for pid in part_ids
    )


def apply_to_line(
    db: Session,
    *,
    line: ProjectQuotationLine,
    series_id: Optional[str],
    product: Optional[Product],
    setting: Optional[SeriesNonCancellable] = None,
) -> None:
    """Compute and store ``line.is_non_cancellable`` on save (the line's own guardrail pass)."""
    if line.is_section:
        line.is_non_cancellable = False
        return
    resolved = setting if setting is not None else series_setting(db, series_id)
    if line.product_set_id:
        line.is_non_cancellable = set_is_non_cancellable(
            db,
            product_set_id=line.product_set_id,
            parts_snapshot=line.set_parts_snapshot,
            setting=resolved,
        )
        return
    line.is_non_cancellable = product_is_non_cancellable(
        db,
        product_id=product.id if product is not None else line.product_id,
        category_id=product.category_id if product is not None else None,
        setting=resolved,
    )


# ------------------------------------------------------------------ the quotation


def versions_have_non_cancellable(db: Session, version_ids: Iterable[str]) -> bool:
    ids = [str(v) for v in version_ids if v]
    if not ids:
        return False
    return (
        db.query(ProjectQuotationLine.id)
        .filter(
            ProjectQuotationLine.version_id.in_(ids),
            ProjectQuotationLine.is_non_cancellable.is_(True),
        )
        .first()
        is not None
    )


def with_terms_sentence(terms_html: Optional[str], needed: bool) -> Optional[str]:
    """The terms with the non-cancellable sentence added once at the end, when a line needs it.

    Idempotent: terms that already carry the sentence (typed by hand, or a re-issue of terms
    copied from an earlier revision) are returned unchanged.
    """
    if not needed:
        return terms_html
    text = terms_html or ""
    if TERMS_SENTENCE in text:
        return terms_html
    return f"{text}<p>{TERMS_SENTENCE}</p>"


# --------------------------------------------------------------------- the gate


@dataclass(frozen=True)
class Reduction:
    """One line a CRM action would cancel or reduce, as a person reads it."""

    label: str
    entity_type: str
    entity_id: str
    from_qty: Optional[str] = None
    to_qty: Optional[str] = None


def so_lines_non_cancellable(db: Session, so_lines: Iterable[Any]) -> Set[str]:
    """The ids of the given SO lines whose quotation line is non-cancellable.

    A set's component lines all point at the set's ONE quotation line, so they share its flag.
    A line with no quotation line (adopted from AutoCount, added outside the quotation) has no
    series answer and is not protected.
    """
    by_quote: Dict[str, List[str]] = {}
    for line in so_lines:
        qid = getattr(line, "quotation_line_id", None)
        if qid:
            by_quote.setdefault(str(qid), []).append(str(line.id))
    if not by_quote:
        return set()
    flagged = {
        str(qid)
        for (qid,) in db.query(ProjectQuotationLine.id).filter(
            ProjectQuotationLine.id.in_(list(by_quote)),
            ProjectQuotationLine.is_non_cancellable.is_(True),
        )
    }
    return {so_id for qid in flagged for so_id in by_quote[qid]}


def _refusal(reductions: Sequence[Reduction], *, can_override: bool) -> AppException:
    names = ", ".join(r.label for r in reductions[:5])
    more = f" and {len(reductions) - 5} more" if len(reductions) > 5 else ""
    tail = (
        "Give a reason to override."
        if can_override
        else "A sales manager can override it with a reason."
    )
    return AppException(
        status_code=409,
        message=f"Non-cancellable: {names}{more} cannot be cancelled or reduced. {tail}",
        code="non_cancellable_line",
        details={
            "can_override": can_override,
            "lines": [
                {"label": r.label, "from_qty": r.from_qty, "to_qty": r.to_qty}
                for r in reductions
            ],
        },
    )


def can_override(db: Session, user_id: Optional[str]) -> bool:
    if not user_id:
        return False
    from app.api.v1.projects._common import permission_slugs

    return OVERRIDE_PERMISSION in permission_slugs(db, str(user_id))


def assert_may_reduce(
    db: Session,
    *,
    reductions: Sequence[Reduction],
    user_id: Optional[str],
    override_reason: Optional[str],
    action: str,
    company_id: Optional[str] = None,
) -> None:
    """Refuse (409) unless nothing is non-cancellable, or an override holder gave a reason.

    ``reductions`` holds only the NON-CANCELLABLE lines the action would cut; the caller
    filters. An empty list passes silently, so an order with no such line is untouched.
    """
    if not reductions:
        return
    reason = (override_reason or "").strip()
    allowed = can_override(db, user_id)
    if not reason or not allowed:
        if reason and not allowed:
            raise AppException(
                status_code=403,
                message=(
                    "Only a sales manager can override a Non-cancellable line. Ask one to "
                    "do it."
                ),
                code="non_cancellable_override_forbidden",
            )
        raise _refusal(reductions, can_override=allowed)
    from app.services import audit_service

    for r in reductions:
        audit_service.record(
            db,
            event=AUDIT_EVENT,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            reason=reason,
            new_values={
                "action": action,
                "line": r.label,
                "from_qty": r.from_qty,
                "to_qty": r.to_qty,
            },
            description=f"Non-cancellable override ({action}): {r.label}",
            company_id=company_id,
        )


# --------------------------------------------------------------- AutoCount alert


def _qty(value: Any) -> str:
    try:
        return format(Decimal(str(value)).normalize(), "f")
    except Exception:  # noqa: BLE001
        return str(value)


def alert_autocount_reductions(
    db: Session, moves: Iterable[Tuple[str, Any, Any]], *, source: str
) -> int:
    """AutoCount cancelled or cut a non-cancellable line: tell the override holders.

    ``moves`` are ``(core sales_order_line id, qty before, qty after)``. Best effort: the
    ingest already committed the fact, so a notification failure only logs. Returns how many
    lines were alerted. One notification per line and quantity, deduped, so a re-run of the
    same ingest stays quiet.
    """
    from app.models.project_so import ProjectSalesOrder, ProjectSalesOrderLine

    cuts: Dict[str, Tuple[Any, Any]] = {}
    for core_id, before, after in moves:
        try:
            if Decimal(str(after)) >= Decimal(str(before)):
                continue
        except Exception:  # noqa: BLE001
            continue
        cuts[str(core_id)] = (before, after)
    if not cuts:
        return 0
    try:
        mirrors = (
            db.query(ProjectSalesOrderLine)
            .filter(ProjectSalesOrderLine.core_sales_order_line_id.in_(list(cuts)))
            .all()
        )
        flagged = so_lines_non_cancellable(db, mirrors)
        mirrors = [m for m in mirrors if str(m.id) in flagged]
        if not mirrors:
            return 0
        from app.services.project_notify_service import approver_user_ids

        alerted = 0
        for mirror in mirrors:
            order = (
                db.query(ProjectSalesOrder)
                .filter(ProjectSalesOrder.id == mirror.project_sales_order_id)
                .first()
            )
            if order is None:
                continue
            before, after = cuts[str(mirror.core_sales_order_line_id)]
            code = (
                db.query(Product.product_code).filter(Product.id == mirror.product_id).scalar()
                if mirror.product_id
                else None
            )
            doc = order.autocount_doc_no or order.provisional_ref
            what = "cancelled" if Decimal(str(after)) <= 0 else "reduced"
            title = f"Non-cancellable item {what} in AutoCount: {doc}"
            body = (
                f"{doc} line {mirror.line_no} {code or mirror.description or ''}".strip()
                + f" went from {_qty(before)} to {_qty(after)} in AutoCount ({source}). "
                "This item is Non-cancellable: check with the customer before it is "
                "released."
            )
            _notify(
                db,
                user_ids=approver_user_ids(db, order.company_id, slug=OVERRIDE_PERMISSION),
                title=title,
                body=body,
                data={
                    "project_sales_order_id": str(order.id),
                    "so_line_id": str(mirror.id),
                    "so_number": doc,
                    "item_code": code,
                    "from_qty": _qty(before),
                    "to_qty": _qty(after),
                    "source": source,
                    "link": f"/project-sales/fulfilment-planning?orders={doc}",
                },
                source_id=str(order.id),
                dedup_key=f"{mirror.id}:non_cancellable:{_qty(after)}",
            )
            alerted += 1
        return alerted
    except Exception as exc:  # noqa: BLE001 - the ingest already committed
        logger.warning("non_cancellable.alert_failed error=%s", exc)
        return 0


def _notify(
    db: Session,
    *,
    user_ids: List[str],
    title: str,
    body: str,
    data: Dict[str, Any],
    source_id: str,
    dedup_key: str,
) -> int:
    from app.services.notification_service import NotificationService

    service = NotificationService(db)
    sent = 0
    for user_id in {u for u in user_ids if u}:
        try:
            service.create_with_channel_preferences(
                user_id=str(user_id),
                type=ALERT_TYPE,
                title=title,
                body=body,
                data=data,
                source_entity_type="project_sales_order",
                source_entity_id=source_id,
                dedup_key=dedup_key,
                event_type=ALERT_TYPE,
                send_in_app=True,
                send_email=True,
            )
            sent += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("non_cancellable.alert_recipient_failed user=%s error=%s", user_id, exc)
    return sent


__all__ = [
    "ALERT_TYPE",
    "AUDIT_EVENT",
    "LINE_NOTE",
    "OVERRIDE_PERMISSION",
    "Reduction",
    "SeriesNonCancellable",
    "TERMS_SENTENCE",
    "alert_autocount_reductions",
    "apply_to_line",
    "assert_may_reduce",
    "can_override",
    "product_is_non_cancellable",
    "series_setting",
    "set_is_non_cancellable",
    "so_lines_non_cancellable",
    "versions_have_non_cancellable",
    "with_terms_sentence",
]
