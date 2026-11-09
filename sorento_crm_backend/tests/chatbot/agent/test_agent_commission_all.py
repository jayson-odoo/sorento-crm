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
from tests.test_dealer_targets_api import _stacking_pair
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


def test_C5_everyone_is_ranked_by_payout_with_totals(team):
    """Crew live x3 (8 Nov): highest payout first, rows with no commission set last."""
    db, _c, _t = team
    out = run(db, {"entity": ENTITY, "fields": ["owner_kind", "payout"]})
    kinds = [r["owner_kind"] for r in out["rows"]]
    assert {"agent", "team", "dealer"} == set(kinds)
    assert "Unassigned" not in [r["label"] for r in out["rows"]]
    paid = [r["payout"] for r in out["rows"] if isinstance(r["payout"], float)]
    assert paid == sorted(paid, reverse=True)
    assert out["totals"]["payout"] == round(sum(paid), 2)


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


# ------------------------------------------------------------------ stacking dealer targets (lane TARGET-PER-ACCOUNT-PAYOUT)


def test_C8_stacking_dealer_targets_both_pay_each_account_its_own_share(api, grant):
    """One row per dealer target, as the Dealers tab lists them (crew live round 2). Owner 8 Nov: the combined target
    and the account's own target both pay, and each row lists each account's own share."""
    client, db, company_id = api
    grant("sales.targets.view")
    dealer, own = _stacking_pair(client, db, company_id, 1300000)
    out = run(db, {"entity": ENTITY, "agent": "ZZT STACK A/C I", "period": YEAR,
                   "fields": ["owner_kind", "targets", "payout", "account_payouts"]})
    assert len(out["rows"]) == 2 and {r["owner_kind"] for r in out["rows"]} == {"dealer"}
    year = date(2026, 1, 1), date(2026, 12, 31)
    top, second = out["rows"]
    assert top["payout"] == _page_payout(db, dealer["id"], *year) == 16000 + 32500
    assert top["account_payouts"] == "A/C I 16,000.00; A/C III 32,500.00"
    assert second["payout"] == _page_payout(db, own["id"], *year) == 8000
    assert second["account_payouts"] == "A/C I 8,000.00"
    assert "replaced" not in (out.get("scope_note") or "")


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
    assert f"No target set on {zero['target_no']}" in out["scope_note"]
    assert "RM 0" not in out["scope_note"] and "of 0" not in out["scope_note"]


def test_E3_no_commission_set_is_said_never_shown_as_rm_0(targets):
    """Owner C3: Agent F III has no commission target; the reply printed "RM 0.00"."""
    from tests.test_sales_targets_s1 import _agent

    db, client, _t = targets
    c = _agent(db, "C", "Agent C")
    _plain_agent_target(client, c, value=5000)
    out = run(db, {"entity": ENTITY, "agent": "Agent C", "period": "2026-10", "fields": ["commission", "payout"]})
    [row] = out["rows"]
    assert row["payout"] == row["commission"] == "no commission set"
    assert "No commission is set" in out["scope_note"] and c.sales_agent in out["scope_note"]


# ------------------------------------------------------------------ review round 1


def test_R1_dealers_of_a_person_match_by_the_person_behind_the_owning_agent(targets):
    db, _c, t = targets
    t["a"].person_label = "Alpha"
    _dealer_account(db, t).sales_agent_id = t["a"].id
    db.flush()
    out = run(db, {"entity": ENTITY, "period": Q3, "fields": ["payout"], "filters": [
        {"field": "agent", "op": "eq", "value": "Alpha"}, {"field": "owner_kind", "op": "eq", "value": "dealer"}]})
    assert [r["label"] for r in out["rows"]] == ["ZZT DEALER W2"]
    assert out["scope_note"].startswith("Agent:")


def test_R2_the_agent_field_note_warns_it_also_returns_the_agents_dealers():
    from app.services.assistant_registry import ENTITIES

    note = ENTITIES[ENTITY].fields["agent"].note
    assert "also returns" in note and "owner_kind eq agent" in note


def test_R3_a_note_naming_more_rows_than_it_lists_says_how_many_more():
    from app.services.assistant_registry.sales import _summary_note

    rows = [{"owner": f"A{i}", "_zero": [], "_has_commission": False} for i in range(7)]
    assert "A0, A1, A2, A3, A4 and 2 more" in _summary_note(rows)


