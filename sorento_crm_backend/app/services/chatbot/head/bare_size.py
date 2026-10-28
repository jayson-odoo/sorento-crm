"""BARE-SIZE-BY-DATA (CHAT-CLOSED-LISTS R6-1, widened by DIMENSION-ANY, owner 28 Oct 2026).

The parser picks the reserved spec_key "size" off the candidate line "size N mm (no dimension
named)", which already gave a centimetre or inch size in mm through the registry's `unit_aliases`.
A length matches EVERY dimension key of the registry (`product_spec_search.dimension_keys`: every
numeric key held in millimetres), as an OR (`spec_any_keys`), never one of them: "it should search
all dimension". The message text is never read here; only the parser's value and unit are.
Another unit keeps R6-1: a numeric key a class scopes (`applies_when.class`) that holds the number
in that class, else the keys flagged `matches_bare_size`. A NAMED dimension is the parser's own
key; when nothing holds it the set falls back to any dimension
(`product_predicate_service.resolve_product_set`). Data only: no word is matched.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.chatbot.head.grounding import Grounded, Vocabulary

RESERVED_KEY = "size"


def _number(value: Any) -> float | None:
    try:
        return float(str(value).split()[0])
    except (TypeError, ValueError, IndexError):
        return None


def _plain(number: float) -> int | float:
    return int(number) if number.is_integer() else number


def _classes(db: "Session", entities: list[dict[str, Any]], held_ids: list[str] | None) -> set[str]:
    """The class values the ask is about, casefolded: the message's own class entity, else
    the held products' stored class."""
    from app.models.product import Product
    from app.services.product_class_signal import resolve_classes_for_term
    from app.models.product_spec import ProductSpecifications

    out: set[str] = set()
    for e in entities:
        if e.get("current_message") is not False and str(e.get("hint") or "").strip().lower() in ("category", "product_type"):
            out.update(str(c).casefold() for c in resolve_classes_for_term(db, str(e.get("raw") or "")))
    if out or not held_ids:
        return out
    rows = (
        db.query(ProductSpecifications.values["class"]["value"].astext)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(ProductSpecifications.product_id.in_(held_ids))
        .distinct()
        .all()
    )
    return {str(c).casefold() for (c,) in rows if c}


def _holds(db: "Session", key: str, number: float, classes: set[str]) -> bool:
    """Does any product of the class carry `number` under `key` (an exact numeric match)?"""
    from sqlalchemy import Float, case, cast, func

    from app.models.product import Product, chat_searchable_products
    from app.models.product_spec import ProductSpecifications

    stored = ProductSpecifications.values[key]["value"]
    number_ok = func.jsonb_typeof(stored) == "number"
    value = cast(case((number_ok, stored.astext), else_=None), Float)
    query = (
        db.query(ProductSpecifications.id)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(chat_searchable_products(), value.between(number - 1e-6, number + 1e-6))
    )
    if classes:
        query = query.filter(func.lower(ProductSpecifications.values["class"]["value"].astext).in_(sorted(classes)))
    return query.first() is not None


def _scopes_class(row: Any, classes: set[str]) -> bool:
    scope = (getattr(row, "applies_when", None) or {}).get("class") or []
    return bool(classes) and any(str(c).casefold() in classes for c in scope)


def ground_bare(
    db: "Session",
    entity: dict[str, Any],
    entities: list[dict[str, Any]],
    vocab: "Vocabulary",
    held_ids: list[str] | None,
    hidden_keys: frozenset[str] = frozenset(),
) -> "Grounded | None":
    """For the reserved "size" pick: the OR over every dimension key for a length, else the strict
    class key or the OR over the bare-size keys; None for anything else (unchanged)."""
    from app.services.chatbot.head.grounding import Grounded
    from app.services.product_spec_registry import active_registry
    from app.services.product_spec_search import dimension_keys, length_factor

    key = str(entity.get("spec_key") or "").strip()
    number = _number(entity.get("spec_value"))
    if number is None or key != RESERVED_KEY:
        return None
    said = str(entity.get("raw") or "").strip() or str(entity.get("spec_value"))
    # A key the contact may not see is never chosen, as the class key or an OR leg.
    rows = [
        r for r in active_registry(db)
        if (r.data_type or "").lower() == "numeric" and getattr(r, "unit", None) and r.spec_key not in hidden_keys
    ]
    # The parser's own unit (`spec_unit`), read through the registry's aliases. The message text
    # is never read here: the candidate line already offered "15cm" as "size 150 mm", and the
    # parser picked it (owner rule, 28 Oct 2026: understanding is the parser's).
    unit_said = str(entity.get("spec_unit") or "").strip().casefold()
    dims = dimension_keys(rows)
    dim_rows = [r for r in rows if r.spec_key in dims]
    base = str(dim_rows[0].unit).casefold() if dim_rows else ""
    aliases = {str(k).casefold(): v for r in dim_rows for k, v in (getattr(r, "unit_aliases", None) or {}).items()}
    if dims and (not unit_said or unit_said == base or unit_said in aliases):
        if unit_said in aliases and unit_said != base:
            number = round(number * float(aliases[unit_said]), 3)
        return Grounded(RESERVED_KEY, "Size", said, _plain(number), str(dim_rows[0].unit), any_keys=dims)
    # Another unit (litres, ounces): R6-1, over the keys of that unit.
    rows = [r for r in rows if length_factor(r.unit) is None]
    classes = _classes(db, entities, held_ids)
    units = {str(r.unit).casefold() for r in rows if getattr(r, "matches_bare_size", False) or _scopes_class(r, classes)}
    # More than one unit in play: the size word's own unit only.
    unit = next(iter(units)) if len(units) == 1 else (unit_said if unit_said in units else None)
    if unit is None and units:
        return None
    same_unit = [r for r in rows if unit is None or str(r.unit).casefold() == unit]
    for row in same_unit:
        if _scopes_class(row, classes) and _holds(db, row.spec_key, number, classes):
            return Grounded(row.spec_key, row.label, said, _plain(number), row.unit)
    any_keys = [r.spec_key for r in same_unit if getattr(r, "matches_bare_size", False)]
    if any_keys:
        return Grounded(RESERVED_KEY, "Size", said, _plain(number), str(same_unit[0].unit), any_keys=any_keys)
    return None
