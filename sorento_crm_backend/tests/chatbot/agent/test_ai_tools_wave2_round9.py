"""AI-TOOLS-WAVE2 crew live x3 on 3c6924bf (round 9): answers 21/21, token budget failed. No LLM.

- The model resolved the agent's name with crm_resolve first (+1 call, ~+20k): `crm_query` takes `agent` as the
  user said it and resolves it inside, and a crm_resolve round that found only sales agents points at it and narrows
  the next rounds' schemas.
- "Since July" read crm_describe and re-queried: `crm_query` takes `period` (a window name or [from, to]).
- "Who is below target" lost its table and its "Not reached = ..." note to a later payout query: one table per
  entity, a later entity never replaces the first.
"""
from __future__ import annotations

from datetime import date

import pytest

from tests.chatbot.agent.test_ai_tools_wave2 import (  # noqa: F401  (fixtures)
    BILLING_VIEW,
    CUSTOMERS_VIEW,
    SALES_REVEAL,
    _doc,
    grant,
    refused,
    run,
    targets,
)
from tests.test_dealer_targets_api import _customer
from tests.test_sales_targets_s1 import _agent, api, world  # noqa: F401  (fixtures)


@pytest.fixture
def october(monkeypatch):
    from app.services.assistant_registry import computed, query

    monkeypatch.setattr(computed, "_today", lambda: date(2026, 10, 20))
    monkeypatch.setattr(query, "local_today", lambda: date(2026, 10, 20))


# ------------------------------------------------------------------ agent and period as arguments


def test_P1_payout_for_an_agent_last_month_is_one_query_by_name(targets, october):
    db, _c, t = targets
    out = run(db, {"entity": "agent_target_summary", "agent": "Agent B", "period": "last_month",
                   "fields": ["achieved_pct", "payout"]})
    [row] = out["rows"]
    assert row["label"] == f"{t['b'].sales_agent} - Agent B"
    assert (row["achieved_pct"], row["payout"]) == (50.0, 0.0)
    assert out["period_display"] == "Period 01/09/2026 to 30/09/2026"
    assert f"Agent: {t['b'].sales_agent} - Agent B." in out["scope_note"]


def test_P2_since_july_is_a_period_from_a_month_to_today(targets, october):
    db, _c, t = targets
    out = run(db, {"entity": "agent_target_summary", "agent": t["a"].sales_agent, "period": ["2026-07", "today"],
                   "fields": ["periods", "payout"]})
    [row] = out["rows"]
    assert row["periods"] == 4 and row["payout"] == 360.0 + 180.0
    assert out["period_display"] == "Period 01/07/2026 to 20/10/2026"


def test_P3_below_target_by_period_argument_reads_that_window_and_keeps_its_definition(targets, october):
    db, _c, _t = targets
    out = run(db, {"entity": "target_list", "period": "last_quarter",
                   "filters": [{"field": "reached", "op": "eq", "value": False}]})
    assert out["period_display"] == "Period 01/07/2026 to 30/09/2026"
    assert out["total"] == 3
    assert run(db, {"entity": "target_list", "period": "2027"})["rows"] == []
    assert out["scope_note"].startswith("Not reached = achieved under 100% of target, as the Targets screen shows it.")


def test_P4_active_customers_of_an_agent_by_argument(api, grant):
    _client, db, company_id = api
    grant(CUSTOMERS_VIEW)
    b, b3 = _agent(db, "B", "ZZT Long I"), _agent(db, "B3", "ZZT Long II")
    for agent, n in ((b, 2), (b3, 5)):
        for i in range(n):
            _customer(db, company_id, f"ZZT {agent.sales_agent} {i}").sales_agent_id = agent.id
    db.flush()
    out = run(db, {"entity": "customer", "agent": "zzt long i", "aggregates": [{"fn": "count"}]})
    assert out["groups"][0]["count"] == 2


def test_P5_sales_of_an_agent_last_month_on_billing_documents(api, grant, monkeypatch):
    from app.services.assistant_registry import query

    monkeypatch.setattr(query, "local_today", lambda: date(2026, 11, 7))
    _client, db, company_id = api
    grant(BILLING_VIEW, SALES_REVEAL)
    a = _agent(db, "SP", "ZZT Sean I")
    cust = _customer(db, company_id, "ZZT P5 CUST")
    _doc(db, company_id, "invoice", "400", date(2026, 10, 9), agent=a, customer=cust)
    _doc(db, company_id, "invoice", "900", date(2026, 11, 2), agent=a, customer=cust)
    out = run(db, {"entity": "billing_document", "agent": "ZZT Sean I", "period": "last_month",
                   "aggregates": [{"fn": "sum", "field": "sales_amount"}]})
    assert out["groups"][0]["sum_sales_amount"] == 400.0
    assert out["period_display"] == "Document date 01/10/2026 to 31/10/2026"


def test_P6_arguments_that_do_not_apply_are_refused_before_anything_runs(api, grant):
    _client, db, _company = api
    grant(CUSTOMERS_VIEW, "order_management.orders.view")
    assert refused(db, {"entity": "customer", "period": "last_month"}).code == "invalid"
    assert refused(db, {"entity": "order", "agent": "X"}).code == "invalid"
    assert refused(db, {"entity": "customer", "agent": "  "}).code == "invalid"
    assert refused(db, {"entity": "customer", "agent": "X", "period": {"from": "2026-07"}}).code == "invalid"