# ------------------------------------------------------------------ crew live x3 on fe1c8af4 (8 Nov)


@pytest.fixture
def dealers(targets):
    """Three more dealers, each one account, Q3 sales 61,000 / 80,000 / 100,000 on a 60,000 tier at 5%."""
    from tests.test_dealer_targets_api import _customer, _dealer_body, _product_id, _sale

    db, client, t = targets
    company_id = _dealer_account(db, t).company_id
    pid = _product_id(db, company_id)
    for name, sold in (("ZZT AAA LOW", 61000), ("ZZT MMM MID", 80000), ("ZZT ZZZ TOP", 100000)):
        c = _customer(db, company_id, name, level=1)
        _sale(db, company_id, c, str(sold), date(2026, 8, 3), product_id=pid)
        res = client.post(BASE, json=_dealer_body([c], tiers=[
            {"period_start": "2026-07-01", "threshold": 60000, "rate": 5},
        ]))
        assert res.status_code == 201, res.text
    return db, client, t


DEALERS_YEAR = {"filters": [{"field": "owner_kind", "op": "eq", "value": "dealer"}], "period": "2026"}


def test_L1_payout_per_dealer_ranks_by_payout_with_totals_over_all_dealers(dealers):
    """Live Q2: 'Showing 20 of 50' sorted by name, the top dealer missing, no totals row."""
    from app.services.chatbot.agent.query_tools import render_card

    db, _c, _t = dealers
    out = run(db, {"entity": ENTITY, **DEALERS_YEAR, "fields": ["payout"]})
    assert [r["label"] for r in out["rows"]] == ["ZZT ZZZ TOP", "ZZT MMM MID", "ZZT DEALER W2", "ZZT AAA LOW"]
    assert [r["payout"] for r in out["rows"]] == [5000.0, 4000.0, 3500.0, 3050.0]
    assert out["totals"]["payout"] == 15550.0
    capped = run(db, {"entity": ENTITY, **DEALERS_YEAR, "fields": ["payout"], "limit": 2})
    assert [r["payout"] for r in capped["rows"]] == [5000.0, 4000.0]
    assert capped["totals"]["payout"] == 15550.0  # every dealer, not the page shown
    card = render_card(capped, title="x", panel=True)
    assert "Top 2 of 4 by commission payout." in card and "Showing" not in card


def test_L1b_grouped_per_dealer_ranks_by_the_sum_and_totals_every_group(dealers):
    db, _c, _t = dealers
    out = run(db, {"entity": ENTITY, **DEALERS_YEAR, "group_by": ["owner"],
                   "aggregates": [{"fn": "sum", "field": "payout"}], "limit": 2})
    # Crew live round 4: a regroup by dealer is answered with the dealer rows themselves (see G1).
    assert [r["payout"] for r in out["rows"]] == [5000.0, 4000.0]
    assert out["totals"]["payout"] == 15550.0 and out["truncated"] is True


def test_L1c_a_long_payout_list_is_not_cut_at_20_by_default(targets):
    from app.services.assistant_registry import ENTITIES
    from app.services.assistant_registry.computed import _rows

    entity = ENTITIES[ENTITY]
    rows = [{"id": str(i), "owner": f"D{i}", "owner_kind": "dealer", "payout": float(i), "_has_commission": True}
            for i in range(45)]
    out = _rows(entity, {"sales.targets.view"}, rows, [], {"fields": ["payout"]})
    assert len(out["rows"]) == 45 and out["truncated"] is False


def test_L2_no_commission_set_is_written_in_the_rows_and_never_totalled_as_0(targets):
    """Live Q5 run 2: 'Total Commission: RM 0, Total Bonus: RM 0' next to 'Payout: Empty'."""
    from app.services.chatbot.agent.query_tools import render_card
    from tests.test_sales_targets_s1 import _agent

    db, client, _t = targets
    c = _agent(db, "C", "Agent C")
    _plain_agent_target(client, c, value=5000)
    out = run(db, {"entity": ENTITY, "agent": "Agent C", "period": "2026-10",
                   "fields": ["commission", "bonus", "payout"]})
    [row] = out["rows"]
    assert row["commission"] == row["bonus"] == row["payout"] == "no commission set"
    assert not {"commission", "bonus", "payout"} & set(out.get("totals") or {})
    card = render_card({**out, "rows": out["rows"] * 11}, title="x", panel=True)
    assert "RM 0" not in card and "| 0 |" not in card


