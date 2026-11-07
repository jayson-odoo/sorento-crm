"""AI-TOOLS-WAVE3: stock, amounts owed, opportunities and projects in the assistant registry
(`documentation/plans/chatbot/PLAN-ai-tools-wave3-7nov.md`).

No LLM: `query.run_query` / `query.describe` directly, in the wave 2 fixtures (blank schema, the SRT company in
scope, "today" pinned to 20 Oct 2026, the registry's slugs patched per test).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest

from tests.test_dealer_targets_api import _customer
from tests.test_sales_targets_s1 import (  # noqa: F401  (fixtures)
    _agent,
    _category,
    _code,
    _product,
    _warehouse,
    world,
)

STOCK_VIEW = "inventory.stock.view"
CUSTOMERS_VIEW = "order_management.customers.view"
BILLING_VIEW = "finance.billing_documents.view"
OPP_VIEW = "sales.opportunities.view"
OPP_OWN = "sales.opportunities.view_own"
PROJECT_VIEW = "projects.projects.view"
PROJECT_OWN = "projects.projects.view_own"


@pytest.fixture
def grant(monkeypatch):
    from app.services.assistant_registry import query

    def set_slugs(*slugs):
        monkeypatch.setattr(query, "_slugs", lambda db, user_id: set(slugs))

    return set_slugs


def run(db, spec, *, user_id=None, panel=True):
    from app.services.assistant_registry.query import run_query

    return run_query(db, user_id or str(uuid.uuid4()), spec, panel=panel)


def refused(db, spec, **kw):
    from app.services.assistant_registry.query import QueryRefused

    with pytest.raises(QueryRefused) as info:
        run(db, spec, **kw)
    return info.value


def _me(monkeypatch, user_id, agent_ids=(), contact_id=None):
    from app.services import own_scope

    monkeypatch.setattr(
        own_scope, "me", lambda db, uid: own_scope.Me(user_id=str(uid), contact_id=contact_id, agent_ids=tuple(agent_ids))
    )


# ------------------------------------------------------------------ stock


def _stock(db, company_id, product, warehouse, *, on_hand, reserved=0):
    from app.models.inventory import Stock

    row = Stock(
        id=str(uuid.uuid4()), company_id=company_id, product_id=product.id, warehouse_id=warehouse.id,
        quantity_on_hand=on_hand, quantity_reserved=reserved,
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def stock(world, grant):
    db, company_id = world
    grant(STOCK_VIEW)
    cat = _category(db, company_id)
    p1, p2 = _product(db, company_id, cat.id), _product(db, company_id, cat.id)
    p1.reorder_level = 10
    w1, w2 = _warehouse(db, company_id), _warehouse(db, company_id)
    shut = _warehouse(db, company_id)
    shut.is_active = False
    db.flush()
    rows = {
        "p1w1": _stock(db, company_id, p1, w1, on_hand=8, reserved=3),   # available 5 < 10: low
        "p1w2": _stock(db, company_id, p1, w2, on_hand=25),               # 25 > 20: overstock
        "p2w1": _stock(db, company_id, p2, w1, on_hand=0),                # critical
        "p2w2": _stock(db, company_id, p2, w2, on_hand=7),                # no reorder level: normal
        "shut": _stock(db, company_id, p1, shut, on_hand=99),             # inactive warehouse: not on the screen
    }
    return db, company_id, {"p1": p1, "p2": p2, "w1": w1, "w2": w2, "shut": shut}, rows


def test_ST1_stock_rows_as_the_grid_shows_them(stock):
    db, _cid, t, _rows = stock
    out = run(db, {
        "entity": "stock",
        "filters": [{"field": "product.product_code", "op": "eq", "value": t["p1"].product_code}],
        "fields": ["warehouse.code", "quantity_on_hand", "quantity_reserved", "quantity_available", "status"],
        "sort": [{"field": "quantity_on_hand", "dir": "asc"}],
    })
    got = [(r["warehouse.code"], r["quantity_on_hand"], r["quantity_reserved"], r["quantity_available"], r["status"])
           for r in out["rows"]]
    # The inactive warehouse's 99 is not on the stock screen (`inventory_service.py:839`), so not here either.
    assert got == [
        (t["w1"].warehouse_code, 8, 3, 5, "low"),
        (t["w2"].warehouse_code, 25, 0, 25, "overstock"),
    ]


def test_ST2_status_equals_the_grid_property_on_every_edge(stock):
    """One reading of status: the SQL expression the registry filters and groups on equals `Stock.status`, the
    property the grid prints, including a product with no reorder level (where `_stock_status_clause` differs)."""
    from app.models.inventory import Stock

    db, _cid, t, rows = stock
    for case in ((0, 0), (0, 5), (3, 0), (10, 0), (21, 0), (20, 0), (-2, 0)):
        for product in (t["p1"], t["p2"]):
            rows[f"x{case}{product.id}"] = _stock(db, _cid, product, _warehouse(db, _cid), on_hand=case[0], reserved=case[1])
    out = run(db, {"entity": "stock", "fields": ["status"], "limit": 50})
    by_id = {r["id"]: r["status"] for r in out["rows"]}
    assert len(by_id) == len(rows) - 1  # every row but the inactive warehouse's
    for row in rows.values():
        if row.warehouse_id == t["shut"].id:
            continue
        db.refresh(row)
        assert by_id[row.id] == db.get(Stock, row.id).status, row.quantity_on_hand


def test_ST3_low_stock_per_warehouse_grouped(stock):
    db, _cid, t, _rows = stock
    out = run(db, {
        "entity": "stock", "filters": [{"field": "status", "op": "in", "value": ["low", "critical"]}],
        "group_by": ["warehouse.code"], "aggregates": [{"fn": "count"}],
    })
    assert out["groups"] == [{"warehouse.code": t["w1"].warehouse_code, "count": 2}]


def test_ST4_stock_is_panel_only_and_names_the_stock_tool(stock):
    """Off the staff panel (a linked user's WhatsApp turn) the stock-visibility policy and the stock switch live in
    the stock tool only, so the registry never answers stock there."""
    db, *_ = stock
    exc = refused(db, {"entity": "stock"}, panel=False)
    assert exc.code == "restricted"
    assert "crm_inventory_stock_balance_list" in exc.message
    from app.services.assistant_registry.query import describe

    listed = {e["entity"] for e in describe(db, str(uuid.uuid4()))["entities"]}
    assert "stock" not in listed
    assert "stock" in {e["entity"] for e in describe(db, str(uuid.uuid4()), panel=True)["entities"]}


def test_ST5_stock_needs_the_stock_slug(stock, grant):
    db, *_ = stock
    grant("master_data.products.view")
    assert refused(db, {"entity": "stock"}).code == "no_access"


# ------------------------------------------------------------------ amounts owed (customer)


def test_AR1_who_owes_us_the_most_needs_the_billing_screen(world, grant):
    db, company_id = world
    a = _customer(db, company_id, "ZZT AR A")
    b = _customer(db, company_id, "ZZT AR B")
    _customer(db, company_id, "ZZT AR none")
    a.ar_outstanding, a.ar_as_of = Decimal("1200.50"), datetime(2026, 10, 19, 8, 0)
    b.ar_outstanding, b.ar_as_of = Decimal("300"), datetime(2026, 10, 19, 8, 0)
    db.flush()
    grant(CUSTOMERS_VIEW, BILLING_VIEW)
    out = run(db, {
        "entity": "customer", "filters": [{"field": "name", "op": "starts_with", "value": "ZZT AR"},
                                          {"field": "ar_outstanding", "op": "gt", "value": 0}],
        "fields": ["ar_outstanding", "ar_as_of"], "sort": [{"field": "ar_outstanding", "dir": "desc"}],
    })
    assert [(r["label"].split(": ")[1], r["ar_outstanding"]) for r in out["rows"]] == [("ZZT AR A", 1200.5), ("ZZT AR B", 300.0)]
    # Without the billing documents screen the figure is restricted, as on the screen.
    grant(CUSTOMERS_VIEW)
    hidden = run(db, {"entity": "customer", "fields": ["ar_outstanding"],
                      "filters": [{"field": "name", "op": "eq", "value": "ZZT AR A"}]})
    assert hidden["restricted"] == ["ar_outstanding"] and "ar_outstanding" not in hidden["rows"][0]
    assert refused(db, {"entity": "customer", "sort": [{"field": "ar_outstanding", "dir": "desc"}]}).code == "restricted"
    plain = run(db, {"entity": "customer", "filters": [{"field": "name", "op": "eq", "value": "ZZT AR A"}]})
    assert "ar_outstanding" not in plain["rows"][0]


def test_AR2_ageing_is_not_offered(world, grant):
    """Nothing writes `ar_ageing_json` (only the model and the merge copy name it), so no bucket is registered."""
    from app.services.assistant_registry import ENTITIES

    fields = ENTITIES["customer"].fields
    assert not {k for k in fields if "ageing" in k or "aging" in k}
    assert "ageing" in (fields["ar_outstanding"].note or "").lower()


# ------------------------------------------------------------------ opportunities


def _opportunity(db, company_id, *, agent=None, customer=None, amount="1000", close=date(2026, 10, 25),
                 outcome="open", status_id=None, title="ZZT Opp"):
    from app.models.sales import SalesOpportunity

    row = SalesOpportunity(
        id=str(uuid.uuid4()), company_id=company_id, opportunity_no=_code(), customer_id=customer.id if customer else None,
        prospect_name=None if customer else "ZZT Prospect", sales_agent_id=agent.id if agent else None, title=title,
        outcome=outcome, expected_amount=Decimal(amount), expected_close_date=close, source="crm", status_id=status_id,
    )
    db.add(row)
    db.flush()
    return row


def _status(db, entity_type, label):
    from app.models.status import Status

    row = Status(id=str(uuid.uuid4()), entity_type=entity_type, key=label.lower().replace(" ", "_"), label=label)
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def opps(world, grant):
    db, company_id = world
    grant(OPP_VIEW)
    a, b = _agent(db, "OA", "Opp Agent A"), _agent(db, "OB", "Opp Agent B")
    cust = _customer(db, company_id, "ZZT OPP CUST")
    stage = _status(db, "sales_opportunity", "ZZT Negotiation")
    rows = [
        _opportunity(db, company_id, agent=a, customer=cust, amount="1000", status_id=stage.id),
        _opportunity(db, company_id, agent=a, amount="2500", close=date(2026, 11, 3)),
        _opportunity(db, company_id, agent=b, amount="4000", outcome="won"),
    ]
    return db, company_id, {"a": a, "b": b, "cust": cust, "stage": stage, "rows": rows}


def test_OP1_open_opportunities_of_an_agent_closing_this_month(opps):
    db, _cid, t = opps
    out = run(db, {
        "entity": "opportunity", "agent": "Opp Agent A", "period": "this_month",
        "filters": [{"field": "outcome", "op": "eq", "value": "open"}],
        "fields": ["title", "stage", "expected_amount", "expected_close_date", "customer.name"],
    })
    [row] = out["rows"]
    assert row["stage"] == "ZZT Negotiation"
    assert row["expected_amount"] == 1000.0
    assert row["customer.name"] == "ZZT OPP CUST"
    assert out["period_display"] == "Close date 01/10/2026 to 31/10/2026"


def test_OP2_amount_per_agent_and_outcome(opps):
    db, _cid, t = opps
    out = run(db, {"entity": "opportunity", "group_by": ["agent", "outcome"],
                   "aggregates": [{"fn": "sum", "field": "expected_amount"}], "sort": [{"field": "agent", "dir": "asc"}]})
    got = {(g["agent"], g["outcome"]): g["sum_expected_amount"] for g in out["groups"]}
    assert got == {
        (f"{t['a'].sales_agent} - Opp Agent A", "open"): 3500.0,
        (f"{t['b'].sales_agent} - Opp Agent B", "won"): 4000.0,
    }


def test_OP3_own_only_holder_sees_their_agents_opportunities(opps, grant, monkeypatch):
    db, _cid, t = opps
    grant(OPP_OWN)
    uid = str(uuid.uuid4())
    _me(monkeypatch, uid, agent_ids=[t["a"].id])
    out = run(db, {"entity": "opportunity", "fields": ["title"]}, user_id=uid)
    assert {r["id"] for r in out["rows"]} == {t["rows"][0].id, t["rows"][1].id}
    _me(monkeypatch, uid, agent_ids=[])
    assert run(db, {"entity": "opportunity"}, user_id=uid)["rows"] == []
    grant()
    assert refused(db, {"entity": "opportunity"}).code == "no_access"


# ------------------------------------------------------------------ projects


def _project(db, company_id, *, owner, title, approval_state=None, outcome="open", critical=False, value=None,
             status_id=None):
    from app.models.projects import Project, ProjectSalesProfile

    row = Project(
        id=str(uuid.uuid4()), company_id=company_id, project_code=_code(), title=title, normalised_title=title.lower(),
        owner_user_id=owner, approval_state=approval_state, outcome=outcome, is_critical=critical, status_id=status_id,
    )
    db.add(row)
    db.flush()
    if value is not None:
        db.add(ProjectSalesProfile(project_id=row.id, estimated_sales_value=Decimal(value)))
        db.flush()
    return row


def _user(db, name):
    from app.models.user import User

    row = User(id=str(uuid.uuid4()), email=f"{uuid.uuid4().hex[:10]}@zzt.test", name=name)
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def projects(world, grant):
    db, company_id = world
    grant(PROJECT_VIEW)
    me, other = _user(db, "ZZT Owner Me"), _user(db, "ZZT Owner Other")
    stage = _status(db, "project", "ZZT Tender")
    rows = {
        "mine": _project(db, company_id, owner=me.id, title="ZZT P mine", critical=True, value="50000", status_id=stage.id),
        "other": _project(db, company_id, owner=other.id, title="ZZT P other", value="20000"),
        "my_draft": _project(db, company_id, owner=me.id, title="ZZT P my draft", approval_state="draft"),
        "their_draft": _project(db, company_id, owner=other.id, title="ZZT P their draft", approval_state="draft"),
    }
    return db, company_id, {"me": me, "other": other, "stage": stage, "rows": rows}


def test_PR1_drafts_only_to_their_owner(projects):
    db, _cid, t = projects
    out = run(db, {"entity": "project", "filters": [{"field": "title", "op": "starts_with", "value": "ZZT P"}],
                   "fields": ["title"], "limit": 50}, user_id=t["me"].id)
    assert {r["label"].split(": ", 1)[1] for r in out["rows"]} == {"ZZT P mine", "ZZT P other", "ZZT P my draft"}


def test_PR2_project_fields_and_value_per_owner(projects):
    db, _cid, t = projects
    out = run(db, {"entity": "project", "filters": [{"field": "is_critical", "op": "eq", "value": True}],
                   "fields": ["title", "stage", "owner", "estimated_value", "outcome"]}, user_id=t["me"].id)
    [row] = out["rows"]
    assert (row["stage"], row["owner"], row["estimated_value"], row["outcome"]) == ("ZZT Tender", "ZZT Owner Me", 50000.0, "open")
    groups = run(db, {"entity": "project", "group_by": ["owner"], "aggregates": [{"fn": "sum", "field": "estimated_value"}],
                      "filters": [{"field": "title", "op": "starts_with", "value": "ZZT P"}]}, user_id=t["me"].id)
    assert {g["owner"]: g["sum_estimated_value"] for g in groups["groups"]} == {"ZZT Owner Me": 50000.0, "ZZT Owner Other": 20000.0}


def test_PR3_own_only_holder_sees_owned_and_collaborated(projects, grant, monkeypatch):
    from app.models.projects import ProjectCollaborator

    db, _cid, t = projects
    grant(PROJECT_OWN)
    db.add(ProjectCollaborator(project_id=t["rows"]["other"].id, user_id=t["me"].id))
    db.flush()
    _me(monkeypatch, t["me"].id)
    out = run(db, {"entity": "project", "fields": ["title"], "limit": 50}, user_id=t["me"].id)
    assert {r["label"].split(": ", 1)[1] for r in out["rows"]} == {"ZZT P mine", "ZZT P other", "ZZT P my draft"}
    stranger = str(uuid.uuid4())
    _me(monkeypatch, stranger)
    assert run(db, {"entity": "project"}, user_id=stranger)["rows"] == []


# ------------------------------------------------------------------ company isolation and the index


def test_CO1_another_companys_rows_stay_out(stock, grant):
    from tests.chatbot.agent.test_ai_tools_wave2 import _company_b

    from app.models.base import company_scope

    db, company_id, t, _rows = stock
    other = _company_b(db)
    with company_scope(db, frozenset({other})):
        cat = _category(db, other)
        p = _product(db, other, cat.id)
        _stock(db, other, p, _warehouse(db, other), on_hand=777)
        agent = _agent(db, "OX", "Other Co Opp", company_id=other)
        _opportunity(db, other, agent=agent, amount="777")
    assert not [r for r in run(db, {"entity": "stock", "fields": ["quantity_on_hand"], "limit": 50})["rows"]
                if r["quantity_on_hand"] == 777]
    grant(OPP_VIEW)
    assert not [r for r in run(db, {"entity": "opportunity", "fields": ["expected_amount"], "limit": 50})["rows"]
                if r["expected_amount"] == 777.0]


def test_IX1_new_entities_are_in_the_compact_index():
    from app.services.chatbot.agent.query_tools import entity_index

    index = entity_index()
    for key in ("stock", "opportunity", "project"):
        assert any(line.startswith(f"{key} (") for line in index.splitlines()), key
    assert "ar_outstanding" in index
