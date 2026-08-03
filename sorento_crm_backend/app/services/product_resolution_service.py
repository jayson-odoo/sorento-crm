"""Turning what a consumer typed into a product, or honestly into nothing (AC-C16 to C18).

A consumer reads a model code off a receipt, a carton, or the underside of a tap. What
arrives is `SRTWC8152`, `WC189-G2`, `SRTWC8517-200mm`, or "the tap in my kitchen". None of
those is a `products.product_code`.

**The answer is a state, never a score** - the same decision as `dealer_resolution_service`,
for the same reason. A float invites every caller to invent a cutoff, and a wrong variant is
a wrong warranty term on the line: the `SRTWC8152` family is three real products whose parts
differ.

    exact       one product, certain.
    ambiguous   a real base code covering SEVERAL variants. `product_id` stays NULL and the
                KIND answers instead (ADR-0010). Common, and not an error.
    candidates  nothing exact; near neighbours worth showing CS.
    unmatched   nothing to go on. The line still lodges (AC-C14).

**The rungs are tried in order and an earlier one always wins.** Each is a shape a consumer
actually produces, not a guess at one:

    1. exact code
    2. dash-strip          `SRTWC8152RLRG` for `SRTWC8152-RL-RG`
    3. `SRT` prefix        `WC189-G2` for `SRTWC189-G2` - the carton prints the short form
    4. trailing unit       `SRTWC8517-200mm` for `SRTWC8517-200`
    5. base-code prefix    `SRTWC8152` covering the family -> ambiguous
    6. trigram neighbours  candidates only, never exact

Rungs 2 to 4 fire ONLY when they land on exactly one product. Two products that differ only
in punctuation were distinguished by that punctuation, so dropping it cannot be a confident
answer.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

STATE_EXACT = "exact"
STATE_AMBIGUOUS = "ambiguous"
STATE_CANDIDATES = "candidates"
STATE_UNMATCHED = "unmatched"

# Sorento's catalogue prefix. ADDED to what the consumer typed, never stripped from what
# the catalogue stores: adding only narrows to this brand, whereas stripping would collide
# every `SRTWCnnn` with a `WCnnn` that could belong to anyone.
BRAND_PREFIX = "SRT"

# Units a consumer appends to a dimension that is already part of the code.
_TRAILING_UNIT = re.compile(r"(mm|cm|inch|in|\")\s*$", re.IGNORECASE)

# A code is letters and digits. Free text is not, and "the tap in my kitchen" must reach
# `unmatched` rather than the nearest of several thousand rows.
_LOOKS_LIKE_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_/. ]*$")
_HAS_DIGIT = re.compile(r"\d")

# Worth showing CS, not worth asserting. Below this a suggestion is noise.
CANDIDATE_AT = 0.45
MAX_CANDIDATES = 8


@dataclass(frozen=True)
class ProductMatch:
    """What the caller gets. `typed_code` always survives (AC-C14)."""

    state: str
    typed_code: Optional[str]
    product_id: Optional[str] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    # Populated for `ambiguous` and `candidates`. Ordered by product_code so two
    # identical receipts produce identical screens.
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    # Which rung answered. Diagnostic only, never a threshold for a caller.
    matched_by: Optional[str] = None


def _squash(value: str) -> str:
    """Letters and digits only, uppercased. The comparison key for rungs 2 to 5."""
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def _catalogue(db: Session) -> List[Tuple[str, str, str, str]]:
    """(id, product_code, product_name, squashed) for every active product.

    Loaded and compared in Python rather than in SQL because the same normalisation has
    to hold for the portal, the extract endpoint and the CS screen. Expressed as a
    Postgres function it would be a second copy of these rules in a second language, and
    the day they drift the two surfaces name different products for one receipt.
    """
    from app.models.product import Product

    rows = (
        db.query(Product.id, Product.product_code, Product.product_name)
        .filter(Product.is_active.is_(True))
        .all()
    )
    return [
        (str(pid), str(code), str(name or ""), _squash(str(code)))
        for pid, code, name in rows
        if code
    ]


def _as_candidate(row: Tuple[str, str, str, str]) -> Dict[str, Any]:
    return {"product_id": row[0], "product_code": row[1], "product_name": row[2]}


def _sorted(rows: List[Tuple[str, str, str, str]]) -> List[Tuple[str, str, str, str]]:
    """By product_code. Deterministic, and never by database order - `q.all()` carries no
    guarantee, so an unsorted list reshuffles between page loads.
    """
    return sorted(rows, key=lambda row: row[1])


def _trigrams(value: str) -> set:
    padded = f"  {value} "
    return {padded[i : i + 3] for i in range(len(padded) - 2)}


def _similarity(left: str, right: str) -> float:
    a, b = _trigrams(left), _trigrams(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _unique(rows: List[Tuple[str, str, str, str]], typed: str, rung: str) -> Optional[ProductMatch]:
    """An exact answer only when the rung lands on exactly one product."""
    if len(rows) != 1:
        return None
    row = rows[0]
    return ProductMatch(
        state=STATE_EXACT,
        typed_code=typed,
        product_id=row[0],
        product_code=row[1],
        product_name=row[2],
        matched_by=rung,
    )


def resolve_product(db: Session, typed_code: Optional[str]) -> ProductMatch:
    """Which product, if any, this typed code names."""
    typed = str(typed_code) if typed_code is not None else None
    probe = (typed or "").strip()
    if not probe:
        return ProductMatch(state=STATE_UNMATCHED, typed_code=typed)

    # A model code has a digit in it and no sentence punctuation. "the tap in my kitchen"
    # stops here, which is the honest answer: the Kind chooser is what resolves it.
    if not _LOOKS_LIKE_CODE.match(probe) or not _HAS_DIGIT.search(probe):
        return ProductMatch(state=STATE_UNMATCHED, typed_code=typed)

    try:
        catalogue = _catalogue(db)
    except Exception as exc:  # pragma: no cover - a lookup failure is not a match
        logger.warning("Product catalogue load failed: %s", exc)
        return ProductMatch(state=STATE_UNMATCHED, typed_code=typed)
    if not catalogue:
        return ProductMatch(state=STATE_UNMATCHED, typed_code=typed)

    upper = probe.upper()
    squashed = _squash(probe)

    # -- rung 1: the literal code. Always wins; every later rung is a repair, and a
    # repair must never overrule something that needed none.
    literal = [row for row in catalogue if row[1].upper() == upper]
    hit = _unique(literal, typed, "exact")
    if hit is not None:
        return hit

    # -- rung 2: punctuation. Only when it lands on one product: two codes that differ
    # only in dashes were distinguished by those dashes.
    hit = _unique([row for row in catalogue if row[3] == squashed], typed, "dash_strip")
    if hit is not None:
        return hit

    # -- rung 3: the carton prints `WC189-G2`, the catalogue stores `SRTWC189-G2`.
    if not squashed.startswith(BRAND_PREFIX):
        prefixed = BRAND_PREFIX + squashed
        hit = _unique([row for row in catalogue if row[3] == prefixed], typed, "brand_prefix")
        if hit is not None:
            return hit

    # -- rung 4: `SRTWC8517-200mm`. The 200 is the code; the mm is the consumer helping.
    trimmed = _TRAILING_UNIT.sub("", probe).strip()
    if trimmed and trimmed != probe:
        trimmed_squashed = _squash(trimmed)
        hit = _unique(
            [row for row in catalogue if row[3] == trimmed_squashed], typed, "unit_strip"
        )
        if hit is not None:
            return hit
        if not trimmed_squashed.startswith(BRAND_PREFIX):
            hit = _unique(
                [row for row in catalogue if row[3] == BRAND_PREFIX + trimmed_squashed],
                typed,
                "unit_strip_brand_prefix",
            )
            if hit is not None:
                return hit

    # -- rung 5: the family. `SRTWC8152` covers SRTWC8152-RL-RG, -SH and -300-RL.
    # A prefix rule, deliberately not a fuzzy one: `SRTWC8152` must not reach
    # `SRTWC8153`, which is a different product with a different warranty.
    for stem in (squashed, BRAND_PREFIX + squashed if not squashed.startswith(BRAND_PREFIX) else None):
        if not stem:
            continue
        family = _sorted([row for row in catalogue if row[3].startswith(stem)])
        if len(family) == 1:
            # One member is not a family. Withholding here costs the consumer an edit
            # for nothing.
            return ProductMatch(
                state=STATE_EXACT,
                typed_code=typed,
                product_id=family[0][0],
                product_code=family[0][1],
                product_name=family[0][2],
                matched_by="base_code",
            )
        if len(family) > 1:
            # THE ADR-0010 case. `product_id` stays NULL and the Kind answers.
            return ProductMatch(
                state=STATE_AMBIGUOUS,
                typed_code=typed,
                candidates=[_as_candidate(row) for row in family[:MAX_CANDIDATES]],
                matched_by="base_code",
            )

    # -- rung 6: neighbours. Shown, never asserted.
    scored = [
        (_similarity(row[3], squashed), row)
        for row in catalogue
    ]
    near = _sorted([row for score, row in scored if score >= CANDIDATE_AT])
    if near:
        return ProductMatch(
            state=STATE_CANDIDATES,
            typed_code=typed,
            candidates=[_as_candidate(row) for row in near[:MAX_CANDIDATES]],
            matched_by="trigram",
        )

    return ProductMatch(state=STATE_UNMATCHED, typed_code=typed)
