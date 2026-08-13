"""Document numbers carrying the portal revision (UAC ``portal-submission-revisions`` section N).

One module, two functions, so render and parse can never disagree about the
suffix format (UAC N7):

* :func:`display_document_number` - ``SI-26-0184`` at revision 2 reads
  ``SI-26-0184-R2``. Used by every OUTBOUND surface: notifications, chat and
  message builders, external API responses, and both PDF services (document body
  AND filename).
* :func:`strip_revision_suffix` - the inverse, applied at every INBOUND
  lookup-by-number.

**The stored number never changes** (UAC N2). ``inquiry_number`` stays
``SI-26-0184``; the suffix is derived from ``revision_no`` at render time. That
keeps every index, import and existing row untouched, and confines the cost of
the feature to the two functions below.

Why the strip half exists (UAC N6): the external API create endpoints use the
document number as a resubmit key - ``POST /api/v1/external/stock-inquiries``
and its purchase-request twin look the number up and, on a match with a rejected
row, UPDATE it instead of inserting. An external caller that echoes back a
number it read from one of our payloads - now carrying ``-R2`` - would miss the
row and **insert a duplicate**. Silent data duplication on a live integration
path, not a visible 404.

``revision_no = 0`` renders bare, with no ``-R0`` (UAC N3).
"""
from __future__ import annotations

import re
from typing import Any, Optional

# A trailing revision marker. Anchored at the end and case-insensitive; no
# document number this system mints ends in "-R<digits>" natively, so this can
# only ever match a suffix we rendered.
REVISION_SUFFIX_RE = re.compile(r"-R(\d+)$", re.IGNORECASE)

# Where a document number lives, per entity, in the order they are probed. One
# list rather than a per-caller guess, so a row from any revisable type renders
# through the same path.
NUMBER_ATTRS: tuple[str, ...] = (
    "inquiry_number",
    "request_number",
    "complaint_number",
    "ticket_number",
    "document_number",
)

REVISION_NO_ATTR = "revision_no"


def _coerce_revision_no(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def suffix_revision(base: Optional[str], revision_no: Any) -> str:
    """``("SI-26-0184", 2) -> "SI-26-0184-R2"``; revision 0 renders bare.

    The primitive both render paths share: callers holding an ORM row use
    :func:`display_document_number`, callers holding a raw ``(number,
    revision_no)`` pair (batched queries, raw SQL) use this.
    """
    text = (base or "").strip()
    if not text:
        return ""
    revision = _coerce_revision_no(revision_no)
    if revision <= 0:
        return text
    # Never stack a suffix: a caller that already rendered one (or a stored value
    # that somehow carries one) must not come out as "SI-26-0184-R1-R2".
    return f"{strip_revision_suffix(text)}-R{revision}"


def display_document_number(
    row: Any,
    *,
    number_attr: Optional[str] = None,
    revision_no: Any = None,
) -> str:
    """The number as every outbound surface must show it (UAC N1/N4).

    ``number_attr`` pins the column when a row carries more than one candidate;
    otherwise the first of :data:`NUMBER_ATTRS` present on the row wins.
    ``revision_no`` overrides the row's own counter (used where the caller
    already holds it, e.g. mid-transaction before a refresh).

    Returns "" when the row has no number, so callers keep their existing
    ``or str(row.id)`` fallbacks working unchanged.
    """
    if row is None:
        return ""
    base: Optional[str] = None
    if number_attr:
        base = getattr(row, number_attr, None)
    else:
        for attr in NUMBER_ATTRS:
            candidate = getattr(row, attr, None)
            if candidate:
                base = candidate
                break
    revision = revision_no if revision_no is not None else getattr(row, REVISION_NO_ATTR, 0)
    return suffix_revision(str(base) if base is not None else None, revision)


def split_revision_suffix(value: Optional[str]) -> tuple[str, Optional[int]]:
    """``"SI-26-0184-R2" -> ("SI-26-0184", 2)``; no suffix -> ``(value, None)``."""
    text = (value or "").strip()
    if not text:
        return "", None
    match = REVISION_SUFFIX_RE.search(text)
    if not match:
        return text, None
    return text[: match.start()], int(match.group(1))


def strip_revision_suffix(value: Optional[str]) -> Optional[str]:
    """The bare stored number, for every lookup-by-number (UAC N6).

    ``None`` passes through as ``None`` so a caller can hand this an optional
    payload field without first testing it.
    """
    if value is None:
        return None
    bare, _revision = split_revision_suffix(str(value))
    return bare
