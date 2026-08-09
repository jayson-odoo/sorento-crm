"""S7b gate, part 1 - ONE ranking, shared by the tester and by production (AC-P6a,
AC-P6b, AC-P6c, AC-P5/AC-D20).

Written BEFORE the implementation. This is the file that decides whether the rule
tester is worth having. A tester that answers from its own ranking agrees with
production right up to the day it matters, and the day it matters is the day an
admin uses it to decide that a mapping is safe.

`test_warranty_engine.py` (69 tests) already pins what `resolve_kind` ANSWERS. This
file pins how that answer is PRODUCED, because S7b needs three things the current
shape cannot give:

1. **The rule that decided it** (AC-P6). `resolve_kind` returns a Kind, and a Kind
   cannot tell an admin whether it won on a model list or on a category rule nobody
   remembers writing. `_RuleMatch` already carries everything needed and throws it
   away at the last line.

2. **Every rule that matched, in rank order** (AC-P6c). A mapping that wins by one
   tie-break is a different fact from a mapping that is the only match, and only the
   second is safe to stop thinking about. The winner alone cannot express that.

3. **A rule that is not saved yet** (AC-P6b). AC-P6 says "before saving". The
   admin's real question is whether the rule they are about to write will win, and a
   tester that can only see saved rules cannot answer it.

**AC-P6a names only `resolve_kind_match()`, and that function alone cannot satisfy
AC-P6b or AC-P6c.** A winner-only accessor forces the tester to build the ranked
list itself, which is precisely the second ranking AC-P6a exists to forbid. So this
gate pins a third name, `rank_kind_matches()`, and makes the other two delegate to
it. The contradiction is recorded in the report rather than worked around silently.

The delegation is asserted BEHAVIOURALLY (a table of inputs where
``resolve_kind(...) is resolve_kind_match(...).kind``) rather than by reading source,
because behaviour is what drifts. The source-level "there is only one ranking" guard
lives in ``test_warranty_config_guards.py``.

Everything runs on Postgres via ``blank_session`` - never sqlite. Rows are marked
with ``TEST_PREFIX`` and discarded by the outer rollback.

Run: venv/bin/python -m pytest tests/test_warranty_config_ranking.py -q -p no:randomly
"""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import uuid
from typing import Optional

import pytest

from app.models.warranty import WarrantyKindRule, WarrantyProductKind

from ._pg_fixture import TEST_PREFIX, blank_session, unique_code

# ---------------------------------------------------------------- the contract

WARRANTY_SERVICE = "app.services.warranty_service"

# AC-P6a, named in the UAC. Returns the WINNING match, or None. `_RuleMatch` gains
# `.rule`, so the caller can say WHICH rule decided it.
WINNER_FN = "resolve_kind_match"

# NOT named in the UAC, and required by it. AC-P6c needs the whole ranked list and
# AC-P6b needs an unsaved rule ranked alongside the saved ones; a function that
# returns only the winner can give neither, so the tester would have to rank for
# itself - the exact duplication AC-P6a forbids. One name, three callers.
RANK_FN = "rank_kind_matches"

# The signature the gate pins for RANK_FN. `extra_rules` are TRANSIENT
# `WarrantyKindRule` instances (never added to the session): the tester's candidate.
RANK_SIGNATURE = (
    "rank_kind_matches(db, *, product_code=None, category_code=None, "
    "product_name=None, extra_rules=()) -> list[_RuleMatch]"
)


# ----------------------------------------------------------------------- fixtures


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


# ------------------------------------------------------------------ helpers


def _module(dotted: str, why: str):
    try:
        found = importlib.util.find_spec(dotted)
    except (ImportError, ModuleNotFoundError):
        found = None
    if found is None:
        raise AssertionError(f"{dotted} does not exist. {why}")
    return importlib.import_module(dotted)


def _fn(name: str, signature: str):
    module = _module(WARRANTY_SERVICE, "The ranking lives beside the algorithm it ranks.")
    fn = getattr(module, name, None)
    assert callable(fn), (
        f"{WARRANTY_SERVICE}.{name} must exist: {signature}. AC-P6a - the tester runs "
        "the PRODUCTION ranking, not a copy of it."
    )
    return fn


def _rank():
    return _fn(RANK_FN, RANK_SIGNATURE)


def _winner():
    return _fn(
        WINNER_FN,
        "resolve_kind_match(db, *, product_code=None, category_code=None, "
        "product_name=None) -> _RuleMatch | None",
    )


def _resolve_kind():
    return _fn("resolve_kind", "resolve_kind(db, *, product_code, category_code, product_name)")


