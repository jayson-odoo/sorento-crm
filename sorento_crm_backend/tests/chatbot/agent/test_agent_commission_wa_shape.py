"""AGENT-COMMISSION-WA shape round (crew live x3 on 0c5c7b78, 8 Nov): every figure was right, the SHAPE of 4 of 11
answers was not. Decided in code, never by the prompt, as #2242 did:

1. "which agents are closest to their next tier" with no agent commission ladder: ONE code-chosen line, never a dealer
   ranking or the payout table (W6 run 1 ranked dealers as agents, run 2 led with the total payout, run 3 appended it).
2. A distance answer ALWAYS carries the next-tier columns, whatever columns the model asked for (X2 run 3, W4 run 2
   "were not retrieved").
3. No lead sentence about the total payout on a distance question.
4. Never an achieved figure for a target of 0 (X3 run 2 printed 9.92M), and no targets table appended to a distance
   answer (W1, W2).

The turn is played as the loop plays it: `next_tier_args` before dispatch, `run_query`, `query_result`, the ledger,
`shape_reply`. Entity output only, no LLM.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from tests.chatbot.agent.test_ai_tools_wave2 import grant, run, targets  # noqa: F401  (fixtures)
from tests.test_dealer_targets_api import _customer, _dealer_body, _product_id, _sale
from tests.test_sales_targets_s1 import BASE, _agent, _so_line, api, world  # noqa: F401  (fixtures)

ENTITY = "agent_target_summary"
OCT = "2026-10"
NO_LADDER = "No agent target has a commission ladder this period."


def _turn(db, user_text: str, calls: list[dict], model_text: str) -> str:
    """The reply of one turn whose model made `calls` (crm_query args) and then wrote `model_text`."""
    from app.services.chatbot.agent.query_tools import next_tier_args, query_result, shape_reply

    ledger = {}
    for i, args in enumerate(calls):
        args = next_tier_args(args, user_text)
        out = query_result(run(db, args), panel=True)
        ledger[f"q{i}"] = {"name": "crm_query", "status": out.status, "args": args, "data": out.data,
                           "display": out.display}
    return shape_reply(model_text, ledger, user_text)


# ------------------------------------------------------------------ 2. the next-tier columns, always


@pytest.mark.parametrize("asked", [
    {"fields": ["payout"]},
    {"fields": ["owner_kind", "achieved_pct", "payout"]},
    {},
    {"group_by": ["owner"], "aggregates": [{"fn": "sum", "field": "payout"}]},
    {"aggregates": [{"fn": "sum", "field": "payout"}]},
])
def test_N1_a_distance_answer_always_shows_the_next_tier_columns_whatever_the_model_asked(targets, asked):
    db, _c, _t = targets
    reply = _turn(db, "How far is Agent A from the next tier this month, and what would it pay?",
                  [{"entity": ENTITY, "agent": "Agent A", "period": OCT, **asked}], "Here it is.")
    for column in ("To the next tier", "Next tier", "Payout at the next tier (RM)"):
        assert column in reply, (asked, reply)
    assert "| 1,000 |" in reply and "| 300 |" in reply
    assert "RM 1,000.00 to go, would pay RM 300.00" in reply


def test_N2_one_subject_is_still_a_code_rendered_table_never_left_to_the_model(targets):
    """W4 run 2 (turn c411df3e): one row, so no card; the model wrote "were not retrieved"."""
    db, _c, _t = targets
    reply = _turn(db, "how much more does agent a need to sell to reach the next tier",
                  [{"entity": ENTITY, "agent": "Agent A", "period": OCT, "fields": ["payout"]}],
                  "The next-tier figures were not retrieved.")
    assert "were not retrieved" not in reply and "To the next tier" in reply


# ------------------------------------------------------------------ 3. no total-payout lead line


def test_N3_no_lead_sentence_about_the_total_payout_on_a_distance_question(targets):
    db, _c, _t = targets
    reply = _turn(db, "Which agents are closest to their next tier this month?",
                  [{"entity": ENTITY, "period": OCT}], "Total commission payout is RM 832,442.75.")
    assert "832,442.75" not in reply and "Total commission payout" not in reply
    assert reply.startswith("Distance to the next tier")


def test_N4_closest_is_ranked_by_distance_and_only_agents_when_agents_were_asked(targets):
    db, _c, t = targets
    reply = _turn(db, "Which agents are closest to their next tier this month?",
                  [{"entity": ENTITY, "period": OCT, "sort": [{"field": "payout", "dir": "desc"}]}], "Ranked.")
    assert "ZZT DEALER W2" not in reply
    a, b = f"{t['a'].sales_agent} - Agent A", f"{t['b'].sales_agent} - Agent B"
    assert a in reply and b in reply


# ------------------------------------------------------------------ 1. no agent ladder: one code line


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
    assert client.post(BASE, json=_dealer_body([dealer], payout_customer_id=dealer.id, tiers=[
        {"period_start": "2026-10-01", "threshold": 60000, "rate": 5}])).status_code == 201
    return db


@pytest.mark.parametrize("calls", [
    [{"entity": ENTITY, "period": OCT}],
    [{"entity": ENTITY, "period": OCT, "fields": ["payout"]}],
    [{"entity": ENTITY, "period": OCT, "group_by": ["owner"], "aggregates": [{"fn": "sum", "field": "payout"}]}],
    # An empty first call on a made-up name, then the real one.
    [{"entity": ENTITY, "agent": "Jayson", "period": OCT}, {"entity": ENTITY, "period": OCT}],
])
def test_N5_no_agent_commission_ladder_is_one_code_line(no_agent_ladder, calls):
    db = no_agent_ladder
    reply = _turn(db, "Which agents are closest to their next tier?", calls,
                  "Total payout is RM 832,442.75. ZZT LADDER DEALER is closest.")
    assert reply == NO_LADDER


def test_N6_a_dealer_ladder_question_is_still_answered_when_agents_have_none(no_agent_ladder):
    db = no_agent_ladder
    reply = _turn(db, "How far is dealer ZZT LADDER DEALER from its next tier?",
                  [{"entity": ENTITY, "agent": "ZZT LADDER DEALER", "period": ["01/10/2026", "31/12/2026"]}], "x")
    assert "RM 50,000.00 to go, would pay RM 3,000.00" in reply and NO_LADDER not in reply


# ------------------------------------------------------------------ 4. target of 0, other tables


def test_N7_a_target_of_0_never_shows_an_achieved_figure_on_the_targets_list(targets):
    db, client, t = targets
    zero = client.post(BASE, json={
        "subject_kind": "agent", "sales_agent_id": t["a"].id, "name": "ZZT zero", "metric": "amount",
        "basis": "ordered", "product_scope": "all", "start_date": "2026-10-01", "end_date": "2026-10-31",
        "target_value": 0,
    }).json()
    out = run(db, {"entity": "target_list", "period": OCT,
                   "fields": ["target_value", "achieved_value", "achieved_pct"]})
    [row] = [r for r in out["rows"] if zero["target_no"] in r["label"]]
    assert row["achieved_value"] == "no target set" and row["achieved_pct"] == "no target set"
    assert row["target_value"] == "no target set"


def test_N8_no_targets_table_is_appended_to_a_distance_answer(targets):
    """W1 / W2: the model also queried target_list and its table (achieved of a target of 0) was appended."""
    db, _c, _t = targets
    reply = _turn(db, "How far is Agent A from the next tier this month?", [
        {"entity": "target_list", "period": OCT},
        {"entity": ENTITY, "agent": "Agent A", "period": OCT},
    ], "x")
    assert "To the next tier" in reply and "Sales targets" not in reply


# ------------------------------------------------------------------ the question, and what is left alone


@pytest.mark.parametrize("said", [
    "How far is Agent A from the next tier this month?",
    "which agents are closest to their next tier",
    "how much more does agent b need to reach the next tier",
    "what would dealer X earn at its next tier",
    "how far is team north from the next tier",
    "who is nearest to the next commission tier",
])
def test_N9_distance_questions(said):
    from app.services.chatbot.agent.query_tools import next_tier_question

    assert next_tier_question(said)


@pytest.mark.parametrize("said", [
    "commission payout for agent a this year",
    "payout per dealer",
    "which tier did agent a reach in september",
    "show the tier ladder of TGT-000001",
])
def test_N10_other_questions_are_left_alone(targets, said):
    from app.services.chatbot.agent.query_tools import next_tier_args, next_tier_question

    assert not next_tier_question(said)
    args = {"entity": ENTITY, "agent": "Agent A", "fields": ["payout"]}
    assert next_tier_args(args, said) == args


def test_N11_a_payout_answer_keeps_its_lead_line_and_its_table(targets):
    db, _c, _t = targets
    reply = _turn(db, "commission payout per agent this month", [{"entity": ENTITY, "period": OCT}],
                  "Total payout is RM 360.00.")
    assert reply.startswith("Total payout is RM 360.00.") and "To the next tier" not in reply


# ------------------------------------------------------------------ review round on f18af7f3


def test_R1_view_own_asking_about_dealers_is_told_not_visible_never_no_ladder(targets, grant, monkeypatch):
    """B1: an empty result is not "no agent target has a commission ladder"; the own-only note speaks."""
    from app.services import own_scope

    db, _c, t = targets
    grant("sales.targets.view_own")
    monkeypatch.setattr(own_scope, "me", lambda db, user_id: own_scope.Me(str(user_id), None, (t["a"].id,)))
    reply = _turn(db, "How far are the dealers from their next tier this quarter?",
                  [{"entity": ENTITY, "period": ["01/10/2026", "31/12/2026"],
                    "filters": [{"field": "owner_kind", "op": "eq", "value": "dealer"}]}], "None found.")
    assert NO_LADDER not in reply and "not visible to you" in reply


def test_R2_a_second_question_in_the_turn_and_what_was_not_done_are_kept(targets):
    """B2: "Agent B's payout in September, and how far is Agent A from the next tier" kept only Agent A's card."""
    db, _c, t = targets
    reply = _turn(db, "What is Agent B's payout in September, and how far is Agent A from the next tier this month?", [
        {"entity": ENTITY, "agent": "Agent B", "period": "2026-09", "fields": ["payout"]},
        {"entity": ENTITY, "agent": "Agent A", "period": OCT},
    ], "Agent B earned nothing in September.\n\nNot checked: Agent B's August payout.\n\nI did not get to: team North.")
    assert f"{t['a'].sales_agent} - Agent A" in reply and f"{t['b'].sales_agent} - Agent B" in reply
    assert "Not checked: Agent B's August payout." in reply and "I did not get to: team North." in reply


