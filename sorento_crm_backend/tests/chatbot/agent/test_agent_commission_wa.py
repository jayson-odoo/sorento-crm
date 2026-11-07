"""AGENT-COMMISSION-WA (wave W-A of `PLAN-agent-commission-all-08nov.md`): "how far is Agent A / dealer D1 / Team T1
from the next tier, and what would it pay?" answered on the `agent_target_summary` rows, from the target page's own
tier ladder and the one commission engine (`target_service.period_figures`). Entity output only, no LLM.

Plan: `documentation/plans/sales/PLAN-agent-commission-wa-08nov.md`. Fixture (`test_ai_tools_wave2.targets`, today
20 Oct 2026): agents A and B on monthly 10,000 targets (80% at 2%, 100% at 3%, retroactive); A 12,000 in Sep, B 5,000
in Sep, both 9,000 in Oct; a quarterly dealer "ZZT DEALER W2" (one account) at 60,000 for 5%, 70,000 sold in Aug.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from tests.chatbot.agent.test_agent_commission_all import _agent_label, team  # noqa: F401  (fixtures)
from tests.chatbot.agent.test_ai_tools_wave2 import grant, run, targets  # noqa: F401  (fixtures)
from tests.test_dealer_targets_api import _customer, _dealer_body, _product_id, _sale
from tests.test_sales_targets_s1 import BASE, _so_line, api, world  # noqa: F401  (fixtures)

ENTITY = "agent_target_summary"
NEXT = ["next_tier", "next_tier_at", "to_next_tier", "next_tier_payout", "next_tier_gain", "payout"]
OCT = "2026-10"
SEP = "2026-09"


def _page_period(db, target_id, start):
    from app.services.sales import target_service

    target = target_service.get_target_or_404(db, target_id)
    return next(p for p in target_service.target_detail(db, target)["periods"] if p["period_start"] == start)


def _company(db, t):
    from app.models.sales import SalesTarget

    return db.get(SalesTarget, t["ta"]["id"]).company_id


def _one(db, said, period, fields=NEXT):
    out = run(db, {"entity": ENTITY, "agent": said, "period": period, "fields": fields})
    [row] = out["rows"]
    return row, out


# ------------------------------------------------------------------ agents


def test_W1_agent_a_october_is_1000_from_tier_2_which_would_pay_300(targets):
    db, _c, t = targets
    row, out = _one(db, "Agent A", OCT)
    assert row["label"] == _agent_label(t, "a")
    assert (row["next_tier"], row["next_tier_at"], row["to_next_tier"]) == (2, 10000.0, 1000.0)
    # Tier 2 is 3% retroactive on 10,000 = 300; today it pays tier 1, 2% of 9,000 = 180.
    assert (row["next_tier_payout"], row["next_tier_gain"], row["payout"]) == (300.0, 120.0, 180.0)
    # The rung is the target page's own ladder.
    page = _page_period(db, t["ta"]["id"], date(2026, 10, 1))
    rung = page["tier_ladder"][1]
    assert rung["tier"] == 2 and float(rung["threshold_rm"]) == row["next_tier_at"]
    assert "instruction" not in out


def test_W2_agent_b_september_below_every_tier_is_3000_from_tier_1(targets):
    db, _c, _t = targets
    row, _out = _one(db, "Agent B", SEP)
    assert (row["next_tier"], row["next_tier_at"], row["to_next_tier"]) == (1, 8000.0, 3000.0)
    assert (row["next_tier_payout"], row["next_tier_gain"]) == (160.0, 160.0)


def test_W3_at_the_top_tier_there_is_no_next_tier_and_the_answer_says_so(targets):
    db, _c, t = targets
    row, out = _one(db, "Agent A", SEP)
    assert row["next_tier"] is None and row["to_next_tier"] is None and row["next_tier_payout"] is None
    assert row["payout"] == 360.0
    assert "top tier" in out["scope_note"] and t["ta"]["target_no"] in out["scope_note"]


def test_W4_what_it_would_pay_is_what_the_page_pays_once_the_sale_lands(targets):
    """Kill test for "no new calculation": the would-pay figure is the engine's, so after the missing 1,000 is sold
    the target page pays exactly what the answer said."""
    db, _c, t = targets
    row, _out = _one(db, "Agent A", OCT)
    company_id = _company(db, t)
    _so_line(db, company_id, agent_id=t["a"].id, order_date=date(2026, 10, 6), line_total=Decimal("1000"),
             product_id=_product_id(db, company_id))
    page = _page_period(db, t["ta"]["id"], date(2026, 10, 1))
    assert page["tier_reached"] == row["next_tier"]
    assert (page["commission_earned"] or 0) + (page["bonus_earned"] or 0) == row["next_tier_payout"]
    after, _ = _one(db, "Agent A", OCT)
    assert after["payout"] == row["next_tier_payout"] and after["next_tier"] is None


def test_W5_two_live_targets_leave_the_row_empty_and_list_each_in_the_note(targets):
    """Q2 (a): a sum of two distances is not a distance; each target's next tier is a line of the note."""
    db, client, t = targets
    res = client.post(BASE, json={
        "subject_kind": "agent", "sales_agent_id": t["a"].id, "name": "ZZT A stretch", "metric": "amount",
        "basis": "ordered", "product_scope": "all", "start_date": "2026-10-01", "end_date": "2026-10-31",
        "target_value": 20000, "commission_method": "retroactive", "tiers": [{"from_pct": 50, "rate": 1}],
    })
    assert res.status_code == 201, res.text
    second = res.json()
    row, out = _one(db, "Agent A", OCT)
    assert row["next_tier"] is None and row["to_next_tier"] is None and row["next_tier_payout"] is None
    note = out["scope_note"]
    assert t["ta"]["target_no"] in note and "RM 1,000.00 to go" in note and "would pay RM 300.00" in note
    assert second["target_no"] in note and "RM 1,000.00 to go" in note and "would pay RM 100.00" in note


