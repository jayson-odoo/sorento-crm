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


def classify_text(text: Optional[str], types: Iterable[PromotionType]) -> Optional[PromotionType]:
    """The type *text* names, or the default type, or None when no types exist.

    Split from `classify_promotion_type` so a caller holding the type rows (a
    backfill over thousands of promotions, a test) can classify without a query
    per row.
    """
    type_list = list(types)
    if not type_list:
        return None
    normalized = _normalize(text)
    if normalized:
        for promo_type in sorted(
            type_list, key=lambda t: (t.match_priority or 100, t.type_code or "")
        ):
            markers = promo_type.match_markers or []
            if not isinstance(markers, list):
                continue
            for marker in markers:
                if isinstance(marker, str) and _marker_matches(normalized, marker):
                    return promo_type
    return default_type(type_list)


def classify_promotion_type(
    db: Session,
    *,
    description: Optional[str] = None,
    filename: Optional[str] = None,
) -> Optional[PromotionType]:
    """Classify one promotion from the name we were given.

    *filename* wins when present: the upload path runs the original name through
    `sanitize_storage_filename`, so the attachment's `original_filename` is the
    closest thing to what marketing actually typed.
    """
    return classify_text(filename or description, list_types_for_matching(db))