def test_R3_two_named_subjects_are_two_tables(targets):
    db, _c, t = targets
    reply = _turn(db, "How far are Agent A and Agent B from the next tier this month?", [
        {"entity": ENTITY, "agent": "Agent A", "period": OCT},
        {"entity": ENTITY, "agent": "Agent B", "period": OCT},
    ], "x")
    assert f"{t['a'].sales_agent} - Agent A" in reply and f"{t['b'].sales_agent} - Agent B" in reply


def test_R4_closest_first_and_furthest_first_are_ranked_by_what_is_still_to_sell(targets):
    """B4 / K4: the ranking itself, and "furthest" (or a model's own desc sort) is furthest first."""
    from app.services.chatbot.agent.query_tools import next_tier_args

    db, _c, t = targets
    a, d = f"{t['a'].sales_agent} - Agent A", "ZZT DEALER W2"  # 1,000 and 60,000 to go in October / Q4
    window = ["01/10/2026", "31/10/2026"]
    closest = _turn(db, "who is closest to the next tier this month", [{"entity": ENTITY, "period": window}], "x")
    assert closest.index(a) < closest.index(d)
    furthest = _turn(db, "who is furthest from the next tier this month",
                     [{"entity": ENTITY, "period": window, "limit": 1}], "x")
    assert d in furthest and a not in furthest
    own = next_tier_args({"entity": ENTITY, "sort": [{"field": "to_next_tier", "dir": "desc"}]}, "how far from the next tier")
    assert own["sort"] == [{"field": "to_next_tier", "dir": "desc"}]


