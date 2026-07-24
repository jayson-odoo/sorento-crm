"""Form-SLA clock start normalization (off-hours / weekend submits).

UAC: documentation/plans/sla/sla-clock-start-next-working-window-acceptance-criteria.md

Supersedes the earlier one-sided due-date clamp (`_clamp_offhours_due_to_workday_end`,
removed with its test file). That clamp relaxed the *deadline* to the end of the
working day; this fixes the *start* instead — an off-hours submit begins its clock
at the next working-window open, then the policy duration is added from there.
Sat 09:01 + 24h is therefore due Tue at the window open, not Mon 09:01 (raw) and
not Mon 17:00 (clamped).

Hermetic (no DB) via a stub CalendarService, mirroring test_working_hours_sla.py.
June 2026: 5th = Fri, 6th = Sat, 7th = Sun, 8th = Mon.
"""
from datetime import date, datetime, time, timezone
from typing import Set
from zoneinfo import ZoneInfo

from app.services.calendar_service import CalendarService
from app.services.form_sla_service import (
    _working_clock_start_naive,
    _working_due_naive,
)

KL = ZoneInfo("Asia/Kuala_Lumpur")


class _StubCalendar(CalendarService):
    """Mon–Fri, configurable window (default 09:00–17:00), injectable holidays, no DB."""

    def __init__(
        self,
        holidays: Set[date] | None = None,
        start_hour: int = 9,
        end_hour: int = 17,
    ):
        self._holidays = holidays or set()
        self._start_hour = start_hour
        self._end_hour = end_hour

    def get_working_weekdays(self) -> Set[int]:
        return {0, 1, 2, 3, 4}

    def get_working_hours(self):
        return (time(self._start_hour, 0, 0), time(self._end_hour, 0, 0))

    def get_public_holidays_between(self, start_date, end_date):
        return {h for h in self._holidays if start_date <= h <= end_date}


class _NoNormalize(_StubCalendar):
    """Pre-change behaviour: preserve the submit time-of-day (no clock-start roll)."""

    def next_working_window_open(self, start_value, *, tz=None):
        if start_value.tzinfo is None:
            return start_value
        return start_value.astimezone(timezone.utc).replace(tzinfo=None)


def _utc(kl_dt: datetime) -> datetime:
    """KL wall-clock -> naive UTC (matches SLA tracking columns)."""
    return kl_dt.replace(tzinfo=KL).astimezone(timezone.utc).replace(tzinfo=None)


def _kl(naive_utc: datetime) -> datetime:
    return naive_utc.replace(tzinfo=timezone.utc).astimezone(KL)


def _due(kl_submit: datetime, hours: float, holidays=None, start_hour=9, end_hour=17):
    cal = _StubCalendar(holidays, start_hour, end_hour)
    return _kl(cal.add_working_days_from_hours(_utc(kl_submit), hours))


# ------------------------------------------------------------------ due dates

def test_saturday_0901_24h_starts_monday_open_and_is_due_tuesday_open():
    # The reported case, re-specified: Sat 09:01 -> start Mon 09:00 -> due Tue 09:00.
    got = _due(datetime(2026, 6, 6, 9, 1), 24)
    assert (got.month, got.day, got.hour, got.minute) == (6, 9, 9, 0)


def test_weekday_preopen_starts_same_day_open():
    # Mon 08:30 -> start Mon 09:00 -> due Tue 09:00.
    got = _due(datetime(2026, 6, 8, 8, 30), 24)
    assert (got.month, got.day, got.hour, got.minute) == (6, 9, 9, 0)


def test_in_window_unchanged_REGRESSION():
    # Wed 14:00 + 24h -> Thu 14:00. In-window submits keep today's behaviour exactly.
    got = _due(datetime(2026, 6, 10, 14, 0), 24)
    assert (got.month, got.day, got.hour, got.minute) == (6, 11, 14, 0)


def test_after_close_rolls_to_next_open():
    # Fri 17:30 -> start Mon 09:00 -> due Tue 09:00 (was Mon 17:30 pre-change).
    got = _due(datetime(2026, 6, 5, 17, 30), 24)
    assert (got.month, got.day, got.hour, got.minute) == (6, 9, 9, 0)


