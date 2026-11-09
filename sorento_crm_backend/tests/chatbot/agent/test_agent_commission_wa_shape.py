"""AGENT-COMMISSION-WA shape (crew live x3 on 0c5c7b78 and bb85f8b5, 8 Nov): every figure right, the SHAPE unstable
run to run. Owner rule (4 Oct, 28 Oct): understanding is semantic only, never a regex or word list on the message.
So the model says what it is asking in structured `crm_query` arguments, `next_tier` (distance | closest |
furthest) and `subjects` (agent | dealer | team | all), and code decides the shape from those arguments and the data:

1. closest / furthest with no commission ladder among the subjects: ONE code line, never another kind's ranking.
2. A distance answer always carries the next-tier columns and ranks by what is still to sell.
3. No lead sentence about the total payout; no targets table appended.
4. Never an achieved figure for a target of 0; one period basis per answer (the periods containing today).

The turn is played as the loop plays it: `run_query`, `query_result`, the ledger, `shape_reply`. No LLM.
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


def _turn(db, calls: list[dict], model_text: str = "x", *, user_text: str = "", admitted=None) -> str:
    """The reply of one turn whose model made `calls` (crm_query args) and then wrote `model_text`."""
    from app.services.chatbot.agent.query_tools import query_result, shape_reply

    ledger = {}
    for i, args in enumerate(calls):
        out = query_result(run(db, args), panel=True)
        ledger[f"q{i}"] = {"name": "crm_query", "status": out.status, "args": args, "data": out.data,
                           "display": out.display}
    return shape_reply(model_text, ledger, user_text, admitted=admitted)


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
def test_N1_a_distance_answer_always_shows_the_next_tier_columns_whatever_else_the_model_sent(targets, asked):
    db, _c, _t = targets
    reply = _turn(db, [{"entity": ENTITY, "agent": "Agent A", "period": OCT, "next_tier": "distance", **asked}])
    for column in ("To the next tier", "Next tier", "Payout at the next tier (RM)"):
        assert column in reply, (asked, reply)
    assert "| 1,000 |" in reply and "| 300 |" in reply
    assert "RM 1,000.00 to go, would pay RM 300.00" in reply


def test_N2_one_subject_is_still_a_code_rendered_table_never_left_to_the_model(targets):
    """W4 run 2 (turn c411df3e): one row, so no card; the model wrote "were not retrieved"."""
    db, _c, _t = targets
    reply = _turn(db, [{"entity": ENTITY, "agent": "Agent A", "period": OCT, "next_tier": "distance"}],
                  "The next-tier figures were not retrieved.")
    assert "were not retrieved" not in reply and "To the next tier" in reply


# ------------------------------------------------------------------ 3. no total-payout lead line


def test_N3_no_lead_sentence_about_the_total_payout(targets):
    db, _c, _t = targets
    reply = _turn(db, [{"entity": ENTITY, "period": OCT, "next_tier": "closest", "subjects": "all"}],
                  "Total commission payout is RM 832,442.75.")
    assert "832,442.75" not in reply and "Total commission payout" not in reply
    assert reply.startswith("Distance to the next tier")


def test_N4_closest_agents_are_agents_only_closest_first(targets):
    db, _c, t = targets
    reply = _turn(db, [{"entity": ENTITY, "period": OCT, "next_tier": "closest", "subjects": "agent",
                        "sort": [{"field": "payout", "dir": "desc"}]}])
    assert "ZZT DEALER W2" not in reply
    assert _a(t) in reply and f"{t['b'].sales_agent} - Agent B" in reply


def test_N4b_closest_dealers_rank_by_distance_and_keep_the_closest_row(targets):
    """X2 run 1 on bb85f8b5: rows in target order, the closest dealer missing."""
    db, client, t = targets
    company_id = _dealer_company(db, t)
    pid = _product_id(db, company_id)
    near = _customer(db, company_id, "ZZT NEAR DEALER", level=1)
    _sale(db, company_id, near, "59000", date(2026, 10, 2), product_id=pid)
    assert client.post(BASE, json=_dealer_body([near], tiers=[
        {"period_start": "2026-10-01", "threshold": 60000, "rate": 5}])).status_code == 201
    reply = _turn(db, [{"entity": ENTITY, "next_tier": "closest", "subjects": "dealer", "limit": 1}])
    assert "ZZT NEAR DEALER" in reply and "ZZT DEALER W2" not in reply and "Payout at the next tier (RM)" in reply


# ------------------------------------------------------------------ 1. no ladder: one code line


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
    # An empty first call (a window with no period running), then the real one.
    [{"entity": ENTITY, "next_tier": "closest", "subjects": "agent", "period": ["01/01/2025", "31/01/2025"]},
     {"entity": ENTITY, "next_tier": "closest", "subjects": "agent"}],
])
def test_N5_no_agent_commission_ladder_is_one_code_line(no_agent_ladder, calls):
    reply = _turn(no_agent_ladder, calls, "Total payout is RM 832,442.75. ZZT LADDER DEALER is closest.")
    assert reply == NO_LADDER


def test_N6_a_dealer_is_still_answered_when_agents_have_no_ladder(no_agent_ladder):
    reply = _turn(no_agent_ladder, [{"entity": ENTITY, "agent": "ZZT LADDER DEALER", "next_tier": "distance"}])
    assert "RM 50,000.00 to go, would pay RM 3,000.00" in reply and NO_LADDER not in reply


# ------------------------------------------------------------------ 4. target of 0, other tables, one period


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


def test_N8_no_targets_table_is_appended_to_a_distance_answer(targets):
    """W1 / W2: the model also queried target_list and its table was appended."""
    db, _c, _t = targets
    reply = _turn(db, [{"entity": "target_list", "period": OCT},
                       {"entity": ENTITY, "agent": "Agent A", "next_tier": "distance"}])
    assert "To the next tier" in reply and "Sales targets" not in reply


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
    """Owner rule: the message text never decides the shape."""
    from app.services.chatbot.agent import query_tools

    db, _c, _t = targets
    calls = [{"entity": ENTITY, "next_tier": "closest", "subjects": "agent", "period": OCT}]
    replies = {
        _turn(db, calls, "Total payout RM 1.", user_text=said)
        for said in ("which agents are closest to their next tier", "ejen mana paling dekat tier seterusnya",
                     "zzz", "")
    }
    assert len(replies) == 1
    for gone in ("next_tier_question", "next_tier_args", "_NEXT_TIER_SAID", "_AGENTS_SAID"):
        assert not hasattr(query_tools, gone), gone


def test_N13_a_payout_answer_without_next_tier_keeps_its_lead_line_and_its_table(targets):
    db, _c, _t = targets
    reply = _turn(db, [{"entity": ENTITY, "period": OCT}], "Total payout is RM 360.00.",
                  user_text="how far is everyone from the next tier")
    assert reply.startswith("Total payout is RM 360.00.") and "To the next tier" not in reply


def test_N14_the_tool_says_how_to_ask_for_the_next_tier():
    from app.services.chatbot.agent.query_tools import QUERY_SCHEMA

    props = QUERY_SCHEMA["function"]["parameters"]["properties"]
    assert props["next_tier"]["enum"] == ["distance", "closest", "furthest"]
    assert props["subjects"]["enum"] == ["agent", "dealer", "team", "all"]
    said = props["next_tier"]["description"].lower()
    assert "earn" in said and "pay" in said and "any language" in said


# ------------------------------------------------------------------ review round on f18af7f3 (B1-B4), kept


def test_R1_view_own_asking_about_dealers_is_told_not_visible_never_no_ladder(targets, grant, monkeypatch):
    from app.services import own_scope

    db, _c, t = targets
    grant("sales.targets.view_own")
    monkeypatch.setattr(own_scope, "me", lambda db, user_id: own_scope.Me(str(user_id), None, (t["a"].id,)))
    reply = _turn(db, [{"entity": ENTITY, "next_tier": "closest", "subjects": "dealer"}], "None found.")
    assert NO_LADDER not in reply and "not visible to you" in reply


def test_R2_a_second_question_in_the_turn_and_what_was_not_done_are_kept(targets):
    db, _c, t = targets
    reply = _turn(db, [
        {"entity": ENTITY, "agent": "Agent B", "period": "2026-09", "fields": ["payout"]},
        {"entity": ENTITY, "agent": "Agent A", "next_tier": "distance"},
    ], "Agent B earned nothing in September.",
        admitted=["Not checked: Agent B's August payout.", "I did not get to: team North."])
    assert _a(t) in reply and f"{t['b'].sales_agent} - Agent B" in reply
    assert "Not checked: Agent B's August payout." in reply and "I did not get to: team North." in reply


def test_R3_two_named_subjects_are_two_tables(targets):
    db, _c, t = targets
    reply = _turn(db, [{"entity": ENTITY, "agent": "Agent A", "next_tier": "distance"},
                       {"entity": ENTITY, "agent": "Agent B", "next_tier": "distance"}])
    assert _a(t) in reply and f"{t['b'].sales_agent} - Agent B" in reply


def test_R4_closest_first_and_furthest_first(targets):
    db, _c, t = targets
    closest = _turn(db, [{"entity": ENTITY, "next_tier": "closest", "subjects": "all"}])
    assert closest.index(_a(t)) < closest.index("ZZT DEALER W2")
    furthest = _turn(db, [{"entity": ENTITY, "next_tier": "furthest", "subjects": "all", "limit": 1}])
    assert "ZZT DEALER W2" in furthest and _a(t) not in furthest


def test_R5_a_named_subject_not_found_is_answered_as_not_found(targets):
    db, _c, _t = targets
    reply = _turn(db, [{"entity": ENTITY, "agent": "Agent Zed", "next_tier": "distance"}], "Agent Zed was not found.")
    assert reply.startswith("Agent Zed was not found.") and NO_LADDER not in reply
    assert "Distance to the next tier" not in reply


# ------------------------------------------------------------------ review on 94969a2f / 728bc296


def test_R6_another_entitys_small_answer_keeps_the_models_text(targets):
    """"... and how many open orders does he have": a count, no table; the model's text answers it."""
    from app.services.chatbot.agent.query_tools import shape_reply

    db, _c, t = targets
    out = run(db, {"entity": ENTITY, "agent": "Agent A", "next_tier": "distance"})
    from app.services.chatbot.agent.query_tools import query_result

    card = query_result(out, panel=True)
    ledger = {
        "q1": {"name": "crm_query", "status": "ok", "args": {"entity": ENTITY, "agent": "Agent A", "next_tier": "distance"},
               "data": card.data, "display": card.display},
        "q2": {"name": "crm_query", "status": "ok", "args": {"entity": "order", "aggregates": [{"fn": "count"}]},
               "data": {"entity": "order", "groups": [{"count": 7}], "columns": [{"key": "count", "label": "Count"}]},
               "display": None},
    }
    reply = shape_reply("Agent A is RM 1,000 from tier 2. He has 7 open orders.", ledger, "")
    assert "To the next tier" in reply and "He has 7 open orders." in reply


