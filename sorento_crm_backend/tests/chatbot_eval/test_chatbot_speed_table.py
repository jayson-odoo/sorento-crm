"""CHATBOT-SPEED hand test: the old-vs-new reply-time table built from stored Console turns (read-only, US$0).

Each Console question is asked once on the copy running main ("old") and once on the copy running this lane ("new").
A turn is "new" when its `span_extract` event carries `prep_ms` (only this lane's code writes it). The table pairs the
latest old and the latest new turn of each question and shows the time before the parser (the `understood` stage minus
the parser's own call, so the model's run-to-run noise is left out), the whole turn, and whether the answer matched.
"""
from __future__ import annotations

from scripts.chatbot_eval import speed_table


def _turn(text, arm, *, turn_ms, und_ms, par_ms, span_ms=1100, reply="zz reply", at=0):
    event = {"kind": "span_extract", "ms": span_ms}
    if arm == "new":
        event["prep_ms"] = 300
    return {
        "text": text, "reply": reply, "turn_ms": turn_ms, "at": at,
        "trace": [{"stage": "understood", "ms": und_ms, "facts": {"latency_ms": par_ms}}, event],
    }


def test_a_turn_is_new_only_when_its_span_event_carries_prep_ms():
    assert speed_table.arm(_turn("q", "new", turn_ms=1, und_ms=1, par_ms=1)["trace"]) == "new"
    assert speed_table.arm(_turn("q", "old", turn_ms=1, und_ms=1, par_ms=1)["trace"]) == "old"


def test_before_the_parser_is_the_understood_stage_minus_the_parser_call():
    row = speed_table.measure(_turn("q", "old", turn_ms=7600, und_ms=5500, par_ms=3400))
    assert row["before_parser_ms"] == 2100 and row["turn_ms"] == 7600


def test_pairs_the_latest_old_and_new_turn_of_each_question():
    turns = [
        _turn("zz stock SRTWC8517", "old", turn_ms=7600, und_ms=5500, par_ms=3400, at=1),
        _turn("zz stock SRTWC8517", "old", turn_ms=7000, und_ms=5300, par_ms=3300, at=2),
        _turn("zz stock SRTWC8517", "new", turn_ms=6500, und_ms=4700, par_ms=3400, at=3),
        _turn("zz basin promo", "new", turn_ms=6000, und_ms=4500, par_ms=3300, at=4),
    ]
    rows = speed_table.pair(turns)
    assert [r["question"] for r in rows] == ["zz stock SRTWC8517", "zz basin promo"]
    first = rows[0]
    assert (first["old"]["turn_ms"], first["new"]["turn_ms"]) == (7000, 6500)
    assert first["saved_before_parser_ms"] == (5300 - 3300) - (4700 - 3400)
    assert rows[1]["old"] is None and rows[1]["saved_before_parser_ms"] is None


def test_the_answer_check_compares_the_reply_text():
    same = speed_table.pair([
        _turn("q", "old", turn_ms=1, und_ms=1, par_ms=0, reply="zz a", at=1),
        _turn("q", "new", turn_ms=1, und_ms=1, par_ms=0, reply="zz a", at=2),
    ])[0]
    differs = speed_table.pair([
        _turn("q", "old", turn_ms=1, und_ms=1, par_ms=0, reply="zz a", at=1),
        _turn("q", "new", turn_ms=1, und_ms=1, par_ms=0, reply="zz b", at=2),
    ])[0]
    assert same["answer_same"] is True and differs["answer_same"] is False


def test_the_table_is_markdown_in_seconds_with_a_median_line():
    rows = speed_table.pair([
        _turn("zz q1", "old", turn_ms=7600, und_ms=5500, par_ms=3400, at=1),
        _turn("zz q1", "new", turn_ms=6600, und_ms=4600, par_ms=3400, at=2),
    ])
    text = speed_table.render(rows)
    assert "| zz q1 | 2.1 | 1.2 | 0.9 | 7.6 | 6.6 | yes |" in text
    assert "Median" in text