def test_sunday_2300_rolls_to_next_open():
    # Sun 23:00 -> start Mon 09:00 -> due Tue 09:00.
    got = _due(datetime(2026, 6, 7, 23, 0), 24)
    assert (got.month, got.day, got.hour, got.minute) == (6, 9, 9, 0)


def test_uses_configured_window_open():
    # Production window is 08:00-23:00: Sat 09:01 -> start Mon 08:00 -> due Tue 08:00.
    got = _due(datetime(2026, 6, 6, 9, 1), 24, start_hour=8, end_hour=23)
    assert (got.month, got.day, got.hour, got.minute) == (6, 9, 8, 0)


def test_holiday_skipped_when_normalizing_start():
    # Sat 09:01 with Mon a holiday -> start Tue 09:00 -> due Wed 09:00.
    got = _due(datetime(2026, 6, 6, 9, 1), 24, holidays={date(2026, 6, 8)})
    assert (got.month, got.day, got.hour, got.minute) == (6, 10, 9, 0)


def test_72h_offhours_lands_three_working_days_after_open():
    got = _due(datetime(2026, 6, 6, 9, 37), 72)
    assert (got.month, got.day, got.hour, got.minute) == (6, 11, 9, 0)


def test_sub_24h_branch_untouched_REGRESSION():
    # 3h SLA opened Sat 09:01 -> Mon 12:00 via the working-hours clock (unchanged).
    got = _due(datetime(2026, 6, 6, 9, 1), 3)
    assert (got.month, got.day, got.hour) == (6, 8, 12)


def test_normalization_never_moves_a_due_earlier():
    # Sweep submit times/days: the normalized due is ALWAYS >= the pre-change due,
    # so no existing tracker could become retroactively overdue (UAC risk note).
    for day in range(5, 12):            # Fri..next Fri
        for hour in range(0, 24, 3):
            for hours in (24, 48, 72):
                submit = _utc(datetime(2026, 6, day, hour, 15))
                raw = _NoNormalize().add_working_days_from_hours(submit, hours)
                got = _StubCalendar().add_working_days_from_hours(submit, hours)
                assert got >= raw, (submit, hours, raw, got)


# -------------------------------------------------------------------- funnels

def test_working_due_naive_applies_normalization(monkeypatch):
    # _working_due_naive builds CalendarService(db) internally; patch it to the stub
    # so we prove the funnel normalizes (covers response/resolution/escalation,
    # which all route through this one funnel) with no DB.
    monkeypatch.setattr(
        "app.services.calendar_service.CalendarService",
        lambda db: _StubCalendar(),
    )
    got = _kl(_working_due_naive(db=None, start_dt=_utc(datetime(2026, 6, 6, 9, 1)), hours=24))
    assert (got.month, got.day, got.hour, got.minute) == (6, 9, 9, 0)


def test_working_due_naive_in_window_unchanged(monkeypatch):
    monkeypatch.setattr(
        "app.services.calendar_service.CalendarService",
        lambda db: _StubCalendar(),
    )
    got = _kl(_working_due_naive(db=None, start_dt=_utc(datetime(2026, 6, 10, 14, 0)), hours=24))
    assert (got.month, got.day, got.hour, got.minute) == (6, 11, 14, 0)


def test_working_clock_start_naive_normalizes_offhours(monkeypatch):
    # The stored current_tier_started_at (UI elapsed counter) moves too, not just due_at.
    monkeypatch.setattr(
        "app.services.calendar_service.CalendarService",
        lambda db: _StubCalendar(),
    )
    got = _kl(_working_clock_start_naive(db=None, start_dt=_utc(datetime(2026, 6, 6, 9, 1))))
    assert (got.month, got.day, got.hour, got.minute) == (6, 8, 9, 0)


def test_working_clock_start_naive_in_window_unchanged(monkeypatch):
    monkeypatch.setattr(
        "app.services.calendar_service.CalendarService",
        lambda db: _StubCalendar(),
    )
    start = _utc(datetime(2026, 6, 10, 14, 0))
    assert _working_clock_start_naive(db=None, start_dt=start) == start
