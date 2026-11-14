"""AI-TOOLS-WAVE2 crew pass on 69b3b479 (5 Nov): the specific panel refusal, the
trimmed default columns and the payout default window. No LLM; the loop runs with a scripted model.
(The staff proof that fixes the identity gate is tested in `tests/test_staff_read_identity.py`.)"""
from __future__ import annotations

import uuid

import pytest

from tests.chatbot.agent._ported_reads_support import panel_turn
from tests.chatbot.agent.test_ai_tools_wave2 import grant, run, targets  # noqa: F401  (fixtures)
from tests.test_sales_targets_s1 import api, world  # noqa: F401  (fixtures)


# ------------------------------------------------------------------ (1a) the refusal says what to do


def test_F1_a_panel_route_refusal_points_to_crm_query_and_does_not_forbid_it(monkeypatch):
    from app.services.chatbot.agent import tools

    with panel_turn(str(uuid.uuid4())):
        out = tools._http_failure(403, "Sales report is not enabled for your account.")
    assert out.status == "denied" and out.message == tools.PANEL_ROUTE_REFUSED
    assert "crm_query" in out.message and tools.DENIED_TAIL not in out.message

    monkeypatch.setattr(tools, "_dispatch_inner", lambda *a, **k: tools.ToolResult("denied", message=tools.PANEL_ROUTE_REFUSED))
    domains: set[str] = set()
    out = tools.dispatch(None, None, "crm_report_ask", {"basis": "invoiced"}, call=None, catalog={}, timeout=5,
                         denied_domains=domains)
    assert tools.DENIED_TAIL not in out.message
    assert domains == {"sales"}  # the report itself stays refused for the rest of the turn
    # crm_query is no data domain: it is never blocked by that memory.
    assert tools.data_domain("crm_query", {"entity": "billing_document"}) is None


def test_F2_a_contact_turns_refusal_is_unchanged():
    from app.services.chatbot.agent import tools

    out = tools._http_failure(403, "Sales report is not enabled for your account.")
    assert out.message == "Sales report is not enabled for your account."


# ------------------------------------------------------------------ (3) default columns, (5) payout default


def test_L1_rows_without_fields_show_the_entitys_list_columns(targets):
    db, _c, _t = targets
    out = run(db, {"entity": "sales_target", "filters": [{"field": "subject_kind", "op": "eq", "value": "agent"}]})
    keys = {c["key"] for c in out["columns"]}
    assert keys == {"label", "period_start", "period_end", "target_value", "achieved_value", "achieved_pct", "payout"}
    assert all(set(r) <= keys | {"id", "link"} for r in out["rows"])


def test_P1_payout_per_agent_without_a_period_is_the_current_period(targets):
    """Today is 20 Oct 2026: both agents' October period only (9,000 of 10,000 = 90%, tier 1 at 2% = 180)."""
    db, _c, t = targets
    out = run(db, {"entity": "sales_target", "group_by": ["agent"], "aggregates": [{"fn": "sum", "field": "payout"}],
                   "filters": [{"field": "subject_kind", "op": "eq", "value": "agent"}]})
    assert out["groups"] == [
        {"agent": f"{t['a'].sales_agent} - Agent A", "sum_payout": 180.0},
        {"agent": f"{t['b'].sales_agent} - Agent B", "sum_payout": 180.0},
    ]
    assert out["scope_note"] == "Periods containing today (20/10/2026)."
