"""Unit tests for contiguous working weekday ranges and external work-calendar summary."""
from datetime import time

import pytest

from app.services.calendar_service import format_time_12h_ampm, weekday_ranges_from_flags


def test_mon_fri_contiguous():
    flags = [True, True, True, True, True, False, False]
    assert weekday_ranges_from_flags(flags) == [("Monday", "Friday")]


def test_wednesday_off_two_ranges():
    flags = [True, True, False, True, True, False, False]
    assert weekday_ranges_from_flags(flags) == [
        ("Monday", "Tuesday"),
        ("Thursday", "Friday"),
    ]


def test_single_wednesday():
    flags = [False, False, True, False, False, False, False]
    assert weekday_ranges_from_flags(flags) == [("Wednesday", "Wednesday")]


def test_weekend_only():
    flags = [False, False, False, False, False, True, True]
    assert weekday_ranges_from_flags(flags) == [("Saturday", "Sunday")]


def test_all_days():
    flags = [True] * 7
    assert weekday_ranges_from_flags(flags) == [("Monday", "Sunday")]


def test_no_working_days():
    assert weekday_ranges_from_flags([False] * 7) == []


def test_invalid_length():
    with pytest.raises(ValueError):
        weekday_ranges_from_flags([True] * 6)


def test_format_time_12h_ampm_morning():
    assert format_time_12h_ampm(time(9, 0)) == "09:00 A.M."


def test_format_time_12h_ampm_noon():
    assert format_time_12h_ampm(time(12, 0)) == "12:00 P.M."


def test_format_time_12h_ampm_midnight():
    assert format_time_12h_ampm(time(0, 0)) == "12:00 A.M."


def test_format_time_12h_ampm_afternoon():
    assert format_time_12h_ampm(time(17, 30)) == "05:30 P.M."


def test_format_time_12h_ampm_with_seconds():
    assert format_time_12h_ampm(time(8, 15, 1)) == "08:15:01 A.M."
