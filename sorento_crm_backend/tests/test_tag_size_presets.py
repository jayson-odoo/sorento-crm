"""Tag size preset CRUD (PLAN-price-tag-ux-r3.md S4, D2).

UAC:
  AC-S4-1 [BE] Migration creates `dealer_kit.tag_size_preset` with a unique
      (company_id, name).
  AC-S4-2 [BE] `GET/POST /dealer-kit/tag-sizes`, `PUT/DELETE
      /dealer-kit/tag-sizes/{id}` behind `dealer_kit.tag_templates.view` (GET)
      and `.manage` (writes); company-scoped; a duplicate name is 409;
      width/height below 10mm is 422; unauthenticated is 401; a viewer
      without manage is 403.

Fixture mirrors `test_tag_template_bulk_delete.py` (real company scope, not
the S6b bypass - company isolation is part of this contract).
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be the first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.dealer_kit import TagSizePreset
from tests._pg_fixture import blank_session, unique_code

_SORENTO = "00000000-0000-0000-0000-000000000001"

_MANAGER_ID = "1a2b3c4d-5e6f-461a-8b2c-3d4e5f6a7b81"
_MANAGER_ROLE = "2b3c4d5e-6f7a-472b-9c3d-4e5f6a7b8c92"
_VIEWER_ID = "3c4d5e6f-7a8b-483c-0d4e-5f6a7b8c9da3"
_VIEWER_ROLE = "4d5e6f7a-8b9c-494d-1e5f-6a7b8c9daeb4"

BASE = "/api/v1/dealer-kit/tag-sizes"


def _seed_roles(db) -> None:
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    slugs = ("dealer_kit.tag_templates.view", "dealer_kit.tag_templates.manage")
    perm_ids: dict[str, str] = {}
    for slug in slugs:
        perm_id = str(uuid.uuid4())
        db.add(UserPermission(id=perm_id, slug=slug, name=slug, description=""))
        perm_ids[slug] = perm_id
    db.flush()

    roles = (
        (_MANAGER_ROLE, "zzt_tsp_manager", _MANAGER_ID, slugs),
        (_VIEWER_ROLE, "zzt_tsp_viewer", _VIEWER_ID, (slugs[0],)),
    )
    for role_id, slug, user_id, granted in roles:
        db.add(
            UserRole(
                id=role_id, slug=slug, name=slug, description="",
                is_protected=False, is_default=False,
            )
        )
        db.add(User(id=user_id, email=f"{slug}@test.com", name=slug, status="ACTIVE"))
        db.flush()
        db.add(UserRoleAssignment(user_id=user_id, role_id=role_id))
        for granted_slug in granted:
            db.add(
                UserRolePermission(
                    id=str(uuid.uuid4()), role_id=role_id, permission_id=perm_ids[granted_slug]
                )
            )
    db.commit()


@pytest.fixture
def api():
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed_roles(db)
        here = {"company": _SORENTO}

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        async def _override_scope():
            scope = frozenset({here["company"]})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _override_scope

        def _as(user_id: str):
            principal = {"id": user_id, "email": f"{user_id}@test.com"}
            app.dependency_overrides[get_current_user] = lambda: principal
            app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        def _in_company(company_id: str):
            here["company"] = company_id
            set_company_scope(db, frozenset({company_id}))

        _as(_MANAGER_ID)
        yield db, _as, _in_company

        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Happy path CRUD
# --------------------------------------------------------------------------- #


def test_manager_creates_lists_updates_and_deletes_a_size(api):
    db, _as, _scope = api

    with TestClient(app) as client:
        name = unique_code("Shelf")
        created = client.post(BASE, json={"name": name, "width_mm": 95, "height_mm": 44.5})
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["name"] == name
        assert body["width_mm"] == 95
        assert body["height_mm"] == 44.5
        assert body["created_by_name"] == "zzt_tsp_manager"
        preset_id = body["id"]

        listed = client.get(BASE)
        assert listed.status_code == 200, listed.text
        assert any(row["id"] == preset_id for row in listed.json())

        updated = client.put(f"{BASE}/{preset_id}", json={"name": f"{name}-renamed"})
        assert updated.status_code == 200, updated.text
        assert updated.json()["name"] == f"{name}-renamed"
        # Untouched fields survive a partial update.
        assert updated.json()["width_mm"] == 95

        deleted = client.delete(f"{BASE}/{preset_id}")
        assert deleted.status_code == 204, deleted.text

    db.expire_all()
    assert db.query(TagSizePreset).filter(TagSizePreset.id == preset_id).first() is None


# --------------------------------------------------------------------------- #
# Validation and conflict
# --------------------------------------------------------------------------- #


def test_duplicate_name_is_409(api):
    db, _as, _scope = api

    with TestClient(app) as client:
        name = unique_code("Dup")
        first = client.post(BASE, json={"name": name, "width_mm": 60, "height_mm": 90})
        assert first.status_code == 201, first.text

        second = client.post(BASE, json={"name": name, "width_mm": 70, "height_mm": 100})

    assert second.status_code == 409, second.text
    assert second.json()["code"] == "DUPLICATE_NAME"


def test_renaming_to_an_existing_name_is_also_409(api):
    db, _as, _scope = api

    with TestClient(app) as client:
        taken = unique_code("Taken")
        client.post(BASE, json={"name": taken, "width_mm": 60, "height_mm": 90})
        mine = client.post(BASE, json={"name": unique_code("Mine"), "width_mm": 60, "height_mm": 90})
        preset_id = mine.json()["id"]

        renamed = client.put(f"{BASE}/{preset_id}", json={"name": taken})

    assert renamed.status_code == 409, renamed.text


@pytest.mark.parametrize("field", ["width_mm", "height_mm"])
def test_a_dimension_below_10mm_is_422(api, field):
    db, _as, _scope = api

    payload = {"name": unique_code("Tiny"), "width_mm": 95, "height_mm": 44.5}
    payload[field] = 9.9

    with TestClient(app) as client:
        response = client.post(BASE, json=payload)

    assert response.status_code == 422, response.text


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #


def test_unauthenticated_is_401(api):
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from fastapi import HTTPException

    db, _as, _scope = api

    def _deny():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[get_current_user] = _deny
    app.dependency_overrides[get_current_user_or_api_key] = _deny
    try:
        with TestClient(app) as client:
            response = client.get(BASE)
    finally:
        _as(_MANAGER_ID)

    assert response.status_code == 401, response.text


def test_viewer_without_manage_can_list_but_not_create(api):
    db, _as, _scope = api
    _as(_VIEWER_ID)

    with TestClient(app) as client:
        listed = client.get(BASE)
        assert listed.status_code == 200, listed.text

        refused = client.post(
            BASE, json={"name": unique_code("Refused"), "width_mm": 60, "height_mm": 90}
        )

    assert refused.status_code == 403, refused.text
    db.expire_all()
    assert (
        db.query(TagSizePreset)
        .filter(TagSizePreset.name.like("ZZT-Refused-%"))
        .first()
        is None
    )


def test_viewer_without_manage_cannot_delete(api):
    db, _as, _scope = api

    with TestClient(app) as client:
        created = client.post(
            BASE, json={"name": unique_code("Keep"), "width_mm": 60, "height_mm": 90}
        )
        preset_id = created.json()["id"]

        _as(_VIEWER_ID)
        refused = client.delete(f"{BASE}/{preset_id}")

    assert refused.status_code == 403, refused.text
    db.expire_all()
    assert db.query(TagSizePreset).filter(TagSizePreset.id == preset_id).first() is not None


# --------------------------------------------------------------------------- #
# Company isolation
# --------------------------------------------------------------------------- #


def test_a_foreign_companys_size_is_invisible(api):
    from app.models.company import Company

    db, _as, _scope = api

    with TestClient(app) as client:
        mine = client.post(
            BASE, json={"name": unique_code("Mine"), "width_mm": 60, "height_mm": 90}
        )
        assert mine.status_code == 201, mine.text
        mine_id = mine.json()["id"]

    other_company = str(uuid.uuid4())
    db.add(Company(id=other_company, name="ZZT other co", code=unique_code("ZZTC")))
    db.commit()
    _scope(other_company)

    with TestClient(app) as client:
        listed = client.get(BASE)
        assert listed.status_code == 200, listed.text
        assert all(row["id"] != mine_id for row in listed.json())

        get_theirs = client.put(f"{BASE}/{mine_id}", json={"name": unique_code("Stolen")})

    assert get_theirs.status_code == 404, get_theirs.text
    _scope(_SORENTO)
    db.expire_all()
    assert db.query(TagSizePreset).filter(TagSizePreset.id == mine_id).first() is not None


def test_a_foreign_companys_size_cannot_be_deleted(api):
    """DELETE is scoped the same as PUT (N5): a foreign preset 404s, not 204,
    and stays on disk."""
    from app.models.company import Company

    db, _as, _scope = api

    with TestClient(app) as client:
        mine = client.post(
            BASE, json={"name": unique_code("Mine"), "width_mm": 60, "height_mm": 90}
        )
        assert mine.status_code == 201, mine.text
        mine_id = mine.json()["id"]

    other_company = str(uuid.uuid4())
    db.add(Company(id=other_company, name="ZZT other co", code=unique_code("ZZTC")))
    db.commit()
    _scope(other_company)

    with TestClient(app) as client:
        deleted = client.delete(f"{BASE}/{mine_id}")

    assert deleted.status_code == 404, deleted.text
    _scope(_SORENTO)
    db.expire_all()
    assert db.query(TagSizePreset).filter(TagSizePreset.id == mine_id).first() is not None
