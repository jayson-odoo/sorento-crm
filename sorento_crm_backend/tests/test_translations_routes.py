"""System Management > Translations - list/update/delete routes (AC-G4, purchasing
consolidation batch, lane C).

Postgres only, on a blank schema (`tests._pg_fixture.blank_session`) - CI's database is
empty, nothing borrowed from an existing row. `response_model` silently drops an
undeclared field (LESSONS-LEARNT), so every field the UAC names is asserted by name,
not just "the row came back".
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be the first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.translation_memory import TranslationMemory
from app.models.user import User, UserRole, UserRoleAssignment
from tests._pg_fixture import blank_session

BASE = "/api/v1/system/translations"


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def client():
    from fastapi import Depends

    from app.database import get_db
    from app.dependencies import get_current_user

    with blank_session() as db:
        # The list/update/delete routes enforce a permission against the acting
        # user; a superadmin role short-circuits the check true.
        role = UserRole(
            id=str(uuid.uuid4()), slug="superadmin", name="ZZT Superadmin",
            description="", is_protected=True, is_default=False,
        )
        actor = User(id=_uid(), email=f"zzt-actor-{_uid()[:8]}@example.test", name="Ada Actor")
        db.add_all([role, actor])
        db.flush()
        db.add(UserRoleAssignment(user_id=actor.id, role_id=role.id))
        db.flush()
        actor_dict = {"id": actor.id, "email": actor.email, "name": actor.name}

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = lambda: actor_dict
        # The system router carries a module-guard dependency resolving through
        # get_current_user_or_api_key; override it too or it 401s before the route's
        # own permission check ever runs.
        from app.dependencies import get_current_user_or_api_key

        app.dependency_overrides[get_current_user_or_api_key] = lambda: actor_dict
        try:
            with TestClient(app) as c:
                yield c, db, actor
        finally:
            app.dependency_overrides.clear()


def _row(db, **over) -> TranslationMemory:
    defaults = dict(
        id=str(uuid.uuid4()),
        source_text="座厕",
        source_lang="zh",
        target_lang="en",
        target_text="Toilet bowl",
        source="ai",
        hit_count=2,
    )
    defaults.update(over)
    row = TranslationMemory(**defaults)
    db.add(row)
    db.flush()
    return row


def test_list_returns_every_field_the_admin_page_reads(client):
    c, db, _actor = client
    _row(db, source_text="座厕", target_text="Toilet bowl", source="ai", hit_count=3)
    db.commit()

    resp = c.get(BASE)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["pagination"]["total"] == 1
    row = body["data"][0]
    assert row["source_text"] == "座厕"
    assert row["target_text"] == "Toilet bowl"
    assert row["source"] == "ai"
    assert row["hit_count"] == 3
    assert "created_by_name" in row
    assert "updated_at" in row
    assert "id" in row


def test_list_search_matches_source_or_target(client):
    c, db, _actor = client
    _row(db, source_text="座厕", target_text="Toilet bowl")
    _row(db, source_text="纸箱", target_text="Carton")
    db.commit()

    resp = c.get(BASE, params={"query": "Toilet"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["source_text"] == "座厕"


def test_list_sorts_by_source_text(client):
    c, db, _actor = client
    _row(db, source_text="纸箱")
    _row(db, source_text="座厕")
    db.commit()

    resp = c.get(BASE, params={"sort": "source_text", "dir": "asc"})
    assert resp.status_code == 200, resp.text
    assert [r["source_text"] for r in resp.json()["data"]] == ["座厕", "纸箱"]

    resp = c.get(BASE, params={"sort": "source_text", "dir": "desc"})
    assert [r["source_text"] for r in resp.json()["data"]] == ["纸箱", "座厕"]


def test_list_sorts_by_source_kind(client):
    c, db, _actor = client
    _row(db, source_text="A", source="manual")
    _row(db, source_text="B", source="ai")
    db.commit()

    resp = c.get(BASE, params={"sort": "source", "dir": "asc"})
    assert [r["source"] for r in resp.json()["data"]] == ["ai", "manual"]


def test_list_sorts_by_hit_count(client):
    c, db, _actor = client
    _row(db, source_text="A", hit_count=5)
    _row(db, source_text="B", hit_count=1)
    db.commit()

    resp = c.get(BASE, params={"sort": "hit_count", "dir": "asc"})
    assert [r["hit_count"] for r in resp.json()["data"]] == [1, 5]

    resp = c.get(BASE, params={"sort": "hit_count", "dir": "desc"})
    assert [r["hit_count"] for r in resp.json()["data"]] == [5, 1]


def test_list_sorts_by_updated_at_default_newest_first(client):
    c, db, _actor = client
    older = _row(db, source_text="older")
    newer = _row(db, source_text="newer")
    db.commit()
    # `updated_at` is server-defaulted `now()`, which ties within one transaction - set
    # explicitly so the default ordering this test pins is deterministic.
    from datetime import datetime, timedelta

    older.updated_at = datetime.utcnow() - timedelta(minutes=5)
    newer.updated_at = datetime.utcnow()
    db.commit()

    resp = c.get(BASE)
    assert [r["source_text"] for r in resp.json()["data"]] == ["newer", "older"]


def test_list_ignores_an_unwhitelisted_sort_field(client):
    # `target_text` is not sortable (it is an inline-editable input on the FE, never
    # sent as `sort` there, but the route must not 500 if it somehow is).
    c, db, _actor = client
    _row(db, source_text="A")
    db.commit()

    resp = c.get(BASE, params={"sort": "target_text"})
    assert resp.status_code == 200, resp.text


def test_update_writes_manual_and_the_actor(client):
    c, db, actor = client
    row = _row(db, source_text="座厕", target_text="Toilet bowl", source="ai")
    db.commit()

    resp = c.put(f"{BASE}/{row.id}", json={"target_text": "Toilet bowl, back outlet"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["target_text"] == "Toilet bowl, back outlet"
    assert body["source"] == "manual"
    assert body["created_by_name"] == actor.name

    refreshed = db.query(TranslationMemory).filter(TranslationMemory.id == row.id).one()
    assert refreshed.target_text == "Toilet bowl, back outlet"
    assert refreshed.source == "manual"
    assert refreshed.created_by == actor.id


def test_update_a_missing_row_is_404(client):
    c, _db, _actor = client
    resp = c.put(f"{BASE}/{uuid.uuid4()}", json={"target_text": "x"})
    assert resp.status_code == 404


def test_delete_removes_the_row(client):
    c, db, _actor = client
    row = _row(db)
    db.commit()

    resp = c.delete(f"{BASE}/{row.id}")
    assert resp.status_code == 204, resp.text

    assert db.query(TranslationMemory).filter(TranslationMemory.id == row.id).first() is None


def test_delete_a_missing_row_is_404(client):
    c, _db, _actor = client
    resp = c.delete(f"{BASE}/{uuid.uuid4()}")
    assert resp.status_code == 404
