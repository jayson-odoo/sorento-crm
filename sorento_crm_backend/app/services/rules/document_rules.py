"""Document status derivation (D20, S2): the one rule every channel that can
receive a document with no stated status falls back to - the outstanding
upload's own `_to_activate`/`_complete_documents` distilled to a single,
per-document, pure function so the ESB can share it instead of re-deriving
its own version.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Optional


def _as_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _line_settled(line: dict) -> bool:
    ordered = _as_decimal(line.get("qty_ordered"))
    delivered = line.get("qty_delivered")
    if delivered is None:
        delivered = line.get("qty_received")
    return _as_decimal(delivered) >= ordered


def derive_document_status(lines: list[dict], existing: Optional[str] = None) -> str:
    """The canonical status word for a document that names none of its own.

    `cancelled` is never derived - once a document is cancelled, only an
    explicit status word moves it, never a quantity comparison. Otherwise:
    every line settled (delivered/received >= ordered) is `closed`; anything
    else, including an existing `draft` being lifted the moment AutoCount
    names the document (it is, by definition, no longer a draft the instant
    the system of record states it), is `open`. `lines` are plain dicts
    (`qty_ordered`, `qty_delivered` or `qty_received`) rather than either
    document's own line model, so this has no import on either.
    """
    if existing == "cancelled":
        return "cancelled"
    if lines and all(_line_settled(line) for line in lines):
        return "closed"
    return "open"
