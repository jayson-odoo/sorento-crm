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


# ------------------------------------------------------------------ reviewer B1


def _both_companies(db):
    from tests._sales_unified_seed import doc as _doc

    p = product(db, company_id=DEFAULT_COMPANY_ID)
    q = product(db, company_id=MOCHA_ID)
    _doc(db, "invoice", "250.00", date(2026, 3, 1), lines=[line(qty="5", prod=p)])
    with company_scope(db, None):
        _doc(db, "invoice", "100.00", date(2026, 3, 2), company_id=MOCHA_ID, lines=[line(qty="2", prod=q)])
    return p, q


@pytest.mark.parametrize("scope", ["unrestricted", "two_companies"])
def test_b1_invoiced_top_selling_reads_every_company_the_caller_may_read(db, scope):
    from app.services.sales.top_selling_invoiced import top_selling_invoiced

    p, q = _both_companies(db)
    grants = None if scope == "unrestricted" else frozenset({DEFAULT_COMPANY_ID, MOCHA_ID})
    set_company_scope(db, grants)
    body = top_selling_invoiced(
        db, rank_by="amount", n=None, direction="top", customer_ids=None, category_ids=None,
        sales_agent_ids=None, brand_ids=None, channel=None,
        date_from=date(2026, 1, 1), date_to=date(2026, 12, 31), dealer_scoped=False,
    )
    assert [(r["code"], r["amount"]) for r in body["rows"]] == [(p.product_code, 250.0), (q.product_code, 100.0)]
    assert body["totals"] == {"quantity": 7, "amount": 350.0}


def test_b1_a_single_company_scope_reads_only_that_company(db):
    from app.services.sales.top_selling_invoiced import top_selling_invoiced

    p, _q = _both_companies(db)
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    body = top_selling_invoiced(
        db, rank_by="amount", n=None, direction="top", customer_ids=None, category_ids=None,
        sales_agent_ids=None, brand_ids=None, channel=None,
        date_from=date(2026, 1, 1), date_to=date(2026, 12, 31), dealer_scoped=False,
    )
    assert [r["code"] for r in body["rows"]] == [p.product_code]


# ------------------------------------------------------------------ reviewer S2, S3


def test_s2_a_month_axis_sorts_in_month_order_not_by_its_labels(db):
    from tests._sales_unified_seed import run

    for month in (2, 4, 8, 12):
        doc(db, "cash_sale", "1.00", date(2026, month, 3))
    result = run(db, "sales_by_debtor_type", rows="month_of_year", cols="channel",
                 period={"kind": "custom", "from": "2026-01-01", "to": "2026-12-31"},
                 pivot_sort={"key": "__row__", "dir": "asc"})
    months = [f"{m:02d}" for m in range(1, 13)]  # a fixed axis prints every month
    assert list(result.layouts.summary.row_values) == months
    desc = run(db, "sales_by_debtor_type", rows="month_of_year", cols="channel",
               period={"kind": "custom", "from": "2026-01-01", "to": "2026-12-31"},
               pivot_sort={"key": "__row__", "dir": "desc"})
    assert list(desc.layouts.summary.row_values) == months[::-1]


def test_s3_top_selling_items_ranks_by_rm_by_default(db):
    from app.services.reports import engine
    from tests._sales_unified_seed import definition_of

    cheap_many, dear_few = product(db, company_id=DEFAULT_COMPANY_ID), product(db, company_id=DEFAULT_COMPANY_ID)
    doc(db, "invoice", "10.00", date(2026, 3, 1), lines=[line(qty="100", net="10.00", prod=cheap_many)])
    doc(db, "invoice", "900.00", date(2026, 3, 1), lines=[line(qty="1", net="900.00", prod=dear_few)])
    definition = definition_of("top_selling_items")
    params = {"date_basis": "order_date", "period": {"kind": "custom", "from": "2026-01-01", "to": "2026-12-31"}}
    result = engine.run(db, definition, params, company_grants=frozenset({DEFAULT_COMPANY_ID}))
    rows = list(result.layouts.summary.row_values)
    assert rows.index(f"{dear_few.product_code} - {dear_few.description}" if dear_few.description else dear_few.product_code) == 0
