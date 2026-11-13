"""How a list search combines several values (SEARCH-CHIPS).

The rule lives here and nowhere else: "any" returns a row matching any value, "all" a row
matching every value. A list builds its clause with ``search_values_filter``.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Literal, Optional

from sqlalchemy import and_
from sqlalchemy.sql.elements import ColumnElement

from app.services.error_handler import handle_unprocessable
from app.utils.multi_value import multi_text

SEARCH_VALUES_MATCH: Literal["any", "all"] = "any"

#: Longest single search value; the count is capped at 200 by `multi_text`.
MAX_SEARCH_VALUE_LENGTH = 100


def search_values(raw: Iterable[str] | str | None, label: str = "Search") -> Optional[list[str]]:
    """The search values of a repeated `query` param: blanks dropped, case-insensitive
    duplicates kept once (first spelling wins), never split on commas, capped at 200 values
    of at most 100 characters each (422 otherwise)."""
    if raw is None:
        return None
    items = [raw] if isinstance(raw, str) else raw
    seen: set[str] = set()
    distinct: list[str] = []
    for item in items:
        value = str(item or "").strip()
        if len(value) > MAX_SEARCH_VALUE_LENGTH:
            raise handle_unprocessable(
                f"{label}: each value at most {MAX_SEARCH_VALUE_LENGTH} characters"
            )
        if value and value.casefold() not in seen:
            seen.add(value.casefold())
            distinct.append(value)
    return multi_text(distinct, label)


def search_values_filter(
    values: Sequence[str], match: Callable[[list[str]], ColumnElement[bool]]
) -> ColumnElement[bool]:
    """`match(values)` matches a row against a LIST of values. "any" calls it once with every
    value; "all" ANDs one call per value."""
    values = list(values)
    if SEARCH_VALUES_MATCH == "all":
        return and_(*(match([v]) for v in values))
    return match(values)
