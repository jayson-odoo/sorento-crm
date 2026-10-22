"""REPORT-SMART-L round S3, AC-S3-1: the ranking question is the parser's open question.

"Show me top salesppl in 2026 for cb6635" asks only what is missing (how many, measure, basis).
The ask is registered `answered_by_parser`, so the parser is SHOWN the question (the State's
Open question names the owed fields and the held period), and its declared answer (mode fill)
runs the first message's ask. Fake codes only.
"""
from __future__ import annotations

import json
from typing import Any

from app.services.chatbot import required_fields as rf
from app.services.chatbot.lanes.business import report_ask
from app.services.chatbot.turn import chat_state, question as question_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import (  # noqa: F401 - fixtures + helpers
    PERIOD_Q,
    _e,
    _rank,
    _reply,
    _seed_cabana,
    console,
)
from tests.chatbot.test_report_smart_step7 import KEEP, NEW_SUBJECT, THIS_YEAR, _state_on

FAMILY = ("CB6635-NL", "CB6635-PP")


def _seed_family(console) -> None:
    from tests._mc_lookup_seed import product

    db = console.session_factory()
    try:
        for code in FAMILY:
            product(db, company_id=DEFAULT_COMPANY_ID, code=code)
        db.commit()
    finally:
        db.close()


def _first(**overrides: Any) -> dict[str, Any]:
    """'Show me top salesppl in 2026 for cb6635' as the live parser reads it: no count, measure or basis."""
    base: dict[str, Any] = dict(top_n=None, measure=None, basis=None, state_changes=list(KEEP), **THIS_YEAR)
    base.update(overrides)
    return _rank(_e("cb6635", "product"), **base)


def _answer(**overrides: Any) -> dict[str, Any]:
    """The parser's reading of 'Top 5, by qty, delivered' when the State states the open question."""
    base: dict[str, Any] = dict(
        top_n=5, measure="qty", basis="delivered", state_changes=list(KEEP),
        open_question_answer={"mode": "fill", "picked": [], "items": [], "qty_for_all": None},
    )
    base.update(overrides)
    return _reply(**base)


def _record_state(console) -> list[str]:
    """Every State block the engine renders for the parser, in order."""
    shown: list[str] = []
    real = chat_state.render

    def spy(view: Any) -> Any:
        out = real(view)
        shown.append(out or "")
        return out

    console.monkeypatch.setattr(chat_state, "render", spy)
    return shown


def _open_line(state_text: str) -> str:
    return next((ln for ln in state_text.splitlines() if ln.startswith("- open question:")), "")


def test_s3_1_the_sales_ranking_required_ask_is_answered_by_the_parser() -> None:
    assert rf.ASKS[report_ask.ASK_NAME].answered_by_parser is True


def test_s3_1_a_held_ranking_slot_is_stated_as_the_open_question_with_its_held_period(console) -> None:
    _state_on(console)
    _seed_family(console)
    shown = _record_state(console)
    text, calls = console.say(_first(), "Show me top salesppl in 2026 for cb6635")
    assert calls == [], (text, calls)
    assert "Top 5" not in text and PERIOD_Q not in text, text  # the period is held, so only the rest is asked
    console.say(_answer(), "Top 5, by qty, delivered")
    state_text = shown[-1]
    line = _open_line(state_text)
    assert line and line != "- open question: none", state_text
    assert "top_n" in line and "basis" in line and ("metric" in line or "measure" in line), line
    assert "2026-01-01" in line and "2026-12-31" in line, line  # the held period rides with the question
    assert "period" not in json.loads(line.split(": ", 1)[1])["owed"], line


def test_s3_1_the_scope_slot_is_stated_as_an_open_question_too() -> None:
    slot = {"ask": report_ask.ASK_NAME, "values": {}, "asking": "scope", "options": [], "misses": 0,
            "extras": {"scope": {"question": "Within the ranking above, or across everything?"}}}
    obj = question_mod.of_required_ask(slot)
    assert obj is not None, "the scope question is never shown to the parser"
    assert obj["about"] == report_ask.ASK_NAME and obj["owed"] == ["scope"], obj
    assert "Within the ranking" in json.dumps(obj), obj


def test_s3_1_the_answer_runs_the_first_ask_for_the_held_year_never_asking_the_period(console) -> None:
    _state_on(console)
    _seed_family(console)
    text, calls = console.say(_first(), "Show me top salesppl in 2026 for cb6635")
    assert calls == [], (text, calls)
    text, calls = console.say(_answer(), "Top 5, by qty, delivered")
    assert "Which period?" not in text, text
    assert len(calls) == 1, (text, calls)
    args = calls[0]
    assert args["date_from"] == "2026-01-01" and args["date_to"] == "2026-12-31", args
    assert args["group_by"] == "sales_agent" and args["top_n"] == 5, args
    assert args["measure"] == "qty" and args["basis"] == "delivered", args
    assert str(args.get("product_code", "")).upper().startswith("CB6635"), args


def test_s3_1_near_miss_a_fresh_full_ask_replaces_the_question_and_runs_with_its_own_args(console) -> None:
    _state_on(console)
    _seed_family(console)
    console.cabana = _seed_cabana(console)
    text, calls = console.say(_first(), "Show me top salesppl in 2026 for cb6635")
    assert calls == [], (text, calls)
    text, calls = console.say(
        _rank(_e("Cabana", "brand"), top_n=3, measure="qty", basis="delivered", state_changes=NEW_SUBJECT, **THIS_YEAR),
        "top 3 salesman for cabana this year, by qty, delivered",
    )
    assert len(calls) == 1, (text, calls)
    args = calls[0]
    assert args["brand_ids"] == [console.cabana] and args["top_n"] == 3, args
    assert "product_code" not in args and "product_ids" not in args, args  # the old question's product is gone
