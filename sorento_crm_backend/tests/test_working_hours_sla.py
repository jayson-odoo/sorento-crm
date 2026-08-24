"""Unit tests for CalendarService.add_working_hours - the working-hours SLA clock.

Clock ticks only Mon - Fri 09:00 - 17:00 Asia/Kuala_Lumpur (UTC+8), skipping nights,
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
    """CalendarService with Mon - Fri 09:00 - 17:00 and an injectable holiday set, no DB."""

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
    # working days - the day model would lose the deadline (4/24 → 0 days). 4h → +4h.
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


# ---------------------------------------------------------------------------
# next_working_window_open - the clock-start normalizer.
# UAC: documentation/plans/sla/sla-clock-start-next-working-window-acceptance-criteria.md
# Stub calendar is Mon-Fri 09:00-17:00, so "window open" is 09:00 here (production
# is 08:00). June 2026: 5th = Fri, 6th = Sat, 7th = Sun, 8th = Mon.
# ---------------------------------------------------------------------------


def _open(kl_dt: datetime, holidays=None) -> datetime:
    out = _StubCalendar(holidays).next_working_window_open(_utc(kl_dt))
    return out.replace(tzinfo=timezone.utc).astimezone(KL)


def test_open_inside_window_unchanged():
    # AC-1
    got = _open(datetime(2026, 6, 8, 10, 0))  # Mon 10:00 -> unchanged
    assert (got.month, got.day, got.hour, got.minute) == (6, 8, 10, 0)


def test_open_at_window_start_is_inside():
    # AC-1 boundary: [start, end) -> 09:00 is inside, not rolled forward.
    got = _open(datetime(2026, 6, 8, 9, 0))
    assert (got.month, got.day, got.hour) == (6, 8, 9)


def test_open_before_window_rolls_to_same_day_open():
    # AC-2
    got = _open(datetime(2026, 6, 8, 6, 0))  # Mon 06:00 -> Mon 09:00
    assert (got.month, got.day, got.hour) == (6, 8, 9)


def test_open_at_window_close_rolls_to_next_day():
    # AC-3 boundary: 17:00 is OUTSIDE (half-open interval) -> Tue 09:00.
    got = _open(datetime(2026, 6, 8, 17, 0))
    assert (got.month, got.day, got.hour) == (6, 9, 9)


def test_open_after_window_close_rolls_to_next_day():
    # AC-3
    got = _open(datetime(2026, 6, 8, 19, 0))  # Mon 19:00 -> Tue 09:00
    assert (got.month, got.day, got.hour) == (6, 9, 9)


def test_open_on_weekend_rolls_to_monday_open():
    # AC-4 - the reported case: Sat 09:01 -> Mon 09:00.
    got = _open(datetime(2026, 6, 6, 9, 1))
    assert (got.month, got.day, got.hour, got.minute) == (6, 8, 9, 0)


def test_open_skips_public_holiday():
    # AC-5 - Sat, with Mon a holiday -> Tue 09:00.
    got = _open(datetime(2026, 6, 6, 9, 1), holidays={date(2026, 6, 8)})
    assert (got.month, got.day, got.hour) == (6, 9, 9)


def test_open_is_idempotent():
    # AC-6 - normalizing an already-normalized value returns it unchanged.
    cal = _StubCalendar()
    once = cal.next_working_window_open(_utc(datetime(2026, 6, 6, 9, 1)))
    twice = cal.next_working_window_open(once)
    assert once == twice


def test_open_accepts_aware_input_and_returns_naive_utc():
    # AC-7
    aware = datetime(2026, 6, 6, 9, 1, tzinfo=KL)
    out = _StubCalendar().next_working_window_open(aware)
    assert out.tzinfo is None
    assert out == _utc(datetime(2026, 6, 8, 9, 0))


def test_open_degenerate_calendar_returns_input_unchanged():
    # AC-8 - never raise, never hang; the SLA path degrades to today's behaviour.
    class _NoWorkdays(_StubCalendar):
        def get_working_weekdays(self):
            return set()

    start = _utc(datetime(2026, 6, 6, 9, 1))
    assert _NoWorkdays().next_working_window_open(start) == start


# ---------------------------------------------------------------------------
# add_working_days_from_hours - now normalizes the start before adding.
# ---------------------------------------------------------------------------


def test_offhours_24h_starts_next_open_and_lands_next_working_day():
    # AC-9 - Sat 09:01 + 24h: start Mon 09:00, +1 working day -> Tue 09:00.
    got = _add_days(datetime(2026, 6, 6, 9, 1), 24)
    assert (got.month, got.day, got.hour, got.minute) == (6, 9, 9, 0)


def test_offhours_72h_starts_next_open_and_lands_three_working_days_later():
    # AC-10 - Sat 09:37 + 72h: start Mon 09:00, +3 working days -> Thu 09:00.
    got = _add_days(datetime(2026, 6, 6, 9, 37), 72)
    assert (got.month, got.day, got.hour, got.minute) == (6, 11, 9, 0)


def test_offhours_sub_day_still_uses_working_hours_clock():
    # AC-11 - Sat 09:01 + 3h: start Mon 09:00, +3 working hours -> Mon 12:00.
    got = _add_days(datetime(2026, 6, 6, 9, 1), 3)
    assert (got.month, got.day, got.hour) == (6, 8, 12)


def test_in_window_start_time_of_day_preserved():
    # AC-12 - no regression for the ordinary weekday case: Mon 10:00 + 24h -> Tue 10:00.
    got = _add_days(datetime(2026, 6, 8, 10, 0), 24)
    assert (got.month, got.day, got.hour, got.minute) == (6, 9, 10, 0)