def test_R5_a_named_subject_not_found_is_answered_as_not_found(targets):
    """K8: no table and no no-ladder line for a name that matched nothing."""
    db, _c, _t = targets
    reply = _turn(db, "How far is Agent Zed from the next tier?", [{"entity": ENTITY, "agent": "Agent Zed", "period": OCT}],
                  "Agent Zed was not found.")
    assert reply.startswith("Agent Zed was not found.") and NO_LADDER not in reply and "Distance to the next tier" not in reply


def test_R6_which_agent_singular_ranks_agents_only(targets):
    from app.services.chatbot.agent.query_tools import next_tier_args

    out = next_tier_args({"entity": ENTITY}, "which agent is closest to the next tier")
    assert {"field": "owner_kind", "op": "eq", "value": "agent"} in out["filters"]


@pytest.mark.parametrize("said", [
    "how far are agents from their next tiers",
    "how much more to reach tier 2",
    "how much away from tier 3",
    "what does agent a need to hit tier 3",
    "what tier is next for agent a",
    "next level for agent a",
    "tier seterusnya untuk agent a",
    "berapa lagi agent a nak sampai tier seterusnya",
])
def test_R7_more_distance_phrasings(said):
    from app.services.chatbot.agent.query_tools import next_tier_question

    assert next_tier_question(said)


@pytest.mark.parametrize("said", [
    "who is closest to target and what tier are they on",
    "how far did agent a get last month and which tier did he reach",
    "what is the next tier rate for dealer d1",
])
def test_R8_not_distance_questions(said):
    from app.services.chatbot.agent.query_tools import next_tier_question

    assert not next_tier_question(said)
