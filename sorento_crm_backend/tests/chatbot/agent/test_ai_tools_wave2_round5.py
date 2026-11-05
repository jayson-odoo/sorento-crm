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


# (b) (c) (e) are `agent_target_summary` now: tests/chatbot/agent/test_ai_tools_wave2_round6.py


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
