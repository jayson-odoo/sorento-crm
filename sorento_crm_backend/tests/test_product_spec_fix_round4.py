"""Fix lane round 4 on PR #1302 (#1286): the owner's hand test, 27 Sep.

F1 (backend half): an Only when on a yes-or-no specification compares the value the
engine holds. "Yes" is stored as "true"; "No" as "false", and a yes-or-no
specification nothing has read counts as No, because a Yes/No rule only ever sets Yes.

F2: See what would change shows only what THIS draft changes. The baseline is a
re-read of the same key with the CURRENT live rules, not the stored values, so a
product whose stored value already differs from today's rules (drift) is never counted
as changed by the draft. That drift is reported once, as its own number.

Every test here was run red against 1e12931b first.
"""
from __future__ import annotations

import pytest

from app.services import product_spec_preview
from tests.test_spec_registry_try_preview import _EDITOR, _key, _product, _spec, api  # noqa: F401

_BLACK = {"builder": {"kind": "words", "words": ["BLACK"], "value": "black"}}
_WHITE = {"builder": {"kind": "words", "words": ["WHITE"], "value": "white"}}
_BLACK_AS_WHITE = {"builder": {"kind": "words", "words": ["BLACK"], "value": "white"}}


def _finish(db, rules):
    return _key(
        db,
        "zzt_finish",
        label="ZZT finish",
        data_type="enum",
        unit=None,
        allowed_values=["black", "white"],
        derivation_rules=rules,
    )


def _derived(value):
    return {"zzt_finish": {"value": value}}, {"zzt_finish": {"source": "derived"}}


def _run(db, rules, job_id):
    product_spec_preview._run_job(job_id, "zzt_finish", rules, db)
    state = product_spec_preview.get(job_id)
    assert state["status"] == "done", state
    return state


# --------------------------------------------------------------------------- #
# F2: the baseline is the live rules, not the stored values
# --------------------------------------------------------------------------- #
def test_f2_a_one_word_rule_lists_only_the_products_that_word_matches(api):
    """The owner's case: one BLACK rule, and the preview listed M3049-S '-' -> White
    and 65 others that do not contain BLACK, because their STORED value differed
    from what the live rules read today."""
    db, _as = api
    _as(_EDITOR)
    _finish(db, [_WHITE])

    black = _product(db, "MATT BLACK TAP")
    _spec(db, black, {}, {})
    # Drift: the live WHITE rule reads White, but nothing is stored.
    white_unstored = _product(db, "WHITE BASIN")
    _spec(db, white_unstored, {}, {})
    # Drift: White is stored, but no live rule reads anything.
    white_stale = _product(db, "PLAIN MIRROR")
    _spec(db, white_stale, *_derived("white"))
    # In step: nothing to say.
    white_ok = _product(db, "WHITE BATH")
    _spec(db, white_ok, *_derived("white"))

    state = _run(db, [_WHITE, _BLACK], "zzt-r4-black")

    assert state["now_set"] == 1
    assert state["changed"] == 0
    assert state["no_longer_set"] == 0
    assert state["unchanged"] == 3
    assert [row["code"] for row in state["sample"]] == [black.product_code]
    assert state["sample"][0] == {
        "code": black.product_code,
        "name": black.product_name,
        "before": None,
        "after": "black",
    }
    assert "added" not in state and "removed" not in state


def test_f2_the_drift_count_is_the_stored_values_todays_rules_disagree_with(api):
    db, _as = api
    _as(_EDITOR)
    _finish(db, [_WHITE])

    _spec(db, _product(db, "WHITE BASIN"), {}, {})
    _spec(db, _product(db, "PLAIN MIRROR"), *_derived("white"))
    _spec(db, _product(db, "WHITE BATH"), *_derived("white"))
    # A person's own answer is not derived, so it is never drift.
    _spec(
        db,
        _product(db, "WHITE SINK"),
        {"zzt_finish": {"value": "black"}},
        {"zzt_finish": {"source": "human"}},
    )

    state = _run(db, [_WHITE, _BLACK], "zzt-r4-drift")

    assert state["drift"] == 2