def _kind(db, stem: str, *, is_active: bool = True) -> WarrantyProductKind:
    row = WarrantyProductKind(
        id=str(uuid.uuid4()),
        code=unique_code(stem)[:64],
        name=f"{TEST_PREFIX} {stem}"[:255],
        is_active=is_active,
    )
    db.add(row)
    db.flush()
    return row


def _rule(db, kind, match_type: str, match_value: str, *, priority: int = 0) -> WarrantyKindRule:
    row = WarrantyKindRule(
        id=str(uuid.uuid4()),
        kind_id=kind.id,
        match_type=match_type,
        match_value=match_value,
        priority=priority,
    )
    db.add(row)
    db.flush()
    return row


def _candidate(kind_id: str, match_type: str, match_value: str, priority: int = 0):
    """An UNSAVED rule - never added to the session (AC-P6b)."""
    return WarrantyKindRule(
        kind_id=kind_id, match_type=match_type, match_value=match_value, priority=priority
    )


def _rule_count(db) -> int:
    return db.query(WarrantyKindRule).count()


# =============================================================================
# AC-P6a - the winning match, carrying the rule that produced it
# =============================================================================


def test_a_rule_match_carries_the_rule_that_produced_it(db):
    """AC-P6a. `_RuleMatch` has kind, priority, specificity, matched_length and
    kind_code, and drops the one thing AC-P6 asks the tester to show: WHICH rule.

    Without it the tester can say "Water Closet" and cannot say whether that came
    from an explicit model list or from a category rule that happens to catch
    everything - which is the whole difference between a working mapping and a
    lucky one.
    """
    rank = _rank()
    kind = _kind(db, "wc")
    rule = _rule(db, kind, "model_prefix", "SRTWC")

    matches = rank(db, product_code="SRTWC8152")
    assert matches, "A model_prefix rule that matches produced no ranked match."
    top = matches[0]
    assert getattr(top, "rule", None) is not None, (
        "_RuleMatch.rule must exist (AC-P6a). The tester has to name the deciding "
        "rule, and re-deriving it from kind + match_type is a second ranking."
    )
    assert top.rule.id == rule.id
    assert top.kind.id == kind.id


def test_resolve_kind_match_returns_the_winner_and_nothing_else(db):
    """AC-P6a. The winner is the head of the ranked list, and no match is None."""
    winner = _winner()
    rank = _rank()
    kind = _kind(db, "wc")
    _rule(db, kind, "model_prefix", "SRTWC")

    got = winner(db, product_code="SRTWC8152")
    assert got is not None
    assert got.kind.id == kind.id
    assert got.sort_key == rank(db, product_code="SRTWC8152")[0].sort_key

    assert winner(db, product_code="NOTHINGMATCHESTHIS") is None, (
        "An unmatched code must return None, not raise - nothing in this journey blocks."
    )


@pytest.mark.parametrize(
    "product_code,category_code,product_name,why",
    [
        ("SRTWC8152", None, None, "a prefix match"),
        ("SRTWC8152-RL", "SRT-WC", None, "prefix and category both match"),
        (None, "SRT-WC", None, "category alone"),
        (None, None, "Honeycomb Series water closet", "series alone"),
        ("SRTMCB8071-BL", None, None, "an explicit model list"),
        ("NOTHINGMATCHES", "NOPE", "nothing", "nothing matches at all"),
        (None, None, None, "no input at all"),
        ("", "", "", "empty input"),
    ],
)
def test_resolve_kind_is_exactly_resolve_kind_match_dot_kind(
    db, product_code, category_code, product_name, why
):
    """AC-P6a, the parity test. THIS is the one that stops the tester and production
    drifting.

    `resolve_kind`'s existing contract is unchanged - every one of the 69 tests in
    `test_warranty_engine.py` still passes - and it is now a one-line accessor over
    the same ranking the tester reads. Two implementations that agree today diverge
    on the first tie-break somebody adjusts in one of them.
    """
    resolve_kind = _resolve_kind()
    winner = _winner()

    wc = _kind(db, "wc")
    mirror = _kind(db, "mirror")
    _rule(db, wc, "model_prefix", "SRTWC")
    _rule(db, wc, "category", "SRT-WC")
    _rule(db, wc, "series", "Honeycomb")
    _rule(db, mirror, "model_list", "SRTMCB8071-BL, SRTMCB6071-BL")

    kwargs = dict(
        product_code=product_code, category_code=category_code, product_name=product_name
    )
    kind = resolve_kind(db, **kwargs)
    match = winner(db, **kwargs)

    if kind is None:
        assert match is None, (
            f"{why}: resolve_kind said None but resolve_kind_match found a winner. "
            "They must be the same ranking."
        )
    else:
        assert match is not None, f"{why}: resolve_kind resolved but resolve_kind_match did not."
        assert match.kind.id == kind.id, (
            f"{why}: resolve_kind chose {kind.code} and resolve_kind_match chose "
            f"{match.kind.code}. Two rankings."
        )


