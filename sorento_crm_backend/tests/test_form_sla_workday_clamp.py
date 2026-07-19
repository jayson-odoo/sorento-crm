"""R1 — Working-day SLA due-date clamp (one-sided, off-hours / weekend submits).

UAC: documentation/plans/forms/form-workday-sla-clamp-acceptance-criteria.md

Bug: the >=24h SLA branch (add_business_days) preserves the submission wall-clock
time-of-day, so a Sat 09:01 + 24h submit lands due Mon 09:01 (~1 min of working
time). Fix: a ONE-SIDED clamp in form_sla_service — when the working-days due
lands at a time BEFORE the work window opens on a working day, snap it forward to
that day's configured work_day_end_time. Never moves a due earlier (after-close /
in-window unchanged). The <24h branch already window-clamps and is untouched.

Hermetic (no DB) via a stub CalendarService, mirroring test_working_hours_sla.py.
"""
from datetime import date, datetime, time, timezone
from typing import Set
from zoneinfo import ZoneInfo

import pytest

from app.services.calendar_service import CalendarService
from app.services import form_sla_service
from app.services.form_sla_service import (
    _clamp_offhours_due_to_workday_end,
    _working_due_naive,
)

KL = ZoneInfo("Asia/Kuala_Lumpur")


class _StubCalendar(CalendarService):
    """Mon–Fri, configurable window (default 09:00–17:00), injectable holidays, no DB."""

    def __init__(self, holidays: Set[date] | None = None, end_hour: int = 17):
        self._holidays = holidays or set()
        self._end_hour = end_hour

    def get_working_weekdays(self) -> Set[int]:
        return {0, 1, 2, 3, 4}

    def get_working_hours(self):
        return (time(9, 0, 0), time(self._end_hour, 0, 0))

    def get_public_holidays_between(self, start_date, end_date):
        return {h for h in self._holidays if start_date <= h <= end_date}


def _utc(kl_dt: datetime) -> datetime:
    """KL wall-clock -> naive UTC (matches SLA tracking columns)."""
    return kl_dt.replace(tzinfo=KL).astimezone(timezone.utc).replace(tzinfo=None)


def _kl(naive_utc: datetime) -> datetime:
    return naive_utc.replace(tzinfo=timezone.utc).astimezone(KL)


def _raw_due(kl_submit: datetime, hours: float, holidays=None, end_hour=17) -> datetime:
    """Unclamped working-days due (what the calendar layer produces today)."""
    return _StubCalendar(holidays, end_hour).add_working_days_from_hours(_utc(kl_submit), hours)


def _clamped_due(kl_submit: datetime, hours: float, holidays=None, end_hour=17) -> datetime:
    """Mirror _working_due_naive: clamp only applies on the >=24h working-days branch."""
    cal = _StubCalendar(holidays, end_hour)
    raw = cal.add_working_days_from_hours(_utc(kl_submit), hours)
    if float(hours) >= 24.0:
        return _clamp_offhours_due_to_workday_end(cal, _utc(kl_submit), raw)
    return raw


# ---------------------------------------------------------------- CLAMP group

def test_clamp1_saturday_0901_24h_snaps_to_monday_end():
    # Hasni's case: Sat 09:01 + 24h -> raw Mon 09:01 -> clamp -> Mon 17:00.
    raw = _kl(_raw_due(datetime(2026, 6, 6, 9, 1), 24))
    assert (raw.month, raw.day, raw.hour, raw.minute) == (6, 8, 9, 1)
    got = _kl(_clamped_due(datetime(2026, 6, 6, 9, 1), 24))
    assert (got.month, got.day, got.hour, got.minute) == (6, 8, 17, 0)


def test_clamp2_weekday_preopen_snaps_to_same_day_end():
    # Mon 08:30 + 24h -> raw Tue 08:30 -> clamp -> Tue 17:00.
    got = _kl(_clamped_due(datetime(2026, 6, 8, 8, 30), 24))
    assert (got.month, got.day, got.hour, got.minute) == (6, 9, 17, 0)


