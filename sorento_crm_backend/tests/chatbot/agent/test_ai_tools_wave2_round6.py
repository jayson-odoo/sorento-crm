"""AI-TOOLS-WAVE2 crew pass on 0463b805 (5 Nov): `agent_target_summary`, one deterministic row per owner per period,
answering "payout per agent", "commission for Agent X last month" and "who is below target" in ONE query, and the
Targets screen's own below-target reading. Entity output only, no LLM.

Fixture (`test_ai_tools_wave2.targets`, today 20 Oct 2026): agents A and B, monthly agent targets Jul to Dec of
10,000 with tiers 80% at 2% and 100% at 3%; A sells 12,000 in Sep and 9,000 in Oct, B 5,000 in Sep and 9,000 in Oct;
a quarterly dealer target (no figure, tiers at 60,000) whose one account sold 70,000 in Aug.
"""
from __future__ import annotations

import uuid

import pytest

from tests.chatbot.agent.test_ai_tools_wave2 import SEP, grant, run, targets  # noqa: F401  (fixtures)
from tests.test_sales_targets_s1 import api, world  # noqa: F401  (fixtures)

QUARTER = {"field": "period", "op": "between", "value": ["01/10/2026", "31/12/2026"]}
ENTITY = "agent_target_summary"


def _owner(t, key):
    return f"{t[key].sales_agent} - Agent {key.upper()}"


def test_S1_payout_per_agent_and_dealer_this_year_ranked_with_totals(targets):
    """AGENT-COMMISSION-ALL (owner 8 Nov): a dealer is its own row; crew live x3: no period named is this year and
    rows rank by payout, highest first."""
    db, _c, t = targets
    out = run(db, {"entity": ENTITY})
    assert [r["label"] for r in out["rows"]] == ["ZZT DEALER W2", _owner(t, "a"), _owner(t, "b")]
    a = out["rows"][1]
    assert a["targets"] == 1 and a["target_value"] == 60000.0 and a["achieved_value"] == 21000.0
    assert a["achieved_pct"] == 35.0 and a["payout"] == 540.0
    assert out["totals"] == {"targets": 3, "payout": 3500.0 + 540.0 + 180.0}
    assert out["period_display"] == "Period 01/01/2026 to 31/12/2026"
    # The dealer target has no figure (0): its sales stay out of target and achieved, its payout counts.
    assert out["scope_note"] == f"No period named: this year. Left out of target and achieved (a target of 0): {t['dealer']['target_no']}."


def test_S1b_a_wider_window_is_still_one_row_per_agent(targets):
    db, _c, t = targets
    out = run(db, {"entity": ENTITY, "filters": [{"field": "period", "op": "between", "value": ["01/07/2026", "31/12/2026"]},
                                                 {"field": "owner_kind", "op": "eq", "value": "agent"}],
                   "fields": ["periods", "targets", "target_value", "achieved_value", "achieved_pct", "payout"]})
    a, b = out["rows"]
    assert a["label"] == _owner(t, "a") and a["periods"] == 6 and a["targets"] == 1
    assert (a["target_value"], a["achieved_value"], a["achieved_pct"], a["payout"]) == (60000.0, 21000.0, 35.0, 540.0)
    assert b["payout"] == 180.0


def test_S2_commission_for_agent_b_last_month_by_name_one_row_period_start_sets_the_window(targets):
    """The crew's first call used `period_start` and was refused; any date field now sets the window."""
    db, _c, t = targets
    out = run(db, {"entity": ENTITY, "filters": [{"field": "owner", "op": "contains", "value": "agent b"},
                                                 {"field": "period_start", "op": "between", "value": SEP}],
                   "fields": ["commission", "bonus", "payout", "achieved_pct"]})
    [row] = out["rows"]
    assert row["label"] == _owner(t, "b")
    assert row["achieved_pct"] == 50.0 and row["payout"] == 0.0 and row["commission"] == 0.0
    assert out["period_display"] == "Period 01/09/2026 to 30/09/2026"


