"""Normalize promotion start/end to UTC-naive instants for MY civil calendar dates (Asia/Kuala_Lumpur)."""
from __future__ import annotations

import re
from datetime import date, datetime, time, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

_MY = ZoneInfo("Asia/Kuala_Lumpur")
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _my_midnight_to_utc_naive(d: date) -> datetime:
    dt_my = datetime.combine(d, time.min, tzinfo=_MY)
    return dt_my.astimezone(timezone.utc).replace(tzinfo=None)


def normalize_promotion_start_end(v: Any) -> datetime:
    """
    Store promotion boundaries as naive UTC corresponding to 00:00 on the civil date in
    Asia/Kuala_Lumpur. Accepts YYYY-MM-DD (preferred), ISO datetime strings, or datetime.
    """
    if isinstance(v, datetime):
        if v.tzinfo is None:
            aware = v.replace(tzinfo=timezone.utc)
        else:
            aware = v
        civil = aware.astimezone(_MY).date()
        return _my_midnight_to_utc_naive(civil)
    if isinstance(v, str):
        s = v.strip()
        if _DATE_ONLY.match(s):
            return _my_midnight_to_utc_naive(date.fromisoformat(s))
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        civil = dt.astimezone(_MY).date()
        return _my_midnight_to_utc_naive(civil)
    raise ValueError("start_date/end_date must be a date string (YYYY-MM-DD) or datetime")


def normalize_promotion_start_end_optional(v: Any) -> Optional[datetime]:
    if v is None:
        return None
    return normalize_promotion_start_end(v)


def naive_utc_stored_instant_to_malaysia_iso_date(dt: datetime) -> str:
    """Map naive-UTC DB instants to Malaysia civil calendar YYYY-MM-DD for JSON responses."""
    if dt.tzinfo is None:
        aware = dt.replace(tzinfo=timezone.utc)
    else:
        aware = dt.astimezone(timezone.utc)
    return aware.astimezone(_MY).date().isoformat()
