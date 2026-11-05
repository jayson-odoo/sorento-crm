"""AI-TOOLS-WAVE2: the sales modules in the assistant registry (`documentation/plans/chatbot/PLAN-ai-tools-wave2-sales-5nov.md`).

No LLM: `query.run_query` / `query.describe` directly, inside the target tests' own fixtures (blank schema, the SRT
company in scope, "today" pinned to 20 Oct 2026, permissions patched per test). Targets are created through the
real API, so the figures are the target page's; every target figure `crm_query` returns is checked against
`target_service.target_detail`, and every sales figure against `invoiced_sales`, the one sales calculation.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from tests._pg_fixture import unique_code
from tests.test_dealer_targets_api import _customer, _dealer_body, _product_id, _sale
from tests.test_sales_targets_s1 import (  # noqa: F401  (fixtures)
    ALL,
    BASE,
    _agent,
    _client,
    _restore,
    _so_line,
    api,
    world,
)

TARGETS_VIEW = "sales.targets.view"
BILLING_VIEW = "finance.billing_documents.view"
CUSTOMERS_VIEW = "order_management.customers.view"
SO_VIEW = "scm.dashboard.view"
SEP = ["01/09/2026", "30/09/2026"]


@pytest.fixture
def grant(monkeypatch):
    """Replace the user's slugs for the registry's own check (`query._slugs`)."""
    from app.services.assistant_registry import query

    def set_slugs(*slugs):
        monkeypatch.setattr(query, "_slugs", lambda db, user_id: set(slugs))

    return set_slugs


def run(db, spec):
    from app.services.assistant_registry.query import run_query

    return run_query(db, str(uuid.uuid4()), spec)


def refused(db, spec):
    from app.services.assistant_registry.query import QueryRefused

    with pytest.raises(QueryRefused) as info:
        run(db, spec)
    return info.value


# ------------------------------------------------------------------ sales targets


def _agent_target(client, agent, tiers, *, value=10000):
    res = client.post(BASE, json={
        "subject_kind": "agent", "sales_agent_id": agent.id, "name": f"ZZT {agent.sales_agent}",
        "metric": "amount", "basis": "ordered", "product_scope": "all",
        "start_date": "2026-07-01", "end_date": "2026-12-31", "split_every": 1, "split_unit": "month",
        "target_value": value, "commission_method": "retroactive", "tiers": tiers,
    })
    assert res.status_code == 201, res.text
    return res.json()


@pytest.fixture
def targets(api, grant):
    """Agent A: 12,000 in Sep on a 10,000 monthly target (120%, tier 2 at 3% = 360). Agent B: 5,000 in Sep (50%,
    no tier). Both have 9,000 in Oct (90%, tier 1 at 2% = 180). A quarterly dealer target with its own tiers."""
    client, db, company_id = api
    grant(TARGETS_VIEW)
    pid = _product_id(db, company_id)
    a, b = _agent(db, "A", "Agent A"), _agent(db, "B", "Agent B")
    tiers = [{"from_pct": 80, "rate": 2}, {"from_pct": 100, "rate": 3}]
    ta, tb = _agent_target(client, a, tiers), _agent_target(client, b, tiers)
    for agent, sep in ((a, "12000"), (b, "5000")):
        _so_line(db, company_id, agent_id=agent.id, order_date=date(2026, 9, 10), line_total=Decimal(sep), product_id=pid)
        _so_line(db, company_id, agent_id=agent.id, order_date=date(2026, 10, 5), line_total=Decimal("9000"), product_id=pid)
    dealer = _customer(db, company_id, "ZZT DEALER W2", level=1)
    _sale(db, company_id, dealer, "70000", date(2026, 8, 2), product_id=pid)
    res = client.post(BASE, json=_dealer_body([dealer], payout_customer_id=dealer.id, tiers=[
        {"period_start": "2026-07-01", "threshold": 60000, "rate": 5},
        {"period_start": "2026-10-01", "threshold": 60000, "rate": 5},
    ]))
    assert res.status_code == 201, res.text
    return db, client, {"a": a, "b": b, "ta": ta, "tb": tb, "dealer": res.json()}


def test_T1_commission_payout_for_agent_a_last_month(targets):
    db, _client_, t = targets
    out = run(db, {
        "entity": "sales_target",
        "filters": [{"field": "agent", "op": "eq", "value": t["a"].sales_agent}, {"field": "period", "op": "between", "value": SEP}],
        "fields": ["commission", "bonus", "payout", "achieved_value", "achieved_pct", "tier_reached"],
    })
    [row] = out["rows"]
    assert row["achieved_value"] == 12000.0
    assert row["achieved_pct"] == 120.0
    assert row["tier_reached"] == 2
    assert row["commission"] == 360.0 and row["payout"] == 360.0
    assert row["label"] == f"{t['ta']['target_no']}: {t['a'].sales_agent} - Agent A"
    assert row["link"] == f"/sales/targets/{t['ta']['id']}"
    assert out["period_display"] == "Period 01/09/2026 to 30/09/2026"


def test_T2_every_figure_equals_the_target_page(targets):
    """One computation with the screen: each period row's figures are `target_detail`'s, for agent and dealer."""
    from app.services.sales import target_service

    db, _c, t = targets
    out = run(db, {
        "entity": "sales_target", "filters": [{"field": "period", "op": "between", "value": ["01/07/2026", "31/12/2026"]}],
        "fields": ["period_start", "target_value", "achieved_value", "achieved_pct", "tier_reached", "commission", "bonus"],
        "limit": 50,
    })
    by_target = {}
    for row in out["rows"]:
        by_target.setdefault(row["label"].split(":")[0], []).append(row)
    assert set(by_target) == {t["ta"]["target_no"], t["tb"]["target_no"], t["dealer"]["target_no"]}
    checked = 0
    for key in ("ta", "tb", "dealer"):
        target = target_service.get_target_or_404(db, t[key]["id"])
        page = {p["period_start"].strftime("%d/%m/%Y"): p for p in target_service.target_detail(db, target)["periods"]}
        for row in by_target[t[key]["target_no"]]:
            mine = page[row["period_start"]]
            assert row["target_value"] == mine["target_value"]
            assert row["achieved_value"] == mine["achieved_value"]
            assert row["achieved_pct"] == mine["achieved_pct"]
            assert row["tier_reached"] == mine["tier_reached"]
            assert row["commission"] == mine["commission_earned"]
            assert row["bonus"] == mine["bonus_earned"]
            checked += 1
    assert checked == 6 + 6 + 2  # six months per agent target, Q3 and Q4 of the dealer
    dealer_q3 = next(r for r in by_target[t["dealer"]["target_no"]] if r["period_start"] == "01/07/2026")
    assert dealer_q3["commission"] == 3500.0  # 70,000 at 5%


def test_T3_who_is_below_target_last_month(targets):
    db, _c, t = targets
    out = run(db, {
        "entity": "sales_target",
        "filters": [
            {"field": "period", "op": "between", "value": SEP},
            {"field": "subject_kind", "op": "eq", "value": "agent"},
            {"field": "below_target", "op": "eq", "value": True},
        ],
        "fields": ["achieved_pct", "shortfall"],
    })
    assert [r["label"] for r in out["rows"]] == [f"{t['tb']['target_no']}: {t['b'].sales_agent} - Agent B"]
    assert out["rows"][0]["achieved_pct"] == 50.0
    assert out["rows"][0]["shortfall"] == 5000.0


def test_T4_without_a_period_the_current_periods_and_the_note_says_so(targets):
    db, _c, t = targets
    out = run(db, {"entity": "sales_target", "filters": [{"field": "subject_kind", "op": "eq", "value": "agent"}],
                   "fields": ["period_start", "achieved_pct"]})
    assert {r["period_start"] for r in out["rows"]} == {"01/10/2026"}
    assert all(r["achieved_pct"] == 90.0 for r in out["rows"])
    assert out["scope_note"] == "Periods containing today (20/10/2026)."
    assert out["period_display"] is None


def test_T5_payout_per_agent_this_quarter_grouped(targets):
    db, _c, t = targets
    out = run(db, {
        "entity": "sales_target",
        "filters": [{"field": "period", "op": "between", "value": ["01/07/2026", "30/09/2026"]},
                    {"field": "subject_kind", "op": "eq", "value": "agent"}],
        "group_by": ["agent"],
        "aggregates": [{"fn": "sum", "field": "payout"}, {"fn": "avg", "field": "achieved_pct"}],
        "sort": [{"field": "sum_payout", "dir": "desc"}],
    })
    assert out["groups"] == [
        {"agent": t["a"].sales_agent, "sum_payout": 360.0, "avg_achieved_pct": 40.0},
        {"agent": t["b"].sales_agent, "sum_payout": 0.0, "avg_achieved_pct": 16.67},
    ]
    assert out["totals"] == {"sum_payout": 360.0}


def test_T6_targets_follow_the_screen_slug_and_nothing_else(targets, grant):
    db, _c, _t = targets
    from app.services.assistant_registry.query import describe

    grant("sales.reports.view", "sales.opportunities.view_own")
    assert refused(db, {"entity": "sales_target"}).code == "no_access"
    assert "sales_target" not in {e["entity"] for e in describe(db, str(uuid.uuid4()))["entities"]}
    grant(TARGETS_VIEW)
    assert "sales_target" in {e["entity"] for e in describe(db, str(uuid.uuid4()))["entities"]}
    shown = describe(db, str(uuid.uuid4()), "sales_target")
    assert shown["only_own_rows"] is False and "window" in shown
    assert {f["field"]: f["type"] for f in shown["fields"]}["payout"] == "number"


def test_T7_bad_specs_are_refused_before_anything_is_computed(targets, monkeypatch):
    db, _c, _t = targets
    from app.services.assistant_registry import ENTITIES

    calls = []
    entity = ENTITIES["sales_target"]
    monkeypatch.setitem(ENTITIES, "sales_target", type(entity)(**{**entity.__dict__, "compute": lambda *a, **k: calls.append(1) or []}))
    assert refused(db, {"entity": "sales_target", "filters": [{"field": "nope", "op": "eq", "value": 1}]}).code == "unknown_field"
    assert refused(db, {"entity": "sales_target", "group_by": ["agent.code"]}).code == "unknown_field"
    assert refused(db, {"entity": "sales_target", "aggregates": [{"fn": "sum", "field": "agent"}]}).code == "invalid"
    assert refused(db, {"entity": "sales_target", "filters": [{"field": "period", "op": "contains", "value": "x"}]}).code == "invalid"
    assert calls == []


# ------------------------------------------------------------------ billing documents (sales)


def _doc(db, company_id, kind, net, when, *, status="posted", agent=None, customer=None):
    from app.models.finance import BillingDocument

    row = BillingDocument(
        id=str(uuid.uuid4()), company_id=company_id, document_type=kind, doc_no=unique_code("IV"), doc_date=when,
        status=status, net_total=Decimal(net), tax_total=Decimal("0"), total=Decimal(net), local_net_total=Decimal(net),
        sales_agent_id=agent.id if agent else None, customer_id=customer.id if customer else None,
        debtor_code=customer.customer_code if customer else None, source_ref=f"SRT_DB:{uuid.uuid4().hex}",
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def sales(api, grant):
    client, db, company_id = api
    grant(BILLING_VIEW)
    a, b = _agent(db, "SA", "Sales A"), _agent(db, "SB", "Sales B")
    cust = _customer(db, company_id, "ZZT BILL CUST")
    oct_ = date(2026, 10, 3)
    _doc(db, company_id, "invoice", "1000", oct_, agent=a, customer=cust)
    _doc(db, company_id, "cash_sale", "200", oct_, agent=a, customer=cust)
    _doc(db, company_id, "debit_note", "50", oct_, agent=b, customer=cust)
    _doc(db, company_id, "credit_note", "300", oct_, agent=a, customer=cust)
    _doc(db, company_id, "invoice", "9999", oct_, agent=a, customer=cust, status="cancelled")
    _doc(db, company_id, "invoice", "777", date(2026, 9, 30), agent=a, customer=cust)
    return db, company_id, {"a": a, "b": b, "cust": cust}


def test_B1_sales_is_iv_cs_dn_minus_cn_by_doc_date_cancelled_excluded(sales):
    from app.models.finance import BillingDocument
    from app.services.sales import invoiced_sales

    db, _company, s = sales
    window = {"field": "doc_date", "op": "between", "value": ["01/10/2026", "31/10/2026"]}
    mine = {"field": "debtor_code", "op": "eq", "value": s["cust"].customer_code}
    out = run(db, {"entity": "billing_document", "filters": [window, mine], "aggregates": [{"fn": "sum", "field": "sales_amount"}]})
    assert out["groups"] == [{"sum_sales_amount": 950.0}]  # 1000 + 200 + 50 - 300, the 9,999 cancelled one out
    assert out["scope_note"] == "Cancelled documents excluded."
    assert out["period_display"] == "Document date 01/10/2026 to 31/10/2026"
    expected = db.execute(
        select(func.sum(invoiced_sales.signed_amount())).where(
            invoiced_sales.posted(), BillingDocument.debtor_code == s["cust"].customer_code,
            BillingDocument.doc_date.between(date(2026, 10, 1), date(2026, 10, 31)),
        )
    ).scalar()
    assert float(expected) == 950.0


def test_B2_sales_per_agent_uses_the_sales_reports_agent(sales):
    db, _company, s = sales
    out = run(db, {
        "entity": "billing_document",
        "filters": [{"field": "customer.code", "op": "eq", "value": s["cust"].customer_code},
                    {"field": "doc_date", "op": "between", "value": ["01/10/2026", "31/10/2026"]}],
        "group_by": ["agent"], "aggregates": [{"fn": "sum", "field": "sales_amount"}, {"fn": "count"}],
        "sort": [{"field": "agent", "dir": "asc"}],
    })
    assert out["groups"] == [
        {"agent": s["a"].sales_agent, "sum_sales_amount": 900.0, "count": 3},
        {"agent": s["b"].sales_agent, "sum_sales_amount": 50.0, "count": 1},
    ]


def test_B3_cancelled_on_request_and_the_slug(sales, grant):
    db, _company, s = sales
    mine = {"field": "debtor_code", "op": "eq", "value": s["cust"].customer_code}
    out = run(db, {"entity": "billing_document", "filters": [mine, {"field": "status", "op": "eq", "value": "cancelled"}],
                   "fields": ["net_total"]})
    assert [r["net_total"] for r in out["rows"]] == [9999.0]
    assert out["scope_note"] is None
    grant("sales.reports.view")
    assert refused(db, {"entity": "billing_document"}).code == "no_access"


# ------------------------------------------------------------------ sales orders, customers


def test_S1_sales_orders_leave_consignments_out_and_group_by_agent(api, grant):
    from app.models.order import SalesOrder

    _c, db, company_id = api
    grant(SO_VIEW)
    pid = _product_id(db, company_id)
    a = _agent(db, "SO", "SO Agent")
    so, _l = _so_line(db, company_id, agent_id=a.id, order_date=date(2026, 10, 1), line_total=Decimal("1"), product_id=pid)
    cons, _l2 = _so_line(db, company_id, agent_id=a.id, order_date=date(2026, 10, 1), line_total=Decimal("1"), product_id=pid)
    db.query(SalesOrder).filter(SalesOrder.id == cons.id).update({"doc_type": "consignment"})
    db.flush()
    out = run(db, {"entity": "sales_order", "filters": [{"field": "agent.code", "op": "eq", "value": a.sales_agent}],
                   "fields": ["order_date", "agent.code"]})
    assert [r["id"] for r in out["rows"]] == [so.id]
    assert out["rows"][0]["agent.code"] == a.sales_agent
    assert out["rows"][0]["link"] == f"/scm/sales-orders/{so.id}"
    grant(CUSTOMERS_VIEW)
    assert refused(db, {"entity": "sales_order"}).code == "no_access"


def test_C1_customers_list_per_agent_without_contact_fields(api, grant):
    _c, db, company_id = api
    grant(CUSTOMERS_VIEW)
    a = _agent(db, "CU", "Cust Agent")
    rows = [_customer(db, company_id, f"ZZT CU {i}") for i in range(3)]
    for row in rows[:2]:
        row.sales_agent_id = a.id
    db.flush()
    out = run(db, {"entity": "customer", "filters": [{"field": "agent.code", "op": "eq", "value": a.sales_agent}],
                   "group_by": ["agent.code"], "aggregates": [{"fn": "count"}]})
    assert out["groups"] == [{"agent.code": a.sales_agent, "count": 2}]
    from app.services.assistant_registry import ENTITIES

    assert not {"email", "phone_number", "mobile_number", "billing_address", "ar_outstanding"} & set(ENTITIES["customer"].fields)
    assert refused(db, {"entity": "customer", "fields": ["email"]}).code == "unknown_field"
