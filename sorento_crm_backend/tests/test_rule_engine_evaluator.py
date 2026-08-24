"""Unit tests for the pure rule evaluator (app/rule_engine/evaluator.py).

No I/O, no ORM - just condition-tree + fact-dict -> bool. Covers the operator
truth table, fail-closed behaviour (missing / null / garbage fact, unknown
operator, over-deep tree), the AND vs OR combinators, ``collect_fact_keys`` and
the combinator-aware ``failed_conditions``.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from app.rule_engine.evaluator import (
    collect_fact_keys,
    evaluate,
    failed_conditions,
)


def _cond(fact, operator, value, value_kind="literal"):
    return {
        "kind": "condition",
        "fact": fact,
        "operator": operator,
        "valueKind": value_kind,
        "value": value,
    }


def _group(combinator, *rules):
    return {"kind": "group", "combinator": combinator, "rules": list(rules)}


def _one(fact, operator, value, facts, value_kind="literal"):
    """Evaluate a single-condition AND group -> bool."""
    return evaluate(_group("and", _cond(fact, operator, value, value_kind)), facts)


# --------------------------------------------------------------------------- #
# Operator truth table                                                          #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "operator,fact_value,operand,expected",
    [
        # eq / neq (string + numeric coercion)
        ("eq", "Sorento", "Sorento", True),
        ("eq", "Sorento", "Cabana", False),
        ("eq", 5, "5", True),  # numeric coercion across str/int
        ("neq", "Sorento", "Cabana", True),
        ("neq", "Sorento", "Sorento", False),
        # contains (substring, case-insensitive)
        ("contains", "Sorento Sale", "sorento", True),
        ("contains", "Cabana Sale", "sorento", False),
        # in / not_in
        ("in", "b", ["a", "b", "c"], True),
        ("in", "z", ["a", "b", "c"], False),
        ("not_in", "z", ["a", "b", "c"], True),
        ("not_in", "b", ["a", "b", "c"], False),
        # numeric comparisons
        ("gt", 10, 5, True),
        ("gt", 5, 10, False),
        ("gte", 5, 5, True),
        ("gte", 4, 5, False),
        ("lt", 3, 5, True),
        ("lt", 5, 3, False),
        ("lte", 5, 5, True),
        ("lte", 6, 5, False),
        # between (inclusive)
        ("between", 5, [1, 10], True),
        ("between", 11, [1, 10], False),
        ("between", 1, [1, 10], True),
        # boolean
        ("is_true", True, None, True),
        ("is_true", False, None, False),
        ("is_false", False, None, True),
        ("is_false", True, None, False),
        # list operators
        ("contains_any", ["a", "b"], ["b", "z"], True),
        ("contains_any", ["a", "b"], ["y", "z"], False),
        ("contains_all", ["a", "b", "c"], ["a", "b"], True),
        ("contains_all", ["a"], ["a", "b"], False),
        ("not_contains", ["a", "b"], ["z"], True),
        ("not_contains", ["a", "b"], ["a"], False),
    ],
)
def test_operator_truth_table(operator, fact_value, operand, expected):
    assert _one("f", operator, operand, {"f": fact_value}) is expected


def test_before_after_dates():
    facts = {"f": date(2026, 1, 1)}
    assert _one("f", "before", "2026-06-01", facts) is True
    assert _one("f", "after", "2025-01-01", facts) is True
    assert _one("f", "before", "2025-01-01", facts) is False
    assert _one("f", "after", "2026-06-01", facts) is False


def test_between_date_end_bound_inclusive_of_whole_day():
    # A datetime at 23:59 on the end day must still fall inside a date-only end
    # bound (code-review fix: date-only END bound covers the whole day).
    facts = {"f": datetime(2026, 1, 31, 23, 59, 0)}
    assert _one("f", "between", ["2026-01-01", "2026-01-31"], facts) is True


# --------------------------------------------------------------------------- #
# Fail-closed (D5)                                                              #
# --------------------------------------------------------------------------- #


def test_missing_fact_fails_closed():
    assert _one("f", "eq", "x", {}) is False
    # even negative operators fail closed on a missing fact
    assert _one("f", "neq", "x", {}) is False
    assert _one("f", "not_in", ["x"], {}) is False


def test_null_fact_fails_closed():
    assert _one("f", "eq", "x", {"f": None}) is False
    assert _one("f", "is_false", None, {"f": None}) is False


def test_garbage_value_fails_closed():
    # gt on a non-numeric, non-date string -> _as_dt raises -> caught -> False
    assert _one("f", "gt", 5, {"f": "not-a-number"}) is False
    # between expects a list operand; a scalar raises -> False
    assert _one("f", "between", 5, {"f": 5}) is False
    # contains_any expects a list operand
    assert _one("f", "contains_any", "notalist", {"f": ["a"]}) is False


def test_unknown_operator_fails_closed():
    assert _one("f", "supercontains", "x", {"f": "x"}) is False


def test_missing_cross_fact_operand_fails_closed():
    tree = _group("and", _cond("a", "eq", "b", value_kind="fact"))
    # 'b' fact missing -> operand None -> False
    assert evaluate(tree, {"a": "x"}) is False


def test_cross_fact_eq_matches():
    tree = _group("and", _cond("a", "eq", "b", value_kind="fact"))
    assert evaluate(tree, {"a": "x", "b": "x"}) is True
    assert evaluate(tree, {"a": "x", "b": "y"}) is False


# --------------------------------------------------------------------------- #
# Combinators                                                                   #
# --------------------------------------------------------------------------- #


def test_and_group_all_must_pass():
    tree = _group(
        "and",
        _cond("name", "contains", "Sorento"),
        _cond("active", "is_true", None),
    )
    assert evaluate(tree, {"name": "Sorento Sale", "active": True}) is True
    assert evaluate(tree, {"name": "Sorento Sale", "active": False}) is False


def test_or_group_any_passes():
    tree = _group(
        "or",
        _cond("levels", "contains_any", ["sorento_dealer"]),
        _cond("name", "contains", "Sorento"),
    )
    # matches via name even though levels miss
    assert evaluate(tree, {"levels": ["cabana_dealer"], "name": "Sorento X"}) is True
    # matches via levels even though name misses
    assert evaluate(tree, {"levels": ["sorento_dealer"], "name": "Cabana X"}) is True
    # neither matches
    assert evaluate(tree, {"levels": ["cabana_dealer"], "name": "Cabana X"}) is False


def test_empty_or_none_tree_is_true():
    assert evaluate(None, {}) is True
    assert evaluate({"kind": "group", "combinator": "and", "rules": []}, {}) is True


def test_nested_groups_evaluate():
    tree = _group(
        "or",
        _group(
            "and",
            _cond("brand", "eq", "sorento"),
            _cond("region", "eq", "north"),
        ),
        _cond("vip", "is_true", None),
    )
    assert evaluate(tree, {"brand": "sorento", "region": "north", "vip": False}) is True
    assert evaluate(tree, {"brand": "sorento", "region": "south", "vip": False}) is False
    assert evaluate(tree, {"brand": "cabana", "region": "south", "vip": True}) is True


# --------------------------------------------------------------------------- #
# Depth guard (>5 -> False)                                                     #
# --------------------------------------------------------------------------- #


def test_depth_guard_over_five_is_false():
    # Build a chain of nested AND groups deeper than _MAX_DEPTH (5). The innermost
    # condition would pass, but the depth guard forces the over-deep group False.
    inner = _cond("f", "eq", "x")
    node = _group("and", inner)
    for _ in range(6):  # wrap 6 more times -> depth 7 for the leaf
        node = _group("and", node)
    assert evaluate(node, {"f": "x"}) is False


def test_within_depth_limit_passes():
    inner = _cond("f", "eq", "x")
    node = _group("and", inner)
    for _ in range(3):  # depth 4 for the leaf group - within limit
        node = _group("and", node)
    assert evaluate(node, {"f": "x"}) is True


# --------------------------------------------------------------------------- #
# collect_fact_keys                                                             #
# --------------------------------------------------------------------------- #


def test_collect_fact_keys_gathers_lhs_and_cross_fact_rhs():
    tree = _group(
        "or",
        _cond("promotion.name", "contains", "Sorento"),
        _group(
            "and",
            _cond("promotion.accessLevels", "contains_any", ["sorento_dealer"]),
            _cond("promotion.startDate", "before", "promotion.endDate", value_kind="fact"),
        ),
    )
    keys = collect_fact_keys(tree)
    assert keys == {
        "promotion.name",
        "promotion.accessLevels",
        "promotion.startDate",
        "promotion.endDate",  # cross-fact RHS captured
    }


def test_collect_fact_keys_none_tree_empty_set():
    assert collect_fact_keys(None) == set()


# --------------------------------------------------------------------------- #
# failed_conditions (combinator-aware)                                          #
# --------------------------------------------------------------------------- #


def test_failed_conditions_lists_blocking_leaf_in_and_group():
    tree = _group(
        "and",
        _cond("name", "contains", "Sorento"),
        _cond("active", "is_true", None),
    )
    facts = {"name": "Sorento Sale", "active": False}
    failed = failed_conditions(tree, facts)
    assert len(failed) == 1
    assert failed[0]["fact"] == "active"


def test_failed_conditions_empty_when_tree_passes():
    tree = _group("and", _cond("name", "contains", "Sorento"))
    assert failed_conditions(tree, {"name": "Sorento Sale"}) == []


def test_failed_conditions_ignores_passing_or_sibling():
    # In an OR group that PASSES, a failing sibling leaf must NOT be reported  - 
    # the group is not blocking.
    tree = _group(
        "or",
        _cond("name", "contains", "Sorento"),  # passes
        _cond("active", "is_true", None),  # fails, but irrelevant
    )
    facts = {"name": "Sorento Sale", "active": False}
    assert failed_conditions(tree, facts) == []