def test_L2b_a_row_of_only_targets_of_0_prints_no_target_or_achieved_figure(targets):
    """Live Q4 run 2: target RM 0.00 / achieved RM 9.92M printed against its own 'left out' note."""
    from tests.test_sales_targets_s1 import _agent

    db, client, _t = targets
    z = _agent(db, "Z", "Agent Z")
    _plain_agent_target(client, z, value=0)
    out = run(db, {"entity": ENTITY, "agent": "Agent Z", "period": "2026-10",
                   "fields": ["target_value", "achieved_value", "achieved_pct"]})
    [row] = out["rows"]
    assert row["target_value"] == row["achieved_value"] == row["achieved_pct"] == "no target set"


def test_L3_no_period_named_is_this_year_and_says_so(targets):
    """Live Q6: 'payout to fullshun' with no period answered only for the period containing today."""
    db, _c, _t = targets
    out = run(db, {"entity": ENTITY, "agent": "ZZT DEALER W2", "fields": ["payout"]})
    assert out["period_display"] == "Period 01/01/2026 to 31/12/2026"
    assert out["rows"][0]["payout"] == 3500.0  # Q3 counts, not only the Q4 period containing today
    assert "No period named: this year, 01/01/2026 to 31/12/2026." in out["scope_note"]


def test_L4_an_empty_crm_query_backs_a_not_found_claim_for_its_term():
    """Live O1: the reply opened with 'I could not confirm that nothing exists for:' after a crm_query that matched
    nothing for the very term."""
    from app.services.chatbot.agent import loop

    ledger = {"q1": {"name": "crm_query", "status": "ok", "args": {"entity": ENTITY, "agent": "fullshun"},
                     "data": {"entity": ENTITY, "rows": [], "total": 0, "instruction": "Nothing matched."}}}
    assert loop._not_found_backed("commission payout for Fullshun", "q1", ledger, set()) is True
    assert loop._not_found_backed("Hanlim", "q1", ledger, set()) is False
    other = {"q1": {**ledger["q1"], "data": {"entity": ENTITY, "rows": [{"id": "1"}], "total": 1}}}
    assert loop._not_found_backed("fullshun", "q1", other, set()) is False


def test_L4b_an_unbacked_not_found_claim_is_worded_plainly():
    from app.services.chatbot.agent import loop

    text, _ = loop.final_reply({"text": "No payout for X."}, [], ["X"], ledger={})
    assert "could not confirm that nothing exists" not in text
    assert text.startswith("I did not search for X, so I cannot say it does not exist.")


# ------------------------------------------------------------------ review round 2


@pytest.mark.parametrize("claim, args", [
    # "dealer" is an owner_kind value, never a searched name.
    ("payout for dealer Hanlim", {"entity": ENTITY, "agent": "fullshun",
                                  "filters": [{"field": "owner_kind", "op": "eq", "value": "dealer"}]}),
    # Empty because of the payout filter: fullshun may well exist.
    ("fullshun", {"entity": ENTITY, "agent": "fullshun", "filters": [{"field": "payout", "op": "gt", "value": 999999}]}),
    # A status value is not a name.
    ("pending orders for Hanlim", {"entity": "order", "filters": [{"field": "status", "op": "eq", "value": "pending"}]}),
])
def test_R4_an_empty_crm_query_backs_only_the_name_it_searched_with_no_other_narrowing(claim, args):
    from app.services.chatbot.agent import loop

    ledger = {"q1": {"name": "crm_query", "status": "ok", "args": args,
                     "data": {"entity": args["entity"], "rows": [], "total": 0}}}
    assert loop._not_found_backed(claim, "q1", ledger, set()) is False


def test_R4b_a_name_filter_and_a_window_still_back_it():
    from app.services.chatbot.agent import loop

    args = {"entity": ENTITY, "period": "2026", "filters": [
        {"field": "owner", "op": "contains", "value": "fullshun"},
        {"field": "period", "op": "between", "value": ["01/01/2026", "31/12/2026"]}]}
    ledger = {"q1": {"name": "crm_query", "status": "ok", "args": args, "data": {"entity": ENTITY, "rows": [], "total": 0}}}
    assert loop._not_found_backed("fullshun", "q1", ledger, set()) is True


