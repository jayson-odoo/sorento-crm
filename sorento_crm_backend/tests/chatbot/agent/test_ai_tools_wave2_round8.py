"""AI-TOOLS-WAVE2 crew pass on ffdd7f87 (round 8). Entity and loop output only, no LLM.

(a) "sales last month per agent" came back on three bases: the report's no-basis refusal told the model to call
    once per basis. Now it says invoiced, and one turn keeps one sales basis across `crm_query` AND
    `crm_report_ask`.
(c) "commission payout for <agent> last month" lost its first call to a refused `period` value ("last_month",
    "2026-10"): a date filter may name its window.
(e) "active customers of Agent B" also listed Agent B III and IV: an agent named exactly is that agent only,
    matched by the record's own agent link, as the agent's Customers tab (`Customer.sales_agent_id ==`).
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

TODAY = date(2026, 11, 7)


# ------------------------------------------------------------------ (c) named windows


@pytest.mark.parametrize("value, window", [
    ("last_month", (date(2026, 10, 1), date(2026, 10, 31))),
    ("Last month", (date(2026, 10, 1), date(2026, 10, 31))),
    ("this_month", (date(2026, 11, 1), date(2026, 11, 30))),
    ("this_quarter", (date(2026, 10, 1), date(2026, 12, 31))),
    ("last_quarter", (date(2026, 7, 1), date(2026, 9, 30))),
    ("this_year", (date(2026, 1, 1), date(2026, 12, 31))),
    ("last_year", (date(2025, 1, 1), date(2025, 12, 31))),
    ("this_week", (date(2026, 11, 2), date(2026, 11, 8))),
    ("today", (TODAY, TODAY)),
    ("2026-02", (date(2026, 2, 1), date(2026, 2, 28))),
    ("10/2026", (date(2026, 10, 1), date(2026, 10, 31))),
    ("Q3 2026", (date(2026, 7, 1), date(2026, 9, 30))),
    ("2026-q4", (date(2026, 10, 1), date(2026, 12, 31))),
    ("2025", (date(2025, 1, 1), date(2025, 12, 31))),
    (2025, (date(2025, 1, 1), date(2025, 12, 31))),
])
def test_W1_a_window_name_is_its_first_and_last_day(value, window):
    from app.services.assistant_registry.query import named_window

    assert named_window(value, TODAY) == window


@pytest.mark.parametrize("value", ["2026-10-05", "05/10/2026", "2026-13", "someday", "", None, True, 3.5])
def test_W2_anything_else_is_not_a_window_name(value):
    from app.services.assistant_registry.query import named_window

    assert named_window(value, TODAY) is None


def test_W3_a_last_quarter_in_january_is_last_years_q4():
    from app.services.assistant_registry.query import named_window

    assert named_window("last_quarter", date(2027, 1, 15)) == (date(2026, 10, 1), date(2026, 12, 31))
    assert named_window("last_month", date(2027, 1, 15)) == (date(2026, 12, 1), date(2026, 12, 31))


def test_W4_expand_window_per_op():
    from app.services.assistant_registry.query import expand_window

    f = lambda op, value: {"field": "doc_date", "op": op, "value": value}  # noqa: E731
    assert expand_window(f("eq", "last_month"), TODAY) == f("between", ["2026-10-01", "2026-10-31"])
    assert expand_window(f("gte", "2026-07"), TODAY) == f("gte", "2026-07-01")
    assert expand_window(f("lte", "2026-07"), TODAY) == f("lte", "2026-07-31")
    assert expand_window(f("lt", "2026-07"), TODAY) == f("lt", "2026-07-01")
    assert expand_window(f("gt", "2026-07"), TODAY) == f("gt", "2026-07-31")
    assert expand_window(f("between", ["2026-07", "Q3 2026"]), TODAY) == f("between", ["2026-07-01", "2026-09-30"])
    assert expand_window(f("between", ["01/07/2026", "last_month"]), TODAY) == f("between", ["01/07/2026", "2026-10-31"])
    plain = f("eq", "05/10/2026")
    assert expand_window(plain, TODAY) is plain


def test_W5_commission_payout_for_agent_b_last_month_in_one_query(targets, monkeypatch):
    """The crew's refused first calls: `period eq last_month` and `period eq 2026-09` now answer."""
    from app.services.assistant_registry import computed, query

    monkeypatch.setattr(computed, "_today", lambda: date(2026, 10, 20))
    monkeypatch.setattr(query, "local_today", lambda: date(2026, 10, 20))
    db, _c, t = targets
    for value in ("last_month", "2026-09", "09/2026"):
        out = run(db, {"entity": "agent_target_summary", "filters": [
            {"field": "owner", "op": "eq", "value": "Agent B"}, {"field": "period", "op": "eq", "value": value},
        ], "fields": ["achieved_pct", "payout"]})
        [row] = out["rows"]
        assert row["label"] == f"{t['b'].sales_agent} - Agent B", value
        assert (row["achieved_pct"], row["payout"]) == (50.0, 0.0)
        assert out["period_display"] == "Period 01/09/2026 to 30/09/2026"