def test_R7_one_subject_found_and_one_not_found_says_both(targets):
    db, _c, t = targets
    reply = _turn(db, [{"entity": ENTITY, "agent": "Agent A", "next_tier": "distance"},
                       {"entity": ENTITY, "agent": "Agent Zed", "next_tier": "distance"}],
                  "Agent A is RM 1,000.00 from tier 2. Agent Zed was not found.")
    assert _a(t) in reply and "To the next tier" in reply and "Agent Zed was not found." in reply


def test_R8_the_next_tier_lines_follow_the_tables_order(targets):
    """RK8: the note's lines in the order the rows are shown (closest first)."""
    db, _c, t = targets
    reply = _turn(db, [{"entity": ENTITY, "next_tier": "closest", "subjects": "all"}])
    note = reply[reply.index("Next tier: "):]
    assert note.index(_a(t)) < note.index("ZZT DEALER W2")
    far = _turn(db, [{"entity": ENTITY, "next_tier": "furthest", "subjects": "all"}])
    note = far[far.index("Next tier: "):]
    assert note.index("ZZT DEALER W2") < note.index(_a(t))


def test_R9_a_not_found_next_tier_call_alone_never_becomes_a_code_reply(targets):
    """RK10: only calls that found rows make the code reply; what was not done is still said."""
    db, _c, _t = targets
    # As `final_reply` hands it over: the admitted line is in the text too.
    reply = _turn(db, [{"entity": ENTITY, "agent": "Agent Zed", "next_tier": "distance"}],
                  "Agent Zed was not found.\n\nNot checked: team North.", admitted=["Not checked: team North."])
    assert reply.startswith("Agent Zed was not found.") and "Not checked: team North." in reply