def test_R5_too_many_periods_this_year_falls_back_to_the_current_periods(targets, monkeypatch):
    from app.services.assistant_registry import ENTITIES
    from app.services.assistant_registry.query import QueryRefused

    db, _c, _t = targets
    entity = ENTITIES[ENTITY]
    real = entity.compute

    def capped(db, user_id, own_only, date_from, date_to, *, limit):
        if date_from != date_to:
            raise QueryRefused("timeout", "More than 2000 target periods in that window; narrow it.")
        return real(db, user_id, own_only, date_from, date_to, limit=limit)

    monkeypatch.setitem(ENTITIES, ENTITY, type(entity)(**{**entity.__dict__, "compute": capped}))
    out = run(db, {"entity": ENTITY, "fields": ["payout"]})
    assert out["rows"] and out["period_display"] is None
    assert "too many periods this year" in out["scope_note"] and "containing today" in out["scope_note"]


# ------------------------------------------------------------------ crew live round 2 on 20d05dcf (8 Nov)


def test_P1_dealers_are_named_and_counted_as_the_dealers_tab_lists_them(targets):
    """Live: 50 dealers vs 52 tab labels, 6 named otherwise. Two dealer targets on the ledgers of one customer
    ("X (A/C I)", "X (A/C III)") were one row under the marker-less name; the tab lists each by its own label."""
    from app.services.sales import target_service
    from tests.test_dealer_targets_api import _customer, _dealer_body, _product_id, _sale

    db, client, t = targets
    company_id = _dealer_account(db, t).company_id
    pid = _product_id(db, company_id)
    for ledger, sold in (("ZZT LEDGER CO (A/C I)", 61000), ("ZZT LEDGER CO (A/C III)", 80000)):
        c = _customer(db, company_id, ledger, level=1)
        _sale(db, company_id, c, str(sold), date(2026, 8, 3), product_id=pid)
        assert client.post(BASE, json=_dealer_body([c], tiers=[
            {"period_start": "2026-07-01", "threshold": 60000, "rate": 5}])).status_code == 201
    out = run(db, {"entity": ENTITY, "period": "2026", "fields": ["payout"],
                   "filters": [{"field": "owner_kind", "op": "eq", "value": "dealer"}]})
    tab = target_service.list_all_targets(db, subject="dealer")["rows"]
    assert sorted(r["label"] for r in out["rows"]) == sorted(r["subject_label"] for r in tab)
    assert len(out["rows"]) == len(tab) == 3
    assert "ZZT LEDGER CO (A/C III)" in [r["label"] for r in out["rows"]]


def test_P2_view_own_never_sees_a_dealer_even_one_whose_accounts_it_owns(targets, grant, monkeypatch):
    """Q4 (a). Not runnable live (no dev role holds view_own): held here."""
    from app.services import own_scope

    db, _c, t = targets
    _dealer_account(db, t).sales_agent_id = t["a"].id
    db.flush()
    grant("sales.targets.view_own")
    monkeypatch.setattr(own_scope, "me", lambda db, user_id: own_scope.Me(str(user_id), None, (t["a"].id,)))
    out = run(db, {"entity": ENTITY, "period": "2026", "fields": ["owner_kind", "payout"]})
    assert [(r["label"], r["owner_kind"]) for r in out["rows"]] == [(_agent_label(t, "a"), "agent")]
    assert out["totals"]["payout"] == 540.0
    by_dealer = run(db, {"entity": ENTITY, "period": "2026", "filters": [
        {"field": "agent", "op": "eq", "value": "Agent A"}, {"field": "owner_kind", "op": "eq", "value": "dealer"}]})
    assert by_dealer["rows"] == [] and "not visible to you" in by_dealer["scope_note"]


# ------------------------------------------------------------------ owner 8 Nov ~11:15 MYT


