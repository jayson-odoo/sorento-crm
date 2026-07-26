"""Price floors and series membership: the two guardrails on a quotation line.

Both are deterministic lookups over configuration, kept out of the quotation service
so they can be specified as a golden set (``tests/test_project_price_floor.py``) and
reused by anything else that needs to ask "is this price allowed" -- a PO check in S4
will want the same answer.

The floor resolves by SPECIFICITY: product > its category > that category's ancestors,
nearest first > system. The level is implied by which key the rule carries, never
stored, so there is one source of truth for it.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Set

from sqlalchemy.orm import Session

from app.models.product import Product, ProductCategory
from app.models.projects import (
    FLOOR_MODE_ABSOLUTE,
    FLOOR_MODE_PERCENT,
    FLOOR_MODES,
    PriceFloorRule,
    ProjectSeries,
    ProjectSeriesCategory,
)
from app.services.error_handler import AppException

LEVEL_PRODUCT = "product"
LEVEL_CATEGORY = "category"
LEVEL_CATEGORY_ANCESTOR = "category_ancestor"
LEVEL_SYSTEM = "system"

_CENTS = Decimal("0.01")
# Depth guard for the category walk. A cycle in parent_category_id would otherwise spin
# forever; the real hierarchy is three deep.
_MAX_CATEGORY_DEPTH = 20


@dataclass(frozen=True)
class ResolvedFloor:
    """The floor in force for one line, and where it came from.

    ``level`` and ``category_id`` are carried so the UI can explain a breach ("below
    the Basins floor of RM 850") instead of stating a bare number the salesperson
    cannot argue with or learn from.
    """

    value: Decimal
    mode: str
    level: str
    rule_id: str
    category_id: Optional[str] = None


# --------------------------------------------------------------- category walk


def category_ancestry(db: Session, category_id: Optional[str]) -> List[str]:
    """``[self, parent, grandparent, ...]``, nearest first.

    Nearest-first is the whole point: the order of this list IS the precedence order
    for the ancestor levels, so the resolver never has to compute depth.
    """
    if not category_id:
        return []

    chain: List[str] = []
    seen: Set[str] = set()
    current: Optional[str] = category_id
    while current and current not in seen and len(chain) < _MAX_CATEGORY_DEPTH:
        chain.append(current)
        seen.add(current)
        row = (
            db.query(ProductCategory.parent_category_id)
            .filter(ProductCategory.id == current)
            .first()
        )
        current = row[0] if row else None
    return chain


def category_with_descendants(db: Session, category_ids: Sequence[str]) -> Set[str]:
    """Expand nominated categories DOWNWARD (AC-E5).

    Nominating "Sanitary Ware" into a series covers every basin and pan under it, which
    is what makes a series a short list of groups rather than a list of every SKU that
    goes stale the week after it is written.
    """
    frontier = {cid for cid in category_ids if cid}
    if not frontier:
        return set()

    covered: Set[str] = set(frontier)
    depth = 0
    while frontier and depth < _MAX_CATEGORY_DEPTH:
        rows = (
            db.query(ProductCategory.id)
            .filter(ProductCategory.parent_category_id.in_(frontier))
            .all()
        )
        children = {row[0] for row in rows} - covered
        covered |= children
        frontier = children
        depth += 1
    return covered


# ------------------------------------------------------------ floor resolution


def _floor_from_rule(rule: PriceFloorRule, list_price: Optional[Decimal]) -> Optional[Decimal]:
    if rule.mode == FLOOR_MODE_ABSOLUTE:
        return Decimal(rule.value).quantize(_CENTS)
    # Percent needs a base. A missing or zero list price yields NO floor rather than
    # zero: zero would mark the line compliant, which reads as "checked and fine".
    if not list_price or Decimal(list_price) <= 0:
        return None
    return (Decimal(list_price) * Decimal(rule.value) / Decimal(100)).quantize(_CENTS)


def resolve_floor(
    db: Session,
    *,
    company_id: str,
    product: Optional[Product],
    list_price: Optional[Decimal] = None,
) -> Optional[ResolvedFloor]:
    """The floor for one line, or None when no policy reaches it.

    None is a real answer and not an error: most installs start with no rules at all,
    and inventing a floor of zero would flag nothing while looking like it had checked.

    An off-catalog line (``product is None``) has no list price and no category, so
    there is nothing to resolve against. It is caught by the non-standard SKU alert
    instead (AC-E5).
    """
    if product is None:
        return None

    effective_list = list_price if list_price is not None else product.list_price
    rules = (
        db.query(PriceFloorRule)
        .filter(
            PriceFloorRule.company_id == company_id,
            PriceFloorRule.is_active.is_(True),
        )
        .all()
    )
    if not rules:
        return None

    by_product = {r.product_id: r for r in rules if r.product_id}
    by_category = {r.category_id: r for r in rules if r.category_id and not r.product_id}
    system = next((r for r in rules if not r.product_id and not r.category_id), None)

    # Specificity order, resolved in one pass. The first candidate that yields a usable
    # value wins; a percent rule with no list price to apply to falls through to the
    # next level rather than blocking the line.
    ancestry = category_ancestry(db, product.category_id)
    candidates: List[tuple[PriceFloorRule, str, Optional[str]]] = []
    if product.id in by_product:
        candidates.append((by_product[product.id], LEVEL_PRODUCT, None))
    for index, category_id in enumerate(ancestry):
        rule = by_category.get(category_id)
        if rule:
            level = LEVEL_CATEGORY if index == 0 else LEVEL_CATEGORY_ANCESTOR
            candidates.append((rule, level, category_id))
    if system:
        candidates.append((system, LEVEL_SYSTEM, None))

    for rule, level, category_id in candidates:
        value = _floor_from_rule(rule, effective_list)
        if value is None:
            continue
        return ResolvedFloor(
            value=value,
            mode=rule.mode,
            level=level,
            rule_id=rule.id,
            category_id=category_id,
        )
    return None


# ------------------------------------------------------------- rule management


def _validate_rule(payload: Dict[str, Any]) -> None:
    mode = payload.get("mode") or FLOOR_MODE_PERCENT
    if mode not in FLOOR_MODES:
        raise AppException(
            status_code=422,
            message=f"Unknown floor mode '{mode}'. Use percent or absolute.",
            code="floor_mode_invalid",
        )
    if payload.get("product_id") and payload.get("category_id"):
        raise AppException(
            status_code=422,
            message=(
                "A floor rule targets either a product or a category, not both -- the "
                "level is decided by which one you set."
            ),
            code="floor_target_ambiguous",
        )

    raw_value = payload.get("value")
    if raw_value is None:
        raise AppException(
            status_code=422,
            message="A floor rule needs a value.",
            code="floor_value_required",
        )
    value = Decimal(str(raw_value))
    if value <= 0:
        raise AppException(
            status_code=422,
            message="A floor value must be greater than zero.",
            code="floor_value_invalid",
        )
    if mode == FLOOR_MODE_PERCENT and value > 100:
        # Refused rather than clamped: a floor above list price is a policy nobody
        # means (every line would breach it), and clamping hides the typo so the admin
        # never learns their 950 should have been 95.
        raise AppException(
            status_code=422,
            message=(
                "A percentage floor cannot exceed 100% of list price. For a hard "
                "amount, use the absolute mode."
            ),
            code="floor_percent_over_hundred",
        )


def upsert_floor_rule(
    db: Session,
    *,
    company_id: str,
    payload: Dict[str, Any],
    actor_user_id: Optional[str] = None,
) -> PriceFloorRule:
    """Create or replace the rule at one level. Idempotent per target.

    Upsert rather than insert because the unique index makes one rule per target the
    invariant, and an admin editing "the Basins floor" means exactly that, not a second
    competing Basins rule.
    """
    _validate_rule(payload)

    product_id = payload.get("product_id") or None
    category_id = payload.get("category_id") or None

    existing = (
        db.query(PriceFloorRule)
        .filter(
            PriceFloorRule.company_id == company_id,
            PriceFloorRule.product_id.is_(None)
            if product_id is None
            else PriceFloorRule.product_id == product_id,
            PriceFloorRule.category_id.is_(None)
            if category_id is None
            else PriceFloorRule.category_id == category_id,
        )
        .first()
    )

    if existing:
        existing.mode = payload.get("mode") or FLOOR_MODE_PERCENT
        existing.value = Decimal(str(payload["value"]))
        if "notes" in payload:
            existing.notes = payload.get("notes")
        if "is_active" in payload:
            existing.is_active = bool(payload["is_active"])
        db.flush()
        return existing

    rule = PriceFloorRule(
        company_id=company_id,
        product_id=product_id,
        category_id=category_id,
        mode=payload.get("mode") or FLOOR_MODE_PERCENT,
        value=Decimal(str(payload["value"])),
        notes=payload.get("notes"),
        is_active=bool(payload.get("is_active", True)),
        created_by=actor_user_id,
    )
    db.add(rule)
    db.flush()
    return rule


def delete_floor_rule(db: Session, rule: PriceFloorRule) -> None:
    """Hard delete. A floor already applied to a line is stored ON that line
    (AC-E7), so removing the rule cannot rewrite quoted history."""
    db.delete(rule)
    db.flush()


def list_floor_rules(db: Session, *, company_id: str) -> List[PriceFloorRule]:
    return (
        db.query(PriceFloorRule)
        .filter(PriceFloorRule.company_id == company_id)
        .order_by(
            # Most specific first, which is the order they take effect in.
            PriceFloorRule.product_id.isnot(None).desc(),
            PriceFloorRule.category_id.isnot(None).desc(),
            PriceFloorRule.created_at.asc(),
        )
        .all()
    )


# ---------------------------------------------------------- series membership


def series_category_ids(db: Session, series_id: Optional[str]) -> Set[str]:
    """Every category the series covers, descendants included (AC-E5)."""
    if not series_id:
        return set()
    nominated = [
        row[0]
        for row in db.query(ProjectSeriesCategory.category_id)
        .filter(ProjectSeriesCategory.series_id == series_id)
        .all()
    ]
    return category_with_descendants(db, nominated)


def is_in_series(
    db: Session,
    *,
    series_id: Optional[str],
    product: Optional[Product],
    covered: Optional[Set[str]] = None,
) -> bool:
    """Is this line's product inside the nominated series?

    An off-catalog line is never in the series (AC-E5): there is no category to check,
    and "we quoted something that isn't in our catalogue" is exactly what the alert is
    for. With NO series nominated everything counts as standard -- a project that never
    picked a series has no allowlist to breach.

    ``covered`` lets a caller expand the series once and reuse it across a whole
    version's lines rather than re-walking the hierarchy per line.
    """
    if not series_id:
        return True
    if product is None:
        return False
    allowed = covered if covered is not None else series_category_ids(db, series_id)
    return product.category_id in allowed


def set_series_categories(
    db: Session, *, series: ProjectSeries, category_ids: Sequence[str]
) -> None:
    """Replace the nominated set. Sent whole, not as a delta.

    Reconciled rather than deleted-and-reinserted so an unchanged nomination keeps its
    row, which keeps the audit trail readable.
    """
    wanted = {cid for cid in category_ids if cid}
    existing = {
        row.category_id: row
        for row in db.query(ProjectSeriesCategory)
        .filter(ProjectSeriesCategory.series_id == series.id)
        .all()
    }

    for category_id in wanted - set(existing):
        db.add(ProjectSeriesCategory(series_id=series.id, category_id=category_id))
    for category_id in set(existing) - wanted:
        db.delete(existing[category_id])
    db.flush()