def test_f2_no_drift_reads_zero(api):
    db, _as = api
    _as(_EDITOR)
    _finish(db, [_WHITE])
    _spec(db, _product(db, "WHITE BATH"), *_derived("white"))

    assert _run(db, [_WHITE, _BLACK], "zzt-r4-nodrift")["drift"] == 0


def test_f2_changed_and_no_longer_set_are_against_the_live_read(api):
    db, _as = api
    _as(_EDITOR)
    _finish(db, [_BLACK_AS_WHITE, _WHITE])

    # Live reads White (the wrong rule); the draft reads Black. Stored says Black
    # already, which a stored-value baseline would have called unchanged.
    fixed = _product(db, "BLACK TAP")
    _spec(db, fixed, *_derived("black"))
    # Live reads White; the draft drops the WHITE rule, so nothing is read.
    dropped = _product(db, "WHITE BASIN")
    _spec(db, dropped, *_derived("white"))

    state = _run(db, [_BLACK], "zzt-r4-changed")

    assert state["changed"] == 1
    assert state["no_longer_set"] == 1
    assert state["now_set"] == 0
    by_code = {row["code"]: row for row in state["sample"]}
    assert by_code[fixed.product_code]["before"] == "white"
    assert by_code[fixed.product_code]["after"] == "black"
    assert by_code[dropped.product_code]["before"] == "white"
    assert by_code[dropped.product_code]["after"] is None
    assert state["drift"] == 1


def test_f2_the_live_list_unchanged_previews_nothing(api):
    db, _as = api
    _as(_EDITOR)
    _finish(db, [_WHITE])
    _spec(db, _product(db, "WHITE BASIN"), {}, {})

    state = _run(db, [_WHITE], "zzt-r4-same")

    assert (state["changed"], state["now_set"], state["no_longer_set"]) == (0, 0, 0)
    assert state["sample"] == []


def test_f2_a_save_still_rereads_the_stored_drift(api):
    """The save path keeps its stored-versus-new comparison: that is why Save reports
    more updates than the preview, and why the drift line exists."""
    from app.services.product_spec_derivation import (
        configured_max_values,
        configured_rules,
        configured_scopes,
    )

    db, _as = api
    _finish(db, [_WHITE])
    _spec(db, _product(db, "WHITE BASIN"), {}, {})

    rows = list(
        product_spec_preview.readings_for_key(
            db,
            "zzt_finish",
            rules_by_key=configured_rules(db),
            scopes_by_key=configured_scopes(db),
            max_values=configured_max_values(db),
        )
    )
    assert [(row["before"], row["after"]) for row in rows] == [(None, "white")]


# --------------------------------------------------------------------------- #
# F1: Only when on a yes-or-no specification
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("held", "values", "is_", "passes"),
    [
        (True, ["true"], True, True),
        (None, ["true"], True, False),
        (None, ["false"], True, True),
        (True, ["false"], True, False),
        (False, ["false"], True, True),
        (None, ["false"], False, False),
        (True, ["false"], False, True),
    ],
)
def test_f1_only_when_yes_or_no_compares_the_held_boolean(held, values, is_, passes):
    from app.services.product_spec_rules import gate_passes

    builder = {"only_when": {"spec": "zzt_board", "is": is_, "values": values}}
    held_values = {} if held is None else {"zzt_board": held}
    assert gate_passes(builder, held_values) is passes


def test_f1_black_only_when_chopping_board_is_yes(api):
    """The owner's hand test: BLACK -> Black, Only when Chopping board is Yes."""
    db, _as = api
    _as(_EDITOR)
    _key(
        db,
        "zzt_board",
        label="ZZT chopping board",
        data_type="boolean",
        unit=None,
        derivation_rules=[
            {"builder": {"kind": "words", "words": ["CHOPPING BOARD"], "value": True}}
        ],
    )
    _finish(db, [])
    board = _product(db, "BLACK SINK WITH CHOPPING BOARD")
    _spec(db, board, {}, {})
    _spec(db, _product(db, "BLACK TAP"), {}, {})

    gated = {
        "builder": {
            **_BLACK["builder"],
            "only_when": {"spec": "zzt_board", "is": True, "values": ["true"]},
        }
    }
    state = _run(db, [gated], "zzt-r4-board")

    assert [row["code"] for row in state["sample"]] == [board.product_code]
    assert state["now_set"] == 1
