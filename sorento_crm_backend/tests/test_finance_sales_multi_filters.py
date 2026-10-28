"""FILTER-MULTISELECT PR3: Billing documents (Status, Customer, Agent; Type is already multi),
Opportunities (Stage, Agent, Customer) and Sales targets (Team) take several values (OR within a
filter, AND across). Red first; Postgres only; rows seeded here into a blank schema.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.models.finance import BillingDocument
from app.models.order import Customer
from app.models.sales import SalesOpportunity, SalesTarget, SalesTargetPeriod, SalesTeam, SalesTeamMember
from app.models.sales_agent import SalesAgent
from app.models.status import Status
from app.services.user_service import UserPermissionService
from tests._multi_filter_client import get, open_client
from tests._pg_fixture import blank_session, unique_code

BILLING = "/api/v1/finance/billing-documents"
OPPS = "/api/v1/sales/opportunities"
TARGETS = "/api/v1/sales/targets"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    from app.api.v1.sales import opportunities as opp_route

    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: {"admin"})
    monkeypatch.setattr(UserPermissionService, "get_user_permission_slugs", lambda self, uid: {opp_route.VIEW})
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


def _customer(db, label):
    row = Customer(id=str(uuid.uuid4()), customer_code=unique_code(label), customer_name=f"ZZT {label}")
    db.add(row)
    db.flush()
    return row


def _agent(db, label):
    row = SalesAgent(id=str(uuid.uuid4()), sales_agent=unique_code(label), description=f"ZZT {label}", is_active=True)
    db.add(row)
    db.flush()
    return row


# ---- Billing documents -------------------------------------------------------------------------------

def _doc(db, tag, label, dtype, status, customer, agent):
    row = BillingDocument(id=str(uuid.uuid4()), document_type=dtype, doc_no=f"{tag}-{label}", doc_date=date(2026, 6, 1),
                          customer_id=customer.id, agent_code=agent.sales_agent, status=status,
                          source_ref=unique_code("ref"))
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def docs(db):
    tag = unique_code("BD", alpha=True)
    c1, c2, c3 = _customer(db, "c1"), _customer(db, "c2"), _customer(db, "c3")
    a1, a2, a3 = _agent(db, "a1"), _agent(db, "a2"), _agent(db, "a3")
    return dict(
        tag=tag, c=(c1, c2, c3), a=(a1, a2, a3),
        r1=_doc(db, tag, "1", "invoice", "posted", c1, a1),
        r2=_doc(db, tag, "2", "credit_note", "cancelled", c2, a2),
        r3=_doc(db, tag, "3", "invoice", "posted", c3, a3),
        r4=_doc(db, tag, "4", "debit_note", "posted", c1, a2),
    )


def _bd(client, s, pairs):
    resp = get(client, BILLING, [("limit", 200), ("query", s["tag"]), *pairs])
    assert resp.status_code == 200, resp.text
    return {r["id"] for r in resp.json()["data"]}


def _ids(s, *keys):
    return {s[k].id for k in keys}


def test_billing_status_both_values_return_both(client, docs):
    s = docs
    assert _bd(client, s, [("status", "posted,cancelled")]) == _ids(s, "r1", "r2", "r3", "r4")
    assert _bd(client, s, [("status", "posted"), ("status", "cancelled")]) == _ids(s, "r1", "r2", "r3", "r4")


def test_billing_status_single_value_still_works(client, docs):
    s = docs
    assert _bd(client, s, [("status", "posted")]) == _ids(s, "r1", "r3", "r4")
    assert _bd(client, s, [("status", "cancelled")]) == _ids(s, "r2")


def test_billing_customer_union_single_and_repeated(client, docs):
    s = docs
    c1, c2, c3 = s["c"]
    assert _bd(client, s, [("customer_id", f"{c2.id},{c3.id}")]) == _ids(s, "r2", "r3")
    assert _bd(client, s, [("customer_id", c1.id)]) == _ids(s, "r1", "r4")
    assert _bd(client, s, [("customer_id", c2.id), ("customer_id", c3.id)]) == _ids(s, "r2", "r3")


def test_billing_malformed_customer_id_is_422(client, docs):
    s = docs
    assert get(client, BILLING, [("customer_id", "not-a-uuid")]).status_code == 422
    assert get(client, BILLING, [("customer_id", f"{s['c'][0].id},not-a-uuid")]).status_code == 422


def test_billing_agent_union_single_and_repeated(client, docs):
    s = docs
    a1, a2, a3 = s["a"]
    assert _bd(client, s, [("agent_code", f"{a1.sales_agent},{a3.sales_agent}")]) == _ids(s, "r1", "r3")
    assert _bd(client, s, [("agent_code", a2.sales_agent)]) == _ids(s, "r2", "r4")
    assert _bd(client, s, [("agent_code", a1.sales_agent), ("agent_code", a3.sales_agent)]) == _ids(s, "r1", "r3")


def test_billing_type_already_takes_several_values(client, docs):
    s = docs
    assert _bd(client, s, [("document_type", "invoice,debit_note")]) == _ids(s, "r1", "r3", "r4")
    assert _bd(client, s, [("document_type", "credit_note"), ("document_type", "debit_note")]) == _ids(s, "r2", "r4")


def test_billing_filters_and_across_each_other(client, docs):
    s = docs
    got = _bd(client, s, [("status", "posted,cancelled"), ("agent_code", f"{s['a'][1].sales_agent},{s['a'][2].sales_agent}"),
                          ("customer_id", f"{s['c'][0].id},{s['c'][1].id}")])
    assert got == _ids(s, "r2", "r4")


# ---- Opportunities -----------------------------------------------------------------------------------

def _stage(db, label):
    row = Status(id=str(uuid.uuid4()), entity_type="sales_opportunity", key=unique_code(label).lower(), label=f"ZZT {label}")
    db.add(row)
    db.flush()
    return row


def _opp(db, tag, label, stage, customer, agent):
    row = SalesOpportunity(id=str(uuid.uuid4()), opportunity_no=f"{tag}-{label}"[:20], title=f"ZZT {tag} {label}",
                           customer_id=customer.id, sales_agent_id=agent.id, status_id=stage.id,
                           expected_amount=Decimal("100.00"), expected_close_date=date(2026, 11, 1), source="crm")
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def opps(db):
    tag = unique_code("OP", alpha=True)
    st = (_stage(db, "s1"), _stage(db, "s2"), _stage(db, "s3"))
    c = (_customer(db, "c1"), _customer(db, "c2"), _customer(db, "c3"))
    a = (_agent(db, "a1"), _agent(db, "a2"), _agent(db, "a3"))
    return dict(
        tag=tag, st=st, c=c, a=a,
        r1=_opp(db, tag, "1", st[0], c[0], a[0]), r2=_opp(db, tag, "2", st[1], c[1], a[1]),
        r3=_opp(db, tag, "3", st[2], c[2], a[2]), r4=_opp(db, tag, "4", st[0], c[0], a[1]),
    )


def _op(client, s, pairs):
    resp = get(client, OPPS, [("limit", 200), ("query", s["tag"]), *pairs])
    assert resp.status_code == 200, resp.text
    return {r["id"] for r in resp.json()["data"]}


def test_opportunity_single_values_work_today(client, opps):
    s = opps
    assert _op(client, s, [("status_id", s["st"][0].id)]) == _ids(s, "r1", "r4")
    assert _op(client, s, [("sales_agent_id", s["a"][1].id)]) == _ids(s, "r2", "r4")
    assert _op(client, s, [("customer_id", s["c"][0].id)]) == _ids(s, "r1", "r4")


def test_opportunity_stage_union_single_and_repeated(client, opps):
    s = opps
    st = s["st"]
    assert _op(client, s, [("status_id", f"{st[1].id},{st[2].id}")]) == _ids(s, "r2", "r3")
    assert _op(client, s, [("status_id", st[0].id)]) == _ids(s, "r1", "r4")
    assert _op(client, s, [("status_id", st[1].id), ("status_id", st[2].id)]) == _ids(s, "r2", "r3")


def test_opportunity_agent_union_single_and_repeated(client, opps):
    s = opps
    a = s["a"]
    assert _op(client, s, [("sales_agent_id", f"{a[0].id},{a[2].id}")]) == _ids(s, "r1", "r3")
    assert _op(client, s, [("sales_agent_id", a[1].id)]) == _ids(s, "r2", "r4")
    assert _op(client, s, [("sales_agent_id", a[0].id), ("sales_agent_id", a[2].id)]) == _ids(s, "r1", "r3")


def test_opportunity_customer_union_single_and_repeated(client, opps):
    s = opps
    c = s["c"]
    assert _op(client, s, [("customer_id", f"{c[1].id},{c[2].id}")]) == _ids(s, "r2", "r3")
    assert _op(client, s, [("customer_id", c[0].id)]) == _ids(s, "r1", "r4")
    assert _op(client, s, [("customer_id", c[1].id), ("customer_id", c[2].id)]) == _ids(s, "r2", "r3")


def test_opportunity_filters_and_across_each_other(client, opps):
    s = opps
    got = _op(client, s, [("status_id", f"{s['st'][0].id},{s['st'][1].id}"),
                          ("sales_agent_id", f"{s['a'][1].id},{s['a'][2].id}"),
                          ("customer_id", f"{s['c'][0].id},{s['c'][1].id}")])
    assert got == _ids(s, "r2", "r4")


def test_opportunity_malformed_ids_are_422(client, opps):
    assert get(client, OPPS, [("status_id", "not-a-uuid")]).status_code == 422
    assert get(client, OPPS, [("customer_id", "not-a-uuid,x")]).status_code == 422


# ---- Sales targets: Team -----------------------------------------------------------------------------

def _team(db, label):
    row = SalesTeam(id=str(uuid.uuid4()), name=f"ZZT {label} {unique_code('t')}", is_active=True)
    db.add(row)
    db.flush()
    return row


def _target(db, n, team):
    row = SalesTarget(id=str(uuid.uuid4()), target_no=f"ZZT-{n}-{unique_code('n')[-6:]}"[:20], name=f"ZZT target {n}",
                      subject_kind="team", sales_team_id=team.id, metric="amount", basis="ordered", product_scope="all",
                      start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), commission_method="retroactive",
                      threshold_unit="pct", rounding="sen", tiers_per_period=False)
    db.add(row)
    db.flush()
    db.add(SalesTargetPeriod(id=str(uuid.uuid4()), target_id=row.id, period_start=date(2026, 1, 1),
                             period_end=date(2026, 12, 31), target_value=Decimal("1000")))
    db.flush()
    return row


@pytest.fixture
def targets(db):
    teams = (_team(db, "t1"), _team(db, "t2"), _team(db, "t3"))
    return dict(t=teams, r1=_target(db, 1, teams[0]), r2=_target(db, 2, teams[1]),
                r3=_target(db, 3, teams[2]), r4=_target(db, 4, teams[0]))


def _tg(client, pairs):
    resp = get(client, TARGETS, [("subject", "team"), ("all", "true"), *pairs])
    assert resp.status_code == 200, resp.text
    return {r["target_id"] for r in resp.json()["rows"]}


def _tids(s, *keys):
    return {s[k].id for k in keys}


def test_target_team_union_single_and_repeated(client, targets):
    s = targets
    t = s["t"]
    assert _tg(client, [("sales_team_id", f"{t[1].id},{t[2].id}")]) == _tids(s, "r2", "r3")
    assert _tg(client, [("sales_team_id", t[0].id)]) == _tids(s, "r1", "r4")
    assert _tg(client, [("sales_team_id", t[1].id), ("sales_team_id", t[2].id)]) == _tids(s, "r2", "r3")


def test_target_team_union_on_the_dated_view_too(client, targets):
    s = targets
    t = s["t"]
    resp = get(client, TARGETS, [("subject", "team"), ("on", "2026-06-15"), ("sales_team_id", f"{t[1].id},{t[2].id}")])
    assert resp.status_code == 200, resp.text
    got = {r["target_id"] for r in resp.json()["rows"] if r.get("target_id")}
    assert got == _tids(s, "r2", "r3")


def test_target_malformed_team_id_is_422(client, targets):
    s = targets
    assert get(client, TARGETS, [("sales_team_id", "not-a-uuid")]).status_code == 422
    assert get(client, TARGETS, [("sales_team_id", f"{s['t'][0].id},not-a-uuid")]).status_code == 422


def test_target_single_team_works_today(client, targets):
    s = targets
    assert _tg(client, [("sales_team_id", s["t"][0].id)]) == _tids(s, "r1", "r4")


# The Agents tab filters agents by their team today, with "none" meaning agents in no team.

def _agent_target(db, n, agent):
    row = SalesTarget(id=str(uuid.uuid4()), target_no=f"ZZT-A{n}-{unique_code('n')[-5:]}"[:20], name=f"ZZT agent target {n}",
                      subject_kind="agent", sales_agent_id=agent.id, metric="amount", basis="ordered", product_scope="all",
                      start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), commission_method="retroactive",
                      threshold_unit="pct", rounding="sen", tiers_per_period=False)
    db.add(row)
    db.flush()
    db.add(SalesTargetPeriod(id=str(uuid.uuid4()), target_id=row.id, period_start=date(2026, 1, 1),
                             period_end=date(2026, 12, 31), target_value=Decimal("1000")))
    db.flush()
    return row


@pytest.fixture
def agent_targets(db):
    t1, t2 = _team(db, "t1"), _team(db, "t2")
    a1, a2, a3 = _agent(db, "a1"), _agent(db, "a2"), _agent(db, "a3")
    for team, agent in ((t1, a1), (t2, a2)):
        db.add(SalesTeamMember(id=str(uuid.uuid4()), sales_team_id=team.id, sales_agent_id=agent.id))
    db.flush()
    return dict(t=(t1, t2), r1=_agent_target(db, 1, a1), r2=_agent_target(db, 2, a2), r3=_agent_target(db, 3, a3))


def _ag(client, pairs):
    resp = get(client, TARGETS, [("subject", "agent"), ("all", "true"), *pairs])
    assert resp.status_code == 200, resp.text
    return {r["target_id"] for r in resp.json()["rows"]}


def test_agent_tab_team_union_single_and_repeated(client, agent_targets):
    s = agent_targets
    t1, t2 = s["t"]
    assert _ag(client, [("sales_team_id", t1.id)]) == _tids(s, "r1")
    assert _ag(client, [("sales_team_id", f"{t1.id},{t2.id}")]) == _tids(s, "r1", "r2")
    assert _ag(client, [("sales_team_id", t1.id), ("sales_team_id", t2.id)]) == _tids(s, "r1", "r2")


def test_agent_tab_no_team_pseudo_value_or_combines_with_a_team(client, agent_targets):
    s = agent_targets
    assert _ag(client, [("sales_team_id", "none")]) == _tids(s, "r3")
    assert _ag(client, [("sales_team_id", f"none,{s['t'][0].id}")]) == _tids(s, "r3", "r1")