def test_P7_the_schema_offers_agent_and_period():
    from app.services.chatbot.agent.query_tools import QUERY_SCHEMA

    props = QUERY_SCHEMA["function"]["parameters"]["properties"]
    assert {"agent", "period"} <= set(props)
    assert "no crm_resolve" in QUERY_SCHEMA["function"]["description"]


# ------------------------------------------------------------------ a crm_resolve round that named an agent


def _schema(name):
    return {"type": "function", "function": {"name": name}}


ALL = [_schema(n) for n in ("crm_query", "crm_describe", "answer", "plan", "crm_resolve", "crm_report_ask",
                            "crm_order_management_orders_list", "crm_products_find")]


def test_N1_a_resolve_round_that_found_only_agents_narrows_the_schemas():
    from app.services.chatbot.agent.loop import narrow_after_query

    calls = [{"name": "crm_resolve"}]
    done = [{"name": "crm_resolve", "status": "ok", "agents_only": True}]
    kept = [s["function"]["name"] for s in narrow_after_query(ALL, calls, done)]
    assert kept == ["crm_query", "crm_describe", "answer", "plan", "crm_report_ask"]


@pytest.mark.parametrize("done", [
    [{"name": "crm_resolve", "status": "ok", "agents_only": False}],
    [{"name": "crm_resolve", "status": "invalid", "agents_only": False}],
])
def test_N2_a_resolve_round_for_anything_else_keeps_every_schema(done):
    from app.services.chatbot.agent.loop import narrow_after_query

    assert narrow_after_query(ALL, [{"name": "crm_resolve"}], done) == ALL


def test_N3_found_agents_only_when_every_term_is_one_sales_agent():
    from app.services.chatbot.agent.loop import found_agents

    agent = {"kind": "sales_agent", "code": "LI", "name": "LONG I"}
    assert found_agents({"results": [{"term": "long i", "status": "found", "matches": [agent]}]}) == ["LI - LONG I"]
    customer = {"kind": "customer", "code": "C1", "name": "Long Trading"}
    assert found_agents({"results": [{"term": "x", "status": "found", "matches": [customer]}]}) == []
    assert found_agents({"results": [{"term": "x", "status": "ambiguous", "matches": [agent, agent]}]}) == []
    assert found_agents({"results": []}) == [] and found_agents(None) == []


# ------------------------------------------------------------------ one table per entity


def _card(entity, display, cid):
    return cid, {"name": "crm_query", "status": "ok", "args": {"entity": entity}, "data": {"entity": entity},
                 "display": display}


def test_T1_a_later_query_on_another_entity_never_replaces_the_answers_table():
    from app.services.chatbot.agent.query_tools import shape_reply

    below = "Sales targets\n| a |\nNot reached = achieved under 100% of target, as the Targets screen shows it."
    payout = "Sales targets by agent\n| b |"
    ledger = dict([_card("target_list", below, "c1"), _card("agent_target_summary", payout, "c2")])
    reply = shape_reply("65 targets are below target.", ledger)
    assert reply.index(below) < reply.index(payout)
    assert "Not reached = achieved under 100% of target" in reply


def test_T2_a_corrected_query_on_the_same_entity_shows_the_last_table_only():
    from app.services.chatbot.agent.query_tools import shape_reply

    ledger = dict([_card("target_list", "first table", "c1"), _card("target_list", "second table", "c2")])
    reply = shape_reply("Here.", ledger)
    assert "second table" in reply and "first table" not in reply


def test_T3_two_tables_the_model_wrote_out_keep_its_sentence_between_them():
    from app.services.chatbot.agent.query_tools import shape_reply

    ledger = dict([_card("target_list", "TABLE ONE", "c1"), _card("agent_target_summary", "TABLE TWO", "c2"),
                   ("c3", {"name": "crm_query", "status": "ok", "args": {"entity": "customer"},
                           "data": {"entity": "customer", "rows": [], "scope_note": None}})])
    text = "Below target:\n\nTABLE ONE\n\nAnd the payout per agent:\n\nTABLE TWO"
    assert shape_reply(text, ledger) == text


def test_P8_agent_on_a_computed_entity_is_exact_never_a_team_containing_it(targets, october):
    db, _c, t = targets
    out = run(db, {"entity": "target_list", "agent": "Agent"})
    assert out["rows"] == [] and "do not show or total other records" in out["instruction"]
    out = run(db, {"entity": "target_list", "agent": "Agent A"})
    assert [r["label"] for r in out["rows"]] == [f"{t['ta']['target_no']}: {t['a'].sales_agent} - Agent A"]


def test_N4_a_plan_in_several_parts_keeps_every_schema_after_an_agent_resolve():
    from app.services.chatbot.agent.loop import narrow_after_query

    done = [{"name": "crm_resolve", "status": "ok", "agents_only": True}]
    assert narrow_after_query(ALL, [{"name": "plan"}, {"name": "crm_resolve"}], done, plan_parts=2) == ALL
    kept = narrow_after_query(ALL, [{"name": "plan"}, {"name": "crm_resolve"}], done, plan_parts=1)
    assert [s["function"]["name"] for s in kept] == ["crm_query", "crm_describe", "answer", "plan", "crm_report_ask"]