# ------------------------------------------------------------------ review on 376cdda8


@pytest.mark.parametrize("ranking", [
    {"next_tier": "closest", "subjects": "dealer"},
    {"next_tier": "closest", "subjects": "all", "limit": 1},
    {"next_tier": "closest", "subjects": "all", "filters": [{"field": "owner_kind", "op": "eq", "value": "dealer"}]},
    {"next_tier": "closest", "subjects": "all", "filters": [{"field": "payout", "op": "gt", "value": 0}]},
])
def test_R10_a_ranking_that_cannot_include_a_missed_name_keeps_the_not_found(targets, ranking):
    db, _c, _t = targets
    reply = _turn(db, [{"entity": ENTITY, "agent": "Agent Zed", "next_tier": "distance"}, {"entity": ENTITY, **ranking}],
                  "Agent Zed was not found. The dealers are ranked below.")
    assert "Agent Zed was not found." in reply and "To the next tier" in reply


def test_R11_a_full_ranking_over_everyone_answers_for_a_missed_name(targets):
    db, _c, t = targets
    reply = _turn(db, [{"entity": ENTITY, "agent": "Agent Zed", "next_tier": "distance"},
                       {"entity": ENTITY, "next_tier": "closest", "subjects": "all"}], "Total payout RM 9.")
    assert "Total payout" not in reply and _a(t) in reply


