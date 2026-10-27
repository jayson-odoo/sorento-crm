"""One parser for a multi-select list filter's query param (FILTER-MULTISELECT).

A dropdown filter on a list carries one or more values, OR-ed within the filter. The frontend
sends them comma-joined in one param (``status=draft,submitted``); a deep link or an older client
may repeat the param (``status=draft&status=submitted``) or send a single value. Declare the param
as ``Optional[list[str]] = Query(None)`` and pass it here: every shape reads the same.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Optional

from app.services.error_handler import handle_unprocessable


def multi_values(raw: Iterable[str] | str | None) -> Optional[list[str]]:
    """The distinct non-blank values, in the order given; None when there are none (no filter)."""
    if raw is None:
        return None
    items = [raw] if isinstance(raw, str) else raw
    out: list[str] = []
    for item in items:
        for part in str(item or "").split(","):
            value = part.strip()
            if value and value not in out:
                out.append(value)
    return out or None


def multi_text(raw: Iterable[str] | str | None) -> Optional[list[str]]:
    """``multi_values`` for FREE-TEXT values (a class label, a spec value), which can contain commas.

    The frontend sends these as repeated params, one value each, read whole. An item is split on
    commas only when it is a legacy comma-joined list of plain values ("Tap,Basin"); an item with a
    comma followed by a space ("Sink, Undermount", `["Gold", "Matt Black"]`) is one value.
    """
    if raw is None:
        return None
    items = [raw] if isinstance(raw, str) else raw
    out: list[str] = []
    for item in items:
        text = str(item or "")
        parts = [text] if ", " in text else text.split(",")
        for part in parts:
            value = part.strip()
            if value and value not in out:
                out.append(value)
    return out or None


def multi_uuids(raw: Iterable[str] | str | None, label: str) -> Optional[list[str]]:
    """``multi_values`` for ids: each must be a UUID, else a 422 naming the filter."""
    values = multi_values(raw)
    if values is None:
        return None
    try:
        return [str(uuid.UUID(v)) for v in values]
    except ValueError:
        raise handle_unprocessable(f"{label}: not a valid id") from None
