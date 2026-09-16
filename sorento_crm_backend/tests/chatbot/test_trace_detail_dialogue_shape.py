"""AC-1035: `trace_detail` keeps its nine keys; `focus[]` and `open_question` entries
match the dialogue module's shape.

`focus[]` entries are `{slot, before, after, rule, source}`; `open_question` is
`{before, answer, after, handler, outcome}` (or `None` when nothing fired this turn).
Pure function, no DB: `compose_trace_detail` reads only `row.trace`.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.chatbot import trace_detail

NINE_KEYS = {
    "stages",
    "parse",
    "decay",
    "open_question",
    "focus",
    "tool",
    "crossdomain",
    "reveals",
    "session",
}


def _turn(records: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(trace=records)


class TestTraceDetailKeepsItsNineKeys:
    def test_the_nine_keys_are_unchanged(self) -> None:
        detail = trace_detail.compose_trace_detail(_turn([]))
        assert set(detail) == NINE_KEYS, sorted(detail)

    def test_no_focus_rule_fired_renders_an_empty_list_not_a_missing_key(self) -> None:
        detail = trace_detail.compose_trace_detail(_turn([]))
        assert detail["focus"] == []

    def test_no_open_question_activity_renders_none_not_a_missing_key(self) -> None:
        detail = trace_detail.compose_trace_detail(_turn([]))
        assert detail["open_question"] is None


class TestFocusEntryShape:
    def test_a_focus_entry_has_exactly_the_five_fields(self) -> None:
        records = [
            {
                "kind": "focus",
                "slot": "products",
                "before": [{"raw": "SRTWC8517"}],
                "after": [{"raw": "SRTWT2635"}],
                "rule": "replace_same_axis",
                "source": "current_message",
            }
        ]
        detail = trace_detail.compose_trace_detail(_turn(records))
        assert detail["focus"] == [
            {
                "slot": "products",
                "before": [{"raw": "SRTWC8517"}],
                "after": [{"raw": "SRTWT2635"}],
                "rule": "replace_same_axis",
                "source": "current_message",
            }
        ]


class TestOpenQuestionEntryShape:
    def test_an_open_question_entry_has_exactly_the_five_fields(self) -> None:
        records = [
            {
                "kind": "open_question",
                "before": {"kind": "product_pick", "expects": "pick", "options": 3, "quoted": False},
                "answer": {"resolved": True, "picks": [2], "yes_no": None, "free_text": None},
                "after": {"entities": 1, "entities_before": 0, "escalate": False, "declined": False},
                "handler": "product_pick",
                "outcome": "Resolved to the second frozen option.",
            }
        ]
        detail = trace_detail.compose_trace_detail(_turn(records))
        assert set(detail["open_question"]) == {"before", "answer", "after", "handler", "outcome"}
        assert detail["open_question"]["handler"] == "product_pick"
