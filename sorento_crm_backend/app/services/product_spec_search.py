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

import json
import re
from decimal import Decimal

from sqlalchemy import cast, func, literal, or_
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.models.product import Brand, Product, ProductCategory
from app.models.product_spec import ProductSpecifications
from app.services.product_class_signal import resolve_classes_for_term, stored_class_labels
from app.services.product_spec_registry import (
    active_registry,
    merged_allowed_values,
    merged_synonyms,
    search_policy,
)
from app.services.product_spec_write import AUTHORED_SOURCES

# These are now DEFAULTS, not the settings. The live numbers come from
# `product_spec_search_policy` (see product_spec_registry.search_policy), because
# "discontinued should rank lower" and "our brand first" are merchandising decisions
# and should not need a deploy. The values here are what the table is seeded with, and
# what is used if the table is empty.
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


# Inside the tolerance band, how much of the score closeness is allowed to decide.
# Small on purpose: it orders products that all genuinely match, and must never
# outweigh a product matching one more spec.
_EXACTNESS_MARGIN = 0.02


def _states(actual, target) -> bool:
    """Does the stored value say `target`?

    A stored value may be a LIST: SRTWT9605-RG is "Rose Gold + Matt Black", two finishes
    on one product, and a customer asking for either is right. Scalars behave exactly as
    before.
    """
    if isinstance(actual, (list, tuple, set)):
        return any(str(a).strip().lower() == str(target).strip().lower() for a in actual)
    return str(actual).strip().lower() == str(target).strip().lower()


def _numeric_score(target: float, actual: float, tolerance: float, decay: float) -> float:
    """1.0 within `tolerance` of the target, then decaying to 0 at `decay`.

    `decay <= 0` means exact-or-nothing. That is the correct shape for a COUNT: two
    bowls and one bowl are not "nearly the same", however small the arithmetic
    difference looks next to a millimetre scale.

    Within the band, nearer still ranks higher. Flat 1.0 made a 500mm and a 495mm seat
    cover indistinguishable when the customer asked for 495 - both matched, so the
    order between them was arbitrary, and the one they named could lose.
    """
    distance = abs(float(target) - float(actual))
    if distance <= tolerance:
        if distance == 0 or tolerance <= 0:
            return 1.0
        return 1.0 - _EXACTNESS_MARGIN * (distance / tolerance)
    if decay <= 0:
        return 0.0
    return max(0.0, 1.0 - (distance / decay))


def _threshold_score(
    op: str, target: float, actual: float, tolerance: float, decay: float
) -> float:
    """How well `actual` answers a comparison against `target`.

    `at_least` / `at_most` are satisfied or not - a 960mm basin fully answers "above
    900mm" and a 850mm one does not answer it at all. There is no partial credit for
    nearly clearing a threshold: a cabinet that does not fit does not nearly fit.

    Anything else falls back to approximate equality, which is what an unqualified
    number means.
    """
    if op in {"at_least", "gte", "min"}:
        return 1.0 if actual >= target else 0.0
    if op in {"at_most", "lte", "max"}:
        return 1.0 if actual <= target else 0.0
    return _numeric_score(target, actual, tolerance, decay)


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9.]+", (text or "").lower()) if len(t) > 2}


def _summarise(values: dict, rendered: str | None) -> str:
    return rendered or ""


def values_only(values: dict | None) -> dict:
    """The stored spec block as `{key: value}`, wire-lean.

    Storage keeps each value in its own envelope (`{"value": 1.2, "unit": "mm"}`)
    because derivation needs somewhere to put the unit. A renderer needs the
    number. A list stays a list - two finishes on one product is one value, not
    two keys - and a key holding no value is simply not offered.
    """
    return {
        key: entry["value"]
        for key, entry in (values or {}).items()
        if isinstance(entry, dict) and entry.get("value") is not None
    }


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


# The flyer states a size as "L750 x W165 x H247mm" and a salesperson quoting a card
# says the same thing. The letter IS the statement of which dimension it is, so reading
# it is not the guess the binder below refuses to make.
_LABELLED_DIM_RE = re.compile(r"(?<![A-Za-z0-9])([LWHlwh])\s*(\d+(?:\.\d+)?)\s*(?:mm)?\b")
_LABEL_TO_KEY = {"l": "dim_length", "w": "dim_width", "h": "dim_height"}

# The largest number that can still be a COUNT. A key with no unit counts things -
# towel bars, bowls, ways - and "grab bar 750mm" was binding 750 to bar_count because
# the word "bar" sat next to it. A product with 750 bars does not exist, and the false
# bind then PENALISED every real grab bar for not having 750 of them.
_MAX_PLAUSIBLE_COUNT = 12

