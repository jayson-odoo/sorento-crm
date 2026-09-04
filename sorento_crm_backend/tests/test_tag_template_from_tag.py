"""POST /dealer-kit/tag-templates/from-tag - "Save as template" (S4, D1).

UAC:
  AC-S4-7 [BE] `POST /dealer-kit/tag-templates/from-tag` accepts {name,
      family, doc, print_size}, creates the template AND publishes v1 in one
      transaction, returns the template with `published_version_no = 1`;
      declared before `/{template_id}`.
  AC-S4-9 [FE] (`templateFromTag` strips `text_override` client-side; owned by
      that helper's own vitest coverage.) This file's job is the ROUTE: it
      stores and returns whatever doc it is handed, faithfully - including a
      layer whose `text_override` is already null, which is what a stripped
      payload looks like by the time it reaches here.

Fixture mirrors `test_dealer_kit_tag_template_versions.py`.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be the first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.dealer_kit import TagTemplate, TagTemplateVersion
from tests._pg_fixture import blank_session, unique_code

_SORENTO = "00000000-0000-0000-0000-000000000001"

_MANAGER_ID = "5a6b7c8d-9e0f-4a15-8b2c-3d4e5f6a7b91"
_MANAGER_ROLE = "6b7c8d9e-0f1a-4b26-9c3d-4e5f6a7b8ca2"
_VIEWER_ID = "7c8d9e0f-1a2b-4c37-0d4e-5f6a7b8c9db3"
_VIEWER_ROLE = "8d9e0f1a-2b3c-4d48-1e5f-6a7b8c9dacc4"

BASE = "/api/v1/dealer-kit/tag-templates"


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
        (_MANAGER_ROLE, "zzt_ftt_manager", _MANAGER_ID, slugs),
        (_VIEWER_ROLE, "zzt_ftt_viewer", _VIEWER_ID, (slugs[0],)),
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


def _doc_with_bound_and_unbound_text() -> dict:
    """A layer whose `text_override` is already null (a bound layer,
    stripped by `templateFromTag` before this ever reaches the route) next to
    one that is NOT bound and carries its own hand-typed text verbatim - the
    two AC-S4-9 draws apart."""
    return {
        "layers": [
            {
                "id": "layer-1",
                "type": "text",
                "x_mm": 0,
                "y_mm": 0,
                "width_mm": 20,
                "height_mm": 10,
                "rotation_deg": 0,
                "z_index": 0,
                "locked": False,
                "visible": True,
                "slot_binding": "code",
                "text_override": None,
                "props": {
                    "kind": "text",
                    "text": "{{product.code}}",
                    "fontFamily": "Jost",
                    "fontSize": 10,
                    "fontWeight": 400,
                    "color": "#000",
                    "align": "left",
                    "lineHeight": 1.2,
                    "letterSpacing": 0,
                },
            },
            {
                "id": "layer-2",
                "type": "text",
                "x_mm": 0,
                "y_mm": 15,
                "width_mm": 20,
                "height_mm": 10,
                "rotation_deg": 0,
                "z_index": 1,
                "locked": False,
                "visible": True,
                "slot_binding": None,
                "text_override": "Hand-typed heading",
                "props": {
                    "kind": "text",
                    "text": "Hand-typed heading",
                    "fontFamily": "Jost",
                    "fontSize": 12,
                    "fontWeight": 700,
                    "color": "#000",
                    "align": "left",
                    "lineHeight": 1.2,
                    "letterSpacing": 0,
                },
            },
        ],
        "width_mm": 95,
        "height_mm": 44.5,
    }


def _payload(name: str | None = None, family: str = "wc") -> dict:
    return {
        "name": name or unique_code("FromTag"),
        "family": family,
        "doc": _doc_with_bound_and_unbound_text(),
        "print_size": {"width_mm": 95, "height_mm": 44.5},
    }


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #


def test_creates_and_publishes_v1_in_one_call(api):
    db, _as, _scope = api

    with TestClient(app) as client:
        response = client.post(f"{BASE}/from-tag", json=_payload())

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["published_version_no"] == 1
    assert body["published_version_id"]
    assert body["family"] == "wc"

    db.expire_all()
    template = db.query(TagTemplate).filter(TagTemplate.id == body["id"]).first()
    assert template is not None
    assert template.published_version_id == body["published_version_id"]

    versions = (
        db.query(TagTemplateVersion)
        .filter(TagTemplateVersion.template_id == template.id)
        .all()
    )
    assert len(versions) == 1
    assert versions[0].version_no == 1
    # The route stores and publishes exactly what it was handed - the strip
    # itself is `templateFromTag`'s job, covered by its own vitest.
    assert versions[0].doc["layers"][0]["text_override"] is None
    assert versions[0].doc["layers"][1]["text_override"] == "Hand-typed heading"
    assert template.doc == versions[0].doc


def test_appears_in_the_published_templates_list_immediately(api):
    db, _as, _scope = api

    with TestClient(app) as client:
        created = client.post(f"{BASE}/from-tag", json=_payload())
        template_id = created.json()["id"]

        listed = client.get(BASE, params={"published": "1"})

    assert listed.status_code == 200, listed.text
    assert any(row["id"] == template_id for row in listed.json())


def test_from_tag_is_not_shadowed_by_the_template_id_route(api):
    """The load-bearing order: `/from-tag` declared before `/{template_id}`
    means this POST is never swallowed as `template_id="from-tag"`."""
    db, _as, _scope = api

    with TestClient(app) as client:
        response = client.post(f"{BASE}/from-tag", json=_payload())

    assert response.status_code == 201, response.text
    assert response.json()["id"] != "from-tag"


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
            response = client.post(f"{BASE}/from-tag", json=_payload())
    finally:
        _as(_MANAGER_ID)

    assert response.status_code == 401, response.text


def test_viewer_without_manage_is_refused(api):
    db, _as, _scope = api
    _as(_VIEWER_ID)

    with TestClient(app) as client:
        response = client.post(f"{BASE}/from-tag", json=_payload())

    assert response.status_code == 403, response.text
    db.expire_all()
    assert db.query(TagTemplate).count() == 0


# --------------------------------------------------------------------------- #
# Company isolation
# --------------------------------------------------------------------------- #


def test_a_template_saved_in_one_company_is_invisible_in_another(api):
    from app.models.company import Company

    db, _as, _scope = api

    with TestClient(app) as client:
        created = client.post(f"{BASE}/from-tag", json=_payload())
        template_id = created.json()["id"]

    other_company = str(uuid.uuid4())
    db.add(Company(id=other_company, name="ZZT other co", code=unique_code("ZZTC")))
    db.commit()
    _scope(other_company)

    with TestClient(app) as client:
        listed = client.get(BASE, params={"published": "1"})

    assert listed.status_code == 200, listed.text
    assert all(row["id"] != template_id for row in listed.json())
