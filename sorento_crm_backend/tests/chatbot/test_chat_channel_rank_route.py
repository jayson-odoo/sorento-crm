"""CHAT-CHANNEL-RANK-ROUTE (owner OK 25 Oct ~15:20; PLAN-chat-channel-rank-route-1025.md): "Project sales top 10 srt102-rg"
over a held ranking, parsed by prod v63 as a SALES ANALYSIS with a count and one channel (no axis), re-runs the held ranking
filtered to that channel with the message's own product and count (AC-CF2 ruling), never the analysis total. EXPLORE-1023C row 6
t3. Real engine seam, the v63 shapes; the route body is the one REPORT-CHANNEL-FILTER stubs. Fake codes."""
from __future__ import annotations

from typing import Any

import pytest

from tests.chatbot import test_report_ask_lane as lane_tests
from tests.chatbot.test_engine import stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import PRODUCT_CODE, TOOL, _e, _say_all, console  # noqa: F401
from tests.chatbot.test_report_channel_filter import OTHER_CODE, _agent_ranking, _body, _dealer_only, _ran, _v63

#: Today's answer to that parse (a sales analysis naming one product is that product's sales report,
#: `business.__init__` "sales_analysis_answered_as_sales_report"): the total prod v63 replied "No sales found" with.
TODAY = "crm_sales_report"


@pytest.fixture(autouse=True)
def _route_body(monkeypatch):
    monkeypatch.setattr(lane_tests, "_fake_body", _body)


@pytest.fixture
def other_product(console):  # noqa: F811
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from tests._mc_lookup_seed import product

    db = console.session_factory()
    try:
        product(db, company_id=DEFAULT_COMPANY_ID, code=OTHER_CODE)
        db.commit()
    finally:
        db.close()


def _project_top_10(**over: Any) -> dict[str, Any]:
    """Row 6 t3's live v63 parse of "Project sales top 10 <code>": a sales analysis, a count, one channel, no axis."""
    base: dict[str, Any] = dict(
        order_status="sales_analysis", sales_channel="project", top_n=10, entities=[_e(OTHER_CODE, "product")],
        entity_op="replace_combine", domain_in_message=True,
    )
    return _v63(**{**base, **over})


def _today(log) -> list[dict[str, Any]]:
    return [a for n, a in log if n == TODAY]


def test_cr1_project_sales_top_10_code_after_a_ranking_reruns_it_filtered(console, monkeypatch, other_product) -> None:
    _agent_ranking(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _dealer_only(), "Dealer sales only")
    assert "Channel: Dealer" in text, ("setup", text)
    text, log = _say_all(console, monkeypatch, _project_top_10(), f"Project sales top 10 {OTHER_CODE.lower()}")
    ran = _ran(log)
    assert len(ran) == 1 and _today(log) == [], (text, log)
    args = ran[0]
    assert args["group_by"] == "sales_agent" and args["top_n"] == 10 and args["channel"] == "project", args
    assert args["product_code"] == OTHER_CODE and args["date_from"] == "2026-01-01" and args["date_to"] == "2026-12-31", args
    assert args["measure"] == "qty" and args["basis"] == "delivered", args
    assert "Top 10 of 12 sales agents" in text and "Channel: Project team" in text, text
    assert "No sales found" not in text and "Across all" not in text, text


def test_cr1b_straight_after_the_ranking_too(console, monkeypatch, other_product) -> None:
    _agent_ranking(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _project_top_10(), f"Project sales top 10 {OTHER_CODE.lower()}")
    ran = _ran(log)
    assert len(ran) == 1 and _today(log) == [], (text, log)
    assert ran[0]["group_by"] == "sales_agent" and ran[0]["top_n"] == 10 and ran[0]["channel"] == "project", ran
    assert ran[0]["product_code"] == OTHER_CODE, ran


# ------------------------------------------------ guards: today's behaviour


def test_cr2_guard_nothing_held_stays_today_s_sales_report(console, monkeypatch, other_product) -> None:
    text, log = _say_all(console, monkeypatch, _project_top_10(), f"Project sales top 10 {OTHER_CODE.lower()}")
    assert _ran(log) == [] and len(_today(log)) == 1, (text, log)
    assert _today(log)[0].get("channel") == "project", log


def test_cr3_guard_no_count_stays_today_s_sales_report(console, monkeypatch, other_product) -> None:
    _agent_ranking(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _project_top_10(top_n=None), f"Project sales {OTHER_CODE.lower()}")
    assert _ran(log) == [] and len(_today(log)) == 1, (text, log)


def test_cr4_guard_a_count_with_an_axis_stays_today_s_sales_report(console, monkeypatch, other_product) -> None:
    _agent_ranking(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _project_top_10(group_by="month"), "Project sales by month top 10")
    assert _ran(log) == [] and len(_today(log)) == 1, (text, log)


def test_cr5_guard_a_plain_refine_of_the_ranking_is_unchanged(console, monkeypatch) -> None:
    _agent_ranking(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _v63(top_n=3, ranking_refine=True), "top 3")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == "sales_agent" and ran[0]["top_n"] == 3 and "channel" not in ran[0], (text, log)
    assert ran[0]["product_code"] == PRODUCT_CODE and "Top 3 of 12 sales agents" in text, text
