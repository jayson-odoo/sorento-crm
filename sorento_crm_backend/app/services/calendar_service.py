"""Calendar service for business-day calculations."""
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional, Set, Tuple
from zoneinfo import ZoneInfo
import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.models.calendar import PublicHoliday, WorkCalendarConfig

logger = logging.getLogger(__name__)

# Default timezone for working-hours checks (tenant wall clock; align with Work Calendar UI).
DEFAULT_WORKING_TZ = ZoneInfo("Asia/Kuala_Lumpur")

# Monday=index 0 … Sunday=6 (matches datetime.weekday()).
WEEKDAY_LABELS: Tuple[str, ...] = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def weekday_ranges_from_flags(flags: List[bool]) -> List[Tuple[str, str]]:
    """
    Split Mon - Sun booleans into contiguous ranges.
    Example: Mon - Tue and Thu - Fri if Wednesday is off →
    [("Monday", "Tuesday"), ("Thursday", "Friday")].
    """
    if len(flags) != 7:
        raise ValueError("flags must have 7 entries (Monday through Sunday)")
    ranges: List[Tuple[str, str]] = []
    i = 0
    while i < 7:
        if not flags[i]:
            i += 1
            continue
        start = i
        while i < 7 and flags[i]:
            i += 1
        end = i - 1
        ranges.append((WEEKDAY_LABELS[start], WEEKDAY_LABELS[end]))
    return ranges


def format_time_12h_ampm(value: time) -> str:
    """
    Format a clock time for human-facing APIs, e.g. 09:00 A.M., 01:30 P.M., 12:00 P.M.
    Uses zero-padded hour and minute; includes :ss only when seconds are non-zero.
    """
    h, m, s = value.hour, value.minute, value.second
    hour12 = 12 if (h % 12 == 0) else (h % 12)
    suffix = "A.M." if h < 12 else "P.M."
    if s:
        return f"{hour12:02d}:{m:02d}:{s:02d} {suffix}"
    return f"{hour12:02d}:{m:02d} {suffix}"