def test_clamp3_in_window_unchanged_REGRESSION():
    # Wed 14:00 + 24h -> Thu 14:00, in window -> NO clamp.
    got = _kl(_clamped_due(datetime(2026, 6, 10, 14, 0), 24))
    assert (got.month, got.day, got.hour, got.minute) == (6, 11, 14, 0)


def test_clamp4_after_close_unchanged_REGRESSION():
    # Fri 17:30 + 24h -> Mon 17:30, after close -> NOT tightened (one-sided).
    got = _kl(_clamped_due(datetime(2026, 6, 5, 17, 30), 24))
    assert (got.month, got.day, got.hour, got.minute) == (6, 8, 17, 30)


def test_clamp5_sunday_2300_unchanged_REGRESSION():
    # Sun 23:00 + 24h -> Mon 23:00, raw time after close (not before open) -> unchanged.
    got = _kl(_clamped_due(datetime(2026, 6, 7, 23, 0), 24))
    assert (got.month, got.day, got.hour) == (6, 8, 23)


def test_clamp6_uses_configured_end_time():
    # Work end changed to 18:00 -> Sat 09:01 + 24h clamps to Mon 18:00.
    got = _kl(_clamped_due(datetime(2026, 6, 6, 9, 1), 24, end_hour=18))
    assert (got.month, got.day, got.hour, got.minute) == (6, 8, 18, 0)


def test_clamp7_holiday_skip_then_clamp():
    # Sat 09:01 + 24h, Mon is a holiday -> raw Tue 09:01 -> clamp -> Tue 17:00.
    got = _kl(_clamped_due(datetime(2026, 6, 6, 9, 1), 24, holidays={date(2026, 6, 8)}))
    assert (got.month, got.day, got.hour, got.minute) == (6, 9, 17, 0)


def test_clamp8_sub_24h_branch_untouched_REGRESSION():
    # 3h SLA opened Sat 09:01 -> Mon 12:00 via add_working_hours; clamp is a no-op
    # (result is never pre-open).
    got = _kl(_clamped_due(datetime(2026, 6, 6, 9, 1), 3))
    assert (got.month, got.day, got.hour) == (6, 8, 12)


def test_clamp9_is_one_sided_never_earlier():
    # Sweep submit times/days: clamped due is ALWAYS >= raw due (never earlier).
    for day in range(5, 12):            # Fri..next Fri
        for hour in range(0, 24, 3):
            for hours in (24, 48, 72):
                submit = datetime(2026, 6, day, hour, 15)
                raw = _raw_due(submit, hours)
                clamped = _clamp_offhours_due_to_workday_end(
                    _StubCalendar(), _utc(submit), raw
                )
                assert clamped >= raw, (submit, hours, raw, clamped)


# ---------------------------------------------------------------- FUNNEL group

def test_funnel1_calendar_layer_is_not_clamped():
    # The raw calendar API preserves time-of-day (proves the clamp is NOT in the
    # calendar layer — only in _working_due_naive).
    raw = _kl(_raw_due(datetime(2026, 6, 6, 9, 1), 24))
    assert (raw.hour, raw.minute) == (9, 1)  # unclamped


def test_funnel_wiring_working_due_naive_applies_clamp(monkeypatch):
    # _working_due_naive builds CalendarService(db) internally; patch it to the stub
    # so we prove the funnel applies the clamp (covers response/resolution/escalation,
    # which all call this one funnel) with no DB.
    monkeypatch.setattr(
        "app.services.calendar_service.CalendarService",
        lambda db: _StubCalendar(),
    )
    out = _working_due_naive(db=None, start_dt=_utc(datetime(2026, 6, 6, 9, 1)), hours=24)
    got = _kl(out)
    assert (got.month, got.day, got.hour, got.minute) == (6, 8, 17, 0)


def test_funnel_working_due_naive_in_window_unchanged(monkeypatch):
    monkeypatch.setattr(
        "app.services.calendar_service.CalendarService",
        lambda db: _StubCalendar(),
    )
    out = _working_due_naive(db=None, start_dt=_utc(datetime(2026, 6, 10, 14, 0)), hours=24)
    got = _kl(out)
    assert (got.month, got.day, got.hour, got.minute) == (6, 11, 14, 0)
