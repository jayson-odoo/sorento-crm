"""AGENT-COMMISSION-ALL (owner 8 Nov): the assistant answers commission payout for dealers and teams, not only
agents (`documentation/plans/sales/PLAN-agent-commission-all-08nov.md`). Entity output only, no LLM.

Owner answers on the behaviour card: Q1 (a) an agent's payout is its own agent targets only, a dealer's payout is
answered as the dealer's; Q2 a team is its team target's own payout, the members only when asked by team; Q3 no
person named for a team; Q4 a view_own holder sees no team or dealer payout ("not visible to you"); Q5 a replaced
dealer period shows 0 with the target that replaced it.

Fixture (`test_ai_tools_wave2.targets`, today 20 Oct 2026): agents A and B with monthly agent targets of 10,000
(80% at 2%, 100% at 3%), A 12,000 in Sep, B 5,000 in Sep, both 9,000 in Oct; a quarterly dealer target whose one
account "ZZT DEALER W2" sold 70,000 in Aug (Q3 tier 60,000 at 5% = 3,500).
"""
from __future__ import annotations

from datetime import date

import pytest

from tests.chatbot.agent.test_ai_tools_wave2 import grant, run, targets  # noqa: F401  (fixtures)
from tests.test_dealer_targets_api import _replacing_pair
from tests.test_sales_targets_s1 import BASE, TEAMS_BASE, api, world  # noqa: F401  (fixtures)

ENTITY = "agent_target_summary"
Q3 = ["01/07/2026", "30/09/2026"]
YEAR = ["01/01/2026", "31/12/2026"]


def _agent_label(t, key):
    return f"{t[key].sales_agent} - Agent {key.upper()}"


def _page_payout(db, target_id, date_from, date_to):
    """Commission + bonus of a target's periods overlapping the window, read from the target page itself."""
    from app.services.sales import target_service

    target = target_service.get_target_or_404(db, target_id)
    total = 0.0
    for p in target_service.target_detail(db, target)["periods"]:
        if p["period_start"] <= date_to and p["period_end"] >= date_from:
            total += (p["commission_earned"] or 0) + (p["bonus_earned"] or 0)
    return round(total, 2)


def _dealer_account(db, t):
    from app.models.order import Customer
    from app.models.sales import SalesTargetAccount

    customer_id = db.query(SalesTargetAccount.customer_id).filter(SalesTargetAccount.target_id == t["dealer"]["id"]).scalar()
    return db.get(Customer, customer_id)


@pytest.fixture
def team(targets):
    """Team "ZZT North" (agents A and B) with an October team target of 20,000 that pays 1% from 80%."""
    db, client, t = targets
    north = client.post(TEAMS_BASE, json={"name": "ZZT North", "sales_agent_ids": [t["a"].id, t["b"].id]})
    assert north.status_code in (200, 201), north.text
    res = client.post(BASE, json={
        "subject_kind": "team", "sales_team_id": north.json()["id"], "name": "ZZT North Oct", "metric": "amount",
        "basis": "ordered", "product_scope": "all", "start_date": "2026-10-01", "end_date": "2026-10-31",
        "agent_figures": [{"sales_agent_id": t["a"].id, "target_value": 10000},
                          {"sales_agent_id": t["b"].id, "target_value": 10000}],
        "commission_method": "retroactive", "tiers": [{"from_pct": 80, "rate": 1}],
    })
    assert res.status_code == 201, res.text
    return db, client, {**t, "team": res.json()}


# ------------------------------------------------------------------ dealers


def test_C1_dealer_payout_by_its_name_is_one_dealer_row_equal_to_the_page(targets):
    db, _c, t = targets
    out = run(db, {"entity": ENTITY, "agent": "ZZT DEALER W2", "period": Q3,
                   "fields": ["owner_kind", "commission", "bonus", "payout"]})
    [row] = out["rows"]
    assert row["label"] == "ZZT DEALER W2" and row["owner_kind"] == "dealer"
    assert row["commission"] == 3500.0 and row["payout"] == 3500.0
    assert row["payout"] == _page_payout(db, t["dealer"]["id"], date(2026, 7, 1), date(2026, 9, 30))
    assert "instruction" not in out


def test_C2_dealer_by_an_account_code_and_by_part_of_its_name(targets):
    db, _c, t = targets
    code = _dealer_account(db, t).customer_code
    by_code = run(db, {"entity": ENTITY, "agent": code, "period": Q3, "fields": ["payout"]})
    assert [r["label"] for r in by_code["rows"]] == ["ZZT DEALER W2"]
    by_part = run(db, {"entity": ENTITY, "filters": [{"field": "owner", "op": "contains", "value": "dealer w2"}],
                       "period": Q3, "fields": ["payout"]})
    assert [r["payout"] for r in by_part["rows"]] == [3500.0]


def test_C3_payout_per_dealer_is_one_row_per_dealer_target_subject(targets):
    db, _c, t = targets
    out = run(db, {"entity": ENTITY, "period": Q3, "filters": [{"field": "owner_kind", "op": "eq", "value": "dealer"}],
                   "fields": ["payout"]})
    assert [r["label"] for r in out["rows"]] == ["ZZT DEALER W2"]
    assert out["totals"]["payout"] == 3500.0


