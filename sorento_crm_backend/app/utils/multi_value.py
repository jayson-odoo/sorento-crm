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


MAX_FILTER_VALUES = 200


def _capped(values: list[str], label: str) -> list[str]:
    if len(values) > MAX_FILTER_VALUES:
        raise handle_unprocessable(f"{label}: at most {MAX_FILTER_VALUES} values")
    return values


def multi_values(
    raw: Iterable[str] | str | None, label: str = "filter", *, capped: bool = True
) -> Optional[list[str]]:
    """The distinct non-blank values, in the order given; None when there are none (no filter).
    `capped=False` skips the 200-value cap (the reserve emails' OI list)."""
    if raw is None:
        return None
    items = [raw] if isinstance(raw, str) else raw
    out: list[str] = []
    for item in items:
        for part in str(item or "").split(","):
            value = part.strip()
            if value and value not in out:
                out.append(value)
    return (_capped(out, label) if capped else out) or None


def multi_text(raw: Iterable[str] | str | None, label: str = "filter") -> Optional[list[str]]:
    """The values of a FREE-TEXT filter (a class label, a spec value), which can contain commas.

    The frontend sends one repeated param per value, so every item is ONE value, read whole:
    stripped, deduped, never split. Use ``multi_values`` for ids and codes.
    """
    if raw is None:
        return None
    items = [raw] if isinstance(raw, str) else raw
    out: list[str] = []
    for item in items:
        value = str(item or "").strip()
        if value and value not in out:
            out.append(value)
    return _capped(out, label) or None


def multi_uuids(raw: Iterable[str] | str | None, label: str) -> Optional[list[str]]:
    """``multi_values`` for ids: each must be a UUID, else a 422 naming the filter."""
    values = multi_values(raw, label)
    if values is None:
        return None
    try:
        return [str(uuid.UUID(v)) for v in values]
    except ValueError:
        raise handle_unprocessable(f"{label}: not a valid id") from None


def multi_choices(raw: Iterable[str] | str | None, allowed: Iterable[str], label: str) -> Optional[list[str]]:
    """``multi_values`` for a CLOSED set of codes: each must be one of ``allowed``, else a 422 naming it."""
    values = multi_values(raw, label)
    if values is None:
        return None
    allowed_set = set(allowed)
    for value in values:
        if value not in allowed_set:
            raise handle_unprocessable(f"{label}: unknown value {value}")
    return values
