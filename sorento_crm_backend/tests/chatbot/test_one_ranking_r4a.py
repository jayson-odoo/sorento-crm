"""REPORT-SMART-L one ranking, round R4a (AC-OR4): the old top-selling lane is gone from the chatbot.

A conversation stored before the deploy (focus.top_selling, focus.status "top_selling") loads clean
and the next ranking runs on `crm_report_ask`; the chatbot no longer carries the old lane's helpers.
The route, the MCP tool and the analytics connector stay. `top_selling_pick` (turn/pending.py) and
`_answer_top_selling_pick` (turn/apply.py) are KEPT (R3c's row pick), so nothing here asserts on them.
Fake names only.
"""
from __future__ import annotations

import importlib
from decimal import Decimal
from typing import Any

import pytest

from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import TOOL, _names, _say_all, console  # noqa: F401
from tests.chatbot.test_report_smart_step7 import KEEP, _state_on

OLD_TOOL = "crm_top_selling_report"
YEAR_2026 = {"date_filter_start": "2026-01-01", "date_filter_end": "2026-12-31"}

#: A stored focus from before the deploy: the old ~20-key top selling slot and its status.
OLD_SLOT = {
    "rank_by": "amount", "basis": "delivered", "rank_group": "item", "rank_direction": "top", "top_n": 30,
    "asked": {"kind": "metric"}, "category_words": ["ZZ cat"], "detail_code": "ZZT-ITEM-1", "who": {"raw": "zz"},
    "customer_ids": ["cust-1"], "dealer_refused": False, "unclear": False,
}


def _item_ask() -> dict[str, Any]:
    return _parser_output(
        domain_hint="order", intent_hint="check_order", order_status="top_selling", group_by="product", rank_group="item",
        rank_direction="top", top_n=10, measure="qty", basis="delivered", rank_by="quantity", entities=[],
        domain_in_message=True, state_changes=list(KEEP), **YEAR_2026)


# ---------------------------------------------------------------- 1. a pre-deploy state loads clean


def test_r4a_1_a_pre_deploy_focus_loads_without_a_top_selling_slot_or_status() -> None:
    from app.services.chatbot.turn.state import focus_from_wire

    focus = focus_from_wire({"domains": ["order"], "status": "top_selling", "top_selling": dict(OLD_SLOT)})
    assert getattr(focus, "top_selling", None) is None, focus.top_selling
    assert focus.status is None, focus.status


def test_r4a_1_a_pre_deploy_session_runs_the_next_ranking_on_the_report_engine(console, monkeypatch) -> None:
    _state_on(console)
    console.session_vars = {"focus": {"domains": ["order"], "status": "top_selling", "top_selling": dict(OLD_SLOT)}}
    text, log = _say_all(console, monkeypatch, _item_ask(), "top 10 selling items this year by qty delivered")
    assert OLD_TOOL not in _names(log), _names(log)
    assert len([1 for n, _a in log if n == TOOL]) == 1, (text, log)
    focus = console.session_vars.get("focus") or {}
    assert not focus.get("top_selling") and focus.get("status") != "top_selling", focus


# ---------------------------------------------------------------- 2. the old lane's helpers are gone

GONE = [
    ("app.services.chatbot.lanes.business", "top_selling_ceiling_note"),
    ("app.services.chatbot.lanes.business", "_top_selling_question"),
    ("app.services.chatbot.lanes.business.fetch", "_top_selling_output"),
    ("app.services.chatbot.engine", "_top_selling_dealer_scope"),
    ("app.services.chatbot.engine", "_top_selling_narrowing"),
    ("app.services.chatbot.engine", "_top_selling_who_answer"),
    ("app.services.chatbot.engine", "_top_selling_question_answer"),
    ("app.services.chatbot.turn.apply", "_top_selling_waiting"),
    ("app.services.chatbot.turn.apply", "_top_selling_rules"),
]


@pytest.mark.parametrize("module, name", GONE)
def test_r4a_2_the_chatbot_no_longer_carries_the_old_top_selling_helper(module, name) -> None:
    assert not hasattr(importlib.import_module(module), name), f"{module}.{name} is still there"


# ---------------------------------------------------------------- 3. guards


def test_r4a_3_guard_the_top_selling_route_still_answers(client, db) -> None:
    from tests.test_top_selling_report import _get, _line, _product

    p = _product(db, "ZZTR4A-A")
    _line(db, product_id=p.id, ordered=4, delivered=4, line_total=Decimal("40.00"))
    db.commit()
    resp = _get(client, rank_by="quantity")
    assert resp.status_code == 200 and resp.json()["rows"], resp.text


def test_r4a_3_the_mcp_tool_is_gone_from_the_catalogue() -> None:
    # REPORT-UNIFY (owner ruling Q1): `crm_top_selling_report` is removed from the MCP catalogue.
    import sys
    from pathlib import Path

    root = str(Path(__file__).resolve().parents[3] / "sorento_crm_mcp")
    if root not in sys.path:
        sys.path.append(root)
    from sorento_crm_mcp.catalog import CATALOG

    assert not any(spec.name == OLD_TOOL for spec in CATALOG)


def test_r4a_3_guard_a_top_10_selling_items_chat_ask_runs_the_report_engine(console, monkeypatch) -> None:
    _state_on(console)
    text, log = _say_all(console, monkeypatch, _item_ask(), "top 10 selling items this year by qty delivered")
    assert OLD_TOOL not in _names(log) and len([1 for n, _a in log if n == TOOL]) == 1, (text, log)


def test_r4a_3_guard_a_row_pick_on_an_item_ranking_still_opens_its_detail(console, monkeypatch) -> None:
    from tests.chatbot.test_one_ranking_r3c import _body, _on_screen, _pick, _ran
    from tests.chatbot import test_report_ask_lane as lane_tests

    monkeypatch.setattr(lane_tests, "_fake_body", _body)
    _on_screen(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _pick(2), "2")
    assert sorted(a.get("group_by") for a in _ran(log)) == ["customer", "month"], (text, log)


from tests.test_top_selling_report import client, db  # noqa: E402,F401 - fixtures of the route tests
