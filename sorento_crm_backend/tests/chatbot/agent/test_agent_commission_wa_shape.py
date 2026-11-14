"""AGENT-COMMISSION-WA shape (crew live x3 on 0c5c7b78 and bb85f8b5, 8 Nov): every figure right, the SHAPE unstable
run to run. Owner rule (4 Oct, 28 Oct): understanding is semantic only, never a regex or word list on the message.
So the model says what it is asking in structured `crm_query` arguments, `next_tier` (distance | closest |
furthest) and `subjects` (agent | dealer | team | all), and code decides from those what the TOOL returns:

1. closest / furthest with no commission ladder among the subjects: the note says so, never another kind's ranking.
2. A distance answer always carries the next-tier columns and each row's next-tier lines, ranked by what is still
   to sell.
3. Never an achieved figure for a target of 0; one period basis per answer (the periods containing today).

The reply itself is the model's (owner 14 Nov, `test_agent_commission_wa_model_reply.py`): these tests read what the
tool hands the model, played as the loop plays it (`run_query`, `query_result`). No LLM.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from tests.chatbot.agent.test_ai_tools_wave2 import grant, refused, run, targets  # noqa: F401  (fixtures)
from tests.test_dealer_targets_api import _customer, _dealer_body, _product_id, _sale
from tests.test_sales_targets_s1 import BASE, _agent, _so_line, api, world  # noqa: F401  (fixtures)

ENTITY = "agent_target_summary"
OCT = "2026-10"
NO_LADDER = "No agent target has a commission ladder this period."


def _data(db, args: dict) -> dict:
    """What the model is given for one crm_query call."""
    from app.services.chatbot.agent.query_tools import query_result

    return query_result(run(db, args), panel=True).data


def _labels(data: dict) -> list[str]:
    return [r["label"] for r in data["rows"]]


def _lines(data: dict) -> str:
    return " ".join(r.get("next_tier_lines") or "" for r in data["rows"])


def _a(t):
    return f"{t['a'].sales_agent} - Agent A"


def _dealer_company(db, t):
    from app.models.sales import SalesTarget

    return db.get(SalesTarget, t["dealer"]["id"]).company_id


# ------------------------------------------------------------------ 2. the next-tier columns, always


@pytest.mark.parametrize("asked", [
    {"fields": ["payout"]},
    {"fields": ["owner_kind", "achieved_pct", "payout"]},
    {},
    {"group_by": ["owner"], "aggregates": [{"fn": "sum", "field": "payout"}]},
    {"aggregates": [{"fn": "sum", "field": "payout"}]},
    {"sort": [{"field": "payout", "dir": "desc"}]},
])
def test_N1_a_distance_answer_always_carries_the_next_tier_columns_whatever_else_the_model_sent(targets, asked):
    db, _c, _t = targets
    data = _data(db, {"entity": ENTITY, "agent": "Agent A", "period": OCT, "next_tier": "distance", **asked})
    [row] = data["rows"]
    assert (row["to_next_tier"], row["next_tier"], row["next_tier_payout"]) == (1000.0, 2, 300.0), (asked, row)
    assert "RM 1,000.00 to go, would pay RM 300.00" in row["next_tier_lines"]


def test_N4_closest_agents_are_agents_only_closest_first(targets):
    db, _c, t = targets
    data = _data(db, {"entity": ENTITY, "period": OCT, "next_tier": "closest", "subjects": "agent",
                      "sort": [{"field": "payout", "dir": "desc"}]})
    assert "ZZT DEALER W2" not in " ".join(_labels(data))
    assert any(_a(t) in x for x in _labels(data)) and any(f"{t['b'].sales_agent} - Agent B" in x for x in _labels(data))


def test_N4b_closest_dealers_rank_by_distance_and_keep_the_closest_row(targets):
    """X2 run 1 on bb85f8b5: rows in target order, the closest dealer missing."""
    db, client, t = targets
    company_id = _dealer_company(db, t)
    pid = _product_id(db, company_id)
    near = _customer(db, company_id, "ZZT NEAR DEALER", level=1)
    _sale(db, company_id, near, "59000", date(2026, 10, 2), product_id=pid)
    assert client.post(BASE, json=_dealer_body([near], tiers=[
        {"period_start": "2026-10-01", "threshold": 60000, "rate": 5}])).status_code == 201
    data = _data(db, {"entity": ENTITY, "next_tier": "closest", "subjects": "dealer", "limit": 1})
    [label] = _labels(data)
    assert "ZZT NEAR DEALER" in label and data["rows"][0]["next_tier_payout"] is not None


# ------------------------------------------------------------------ 1. no ladder: one note


@pytest.fixture
def no_agent_ladder(api, grant):
    """Agent C with a plain October target (no commission); a dealer with a commission tier this quarter."""
    client, db, company_id = api
    grant("sales.targets.view")
    pid = _product_id(db, company_id)
    c = _agent(db, "C", "Agent C")
    assert client.post(BASE, json={
        "subject_kind": "agent", "sales_agent_id": c.id, "name": "ZZT plain", "metric": "amount", "basis": "ordered",
        "product_scope": "all", "start_date": "2026-10-01", "end_date": "2026-10-31", "target_value": 5000,
    }).status_code == 201
    _so_line(db, company_id, agent_id=c.id, order_date=date(2026, 10, 5), line_total=Decimal("1000"), product_id=pid)
    dealer = _customer(db, company_id, "ZZT LADDER DEALER", level=1)
    _sale(db, company_id, dealer, "10000", date(2026, 10, 2), product_id=pid)
    assert client.post(BASE, json=_dealer_body([dealer], tiers=[
        {"period_start": "2026-10-01", "threshold": 60000, "rate": 5}])).status_code == 201
    return db


@pytest.mark.parametrize("calls", [
    [{"entity": ENTITY, "next_tier": "closest", "subjects": "agent"}],
    [{"entity": ENTITY, "next_tier": "closest", "subjects": "agent", "fields": ["payout"]}],
    [{"entity": ENTITY, "next_tier": "closest", "subjects": "agent", "group_by": ["owner"],
      "aggregates": [{"fn": "sum", "field": "payout"}]}],
    [{"entity": ENTITY, "next_tier": "closest", "subjects": "agent",
      "filters": [{"field": "owner_kind", "op": "eq", "value": "agent"}]}],
])
def test_N5_no_agent_commission_ladder_is_said_by_the_note(no_agent_ladder, calls):
    data = _data(no_agent_ladder, calls[-1])
    assert NO_LADDER in (data.get("scope_note") or ""), data
    assert "ZZT LADDER DEALER" not in " ".join(_labels(data)) and not _lines(data).strip()


def test_N6_a_dealer_is_still_answered_when_agents_have_no_ladder(no_agent_ladder):
    data = _data(no_agent_ladder, {"entity": ENTITY, "agent": "ZZT LADDER DEALER", "next_tier": "distance"})
    assert "RM 50,000.00 to go, would pay RM 3,000.00" in _lines(data)
    assert NO_LADDER not in (data.get("scope_note") or "")


# ------------------------------------------------------------------ 3. target of 0, one period


def test_N7_a_target_of_0_never_shows_an_achieved_figure_on_the_targets_list(targets):
    db, client, t = targets
    zero = client.post(BASE, json={
        "subject_kind": "agent", "sales_agent_id": t["a"].id, "name": "ZZT zero", "metric": "amount",
        "basis": "ordered", "product_scope": "all", "start_date": "2026-10-01", "end_date": "2026-10-31",
        "target_value": 0,
    }).json()
    out = run(db, {"entity": "target_list", "period": OCT, "fields": ["target_value", "achieved_value", "achieved_pct"]})
    [row] = [r for r in out["rows"] if zero["target_no"] in r["label"]]
    assert row["achieved_value"] == "no target set" and row["achieved_pct"] == "no target set"
    assert row["target_value"] == "no target set"


def test_N9_a_distance_answer_is_about_the_periods_containing_today_whatever_window_was_asked(targets):
    """X1 / W9 on bb85f8b5: a year table summed other quarters while the note spoke of the current one."""
    db, _c, _t = targets
    for period in ("this_year", "2026", None, ["01/07/2026", "31/12/2026"]):
        args = {"entity": ENTITY, "agent": "Agent A", "next_tier": "distance"}
        if period:
            args["period"] = period
        out = run(db, args)
        [row] = out["rows"]
        # October alone: 9,000 at 2% = 180 (the year would add September's 360).
        assert row["payout"] == 180.0 and row["to_next_tier"] == 1000.0, period
        assert "Periods containing today" in out["scope_note"] and "No period named" not in out["scope_note"]


# ------------------------------------------------------------------ the structured arguments


def test_N10_closest_or_furthest_without_subjects_asks_rather_than_guesses(targets):
    db, _c, _t = targets
    for kind in ("closest", "furthest"):
        err = refused(db, {"entity": ENTITY, "next_tier": kind})
        assert "subjects" in err.message and "ask" in err.message.lower()


def test_N11_bad_or_misplaced_arguments_are_refused(targets):
    db, _c, _t = targets
    assert "next_tier" in refused(db, {"entity": ENTITY, "next_tier": "soonest"}).message
    assert "subjects" in refused(db, {"entity": ENTITY, "next_tier": "closest", "subjects": "people"}).message
    assert "next_tier" in refused(db, {"entity": "target_list", "next_tier": "distance"}).message


def test_N12_same_arguments_any_wording_same_reply_and_no_text_matching_in_the_code(targets):
    """Owner rule: the message text never decides anything; the reply is the model's text whatever was said."""
    from app.services.chatbot.agent import query_tools
    from app.services.chatbot.agent.query_tools import query_result, shape_reply

    db, _c, _t = targets
    args = {"entity": ENTITY, "next_tier": "closest", "subjects": "agent", "period": OCT}
    out = query_result(run(db, args), panel=True)
    ledger = {"q0": {"name": "crm_query", "status": "ok", "args": args, "data": out.data, "display": out.display}}
    for said in ("which agents are closest to their next tier", "ejen mana paling dekat tier seterusnya", "zzz", ""):
        assert shape_reply("Agent A is closest.", ledger, said) == "Agent A is closest."
    for gone in ("next_tier_question", "next_tier_args", "_NEXT_TIER_SAID", "_AGENTS_SAID", "_distance_reply"):
        assert not hasattr(query_tools, gone), gone


