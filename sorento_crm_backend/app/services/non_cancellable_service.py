"""NON-CANCELLABLE-ITEMS: which lines cannot be cancelled, and the one gate every cancel asks.

Plan: documentation/plans/project-sales/PLAN-non-cancellable-items-11nov.md.

The setting lives on the PROJECT SERIES (owner, 11 Nov 2026): a series marks whole categories
(a parent covers its children), a product row can say yes or no for its own model (model beats
category), and a set priced on the series can be marked. A company-wide default by product or
category (``NonCancellableRule``, owner answer (a)) covers what the series says nothing about.
Precedence, first answer wins: series product row, series category, company product rule,
company category rule (nearest ancestor). A line's answer is computed when the
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
    NonCancellableRule,
)
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

OVERRIDE_PERMISSION = "projects.non_cancellable.override"
AUDIT_EVENT = "non_cancellable_override"
ALERT_TYPE = "project_non_cancellable_reduced"



# --------------------------------------------------------------------- the setting


@dataclass(frozen=True)
class SeriesNonCancellable:
    """One series' setting, read once and reused across a whole version's lines."""

    categories: Set[str] = field(default_factory=set)
    #: product id -> True / False (the model's own answer; absent = follow the category).
    products: Dict[str, bool] = field(default_factory=dict)
    sets: Set[str] = field(default_factory=set)
    #: The company default: product id -> answer, category id -> answer.
    company_products: Dict[str, bool] = field(default_factory=dict)
    company_categories: Dict[str, bool] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not (
            self.categories
            or self.products
            or self.sets
            or self.company_products
            or self.company_categories
        )


def series_setting(
    db: Session, series_id: Optional[str], company_id: Optional[str] = None
) -> SeriesNonCancellable:
    """The series' setting plus the company default, read once for a whole version."""
    company_products: Dict[str, bool] = {}
    company_categories: Dict[str, bool] = {}
    if company_id:
        for rule in db.query(NonCancellableRule).filter(
            NonCancellableRule.company_id == str(company_id)
        ):
            if rule.product_id:
                company_products[str(rule.product_id)] = bool(rule.non_cancellable)
            elif rule.category_id:
                company_categories[str(rule.category_id)] = bool(rule.non_cancellable)
    if not series_id:
        return SeriesNonCancellable(
            company_products=company_products, company_categories=company_categories
        )
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
    return SeriesNonCancellable(
        categories=categories,
        products=products,
        sets=sets,
        company_products=company_products,
        company_categories=company_categories,
    )


def product_is_non_cancellable(
    db: Session,
    *,
    product_id: Optional[str],
    category_id: Optional[str],
    setting: SeriesNonCancellable,
) -> bool:
    """Series before company default; within each, model beats category."""
    if not product_id or setting.empty:
        return False
    own = setting.products.get(str(product_id))
    if own is not None:
        return own
    ancestry: List[str] = []
    if category_id and (setting.categories or setting.company_categories):
        from app.services.project_pricing_service import category_ancestry

        ancestry = category_ancestry(db, str(category_id))
    if any(cid in setting.categories for cid in ancestry):
        return True
    company_own = setting.company_products.get(str(product_id))
    if company_own is not None:
        return company_own
    for cid in ancestry:  # nearest first
        if cid in setting.company_categories:
            return setting.company_categories[cid]
    return False


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
    resolved = (
        setting
        if setting is not None
        else series_setting(db, series_id, getattr(line, "company_id", None))
    )
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


# ------------------------------------------------------------- writing the setting


def set_series_categories(db: Session, *, series: Any, category_ids: Sequence[str]) -> None:
    """Mark exactly these of the series' nominated categories Non-cancellable (sent whole)."""
    wanted = {str(c) for c in category_ids if c}
    rows = (
        db.query(ProjectSeriesCategory)
        .filter(ProjectSeriesCategory.series_id == str(series.id))
        .all()
    )
    nominated = {str(row.category_id) for row in rows}
    stray = wanted - nominated
    if stray:
        raise AppException(
            status_code=422,
            message="Only a category of this series can be marked Non-cancellable.",
            code="series_non_cancellable_category_invalid",
        )
    for row in rows:
        flag = str(row.category_id) in wanted
        if bool(row.non_cancellable) != flag:
            row.non_cancellable = flag
    db.flush()


