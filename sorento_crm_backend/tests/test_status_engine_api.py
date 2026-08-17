"""S1 gate — status engine routes (happy path, auth denial, validation).

Runs against a real Postgres session in a rolled-back transaction, so the graph
these tests build never escapes. Rows are marker-prefixed (``zzt_``) and cleanup is
scoped to them: this database is a copy of production data and an unscoped DELETE
in a fixture has destroyed real rows here before.
"""
from __future__ import annotations

import uuid
from typing import Iterator

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.main import app
from app.services.user_service import UserPermissionService
from app.status_engine import registry as status_registry

ENTITY = "zzt_api_pipeline"
BASE = "/api/v1/system"


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def db() -> Iterator[Session]:
    """One session shared with the route, rolled back at the end."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(autouse=True)
def _cleanup():
    """Marker-scoped cleanup, before and after. Never unscoped."""
    def _purge():
        with SessionLocal() as s:
            s.execute(
                text(
                    "DELETE FROM status_transitions WHERE entity_type LIKE 'zzt\\_%' ESCAPE '\\'"
                )
            )
            s.execute(
                text("DELETE FROM statuses WHERE entity_type LIKE 'zzt\\_%' ESCAPE '\\'")
            )
            s.commit()

    _purge()
    # Force the lazy module discovery before snapshotting; see the matching fixture
    # in test_status_engine.py for why an empty snapshot poisons the whole session.
    status_registry.list_status_entities()
    saved = dict(status_registry._REGISTRY)
    yield
    status_registry._REGISTRY.clear()
    status_registry._REGISTRY.update(saved)
    _purge()


@pytest.fixture
def client(db, monkeypatch) -> Iterator[TestClient]:
    def _db():
        yield db

    user = {"id": "zzt-admin"}
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_or_api_key] = lambda: user
    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


def _create_status(client, key, label, **kw):
    payload = {"entity_type": ENTITY, "key": key, "label": label, **kw}
    r = client.post(f"{BASE}/statuses", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _ladder(client):
    registered = _create_status(client, "registered", "Registered", is_initial=True, sort_order=0)
    quoted = _create_status(client, "quoted", "Quoted", sort_order=1)
    won = _create_status(client, "po_received", "PO Received", sort_order=2, is_terminal=True)
    r = client.post(
        f"{BASE}/status-transitions",
        json={
            "entity_type": ENTITY,
            "from_status_id": registered["id"],
            "to_status_id": quoted["id"],
            "label": "Quote issued",
        },
    )
    assert r.status_code == 201, r.text
    return registered, quoted, won


# ------------------------------------------------------------- happy path


def test_create_status_and_read_graph(client):
    registered, quoted, won = _ladder(client)

    r = client.get(f"{BASE}/statuses/graph/{ENTITY}")
    assert r.status_code == 200
    body = r.json()
    assert body["entity_type"] == ENTITY
    assert body["is_fork"] is False
    assert body["resolved_scope_id"] is None
    assert [s["key"] for s in body["statuses"]] == ["registered", "quoted", "po_received"]
    assert [t["label"] for t in body["transitions"]] == ["Quote issued"]


def test_graph_of_unforked_scope_falls_back_to_default(client):
    _ladder(client)
    scope = _uid()
    r = client.get(f"{BASE}/statuses/graph/{ENTITY}", params={"scope_id": scope})
    assert r.status_code == 200
    body = r.json()
    # The admin UI needs to distinguish "this template's own graph" from "the
    # default it inherits", because editing the default hits every inheritor.
    assert body["requested_scope_id"] == scope
    assert body["resolved_scope_id"] is None
    assert body["is_fork"] is False


def test_update_status_label(client):
    registered, _, _ = _ladder(client)
    r = client.patch(f"{BASE}/statuses/{registered['id']}", json={"label": "Claimed"})
    assert r.status_code == 200
    assert r.json()["label"] == "Claimed"


def test_delete_status_removes_it_and_its_edges(client):
    registered, quoted, won = _ladder(client)
    # Deleting `quoted` cascades the registered->quoted edge.
    r = client.delete(f"{BASE}/statuses/{quoted['id']}")
    assert r.status_code == 204, r.text
    body = client.get(f"{BASE}/statuses/graph/{ENTITY}").json()
    assert [s["key"] for s in body["statuses"]] == ["registered", "po_received"]
    assert body["transitions"] == []


def test_graph_with_counts_reports_zero_for_unregistered_entity(client):
    _ladder(client)
    r = client.get(f"{BASE}/statuses/graph/{ENTITY}", params={"with_counts": True})
    assert r.status_code == 200
    assert all(s["record_count"] == 0 for s in r.json()["statuses"])


def test_status_entities_endpoint_lists_registered_entities(client):
    from app.status_engine.registry import StatusEntity, register_status_entity

    register_status_entity(
        StatusEntity(
            entity_type=ENTITY,
            label="Zzt Pipeline",
            module="zzt",
            count_records=lambda db, s: 0,
            migrate_records=lambda db, f, t: 0,
            scope_resolver=lambda rec: None,
            scope_label="Template",
        )
    )
    r = client.get(f"{BASE}/status-entities")
    assert r.status_code == 200
    row = next(x for x in r.json() if x["entity_type"] == ENTITY)
    assert row["label"] == "Zzt Pipeline"
    assert row["supports_scoped_graphs"] is True


def test_transition_update_and_delete(client):
    registered, quoted, _ = _ladder(client)
    edge = client.get(f"{BASE}/statuses/graph/{ENTITY}").json()["transitions"][0]

    r = client.patch(f"{BASE}/status-transitions/{edge['id']}", json={"label": "Quoted it"})
    assert r.status_code == 200
    assert r.json()["label"] == "Quoted it"

    r = client.delete(f"{BASE}/status-transitions/{edge['id']}")
    assert r.status_code == 204
    assert client.get(f"{BASE}/statuses/graph/{ENTITY}").json()["transitions"] == []


# -------------------------------------------------------------- validation


def test_second_initial_status_is_rejected(client):
    _ladder(client)
    r = client.post(
        f"{BASE}/statuses",
        json={"entity_type": ENTITY, "key": "other", "label": "Other", "is_initial": True},
    )
    assert r.status_code == 422
    assert r.json()["message"] == (
        "Only one status can be the starting state. Found: Other, Registered."
    )


def test_duplicate_key_in_the_same_graph_is_rejected_readably(client):
    """Two layers here, and both matter.

    The NULLS NOT DISTINCT index is the guarantee (without it, two default-graph
    rows with the same key would both insert). But on its own it surfaces to the
    admin as a 500 quoting a Postgres constraint name, so the route pre-checks and
    returns a sentence.
    """
    _create_status(client, "registered", "Registered", is_initial=True)
    r = client.post(
        f"{BASE}/statuses", json={"entity_type": ENTITY, "key": "registered", "label": "Dup"}
    )
    assert r.status_code == 422
    assert r.json()["code"] == "status_key_duplicate"
    assert r.json()["message"] == (
        "A status with the key 'registered' already exists in the default graph."
    )


def test_renaming_a_key_onto_an_existing_one_is_rejected(client):
    registered, quoted, _ = _ladder(client)
    r = client.patch(f"{BASE}/statuses/{quoted['id']}", json={"key": "registered"})
    assert r.status_code == 422
    assert r.json()["code"] == "status_key_duplicate"


def test_a_fork_may_reuse_a_key_the_default_already_uses(client):
    """The flip side: the same rung in a forked graph MUST keep the same key, or
    cross-graph roll-ups break."""
    _create_status(client, "registered", "Registered", is_initial=True)
    scope = _uid()
    r = client.post(
        f"{BASE}/statuses",
        json={
            "entity_type": ENTITY,
            "key": "registered",
            "label": "Registered",
            "is_initial": True,
            "scope_id": scope,
        },
    )
    assert r.status_code == 201, r.text


def test_auto_transition_without_conditions_is_rejected(client):
    registered, quoted, _ = _ladder(client)
    r = client.post(
        f"{BASE}/status-transitions",
        json={
            "entity_type": ENTITY,
            "from_status_id": registered["id"],
            "to_status_id": quoted["id"],
            "label": "Auto",
            "trigger_mode": "auto",
        },
    )
    assert r.status_code == 422
    assert r.json()["code"] == "status_auto_needs_conditions"


def test_self_loop_transition_is_rejected(client):
    registered, _, _ = _ladder(client)
    r = client.post(
        f"{BASE}/status-transitions",
        json={
            "entity_type": ENTITY,
            "from_status_id": registered["id"],
            "to_status_id": registered["id"],
            "label": "Nowhere",
        },
    )
    assert r.status_code == 422
    assert r.json()["code"] == "status_self_loop"


def test_transition_out_of_a_terminal_status_is_rejected(client):
    registered, _, won = _ladder(client)
    r = client.post(
        f"{BASE}/status-transitions",
        json={
            "entity_type": ENTITY,
            "from_status_id": won["id"],
            "to_status_id": registered["id"],
            "label": "Reopen",
        },
    )
    assert r.status_code == 422
    assert r.json()["code"] == "status_terminal_has_outgoing"


def test_unknown_status_returns_404(client):
    r = client.patch(f"{BASE}/statuses/{_uid()}", json={"label": "x"})
    assert r.status_code == 404
    assert r.json()["code"] == "status_not_found"


def test_migrate_into_the_same_status_is_rejected(client):
    registered, _, _ = _ladder(client)
    r = client.post(
        f"{BASE}/statuses/{registered['id']}/migrate-records",
        json={"to_status_id": registered["id"]},
    )
    assert r.status_code == 422
    assert r.json()["code"] == "status_migrate_same"


def test_delete_blocked_while_records_hold_the_status(client):
    """AC-B5 end to end through the route."""
    from app.status_engine.registry import StatusEntity, register_status_entity

    registered, quoted, _ = _ladder(client)
    register_status_entity(
        StatusEntity(
            entity_type=ENTITY,
            label="Zzt Pipeline",
            module="zzt",
            count_records=lambda db, s, _target=quoted["id"]: 3 if s == _target else 0,
            migrate_records=lambda db, f, t: 3,
        )
    )
    r = client.delete(f"{BASE}/statuses/{quoted['id']}")
    assert r.status_code == 422
    assert r.json()["code"] == "status_in_use"
    assert r.json()["message"] == "3 records still use 'Quoted'. Move them to another status first."

    # ...and the count surfaces in the graph read, so the UI can warn first.
    body = client.get(f"{BASE}/statuses/graph/{ENTITY}", params={"with_counts": True}).json()
    assert next(s for s in body["statuses"] if s["key"] == "quoted")["record_count"] == 3


# ------------------------------------------------------------ auth denial


def test_routes_require_a_principal(client):
    def _deny():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[get_current_user_or_api_key] = _deny
    assert client.get(f"{BASE}/statuses/graph/{ENTITY}").status_code == 401
    assert client.get(f"{BASE}/status-entities").status_code == 401


def test_writes_require_the_edit_permission(client, monkeypatch):
    """view must not imply edit: configuring a graph changes what every record of
    that entity can legally do."""
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug == "system.statuses.view",
    )
    r = client.post(
        f"{BASE}/statuses", json={"entity_type": ENTITY, "key": "k", "label": "L"}
    )
    assert r.status_code == 403
    # ...while reads still work.
    assert client.get(f"{BASE}/statuses/graph/{ENTITY}").status_code == 200
