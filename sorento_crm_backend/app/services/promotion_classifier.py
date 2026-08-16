"""Which kind of promotion an uploaded file is, read off its name.

n8n posts a promotion whose only human-readable identity is the PDF's filename
(`promotions.description`), and the wording in that name is what marketing has
always used to say what kind of offer it is: "SPECIAL" for a one-month clearance,
"PP" for a PP promo, "FOCUS ITEM", "A3 FLYER". Nobody is asked to pick a type at
upload, because the answer is already in the file we were handed.

**The markers live in the database**, on `promotion_types.match_markers`, so a
sixth kind of promotion (or a marker somebody spelled differently) is a row edit
rather than a deploy.

**Matching is on word boundaries, never substrings.** "SUPPLY PROMO" carries the
letters `pp` and is not a PP promo; "SPECIALIST TOOLS" is not a special. A
substring match here would classify a standard offer as one that cannot be used
after expiry, which reads to the customer as a promotion vanishing.

**Collisions resolve conservatively.** Types are evaluated by `match_priority`
ascending and the first match wins; `special` is seeded lowest, so a name
carrying two markers becomes the type that CANNOT be served after its end date.
Promising a price nobody will honour is the expensive mistake; withholding one
that would still have been honoured is a question the customer can ask again.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models.marketing import PromotionType


def _normalize(text: Optional[str]) -> str:
    """Uppercase, with every non-alphanumeric run collapsed to one space.

    Filenames arrive as `_SORENTO A3 FLYER 2025-2026_compressed.pdf` and
    `@ CABANA COMBINE PROMO (OFFICE)_08072026.pdf`; the separators carry no
    meaning, so they all become the same token boundary.
    """
    if not text:
        return ""
    return re.sub(r"[^A-Za-z0-9]+", " ", text).upper().strip()


def _marker_matches(normalized: str, marker: str) -> bool:
    """Whether *marker* appears in *normalized* as a whole token (or token run)."""
    marker_norm = _normalize(marker)
    if not marker_norm or not normalized:
        return False
    pattern = r"(?<![A-Z0-9])" + re.escape(marker_norm) + r"(?![A-Z0-9])"
    return re.search(pattern, normalized) is not None


def list_types_for_matching(db: Session) -> list[PromotionType]:
    """All promotion types, in the order the classifier must consider them."""
    return (
        db.query(PromotionType)
        .order_by(PromotionType.match_priority.asc(), PromotionType.type_code.asc())
        .all()
    )


def default_type(types: Iterable[PromotionType]) -> Optional[PromotionType]:
    """The type standing in for "no marker in the name" (and for unclassified rows)."""
    for t in types:
        if t.is_default:
            return t
    return None


def match_marker_type(
    text: Optional[str], types: Iterable[PromotionType]
) -> Optional[PromotionType]:
    """The type whose marker *text* carries, or None when it carries none.

    Separate from `classify_text` because "this name says nothing" and "this name
    says standard" are different answers: only the first one lets a caller go
    look somewhere else before settling for the default.
    """
    normalized = _normalize(text)
    if not normalized:
        return None
    for promo_type in sorted(
        list(types),
        # `or 100` would treat an explicit priority of 0 as the most permissive
        # slot, which is the opposite of what the admin asked for: the form
        # allows 0 and tells them the lowest number wins. Only a missing value
        # falls back.
        key=lambda t: (
            100 if t.match_priority is None else t.match_priority,
            t.type_code or "",
        ),
    ):
        markers = promo_type.match_markers or []
        if not isinstance(markers, list):
            continue
        for marker in markers:
            if isinstance(marker, str) and _marker_matches(normalized, marker):
                return promo_type
    return None


def classify_text(text: Optional[str], types: Iterable[PromotionType]) -> Optional[PromotionType]:
    """The type *text* names, or the default type, or None when no types exist.

    Split from `classify_promotion_type` so a caller holding the type rows (a
    backfill over thousands of promotions, a test) can classify without a query
    per row.
    """
    type_list = list(types)
    if not type_list:
        return None
    return match_marker_type(text, type_list) or default_type(type_list)


def classify_promotion_type(
    db: Session,
    *,
    description: Optional[str] = None,
    filename: Optional[str] = None,
) -> Optional[PromotionType]:
    """Classify one promotion from the two names we were given.

    *filename* is consulted first and wins outright when it carries a marker: the
    upload path runs the original name through `sanitize_storage_filename`, so
    the attachment's `original_filename` is the closest thing to what marketing
    actually typed.

    A filename carrying NO marker is not an answer, though -- the first
    attachment on the request can be a re-saved, renamed or generic document
    (a T&C page ahead of the flyer), and the marker is then still sitting in the
    posted description. So the description is read before falling back to the
    default type: defaulting a "SPECIAL" upload to standard makes it usable after
    its end date, which is the one mistake this module exists to avoid.
    """
    types = list_types_for_matching(db)
    if not types:
        return None
    return (
        match_marker_type(filename, types)
        or match_marker_type(description, types)
        or default_type(types)
    )
