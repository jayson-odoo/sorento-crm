"""Coder-7 cluster report T2 (16 Sep 2026): `scripts/chatbot_record_turn.py::_pending_of`
read the open question only from the `remembered` trace stage - a CANNED lane
(`escalate_offer`, `demand_qty`, `clarify_menu`-as-domain-menu, ...) never emits that
stage at all (`engine.py`'s canned-lane arm, ~L1596-1630, returns straight from
`_complete_canned_lane`, calling no `_record_memory_trace`), so 122/122 sampled
escalation-offer turns in `focus_full` recorded `expected.pending: null` even though
every one of them opened a real question. Finding 2a's fix (a dry-run turn now hands
back `TurnResult.session_patch`) made this visible in `test_turn_replay.py`, which only
grades `pending` when either side is non-null: before 2a, the ACTUAL side read null too,
masking the gap.

`reply["quick_replies"]` (n8n's comma-joined option-label string, AC-507) is non-null
EXACTLY when a question was asked - unlike `reply["result_set"]`, which this same
function's docstring already ruled out for false-positiving on a plain multi-row
ANSWER (a real 11-row stock reply with no question still populates `result_set`). This
file proves the fallback is precise: it fires only when the primary (`remembered`
stage) source is silent, and only when `quick_replies` is truthy.

Not itself a replay case - this is a pure unit test of the recorder's derivation
function, run with hand-built `trace`/`row` inputs (no DB, no live turn). Importing the
script as a module (it has no `if __name__` side effects on import) rather than via
`sys.path` hacks scattered per-test - one insertion, at module load.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "chatbot_record_turn.py"
_spec = importlib.util.spec_from_file_location("chatbot_record_turn", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
recorder = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("chatbot_record_turn", recorder)
_spec.loader.exec_module(recorder)


def _remembered_stage(open_question: dict) -> dict:
    return {
        "stage": "remembered",
        "raw": {"session_patch": {"open_question": open_question}},
    }


class TestPrimarySourceUnchanged:
    """The `remembered` stage, when present, still wins - the ASK arm's own shape is
    untouched by this fix."""

    def test_an_ask_arm_turn_still_reads_from_the_remembered_stage(self):
        trace = [
            _remembered_stage(
                {
                    "kind": "product_pick",
                    "options": [{"label": "SRTWC286-SH-150"}, {"label": "SRTWC286-SH-200"}],
                }
            )
        ]
        result = recorder._pending_of(trace, row={"response": {"reply": {"quick_replies": "ignored"}}})

        assert result == {"kind": "product_pick", "option_labels": ["SRTWC286-SH-150", "SRTWC286-SH-200"]}

    def test_a_turn_that_really_asked_nothing_still_reads_null_from_the_stage(self):
        trace = [_remembered_stage({})]
        result = recorder._pending_of(trace, row={"response": {"reply": {"quick_replies": None}}})

        assert result is None


class TestSecondSourceForCannedLanes:
    """No `remembered` stage at all (every canned lane) - the reply's own
    `quick_replies` is the fallback."""

    def test_no_remembered_stage_falls_back_to_reply_quick_replies(self):
        trace: list = []  # a canned lane's trace has "replied"/"sent", never "remembered"
        row = {
            "response": {
                "reply": {
                    "text": "Please choose who to route to (reply with the number):",
                    "quick_replies": "Maryam Ariffin, Cyndi, Aisyah, Balqis, Niki, Nurain",
                }
            }
        }

        result = recorder._pending_of(trace, row)

        assert result == {
            "kind": None,
            "option_labels": ["Maryam Ariffin", "Cyndi", "Aisyah", "Balqis", "Niki", "Nurain"],
        }

    def test_a_single_member_offer_still_parses_one_label(self):
        trace: list = []
        row = {"response": {"reply": {"quick_replies": "Yes"}}}

        result = recorder._pending_of(trace, row)

        assert result == {"kind": None, "option_labels": ["Yes"]}

    def test_no_remembered_stage_and_no_quick_replies_is_a_real_null_not_a_false_positive(self):
        """A canned lane that answers with a plain sentence (no question at all, e.g.
        `escalation_declined`) must not manufacture a pending from nothing."""
        trace: list = []
        row = {"response": {"reply": {"text": "Escalation declined.", "quick_replies": None}}}

        result = recorder._pending_of(trace, row)

        assert result is None

    def test_result_set_alone_is_never_read_even_as_a_fallback(self):
        """The false-positive this whole function exists to avoid: a plain multi-row
        ANSWER (no question) still populates `result_set` - the fallback must key off
        `quick_replies` only, never `result_set`."""
        trace: list = []
        row = {
            "response": {
                "reply": {
                    "text": "11 rows found.",
                    "quick_replies": None,
                    "result_set": [{"sku": f"P{i}"} for i in range(11)],
                }
            }
        }

        result = recorder._pending_of(trace, row)

        assert result is None

    def test_row_omitted_entirely_is_still_safe(self):
        """Backward compatible: an older call site that never passes `row` (there is
        none left in this script, but the parameter is optional) must not crash."""
        result = recorder._pending_of([])

        assert result is None


@pytest.mark.parametrize(
    "quick_replies",
    ["", "   ", ",", None],
)
def test_blank_or_empty_quick_replies_never_fabricates_labels(quick_replies):
    trace: list = []
    row = {"response": {"reply": {"quick_replies": quick_replies}}}

    result = recorder._pending_of(trace, row)

    assert result is None