# ------------------------------------------------------------------ agents: their own targets only (Q1)


def test_C4_an_agents_payout_never_includes_a_dealer_it_owns(targets):
    """Q1 (a): the dealer's commission is paid to the dealer's account, not to the agent who owns it."""
    db, _c, t = targets
    _dealer_account(db, t).sales_agent_id = t["a"].id
    db.flush()
    out = run(db, {"entity": ENTITY, "agent": "Agent A", "period": Q3, "fields": ["kinds", "targets", "payout"]})
    [row] = out["rows"]
    assert row["label"] == _agent_label(t, "a")
    assert row["kinds"] == "agent" and row["targets"] == 1
    assert row["payout"] == 360.0 == _page_payout(db, t["ta"]["id"], date(2026, 7, 1), date(2026, 9, 30))
    dealer = run(db, {"entity": ENTITY, "agent": "ZZT DEALER W2", "period": Q3, "fields": ["agent", "payout"]})
    [d] = dealer["rows"]
    # The dealer row names the agent who owns its accounts, so "dealers of Agent A" is a filter.
    assert d["agent"] == _agent_label(t, "a") and d["payout"] == 3500.0
    mine = run(db, {"entity": ENTITY, "period": Q3, "fields": ["payout"], "filters": [
        {"field": "agent", "op": "eq", "value": "Agent A"}, {"field": "owner_kind", "op": "eq", "value": "dealer"}]})
    assert [r["label"] for r in mine["rows"]] == ["ZZT DEALER W2"]


def test_C5_everyone_is_agents_then_teams_then_dealers_with_totals(team):
    db, _c, t = team
    out = run(db, {"entity": ENTITY, "fields": ["owner_kind", "payout"]})
    kinds = [r["owner_kind"] for r in out["rows"]]
    assert kinds == sorted(kinds, key=["agent", "team", "dealer"].index)
    assert {"agent", "team", "dealer"} == set(kinds)
    assert "Unassigned" not in [r["label"] for r in out["rows"]]
    assert out["totals"]["payout"] == round(sum(r["payout"] or 0 for r in out["rows"]), 2)


# ------------------------------------------------------------------ teams (Q2, Q3)


@pytest.mark.parametrize("said", ["ZZT North", "Team ZZT North", "team zzt north"])
def test_C6_team_payout_by_its_name_with_or_without_team(team, said):
    db, _c, t = team
    out = run(db, {"entity": ENTITY, "agent": said, "period": "2026-10",
                   "fields": ["owner_kind", "commission", "payout", "achieved_pct"]})
    [row] = out["rows"]
    assert row["label"] == "Team ZZT North" and row["owner_kind"] == "team"
    page = _page_payout(db, t["team"]["id"], date(2026, 10, 1), date(2026, 10, 31))
    assert row["payout"] == page == 180.0  # 18,000 of 20,000 = 90%, 1%
    assert "instruction" not in out


def test_C7_team_members_payout_is_their_own_agent_targets_by_team(team):
    """Q2 (b): "commission of the agents in team North" is the agent rows filtered by team, never the team row."""
    db, _c, t = team
    out = run(db, {"entity": ENTITY, "period": "2026-10", "fields": ["team", "payout"],
                   "filters": [{"field": "team", "op": "eq", "value": "ZZT North"}]})
    assert [r["label"] for r in out["rows"]] == [_agent_label(t, "a"), _agent_label(t, "b")]
    assert out["totals"]["payout"] == 180.0 + 180.0


# ------------------------------------------------------------------ replaced dealer period (Q5)


def test_C8_a_replaced_dealer_period_pays_0_and_names_the_target_that_replaced_it(api, grant):
    """The account's own target and the dealer target that replaces it carry the same dealer name: one dealer row,
    paid once (the dealer's tier), and the answer says which target was replaced by which."""
    client, db, company_id = api
    grant("sales.targets.view")
    dealer, own = _replacing_pair(client, db, company_id, 1300000)
    out = run(db, {"entity": ENTITY, "agent": "ZZT REPL A/C I", "period": YEAR,
                   "fields": ["owner_kind", "targets", "payout", "replaced_by"]})
    [row] = out["rows"]
    assert row["owner_kind"] == "dealer" and row["targets"] == 2
    year = date(2026, 1, 1), date(2026, 12, 31)
    assert _page_payout(db, own["id"], *year) == 0
    assert row["payout"] == _page_payout(db, dealer["id"], *year) == 16000 + 32500
    assert row["replaced_by"] == dealer["target_no"]
    assert f"{own['target_no']} (ZZT REPL A/C I) is replaced by {dealer['target_no']}" in out["scope_note"]


# ------------------------------------------------------------------ permissions (Q4) and the index