def test_resolve_kind_still_takes_the_same_arguments_it_always_did():
    """AC-P6a: "its existing contract is unchanged".

    A refactor that quietly renames a keyword breaks three live callers whose tests
    live in another file, and the failure surfaces as an unrelated TypeError.
    """
    resolve_kind = _resolve_kind()
    params = inspect.signature(resolve_kind).parameters
    for name in ("product_code", "category_code", "product_name"):
        assert name in params, f"resolve_kind lost its {name} keyword."
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY, (
            f"resolve_kind.{name} must stay keyword-only - every caller passes it by name."
        )


# =============================================================================
# AC-P6c - the whole ranked list, in the production order
# =============================================================================


def test_the_ranked_list_holds_every_match_not_only_the_winner(db):
    """AC-P6c. Three rules reach three different Kinds from one product code.

    An admin looking at one answer cannot tell whether the mapping is unambiguous.
    """
    rank = _rank()
    listed = _kind(db, "listed")
    prefixed = _kind(db, "prefixed")
    categorised = _kind(db, "categorised")
    _rule(db, listed, "model_list", "SRTWC8152-RL")
    _rule(db, prefixed, "model_prefix", "SRTWC")
    _rule(db, categorised, "category", "SRT-WC")

    matches = rank(db, product_code="SRTWC8152-RL", category_code="SRT-WC")
    assert len(matches) == 3, (
        f"Expected all three matching rules, got {len(matches)}. AC-P6c: a mapping "
        "that wins by one tie-break is a different fact from the only match."
    )


def test_the_ranked_list_is_sorted_by_the_production_sort_key(db):
    """AC-P6c: "ordered by the production `sort_key`".

    Asserted against `sort_key` itself rather than against an expected order of
    kinds, so the test states the rule instead of restating one example of it.
    """
    rank = _rank()
    listed = _kind(db, "listed")
    prefixed = _kind(db, "prefixed")
    categorised = _kind(db, "categorised")
    _rule(db, listed, "model_list", "SRTWC8152-RL", priority=0)
    _rule(db, prefixed, "model_prefix", "SRTWC", priority=0)
    _rule(db, categorised, "category", "SRT-WC", priority=5)

    matches = rank(db, product_code="SRTWC8152-RL", category_code="SRT-WC")
    keys = [m.sort_key for m in matches]
    assert keys == sorted(keys), f"Ranked list is not in sort_key order: {keys}"
    assert matches[0].kind.id == categorised.id, (
        "AC-D20 / AC-P5: priority is consulted BEFORE match-type specificity, so a "
        "priority-5 category rule outranks a priority-0 model list."
    )


def test_priority_beats_specificity_in_the_ranked_list_not_only_in_the_winner(db):
    """AC-P5 / AC-D20, asserted over the full list.

    The tester renders the whole list, so an implementation that applies priority
    only when picking the head would show an admin a correct winner above a wrongly
    ordered set of runners-up - and the runners-up are what the admin reads to
    decide whether the winner is safe.
    """
    rank = _rank()
    low_specificity_high_priority = _kind(db, "boosted-category")
    high_specificity_low_priority = _kind(db, "plain-list")
    _rule(db, low_specificity_high_priority, "category", "SRT-WC", priority=10)
    _rule(db, high_specificity_low_priority, "model_list", "SRTWC8152-RL", priority=0)

    matches = rank(db, product_code="SRTWC8152-RL", category_code="SRT-WC")
    assert [m.kind.id for m in matches] == [
        low_specificity_high_priority.id,
        high_specificity_low_priority.id,
    ]


def test_a_rule_that_did_not_match_is_absent_from_the_list(db):
    """The list is the MATCHES, not every rule. A tester that lists non-matches
    with rank None teaches an admin to skim, which is how the winner stops being
    read at all."""
    rank = _rank()
    wc = _kind(db, "wc")
    other = _kind(db, "other")
    _rule(db, wc, "model_prefix", "SRTWC")
    _rule(db, other, "model_prefix", "SRTMCB")

    matches = rank(db, product_code="SRTWC8152")
    assert [m.kind.id for m in matches] == [wc.id]


def test_an_inactive_kind_is_unreachable_through_the_ranking(db):
    """The existing engine filters on `is_active`. The refactor must keep it, or a
    Kind an admin deliberately retired starts answering complaints again."""
    rank = _rank()
    retired = _kind(db, "retired", is_active=False)
    _rule(db, retired, "model_prefix", "SRTWC")
    assert rank(db, product_code="SRTWC8152") == []