def test_R12_subjects_with_distance_is_refused(targets):
    db, _c, _t = targets
    err = refused(db, {"entity": ENTITY, "agent": "ZZT DEALER W2", "next_tier": "distance", "subjects": "agent"})
    assert "subjects" in err.message and "closest or furthest" in err.message


def test_R13_a_targets_table_shown_by_code_is_dropped_from_a_next_tier_answer(targets):
    """S1 / K11: a real card (over 10 rows) of target_list, not only a short result."""
    from app.services.chatbot.agent.query_tools import query_result, shape_reply

    db, _c, _t = targets
    out = query_result(run(db, {"entity": ENTITY, "agent": "Agent A", "next_tier": "distance"}), panel=True)
    ledger = {
        "q1": {"name": "crm_query", "status": "ok", "args": {"entity": "target_list"},
               "data": {"entity": "target_list", "shown_to_user": True, "total": 40}, "display": "SALES TARGETS TABLE"},
        "q2": {"name": "crm_query", "status": "ok", "args": {"entity": ENTITY, "agent": "Agent A", "next_tier": "distance"},
               "data": out.data, "display": out.display},
    }
    reply = shape_reply("x", ledger, "")
    assert "SALES TARGETS TABLE" not in reply and "To the next tier" in reply


def test_R14_what_was_not_done_is_said_once_when_the_models_text_is_kept(targets):
    """K14: the admitted line is taken out of the kept text, so it is never said twice."""
    db, _c, _t = targets
    reply = _turn(db, [{"entity": ENTITY, "agent": "Agent A", "next_tier": "distance"},
                       {"entity": ENTITY, "agent": "Agent Zed", "next_tier": "distance"}],
                  "Agent Zed was not found. Not checked: team North.", admitted=["Not checked: team North."])
    assert reply.count("Not checked: team North.") == 1 and "Agent Zed was not found." in reply


def test_R15_a_ranking_cut_by_the_row_cap_never_hides_a_missed_name(targets):
    """KR15: truncated means not every row was shown."""
    from app.services.chatbot.agent.query_tools import query_result, shape_reply

    db, _c, _t = targets
    out = query_result(run(db, {"entity": ENTITY, "next_tier": "closest", "subjects": "all"}), panel=True)
    data = {**out.data, "truncated": True}
    ledger = {
        "q1": {"name": "crm_query", "status": "ok", "args": {"entity": ENTITY, "agent": "Agent Zed", "next_tier": "distance"},
               "data": {"entity": ENTITY, "rows": [], "total": 0}, "display": None},
        "q2": {"name": "crm_query", "status": "ok", "args": {"entity": ENTITY, "next_tier": "closest", "subjects": "all"},
               "data": data, "display": out.display},
    }
    assert "Agent Zed was not found." in shape_reply("Agent Zed was not found.", ledger, "")
