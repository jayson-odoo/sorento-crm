"""BARE-SIZE-BY-DATA (CHAT-CLOSED-LISTS R6-1): a size given alone matches width OR length.

The parser picks the reserved spec_key "size" for a number with a unit and no dimension named.
Which keys that can mean is read from the registry, never from code: a numeric key a class scopes
(`applies_when.class`) that holds the number in that class, else the keys flagged
`matches_bare_size`, as an OR (`spec_any_keys`). A NAMED dimension stays strict, except that when
no member of the class holds the number under it, the class's own key for the same quantity (one
sharing a registry phrase with it) that does hold it is read instead. The class is the message's
own class entity, else the held products' stored class. Data only: no word is matched.
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
    db: "Session", entity: dict[str, Any], entities: list[dict[str, Any]], vocab: "Vocabulary", held_ids: list[str] | None
) -> "Grounded | None":
    """The strict class key, or the OR over the bare-size keys, for the reserved "size" pick;
    the class's own key for a named dimension no class member holds; else None (unchanged)."""
    from app.services.chatbot.head.grounding import Grounded
    from app.services.product_spec_registry import active_registry, merged_synonyms

    key = str(entity.get("spec_key") or "").strip()
    number = _number(entity.get("spec_value"))
    if number is None:
        return None
    value: int | float = int(number) if number.is_integer() else number
    said = str(entity.get("raw") or "").strip() or str(entity.get("spec_value"))
    rows = [r for r in active_registry(db) if (r.data_type or "").lower() == "numeric" and getattr(r, "unit", None)]
    by_key = {r.spec_key: r for r in rows}
    classes = _classes(db, entities, held_ids)
    if key == RESERVED_KEY:
        units = {str(r.unit).casefold() for r in rows if getattr(r, "matches_bare_size", False) or _scopes_class(r, classes)}
        unit = next(iter(sorted(units)), None) if len(units) == 1 else None
        same_unit = [r for r in rows if unit is None or str(r.unit).casefold() == unit]
        for row in same_unit:
            if _scopes_class(row, classes) and _holds(db, row.spec_key, number, classes):
                return Grounded(row.spec_key, row.label, said, value, row.unit)
        any_keys = [r.spec_key for r in same_unit if getattr(r, "matches_bare_size", False)]
        if any_keys:
            return Grounded(RESERVED_KEY, "Size", said, value, str(same_unit[0].unit), any_keys=any_keys)
        return None
    row = by_key.get(key)
    if row is None or not classes or _holds(db, key, number, classes):
        return None
    phrases = {str(p).casefold() for p in (merged_synonyms(row).get("_self") or [])}
    for other in rows:
        if other.spec_key == key or not _scopes_class(other, classes) or str(other.unit).casefold() != str(row.unit).casefold():
            continue
        if phrases & {str(p).casefold() for p in (merged_synonyms(other).get("_self") or [])} and _holds(db, other.spec_key, number, classes):
            return Grounded(other.spec_key, other.label, said, value, other.unit)
    return None
