"""Tests for the is_discontinued auto-derivation helpers."""
from app.services.product_service import (
    is_discontinued_from_description,
    is_discontinued_from_row,
)


def test_starts_with_four_asterisks_returns_true():
    assert is_discontinued_from_description("****Discontinued sink") is True


def test_no_asterisks_returns_false():
    assert is_discontinued_from_description("Standard product description") is False


def test_three_asterisks_returns_false():
    assert is_discontinued_from_description("***Almost discontinued") is False


def test_five_asterisks_returns_true():
    # `****` is a prefix; extra asterisks still satisfy the rule.
    assert is_discontinued_from_description("*****Heavy mark") is True


def test_leading_whitespace_is_ignored():
    assert is_discontinued_from_description("   ****Trimmed") is True
    assert is_discontinued_from_description("\t\n****Tabs") is True


def test_asterisks_in_middle_returns_false():
    assert is_discontinued_from_description("Sink **** in the middle") is False


def test_none_returns_false():
    assert is_discontinued_from_description(None) is False


def test_empty_string_returns_false():
    assert is_discontinued_from_description("") is False


def test_only_whitespace_returns_false():
    assert is_discontinued_from_description("   ") is False


# --- is_discontinued_from_row: explicit column wins, description is the fallback ---


def test_row_checked_column_wins_over_plain_description():
    # Mocha AutoCount export: checkbox says discontinued, description has no stars.
    assert is_discontinued_from_row({"Discontinued": "Checked"}, "MOCHA BIB TAP") is True


def test_row_unchecked_column_wins_over_starred_description():
    # `**X**` wrap is legacy naming in the Mocha file, not a status; the
    # explicit column must override the star heuristic.
    assert (
        is_discontinued_from_row({"Discontinued": "Unchecked"}, "****MOCHA JACUZZI F035J")
        is False
    )


def test_row_without_column_falls_back_to_description():
    assert is_discontinued_from_row({"Item Code": "F035J"}, "****MOCHA JACUZZI") is True
    assert is_discontinued_from_row({"Item Code": "2001"}, "MBS ROLLER REFILL") is False


def test_row_blank_cell_falls_back_to_description():
    assert is_discontinued_from_row({"Discontinued": ""}, "****OLD SINK") is True
    assert is_discontinued_from_row({"Discontinued": None}, "****OLD SINK") is True
    assert is_discontinued_from_row({"Discontinued": "   "}, "CURRENT SINK") is False


def test_row_accepts_boolean_and_truthy_spellings():
    assert is_discontinued_from_row({"Discontinued": True}, "PLAIN") is True
    assert is_discontinued_from_row({"Discontinued": False}, "****STARRED") is False
    for spelling in ("T", "true", "1", "y", "YES", "checked"):
        assert is_discontinued_from_row({"Discontinued": spelling}, "PLAIN") is True


def test_row_snake_case_key_supported():
    assert is_discontinued_from_row({"is_discontinued": "true"}, "PLAIN") is True
    assert is_discontinued_from_row({"discontinued": "Unchecked"}, "****STARRED") is False