def test_D1_same_name_dealer_rows_carry_the_account_payouts_and_target_no_as_the_dealers_tab(targets):
    """Owner (a): SK ONE STOP HOME CENTRE shown 3 times; each row says its accounts ('A/C I') with each one's own
    payout (lane TARGET-PER-ACCOUNT-PAYOUT) and its TGT number, row for row with the Dealers tab, in the default
    columns."""
    from app.services.sales import target_service
    from tests.test_dealer_targets_api import _customer, _dealer_body, _product_id, _sale

    db, client, t = targets
    company_id = _dealer_account(db, t).company_id
    pid = _product_id(db, company_id)
    group = [_customer(db, company_id, "ZZT SAME NAME", level=level) for level in (1, 3)]
    for c, sold in zip(group, (61000, 80000)):
        _sale(db, company_id, c, str(sold), date(2026, 8, 3), product_id=pid)
        assert client.post(BASE, json=_dealer_body([c], tiers=[
            {"period_start": "2026-07-01", "threshold": 60000, "rate": 5}])).status_code == 201
    out = run(db, {"entity": ENTITY, "period": "2026", "filters": [{"field": "owner_kind", "op": "eq", "value": "dealer"}]})
    assert {"target_no", "account_payouts"} <= {c["key"] for c in out["columns"]}
    tab = target_service.list_all_targets(db, subject="dealer")["rows"]
    assert sorted((r["label"], r["target_no"]) for r in out["rows"]) == sorted(
        (r["subject_label"], r["target_no"]) for r in tab
    )
    same = sorted((r["account_payouts"], r["payout"]) for r in out["rows"] if r["label"] == "ZZT SAME NAME")
    assert same == [("A/C I 3,050.00", 3050.0), ("A/C III 4,000.00", 4000.0)]


def test_D2_an_unasked_whole_table_after_a_named_empty_query_is_not_shown():
    """Live Q6 run: 'payout to fullshun' matched nothing, then the reply appended the whole summary table."""
    from app.services.chatbot.agent.query_tools import shape_reply

    ledger = {
        "q1": {"name": "crm_query", "status": "ok", "args": {"entity": ENTITY, "agent": "fullshun"},
               "data": {"entity": ENTITY, "rows": [], "total": 0}, "display": None},
        "q2": {"name": "crm_query", "status": "ok", "args": {"entity": ENTITY},
               "data": {"entity": ENTITY, "shown_to_user": True, "total": 40}, "display": "WHOLE TABLE"},
    }
    text = shape_reply("No commission payout for fullshun this year.", ledger, user_text="payout to fullshun")
    assert "WHOLE TABLE" not in text and text.startswith("No commission payout for fullshun")
    # A table that was asked for (a named query that found rows) still shows.
    ledger["q1"]["data"] = {"entity": ENTITY, "rows": [{"id": "1"}], "total": 1}
    assert "WHOLE TABLE" in shape_reply("Payout per dealer.", ledger, user_text="payout to fullshun")


# ------------------------------------------------------------------ crew live round 4 on 73403177 (8 Nov)


def test_G1_a_regroup_by_dealer_still_returns_the_per_row_table_with_tgt_and_account(dealers):
    """O2 run 3: the model grouped by dealer name, 52 rows without TGT / account columns and no 'Top N of M'."""
    db, _c, _t = dealers
    for spec in ({"group_by": ["owner"], "aggregates": [{"fn": "sum", "field": "payout"}]},
                 {"group_by": [{"field": "owner"}, "account_payouts"]},
                 {"aggregates": [{"fn": "sum", "field": "payout"}]}):
        out = run(db, {"entity": ENTITY, **DEALERS_YEAR, **spec, "limit": 2})
        assert "groups" not in out, spec
        assert {"target_no", "account_payouts", "payout"} <= {c["key"] for c in out["columns"]}
        assert [r["payout"] for r in out["rows"]] == [5000.0, 4000.0]
        assert out["totals"]["payout"] == 15550.0 and out["ranked_by"] == "Commission payout"
    # A real grouping (per kind) is still a grouping.
    kinds = run(db, {"entity": ENTITY, "period": "2026", "group_by": ["owner_kind"], "aggregates": [{"fn": "sum", "field": "payout"}]})
    assert "groups" in kinds


