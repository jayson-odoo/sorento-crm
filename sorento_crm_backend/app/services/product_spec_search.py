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
from app.services.product_spec_registry import active_registry, merged_synonyms

# Tuned against the eval baseline, not guessed. Kept here rather than in the registry
# because they describe the ranker's shape, not the vocabulary.
CLASS_BOOST = 5.0
FREE_TERM_BOOST = 1.2
NUMERIC_BOOST = 2.0
ACCESSORY_PENALTY = 6.0
# A stated spec the product CONTRADICTS. Someone who says "wall hung" is not helped by
# a floor-standing model ranked above a wall-hung one, which is what happened while a
# mismatch merely scored zero. Deliberately smaller than the match it opposes: this
# demotes a contradicting product, it does not remove it, because the parser is the
# thing most likely to be wrong.
MISMATCH_PENALTY = 2.5
# Numeric tolerance is NOT a constant here any more. It is a property of the quantity
# and lives on the registry row (`match_tolerance` / `match_decay`), because one
# millimetre-shaped "+/- 5" applied to every numeric key made a one-bowl sink an exact
# match for "double bowl". See product_spec_registry.default_match_window.
MAX_CANDIDATES = 5
# A single class match scores 5.0, so the floor sits just under "one real signal".
# Below that a result is one weak trigram hit, which is how "flux capacitor" would
# otherwise return a kitchen sink.
RELEVANCE_FLOOR = 1.5


def _numeric_score(target: float, actual: float, tolerance: float, decay: float) -> float:
    """1.0 within `tolerance` of the target, then decaying to 0 at `decay`.

    `decay <= 0` means exact-or-nothing. That is the correct shape for a COUNT: two
    bowls and one bowl are not "nearly the same", however small the arithmetic
    difference looks next to a millimetre scale.
    """
    distance = abs(float(target) - float(actual))
    if distance <= tolerance:
        return 1.0
    if decay <= 0:
        return 0.0
    return max(0.0, 1.0 - (distance / decay))


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9.]+", (text or "").lower()) if len(t) > 2}


def _summarise(values: dict, rendered: str | None) -> str:
    return rendered or ""


# Customers do not write in one unit. The catalog is millimetres throughout, so every
# quantity is normalised to mm through this table before it is compared. Adding a unit
# is a row here, not a new code path.
_UNIT_TO_MM: dict[str, float] = {
    "mm": 1.0,
    "cm": 10.0,
    "m": 1000.0,
    "in": 25.4,
    "inch": 25.4,
    "inches": 25.4,
    '"': 25.4,
    "”": 25.4,
    "''": 25.4,
}

# A number with an optional trailing unit. The leading guard stops it eating the digits
# out of a product code (CKS1050), which is text a customer legitimately types.
_QUANTITY_RE = re.compile(
    r"(?<![a-z0-9.])(\d+(?:\.\d+)?)\s*(mm|cm|m|inches|inch|in|\"|”|'')?(?![a-z0-9])",
    re.IGNORECASE,
)

# How far from a quantity a key's own word may sit and still claim it. Wide enough for
# "S-TRAP 8\" ( 200mm)" and "thickness of 1.2mm", short enough that two different
# measurements in one sentence do not steal each other's numbers.
_QUANTITY_BINDING_WINDOW = 20

# Inside a key's `synonyms` map, this pseudo-value holds the words that name the KEY
# ITSELF rather than one of its values — "thickness", "trap", "length". Enum keys have
# no use for it; numeric keys have no values to hang synonyms off, so without it there
# is no way to write down what a customer calls the measurement.
SELF_SYNONYM_KEY = "_self"


def normalise_quantity(text: str) -> float | None:
    """The first quantity in `text` as millimetres, or None.

    Shared with the semantic extractor: a model told "the unit is mm" will still
    sometimes echo the customer's own unit back ("8 inch"), so the conversion cannot
    live only in the deterministic path.
    """
    match = _QUANTITY_RE.search(text or "")
    if not match:
        return None
    try:
        number = float(match.group(1))
    except (TypeError, ValueError):
        return None
    return number * _UNIT_TO_MM.get((match.group(2) or "").lower(), 1.0)


def _extract_quantities(haystack: str) -> list[tuple[float, int, int, str]]:
    """Every (value_in_mm, start, end, evidence) in the phrase.

    A bare number carries no unit and is returned unconverted: "200" and "200mm" mean
    the same thing in a millimetre catalog, but 8 does not become 8mm — see the caller,
    which only binds a unitless number when a key's word is adjacent.
    """
    found: list[tuple[float, int, int, str]] = []
    for match in _QUANTITY_RE.finditer(haystack):
        raw, unit = match.group(1), (match.group(2) or "").lower()
        try:
            number = float(raw)
        except ValueError:
            continue
        found.append(
            (number * _UNIT_TO_MM.get(unit, 1.0), match.start(), match.end(), match.group(0).strip())
        )
    return found