class CalendarService:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create_work_calendar(self) -> WorkCalendarConfig:
        config = self.db.query(WorkCalendarConfig).filter(
            WorkCalendarConfig.config_key == "default"
        ).first()
        if not config:
            config = WorkCalendarConfig(
                config_key="default",
                monday=True,
                tuesday=True,
                wednesday=True,
                thursday=True,
                friday=True,
                saturday=False,
                sunday=False,
                work_day_start_time=time(9, 0, 0),
                work_day_end_time=time(17, 0, 0),
            )
            self.db.add(config)
            self.db.flush()
        return config

    def get_working_weekdays(self) -> Set[int]:
        try:
            config = self.get_or_create_work_calendar()
            weekday_map = {
                0: config.monday,
                1: config.tuesday,
                2: config.wednesday,
                3: config.thursday,
                4: config.friday,
                5: config.saturday,
                6: config.sunday,
            }
            return {day for day, is_working in weekday_map.items() if is_working}
        except SQLAlchemyError:
            logger.warning("Work calendar config unavailable; defaulting to Mon-Fri.")
            return {0, 1, 2, 3, 4}

    def get_working_hours(self) -> tuple[time, time]:
        """Start and end clock times for a standard working day (same every working weekday)."""
        try:
            config = self.get_or_create_work_calendar()
            start = config.work_day_start_time
            end = config.work_day_end_time
            if start is not None and end is not None:
                return (start, end)
        except SQLAlchemyError:
            logger.warning("Work calendar config unavailable; defaulting working hours 09:00 - 17:00.")
        return (time(9, 0, 0), time(17, 0, 0))

    def get_working_day_ranges(self) -> list[dict[str, str]]:
        """
        Contiguous working weekday ranges for the default work calendar.
        Each item has start_weekday and end_weekday (English names, e.g. Monday - Friday).
        """
        try:
            config = self.get_or_create_work_calendar()
            flags = [
                bool(config.monday),
                bool(config.tuesday),
                bool(config.wednesday),
                bool(config.thursday),
                bool(config.friday),
                bool(config.saturday),
                bool(config.sunday),
            ]
            return [
                {"start_weekday": a, "end_weekday": b}
                for a, b in weekday_ranges_from_flags(flags)
            ]
        except SQLAlchemyError:
            logger.warning("Work calendar config unavailable; defaulting Mon - Fri.")
            return [
                {"start_weekday": "Monday", "end_weekday": "Friday"},
            ]

    def is_within_working_time(
        self,
        when: Optional[datetime] = None,
        *,
        tz: ZoneInfo = DEFAULT_WORKING_TZ,
    ) -> bool:
        """
        True if `when` falls on a configured business day (weekday + not a public holiday)
        and the local time-of-day is within work_day_start_time..work_day_end_time (inclusive).

        If `when` is None, uses current time in `tz`.
        If `when` is naive, it is interpreted as local wall time in `tz` (not UTC).
        """
        try:
            if when is None:
                dt_local = datetime.now(tz)
            elif when.tzinfo is None:
                dt_local = when.replace(tzinfo=tz)
            else:
                dt_local = when.astimezone(tz)

            d = dt_local.date()
            weekday = d.weekday()
            working_weekdays = self.get_working_weekdays()
            holidays = self.get_public_holidays_between(d, d)
            if not self._is_business_day(d, working_weekdays, holidays):
                return False

            start_t, end_t = self.get_working_hours()
            t = dt_local.time()
            return start_t <= t <= end_t
        except SQLAlchemyError:
            logger.warning("Work calendar unavailable for working-time check; treating as non-working.")
            return False

    def is_working_day(
        self,
        *,
        tz: ZoneInfo = DEFAULT_WORKING_TZ,
        when: Optional[datetime] = None,
    ) -> dict:
        """
        True if the calendar date in `tz` is a configured working weekday and not a public holiday.

        Does not consider clock time (use is_within_working_time for start/end hours).

        If `when` is None, uses current UTC instant converted to `tz`.
        If `when` is naive, it is interpreted as local wall time in `tz`.
        """
        if when is None:
            dt_local = datetime.now(tz)
        elif when.tzinfo is None:
            dt_local = when.replace(tzinfo=tz)
        else:
            dt_local = when.astimezone(tz)

        d = dt_local.date()
        working_weekdays = self.get_working_weekdays()
        holidays = self.get_public_holidays_between(d, d)
        is_day = self._is_business_day(d, working_weekdays, holidays)
        tz_key = getattr(tz, "key", None) or str(tz)
        return {
            "is_working_day": is_day,
            "timezone": tz_key,
            "local_datetime": dt_local.isoformat(),
            "local_date": d,
            "weekday": WEEKDAY_LABELS[d.weekday()],
            "is_public_holiday": d in holidays,
        }

    def get_public_holidays_between(self, start_date: date, end_date: date) -> Set[date]:
        try:
            holidays = self.db.query(PublicHoliday).filter(
                PublicHoliday.date >= start_date,
                PublicHoliday.date <= end_date,
            ).all()
            return {holiday.date for holiday in holidays}
        except SQLAlchemyError:
            logger.warning("Public holidays table unavailable; ignoring holidays for now.")
            return set()

    def _to_date(self, value: Optional[date | datetime]) -> Optional[date]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        return value

    def _is_business_day(self, value: date, working_weekdays: Set[int], holidays: Set[date]) -> bool:
        return value.weekday() in working_weekdays and value not in holidays

    def add_business_days(
        self,
        start_value: date | datetime,
        days: int,
        working_weekdays: Optional[Set[int]] = None,
        holidays: Optional[Set[date]] = None,
    ) -> Optional[datetime]:
        if start_value is None:
            return None
        if days <= 0:
            return start_value if isinstance(start_value, datetime) else datetime.combine(start_value, datetime.min.time())

        start_date = self._to_date(start_value)
        if start_date is None:
            return None
        working_weekdays = working_weekdays or self.get_working_weekdays()
        end_date = start_date
        if holidays is None:
            holidays = self.get_public_holidays_between(start_date, start_date + timedelta(days=days * 7 + 14))

        added = 0
        while added < days:
            end_date = end_date + timedelta(days=1)
            if self._is_business_day(end_date, working_weekdays, holidays):
                added += 1

        if isinstance(start_value, datetime):
            return datetime.combine(end_date, start_value.time())
        return datetime.combine(end_date, datetime.min.time())

    def add_working_days(
        self,
        start_value: date | datetime,
        n_days: int,
        working_weekdays: Optional[Set[int]] = None,
        holidays: Optional[Set[date]] = None,
    ) -> Optional[datetime]:
        """Add ``n_days`` *working* days to ``start_value`` (skipping weekends + KL
        public holidays), preserving the time-of-day. Thin alias over
        ``add_business_days`` with a name that matches the SLA extend-deadline calc
        (``add_working_days`` reads as "N whole working days", never hours)."""
        return self.add_business_days(start_value, n_days, working_weekdays, holidays)

    def count_working_days(
        self,
        start_value: date | datetime,
        end_value: date | datetime,
        working_weekdays: Optional[Set[int]] = None,
        holidays: Optional[Set[date]] = None,
    ) -> int:
        """Count *working* days strictly after ``start_value`` up to and including
        ``end_value`` (skipping weekends + KL public holidays). Thin alias over
        ``business_days_between`` for the extend-deadline date-mode derivation."""
        return self.business_days_between(start_value, end_value, working_weekdays, holidays)

    def next_working_window_open(
        self,
        start_value: datetime,
        *,
        tz: ZoneInfo = DEFAULT_WORKING_TZ,
    ) -> Optional[datetime]:
        """Roll an SLA clock start forward to the next working-window open.

        Nobody is working at 22:48 on a non-working Monday, so starting the clock
        there hands the responder a deadline they never had the full window for.
        Returns ``start_value`` unchanged when it already falls inside a working
        window (business weekday, not a public holiday, and within
        ``[work_day_start_time, work_day_end_time)`` in ``tz`` - the interval is
        half-open, so exactly the close time rolls to the next day). Otherwise
        returns the next business day's open, or the same day's open when the
        start is merely before it.

        Input may be naive (interpreted as UTC, matching the SLA columns) or
        aware; output is naive UTC. Idempotent. A degenerate work calendar (no
        working weekday, or a non-positive window) returns the input unchanged
        and warns, so the SLA path degrades instead of raising or hanging.
        """
        if start_value is None:
            return None
        if start_value.tzinfo is None:
            start_utc = start_value.replace(tzinfo=timezone.utc)
        else:
            start_utc = start_value.astimezone(timezone.utc)

        def _to_naive_utc(dt: datetime) -> datetime:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)

        working_weekdays = self.get_working_weekdays()
        start_t, end_t = self.get_working_hours()
        window_seconds = (
            datetime.combine(date.min, end_t) - datetime.combine(date.min, start_t)
        ).total_seconds()
        if not working_weekdays or window_seconds <= 0:
            logger.warning(
                "next_working_window_open: degenerate work calendar (weekdays=%s, "
                "window=%ss); leaving the clock start unchanged.",
                working_weekdays,
                window_seconds,
            )
            return _to_naive_utc(start_utc)

        local = start_utc.astimezone(tz)
        local_date = local.date()
        # Prefetch generously so a long holiday run never needs a second query.
        holidays = self.get_public_holidays_between(
            local_date, local_date + timedelta(days=60)
        )

        on_business_day = self._is_business_day(local_date, working_weekdays, holidays)
        local_time = local.time().replace(tzinfo=None)
        if on_business_day and start_t <= local_time < end_t:
            return _to_naive_utc(start_utc)  # already inside a window

        # Before open on a working day -> today's open; otherwise the next day's.
        cursor = local_date if (on_business_day and local_time < start_t) else local_date + timedelta(days=1)

        guard = 60  # matches the prefetched holiday span
        while guard > 0:
            guard -= 1
            if self._is_business_day(cursor, working_weekdays, holidays):
                return _to_naive_utc(datetime.combine(cursor, start_t, tzinfo=tz))
            cursor = cursor + timedelta(days=1)

        logger.warning(
            "next_working_window_open: no working day found within 60 days of %s; "
            "leaving the clock start unchanged.",
            local_date,
        )
        return _to_naive_utc(start_utc)

    def add_working_days_from_hours(
        self,
        start_value: datetime,
        hours: float,
        *,
        tz: ZoneInfo = DEFAULT_WORKING_TZ,
    ) -> Optional[datetime]:
        """SLA due date = start + (hours / 24) *working days*, skipping weekends +
        public holidays, keeping the time-of-day.

        The policy expresses the SLA in hours but each 24h = one *working* day
        (e.g. 72h → 3 working days). Working days are counted on the ``tz`` (KL)
        calendar. Input may be naive (interpreted as UTC, matching SLA columns)
        or aware; output is naive UTC. Falls back to plain calendar hours if the
        work calendar is misconfigured.

        The clock start is first normalized to the next working-window open
        (:meth:`next_working_window_open`), so an off-hours submission is not
        charged for time nobody was working: Sat 09:01 + 24h starts Mon at the
        window open and lands Tue at the window open, not Mon 09:01.
        """
        if start_value is None:
            return None
        if start_value.tzinfo is None:
            start_utc = start_value.replace(tzinfo=timezone.utc)
        else:
            start_utc = start_value.astimezone(timezone.utc)

        if hours is None or hours <= 0:
            return start_utc.astimezone(timezone.utc).replace(tzinfo=None)

        # Off-hours starts (weekend, holiday, before open, after close) roll forward
        # to the next window open before any duration is added. Idempotent, and a
        # no-op for a start already inside a window.
        normalized = self.next_working_window_open(start_utc, tz=tz)
        if normalized is not None:
            start_utc = normalized.replace(tzinfo=timezone.utc)

        # Sub-day SLAs (e.g. 3h response) advance on the *working-hours* clock:
        # the working-days model (24h = one business day) rounds anything under ~12h
        # to zero days and loses the deadline entirely. Below one day, count only
        # hours inside the configured work window (skipping nights/weekends/holidays)
        # so a 3h SLA opened at 17:42 spills into the next morning, not to 20:42.
        if float(hours) < 24.0:
            return self.add_working_hours(start_utc, hours, tz=tz)

        days = int(round(float(hours) / 24.0))
        local = start_utc.astimezone(tz)
        try:
            out_local = self.add_business_days(local, days)
        except Exception:
            logger.warning(
                "add_working_days_from_hours: business-day calc failed; "
                "falling back to calendar hours.",
                exc_info=True,
            )
            return (start_utc + timedelta(hours=float(hours))).astimezone(timezone.utc).replace(tzinfo=None)
        if out_local is None:
            return None
        # add_business_days returns a naive datetime (same wall-clock, tz dropped)  - 
        # re-attach the local tz before converting back to UTC.
        if out_local.tzinfo is None:
            out_local = out_local.replace(tzinfo=tz)
        return out_local.astimezone(timezone.utc).replace(tzinfo=None)

    def business_days_between(
        self,
        start_value: date | datetime,
        end_value: date | datetime,
        working_weekdays: Optional[Set[int]] = None,
        holidays: Optional[Set[date]] = None,
    ) -> int:
        start_date = self._to_date(start_value)
        end_date = self._to_date(end_value)
        if not start_date or not end_date:
            return 0
        if end_date < start_date:
            return 0

        working_weekdays = working_weekdays or self.get_working_weekdays()
        if holidays is None:
            holidays = self.get_public_holidays_between(start_date, end_date)
        total = 0
        current = start_date
        while current < end_date:
            current = current + timedelta(days=1)
            if self._is_business_day(current, working_weekdays, holidays):
                total += 1
        return total

    def add_working_hours(
        self,
        start_value: datetime,
        hours: float,
        *,
        tz: ZoneInfo = DEFAULT_WORKING_TZ,
    ) -> Optional[datetime]:
        """Add ``hours`` *working* hours to ``start_value`` and return naive UTC.

        The clock advances only inside configured working windows - a working
        weekday (``get_working_weekdays``), not a public holiday, and between
        ``work_day_start_time`` and ``work_day_end_time`` in ``tz``. Nights,
        weekends and holidays are skipped. If ``start_value`` falls outside a
        window, accumulation begins at the next window open.

        Input may be naive (interpreted as UTC, matching SLA tracking columns)
        or aware. Output is naive UTC. Returns ``start`` unchanged for
        ``hours <= 0``. Falls back to plain calendar arithmetic only if the work
        calendar is misconfigured (no working weekday, or non-positive window).
        """
        if start_value is None:
            return None

        # Normalise to aware UTC, then to local wall time.
        if start_value.tzinfo is None:
            start_utc = start_value.replace(tzinfo=timezone.utc)
        else:
            start_utc = start_value.astimezone(timezone.utc)

        def _to_naive_utc(dt_local: datetime) -> datetime:
            return dt_local.astimezone(timezone.utc).replace(tzinfo=None)

        if hours is None or hours <= 0:
            return _to_naive_utc(start_utc.astimezone(tz))

        working_weekdays = self.get_working_weekdays()
        start_t, end_t = self.get_working_hours()
        window_seconds = (
            datetime.combine(date.min, end_t) - datetime.combine(date.min, start_t)
        ).total_seconds()

        # Degenerate calendar config -> fall back to calendar hours (never hang).
        if not working_weekdays or window_seconds <= 0:
            logger.warning(
                "add_working_hours: degenerate work calendar (weekdays=%s, window=%ss); "
                "falling back to calendar-hour arithmetic.",
                working_weekdays,
                window_seconds,
            )
            return _to_naive_utc(start_utc + timedelta(hours=float(hours)))

        remaining = timedelta(hours=float(hours))
        cursor = start_utc.astimezone(tz)

        # Pre-fetch holidays generously across the projected span.
        max_days = int(remaining.total_seconds() // window_seconds) + 14
        span_start = cursor.date()
        holidays = self.get_public_holidays_between(
            span_start, span_start + timedelta(days=max_days * 3 + 14)
        )

        # Hard iteration cap (defensive; ~ max_days working days max).
        guard = (max_days + 14) * 3
        while guard > 0:
            guard -= 1
            d = cursor.date()
            if not self._is_business_day(d, working_weekdays, holidays):
                # Skip to next day's window open.
                cursor = datetime.combine(d + timedelta(days=1), start_t, tzinfo=tz)
                continue

            day_open = datetime.combine(d, start_t, tzinfo=tz)
            day_close = datetime.combine(d, end_t, tzinfo=tz)

            if cursor < day_open:
                cursor = day_open
            if cursor >= day_close:
                cursor = datetime.combine(d + timedelta(days=1), start_t, tzinfo=tz)
                continue

            available = day_close - cursor
            if remaining <= available:
                return _to_naive_utc(cursor + remaining)
            remaining -= available
            cursor = datetime.combine(d + timedelta(days=1), start_t, tzinfo=tz)

        # Should never reach here; fall back rather than loop forever.
        logger.warning("add_working_hours: iteration guard exhausted; returning calendar fallback.")
        return _to_naive_utc(start_utc + timedelta(hours=float(hours)))
