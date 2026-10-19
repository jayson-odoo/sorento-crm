"""SPEC-OVER-HELD (CHAT-CLOSED-LISTS, CHAT-STATE handoff 17 Oct 2026): a spec said about a
held product narrows that product's family, never the catalogue.

A family is the chat-searchable products of the held product's own company that share its
non-null `products.family_code` (the field the ORM derives from the code), plus the variant
graph (`products.variant_of_id`, root and descendants) for hand-curated links.

"How about p trap" after "SRTWC286-SH x 10: no stock" is about the SRTWC286 family's P-trap
variant, which exists; the bot answered every P-trap WC. When a gated message names
specification values and no product of its own, and the conversation holds products, the
held products are filtered by the stored spec values (and a named brand), the parser's
registry values compared exactly. Held products that carry every named value are the answer,
with no siblings; only when none does, the same filter runs over their family. Those members
become this turn's products. No member carries them: the held products stay the subject. Data only: no word of the message is read.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.services.chatbot.head.scheme_index import names_own_class

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

#: How far up and down the variant graph a family is read (codes nest a few levels deep).
MAX_DEPTH = 6

_SPEC_HINTS = frozenset({"specification", "spec"})


def _family_ids(db: "Session", held_ids: list[str]) -> set[str]:
    from sqlalchemy import or_

    from app.models.product import Product, chat_searchable_products

    roots: set[str] = set()
    for pid in held_ids:
        current = pid
        for _ in range(MAX_DEPTH):
            row = db.query(Product.variant_of_id).filter(Product.id == current).first()
            if row is None or not row[0]:
                break
            current = str(row[0])
        roots.add(current)
    family = set(roots)
    frontier = set(roots)
    for _ in range(MAX_DEPTH):
        if not frontier:
            break
        children = {
            str(pid)
            for (pid,) in db.query(Product.id).filter(Product.variant_of_id.in_(list(frontier))).all()
        }
        frontier = children - family
        family |= children
    # The same company's products sharing a held product's family_code. One query for the
    # held rows' (company, family_code), one for the members; NULL adds nothing.
    codes = {
        (str(company_id), str(code))
        for company_id, code in db.query(Product.company_id, Product.family_code)
        .filter(Product.id.in_(list(family)), Product.family_code.isnot(None))
        .all()
    }
    if codes:
        by_company: dict[str, set[str]] = {}
        for company_id, code in codes:
            by_company.setdefault(company_id, set()).add(code)
        family |= {
            str(pid)
            for (pid,) in db.query(Product.id)
            .filter(
                or_(*[(Product.company_id == c) & Product.family_code.in_(sorted(v)) for c, v in by_company.items()]),
                chat_searchable_products(),
            )
            .all()
        }
    return {
        str(pid)
        for (pid,) in db.query(Product.id).filter(Product.id.in_(list(family)), chat_searchable_products()).all()
    }


def _value_texts(value: Any) -> list[str]:
    """The stored text forms of a registry value: an enum choice case aside, a number as
    it is written in a JSON value (600 and 600.0 are the same size)."""
    if isinstance(value, bool):
        return [str(value).lower()]
    if isinstance(value, (int, float)):
        number = float(value)
        return sorted({repr(number), str(int(number))} if number.is_integer() else {repr(number)})
    return [str(value).lower()]


def _brand_ids(db: "Session", brands: list[dict[str, Any]]) -> set[str] | None:
    """The brands the message names, by the brand entity's id, code or name; None when it
    names none."""
    from sqlalchemy import func, or_

    from app.models.product import Brand

    words = {
        str(v).strip().casefold()
        for e in brands
        for v in (e.get("canonical_code"), e.get("raw"))
        if str(v or "").strip()
    }
    if not words:
        return None
    rows = db.query(Brand.id).filter(
        or_(
            Brand.id.in_([w for w in words if len(w) == 36]),
            func.lower(Brand.brand_code).in_(words),
            func.lower(Brand.brand_name).in_(words),
        )
    ).all()
    return {str(bid) for (bid,) in rows}


def narrow_held_family(
    db: "Session", verdict: dict[str, Any], held_products: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """The verdict with the held family's matching members as its products, and a trace
    note; the verdict unchanged (and no note) when the rule does not apply.

    FILTER-OVER-HELD (CHAT-STATE card R1, crew 18 Oct): a size is a number and a brand is a
    filter too. When no member carries what the message names, the held products stay the
    subject ("held, none match"), so the answer says plainly that they do not have it,
    never the whole catalogue's set."""
    from sqlalchemy import func

    from app.models.product import Product
    from app.models.product_spec import ProductSpecifications

    entities = [e for e in verdict.get("entities") or [] if isinstance(e, dict)]
    said = [e for e in entities if e.get("current_message") is not False]
    specs = [
        (str(e.get("spec_key")), e.get("spec_value"))
        for e in said
        if str(e.get("hint") or "").strip().lower() in _SPEC_HINTS
        and e.get("spec_key")
        and e.get("spec_value") is not None
        and str(e.get("spec_value")) != ""
    ]
    brands = [e for e in said if str(e.get("hint") or "").strip().lower() == "brand"]
    # A message naming its own class is not about the held products either.
    names_a_product = any(str(e.get("hint") or "").strip().lower() == "product" for e in said) or names_own_class(said)
    held_ids = [str(p["uuid"]) for p in held_products if isinstance(p, dict) and p.get("uuid")]
    if not (specs or brands) or names_a_product or not held_ids or verdict.get("family") is True:
        return verdict, None
    brand_ids = _brand_ids(db, brands) if brands else None

    def narrowed(ids: set[str]) -> list[tuple[Any, Any]]:
        query = db.query(Product.id, Product.product_code).filter(Product.id.in_(list(ids)))
        if specs:
            query = query.join(ProductSpecifications, ProductSpecifications.product_id == Product.id)
        for key, value in specs:
            query = query.filter(func.lower(ProductSpecifications.values[key]["value"].astext).in_(_value_texts(value)))
        if brand_ids is not None:
            query = query.filter(Product.brand_id.in_(list(brand_ids) or [""]))
        return sorted(query.all(), key=lambda row: row[1])

    # The held products answer first; their family only when none of them carries what was said.
    matched = narrowed(set(held_ids))
    family = set(held_ids)
    if not matched:
        family = _family_ids(db, held_ids)
        if not family:
            return verdict, None
        matched = narrowed(family)
    note = {"held": len(held_ids), "family": len(family), "specs": specs, "brands": len(brands)}
    if not matched:
        # Held, none match: the subject is kept, and the filter beside it finds nothing.
        held = [
            {"raw": p.get("canonical_code"), "hint": "product", "canonical_code": p.get("canonical_code"),
             "current_message": True, "confident": True}
            for p in held_products
            if isinstance(p, dict) and p.get("uuid") and p.get("canonical_code")
        ]
        if not held:
            return verdict, None
        return {**verdict, "entities": [*held, *entities]}, {**note, "matched": [], "none_match": True}
    products = [
        {"raw": code, "hint": "product", "canonical_code": code, "current_message": True, "confident": True}
        for _pid, code in matched
    ]
    return {**verdict, "entities": [*products, *entities]}, {**note, "matched": [code for _pid, code in matched]}
