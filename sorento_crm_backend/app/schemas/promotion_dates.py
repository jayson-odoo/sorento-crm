"""Normalize promotion start/end to calendar dates (Asia/Kuala_Lumpur civil day for datetimes)."""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

_MY = ZoneInfo("Asia/Kuala_Lumpur")
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def normalize_promotion_start_end(v: Any) -> date:
    """
    Store promotion boundaries as DATE (calendar day).

  - YYYY-MM-DD strings: stored as that calendar day (as-is).
  - Datetime / ISO strings: civil calendar date in Malaysia (same behaviour as before for
      interpreting naive UTC instants from legacy data).
    """
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        if v.tzinfo is None:
            aware = v.replace(tzinfo=timezone.utc)
        else:
            aware = v.astimezone(timezone.utc)
        return aware.astimezone(_MY).date()
    if isinstance(v, str):
        s = v.strip()
        if _DATE_ONLY.match(s):
            return date.fromisoformat(s)
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_MY).date()
    raise ValueError("start_date/end_date must be a date string (YYYY-MM-DD) or datetime")


def normalize_promotion_start_end_optional(v: Any) -> Optional[date]:
    if v is None:
        return None
    return normalize_promotion_start_end(v)


def promotion_date_to_api_iso(d: date) -> str:
    """Serialize a stored promotion DATE for JSON (YYYY-MM-DD)."""
    return d.isoformat()
