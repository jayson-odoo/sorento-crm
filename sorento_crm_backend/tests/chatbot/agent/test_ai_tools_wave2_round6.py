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


def test_S1_payout_per_agent_one_row_per_agent_per_current_period_with_totals(targets):
    db, _c, t = targets
    out = run(db, {"entity": ENTITY})
    rows = {r["label"]: r for r in out["rows"]}
    assert set(rows) == {_owner(t, "a"), _owner(t, "b"), "(no single agent)"}
    a = rows[_owner(t, "a")]
    assert (a["period_start"], a["period_end"]) == ("01/10/2026", "31/10/2026")
    assert a["targets"] == 1 and a["target_value"] == 10000.0 and a["achieved_value"] == 9000.0
    assert a["achieved_pct"] == 90.0 and a["below_target"] == 1 and a["payout"] == 180.0
    assert out["totals"] == {"targets": 3, "below_target": 3, "payout": 360.0 + 0.0}
    assert out["scope_note"] == "Periods containing today (20/10/2026)."
    assert [c["key"] for c in out["columns"]] == [
        "label", "period_start", "period_end", "targets", "below_target", "target_value", "achieved_value",
        "achieved_pct", "payout"]


def test_S2_commission_for_agent_b_last_month_by_name_one_row(targets):
    db, _c, t = targets
    out = run(db, {"entity": ENTITY, "filters": [{"field": "owner", "op": "contains", "value": "agent b"},
                                                 {"field": "period", "op": "between", "value": SEP}],
                   "fields": ["commission", "bonus", "payout", "achieved_pct"]})
    [row] = out["rows"]
    assert row["label"] == _owner(t, "b")
    assert row["achieved_pct"] == 50.0 and row["payout"] == 0.0 and row["commission"] == 0.0
    assert out["period_display"] == "Period 01/09/2026 to 30/09/2026"


def test_S3_below_target_total_is_the_screens_count(targets):
    """The screen's reading (`SalesTargetsView.tsx`: reached = % shown and >= 100) over every target period of the
    quarter, from the target page itself, equals the summary's below_target total and `sales_target`'s count."""
    from app.services.sales import target_service

    db, _c, t = targets
    summary = run(db, {"entity": ENTITY, "filters": [QUARTER, {"field": "below_target", "op": "gt", "value": 0}]})
    per_period = run(db, {"entity": "sales_target", "filters": [QUARTER, {"field": "below_target", "op": "eq", "value": True}],
                          "limit": 50})
    screen = 0
    for key in ("ta", "tb", "dealer"):
        target = target_service.get_target_or_404(db, t[key]["id"])
        for p in target_service.target_detail(db, target)["periods"]:
            if p["period_end"].isoformat() >= "2026-10-01" and p["period_start"].isoformat() <= "2026-12-31":
                pct = p["achieved_pct"]
                screen += 0 if (pct is not None and pct >= 100) else 1
    assert screen == 7  # A and B: Oct (90%), Nov, Dec (0%); the dealer's Q4 (nothing sold yet)
    assert summary["totals"]["below_target"] == per_period["total"] == screen


def test_S4_the_screens_reading_a_target_without_a_percent_is_below():
    """`SalesTargetsView.tsx`: green ("reached") only for `pct !== null && pct >= 100`. A target of 0 or a points
    target without a ratio has no % and reads as not reached; 99.95 rounds to 100.0 on the page and is reached."""
    from app.services.assistant_registry.sales import _below

    assert _below(None) is True
    assert _below(99.9) is True
    assert _below(100.0) is False and _below(120.0) is False


def test_S5_a_dealer_whose_accounts_one_agent_owns_is_that_agents(targets):
    from app.models.order import Customer
    from app.models.sales import SalesTargetAccount

    db, _c, t = targets
    customer_id = db.query(SalesTargetAccount.customer_id).filter(SalesTargetAccount.target_id == t["dealer"]["id"]).scalar()
    db.get(Customer, customer_id).sales_agent_id = t["a"].id
    db.flush()
    out = run(db, {"entity": ENTITY, "filters": [{"field": "period", "op": "between", "value": ["01/07/2026", "30/09/2026"]},
                                                 {"field": "owner", "op": "contains", "value": "agent a"}],
                   "fields": ["period_start", "period_end", "kinds", "targets", "payout"]})
    by_period = {(r["period_start"], r["period_end"]): r for r in out["rows"]}
    dealer_q3 = by_period[("01/07/2026", "30/09/2026")]
    assert dealer_q3["kinds"] == "dealer" and dealer_q3["payout"] == 3500.0  # 70,000 at 5%
    assert out["totals"]["payout"] == 3500.0 + 360.0  # plus A's own September commission
    assert "(no single agent)" not in {r["label"] for r in out["rows"]}


def test_S6_nothing_matched_is_said_never_padded(targets):
    db, _c, t = targets
    out = run(db, {"entity": ENTITY, "filters": [{"field": "owner", "op": "contains", "value": "Nobody"}]})
    assert out["rows"] == [] and "do not show or total other records" in out["instruction"]
    assert _owner(t, "a") in out["values_in_window"]["owner"]


def test_S7_follows_the_targets_slugs_and_the_own_rule(targets, grant):
    from app.services.assistant_registry import query

    db, _c, _t = targets
    grant("sales.reports.view")
    with pytest.raises(query.QueryRefused) as info:
        run(db, {"entity": ENTITY})
    assert info.value.code == "no_access"
    grant("sales.targets.view_own")
    # A user with no linked agent: nothing of anyone's.
    assert run(db, {"entity": ENTITY})["rows"] == []


def test_S8_the_index_offers_only_the_summary_for_targets():
    from app.services.chatbot.agent import query_tools

    index = query_tools.entity_index()
    assert "\nagent_target_summary (" in f"\n{index}"
    assert "\nsales_target (" not in f"\n{index}"
