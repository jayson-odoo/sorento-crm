"""Regression tests for the shared Total Project Value validator.

One guard rail for portal + system forms - see
docs/plans/PLAN-project-value-centralized-validation.md.
"""
from decimal import Decimal

import pytest

from app.services.error_handler import AppException
from app.services.validators import PROJECT_VALUE_MAX, validate_project_value


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, None),
        ("", None),
        ("   ", None),
        (1234, Decimal("1234")),
        (1234.5, Decimal("1234.5")),
        ("1234", Decimal("1234")),
        ("1234.00", Decimal("1234.00")),
        ("0.5", Decimal("0.5")),
        (Decimal("9999999999999.99"), Decimal("9999999999999.99")),
        (-1234, Decimal("-1234")),
    ],
)
def test_valid_values_pass_through(raw, expected):
    assert validate_project_value(raw) == expected


@pytest.mark.parametrize("raw", ["800K", "abc", "1.6 mil", "RM 1000", "1,234"])
def test_non_numeric_rejected(raw):
    with pytest.raises(AppException) as exc:
        validate_project_value(raw)
    assert "must be a number" in str(exc.value.detail["message"])


@pytest.mark.parametrize(
    "raw",
    [
        PROJECT_VALUE_MAX,                       # exactly 10^13 -> out of range
        Decimal("10000000000000"),
        "123446433232323232323232",
        -(Decimal(10) ** 13),
    ],
)
def test_out_of_range_rejected(raw):
    with pytest.raises(AppException) as exc:
        validate_project_value(raw)
    assert "too large" in str(exc.value.detail["message"])


def test_max_boundary_is_inclusive_below_limit():
    # 9,999,999,999,999.99 is the largest value Numeric(15,2) accepts.
    assert validate_project_value("9999999999999.99") == Decimal("9999999999999.99")
