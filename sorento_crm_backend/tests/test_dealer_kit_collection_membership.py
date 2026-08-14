"""Golden set for collection membership (AC-F2).

Written BEFORE the implementation.

A collection resolves as **rule union pins minus exclusions**, ordered by
`manual_order` and then by a documented fallback. The set algebra is what a
Designer reasons about ("I added this one by hand, I took that one out"), so it
has to behave the way they expect in every combination - most importantly, an
exclusion beats everything, including a pin the same person added earlier.

This file tests that algebra as pure data. Whether the RULE matched the right
products is a separate question with its own database-backed tests; here the
matched set is an input, which is what makes exhaustive cases cheap.
"""
from __future__ import annotations

import pytest

from app.services.dealer_kit.collection_membership import assemble_members


def _order(*ids):
    return list(ids)


# --------------------------------------------------------------------------
# The set algebra
# --------------------------------------------------------------------------


def test_a_rule_match_alone_is_the_membership():
    assert assemble_members(matched=["a", "b"], pinned=[], excluded=[]) == ["a", "b"]


def test_a_pin_adds_a_product_the_rule_missed():
    result = assemble_members(matched=["a"], pinned=["b"], excluded=[])
    assert set(result) == {"a", "b"}


def test_an_exclusion_removes_a_product_the_rule_matched():
    assert assemble_members(matched=["a", "b"], pinned=[], excluded=["b"]) == ["a"]


def test_an_exclusion_beats_a_pin():
    # The case a Designer hits when they pin something, change their mind and
    # exclude it. Silently keeping it because "they pinned it" would be the
    # system arguing with the more recent decision.
    assert assemble_members(matched=[], pinned=["a"], excluded=["a"]) == []


def test_an_exclusion_beats_a_rule_match_and_a_pin_together():
    assert assemble_members(matched=["a"], pinned=["a"], excluded=["a"]) == []


def test_a_product_matched_and_pinned_appears_once():
    assert assemble_members(matched=["a", "b"], pinned=["a"], excluded=[]) == ["a", "b"]


def test_duplicates_in_any_input_collapse():
    result = assemble_members(matched=["a", "a", "b"], pinned=["b", "b"], excluded=[])
    assert result == ["a", "b"]


def test_excluding_something_that_is_not_a_member_changes_nothing():
    assert assemble_members(matched=["a"], pinned=[], excluded=["z"]) == ["a"]


def test_an_empty_collection_is_empty_not_an_error():
    assert assemble_members(matched=[], pinned=[], excluded=[]) == []


def test_excluding_everything_yields_an_empty_collection():
    assert assemble_members(matched=["a", "b"], pinned=["c"], excluded=["a", "b", "c"]) == []


# --------------------------------------------------------------------------
# Ordering
# --------------------------------------------------------------------------


def test_manual_order_wins_over_the_fallback():
    result = assemble_members(
        matched=["a", "b", "c"], pinned=[], excluded=[], manual_order=_order("c", "a", "b")
    )
    assert result == ["c", "a", "b"]


def test_a_member_missing_from_manual_order_sorts_after_the_ordered_ones():
    # A Designer orders three products, then the rule starts matching a fourth.
    # It must not silently jump to the front, and it must not disappear.
    result = assemble_members(
        matched=["a", "b", "c", "d"], pinned=[], excluded=[], manual_order=_order("c", "a")
    )
    assert result[:2] == ["c", "a"]
    assert set(result[2:]) == {"b", "d"}


def test_manual_order_entries_that_are_no_longer_members_are_ignored():
    # The order list outlives the membership: a product removed from the rule
    # leaves a stale id behind, and it must not resurrect it.
    result = assemble_members(
        matched=["a", "b"], pinned=[], excluded=[], manual_order=_order("z", "b", "a")
    )
    assert result == ["b", "a"]


def test_an_excluded_product_stays_out_even_when_manual_order_names_it():
    result = assemble_members(
        matched=["a", "b"], pinned=[], excluded=["b"], manual_order=_order("b", "a")
    )
    assert result == ["a"]


def test_the_fallback_order_is_the_matched_order_then_pins():
    # With no manual order the caller's sequence is preserved - the caller sorts
    # the query, so the documented fallback is "whatever order the rule
    # produced", with hand-picked products after it.
    result = assemble_members(matched=["b", "a"], pinned=["z"], excluded=[])
    assert result == ["b", "a", "z"]


def test_ordering_is_stable_across_calls():
    args = dict(matched=["c", "a", "b"], pinned=["d"], excluded=[])
    assert assemble_members(**args) == assemble_members(**args)


# --------------------------------------------------------------------------
# Refusals and edges
# --------------------------------------------------------------------------


def test_none_is_accepted_wherever_a_list_is_optional():
    # The columns are nullable, so the resolver must not require the caller to
    # normalise them first.
    assert assemble_members(matched=["a"], pinned=None, excluded=None, manual_order=None) == ["a"]


@pytest.mark.parametrize("bad", [["a", None], [""], [None]])
def test_empty_or_missing_ids_are_dropped_rather_than_rendered(bad):
    # A null in the pinned array would otherwise become a tile bound to nothing.
    result = assemble_members(matched=["a"], pinned=bad, excluded=[])
    assert all(member for member in result)
    assert "a" in result
