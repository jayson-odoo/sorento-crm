"""R2 - CS-routing predicate engine unit tests (pure, no DB).

UAC groups ME (matching) + RES (ranking). Rows are lightweight fakes so the engine
is proven without the migration / DB.
"""
from datetime import datetime
from types import SimpleNamespace

from app.services.cs_routing_match import (
    canonical_conditions,
    predicate_passes,
    rank_matching_rows,
    row_matches,
    select_pin_row,
)


def _row(conditions, priority=0, created_at=None, tag=None):
    return SimpleNamespace(
        match_conditions=conditions,
        priority=priority,
        created_at=created_at or datetime(2026, 1, 1),
        tag=tag,
    )


# ------------------------------------------------------------------ ME group

def test_me2_equals():
    p = {"field": "sales_type", "operator": "equals", "value": "project"}
    assert predicate_passes(p, {"sales_type": "project"}) is True
    assert predicate_passes(p, {"sales_type": "cash_sales"}) is False


def test_me3_not_equals_present_and_different():
    p = {"field": "sales_type", "operator": "not_equals", "value": "project"}
    assert predicate_passes(p, {"sales_type": "cash_sales"}) is True
    assert predicate_passes(p, {"sales_type": "project"}) is False


def test_me4_contains_and_not_contains_string_only():
    c = {"field": "title", "operator": "contains", "value": "urgent"}
    nc = {"field": "title", "operator": "not_contains", "value": "urgent"}
    assert predicate_passes(c, {"title": "very urgent request"}) is True
    assert predicate_passes(c, {"title": "routine"}) is False
    assert predicate_passes(nc, {"title": "routine"}) is True
    assert predicate_passes(nc, {"title": "urgent!"}) is False


def test_me5_multi_predicate_is_AND():
    conds = [
        {"field": "sales_type", "operator": "equals", "value": "project"},
        {"field": "sponsor_subject", "operator": "equals", "value": "showroom"},
    ]
    assert row_matches(conds, {"sales_type": "project", "sponsor_subject": "showroom"}) is True
    assert row_matches(conds, {"sales_type": "project", "sponsor_subject": "mockup"}) is False


def test_me6_null_field_never_equals():
    p = {"field": "sales_type", "operator": "equals", "value": "project"}
    assert predicate_passes(p, {"sales_type": None}) is False
    assert predicate_passes(p, {}) is False  # absent == null


def test_me7_empty_conditions_is_wildcard():
    assert row_matches([], {"anything": "x"}) is True
    assert row_matches(None, {}) is True


def test_me8_unknown_operator_never_matches():
    p = {"field": "sales_type", "operator": "regex", "value": ".*"}
    assert predicate_passes(p, {"sales_type": "project"}) is False


# ------------------------------------------------------------------ RES group

def test_res1_lower_priority_wins():
    specific = _row([{"field": "sales_type", "operator": "equals", "value": "project"}],
                    priority=1, tag="A")
    wildcard = _row([], priority=2, tag="B")
    winner = select_pin_row([wildcard, specific], {"sales_type": "project"})
    assert winner.tag == "A"


def test_res2_wildcard_can_win_pure_priority_no_auto_specificity():
    wildcard = _row([], priority=1, tag="WILD")
    specific = _row([{"field": "sales_type", "operator": "equals", "value": "project"}],
                    priority=2, tag="SPEC")
    winner = select_pin_row([specific, wildcard], {"sales_type": "project"})
    assert winner.tag == "WILD"  # pure admin priority, wildcard NOT auto-deprioritized


def test_res3_created_at_tiebreak():
    early = _row([], priority=1, created_at=datetime(2026, 1, 1), tag="EARLY")
    late = _row([], priority=1, created_at=datetime(2026, 6, 1), tag="LATE")
    winner = select_pin_row([late, early], {})
    assert winner.tag == "EARLY"


def test_res4_no_match_returns_none():
    specific = _row([{"field": "sales_type", "operator": "equals", "value": "project"}],
                    priority=1)
    assert select_pin_row([specific], {"sales_type": "cash_sales"}) is None
    assert select_pin_row([], {"sales_type": "project"}) is None


def test_ranking_is_stable_and_ordered():
    rows = [
        _row([], priority=3, tag="c"),
        _row([], priority=1, tag="a"),
        _row([], priority=2, tag="b"),
    ]
    ranked = rank_matching_rows(rows, {})
    assert [r.tag for r in ranked] == ["a", "b", "c"]


# ------------------------------------------------------- canonicalization (R1 risk)

def test_canonical_conditions_order_independent():
    a = [
        {"field": "sales_type", "operator": "equals", "value": "project"},
        {"field": "sponsor_subject", "operator": "equals", "value": "showroom"},
    ]
    b = list(reversed(a))
    assert canonical_conditions(a) == canonical_conditions(b)


def test_canonical_conditions_empty_and_none_equal():
    assert canonical_conditions([]) == canonical_conditions(None) == "[]"