# The smallest an OVERALL product dimension can plausibly be, in millimetres. The flyer
# prints towel bars as "Length 23", meaning inches, and a bare number is read as
# millimetres - so the card's own words asked for a 23mm towel bar and penalised every
# real one. Deliberately limited to the three envelope dimensions: an 8mm thickness or a
# 32mm trap is a perfectly ordinary measurement.
_MIN_PLAUSIBLE_ENVELOPE_MM = 50
_ENVELOPE_KEYS = {"dim_length", "dim_width", "dim_height"}


# Did the customer say what unit they meant?
_HAS_UNIT_RE = re.compile(r"(mm|cm|m|inch|inches|in|\"|”|'')\s*$", re.IGNORECASE)


def _labelled_dimensions(haystack: str) -> dict[str, float]:
    """Sizes the phrase labels for itself: L750 x W165 x H247mm."""
    found: dict[str, float] = {}
    for match in _LABELLED_DIM_RE.finditer(haystack):
        key = _LABEL_TO_KEY[match.group(1).lower()]
        found.setdefault(key, float(match.group(2)))
    return found


def _resolve_quantities(
    haystack: str, rows, consumed: list[tuple[int, int]] | None = None
) -> dict[str, float]:
    """Bind numbers in the phrase onto the numeric key whose own word sits nearest.

    Nothing here guesses. A quantity is only claimed when a key's synonym is within
    `_QUANTITY_BINDING_WINDOW` characters of it, so "S trap 8\" (200mm)" reaches
    `trap_length` while a stray number in a product code reaches nothing. The
    alternative — binding an unqualified number to the class's "obvious" dimension —
    is exactly the kind of guess that puts a wrong product in front of a customer.
    """
    quantities = _extract_quantities(haystack)
    # Numbers another spec already claimed in words. "S/Steel 304" states a steel grade,
    # and once the towel bar's own "Length 23" was rejected as too small to be
    # millimetres, 304 was the next number near the word "length" - so the grade became
    # the length. A number can only mean one thing.
    if consumed:
        quantities = [
            q
            for q in quantities
            if not any(start <= q[1] and q[2] <= end for start, end in consumed)
        ]
    labelled = _labelled_dimensions(haystack)
    if not quantities and not labelled:
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
                        # A key with no unit counts things. 750 is not a count of
                        # anything, and binding it anyway turned "grab bar 750mm" into
                        # a search for a bar with 750 bars.
                        if row.unit is None and (
                            value > _MAX_PLAUSIBLE_COUNT or value != int(value)
                        ):
                            continue
                        # Stated without a unit and too small to be millimetres: the
                        # number is in some other unit and we do not know which.
                        if (
                            row.spec_key in _ENVELOPE_KEYS
                            and value < _MIN_PLAUSIBLE_ENVELOPE_MM
                            and not _HAS_UNIT_RE.search(_evidence)
                        ):
                            continue
                        current = claimed.get(row.spec_key)
                        if current is None or distance < current[0]:
                            claimed[row.spec_key] = (distance, value)

    resolved = {key: value for key, (_, value) in claimed.items()}
    # A size the phrase labelled for itself wins: "L750" says length outright, where the
    # binder above only ever inferred it from a nearby word.
    resolved.update(labelled)
    return resolved


def brand_names(db: Session) -> list[str]:
    """Every brand name the catalog spells, once. One query, name column only.

    Exposed so a request that consults brands more than once (resolve reads them
    for binding, for the vocabulary, and for junk suppression) can read them ONCE
    and hand the same list round.
    """
    return [
        str(name).strip()
        for (name,) in db.query(Brand.brand_name).all()
        if str(name or "").strip()
    ]


# A placeholder brand word too generic to ever be an ask. "OTHERS" is how the
# catalog records the ABSENCE of a brand on 1,956 products, and a customer writing
# "others" means the English word, never that bucket - so it stays unbindable even
# though the full name matches. "NO LOGO" is the opposite case: nobody says those
# two words in that order by accident, so the full phrase IS an ask (F8).
_UNBINDABLE_BRAND_NAMES: frozenset[str] = frozenset({"others"})


