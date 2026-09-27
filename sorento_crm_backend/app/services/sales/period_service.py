"""A target's periods from its date range and optional split (plan 3.1, 16.2; UAC S1-19).

No split: one period, start to end. A split of every N days, weeks or months: period k starts
at `start + kN days`, `start + 7kN days`, or `start` plus kN calendar months clamped to that
month's last day (always counted from the ORIGINAL start, so a 31 Jan start gives 31 Jan,
28 Feb, 31 Mar and never drifts to the 28th). Each period ends the day before the next one
starts; the last ends at `end`, however short. Both ends are counted.

The frontend's `lib/periods.ts` mirrors this for the modal's hint; the golden table is the
same on both sides.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import List, Optional, Tuple

from app.services.error_handler import AppException

#: Two years of weeks (plan 3.1). More is 422 `TOO_MANY_PERIODS`.
MAX_PERIODS = 104


def add_months(day: date, months: int) -> date:
    """`day` plus `months` calendar months, clamped to the target month's last day."""
    index = day.year * 12 + (day.month - 1) + months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _start_of(k: int, start: date, every: int, unit: str) -> date:
    if unit == "day":
        return start + timedelta(days=k * every)
    if unit == "week":
        return start + timedelta(days=7 * k * every)
    return add_months(start, k * every)


def generate_periods(
    start: date, end: date, split_every: Optional[int], split_unit: Optional[str]
) -> List[Tuple[date, date]]:
    if end < start:
        raise AppException(
            status_code=422, message="The end date is before the start date.", code="INVALID_DATES"
        )
    if (split_every is None) != (split_unit is None):
        raise AppException(
            status_code=422,
            message="A split needs both how many and which unit.",
            code="INVALID_SPLIT",
        )
    if split_every is None or split_unit is None:
        return [(start, end)]

    starts: List[date] = []
    k = 0
    while True:
        begin = _start_of(k, start, split_every, split_unit)
        if begin > end:
            break
        starts.append(begin)
        if len(starts) > MAX_PERIODS:
            raise AppException(
                status_code=422,
                message=f"That split makes more than {MAX_PERIODS} periods.",
                code="TOO_MANY_PERIODS",
            )
        k += 1

    periods: List[Tuple[date, date]] = []
    for i, begin in enumerate(starts):
        finish = starts[i + 1] - timedelta(days=1) if i + 1 < len(starts) else end
        periods.append((begin, finish))
    return periods
