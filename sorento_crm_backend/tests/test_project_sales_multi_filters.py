"""FILTER-MULTISELECT PR6 (project sales): Divergences State (and the broken "Any": no state param is every
state) and Fulfilment planning Review state take several values (OR within a filter), comma-joined,
repeated and single; an unknown value is refused. Red first; Postgres only; rows seeded here into a
blank schema.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.base import company_scope
from app.models.project_so import ProjectSODivergence
from app.services import project_seed_service
from app.services.project_so_adoption_service import ProjectSOAdoptionService
from tests._multi_filter_client import SORENTO, get, ok_ids, open_client
from tests._pg_fixture import blank_session
from tests.test_fulfilment_planning_worklist import (
    _authored_line,
    _authored_order,
    _project,
    _user,
)
from tests.test_project_so_adoption import (
    _core_line,
    _core_order,
    _product,
    _sorento,
    _warehouse,
)

BASE = "/api/v1/project-sales"


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


# ---- Divergences: State, and "Any" = no state param ---------------------------------------------------------

@pytest.fixture
def divergences(db):
    company_id = _sorento(db)
    project_seed_service.run(db, company_id=company_id)
    rows = {}
    with company_scope(db, frozenset({company_id})):
        owner = _user(db)
        product = _product(db)
        for key, status in (("a", "open"), ("b", "resolved"), ("c", "open"), ("d", "resolved")):
            project = _project(db, company_id, owner)
            order = _authored_order(db, project)
            _authored_line(db, order, product)
            div = ProjectSODivergence(
                id=_uid(), company_id=company_id, project_sales_order_id=order.id, status=status,
                autocount_doc_no=f"ZZT-{key}",
            )
            db.add(div)
            db.flush()
            rows[key] = div
    db.commit()
    return rows


def test_divergences_open_is_still_the_filter_when_asked_for(client, divergences):
    s = divergences
    assert ok_ids(get(client, f"{BASE}/divergences", [("status", "open")])) == {s["a"].id, s["c"].id}
    assert ok_ids(get(client, f"{BASE}/divergences", [("status", "resolved")])) == {s["b"].id, s["d"].id}


def test_divergences_any_is_every_state(client, divergences):
    # Today an absent state still means "open" server-side, so the screen's "Any" shows open only.
    s = divergences
    assert ok_ids(get(client, f"{BASE}/divergences", [])) == {s[k].id for k in "abcd"}


def test_divergences_several_states_are_a_union(client, divergences):
    s = divergences
    assert ok_ids(get(client, f"{BASE}/divergences", [("status", "open,resolved")])) == {s[k].id for k in "abcd"}
    got = ok_ids(get(client, f"{BASE}/divergences", [("status", "open"), ("status", "resolved")]))
    assert got == {s[k].id for k in "abcd"}


def test_divergences_unknown_state_is_refused(client, divergences):
    assert get(client, f"{BASE}/divergences", [("status", "open,bogus")]).status_code == 422


# ---- Fulfilment planning: Review state --------------------------------------------------------------------

@pytest.fixture
def planning(db):
    company_id = _sorento(db)
    project_seed_service.run(db, company_id=company_id)
    with company_scope(db, frozenset({company_id})):
        owner = _user(db)
        project = _project(db, company_id, owner)
        product = _product(db)
        warehouse = _warehouse(db, company_id)
        unplanned = _core_order(db, company_id)
        _core_line(db, unplanned, product, warehouse=warehouse)
        planned = _core_order(db, company_id)
        _core_line(db, planned, product, warehouse=warehouse)
        authored = _authored_order(db, project)
        _authored_line(db, authored, product)
        db.flush()
        ProjectSOAdoptionService(db).adopt(planned.id, actor_user_id=None)
        db.flush()
    db.commit()
    return dict(not_started=unplanned.so_number, needs_cs_review=planned.so_number, authored=authored.id)


def _states(client, pairs):
    resp = get(client, f"{BASE}/fulfilment-planning", [("limit", 100), *pairs])
    assert resp.status_code == 200, resp.text
    return {r["review_state"] for r in resp.json()["data"]}


def test_planning_review_state_single(client, planning):
    assert _states(client, [("review_state", "not_started")]) == {"not_started"}
    assert _states(client, []) == {"not_started", "needs_cs_review", "awaiting_reconciliation"}


def test_planning_review_state_union_comma_and_repeated(client, planning):
    assert _states(client, [("review_state", "not_started,needs_cs_review")]) == {"not_started", "needs_cs_review"}
    got = _states(client, [("review_state", "needs_cs_review"), ("review_state", "awaiting_reconciliation")])
    assert got == {"needs_cs_review", "awaiting_reconciliation"}


def test_planning_review_state_total_counts_the_union(client, planning):
    resp = get(client, f"{BASE}/fulfilment-planning", [("review_state", "not_started,awaiting_reconciliation")])
    assert resp.status_code == 200, resp.text
    assert resp.json()["pagination"]["total"] == 2


def test_planning_review_state_unknown_is_refused(client, planning):
    assert get(client, f"{BASE}/fulfilment-planning", [("review_state", "not_started,bogus")]).status_code == 422