def test_C9_view_own_sees_no_team_or_dealer_payout_and_is_told(team, grant, monkeypatch):
    from app.services import own_scope

    db, _c, t = team
    grant("sales.targets.view_own")
    monkeypatch.setattr(own_scope, "me", lambda db, user_id: own_scope.Me(str(user_id), None, (t["a"].id,)))
    out = run(db, {"entity": ENTITY, "period": "2026-10", "fields": ["owner_kind", "payout"]})
    assert {r["owner_kind"] for r in out["rows"]} == {"agent"}
    assert [r["label"] for r in out["rows"]] == [_agent_label(t, "a")]
    assert "not visible to you" in out["scope_note"]
    dealer = run(db, {"entity": ENTITY, "agent": "ZZT DEALER W2", "period": Q3})
    assert dealer["rows"] == [] and "not visible to you" in dealer["scope_note"]


def test_C10_view_holder_gets_no_own_only_note(team):
    db, _c, _t = team
    out = run(db, {"entity": ENTITY, "period": "2026-10"})
    assert "not visible to you" not in (out["scope_note"] or "")


def test_C11_the_index_routes_agent_team_and_dealer_payout_to_the_summary():
    from app.services.chatbot.agent import query_tools

    line = next(x for x in query_tools.entity_index().splitlines() if x.startswith("agent_target_summary ("))
    hint = line.split("):")[0].lower()
    assert "dealer" in hint and "team" in hint and "agent" in hint


def test_C12_every_row_is_the_sum_of_its_targets_page_payouts(team):
    """One computation: each subject's payout equals its targets' page figures over the window."""
    db, _c, t = team
    out = run(db, {"entity": ENTITY, "period": ["01/07/2026", "31/10/2026"], "fields": ["owner_kind", "payout"]})
    by = {r["label"]: r["payout"] for r in out["rows"]}
    lo, hi = date(2026, 7, 1), date(2026, 10, 31)
    assert by[_agent_label(t, "a")] == _page_payout(db, t["ta"]["id"], lo, hi)
    assert by[_agent_label(t, "b")] == _page_payout(db, t["tb"]["id"], lo, hi)
    assert by["Team ZZT North"] == _page_payout(db, t["team"]["id"], lo, hi)
    assert by["ZZT DEALER W2"] == _page_payout(db, t["dealer"]["id"], lo, hi)


# ------------------------------------------------------------------ owner session evidence (crew, 8 Nov)


def _plain_agent_target(client, agent, *, value, tiers=None):
    body = {
        "subject_kind": "agent", "sales_agent_id": agent.id, "name": "Test", "metric": "amount", "basis": "ordered",
        "product_scope": "all", "start_date": "2026-10-01", "end_date": "2026-10-31", "target_value": value,
    }
    if tiers:
        body.update({"commission_method": "retroactive", "tiers": tiers})
    res = client.post(BASE, json=body)
    assert res.status_code == 201, res.text
    return res.json()


def test_E1_a_persons_first_name_takes_every_code_of_that_person_in_one_query(targets):
    """Owner C3: "commission payout to <first name>" matched none of Agent F I / III / IV (one person, three codes);
    the model then queried each code and the 3-call cap left Agent F IV unchecked."""
    from tests.test_sales_targets_s1 import _agent

    db, client, _t = targets
    codes = [_agent(db, f"F{n}", f"Fanny {n}", person_label="Fanny") for n in ("I", "III", "IV")]
    for agent in codes:
        _plain_agent_target(client, agent, value=1000, tiers=[{"from_pct": 100, "rate": 1}])
    for said in ("Fanny", "fanny"):
        out = run(db, {"entity": ENTITY, "agent": said, "period": "2026-10", "fields": ["payout"]})
        assert sorted(r["label"] for r in out["rows"]) == sorted(f"{a.sales_agent} - {a.description}" for a in codes)
        assert "instruction" not in out


def test_E2_a_target_of_0_adds_nothing_to_target_achieved_or_percent(targets):
    """Owner C3: an RM-0 agent target named "Test" put RM 10.4M "achieved" on the row: 1,396.8%, payout RM 0."""
    db, client, t = targets
    zero = _plain_agent_target(client, t["a"], value=0)
    out = run(db, {"entity": ENTITY, "agent": "Agent A", "period": "2026-10",
                   "fields": ["targets", "target_value", "achieved_value", "achieved_pct", "payout"]})
    [row] = out["rows"]
    assert row["targets"] == 2
    assert (row["target_value"], row["achieved_value"], row["achieved_pct"], row["payout"]) == (10000.0, 9000.0, 90.0, 180.0)
    assert zero["target_no"] in out["scope_note"] and "target of 0" in out["scope_note"]


def test_E3_no_commission_set_is_said_never_shown_as_rm_0(targets):
    """Owner C3: Agent F III has no commission target; the reply printed "RM 0.00"."""
    from tests.test_sales_targets_s1 import _agent

    db, client, _t = targets
    c = _agent(db, "C", "Agent C")
    _plain_agent_target(client, c, value=5000)
    out = run(db, {"entity": ENTITY, "agent": "Agent C", "period": "2026-10", "fields": ["commission", "payout"]})
    [row] = out["rows"]
    assert row["payout"] is None and row["commission"] is None
    assert "No commission is set" in out["scope_note"] and c.sales_agent in out["scope_note"]
