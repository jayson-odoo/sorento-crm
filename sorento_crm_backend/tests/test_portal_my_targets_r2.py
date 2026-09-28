"""Fix lane round 2, F2: the logging agent's own target progress on the portal.

Owner ruling (PR #1296, 27 Sep): "how do i see my target here, like what's my target, gap to
the target, and how can my opportunity help me to reach it? ... the target also got end date,
so by that date I need to hit 100k, so my sales oportuniteis before the date should help me
hit 100k".

`GET /api/v1/public/portal/sales-opportunities/my-targets` answers, per active agent target
of the contact's agent: the target (whole range, every period summed), achieved so far (S1's
own `achievement_service.achieved_by_period`, never a copy), the gap, and the agent's OPEN
opportunities whose expected close date is on or before the target's end date, with what they
would add if won (expected amount for an amount target, the lines' quantity for a quantity
target), the projected total and what is still short.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.main import app  # noqa: F401,E402  (first app import, see the S2 portal tests)

from tests._pg_fixture import blank_session
from tests.test_portal_sales_opportunities_s2 import (
    _agent,
    _contact,
    _grant_kind,
    _portal_client,
    _product,
    _seed,
    _sorento,
    _status_id,
    _uid,
)

URL = "/api/v1/public/portal/sales-opportunities/my-targets"
TODAY = date(2026, 9, 27)


@pytest.fixture(autouse=True)
def _fixed_today(monkeypatch):
    from app.services.sales import target_service

    monkeypatch.setattr(target_service, "_today", lambda: TODAY)


def _target(db, company_id, agent_id, *, name="ZZT Q4", metric="amount", start, end, value):
    from app.services.sales import target_service
    from app.schemas.sales import SalesTargetCreate

    payload = SalesTargetCreate(
        subject_kind="agent", sales_agent_id=agent_id, name=name, metric=metric,
        basis="ordered", product_scope="all", start_date=start, end_date=end, target_value=value,
    )
    target = target_service.create_target(db, payload)
    db.flush()
    return target


def _order(db, company_id, agent_id, product_id, *, order_date, line_total, qty=1):
    from app.models.order import SalesOrder, SalesOrderLine

    so = SalesOrder(
        id=_uid(), company_id=company_id, so_number=f"ZZT{_uid()[:8]}", order_date=order_date,
        status="open", sales_agent_id=agent_id,
    )
    db.add(so)
    db.flush()
    db.add(SalesOrderLine(
        id=_uid(), company_id=company_id, sales_order_id=so.id, product_id=product_id,
        qty_ordered=qty, qty_delivered=0, line_total=Decimal(str(line_total)), line_status="open",
    ))
    db.flush()


def _opp(db, company_id, agent_id, *, amount, close, outcome="open", lines=()):
    from app.models.sales import SalesOpportunity, SalesOpportunityLine

    opp = SalesOpportunity(
        id=_uid(), company_id=company_id, opportunity_no=f"ZZT-{_uid()[:6]}", title=f"ZZT {amount}",
        prospect_name="ZZT Prospect", sales_agent_id=agent_id, outcome=outcome,
        expected_amount=Decimal(str(amount)), expected_close_date=close, source="portal", status_id=_status_id(db, "new"),
    )
    db.add(opp)
    db.flush()
    for i, (product_id, qty) in enumerate(lines):
        db.add(SalesOpportunityLine(
            id=_uid(), company_id=company_id, opportunity_id=opp.id, product_id=product_id,
            qty=Decimal(str(qty)), sort_order=i,
        ))
    db.flush()
    return opp


def _setup(db):
    _seed(db)
    company_id = _sorento(db)
    contact = _contact(db)
    _grant_kind(db, contact.id)
    agent = _agent(db, contact_id=contact.id, company_id=company_id)
    return company_id, contact, agent


def test_f2_amount_target_achieved_gap_and_open_opportunities_before_the_end_date():
    with blank_session() as db:
        company_id, contact, agent = _setup(db)
        other = _agent(db, company_id=company_id)
        product = _product(db)
        target = _target(db, company_id, agent.id, start=date(2026, 9, 1), end=date(2026, 10, 31),
                         value=100000)
        _order(db, company_id, agent.id, product.id, order_date=date(2026, 9, 10), line_total=40000)
        _order(db, company_id, agent.id, product.id, order_date=date(2026, 8, 31), line_total=5000)  # before start
        _order(db, company_id, other.id, product.id, order_date=date(2026, 9, 12), line_total=7000)  # other agent
        a = _opp(db, company_id, agent.id, amount=20000, close=date(2026, 10, 10))
        b = _opp(db, company_id, agent.id, amount=15000, close=date(2026, 10, 18))
        c = _opp(db, company_id, agent.id, amount=10000, close=date(2026, 10, 31))  # on the end date counts
        _opp(db, company_id, agent.id, amount=99000, close=date(2026, 11, 1))  # after the end date
        _opp(db, company_id, agent.id, amount=88000, close=date(2026, 10, 5), outcome="won")
        _opp(db, company_id, agent.id, amount=77000, close=date(2026, 10, 5), outcome="lost")
        _opp(db, company_id, other.id, amount=66000, close=date(2026, 10, 5))  # another agent's

        with _portal_client(db, contact.id) as client:
            res = client.get(URL)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["today"] == "2026-09-27"
        assert len(body["targets"]) == 1
        row = body["targets"][0]
        assert row["target_id"] == target.id
        assert row["name"] == "ZZT Q4"
        assert row["metric"] == "amount"
        assert row["counts_label"] == "Ordered"
        assert row["scope_labels"] == []
        assert row["start_date"] == "2026-09-01"
        assert row["end_date"] == "2026-10-31"
        assert float(row["target_value"]) == 100000
        assert float(row["achieved_value"]) == 40000
        assert float(row["gap_value"]) == 60000
        assert float(row["pipeline_value"]) == 45000
        assert float(row["projected_value"]) == 85000
        assert float(row["short_value"]) == 15000
        assert [o["id"] for o in row["opportunities"]] == [a.id, b.id, c.id]  # by close date
        first = row["opportunities"][0]
        assert first["opportunity_no"] == a.opportunity_no
        assert first["customer_or_prospect"] == "ZZT Prospect"
        assert first["expected_close_date"] == "2026-10-10"
        assert float(first["value"]) == 20000
        assert first["stage_label"]


def test_f2_target_reached_leaves_nothing_short_and_gap_never_negative():
    with blank_session() as db:
        company_id, contact, agent = _setup(db)
        product = _product(db)
        _target(db, company_id, agent.id, start=date(2026, 9, 1), end=date(2026, 9, 30), value=1000)
        _order(db, company_id, agent.id, product.id, order_date=date(2026, 9, 2), line_total=1500)
        with _portal_client(db, contact.id) as client:
            row = client.get(URL).json()["targets"][0]
        assert float(row["gap_value"]) == 0
        assert float(row["short_value"]) == 0
        assert float(row["projected_value"]) == 1500


def test_f2_quantity_target_counts_the_lines_quantity():
    with blank_session() as db:
        company_id, contact, agent = _setup(db)
        product = _product(db)
        _target(db, company_id, agent.id, metric="quantity", start=date(2026, 9, 1),
                end=date(2026, 12, 31), value=150)
        _order(db, company_id, agent.id, product.id, order_date=date(2026, 9, 3), line_total=10, qty=120)
        _opp(db, company_id, agent.id, amount=9999, close=date(2026, 11, 1), lines=[(product.id, 25), (product.id, 15)])
        with _portal_client(db, contact.id) as client:
            row = client.get(URL).json()["targets"][0]
        assert float(row["achieved_value"]) == 120
        assert float(row["pipeline_value"]) == 40
        assert float(row["short_value"]) == 0


def test_f2_only_the_agents_own_active_targets():
    with blank_session() as db:
        company_id, contact, agent = _setup(db)
        other = _agent(db, company_id=company_id)
        _target(db, company_id, agent.id, name="ZZT Now", start=date(2026, 9, 1), end=date(2026, 10, 31), value=1)
        _target(db, company_id, agent.id, name="ZZT Ended", start=date(2026, 7, 1), end=date(2026, 8, 31), value=1)
        _target(db, company_id, agent.id, name="ZZT Later", start=date(2026, 11, 1), end=date(2026, 11, 30), value=1)
        _target(db, company_id, other.id, name="ZZT Theirs", start=date(2026, 9, 1), end=date(2026, 10, 31), value=1)
        with _portal_client(db, contact.id) as client:
            names = [t["name"] for t in client.get(URL).json()["targets"]]
        assert names == ["ZZT Now"]


def test_f2_no_target_is_an_empty_list_not_an_error():
    with blank_session() as db:
        company_id, contact, agent = _setup(db)
        with _portal_client(db, contact.id) as client:
            res = client.get(URL)
        assert res.status_code == 200, res.text
        assert res.json()["targets"] == []


def test_f2_same_gates_as_the_opportunity_routes():
    with blank_session() as db:
        _seed(db)
        contact = _contact(db)
        with _portal_client(db, contact.id) as client:
            res = client.get(URL)
        assert res.status_code == 403, res.text
        assert "FORM_TYPE_NOT_VISIBLE" in res.text
        _grant_kind(db, contact.id)
        with _portal_client(db, contact.id) as client:
            res = client.get(URL)
        assert res.status_code == 403, res.text
        assert "NOT_A_SALES_AGENT" in res.text
