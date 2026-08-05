"""Rank products against extracted specs, and refuse to answer when nothing fits.

Two rules carry the whole design.

**Every spec is a boost, never a WHERE.** A reader expects filters; filters are wrong
here. The output is a recall-oriented did-you-mean picker, so one over-extracted spec
must not empty it. A customer who says "stainless steel kitchen sink" and is handed
nothing because the parser also guessed `mounting=wall_hung` has been failed by the
filter, not helped by it. Scoring degrades gracefully where a filter fails cliff-edged.

**The relevance floor is the counterweight.** A soft ranker is never empty, so without
a floor it always has an answer, including for "flux capacitor". Below the floor the
caller shows nothing and falls through to the existing clarify path.

Query-time inputs are structured spec values and the rendered spec sentence. The raw
`products.description` is never read here: it is consulted once, offline, during
derivation. That is what keeps the code-only resolution rule in
`entity_resolver.py:2945` intact while still allowing description-derived search.

Ticket: jayson-odoo/sorento-crm#76.
"""
from __future__ import annotations

import re
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.product import Product, ProductCategory
from app.models.product_spec import ProductSpecifications
from app.services.product_class_signal import resolve_classes_for_term
from app.services.product_spec_registry import active_registry

# Tuned against the eval baseline, not guessed. Kept here rather than in the registry
# because they describe the ranker's shape, not the vocabulary.
CLASS_BOOST = 5.0
FREE_TERM_BOOST = 1.2
NUMERIC_BOOST = 2.0
ACCESSORY_PENALTY = 6.0
# +/- 5mm reads as exact, matching the hedge convention already used for dimensions
# elsewhere in the CRM.
NUMERIC_EXACT_TOLERANCE = 5.0
NUMERIC_DECAY = 150.0
MAX_CANDIDATES = 5
# A single class match scores 5.0, so the floor sits just under "one real signal".
# Below that a result is one weak trigram hit, which is how "flux capacitor" would
# otherwise return a kitchen sink.
RELEVANCE_FLOOR = 1.5


def _numeric_score(target: float, actual: float) -> float:
    """1.0 at (or within tolerance of) the target, decaying with distance."""
    distance = abs(float(target) - float(actual))
    if distance <= NUMERIC_EXACT_TOLERANCE:
        return 1.0
    return max(0.0, 1.0 - (distance / NUMERIC_DECAY))


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9.]+", (text or "").lower()) if len(t) > 2}


def _summarise(values: dict, rendered: str | None) -> str:
    return rendered or ""


def search_specs(
    db: Session,
    *,
    specs: list[dict] | None = None,
    free_terms: list[str] | None = None,
    limit: int = MAX_CANDIDATES,
    include_accessories: bool = False,
    floor: float = RELEVANCE_FLOOR,
) -> dict:
    """Rank the catalog against extracted specs. Returns candidates and a floor verdict.

    `include_accessories` only relaxes the deboost, it never becomes a filter: a
    customer asking for a "sink basket" should find one.
    """
    specs = specs or []
    free_terms = [t for t in (free_terms or []) if t and t.strip()]

    weights = {row.spec_key: float(row.rank_weight or 1.0) for row in active_registry(db)}

    # A free term that names a class IS a class match, and class is the strongest
    # signal we have. Without this, "sink" scored one weak text hit and fell below the
    # floor, so the single most natural query in the corpus returned nothing.
    implied_classes = {
        label.lower()
        for term in free_terms
        for label in resolve_classes_for_term(db, term)
    }

    rows = (
        db.query(ProductSpecifications, Product, ProductCategory)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
        .filter(Product.is_active.is_(True))
        .all()
    )

    wanted_terms: set[str] = set()
    for term in free_terms:
        wanted_terms |= _tokens(term)

    scored: list[dict] = []
    for spec_row, product, category in rows:
        values = spec_row.values or {}
        score = 0.0
        matched: list[str] = []

        for entry in specs:
            key, target = entry.get("key"), entry.get("value")
            if key is None or target is None:
                continue
            stored = values.get(key)
            if not isinstance(stored, dict):
                continue
            actual = stored.get("value")
            if actual is None:
                continue

            weight = weights.get(key, 1.0)
            if key == "class":
                if str(actual).lower() == str(target).lower():
                    score += CLASS_BOOST
                    matched.append(key)
            elif isinstance(actual, (int, float, Decimal)) and isinstance(target, (int, float, Decimal)):
                gain = _numeric_score(float(target), float(actual))
                if gain > 0:
                    score += NUMERIC_BOOST * weight * gain
                    if gain == 1.0:
                        matched.append(key)
            elif str(actual).lower() == str(target).lower():
                score += weight
                matched.append(key)

        # A free term naming this product's class counts as a class match.
        class_value = str((values.get("class") or {}).get("value") or "").lower()
        if implied_classes and class_value and class_value in implied_classes:
            if "class" not in matched:
                score += CLASS_BOOST
                matched.append("class")

        # Free terms match the RENDERED SENTENCE, never the raw description.
        if wanted_terms:
            haystack = _tokens(spec_row.rendered_text or "")
            if category is not None:
                haystack |= _tokens(category.class_label or "")
                for synonym in category.search_synonyms or []:
                    haystack |= _tokens(str(synonym))
            hits = wanted_terms & haystack
            if hits:
                score += FREE_TERM_BOOST * len(hits)
                matched.append("free_terms")

        is_accessory = bool((values.get("is_accessory") or {}).get("value"))
        if is_accessory and not include_accessories:
            score -= ACCESSORY_PENALTY

        if score <= 0:
            continue

        scored.append(
            {
                "product_id": str(product.id),
                "product_code": product.product_code,
                "summary": _summarise(values, spec_row.rendered_text),
                "class": (values.get("class") or {}).get("value"),
                "matched_specs": sorted(set(matched)),
                "score": round(score, 4),
                "is_discontinued": bool(product.is_discontinued),
                "is_accessory": is_accessory,
                # Collapse key. Two jobs: a variant answers for its parent (five
                # finishes of one sink must not eat all five slots), AND the same
                # model exists once per company, so keying on a row id would show
                # every product twice. Both collapse onto the model's CODE.
                "_variant_of": str(product.variant_of_id) if product.variant_of_id else None,
                "_code": product.product_code,
            }
        )

    scored.sort(key=lambda c: (-c["score"], c["product_code"]))

    # Family is a property of the MODEL, not of a row, and it has to be resolved that
    # way. Real catalog data has the same code marked a variant in one company and a
    # base in the other, so resolving per row gave the two copies different families
    # and the same sink appeared twice in a five-slot shortlist.
    code_for_id = {str(product.id): product.product_code for _, product, _ in rows}
    family_for_code: dict[str, str] = {}
    for _, product, _ in sorted(rows, key=lambda r: (r[1].product_code, str(r[1].company_id or ""))):
        code = product.product_code
        parent_code = code_for_id.get(str(product.variant_of_id)) if product.variant_of_id else None
        if parent_code and parent_code != code:
            family_for_code.setdefault(code, parent_code)
    
    collapsed: list[dict] = []
    seen_families: set[str] = set()
    for candidate in scored:
        candidate.pop("_variant_of")
        code = candidate.pop("_code")
        family = family_for_code.get(code, code)
        if family in seen_families:
            continue
        seen_families.add(family)
        collapsed.append(candidate)

    top = collapsed[:limit]
    floor_missed = (not top) or top[0]["score"] < floor

    return {
        "candidates": [] if floor_missed else top,
        "floor_missed": floor_missed,
        "top_score": top[0]["score"] if top else 0.0,
    }
