"""The one way the backend writes a date a person reads (DATE-FORMAT-UNIFY, 4 Nov 2026).

- date:      ``01/01/2026``
- date-time: ``30/09/2026, 12:23 pm``
- range:     ``01/01/2026 - 31/03/2026`` (plain hyphen, the range picker's own shape)

Malaysia time, the same as the frontend's ``formatDateInMalaysia``. A NAIVE datetime is read as
UTC by default because that is how timestamps are stored; pass ``naive_is_utc=False`` for a value
that is already Malaysia wall clock. A plain ``date`` carries no instant and is shown as is.
Wire values (ISO in JSON, ``%Y%m%d`` filenames, ``%Y-%m`` bucket keys) do not use this module.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

MY_TZ = ZoneInfo("Asia/Kuala_Lumpur")


def _coerce(value: Any) -> date | datetime | None:
    if isinstance(value, (date, datetime)):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            if len(s) == 10:
                return date.fromisoformat(s)
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _in_malaysia(value: datetime, naive_is_utc: bool) -> datetime:
    if value.tzinfo is None:
        if not naive_is_utc:
            return value
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(MY_TZ)


def fmt_date(value: Any, fallback: str = "", *, naive_is_utc: bool = True) -> str:
    """``01/01/2026``. ``None`` / ``''`` -> ``fallback``; text that is not a date passes through."""
    if value is None or value == "":
        return fallback
    d = _coerce(value)
    if d is None:
        return str(value)
    if isinstance(d, datetime):
        d = _in_malaysia(d, naive_is_utc)
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


def fmt_datetime(value: Any, fallback: str = "", *, naive_is_utc: bool = True) -> str:
    """``30/09/2026, 12:23 pm``. A plain date shows as a date."""
    if value is None or value == "":
        return fallback
    d = _coerce(value)
    if d is None:
        return str(value)
    if not isinstance(d, datetime):
        return fmt_date(d)
    d = _in_malaysia(d, naive_is_utc)
    hour12 = d.hour % 12 or 12
    ampm = "pm" if d.hour >= 12 else "am"
    return f"{d.day:02d}/{d.month:02d}/{d.year}, {hour12}:{d.minute:02d} {ampm}"


def fmt_date_range(start: Any, end: Any, fallback: str = "", *, naive_is_utc: bool = True) -> str:
    """``01/01/2026 - 31/03/2026``; one end alone shows that end; neither -> ``fallback``."""
    a = fmt_date(start, naive_is_utc=naive_is_utc)
    b = fmt_date(end, naive_is_utc=naive_is_utc)
    if a and b:
        return f"{a} - {b}"
    return a or b or fallback


_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")


def fmt_maybe_date(value: Any) -> Any:
    """A stored value that MAY be a date, in the one shape (the FE's ``formatMaybeDate``).

    A bare ``YYYY-MM-DD`` -> ``20/06/2027``; an ISO timestamp (naive UTC, zoned, with
    microseconds) -> ``04/11/2026, 7:11 pm`` in Malaysia; anything else unchanged. For audit
    change values, whose type is only known as "whatever the snapshot stored".
    """
    if not isinstance(value, str):
        return value
    text = value.strip()
    if _ISO_DAY.match(text):
        return fmt_date(text)
    if _ISO_INSTANT.match(text):
        try:
            return fmt_datetime(datetime.fromisoformat(text.replace("Z", "+00:00")))
        except ValueError:
            return value
    return value
