"""AI-TOOLS-WAVE2 crew pass on d430fe3c (5 Nov): the sales report's gate on sales totals, the Customers list's Active
filter, the entity index in `crm_query`'s description, the per-turn query cap, and the table's blank lines.

No LLM. Registry calls run in the target tests' fixtures (blank schema, SRT in scope) with the REAL `query._slugs`,
so the reveal keys come from `contact_field_reveal_service.staff_reveal_keys`, the sales report route's own staff gate.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from tests.chatbot.agent.test_ai_tools_wave2 import _doc
from tests.test_dealer_targets_api import _customer
from tests.test_sales_targets_s1 import _agent, api, world  # noqa: F401  (fixtures)

BILLING_VIEW = "finance.billing_documents.view"
SALES_REPORTS = "sales.reports.view"
ORDERS_VIEW = "order_management.orders.view"
SO_VIEW = "scm.dashboard.view"
CUSTOMERS_VIEW = "order_management.customers.view"


@pytest.fixture
def holds(api):
    """The user's real slugs for both the registry and the reveal lookup (`UserPermissionService`). Restored by
    hand BEFORE `api` restores its own patch: the `world` fixture's monkeypatch is torn down after `api`, so a
    monkeypatch here would put `api`'s patched methods back for every later test."""
    from app.services.user_service import UserPermissionService

    before = (UserPermissionService.get_user_permission_slugs, UserPermissionService.check_user_has_permission)

    def set_slugs(*slugs):
        granted = set(slugs)
        UserPermissionService.get_user_permission_slugs = lambda self, uid: list(granted)
        UserPermissionService.check_user_has_permission = lambda self, uid, slug: slug in granted

    yield set_slugs
    UserPermissionService.get_user_permission_slugs, UserPermissionService.check_user_has_permission = before


def run(db, spec, user_id="u-wave2"):
    from app.services.assistant_registry.query import run_query

    return run_query(db, user_id, spec)


def refusal(db, spec):
    from app.services.assistant_registry.query import QueryRefused

    with pytest.raises(QueryRefused) as info:
        run(db, spec)
    return info.value


@pytest.fixture
def docs(api):
    _client, db, company_id = api
    cust = _customer(db, company_id, "ZZT R3 CUST")
    agent = _agent(db, "R3", "Round Three")
    _doc(db, company_id, "invoice", "1000", date(2026, 10, 3), agent=agent, customer=cust)
    _doc(db, company_id, "credit_note", "100", date(2026, 10, 4), agent=agent, customer=cust)
    return db, company_id, cust


# ------------------------------------------------------------------ (1) the sales report's gate


def test_G1_sales_totals_need_the_same_reveal_as_the_sales_report(docs, holds):
    """`report_ask.py`: a staff read is granted iff `report_ask.GRANT` is in the staff member's reveal keys
    (`staff_reveal_keys`, `sales.reports.view`). Without it the report refuses; so does every billing total and
    money field here. With it, both answer."""
    from app.api.v1.order_management import report_ask
    from app.services.contact_field_reveal_service import staff_reveal_keys

    db, _company, cust = docs
    mine = {"field": "debtor_code", "op": "eq", "value": cust.customer_code}
    for slugs, granted in (((BILLING_VIEW,), False), ((BILLING_VIEW, SALES_REPORTS), True)):
        holds(*slugs)
        report_says = report_ask.GRANT in staff_reveal_keys(db, "u-wave2")
        assert report_says is granted
        if granted:
            out = run(db, {"entity": "billing_document", "filters": [mine], "aggregates": [{"fn": "sum", "field": "sales_amount"}]})
            assert out["groups"] == [{"sum_sales_amount": 900.0}]
            continue
        # Totals and rankings: refused, whatever field (a count too).
        for spec in (
            {"aggregates": [{"fn": "sum", "field": "sales_amount"}]},
            {"aggregates": [{"fn": "count"}]},
            {"group_by": ["agent"]},
        ):
            assert refusal(db, {"entity": "billing_document", "filters": [mine], **spec}).code == "restricted", spec
        # Rows: the screen's documents, without a money figure.
        rows = run(db, {"entity": "billing_document", "filters": [mine]})
        assert {"sales_amount", "net_total", "total"} <= set(rows["restricted"])
        assert all("net_total" not in r and "sales_amount" not in r for r in rows["rows"])
        assert refusal(db, {"entity": "billing_document", "filters": [mine], "sort": [{"field": "net_total", "dir": "desc"}]}).code == "restricted"


def test_G2_outstanding_follows_the_outstanding_reveal(docs, holds):
    db, _company, cust = docs
    mine = {"field": "debtor_code", "op": "eq", "value": cust.customer_code}
    holds(BILLING_VIEW, SALES_REPORTS)
    assert "outstanding" in run(db, {"entity": "billing_document", "filters": [mine]})["restricted"]
    holds(BILLING_VIEW, SALES_REPORTS, ORDERS_VIEW)  # `sales_orders.outstanding` answers to the orders slug
    assert "outstanding" not in run(db, {"entity": "billing_document", "filters": [mine]})["restricted"]