def _resolve_quantities(haystack: str, rows) -> dict[str, float]:
    """Bind numbers in the phrase onto the numeric key whose own word sits nearest.

    Nothing here guesses. A quantity is only claimed when a key's synonym is within
    `_QUANTITY_BINDING_WINDOW` characters of it, so "S trap 8\" (200mm)" reaches
    `trap_length` while a stray number in a product code reaches nothing. The
    alternative — binding an unqualified number to the class's "obvious" dimension —
    is exactly the kind of guess that puts a wrong product in front of a customer.
    """
    quantities = _extract_quantities(haystack)
    if not quantities:
        return {}

    numeric_keys = [r for r in rows if r.data_type == "numeric"]
    claimed: dict[str, tuple[int, float]] = {}

    for row in numeric_keys:
        words = [str(w).lower() for w in merged_synonyms(row).get(SELF_SYNONYM_KEY, [])]
        for word in words:
            if not word:
                continue
            for anchor in re.finditer(rf"(?<!\w){re.escape(word)}(?!\w)", haystack):
                for value, start, end, _evidence in quantities:
                    # Distance from the word to the number, in either direction.
                    distance = start - anchor.end() if start >= anchor.end() else anchor.start() - end
                    if 0 <= distance <= _QUANTITY_BINDING_WINDOW:
                        current = claimed.get(row.spec_key)
                        if current is None or distance < current[0]:
                            claimed[row.spec_key] = (distance, value)

    return {key: value for key, (_, value) in claimed.items()}


def resolve_terms_to_specs(db: Session, free_terms: list[str]) -> list[dict]:
    """Turn customer words into registry spec values, longest phrase first.

    The registry has carried the synonyms all along and nothing consulted them, so a
    phrase only ever earned a weak substring boost against the rendered sentence. That
    is why "angle valve" fell below the floor while 338 angle valves sat in the catalog
    with `product_type=angle_valve` stored: the words appeared nowhere in the sentence
    the ranker could see, and the key that held the answer was never scored.

    Longest-first matters: "single bowl" must not resolve as "single lever" losing to
    "bowl", and "hand shower" must beat "shower".
    """
    haystack = " ".join(t.lower() for t in free_terms if t)
    if not haystack:
        return []

    rows = active_registry(db)

    candidates: list[tuple[int, str, str]] = []
    for row in rows:
        for value, synonyms in merged_synonyms(row).items():
            # `_self` names the key, not a value. Reading it as one would resolve
            # `thickness = "_self"`.
            if value == SELF_SYNONYM_KEY:
                continue
            for synonym in synonyms:
                phrase = str(synonym).lower().strip()
                if not phrase:
                    continue
                if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", haystack):
                    candidates.append((len(phrase), row.spec_key, value))

    # One value per key: the longest phrase that matched wins, so a specific reading
    # beats a generic one that happens to be a substring of the same words.
    best: dict[str, tuple[int, str]] = {}
    for length, key, value in candidates:
        if key not in best or length > best[key][0]:
            best[key] = (length, value)

    types = {row.spec_key: row.data_type for row in rows}
    resolved: list[dict] = []
    for key, (_, value) in best.items():
        # The synonym map is JSON, so every key arrives as a string. Coerce back to the
        # type the value is STORED as, or the comparison silently never matches: "2" is
        # not 2, and a mismatch that cannot match also cannot be penalised.
        if types.get(key) == "boolean":
            value = value == "true"
        elif types.get(key) == "numeric":
            try:
                value = int(value)
            except (TypeError, ValueError):
                continue
        resolved.append({"key": key, "value": value})

    # Numbers the customer typed: "trap 200mm", "thickness 1.2mm", 'S trap 8"'.
    # A value stated in WORDS wins over one bound by proximity — "double bowl" is a
    # direct statement, a nearby number is an inference about which measurement was
    # meant.
    already = {entry["key"] for entry in resolved}
    for key, value in _resolve_quantities(haystack, rows).items():
        if key not in already:
            resolved.append({"key": key, "value": value})

    return resolved


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

    registry_rows = active_registry(db)
    weights = {row.spec_key: float(row.rank_weight or 1.0) for row in registry_rows}
    # (tolerance, decay) per key, so a count is compared as a count and a millimetre as
    # a millimetre.
    match_windows = {
        row.spec_key: (float(row.match_tolerance or 0.0), float(row.match_decay or 0.0))
        for row in registry_rows
    }

    # Words the caller did not map onto a key are mapped here. An explicitly-passed
    # spec always wins: the caller's parser saw the whole sentence, this sees a bag of
    # words.
    stated = {str(entry.get("key")) for entry in specs if entry.get("key")}
    specs = specs + [e for e in resolve_terms_to_specs(db, free_terms) if e["key"] not in stated]

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
        # Penalties are accumulated apart from the boosts so that "did this product
        # match anything at all" stays answerable after they are applied.
        penalty = 0.0
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
                tolerance, decay = match_windows.get(key, (0.0, 0.0))
                gain = _numeric_score(float(target), float(actual), tolerance, decay)
                if gain > 0:
                    score += NUMERIC_BOOST * weight * gain
                    if gain == 1.0:
                        matched.append(key)
                else:
                    # Stated, stored, and outside the window entirely. A number can
                    # contradict exactly as an enum can — without this a one-bowl sink
                    # merely scored zero on bowl_count and still won on its other
                    # signals, which is what put it above real double-bowl sinks.
                    penalty += MISMATCH_PENALTY
            elif str(actual).lower() == str(target).lower():
                score += weight
                matched.append(key)
            else:
                # Stated, stored, and different. Not the same thing as unstated: a
                # product with NO mounting is merely unknown and stays neutral, but one
                # that is explicitly floor standing contradicts "wall hung" and must not
                # outrank a product that matches it.
                penalty += MISMATCH_PENALTY

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
            penalty += ACCESSORY_PENALTY

        positive = score
        score -= penalty

        # Dropped for having NO positive evidence, never for scoring badly. A penalty
        # that can delete a row is a filter wearing a boost's clothes, and this file's
        # first rule is that one over-extracted spec must not empty the shortlist: a
        # floor-standing WC still answers "wall hung water closet" better than silence,
        # it just answers it last.
        if positive <= 0:
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