def test_N14_the_tool_says_how_to_ask_for_the_next_tier():
    from app.services.chatbot.agent.query_tools import QUERY_SCHEMA

    props = QUERY_SCHEMA["function"]["parameters"]["properties"]
    assert props["next_tier"]["enum"] == ["distance", "closest", "furthest"]
    assert props["subjects"]["enum"] == ["agent", "dealer", "team", "all"]
    said = props["next_tier"]["description"].lower()
    assert "earn" in said and "pay" in said and "any language" in said


# ------------------------------------------------------------------ review rounds, kept as data checks


def test_R1_view_own_asking_about_dealers_is_told_not_visible_never_no_ladder(targets, grant, monkeypatch):
    from app.services import own_scope

    db, _c, t = targets
    grant("sales.targets.view_own")
    monkeypatch.setattr(own_scope, "me", lambda db, user_id: own_scope.Me(str(user_id), None, (t["a"].id,)))
    note = _data(db, {"entity": ENTITY, "next_tier": "closest", "subjects": "dealer"}).get("scope_note") or ""
    assert NO_LADDER not in note and "not visible to you" in note


def test_R4_closest_first_and_furthest_first(targets):
    db, _c, t = targets
    closest = " ".join(_labels(_data(db, {"entity": ENTITY, "next_tier": "closest", "subjects": "all"})))
    assert closest.index(_a(t)) < closest.index("ZZT DEALER W2")
    furthest = _labels(_data(db, {"entity": ENTITY, "next_tier": "furthest", "subjects": "all", "limit": 1}))
    assert len(furthest) == 1 and "ZZT DEALER W2" in furthest[0]


def test_R8_the_next_tier_lines_follow_the_rows_order(targets):
    """RK8: each row's lines in the order the rows are given (closest first)."""
    db, _c, t = targets
    near = _lines(_data(db, {"entity": ENTITY, "next_tier": "closest", "subjects": "all"}))
    assert near.index(_a(t)) < near.index("ZZT DEALER W2")
    far = _lines(_data(db, {"entity": ENTITY, "next_tier": "furthest", "subjects": "all"}))
    assert far.index("ZZT DEALER W2") < far.index(_a(t))


def test_R12_subjects_with_distance_is_refused(targets):
    db, _c, _t = targets
    err = refused(db, {"entity": ENTITY, "agent": "ZZT DEALER W2", "next_tier": "distance", "subjects": "agent"})
    assert "subjects" in err.message and "closest or furthest" in err.message