def non_cancellable_category_ids(db: Session, series_ids: Sequence[str]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    if not series_ids:
        return out
    for series_id, category_id in db.query(
        ProjectSeriesCategory.series_id, ProjectSeriesCategory.category_id
    ).filter(
        ProjectSeriesCategory.series_id.in_([str(i) for i in series_ids]),
        ProjectSeriesCategory.non_cancellable.is_(True),
    ):
        out.setdefault(str(series_id), []).append(str(category_id))
    return out


def set_series_product(
    db: Session, *, series: Any, product_id: str, non_cancellable: Optional[bool]
) -> None:
    """A product row's own answer. A product the series lists by scope gets its row here."""
    from app.services.project_pricing_service import product_in_series_scope

    link = (
        db.query(ProjectSeriesProduct)
        .filter(
            ProjectSeriesProduct.series_id == str(series.id),
            ProjectSeriesProduct.product_id == str(product_id),
        )
        .first()
    )
    if link is None or link.excluded:
        if link is None and not product_in_series_scope(db, series, str(product_id)):
            raise AppException(
                status_code=404,
                message="That product is not in this series.",
                code="series_product_not_found",
            )
        if link is not None and link.excluded:
            raise AppException(
                status_code=404,
                message="That product was removed from this series.",
                code="series_product_not_found",
            )
        link = ProjectSeriesProduct(series_id=str(series.id), product_id=str(product_id))
        db.add(link)
    link.non_cancellable = non_cancellable
    db.flush()


def set_series_set(db: Session, *, series: Any, product_set_id: str, non_cancellable: bool) -> None:
    link = (
        db.query(ProjectSeriesSet)
        .filter(
            ProjectSeriesSet.series_id == str(series.id),
            ProjectSeriesSet.product_set_id == str(product_set_id),
        )
        .first()
    )
    if link is None:
        raise AppException(
            status_code=404,
            message="That set is not on this series.",
            code="series_set_not_found",
        )
    link.non_cancellable = bool(non_cancellable)
    db.flush()


def effective_for_products(
    db: Session, *, series_id: str, company_id: Optional[str], product_ids: Sequence[str]
) -> Dict[str, bool]:
    """Each product's answer on this series, every level applied (the series table column)."""
    ids = [str(p) for p in product_ids if p]
    if not ids:
        return {}
    setting = series_setting(db, series_id, company_id)
    categories = dict(db.query(Product.id, Product.category_id).filter(Product.id.in_(ids)).all())
    return {
        pid: product_is_non_cancellable(
            db, product_id=pid, category_id=categories.get(pid), setting=setting
        )
        for pid in ids
    }


# --------------------------------------------------------------- company default


def serialize_rules(db: Session, rules: Sequence[NonCancellableRule]) -> List[Dict[str, Any]]:
    from app.models.product import ProductCategory

    product_ids = [r.product_id for r in rules if r.product_id]
    category_ids = [r.category_id for r in rules if r.category_id]
    products = (
        {
            str(pid): (code, name)
            for pid, code, name in db.query(
                Product.id, Product.product_code, Product.product_name
            ).filter(Product.id.in_(product_ids))
        }
        if product_ids
        else {}
    )
    categories = (
        {
            str(cid): name
            for cid, name in db.query(ProductCategory.id, ProductCategory.category_name).filter(
                ProductCategory.id.in_(category_ids)
            )
        }
        if category_ids
        else {}
    )
    out = []
    for r in rules:
        code, name = products.get(str(r.product_id), (None, None)) if r.product_id else (None, None)
        out.append(
            {
                "id": str(r.id),
                "product_id": str(r.product_id) if r.product_id else None,
                "product_code": code,
                "product_name": name,
                "category_id": str(r.category_id) if r.category_id else None,
                "category_name": categories.get(str(r.category_id)) if r.category_id else None,
                "non_cancellable": bool(r.non_cancellable),
                "notes": r.notes,
                "updated_at": r.updated_at,
            }
        )
    return out


def list_rules(db: Session, *, company_id: str) -> List[NonCancellableRule]:
    return (
        db.query(NonCancellableRule)
        .filter(NonCancellableRule.company_id == str(company_id))
        .order_by(NonCancellableRule.created_at.asc(), NonCancellableRule.id.asc())
        .all()
    )


def rule_or_404(db: Session, rule_id: str, *, company_id: str) -> NonCancellableRule:
    rule = (
        db.query(NonCancellableRule)
        .filter(
            NonCancellableRule.id == str(rule_id),
            NonCancellableRule.company_id == str(company_id),
        )
        .first()
    )
    if rule is None:
        raise AppException(
            status_code=404,
            message="Non-cancellable rule not found.",
            code="non_cancellable_rule_not_found",
        )
    return rule


def create_rule(
    db: Session, *, company_id: str, payload: Dict[str, Any], actor_user_id: Optional[str]
) -> NonCancellableRule:
    from app.models.product import ProductCategory

    product_id = (payload.get("product_id") or "").strip() or None
    category_id = (payload.get("category_id") or "").strip() or None
    if bool(product_id) == bool(category_id):
        raise AppException(
            status_code=422,
            message="Pick one product or one category.",
            code="non_cancellable_rule_target",
        )
    model, target = (Product, product_id) if product_id else (ProductCategory, category_id)
    found = (
        db.query(model.id)
        .filter(model.id == target, model.company_id == str(company_id))
        .first()
    )
    if found is None:
        raise AppException(
            status_code=422,
            message="That product or category is not in this company.",
            code="non_cancellable_rule_target",
        )
    exists = (
        db.query(NonCancellableRule.id)
        .filter(
            NonCancellableRule.company_id == str(company_id),
            NonCancellableRule.product_id == product_id
            if product_id
            else NonCancellableRule.product_id.is_(None),
            NonCancellableRule.category_id == category_id
            if category_id
            else NonCancellableRule.category_id.is_(None),
        )
        .first()
    )
    if exists is not None:
        raise AppException(
            status_code=409,
            message="That item already has a Non-cancellable rule. Edit it instead.",
            code="non_cancellable_rule_exists",
        )
    rule = NonCancellableRule(
        company_id=str(company_id),
        product_id=product_id,
        category_id=category_id,
        non_cancellable=bool(payload.get("non_cancellable", True)),
        notes=(payload.get("notes") or None),
        created_by=str(actor_user_id) if actor_user_id else None,
    )
    db.add(rule)
    db.flush()
    return rule


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


def confirmed_quotation_line_ids(db: Session, line_ids: Iterable[str]) -> Set[str]:
    """The quotation lines a published (confirmed) project SO already consumes."""
    from app.models.project_so import ProjectSalesOrder, ProjectSalesOrderLine

    ids = [str(i) for i in line_ids if i]
    if not ids:
        return set()
    return {
        str(qid)
        for (qid,) in db.query(ProjectSalesOrderLine.quotation_line_id)
        .join(
            ProjectSalesOrder,
            ProjectSalesOrder.id == ProjectSalesOrderLine.project_sales_order_id,
        )
        .filter(
            ProjectSalesOrderLine.quotation_line_id.in_(ids),
            ProjectSalesOrder.published_at.isnot(None),
        )
        .distinct()
    }


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
                {"label": r.label, "from_qty": _qty_or_none(r.from_qty), "to_qty": _qty_or_none(r.to_qty)}
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
                "from_qty": _qty_or_none(r.from_qty),
                "to_qty": _qty_or_none(r.to_qty),
            },
            description=f"Non-cancellable override ({action}): {r.label}",
            company_id=company_id,
        )


