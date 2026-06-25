"""Unit tests for CalendarService.add_working_hours — the working-hours SLA clock.

Clock ticks only Mon–Fri 09:00–17:00 Asia/Kuala_Lumpur (UTC+8), skipping nights,
weekends and configured public holidays. Input may be naive (treated as UTC) or
aware; output is naive UTC (matches SLA tracking columns).

The work-calendar inputs are stubbed (no DB) so the test is deterministic and
free of the global-SQLAlchemy-listener interference that hits sqlite fixtures
when the full suite runs.
"""
from datetime import date, datetime, time, timezone
from typing import Set
from zoneinfo import ZoneInfo

from app.services.calendar_service import CalendarService

KL = ZoneInfo("Asia/Kuala_Lumpur")


class _StubCalendar(CalendarService):
    """CalendarService with Mon–Fri 09:00–17:00 and an injectable holiday set, no DB."""

    def __init__(self, holidays: Set[date] | None = None):
        self._holidays = holidays or set()

    def get_working_weekdays(self) -> Set[int]:
        return {0, 1, 2, 3, 4}

    def get_working_hours(self):
        return (time(9, 0, 0), time(17, 0, 0))

    def get_public_holidays_between(self, start_date, end_date):
        return {h for h in self._holidays if start_date <= h <= end_date}


def _utc(kl_dt: datetime) -> datetime:
    return kl_dt.replace(tzinfo=KL).astimezone(timezone.utc).replace(tzinfo=None)


def _add(kl_start: datetime, hours: float, holidays=None) -> datetime:
    out = _StubCalendar(holidays).add_working_hours(_utc(kl_start), hours)
    return out.replace(tzinfo=timezone.utc).astimezone(KL)


def test_within_hours_same_day():
    got = _add(datetime(2026, 6, 8, 10, 0), 4)  # Mon 10:00 + 4h -> Mon 14:00
    assert (got.month, got.day, got.hour, got.minute) == (6, 8, 14, 0)


def test_spills_to_next_day():
    got = _add(datetime(2026, 6, 8, 15, 0), 4)  # Mon 15:00 -> Tue 11:00
    assert (got.month, got.day, got.hour) == (6, 9, 11)


def test_weekend_skipped():
    got = _add(datetime(2026, 6, 5, 16, 0), 4)  # Fri 16:00 -> Mon 12:00
    assert (got.month, got.day, got.hour) == (6, 8, 12)


def test_public_holiday_skipped():
    got = _add(datetime(2026, 6, 9, 16, 0), 4, holidays={date(2026, 6, 10)})  # Tue->Thu (Wed holiday)
    assert (got.month, got.day, got.hour) == (6, 11, 12)


def test_start_after_hours_begins_next_open():
    got = _add(datetime(2026, 6, 8, 20, 0), 1)  # Mon 20:00 -> Tue 10:00
    assert (got.month, got.day, got.hour) == (6, 9, 10)


def test_start_before_hours_begins_at_open():
    got = _add(datetime(2026, 6, 8, 6, 0), 2)  # Mon 06:00 -> Mon 11:00
    assert (got.month, got.day, got.hour) == (6, 8, 11)


def test_zero_hours_returns_start():
    start = _utc(datetime(2026, 6, 8, 10, 0))
    out = _StubCalendar().add_working_hours(start, 0)
    assert out == start


def test_multi_day_accumulation():
    got = _add(datetime(2026, 6, 8, 9, 0), 20)  # Mon 09:00 + 20h -> Wed 13:00
    assert (got.month, got.day, got.hour) == (6, 10, 13)


def test_fractional_hours():
    got = _add(datetime(2026, 6, 8, 10, 0), 1.5)  # Mon 10:00 + 1.5h -> Mon 11:30
    assert (got.hour, got.minute) == (11, 30)


def _add_days(kl_start: datetime, hours: float, holidays=None) -> datetime:
    out = _StubCalendar(holidays).add_working_days_from_hours(_utc(kl_start), hours)
    return out.replace(tzinfo=timezone.utc).astimezone(KL)


def test_72h_is_three_working_days_skipping_weekend():
    # Fri + 72h (=3 working days) -> Mon, Tue, Wed -> Wed, same time.
    got = _add_days(datetime(2026, 6, 5, 10, 0), 72)
    assert (got.month, got.day, got.hour) == (6, 10, 10)


def test_24h_is_one_working_day():
    got = _add_days(datetime(2026, 6, 8, 9, 0), 24)  # Mon -> Tue
    assert (got.month, got.day) == (6, 9)


def test_working_days_skip_holiday():
    # Tue + 72h, Wed is a holiday -> Thu, Fri, Mon -> Mon.
    got = _add_days(datetime(2026, 6, 9, 10, 0), 72, holidays={date(2026, 6, 10)})
    assert (got.month, got.day) == (6, 15)


def test_sub_24h_is_wall_clock():
    # Sub-day SLAs (e.g. warehouse 0.5h / 1h) are wall-clock, not rounded to whole
    # working days — the day model would lose the deadline (4/24 → 0 days). 4h → +4h.
    got = _add_days(datetime(2026, 6, 8, 10, 0), 4)
    assert (got.month, got.day, got.hour) == (6, 8, 14)


def test_sub_hour_is_wall_clock():
    # 0.5h must yield +30 minutes (the warehouse fast-SLA requirement, UAC-11).
    got = _add_days(datetime(2026, 6, 8, 10, 0), 0.5)
    assert (got.month, got.day, got.hour, got.minute) == (6, 8, 10, 30)


def test_degenerate_calendar_falls_back_to_calendar_hours():
    from datetime import timedelta

    class _NoWorkdays(_StubCalendar):
        def get_working_weekdays(self):
            return set()

    start = _utc(datetime(2026, 6, 8, 10, 0))
    out = _NoWorkdays().add_working_hours(start, 5)
    # Degenerate calendar -> plain calendar-hour fallback, naive UTC.
    assert out == start + timedelta(hours=5)
