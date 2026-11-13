"""Shared list plumbing for the ``last_activity_at`` column on the form lists (FORMS-LAST-ACTIVITY).

The stamps are naive UTC (the clock of ``audit_logs.changed_at``); the list filter days are
Malaysia calendar days, inclusive at both ends.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import and_

from app.services.error_handler import handle_unprocessable

_MYT_OFFSET = timedelta(hours=8)


def _day(value: Optional[date | str], label: str) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = (value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        raise handle_unprocessable(f"{label} must be a date (YYYY-MM-DD).")


def last_activity_range(column: Any, date_from: Optional[date | str], date_to: Optional[date | str]) -> Optional[Any]:
    """A WHERE clause for ``column`` between the two Malaysia days (inclusive), or None."""
    start, end = _day(date_from, "last_activity_from"), _day(date_to, "last_activity_to")
    clauses = []
    if start is not None:
        clauses.append(column >= datetime.combine(start, datetime.min.time()) - _MYT_OFFSET)
    if end is not None:
        clauses.append(column < datetime.combine(end + timedelta(days=1), datetime.min.time()) - _MYT_OFFSET)
    return and_(*clauses) if clauses else None


def last_activity_order(column: Any, created_at: Any, row_id: Any, direction: Optional[str]) -> list:
    """ORDER BY for the stamp: the stamp in the asked direction (rows without one last), then
    ``created_at`` newest first, then the id, so ties and pages stay stable."""
    primary = column.desc().nulls_last() if (direction or "").lower() == "desc" else column.asc().nulls_last()
    return [primary, created_at.desc(), row_id.asc()]