# --------------------------------------------------------------- AutoCount alert


def _qty_or_none(value: Any) -> Optional[str]:
    """"53.00" and "53" read the same on screen: "53"."""
    return None if value is None else _qty(value)


def _qty(value: Any) -> str:
    try:
        return format(Decimal(str(value)).normalize(), "f")
    except Exception:  # noqa: BLE001
        return str(value)


def alert_autocount_reductions(
    db: Session, moves: Iterable[Tuple[str, Any, Any]], *, source: str
) -> int:
    """AutoCount cancelled or cut a non-cancellable line: tell the override holders.

    ``moves`` are ``(core sales_order_line id, qty before, qty after)``. Returns how many lines
    were queued. The notifications are SENT only after ``db`` commits, on their own session:
    the notification service commits as it writes, and a caller still mid-transaction (the
    planning-change build) must neither be committed early nor lose its work to a rollback
    there. A rolled-back caller sends nothing. One notification per line and quantity,
    deduped, so a re-run of the same ingest stays quiet. Best effort throughout.
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

        queued = 0
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
            _queue_alert(
                db,
                {
                    "user_ids": approver_user_ids(
                        db, order.company_id, slug=OVERRIDE_PERMISSION
                    ),
                    "title": f"Non-cancellable item {what} in AutoCount: {doc}",
                    "body": (
                        f"{doc} line {mirror.line_no} {code or mirror.description or ''}".strip()
                        + f" went from {_qty(before)} to {_qty(after)} in AutoCount ({source}). "
                        "This item is Non-cancellable: check with the customer before it is "
                        "released."
                    ),
                    "data": {
                        "project_sales_order_id": str(order.id),
                        "so_line_id": str(mirror.id),
                        "so_number": doc,
                        "item_code": code,
                        "from_qty": _qty(before),
                        "to_qty": _qty(after),
                        "source": source,
                        "link": f"/project-sales/fulfilment-planning?orders={doc}",
                    },
                    "source_id": str(order.id),
                    "dedup_key": f"{mirror.id}:non_cancellable:{_qty(after)}",
                },
            )
            queued += 1
        return queued
    except Exception as exc:  # noqa: BLE001 - an alert never fails the ingest
        logger.warning("non_cancellable.alert_failed error=%s", exc)
        return 0


_ALERTS_KEY = "non_cancellable_alerts"


def _queue_alert(db: Session, spec: Dict[str, Any]) -> None:
    from sqlalchemy import event

    pending = db.info.setdefault(_ALERTS_KEY, [])
    if not pending:
        event.listen(db, "after_commit", _send_queued, once=True)
        event.listen(db, "after_soft_rollback", _drop_queued, once=True)
    pending.append(spec)


def _drop_queued(session: Session, _previous_transaction: Any) -> None:
    session.info.pop(_ALERTS_KEY, None)
    from sqlalchemy import event

    if event.contains(session, "after_commit", _send_queued):
        event.remove(session, "after_commit", _send_queued)


def _send_queued(session: Session) -> None:
    from sqlalchemy import event

    if event.contains(session, "after_soft_rollback", _drop_queued):
        event.remove(session, "after_soft_rollback", _drop_queued)
    specs = session.info.pop(_ALERTS_KEY, None) or []
    if not specs:
        return
    from app.database import SessionLocal

    own = SessionLocal()
    try:
        for spec in specs:
            _notify(own, **spec)
        own.commit()
    except Exception as exc:  # noqa: BLE001 - the caller already committed its fact
        own.rollback()
        logger.warning("non_cancellable.alert_send_failed error=%s", exc)
    finally:
        own.close()


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
            if not db.is_active:
                db.rollback()
    return sent


__all__ = [
    "ALERT_TYPE",
    "AUDIT_EVENT",
    "OVERRIDE_PERMISSION",
    "Reduction",
    "SeriesNonCancellable",
    "alert_autocount_reductions",
    "apply_to_line",
    "assert_may_reduce",
    "can_override",
    "product_is_non_cancellable",
    "series_setting",
    "confirmed_quotation_line_ids",
    "create_rule",
    "effective_for_products",
    "list_rules",
    "non_cancellable_category_ids",
    "rule_or_404",
    "serialize_rules",
    "set_is_non_cancellable",
    "set_series_categories",
    "set_series_product",
    "set_series_set",
    "so_lines_non_cancellable",
]
