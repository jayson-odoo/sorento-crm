"""Tests for the is_discontinued auto-derivation helper."""
from app.services.product_service import is_discontinued_from_description


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
