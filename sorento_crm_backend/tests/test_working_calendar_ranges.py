"""Unit tests for contiguous working weekday ranges and external work-calendar summary."""
import pytest

from app.services.calendar_service import weekday_ranges_from_flags


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
