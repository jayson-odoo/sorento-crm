"""RANK-REFINE-ROUTE layer-2 contract (PLAN-rank-refine-route-1025.md): the R5 ranking follow-ups CHAT-SLIM-INDEX phase 1
lost under a prompt edit (gpt-5.4-mini, arm B vs v63 arm A) still give the user the SAME answer through the real engine seam,
so the parser-gold flip is not a user-visible change. Each B shape is the parse the B run emitted, with exactly the fields its
gold reasons pin (`parser_gold.grade_parse` lists every mismatch); the held ranking is the gold row's context. Fake codes.

Not here (DIFFERENT, no parser field to route on, prompt lane): or5-c-03 "dealer only" where B drops `sales_channel`."""
from __future__ import annotations

from typing import Any

import pytest

from tests.chatbot import test_report_ask_lane as lane_tests
from tests.chatbot.test_engine import stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import PRODUCT_CODE, _say_all, console  # noqa: F401
from tests.chatbot.test_report_channel_filter import _agent_ranking, _body, _ran, _v63

YEAR_2026 = {"date_filter_start": "2026-01-01", "date_filter_end": "2026-12-31"}
#: Every R5 follow-up below names no entity and reuses the held subject (stored on the A and B runs alike).
FOLLOW_UP = {"entities": [], "entity_op": "reuse"}


@pytest.fixture(autouse=True)
def _route_body(monkeypatch):
    monkeypatch.setattr(lane_tests, "_fake_body", _body)


def _product_ranking(console, monkeypatch) -> None:  # noqa: F811
    """or5-5-03's context: "Top 5 products by delivered qty this year" on screen."""
    v = _v63(group_by="product", top_n=5, ranking_refine=False, measure="qty", rank_by="quantity", basis="delivered",
             entity_op="replace_combine", domain_in_message=True, **YEAR_2026)
    text, log = _say_all(console, monkeypatch, v, "Top 5 products by delivered qty this year")
    assert len(_ran(log)) == 1 and _ran(log)[0]["group_by"] == "product", ("setup", text, log)


def _answer(console, monkeypatch, held, shape: dict[str, Any], message: str) -> tuple[list[dict[str, Any]], str]:  # noqa: F811
    held(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _v63(**FOLLOW_UP, **shape), message)
    return _ran(log), text


#: or5-c-02 "only project" / or5-c-04 "channel project sahaja" after "Top 5 sales agents by delivered qty".
#: A passed: sales_ranking, sales_channel project, ranking_refine true. B failed ONLY on `order_status` top_selling.
CHANNEL_ROWS = {
    "or5-c-02 A": ({"sales_channel": "project", "ranking_refine": True}, "only project"),
    "or5-c-02 B": ({"order_status": "top_selling", "sales_channel": "project", "ranking_refine": True}, "only project"),
    "or5-c-04 A": ({"sales_channel": "project", "ranking_refine": True}, "channel project sahaja"),
    "or5-c-04 B": ({"order_status": "top_selling", "sales_channel": "project", "ranking_refine": True}, "channel project sahaja"),
}


@pytest.mark.parametrize("row", list(CHANNEL_ROWS))
def test_r5_channel_follow_up_filters_the_held_agent_ranking_for_a_and_b(console, monkeypatch, row) -> None:  # noqa: F811
    shape, message = CHANNEL_ROWS[row]
    ran, text = _answer(console, monkeypatch, _agent_ranking, shape, message)
    assert len(ran) == 1, (row, text, ran)
    args = ran[0]
    assert args["group_by"] == "sales_agent" and args["top_n"] == 5 and args["channel"] == "project", (row, args)
    assert args["product_code"] == PRODUCT_CODE and args["date_from"] == "2026-01-01", (row, args)
    assert "Top 5 of 12 sales agents" in text and "Channel: Project team" in text, (row, text)
    assert "Across all" not in text and "Which period?" not in text, (row, text)


#: or5-5-03 "yang 3 tu sahaja" after "Top 5 products by delivered qty": A passed (ranking_refine true); B failed only on
#: `ranking_refine` (false), one B run also read the position as an open-question pick. All carry `reference_positions` [3].
POSITION_ROWS = {
    "or5-5-03 A": {"ranking_refine": True, "reference_positions": [3]},
    "or5-5-03 B": {"ranking_refine": False, "reference_positions": [3]},
    "or5-5-03 B pick": {"ranking_refine": False, "reference_positions": [3],
                        "open_question_answer": {"mode": "pick", "picked": [3], "items": []}},
}


@pytest.mark.parametrize("row", list(POSITION_ROWS))
def test_r5_position_follow_up_opens_rank_3_for_a_and_b(console, monkeypatch, row) -> None:  # noqa: F811
    """The rank pick (position vs count is the parser's call, crew a35910508): rank 3's breakdown, whatever the flag."""
    ran, text = _answer(console, monkeypatch, _product_ranking, POSITION_ROWS[row], "yang 3 tu sahaja")
    assert [a["group_by"] for a in ran] == ["customer", "month"], (row, text, ran)
    assert all(a["product_ids"] == ["zzk-3"] for a in ran), (row, ran)
