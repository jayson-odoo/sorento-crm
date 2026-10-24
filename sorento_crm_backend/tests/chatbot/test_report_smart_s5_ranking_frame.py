"""REPORT-SMART-L S5-2 (AC-S5-2): a sales ranking that returned ranked rows is remembered as answered.

The ranking envelope carries no `figures`, so the turn's `looked_up` record said "missed" and the
episode digest wrote "..., but nothing was found" for a ranking that answered. A ranking that
returned no rows still says so. Fake names only.
"""
from __future__ import annotations

from typing import Any

from tests.chatbot.test_engine import stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import GRANT, PRODUCT_CODE, _e, _fake_body, _rank, console  # noqa: F401 - fixtures + helpers
from tests.chatbot.test_report_smart_step7 import KEEP, THIS_YEAR


def _digest_of_the_turn(console) -> tuple[str, list[str]]:
    """The episode digest's summary for the one stored turn, and the `looked_up` record's missed list."""
    from app.models.chatbot_turn import ChatbotTurn
    from app.services.chatbot.turn import episode_digest

    db = console.session_factory()
    try:
        row = db.query(ChatbotTurn).filter(ChatbotTurn.is_test.is_(True)).order_by(ChatbotTurn.created_at.desc()).first()
        assert row is not None, "harness: no stored turn"
        trace = row.trace or []
        turn = {"id": str(row.id), "created_at": row.created_at, "branch_kind": row.branch_kind,
                "status": row.status, "message": "top 3 salesman this year", "trace": trace}
        looked = next((r for r in trace if (r.get("kind") or r.get("stage")) == "looked_up"), {})
        return episode_digest.digest([turn])["summary"], list((looked.get("facts") or {}).get("missed") or [])
    finally:
        db.close()


def _run_ranking(console) -> str:
    text, calls = console.say(
        _rank(_e(PRODUCT_CODE, "product"), top_n=3, measure="qty", basis="delivered", state_changes=list(KEEP), **THIS_YEAR),
        "top 3 salesman this year",
    )
    assert len(calls) == 1, ("setup: the ranking did not run", text, calls)
    return text


def test_s5_2_a_ranking_with_ranked_rows_is_remembered_as_answered(console) -> None:
    text = _run_ranking(console)
    assert "AGENT A" in text, ("setup: the rows were not shown", text)
    summary, missed = _digest_of_the_turn(console)
    assert "nothing was found" not in summary, summary
    assert missed == [], missed


def test_s5_2_near_miss_a_ranking_with_no_rows_still_says_nothing_was_found(console, monkeypatch) -> None:
    from tests.chatbot import test_report_ask_lane as lane

    real = lane._fake_body
    monkeypatch.setattr(lane, "_fake_body", lambda args: {**real(args), "rows": [], "total_count": 0, "total": {"qty": 0, "amount": 0.0}})
    _run_ranking(console)
    summary, missed = _digest_of_the_turn(console)
    assert "nothing was found" in summary, (summary, missed)