def test_G3_sales_order_counts_need_the_reveal_rows_do_not(api, holds):
    _client, db, _company = api
    holds(SO_VIEW)
    assert run(db, {"entity": "sales_order", "limit": 1})["entity"] == "sales_order"
    assert refusal(db, {"entity": "sales_order", "group_by": ["agent.code"]}).code == "restricted"
    holds(SO_VIEW, SALES_REPORTS)
    assert "groups" in run(db, {"entity": "sales_order", "group_by": ["agent.code"]})


# ------------------------------------------------------------------ (2) active customers


def test_A1_active_customers_of_an_agent_use_the_customers_lists_active_filter(api, holds):
    _client, db, company_id = api
    holds(CUSTOMERS_VIEW)
    agent = _agent(db, "ACT", "Active Agent")
    rows = [_customer(db, company_id, f"ZZT ACT {i}") for i in range(3)]
    for row in rows:
        row.sales_agent_id = agent.id
    rows[2].is_active = False
    db.flush()
    by_agent = {"field": "agent.code", "op": "eq", "value": agent.sales_agent}
    out = run(db, {"entity": "customer", "filters": [by_agent], "aggregates": [{"fn": "count"}]})
    assert out["groups"] == [{"count": 2}]
    assert out["scope_note"] == "Inactive customers excluded."
    every = run(db, {"entity": "customer", "filters": [by_agent, {"field": "is_active", "op": "in", "value": [True, False]}],
                     "aggregates": [{"fn": "count"}]})
    assert every["groups"] == [{"count": 3}] and every["scope_note"] is None


# ------------------------------------------------------------------ (3) the index and the cap


def test_I1_the_entity_index_is_in_the_query_tools_description():
    from app.services.assistant_registry import ENTITIES
    from app.services.chatbot.agent import query_tools

    text = query_tools.QUERY_SCHEMA["function"]["description"]
    for key, entity in ENTITIES.items():
        if entity.view_permission:
            assert f"\n{key} (" in text, key
            assert entity.hint, f"{key} has no index hint"
    assert "payout" in text and "sales_amount" in text and "customer.{code,name}" in text
    assert "call crm_describe only when" in text


def test_I2_at_most_four_query_calls_per_turn():
    """The loop denies the fifth crm_query / crm_describe call of a turn and tells the model to answer."""
    import app.main  # noqa: F401
    from app.services.chatbot.agent import loop
    from app.services.company_scope import register_company_scope_listeners
    from tests._pg_fixture import blank_session
    from tests.chatbot.agent.test_ai_query_reply import Scripted, agent_contact, answer, asks, turn

    assert loop.MAX_QUERY_CALLS == 4
    register_company_scope_listeners()
    seen: list[list[dict]] = []

    class Recording(Scripted):
        def chat(self, messages, **kw):
            seen.append([m for m in messages if m.get("role") == "tool"])
            return super().chat(messages, **kw)

    with blank_session() as db:
        contact = agent_contact(db, ORDERS_VIEW)
        script = [asks("crm_describe", {}, cid=f"c{i}") for i in range(5)] + [answer("Done.")]
        from tests.chatbot.agent import test_ai_query_reply as harness

        original = harness.Scripted
        harness.Scripted = Recording
        try:
            turn(db, contact, script, "what can you read?", panel=True)
        finally:
            harness.Scripted = original
    replies = seen[-1]
    assert len(replies) == 5
    assert all("At most" not in r["content"] for r in replies[:4])
    assert "At most 4 crm_query/crm_describe calls" in replies[4]["content"]


# ------------------------------------------------------------------ (4) the table renders


def test_T1_the_panel_table_has_blank_lines_around_it():
    from app.services.chatbot.agent.query_tools import render_card

    data = {
        "columns": [{"key": "agent", "label": "Agent"}, {"key": "count", "label": "Orders"}],
        "groups": [{"agent": "A", "count": 2}, {"agent": "B", "count": 3}],
        "totals": {"count": 5}, "period_display": "Order date 01/10/2026 to 31/10/2026",
        "scope_note": "Cancelled orders excluded.", "truncated": False,
    }
    lines = render_card(data, title="Orders per agent", panel=True).split("\n")
    assert lines[0] == "Orders per agent, Order date 01/10/2026 to 31/10/2026"
    assert lines[1] == ""  # without it markdown shows the table as raw "|" text
    assert lines[2] == "| Agent | Orders |"
    table_end = max(i for i, line in enumerate(lines) if line.startswith("|"))
    assert lines[table_end + 1] == "" and lines[table_end + 2] == "Cancelled orders excluded."
    # WhatsApp has no table: one line per row, unchanged.
    assert "|" not in render_card(data, title="Orders per agent", panel=False)