def _brand_match_in_haystack(
    haystack: str, registry_rows, names: list[str]
) -> tuple[str | None, tuple[int, int] | None]:
    """The brand named in the customer's words, with the span that named it.

    `excluded_values` on the registry row is how the catalog records the ABSENCE
    of a brand (OTHERS, NO LOGO). Those values are never OFFERED to the
    understanding model, but a customer who names one IN FULL is asking a real
    question - "no logo kitchen sink" is a request for the unbranded range, and
    answering it with silence was the gap. So an excluded value binds only on a
    full-phrase, word-boundary match of a MULTI-WORD name; a single generic word
    (OTHERS) never binds at all.

    Longest name wins, for the same reason the synonym loop above prefers the
    longest phrase: a specific reading beats a generic one that is a substring of
    the same words.
    """
    brand_row = next((row for row in registry_rows if row.spec_key == "brand"), None)
    excluded = {
        str(value).strip().lower()
        for value in (getattr(brand_row, "excluded_values", None) or [])
    }
    for name in sorted(names, key=len, reverse=True):
        lowered = name.lower()
        if lowered in _UNBINDABLE_BRAND_NAMES:
            continue
        if lowered in excluded and " " not in lowered:
            continue
        match = re.search(rf"(?<!\w){re.escape(lowered)}(?!\w)", haystack)
        if match:
            return name, (match.start(), match.end())
    return None, None


def resolve_terms_to_specs(
    db: Session,
    free_terms: list[str],
    *,
    registry_rows=None,
    brands: list[str] | None = None,
) -> list[dict]:
    """Turn customer words into registry spec values, longest phrase first.

    Kept as the plain list-returning entry point every existing caller uses;
    `resolve_terms_to_specs_with_spans` is the same work with the WHERE reported
    as well (see there).
    """
    resolved, _spans, _haystack = resolve_terms_to_specs_with_spans(
        db, free_terms, registry_rows=registry_rows, brands=brands
    )
    return resolved