# ------------------------------------------------------------------ dealers and teams


def test_W6_dealer_by_name_this_quarter_is_60000_from_its_tier(targets):
    db, _c, _t = targets
    row, _out = _one(db, "ZZT DEALER W2", ["01/10/2026", "31/12/2026"])
    assert (row["next_tier"], row["next_tier_at"], row["to_next_tier"]) == (1, 60000.0, 60000.0)
    assert (row["next_tier_payout"], row["next_tier_gain"]) == (3000.0, 3000.0)


def test_W7_dealer_q3_already_reached_its_only_tier(targets):
    db, _c, _t = targets
    row, out = _one(db, "ZZT DEALER W2", ["01/07/2026", "30/09/2026"])
    assert row["next_tier"] is None and row["payout"] == 3500.0
    assert "top tier" in out["scope_note"]


def test_W8_team_at_its_only_tier_has_no_next_tier(team):
    db, _c, _t = team
    row, out = _one(db, "Team ZZT North", OCT)
    assert row["next_tier"] is None and row["payout"] == 180.0
    assert "top tier" in out["scope_note"]


@pytest.fixture
def two_accounts(targets):
    """Dealer "ZZT MIX" with two accounts, a tier at 100,000 each quarter paying A/C 1 2% and A/C 2 4%. Q4 so far:
    A/C 1 30,000, A/C 2 10,000. Q3: nothing."""
    db, client, t = targets
    company_id = _company(db, t)
    pid = _product_id(db, company_id)
    a1, a2 = _customer(db, company_id, "ZZT MIX ONE"), _customer(db, company_id, "ZZT MIX TWO")
    _sale(db, company_id, a1, "30000", date(2026, 10, 3), product_id=pid)
    _sale(db, company_id, a2, "10000", date(2026, 10, 4), product_id=pid)
    rates = [{"customer_id": a1.id, "rate": 2}, {"customer_id": a2.id, "rate": 4}]
    res = client.post(BASE, json={**_dealer_body([a1, a2], payout_customer_id=a1.id, tiers=[
        {"period_start": "2026-07-01", "threshold": 100000, "account_rates": rates},
        {"period_start": "2026-10-01", "threshold": 100000, "account_rates": rates},
    ]), "name": "ZZT MIX 2026"})
    assert res.status_code == 201, res.text
    return db, client, {**t, "mix": res.json(), "a1": a1}


def test_W9_per_account_rates_pay_the_rest_in_the_mix_sold_so_far(two_accounts):
    """Q1 (a): 60,000 to go, sold 3:1 so far -> 75,000 at 2% + 25,000 at 4% = 2,500; the answer says the mix."""
    db, _c, t = two_accounts
    row, out = _one(db, t["a1"].customer_code, ["01/10/2026", "31/12/2026"])
    assert (row["to_next_tier"], row["next_tier_payout"]) == (60000.0, 2500.0)
    assert "mix sold so far" in out["scope_note"]


def test_W10_per_account_rates_with_nothing_sold_split_evenly(two_accounts):
    db, _c, t = two_accounts
    row, out = _one(db, t["a1"].customer_code, ["01/07/2026", "30/09/2026"])
    # 50,000 at 2% + 50,000 at 4%.
    assert (row["to_next_tier"], row["next_tier_payout"]) == (100000.0, 3000.0)
    assert "split evenly" in out["scope_note"]


# ------------------------------------------------------------------ permissions, index, per period


def test_W11_view_own_gets_its_own_agents_next_tier_and_no_dealer(targets, grant, monkeypatch):
    from app.services import own_scope

    db, _c, t = targets
    grant("sales.targets.view_own")
    monkeypatch.setattr(own_scope, "me", lambda db, user_id: own_scope.Me(str(user_id), None, (t["a"].id,)))
    row, _out = _one(db, "Agent A", OCT)
    assert row["to_next_tier"] == 1000.0
    dealer = run(db, {"entity": ENTITY, "agent": "ZZT DEALER W2", "period": ["01/10/2026", "31/12/2026"],
                      "fields": NEXT})
    assert dealer["rows"] == [] and "not visible to you" in dealer["scope_note"]


def test_W12_the_index_routes_next_tier_questions_to_the_summary():
    from app.services.chatbot.agent import query_tools

    line = next(x for x in query_tools.entity_index().splitlines() if x.startswith("agent_target_summary ("))
    assert "next tier" in line.lower()


def test_W13_the_per_period_rows_carry_the_same_next_tier(targets):
    db, _c, t = targets
    out = run(db, {"entity": "sales_target", "filters": [{"field": "agent", "op": "contains", "value": "agent a"}],
                   "period": OCT, "fields": NEXT})
    [row] = out["rows"]
    assert (row["to_next_tier"], row["next_tier_payout"], row["next_tier_gain"]) == (1000.0, 300.0, 120.0)