def test_S3_below_target_is_the_targets_screens_count_and_says_its_definition(targets):
    """`target_list` is the Targets screens' own rows (`list_all_targets`); not reached = % missing or under 100."""
    from app.services.sales import target_service

    db, _c, t = targets
    out = run(db, {"entity": "target_list", "filters": [{"field": "reached", "op": "eq", "value": False}]})
    screen = [r for subject in ("agent", "team", "dealer") for r in target_service.list_all_targets(db, subject=subject)["rows"]
              if not (r["achieved_pct"] is not None and r["achieved_pct"] >= 100)]
    assert out["total"] == len(screen) == 3
    assert {r["label"].split(":")[0] for r in out["rows"]} == {t["ta"]["target_no"], t["tb"]["target_no"], t["dealer"]["target_no"]}
    assert out["scope_note"].startswith("Not reached = achieved under 100% of target, as the Targets screen shows it.")
    a = next(r for r in out["rows"] if r["label"].startswith(t["ta"]["target_no"]))
    assert (a["target_value"], a["achieved_value"], a["achieved_pct"]) == (60000.0, 21000.0, 35.0)


def test_S3b_target_list_window_is_the_targets_date_range(targets):
    db, _c, t = targets
    out = run(db, {"entity": "target_list", "filters": [{"field": "period", "op": "between", "value": ["01/01/2027", "31/03/2027"]}]})
    assert out["rows"] == []


def test_S4_the_screens_reading_a_target_without_a_percent_is_below():
    """`SalesTargetsView.tsx`: green ("reached") only for `pct !== null && pct >= 100`. A target of 0 or a points
    target without a ratio has no % and reads as not reached; 99.95 rounds to 100.0 on the page and is reached."""
    from app.services.assistant_registry.sales import _below

    assert _below(None) is True
    assert _below(99.9) is True
    assert _below(100.0) is False and _below(120.0) is False


def test_S5_a_dealer_whose_accounts_one_agent_owns_stays_the_dealers(targets):
    """AGENT-COMMISSION-ALL Q1 (a), owner 8 Nov: replaces the 5 Nov rule that folded such a dealer into the agent."""
    from app.models.order import Customer
    from app.models.sales import SalesTargetAccount

    db, _c, t = targets
    customer_id = db.query(SalesTargetAccount.customer_id).filter(SalesTargetAccount.target_id == t["dealer"]["id"]).scalar()
    db.get(Customer, customer_id).sales_agent_id = t["a"].id
    db.flush()
    out = run(db, {"entity": ENTITY, "filters": [{"field": "period", "op": "between", "value": ["01/07/2026", "30/09/2026"]},
                                                 {"field": "owner", "op": "contains", "value": "agent a"}],
                   "fields": ["kinds", "targets", "payout"]})
    [row] = out["rows"]
    assert row["kinds"] == "agent" and row["targets"] == 1
    assert row["payout"] == 360.0  # A's own September only; the dealer's 3,500 is the dealer's row


def test_S6_nothing_matched_is_said_never_padded(targets):
    db, _c, t = targets
    out = run(db, {"entity": ENTITY, "filters": [{"field": "owner", "op": "contains", "value": "Nobody"}]})
    assert out["rows"] == [] and "do not show or total other records" in out["instruction"]
    assert _owner(t, "a") in out["values_in_window"]["owner"]


def test_S7_follows_the_targets_slugs_and_the_own_rule(targets, grant):
    from app.services.assistant_registry import query

    db, _c, _t = targets
    grant("sales.reports.view")
    for entity in (ENTITY, "target_list"):
        with pytest.raises(query.QueryRefused) as info:
            run(db, {"entity": entity})
        assert info.value.code == "no_access"
    grant("sales.targets.view_own")
    # A user with no linked agent: nothing of anyone's.
    assert run(db, {"entity": ENTITY})["rows"] == []
    assert run(db, {"entity": "target_list"})["rows"] == []


def test_S8_the_index_offers_the_two_target_entities_only():
    from app.services.chatbot.agent import query_tools

    index = f"\n{query_tools.entity_index()}"
    assert "\nagent_target_summary (" in index and "\ntarget_list (" in index
    assert "\nsales_target (" not in index
