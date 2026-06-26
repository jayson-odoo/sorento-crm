"""Unit tests for the pure prev/next neighbour math.

``compute_neighbours(ordered_ids, current_id)`` is intentionally DB-free, so these
tests exercise the position/wrap logic directly. They cover the UAC items the helper
is responsible for:

- UAC-2  1-based index of the current id within the ordered set.
- UAC-3  next/prev are the adjacent ids in display order.
- UAC-6  circular wrap (first.prev = last, last.next = first).
- UAC-7  single-record set -> both neighbours None, index 1.
- UAC-8  id absent from the set -> index None (caller does the D2 fallback).
"""
from __future__ import annotations

import uuid

from app.services.record_navigation import compute_neighbours


def test_middle_record_has_both_neighbours_and_index():
    ids = ["a", "b", "c", "d", "e"]
    out = compute_neighbours(ids, "c")
    assert out == {"total": 5, "index": 3, "prev_id": "b", "next_id": "d"}


def test_first_record_prev_wraps_to_last():
    # UAC-6: Prev on the first record lands on the last.
    ids = ["a", "b", "c", "d"]
    out = compute_neighbours(ids, "a")
    assert out["index"] == 1
    assert out["prev_id"] == "d"
    assert out["next_id"] == "b"


def test_last_record_next_wraps_to_first():
    # UAC-6: Next on the last record lands on the first.
    ids = ["a", "b", "c", "d"]
    out = compute_neighbours(ids, "d")
    assert out["index"] == 4
    assert out["next_id"] == "a"
    assert out["prev_id"] == "c"


def test_single_element_set_has_no_neighbours_index_one():
    # UAC-7: total == 1 -> both chevrons disabled, pager reads "1 / 1".
    out = compute_neighbours(["only"], "only")
    assert out == {"total": 1, "index": 1, "prev_id": None, "next_id": None}


def test_two_element_set_wraps_both_ways():
    # With exactly 2 ids, prev and next of either point at the other (circular).
    out_first = compute_neighbours(["a", "b"], "a")
    assert out_first == {"total": 2, "index": 1, "prev_id": "b", "next_id": "b"}
    out_second = compute_neighbours(["a", "b"], "b")
    assert out_second == {"total": 2, "index": 2, "prev_id": "a", "next_id": "a"}


def test_empty_set_returns_zero_total_no_index():
    out = compute_neighbours([], "anything")
    assert out == {"total": 0, "index": None, "prev_id": None, "next_id": None}


def test_id_absent_returns_index_none_with_total():
    # UAC-8 contract: caller sees index None and decides to fall back to the
    # unfiltered set. total still reflects the (filtered) set size.
    out = compute_neighbours(["a", "b", "c"], "z")
    assert out == {"total": 3, "index": None, "prev_id": None, "next_id": None}


def test_string_uuid_id_coercion():
    # ids may be UUID objects in the list and a str passed as current_id (or vice
    # versa); the helper compares by str() so both forms resolve.
    u1, u2, u3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    out = compute_neighbours([u1, u2, u3], str(u2))
    assert out["index"] == 2
    assert out["prev_id"] == str(u1)
    assert out["next_id"] == str(u3)
    # next_id/prev_id are always returned as str.
    assert isinstance(out["prev_id"], str)
    assert isinstance(out["next_id"], str)


def test_current_id_passed_as_non_str_is_coerced():
    u1, u2, u3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    out = compute_neighbours([str(u1), str(u2), str(u3)], u2)  # current_id is UUID
    assert out["index"] == 2
    assert out["prev_id"] == str(u1)


def test_deterministic_first_match_with_duplicate_looking_ids():
    # If the ordered list somehow contains the same id twice, the helper resolves
    # to the FIRST occurrence deterministically (no ambiguity / no exception).
    ids = ["a", "dup", "dup", "b"]
    out = compute_neighbours(ids, "dup")
    assert out["index"] == 2  # first 'dup' at position 2 (1-based)
    assert out["prev_id"] == "a"
    assert out["next_id"] == "dup"  # the second duplicate follows the first
