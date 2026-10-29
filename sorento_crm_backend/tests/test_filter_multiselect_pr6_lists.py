"""FILTER-MULTISELECT PR6 (parties, plans, sample requests, stock debt snapshot): Parties Type, Plans State,
Sample requests Salesperson and Stock debt snapshot Decision take several values (OR within a filter);
comma-joined, repeated and single all read, and an unknown value is refused (422) per value. Red first;
Postgres only; every row seeded here.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.projects import ProjectParty
from app.models.project_so import DECISION_ACTIVE, DECISION_CHALLENGED, DECISION_SUPERSEDED
from app.models.stock_debt_snapshot import StockDebtSnapshot, StockDebtSnapshotRow
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._multi_filter_client import get, open_client
from tests._pg_fixture import blank_session
from tests.test_project_so_plans_list_route import (  # noqa: F401  (`world` is a pytest fixture)
    _agent,
    _core_so,
    _customer,
    _decision,
    _project_line,
    _project_so,
    _user,
    world as plans_world,
)
from tests.test_sample_requests_core import (  # noqa: F401  (`world` is a pytest fixture)
    SR,
    _draft,
    _submit,
    world as sample_world,
)

BASE = "/api/v1/project-sales"


def _uid() -> str:
    return str(uuid.uuid4())


# ---- Parties: Type -------------------------------------------------------------------------------------------

@pytest.fixture
def parties():
    with blank_session() as db:
        rows = {}
        for key in ("developer", "architect", "contractor"):
            row = ProjectParty(id=_uid(), company_id=DEFAULT_COMPANY_ID, party_type=key, name=f"ZZT-PTY {key} {_uid()[:6]}")
            db.add(row)
            rows[key] = row
        db.commit()
        yield db, rows


def _party_ids(db, monkeypatch, pairs):
    with open_client(db, monkeypatch) as (c, _a):
        resp = get(c, f"{BASE}/parties/", [("limit", 200), *pairs])
        assert resp.status_code == 200, resp.text
        return {r["id"] for r in resp.json()["data"]}


def test_parties_type_single_comma_and_repeated(parties, monkeypatch):
    db, r = parties
    ids = {k: v.id for k, v in r.items()}
    ours = set(ids.values())
    assert _party_ids(db, monkeypatch, [("party_type", "architect")]) & ours == {ids["architect"]}
    assert _party_ids(db, monkeypatch, [("party_type", "developer,contractor")]) & ours == {ids["developer"], ids["contractor"]}
    assert _party_ids(db, monkeypatch, [("party_type", "developer"), ("party_type", "architect")]) & ours == {ids["developer"], ids["architect"]}


def test_parties_type_and_across_with_search(parties, monkeypatch):
    db, r = parties
    got = _party_ids(db, monkeypatch, [("party_type", "developer,architect"), ("query", r["architect"].name)])
    assert got == {r["architect"].id}


# ---- Plans: State --------------------------------------------------------------------------------------------

@pytest.fixture
def plans(plans_world):
    w = plans_world
    db = w.db
    farah = _user(db, "zzt-plans Farah")
    out = {}
    for key, state in (("a", DECISION_ACTIVE), ("b", DECISION_SUPERSEDED), ("c", DECISION_CHALLENGED)):
        agent = _agent(db, f"ZZT-AGT-{_uid()[:4]}")
        core = _core_so(db, w.company_id, customer=_customer(db, f"zzt-plans {key}"), agent=agent)
        order = _project_so(db, w.project, so_id=core.id)
        line = _project_line(db, order, w.product)
        decision = _decision(
            db, order, revision_no=1, state=state, decided_by=farah,
            snapshots=[{"line_no": 10, "project_line_id": line.id, "components": [{"kind": "reserve", "qty": "1"}]}],
        )
        out[key] = (order, decision)
    db.commit()
    return db, out


def _plan_orders(db, monkeypatch, pairs):
    with open_client(db, monkeypatch) as (c, _a):
        resp = get(c, f"{BASE}/plans", [("limit", 200), *pairs])
        return resp


def test_plans_state_single_default_and_union(plans, monkeypatch):
    db, o = plans
    oid = {k: v[0].id for k, v in o.items()}

    def ids(*pairs):
        resp = _plan_orders(db, monkeypatch, list(pairs))
        assert resp.status_code == 200, resp.text
        return {r["project_sales_order_id"] for r in resp.json()["data"]} & set(oid.values())

    assert ids() == {oid["a"]}
    assert ids(("state", "superseded")) == {oid["b"]}
    assert ids(("state", "active,challenged")) == {oid["a"], oid["c"]}
    assert ids(("state", "superseded"), ("state", "challenged")) == {oid["b"], oid["c"]}
    assert ids(("state", "active,superseded,challenged")) == set(oid.values())


def test_plans_state_unknown_value_is_refused_per_value(plans, monkeypatch):
    db, _o = plans
    assert _plan_orders(db, monkeypatch, [("state", "active,bogus")]).status_code == 422


# ---- Sample requests: Salesperson, Status ---------------------------------------------------------------------

def _sent(w, user):
    rid = _draft(w, user=user)["id"]
    assert _submit(w, rid, user).status_code in (200, 201)
    return rid


def test_sample_requests_salesperson_union(sample_world):
    w = sample_world
    mine, theirs, admins = (_sent(w, u) for u in (w.sales, w.sales_b, w.admin))

    def ids(*pairs):
        res = w.api.as_(w.coord).get(SR, params=list(pairs))
        assert res.status_code == 200, res.text
        return {r["id"] for r in res.json()["data"]}

    assert ids(("salesperson_id", w.sales)) == {mine}
    assert ids(("salesperson_id", f"{w.sales},{w.sales_b}")) == {mine, theirs}
    assert ids(("salesperson_id", w.sales), ("salesperson_id", w.admin)) == {mine, admins}


def test_sample_requests_status_union_guard(sample_world):
    w = sample_world
    d = _draft(w, user=w.sales)["id"]
    s = _sent(w, w.sales)
    res = w.api.as_(w.sales).get(SR, params=[("status", "draft,submitted")])
    assert res.status_code == 200, res.text
    assert {d, s} <= {r["id"] for r in res.json()["data"]}


# ---- Stock debt snapshot rows: Decision ------------------------------------------------------------------------

@pytest.fixture
def snapshot():
    with blank_session() as db:
        snap = StockDebtSnapshot(
            id=_uid(), company_id=DEFAULT_COMPANY_ID, name="ZZT snap", filters={}, months=[], totals={}, row_count=4
        )
        db.add(snap)
        db.flush()
        rows = {}
        for i, decision in enumerate(("reserve", "buy", "ignore", None)):
            row = StockDebtSnapshotRow(
                id=_uid(), company_id=DEFAULT_COMPANY_ID, snapshot_id=snap.id, position=i,
                product_code=f"ZZT-SNP-{i}", product_name="x", row_data={
                    "product_id": _uid(), "product_code": f"ZZT-SNP-{i}", "months": [], "tba": 0, "undated": 0, "unlocated": 0,
                },
                lines=[], decision=decision,
            )
            db.add(row)
            rows[decision or "none"] = row
        db.commit()
        yield db, snap, rows


def _snap_rows(db, monkeypatch, snap, pairs):
    with open_client(db, monkeypatch) as (c, _a):
        return get(c, f"{BASE}/stock-debt/snapshots/{snap.id}/rows", [("limit", 200), *pairs])


def test_snapshot_decision_single_union_and_pseudo(snapshot, monkeypatch):
    db, snap, rows = snapshot

    def ids(*pairs):
        resp = _snap_rows(db, monkeypatch, snap, list(pairs))
        assert resp.status_code == 200, resp.text
        return {r["row_id"] for r in resp.json()["data"]}

    rid = {k: v.id for k, v in rows.items()}
    assert ids(("decision", "buy")) == {rid["buy"]}
    assert ids(("decision", "reserve,ignore")) == {rid["reserve"], rid["ignore"]}
    assert ids(("decision", "reserve"), ("decision", "buy")) == {rid["reserve"], rid["buy"]}
    assert ids(("decision", "undecided,reserve")) == {rid["none"], rid["reserve"]}
    assert ids(("decision", "decided")) == {rid["reserve"], rid["buy"], rid["ignore"]}


def test_snapshot_decision_unknown_value_is_refused(snapshot, monkeypatch):
    db, snap, _rows = snapshot
    assert _snap_rows(db, monkeypatch, snap, [("decision", "reserve,bogus")]).status_code == 422