def resolve_terms_to_specs_with_spans(
    db: Session,
    free_terms: list[str],
    *,
    registry_rows=None,
    brands: list[str] | None = None,
) -> tuple[list[dict], dict[str, list[tuple[int, int]]], str]:
    """The resolved specs, WHERE in the phrase each one was said, and the phrase.

    The spans are what makes a refusal readable without a model: knowing that
    `material=glass` was earned by the characters at 17..22 lets the caller look
    at the words just before them and see the "not" (see
    `product_spec_understanding._split_refusals`). Without them the word-level
    reader answers "not glass" with material=glass, which is the exact opposite
    of what was said.

    Spans are reported for values stated in WORDS and for the brand. A number
    bound by proximity has no phrase of its own to negate.

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
        return [], {}, ""

    rows = active_registry(db) if registry_rows is None else registry_rows

    candidates: list[tuple[int, str, str]] = []
    # Where a spec was stated in words, so a number inside those words is not also
    # free to be read as a measurement.
    spoken_spans: dict[tuple[str, str], list[tuple[int, int]]] = {}
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
                hits = list(re.finditer(rf"(?<!\w){re.escape(phrase)}(?!\w)", haystack))
                if hits:
                    candidates.append((len(phrase), row.spec_key, value))
                    spoken_spans.setdefault((row.spec_key, value), []).extend(
                        (m.start(), m.end()) for m in hits
                    )

    # One value per key: the longest phrase that matched wins, so a specific reading
    # beats a generic one that happens to be a substring of the same words.
    best: dict[str, tuple[int, str]] = {}
    for length, key, value in candidates:
        if key not in best or length > best[key][0]:
            best[key] = (length, value)

    types = {row.spec_key: row.data_type for row in rows}
    brand_binding: str | None = None
    brand_span: tuple[int, int] | None = None
    if "brand" not in best:
        brand_binding, brand_span = _brand_match_in_haystack(
            haystack, rows, brand_names(db) if brands is None else brands
        )
    spans: dict[str, list[tuple[int, int]]] = {}
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
        # The winning value's own spans: where the customer SAID this.
        spans[key] = list(spoken_spans.get((key, best[key][1]), []))

    # A brand is a brand. The registry's `brand` row ships with an empty synonym map,
    # so "sorento" bound to nothing and the word was left to the code probes, which
    # prefix-matched it into SORENTOBAG and SORENTO188 (live turn 12303509). The names
    # are read from the `brands` table rather than hand-seeded into the registry, so a
    # brand added tomorrow is understood the same day, spelled exactly as the catalog
    # spells it - which is the spelling the derived `brand` values carry.
    if brand_binding is not None:
        resolved.append({"key": "brand", "value": brand_binding})
        spans["brand"] = [brand_span] if brand_span else []

    # Numbers the customer typed: "trap 200mm", "thickness 1.2mm", 'S trap 8"'.
    # A value stated in WORDS wins over one bound by proximity — "double bowl" is a
    # direct statement, a nearby number is an inference about which measurement was
    # meant.
    already = {entry["key"] for entry in resolved}
    consumed = [
        span
        for key, (_, value) in best.items()
        for span in spoken_spans.get((key, value), [])
    ]
    for key, value in _resolve_quantities(haystack, rows, consumed).items():
        if key not in already:
            resolved.append({"key": key, "value": value})

    return resolved, spans, haystack


# The words that turn the thing after them into a refusal, in the two languages the
# catalogue's customers write in. Single source of truth: `product_spec_understanding`
# compiles its `_NEGATORS` pattern from this set, and the set is also folded into the
# stopwords below, so a word that layer READS as a refusal can never be reported back
# as one we did not understand. It lives here because the import runs one way only
# (understanding imports search, never the reverse).
NEGATOR_WORDS: frozenset[str] = frozenset({"not", "no", "without", "non", "bukan", "tanpa"})

# Words that name nothing about a product and are never reported. Small and inline
# on purpose: this whole helper is precision-first, and the cost of the two errors
# is nowhere near symmetric. Telling a customer "I don't know what 'kitchen' means"
# destroys the conversation; missing one alien word costs a clarifying question we
# were going to be able to answer anyway.
_PHRASE_STOPWORDS: frozenset[str] = NEGATOR_WORDS | frozenset(
    {
        "the", "a", "an", "and", "or", "for", "in", "of", "to", "with", "without",
        "me", "my", "i", "we", "is", "are", "it", "this", "that", "there",
        "any", "some", "all", "want", "wanted", "need", "have", "has", "got",
        "looking", "look", "find", "get", "send", "show", "please", "can", "you",
        "do", "does", "like", "would", "also", "just", "about", "price",
    }
)

# Shorter than this and a word carries no reportable meaning: "hi", "ok", "no" and
# every stray letter left by punctuation would otherwise read as alien.
_MIN_REPORTABLE_WORD = 3


def _search_vocabulary(
    db: Session, *, registry_rows=None, brands: list[str] | None = None
) -> frozenset[str]:
    """Every WORD the catalogue's own vocabulary contains.

    Multi-word phrases are split, so "kitchen sink" whitelists both halves: a
    customer writes one word at a time and the sentence they wrote is the only
    thing being checked. Three sources, the same three a term is resolved
    against - the registry (keys, values and their synonyms), the class
    vocabulary (labels, category search synonyms, values products actually
    carry), and the brand names.
    """
    words: set[str] = set()

    def absorb(text) -> None:
        for word in re.split(r"[^a-z0-9]+", str(text or "").lower()):
            if word:
                words.add(word)

    for row in (active_registry(db) if registry_rows is None else registry_rows):
        absorb(row.spec_key)
        absorb(row.label)
        for value, synonyms in merged_synonyms(row).items():
            if value != SELF_SYNONYM_KEY:
                absorb(value)
            for synonym in synonyms:
                absorb(synonym)
        for value in merged_allowed_values(row):
            absorb(value)

    categories = (
        db.query(ProductCategory.class_label, ProductCategory.search_synonyms)
        .filter(ProductCategory.is_searchable.is_(True))
        .all()
    )
    for label, synonyms in categories:
        absorb(label)
        for synonym in synonyms or []:
            absorb(synonym)
    for label in stored_class_labels(db):
        absorb(label)

    for name in (brand_names(db) if brands is None else brands):
        absorb(name)

    return frozenset(words)


def _content_words(phrase: str) -> list[str]:
    """The words in `phrase` that could carry product meaning, in order.

    A number is never one of them: "1.2mm" and "820" are measurements, and a
    token with a digit in it is either that or a product code - and a code is
    reported through `unresolved_tokens`, which is the channel that can say
    "I could not find that code" rather than "I do not know that word".
    """
    seen: list[str] = []
    for raw in re.split(r"[^a-z0-9.]+", (phrase or "").lower()):
        word = raw.strip(".")
        if not word or word in seen:
            continue
        if len(word) < _MIN_REPORTABLE_WORD:
            continue
        if word in _PHRASE_STOPWORDS:
            continue
        if any(character.isdigit() for character in word):
            continue
        seen.append(word)
    return seen


def unrecognized_words(
    db: Session,
    phrase: str,
    *,
    vocabulary: frozenset[str] | None = None,
    registry_rows=None,
    brands: list[str] | None = None,
) -> list[str]:
    """Words in the sentence that name nothing this catalogue knows.

    The honest counterpart to `unmet`: a key the customer named and no product
    could answer is one sentence ("thickness isn't recorded for these"), and a
    word that bound to nothing at all is a different one ("I don't know what
    'flurbish' means"). Reported in the order they were written, once each.

    Word level, not term level, because the raw free term IS the whole sentence
    once the CRM reads it itself - checking the term would only ever report the
    customer's entire message back at them.
    """
    known = (
        _search_vocabulary(db, registry_rows=registry_rows, brands=brands)
        if vocabulary is None
        else vocabulary
    )
    return [word for word in _content_words(phrase) if word not in known]


def unrecognized_terms(
    db: Session,
    *,
    query: str | None = None,
    free_terms: list[str] | None = None,
    registry_rows=None,
    brands: list[str] | None = None,
) -> list[str]:
    """Everything in the request that bound to nothing, ready to be read out.

    A term the CALLER supplied is reported VERBATIM when every content word in
    it is alien: they sent "flurbish grommet" as one thing, so answering with
    two mystery words would misdescribe their own question. Its words are then
    dropped from the word-level list, so each unhonourable thing is named once.

    A term that is only PARTLY alien is reported word by word instead. Skipping
    it - which is what a term-level check does - meant "sink flurbish" arrived as
    one caller term and the mystery word inside it was never named at all, so a
    request that could not be honoured read as a clean success.
    """
    vocabulary = _search_vocabulary(db, registry_rows=registry_rows, brands=brands)
    reported = unrecognized_words(db, query or "", vocabulary=vocabulary)

    for term in free_terms or []:
        phrase = str(term or "").strip()
        if not phrase or phrase in reported:
            continue
        content = _content_words(phrase)
        alien = [word for word in content if word not in vocabulary]
        if not alien:
            continue
        if len(alien) == len(content):
            reported = [word for word in reported if word not in content]
            reported.append(phrase)
            continue
        for word in alien:
            if word not in reported:
                reported.append(word)

    return reported


def filter_specs(db: Session, *, specs: list[dict] | None = None, free_terms: list[str] | None = None) -> dict:
    """The described set as a MEMBERSHIP clause — shape B's filter leg.

    Class-only by decision: class coverage is broad, so a class filter is safe;
    spec-VALUE derivation is partial, so a value filter silently undercounts, and
    numeric entries carry ops (at_least, tolerance windows) that have no boolean
    meaning. Non-class entries are dropped here and still reach the ranker as
    boosts, so the customer's number is heard, just not membership-defining.

    Three verdicts per word, because n8n renders them differently:
      - names a class            -> membership
      - names a known spec value -> dropped (recognized, boost-only)
      - names nothing            -> `unrecognized_terms` (clarify, never "none")

    The third verdict is reached WORD by word, not term by term. A term that
    bound something can still carry an alien word inside it - "sorento grommet"
    resolves the brand and says nothing about the grommet - and a term-level
    check called that a success, so the one thing the CRM could not honour was
    the one thing it never mentioned. A term whose every content word is alien
    is still reported verbatim: they asked it as one thing.

    Returns `{"clause", "class_labels", "unrecognized_terms"}`; `clause` is a
    predicate over `ProductSpecifications.values`, or None when no class was named.
    """
    free_terms = [t for t in (free_terms or []) if t and t.strip()]

    labels: set[str] = set()
    for entry in specs or []:
        if entry.get("key") == "class" and entry.get("value"):
            labels.add(str(entry["value"]))

    vocabulary = _search_vocabulary(db) if free_terms else frozenset()
    unrecognized: list[str] = []
    for term in free_terms:
        classes = resolve_classes_for_term(db, term)
        if classes:
            labels.update(classes)
        content = _content_words(term)
        alien = [word for word in content if word not in vocabulary]
        if content and len(alien) == len(content):
            if term not in unrecognized:
                unrecognized.append(term)
            continue
        for word in alien:
            if word not in unrecognized:
                unrecognized.append(word)

    clause = None
    if labels:
        # Scalar branch is case-insensitive, matching the ranker's `_states`. The
        # containment branch (case-sensitive, against the stored spelling the
        # resolvers returned) exists because a value may be a LIST — two finishes
        # on one product — and `#>>` renders a list as its JSON text.
        lowered = [label.lower() for label in labels]
        scalar = func.lower(ProductSpecifications.values["class"]["value"].astext).in_(lowered)
        contained = [
            ProductSpecifications.values["class"]["value"].op("@>")(cast(literal(json.dumps(label)), JSONB))
            for label in sorted(labels)
        ]
        clause = or_(scalar, *contained)

    return {
        "clause": clause,
        "class_labels": sorted(labels),
        "unrecognized_terms": unrecognized,
    }


def _is_excluded(values: dict, exclusions: list[dict]) -> bool:
    """True when the product is KNOWN to hold a value the customer ruled out."""
    for entry in exclusions or []:
        key, refused = entry.get("key"), entry.get("value")
        if key is None or refused is None:
            continue
        stored = values.get(key)
        if not isinstance(stored, dict):
            continue
        actual = stored.get("value")
        if actual is None:
            continue
        # A two-tone product holding a refused tone is still refused.
        if _states(actual, refused):
            return True
    return False


def _fails_threshold(values: dict, specs: list[dict]) -> bool:
    """True when the product is known to be on the wrong side of a stated limit."""
    for entry in specs or []:
        op = str(entry.get("op") or "")
        if op not in {"at_least", "at_most"}:
            continue
        key, target = entry.get("key"), entry.get("value")
        stored = values.get(key) if key else None
        if not isinstance(stored, dict) or not isinstance(target, (int, float)):
            continue
        actual = stored.get("value")
        if not isinstance(actual, (int, float)):
            continue
        if op == "at_least" and float(actual) < float(target):
            return True
        if op == "at_most" and float(actual) > float(target):
            return True
    return False


def search_specs(
    db: Session,
    *,
    specs: list[dict] | None = None,
    exclusions: list[dict] | None = None,
    free_terms: list[str] | None = None,
    limit: int | None = None,
    floor: float | None = None,
    product_ids: list[str] | None = None,
) -> dict:
    """Rank the catalog against extracted specs. Returns candidates and a floor verdict.

    `exclusions` are specs the customer refused. They are a filter rather than a
    negative weight: see the comment at the candidate loop.

    `product_ids` restricts ranking to a caller-supplied whitelist (shape B's
    stage 2: membership was decided in SQL, the ranker only ORDERS what already
    qualifies). None means the whole catalog; an empty list ranks nothing.
    """
    specs = specs or []
    exclusions = exclusions or []
    free_terms = [t for t in (free_terms or []) if t and t.strip()]

    policy = search_policy(db)
    class_boost = policy["class_boost"]
    free_term_boost = policy["free_term_boost"]
    numeric_boost = policy["numeric_boost"]
    mismatch_penalty = policy["mismatch_penalty"]
    discontinued_penalty = policy["discontinued_penalty"]
    # How much more a spec is worth for WHERE IT CAME FROM, keyed by source rather than
    # branched on one of them: the flyer is not the only source better than a parsed
    # description, and a hardcoded flyer test would turn PR 4's promotion of flyer
    # values to authored ones into a silent demotion. An unlisted source multiplies by
    # 1, so `derived` and `category` are untouched.
    # Authored sources take the shared authored knob as their DEFAULT, then any source
    # with a knob of its own overwrites it. That order is the point: `flyer` joins
    # `AUTHORED_SOURCES` in the later flyer-ingestion slice (AC-F.7), and building the
    # authored defaults last would silently collapse `flyer_source_boost` into
    # `human_source_boost` on that one-line membership change, which AC-F.10 requires to
    # stay separately tunable. Nothing would fail; the ranking would just move.
    human_source_boost = policy.get("human_source_boost", 1.0)
    source_boosts = {authored: human_source_boost for authored in AUTHORED_SOURCES}
    source_boosts["flyer"] = policy.get("flyer_source_boost", 1.0)
    if floor is None:
        floor = policy["relevance_floor"]
    if limit is None:
        limit = int(policy["max_candidates"])

    registry_rows = active_registry(db)
    # A standing preference for particular values - "our own brand first". Keyed by
    # spec key, then by the value in the catalog's own spelling.
    house_preferences = {
        row.spec_key: {str(k).lower(): float(v) for k, v in (row.value_weights or {}).items()}
        for row in registry_rows
        if row.value_weights
    }
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
    # The word-level resolver sees "not glass" as the word "glass" and nothing else, so
    # anything the customer refused has to be withheld from it. Without this the refusal
    # is undone one line after it was understood.
    refused = {(e.get("key"), str(e.get("value")).strip().lower()) for e in exclusions}
    specs = specs + [
        e
        for e in resolve_terms_to_specs(db, free_terms)
        if e["key"] not in stated
        and (e["key"], str(e.get("value")).strip().lower()) not in refused
    ]

    # A free term that names a class IS a class match, and class is the strongest
    # signal we have. Without this, "sink" scored one weak text hit and fell below the
    # floor, so the single most natural query in the corpus returned nothing.
    implied_classes = {
        label.lower()
        for term in free_terms
        for label in resolve_classes_for_term(db, term)
    }

    candidate_query = (
        db.query(ProductSpecifications, Product, ProductCategory)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
        .filter(Product.is_active.is_(True))
    )
    if product_ids is not None:
        candidate_query = candidate_query.filter(
            ProductSpecifications.product_id.in_(list(product_ids))
        )
    rows = candidate_query.all()

    wanted_terms: set[str] = set()
    for term in free_terms:
        wanted_terms |= _tokens(term)


    scored: list[dict] = []
    for spec_row, product, category in rows:
        values = spec_row.values or {}
        # Where each value was read from, so the flyer can outweigh the description.
        provenance = spec_row.provenance or {}

        # A refusal removes a product; it never merely demotes it. Showing a glass basin
        # to someone who said "not glass" is not a ranking mistake, it is an answer to a
        # question nobody asked, and no amount of penalty makes it acceptable at rank 5.
        #
        # It bites ONLY on a value the product is KNOWN to hold. A product whose material
        # was never derived is not excluded - absence of a word is not evidence of the
        # thing, which is this module's standing rule everywhere else too, and the strict
        # reading would silently drop most of the catalog for any refusal.
        if _is_excluded(values, exclusions):
            continue

        # A threshold the product is KNOWN to fail removes it, for the same reason a
        # refusal does: "above 900mm" is the customer saying 850mm is not what they
        # want. Demoting it merely was not enough - the 850mm basins still matched
        # `free_standing` and outranked the one basin that actually cleared 900.
        #
        # Unknown is not failure. A product with no height is not excluded by a height
        # threshold, which is the same rule the rest of this module follows.
        if _fails_threshold(values, specs):
            continue

        score = 0.0
        # What the CUSTOMER'S OWN WORDS earned, kept apart from the total.
        #
        # `score` also carries the house preference, which is a standing merchandising
        # thumb on the scale and is added to every product that qualifies for it
        # whatever the customer said. Mixing the two made the relevance floor
        # unreachable: "hi" extracts nothing, matches nothing, and still scored 8.0 on
        # every Sorento product, so a greeting came back as five arbitrary products
        # presented as answers. A preference can reorder answers; it cannot BE one.
        evidence = 0.0
        # Penalties are accumulated apart from the boosts so that "did this product
        # match anything at all" stays answerable after they are applied.
        penalty = 0.0
        matched: list[str] = []
        # Keys the HOUSE put there, kept apart from the ones the customer earned.
        # Reported separately for the same reason the score is split: a renderer
        # reading "matched: brand" could not tell "you asked for Sorento" from "we
        # like Sorento", and told the customer they had asked for something they
        # never said.
        preferred: list[str] = []

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
            # A spec the FLYER states outranks one merely mentioned in a description.
            # The flyer is the curated source and frequently the only one: 14 cards say
            # FRAMELESS where 2 descriptions do, 9 say MASSAGE JET where none do. Without
            # this, a product whose flyer card names the exact spec tied with one whose
            # description happens to contain the word, and lost on alphabetical order.
            # A spec a person set outranks both, on its own knob.
            source = (provenance.get(key) or {}).get("source")
            if source:
                weight *= source_boosts.get(source, 1.0)
            if key == "class":
                if _states(actual, target):
                    score += class_boost
                    evidence += class_boost
                    matched.append(key)
            elif (
                isinstance(actual, (int, float, Decimal))
                and isinstance(target, (int, float, Decimal))
                and not isinstance(actual, bool)
            ):
                tolerance, decay = match_windows.get(key, (0.0, 0.0))
                # "above 900mm" is a THRESHOLD, not an approximate equality. Scored as
                # equality, a 960mm basin sat 60mm from the target and a 850mm one sat
                # 50mm from it, so the basin that actually cleared 900 ranked BELOW the
                # ones that did not - the opposite of what was asked for.
                gain = _threshold_score(
                    str(entry.get("op") or "about"),
                    float(target),
                    float(actual),
                    tolerance,
                    decay,
                )
                if gain > 0:
                    score += numeric_boost * weight * gain
                    evidence += numeric_boost * weight * gain
                    # Anywhere inside the tolerance band counts as answering the
                    # question. Closeness only orders the products that all do.
                    if gain >= 1.0 - _EXACTNESS_MARGIN:
                        matched.append(key)
                else:
                    # Stated, stored, and outside the window entirely. A number can
                    # contradict exactly as an enum can — without this a one-bowl sink
                    # merely scored zero on bowl_count and still won on its other
                    # signals, which is what put it above real double-bowl sinks.
                    penalty += mismatch_penalty
            elif _states(actual, target):
                score += weight
                evidence += weight
                matched.append(key)
            else:
                # Stated, stored, and different. Not the same thing as unstated: a
                # product with NO mounting is merely unknown and stays neutral, but one
                # that is explicitly floor standing contradicts "wall hung" and must not
                # outrank a product that matches it.
                penalty += mismatch_penalty

        # A free term naming this product's class counts as a class match.
        class_value = str((values.get("class") or {}).get("value") or "").lower()
        if implied_classes and class_value and class_value in implied_classes:
            if "class" not in matched:
                score += class_boost
                evidence += class_boost
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
                score += free_term_boost * len(hits)
                evidence += free_term_boost * len(hits)
                matched.append("free_terms")


        # House preference. Applied only where the customer did NOT name the key
        # themselves: someone asking for Bravat is asking for Bravat, and a preference
        # that outranked their own words would be a bug wearing a boost's clothes.
        # It is a tie-breaker by design - it lands on top of whatever the specs scored,
        # so it reorders equally-good answers without promoting a worse one.
        for key, weighted in house_preferences.items():
            if key in stated:
                continue
            held = str((values.get(key) or {}).get("value") or "").lower()
            bonus = weighted.get(held)
            if bonus:
                score += bonus
                preferred.append(key)

        # Discontinued still sells - it is ranked below a live equivalent, not hidden.
        # Applied as a PENALTY rather than a filter for the same reason as everything
        # else here: a discontinued product that answers the question beats a live one
        # that does not.
        is_discontinued = bool(product.is_discontinued)
        if is_discontinued:
            penalty += discontinued_penalty

        score -= penalty

        # Dropped for having NO positive evidence, never for scoring badly. A penalty
        # that can delete a row is a filter wearing a boost's clothes, and this file's
        # first rule is that one over-extracted spec must not empty the shortlist: a
        # floor-standing WC still answers "wall hung water closet" better than silence,
        # it just answers it last.
        #
        # Evidence, NOT the total: on the total, every Sorento product in the catalog
        # cleared this line on the house preference alone and the shortlist was never
        # empty for anything.
        if evidence <= 0:
            continue

        scored.append(
            {
                "product_id": str(product.id),
                "product_code": product.product_code,
                "summary": _summarise(values, spec_row.rendered_text),
                "class": (values.get("class") or {}).get("value"),
                # What this product IS, values only. The shortlist has to be able to
                # say "this one is 1.2mm, that one 1.0mm" or the customer cannot tell
                # the rows apart, and a code is not an answer to a description.
                # Evidence, provenance and unit stay behind: they are review data,
                # and this rides a reply path.
                "specifications": values_only(values),
                # What the customer's OWN WORDS earned. A house preference is
                # reported next door, never here (see `preferred`).
                "matched_specs": sorted(set(matched)),
                "preferred_specs": sorted(set(preferred)),
                "score": round(score, 4),
                # Kept only to test the floor, then dropped before the caller sees it.
                "_evidence": round(evidence - penalty, 4),
                "is_discontinued": is_discontinued,
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
    # The floor asks "did the customer's words find anything", so it is measured on the
    # evidence and not on the total. Scored on the total, a standing brand preference
    # of 8.0 sat above a floor of 1.5 on its own and the answer to "is there anything
    # here" was permanently yes.
    # Read BEFORE the pop below, which is the only reason the number is still here.
    top_evidence = max((c["_evidence"] for c in top), default=0.0)
    floor_missed = (not top) or top_evidence < floor
    for candidate in collapsed:
        candidate.pop("_evidence", None)

    # WHAT THE CUSTOMER ASKED FOR AND DID NOT GET.
    #
    # Every spec is a boost, never a filter, which is right: "cabana free standing
    # bathtub" should still offer the Sorento ones rather than nothing. But offering
    # them silently reads as a broken search - the customer said Cabana and got Sorento
    # with no acknowledgement. Nothing in the result said "there is no Cabana one", so
    # the only available conclusion was that the engine ignored them.
    #
    # A key is unmet when it was ASKED FOR and NO offered product matches it. Computed
    # over what is actually shown, not the whole catalog: a product that exists but did
    # not make the shortlist is not something the customer can see.
    shown = [] if floor_missed else top
    asked = {
        str(entry["key"]): entry.get("value")
        for entry in specs
        if entry.get("key") and entry.get("value") is not None
    }
    satisfied = {key for candidate in shown for key in candidate["matched_specs"]}
    unmet = [
        {"key": key, "value": value}
        for key, value in asked.items()
        if key not in satisfied
    ]

    return {
        "candidates": shown,
        "floor_missed": floor_missed,
        "top_score": top[0]["score"] if top else 0.0,
        # The quantity the floor was actually tested against, so a caller can tell
        # "there is nothing" (0.0) from "something scored and none of it cleared the
        # bar" (non-zero) - two answers `floor_missed` collapses into one bool while
        # emptying the list that would otherwise show the difference.
        #
        # Deliberately NOT `top_score`, which carries the house preference: a product
        # nobody described would report a near miss it never earned, which is the
        # permanently-yes bug the floor itself was moved onto evidence to kill.
        "top_evidence": top_evidence,
        "asked_for": [{"key": k, "value": v} for k, v in asked.items()],
        "unmet": unmet,
    }