def test_G1b_a_two_row_payout_table_is_code_rendered_and_survives_the_models_own_table():
    """Q2 run 1: the right call came back but the answer was the total only; the table must be passed through."""
    from app.services.chatbot.agent.query_tools import as_card, shape_reply

    data = {"entity": ENTITY, "columns": [{"key": "label", "label": "x"}, {"key": "target_no", "label": "Target"},
                                          {"key": "account_payouts", "label": "Payout account"},
                                          {"key": "payout", "label": "Commission payout"}],
            "rows": [{"id": "1", "label": "ZZT SK", "target_no": "TGT-000065", "account_payouts": "A/C I", "payout": 170643.26},
                     {"id": "2", "label": "ZZT SK", "target_no": "TGT-000064", "account_payouts": "A/C I", "payout": 11769.92}],
            "total": 2, "truncated": False, "totals": {"payout": 182413.18}}
    card = as_card(data, panel=True)
    assert card is not None and "TGT-000065" in card.display and "TGT-000064" in card.display
    ledger = {"q1": {"name": "crm_query", "status": "ok", "args": {"entity": ENTITY}, "data": card.data,
                     "display": card.display}}
    regrouped = "Total dealer payout is RM 182,413.18.\n\n| Dealer | Payout |\n|---|---|\n| ZZT SK | 182,413.18 |"
    text = shape_reply(regrouped, ledger)
    assert text.startswith("Total dealer payout is RM 182,413.18.")
    assert "| ZZT SK | 182,413.18 |" not in text and "TGT-000064" in text and "182,413.18" in text


def test_G2_the_asking_users_own_name_is_never_the_agent_unless_the_model_says_it_is_about_them():
    """Q2 run 1: the first call filtered agent = the asking user's own name and found nothing. "my" / "for Jayson"
    is the model's `about_self`, never a word read from the message (AGENT-COMMISSION-WA, owner rule)."""
    from app.services.chatbot.agent.query_tools import strip_self_agent

    args = {"entity": ENTITY, "agent": "Jayson", "period": "2026"}
    kept, note = strip_self_agent(args, "Jayson Teh")
    assert "agent" not in kept and kept["period"] == "2026" and "your own name" in note
    filt = {"entity": ENTITY, "filters": [{"field": "owner", "op": "eq", "value": "jayson teh"},
                                          {"field": "owner_kind", "op": "eq", "value": "dealer"}]}
    kept, note = strip_self_agent(filt, "Jayson Teh")
    assert kept["filters"] == [{"field": "owner_kind", "op": "eq", "value": "dealer"}] and note
    mine = {**args, "about_self": True}
    kept, note = strip_self_agent(mine, "Jayson Teh")
    assert kept == mine and note is None
    kept, note = strip_self_agent({"entity": ENTITY, "agent": "Agent B"}, "Jayson Teh")
    assert kept["agent"] == "Agent B" and note is None


def test_G3_q6_reply_tidy_range_not_year_one_period_note_no_unasked_notes():
    from app.services.chatbot.agent.query_tools import shape_reply

    year = "Period 01/01/2026 to 31/12/2026"
    ledger = {
        "q1": {"name": "crm_query", "status": "ok", "args": {"entity": ENTITY, "agent": "fullshun"},
               "data": {"entity": ENTITY, "rows": [], "total": 0, "period_display": year,
                        "scope_note": "No period named: this year, 01/01/2026 to 31/12/2026."}, "display": None},
        "q2": {"name": "crm_query", "status": "ok", "args": {"entity": ENTITY},
               "data": {"entity": ENTITY, "rows": [{"id": "1", "label": "AA - Agent A"}], "total": 1, "period_display": year,
                        "scope_note": "No period named: this year, 01/01/2026 to 31/12/2026. "
                                      "No commission is set on the targets of AA - Agent A."}, "display": None},
    }
    text = shape_reply("No commission payout was found for fullshun for 2026.", ledger, user_text="commission payout to fullshun")
    assert text.splitlines()[0] == "No commission payout was found for fullshun from 01/01/2026 to 31/12/2026."
    assert text.count("No period named") == 1
    assert "Agent A" not in text


# ------------------------------------------------------------------ crew live round 5 on 828c88de (8 Nov)


