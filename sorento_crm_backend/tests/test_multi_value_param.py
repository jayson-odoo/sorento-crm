"""FILTER-MULTISELECT: the shared multi-select filter param parser (app/utils/multi_value.py)."""
from __future__ import annotations

import pytest

from app.services.error_handler import AppException
from app.utils.multi_value import multi_uuids, multi_values

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"


@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, None),
        ([], None),
        ("", None),
        ([""], None),
        ([" , "], None),
        ("draft", ["draft"]),
        (["draft"], ["draft"]),
        ("draft,submitted", ["draft", "submitted"]),
        (["draft", "submitted"], ["draft", "submitted"]),
        (["draft,submitted", "void"], ["draft", "submitted", "void"]),
        ([" draft ", "draft", "submitted,draft"], ["draft", "submitted"]),
    ],
)
def test_multi_values_reads_single_repeated_and_comma_joined_alike(raw, expected):
    assert multi_values(raw) == expected


def test_multi_uuids_normalises_and_keeps_order():
    assert multi_uuids([f"{B},{A.upper()}"], "Company") == [B, A]


def test_multi_uuids_absent_is_no_filter():
    assert multi_uuids(None, "Company") is None


def test_multi_uuids_rejects_a_malformed_value_with_422():
    with pytest.raises(AppException) as err:
        multi_uuids([A, "nope"], "Company")
    assert err.value.status_code == 422
    assert "Company" in err.value.message


def test_more_than_200_values_is_a_422_naming_the_filter():
    from app.utils.multi_value import multi_choices, multi_text

    many = [f"v{i}" for i in range(201)]
    ids = [f"{i:08d}-1111-4111-8111-111111111111" for i in range(201)]
    for call in (
        lambda: multi_values(many, "status"),
        lambda: multi_text(many, "class_label"),
        lambda: multi_uuids(ids, "agent"),
        lambda: multi_choices(many, many, "state"),
    ):
        with pytest.raises(AppException) as exc:
            call()
        assert exc.value.status_code == 422
    assert len(multi_values([f"v{i}" for i in range(200)])) == 200
