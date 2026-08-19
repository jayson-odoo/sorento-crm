"""The agent's ownership group over HTTP - PLAN-demo-followups-19aug-ladder-v2.md C3.

    PATCH /api/v1/master-data/sales-agents/{id}/annotation   body: {"location_group": ...}

Same harness as `test_sales_agents_master_api.py` (blank scratch schema, `ZZT`-marked rows),
scoped to the one field that file's `RESPONSE_KEYS` did not yet know about. Three things:

1. `location_group` is on the wire, both directions - set it, get it back, and it survives a
   save that touches a DIFFERENT field (the `write_*` omitted-vs-null distinction the other
   two annotations already have).
2. It is upper/trim-normalised the same way an agent CODE is (`sales_agent_service.
   normalize_code`), so a planner typing `bb` still lands on the group the warehouse suffix
   (`BRW-BB`) actually carries.
3. Sending `null` clears it - unlike `demand_class`, there is no closed vocabulary to refuse,
   so the only failure mode worth pinning is "did it actually unset".
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.models.sales_agent import SalesAgent
from tests._pg_fixture import blank_session, unique_code

BASE = "/api/v1/master-data/sales-agents"
_USER = {"id": str(uuid.uuid4()), "email": "captain@example.test", "role": "admin"}

VIEW = "master_data.sales_agents.view"
EDIT = "master_data.sales_agents.edit"


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


@pytest.fixture
def client(db, monkeypatch):
    from app.main import app
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.services.user_service import UserPermissionService

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[get_current_user_or_api_key] = lambda: _USER
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in {VIEW, EDIT},
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed(db, **kwargs) -> SalesAgent:
    row = SalesAgent(
        id=str(uuid.uuid4()),
        sales_agent=kwargs.pop("sales_agent", unique_code("AGENT")),
        source=kwargs.pop("source", "manual"),
        is_active=kwargs.pop("is_active", True),
        **kwargs,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_it_is_declared_on_the_wire(client, db):
    _seed(db, sales_agent="ZZT LOCGROUP LIST", location_group="BB")

    row = client.get(BASE, params={"query": "ZZT LOCGROUP LIST"}).json()["data"][0]
    assert row["location_group"] == "BB"


def test_patch_sets_it_normalised(client, db):
    agent = _seed(db, sales_agent="ZZT LOCGROUP SET")

    res = client.patch(f"{BASE}/{agent.id}/annotation", json={"location_group": "  bb  "})
    assert res.status_code == 200, res.text
    assert res.json()["location_group"] == "BB"

    db.expire_all()
    assert (
        db.query(SalesAgent).filter(SalesAgent.id == agent.id).one().location_group == "BB"
    )


def test_patch_clears_it(client, db):
    agent = _seed(db, sales_agent="ZZT LOCGROUP CLEAR", location_group="BB")

    res = client.patch(f"{BASE}/{agent.id}/annotation", json={"location_group": None})
    assert res.status_code == 200, res.text
    assert res.json()["location_group"] is None

    db.expire_all()
    assert db.query(SalesAgent).filter(SalesAgent.id == agent.id).one().location_group is None


def test_an_all_blank_group_clears_it_too(client, db):
    agent = _seed(db, sales_agent="ZZT LOCGROUP BLANK", location_group="BB")

    res = client.patch(f"{BASE}/{agent.id}/annotation", json={"location_group": "   "})
    assert res.status_code == 200, res.text
    assert res.json()["location_group"] is None


def test_omitting_it_leaves_it_alone(client, db):
    agent = _seed(db, sales_agent="ZZT LOCGROUP KEEP", location_group="BB")

    res = client.patch(
        f"{BASE}/{agent.id}/annotation", json={"person_label": "ZZT Someone"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["location_group"] == "BB"


def test_setting_it_does_not_disturb_the_demand_class(client, db):
    from app.services.scm.demand_class import PROJECT

    agent = _seed(db, sales_agent="ZZT LOCGROUP SIDE", demand_class=PROJECT)

    res = client.patch(f"{BASE}/{agent.id}/annotation", json={"location_group": "HP"})
    assert res.status_code == 200, res.text
    assert res.json()["demand_class"] == PROJECT
    assert res.json()["location_group"] == "HP"