def test_W6_since_a_month_runs_to_today(targets, monkeypatch):
    from app.services.assistant_registry import computed, query

    monkeypatch.setattr(computed, "_today", lambda: date(2026, 10, 20))
    monkeypatch.setattr(query, "local_today", lambda: date(2026, 10, 20))
    db, _c, t = targets
    out = run(db, {"entity": "agent_target_summary", "filters": [
        {"field": "owner", "op": "eq", "value": "agent a"}, {"field": "period", "op": "gte", "value": "2026-09"},
    ], "fields": ["periods", "payout"]})
    [row] = out["rows"]
    assert row["periods"] == 2 and row["payout"] == 360.0 + 180.0
    assert out["period_display"] == "Period 01/09/2026 to 20/10/2026"


def test_W7_billing_document_doc_date_last_month(api, grant, monkeypatch):
    from app.services.assistant_registry import query

    monkeypatch.setattr(query, "local_today", lambda: date(2026, 11, 7))
    _client, db, company_id = api
    grant(BILLING_VIEW, SALES_REVEAL)
    a = _agent(db, "WS", "Window Sales")
    cust = _customer(db, company_id, "ZZT W7 CUST")
    _doc(db, company_id, "invoice", "1000", date(2026, 10, 31), agent=a, customer=cust)
    _doc(db, company_id, "invoice", "500", date(2026, 11, 1), agent=a, customer=cust)
    _doc(db, company_id, "invoice", "250", date(2026, 9, 30), agent=a, customer=cust)
    out = run(db, {"entity": "billing_document", "filters": [
        {"field": "doc_date", "op": "eq", "value": "last_month"}, {"field": "agent", "op": "eq", "value": a.sales_agent},
    ], "aggregates": [{"fn": "sum", "field": "sales_amount"}]})
    assert out["groups"][0]["sum_sales_amount"] == 1000.0
    assert out["period_display"] == "Document date 01/10/2026 to 31/10/2026"


# ------------------------------------------------------------------ (e) one agent, by its link


@pytest.fixture
def owner_records(api, grant):
    """Agent B with two more owner records whose names contain "Agent B" (III and IV), each with customers."""
    _client, db, company_id = api
    grant(CUSTOMERS_VIEW)
    b, b3, b4 = _agent(db, "B", "ZZT Agent B"), _agent(db, "B3", "ZZT Agent B III"), _agent(db, "B4", "ZZT Agent B IV")
    made = {}
    for agent, active, inactive in ((b, 3, 2), (b3, 4, 0), (b4, 1, 1)):
        rows = []
        for i in range(active + inactive):
            row = _customer(db, company_id, f"ZZT {agent.sales_agent} {i}")
            row.sales_agent_id = agent.id
            row.is_active = i < active
            rows.append(row)
        made[agent.id] = rows
    db.flush()
    return db, {"b": b, "b3": b3, "b4": b4}


def test_A1_active_customers_of_an_agent_named_exactly_are_its_customers_tab(owner_records):
    from app.models.order import Customer

    db, t = owner_records
    for value in ("ZZT Agent B", "zzt agent b", t["b"].sales_agent, f"{t['b'].sales_agent} - ZZT Agent B"):
        for op in ("eq", "contains"):
            out = run(db, {"entity": "customer", "filters": [{"field": "agent", "op": op, "value": value}]})
            tab = db.query(Customer).filter(Customer.sales_agent_id == t["b"].id, Customer.is_active.is_(True)).count()
            assert out["total"] == tab == 3, (op, value)
            assert out["scope_note"].startswith(f"Agent: {t['b'].sales_agent} - ZZT Agent B.")
    out = run(db, {"entity": "customer", "filters": [{"field": "agent", "op": "eq", "value": "ZZT Agent B"}],
                   "aggregates": [{"fn": "count"}]})
    assert out["groups"][0]["count"] == 3


def test_A2_a_name_no_agent_has_exactly_still_matches_as_contains(owner_records):
    db, t = owner_records
    out = run(db, {"entity": "customer", "filters": [{"field": "agent", "op": "contains", "value": "ZZT Agent B I"}]})
    assert out["total"] == 4 + 1
    assert "Agents:" in out["scope_note"]
    assert refused(db, {"entity": "customer", "filters": [{"field": "agent", "op": "contains", "value": ""}]}).code == "invalid"


def test_A3_eq_with_no_exact_agent_matches_nothing_and_never_another_agent(owner_records):
    db, _t = owner_records
    out = run(db, {"entity": "customer", "filters": [{"field": "agent", "op": "eq", "value": "ZZT Agent"}]})
    assert out["total"] == 0