def test_an_empty_match_value_matches_nothing(db):
    """The existing engine's ruling, re-pinned on the new entry point.

    An empty value would match EVERYTHING - the same footgun as an empty rule-engine
    `rules[]` this repo has already been bitten by. Legacy rows can hold `''`
    (`match_value` is NOT NULL, and `''` is not NULL), so this is reachable data,
    not a hypothetical.
    """
    rank = _rank()
    kind = _kind(db, "wc")
    _rule(db, kind, "model_prefix", "")
    _rule(db, kind, "category", "   ")

    assert rank(db, product_code="SRTWC8152", category_code="SRT-WC") == []


# =============================================================================
# AC-P6b - the unsaved candidate
# =============================================================================


def test_an_unsaved_candidate_rule_is_ranked_alongside_the_saved_ones(db):
    """AC-P6b. The admin's real question is whether the rule they are about to
    write will win."""
    rank = _rank()
    incumbent = _kind(db, "incumbent")
    challenger = _kind(db, "challenger")
    _rule(db, incumbent, "category", "SRT-WC", priority=0)

    candidate = _candidate(challenger.id, "model_list", "SRTWC8152-RL", priority=0)
    matches = rank(
        db, product_code="SRTWC8152-RL", category_code="SRT-WC", extra_rules=(candidate,)
    )

    assert [m.kind.id for m in matches] == [challenger.id, incumbent.id], (
        "The candidate model_list did not outrank the saved category rule. It has to "
        "be ranked by the same sort_key, not appended."
    )
    assert matches[0].rule is candidate, (
        "The winning match must carry the candidate object itself, so the caller can "
        "mark it unsaved by identity rather than by guessing."
    )


def test_ranking_a_candidate_never_writes_it(db):
    """AC-P6b. The tester runs on a POST; a candidate that leaks into the session
    is a rule an admin never saved, silently deciding real complaints.
    """
    rank = _rank()
    kind = _kind(db, "wc")
    before = _rule_count(db)

    candidate = _candidate(kind.id, "model_prefix", "SRTWC")
    rank(db, product_code="SRTWC8152", extra_rules=(candidate,))
    db.flush()

    assert _rule_count(db) == before, (
        "The candidate rule was persisted. It must never be added to the session - "
        "not even transiently, since any flush in the request would write it."
    )
    assert candidate.id is None, "The candidate was given a primary key, so it was flushed."


def test_a_candidate_that_matches_nothing_is_simply_absent(db):
    """A tester that answers "your rule would not win" is useful; one that answers
    it by omitting the rule from a list of matches is the same answer, honestly."""
    rank = _rank()
    kind = _kind(db, "wc")
    saved = _rule(db, kind, "model_prefix", "SRTWC")

    candidate = _candidate(kind.id, "model_prefix", "SRTMCB")
    matches = rank(db, product_code="SRTWC8152", extra_rules=(candidate,))
    assert [m.rule.id for m in matches] == [saved.id]


def test_a_candidate_pointing_at_an_unknown_kind_contributes_no_match(db):
    """A rule whose `kind_id` names nothing cannot be ranked - there is no Kind to
    report. It must be dropped, not crash the tester: the field is a dropdown the
    FE can send stale."""
    rank = _rank()
    kind = _kind(db, "wc")
    _rule(db, kind, "model_prefix", "SRTWC")

    candidate = _candidate(str(uuid.uuid4()), "model_list", "SRTWC8152", priority=99)
    matches = rank(db, product_code="SRTWC8152", extra_rules=(candidate,))
    assert [m.kind.id for m in matches] == [kind.id]


def test_a_candidate_pointing_at_an_inactive_kind_contributes_no_match(db):
    """Same filter as a saved rule's. An inactive Kind is unreachable however the
    rule reaching it arrived."""
    rank = _rank()
    active = _kind(db, "active")
    retired = _kind(db, "retired", is_active=False)
    _rule(db, active, "model_prefix", "SRTWC")

    candidate = _candidate(retired.id, "model_list", "SRTWC8152", priority=99)
    matches = rank(db, product_code="SRTWC8152", extra_rules=(candidate,))
    assert [m.kind.id for m in matches] == [active.id]


def test_no_candidate_is_the_same_answer_as_no_argument(db):
    """`extra_rules` defaults to empty, and production calls it that way. A default
    that changed the answer would make every existing caller's result depend on a
    parameter none of them pass."""
    rank = _rank()
    kind = _kind(db, "wc")
    _rule(db, kind, "model_prefix", "SRTWC")

    without = rank(db, product_code="SRTWC8152")
    with_empty = rank(db, product_code="SRTWC8152", extra_rules=())
    assert [m.sort_key for m in without] == [m.sort_key for m in with_empty]