def test_H1_tgt_and_account_payouts_are_shown_whatever_columns_the_model_asks_for(targets):
    """Q2 run 3: the model passed its own column list without TGT / account and SK ONE STOP's rows looked identical."""
    from tests.test_dealer_targets_api import _customer, _dealer_body, _product_id, _sale

    db, client, t = targets
    company_id = _dealer_account(db, t).company_id
    pid = _product_id(db, company_id)
    for level, sold in ((1, 61000), (1, 80000)):
        c = _customer(db, company_id, "ZZT TWIN", level=level)
        _sale(db, company_id, c, str(sold), date(2026, 8, 3), product_id=pid)
        assert client.post(BASE, json=_dealer_body([c], tiers=[
            {"period_start": "2026-07-01", "threshold": 60000, "rate": 5}])).status_code == 201
    for fields in (["payout"], ["owner_kind", "achieved_pct", "payout"],
                   ["targets", "target_value", "achieved_value", "achieved_pct", "commission", "bonus", "payout", "kinds"]):
        out = run(db, {"entity": ENTITY, "agent": "ZZT TWIN", "period": "2026", "fields": fields})
        keys = [c["key"] for c in out["columns"]]
        assert keys[:3] == ["label", "target_no", "account_payouts"], fields
        assert "payout" in keys and "columns_dropped" not in out
        twins = [(r["target_no"], r["account_payouts"]) for r in out["rows"]]
        assert len(twins) == 2 and len(set(twins)) == 2 and all(a.startswith("A/C I ") for _n, a in twins)


# ------------------------------------------------------------------ crew live round 6 on 3f9edf78 (8 Nov)


def test_K1_an_empty_first_call_on_the_askers_name_never_hides_the_second_calls_table():
    """Q2 run 1 (turn f7be4cd6): call 1 filtered agent = the asker and found nothing, call 2 returned the per-dealer
    table, the reply was the total only. The user never named the asker: the table must show."""
    from app.services.chatbot.agent.query_tools import shape_reply

    from app.services.chatbot.agent.query_tools import strip_self_agent

    # As the loop records it: the asker's name is stripped before the call runs (no text is read for it).
    first, _note = strip_self_agent({"entity": ENTITY, "agent": "Jayson"}, "Jayson Teh")
    ledger = {
        "q1": {"name": "crm_query", "status": "ok", "args": first,
               "data": {"entity": ENTITY, "rows": [], "total": 0}, "display": None},
        "q2": {"name": "crm_query", "status": "ok",
               "args": {"entity": ENTITY, "filters": [{"field": "owner_kind", "op": "eq", "value": "dealer"}]},
               "data": {"entity": ENTITY, "shown_to_user": True, "total": 88}, "display": "DEALER TABLE"},
    }
    text = shape_reply("Total dealer payout this year is RM 478,755.53.", ledger,
                       user_text="commission payout per dealer this year")
    assert "DEALER TABLE" in text and text.startswith("Total dealer payout")


def test_K1b_the_askers_name_in_any_order_or_part_is_stripped_unless_about_self():
    from app.services.chatbot.agent.query_tools import strip_self_agent

    for said_agent in ("Teh", "teh jayson", "Jayson Teh", "JAYSON"):
        kept, note = strip_self_agent({"entity": ENTITY, "agent": said_agent}, "Jayson Teh")
        assert "agent" not in kept and note, said_agent
    # "saya punya commission": the model's about_self, in any language.
    kept, note = strip_self_agent({"entity": ENTITY, "agent": "Teh", "about_self": True}, "Jayson Teh")
    assert kept["agent"] == "Teh" and note is None
    # Another person who only shares a word is not the asker.
    kept, _ = strip_self_agent({"entity": ENTITY, "agent": "Jayson Lim"}, "Jayson Teh")
    assert kept["agent"] == "Jayson Lim"


def test_K2_fifty_long_rows_are_all_in_the_table_plus_totals_never_49():
    """'Top 49 of 88': the result was cut to fit the model's size cap before the table was drawn."""
    from app.services.chatbot.agent.query_tools import query_result

    columns = [{"key": "label", "label": "Dealer"}, {"key": "target_no", "label": "Target"},
               {"key": "account_payouts", "label": "Payout account"}, {"key": "payout", "label": "Commission payout"}]
    rows = [{"id": str(i), "label": f"ZZT A VERY LONG DEALER NAME SDN BHD NUMBER {i:03d} " + "X" * 120,
             "target_no": f"TGT-{i:06d}", "account_payouts": "A/C I", "payout": float(1000 - i)} for i in range(50)]
    data = {"entity": ENTITY, "columns": columns, "rows": rows, "total": 88, "truncated": True,
            "ranked_by": "Commission payout", "totals": {"payout": 99999.0}}
    out = query_result(data, panel=True)
    body = [line for line in out.display.splitlines() if line.startswith("| ZZT")]
    assert len(body) == 50
    assert "Top 50 of 88 by commission payout." in out.display and "| Total |" in out.display