def test_A4_billing_documents_of_one_agent_by_name(api, grant):
    _client, db, company_id = api
    grant(BILLING_VIEW, SALES_REVEAL)
    a, a2 = _agent(db, "SN", "ZZT Seller"), _agent(db, "SN2", "ZZT Seller II")
    cust = _customer(db, company_id, "ZZT A4 CUST")
    _doc(db, company_id, "invoice", "100", date(2026, 10, 3), agent=a, customer=cust)
    _doc(db, company_id, "invoice", "900", date(2026, 10, 3), agent=a2, customer=cust)
    out = run(db, {"entity": "billing_document", "filters": [{"field": "agent", "op": "contains", "value": "zzt seller"}],
                   "aggregates": [{"fn": "sum", "field": "sales_amount"}]})
    assert out["groups"][0]["sum_sales_amount"] == 100.0


def test_A5_computed_owner_named_exactly_is_that_owner_only(world):
    from tests.chatbot.agent.test_ai_tools_wave2 import ROWS, SEPW, _computed

    db, _company = world
    rows = [{**r, "agent": agent} for r, agent in zip(ROWS, ["AB - Agent B", "AB3 - Agent B III", "AB4 - Agent B IV", "AA - Agent A"])]
    pick = lambda f: sorted(r["agent"] for r in _computed(db, rows, {"filters": [SEPW, f], "fields": ["agent"]})["rows"])  # noqa: E731
    for value in ("Agent B", "agent b", "AB", "AB - Agent B"):
        assert pick({"field": "agent", "op": "contains", "value": value}) == ["AB - Agent B"], value
        assert pick({"field": "agent", "op": "eq", "value": value}) == ["AB - Agent B"], value
    assert pick({"field": "agent", "op": "contains", "value": "Agent B I"}) == ["AB3 - Agent B III", "AB4 - Agent B IV"]
    out = _computed(db, rows, {"filters": [SEPW, {"field": "agent", "op": "eq", "value": "Agent B"}], "fields": ["agent"]})
    assert "Agent: AB - Agent B." in out["scope_note"]


# ------------------------------------------------------------------ (a) one sales basis per answer


def test_S1_no_basis_names_invoiced_not_three_calls():
    from app.services.chatbot.agent.tools import SALES_BASIS_MESSAGE

    assert "basis=invoiced" in SALES_BASIS_MESSAGE and "call once per basis" not in SALES_BASIS_MESSAGE
    assert "One basis per answer" in SALES_BASIS_MESSAGE


def test_S2_money_basis_covers_the_report_and_crm_query():
    from app.services.chatbot.agent.query_tools import money_basis

    assert money_basis({"basis": "invoiced", "group_by": "sales_agent"}, "crm_report_ask") == "invoiced"
    assert money_basis({"basis": "Delivered"}, "crm_report_ask") == "delivered"
    assert money_basis({"basis": "ordered"}, "crm_report_ask") == "ordered"
    assert money_basis({"basis": "outstanding"}, "crm_report_ask") is None
    assert money_basis({"dataset": "chat", "basis": "invoiced"}, "crm_report_ask") is None
    assert money_basis({"basis": "invoiced"}, "crm_other_tool") is None
    q = {"entity": "billing_document", "aggregates": [{"fn": "sum", "field": "sales_amount"}]}
    assert money_basis(q) == money_basis(q, "crm_query") == "invoiced"


def test_S3_the_refusal_names_both_bases():
    from app.services.chatbot.agent.query_tools import mixed_basis_refusal

    out = mixed_basis_refusal("invoiced", "ordered")
    assert out.status == "denied"
    assert "invoiced (billing documents)" in out.message and "ordered (sales orders)" in out.message
    assert "Answer from the first result only" in out.message


def test_S4_a_turn_never_adds_the_reports_other_bases_to_an_invoiced_answer():
    """The crew pass: invoiced per agent, then the report on delivered and ordered. Both later calls are refused
    before they run, so the answer is on the invoiced basis only."""
    import json

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

    invoiced = {"entity": "billing_document", "group_by": ["agent"], "aggregates": [{"fn": "sum", "field": "sales_amount"}]}
    with blank_session() as db:
        contact = agent_contact(db, "finance.billing_documents.view", "sales.reports.view", "order_management.orders.view")
        script = [
            asks("crm_query", invoiced, cid="c1"),
            asks("crm_report_ask", {"basis": "delivered", "group_by": "sales_agent"}, cid="c2"),
            asks("crm_report_ask", {"basis": "ordered", "group_by": "sales_agent"}, cid="c3"),
            answer("Done."),
        ]
        harness.Scripted, original = Recording, harness.Scripted
        try:
            turn(db, contact, script, "sales last month per agent", panel=True)
        finally:
            harness.Scripted = original
    replies = [json.loads(m["content"]) for m in seen[-1]]
    assert replies[0]["status"] == "ok"
    for later in replies[1:]:
        assert later["status"] == "denied" and "invoiced (billing documents)" in later["message"]
