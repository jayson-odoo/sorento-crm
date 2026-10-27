"""SALES-UNIFIED security review fixes: M1 (invoiced figures need `sales.reports.view` on the
order routes too), L3 (a class edit re-derives every company's orders), L5 (a non-id filter
value is 422, never a 500), L6 (the stock report's entry point never sums every company).
"""
from __future__ import annotations

from datetime import date

import pytest

from app.main import app  # noqa: F401  (import order)
from app.models.base import company_scope, set_company_scope
from app.models.order import SalesOrder
from app.models.sales import SalesAgentClass
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.error_handler import AppException
from tests._mc_lookup_seed import MOCHA_ID, product, seed_mocha
from tests._pg_fixture import blank_session, unique_code
from tests._sales_unified_seed import agent, doc, line, so
from tests.test_sales_yearly_routes import _client, _user

TOP = "/api/v1/order-management/top-selling"
YEAR = {"date_from": "2026-01-01", "date_to": "2026-12-31"}


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, frozenset({DEFAULT_COMPANY_ID}))
        seed_mocha(s)
        yield s


def test_m1_invoiced_top_selling_needs_the_sales_reports_slug(db):
    principal = _user(db, DEFAULT_COMPANY_ID)
    with _client(db, principal, allow=("order_management.orders.view",)) as client:
        refused = client.get(TOP, params={"rank_by": "amount", **YEAR})
        assert refused.status_code == 403, refused.text
        assert refused.json()["code"] == "invoiced_needs_sales_reports"
        assert client.get(TOP, params={"rank_by": "amount", "basis": "delivered", **YEAR}).status_code == 200
    with _client(db, principal, allow=("order_management.orders.view", "sales.reports.view")) as client:
        assert client.get(TOP, params={"rank_by": "amount", **YEAR}).status_code == 200


def test_l3_a_class_edit_rederives_every_companys_orders(db):
    from app.services.sales import agent_class_service as svc

    a = agent(db, unique_code("ZZTSEC"))
    with company_scope(db, None):
        mocha_order, _ = so(db, demand_class="retail", company_id=MOCHA_ID)
        mocha_order.sales_agent_id = a.id
        mocha_order.order_date = date(2026, 3, 3)
        db.flush()
    db.add(SalesAgentClass(sales_agent_id=a.id, demand_class="project"))
    db.flush()
    svc.rederive(db, agent_ids=[str(a.id)], apply=True)  # caller scoped to Sorento only
    db.expire_all()
    with company_scope(db, None):
        assert db.get(SalesOrder, mocha_order.id).demand_class == "project"


def test_l5_a_non_id_filter_value_is_422(db):
    from app.services.sales import invoiced_sales as inv

    with pytest.raises(AppException) as bad:
        inv.agent_condition(["not-a-uuid"])
    assert bad.value.status_code == 422
    assert inv.uuid_values(["none"][:0], "agent") == []


def test_l6_the_entry_point_refuses_an_unrestricted_scope_and_takes_explicit_companies(db):
    from app.services.sales.invoiced_sales import quantity_by_product_month

    p = product(db, company_id=DEFAULT_COMPANY_ID)
    doc(db, "invoice", "10.00", date(2026, 1, 5), lines=[line(qty="2", prod=p)])
    with company_scope(db, None):
        with pytest.raises(AppException):
            quantity_by_product_month(db, date(2026, 1, 1), date(2026, 2, 1))
        assert quantity_by_product_month(db, date(2026, 1, 1), date(2026, 2, 1), company_ids=[MOCHA_ID]) == []
        got = quantity_by_product_month(db, date(2026, 1, 1), date(2026, 2, 1), company_ids=[DEFAULT_COMPANY_ID])
    assert [(pid, m) for pid, m, _q in got] == [(str(p.id), "2026-01")]
