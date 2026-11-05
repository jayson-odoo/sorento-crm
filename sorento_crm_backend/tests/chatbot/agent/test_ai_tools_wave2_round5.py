"""AI-TOOLS-WAVE2 crew pass on 74b6b751 (5 Nov): one row per agent for payout and target questions, an agent named
by name, nothing padded when nothing matches, at most 8 columns, and one sales basis per answer. No LLM; the loop
runs with a scripted model."""
from __future__ import annotations

import json
import uuid
from datetime import date

import pytest

from tests.chatbot.agent.test_ai_tools_wave2 import SEP, grant, run, targets  # noqa: F401  (fixtures)
from tests.test_sales_targets_s1 import api, world  # noqa: F401  (fixtures)

YEAR = {"field": "period", "op": "between", "value": ["01/07/2026", "31/12/2026"]}


# ------------------------------------------------------------------ (b) (c) (e) one row per agent, one query


def test_AT1_payout_per_agent_is_one_row_per_agent_dealers_left_out(targets):
    db, _c, t = targets
    out = run(db, {"entity": "agent_target", "filters": [YEAR], "fields": ["periods", "target_value", "achieved_value", "payout"],
                   "sort": [{"field": "payout", "dir": "desc"}]})
    assert [r["label"] for r in out["rows"]] == [f"{t['a'].sales_agent} - Agent A", f"{t['b'].sales_agent} - Agent B"]
    a, b = out["rows"]
    assert a["periods"] == 6 and a["target_value"] == 60000.0
    # The sum of the target page's own period figures (`sales_target`), nothing recomputed.
    per_period = run(db, {"entity": "sales_target", "filters": [YEAR, {"field": "agent", "op": "contains", "value": "agent a"}],
                          "fields": ["payout", "achieved_value"], "limit": 50})["rows"]
    assert a["payout"] == round(sum(r["payout"] or 0 for r in per_period), 2) == 360.0 + 180.0
    assert a["achieved_value"] == sum(r["achieved_value"] for r in per_period) == 21000.0
    assert b["payout"] == 180.0
    assert t["dealer"]["target_no"] not in json.dumps(out)


def test_AT2_commission_payout_for_agent_a_last_month_by_name_in_one_query(targets):
    db, _c, t = targets
    out = run(db, {"entity": "agent_target", "filters": [{"field": "agent", "op": "contains", "value": "Agent A"},
                                                          {"field": "period", "op": "between", "value": SEP}]})
    [row] = out["rows"]
    assert row["label"] == f"{t['a'].sales_agent} - Agent A"
    assert row["payout"] == 360.0 and row["achieved_pct"] == 120.0
    assert out["period_display"] == "Period 01/09/2026 to 30/09/2026"


def test_AT3_without_a_period_the_current_periods(targets):
    db, _c, _t = targets
    out = run(db, {"entity": "agent_target", "group_by": [], "fields": ["payout"]})
    assert {r["payout"] for r in out["rows"]} == {180.0}
    assert out["scope_note"] == "Periods containing today (20/10/2026)."


def test_AT4_follows_the_targets_slugs(targets, grant):
    db, _c, _t = targets
    from app.services.assistant_registry.query import QueryRefused

    grant("sales.reports.view")
    with pytest.raises(QueryRefused) as info:
        run(db, {"entity": "agent_target"})
    assert info.value.code == "no_access"


# ------------------------------------------------------------------ (c) never padded


def test_NM1_no_match_says_so_and_lists_who_exists_never_other_rows(targets):
    db, _c, t = targets
    out = run(db, {"entity": "agent_target", "filters": [{"field": "agent", "op": "contains", "value": "Nobody"}, YEAR]})
    assert out["rows"] == [] and out["total"] == 0
    assert "do not show or total other records" in out["instruction"]
    assert out["values_in_window"]["agent"] == sorted([f"{t['a'].sales_agent} - Agent A", f"{t['b'].sales_agent} - Agent B"])


# ------------------------------------------------------------------ (d) the columns asked, at most 8


def test_C1_at_most_eight_columns_the_rest_named(targets):
    db, _c, _t = targets
    asked = ["period_start", "period_end", "target_value", "achieved_value", "achieved_pct", "below_target",
             "shortfall", "tier_reached", "commission", "bonus", "payout", "team"]
    out = run(db, {"entity": "sales_target", "filters": [YEAR], "fields": asked, "limit": 1})
    keys = [c["key"] for c in out["columns"]]
    assert keys == ["label", *asked[:8]]
    assert out["columns_dropped"] == asked[8:]
    assert set(out["rows"][0]) <= {"id", "link", "label", *asked[:8]}


# ------------------------------------------------------------------ (a) one sales basis per answer


def test_SB1_the_sales_total_says_its_basis(api, grant):
    from tests.chatbot.agent.test_ai_tools_wave2 import BILLING_VIEW, SALES_REVEAL

    _client, db, _company = api
    grant(BILLING_VIEW, SALES_REVEAL)
    out = run(db, {"entity": "billing_document", "aggregates": [{"fn": "sum", "field": "sales_amount"}]})
    assert out["scope_note"].startswith("Invoiced sales (invoices + cash sales + debit notes - credit notes")


def test_SB2_money_basis_names_only_money_totals():
    from app.services.chatbot.agent.query_tools import money_basis

    assert money_basis({"entity": "billing_document", "aggregates": [{"fn": "sum", "field": "sales_amount"}]}) == "billing_document"
    assert money_basis({"entity": "order", "aggregates": [{"fn": "sum", "field": "total_amount"}]}) == "order"
    assert money_basis({"entity": "order", "aggregates": [{"fn": "count"}]}) is None
    assert money_basis({"entity": "sales_target", "aggregates": [{"fn": "sum", "field": "payout"}]}) is None


def test_SB3_a_turn_never_mixes_invoiced_and_delivery_order_totals():
    """The crew pass: an invoiced total, then a per-agent table on the DO basis. The second basis is refused."""
    import app.main  # noqa: F401
    from app.services.company_scope import register_company_scope_listeners
    from tests._pg_fixture import blank_session
    from tests.chatbot.agent import test_ai_query_reply as harness
    from tests.chatbot.agent.test_ai_query_reply import Scripted, agent_contact, answer, asks, turn

    register_company_scope_listeners()
    seen: list[list[dict]] = []

    class Recording(Scripted):
        def chat(self, messages, **kw):
            seen.append([m for m in messages if m.get("role") == "tool"])
            return super().chat(messages, **kw)

    invoiced = {"entity": "billing_document", "aggregates": [{"fn": "sum", "field": "sales_amount"}]}
    delivered = {"entity": "order", "group_by": ["agent"], "aggregates": [{"fn": "sum", "field": "total_amount"}]}
    with blank_session() as db:
        contact = agent_contact(db, "finance.billing_documents.view", "sales.reports.view", "order_management.orders.view")
        script = [asks("crm_query", invoiced, cid="c1"), asks("crm_query", delivered, cid="c2"), answer("Done.")]
        harness.Scripted, original = Recording, harness.Scripted
        try:
            turn(db, contact, script, "sales last month per agent", panel=True)
        finally:
            harness.Scripted = original
    first, second = (json.loads(m["content"]) for m in seen[-1])
    assert first["status"] == "ok"
    assert second["status"] == "denied" and "mix two bases" in second["message"]
