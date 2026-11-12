"""AGENT-QUOTE-COMPARE AC-C3: a padded project id in the path is the same project, not a 500.

`validate_uuid_path` already strips and lower-cases the id, but the quotations list route keeps
querying with the raw value, so a leading space reaches Postgres as a bad uuid. Postgres only,
every row seeded here.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.user import User
from app.services import project_seed_service

from ._pg_fixture import blank_session

MARKER = "zzt-qpadded"
BASE = "/api/v1/project-sales"
ALL_SLUGS = ["projects.projects.view", "projects.projects.create", "projects.projects.edit"]


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def api():
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.models.base import company_scope
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.project_service import register_project
    from app.services.user_service import UserPermissionService

    with blank_session() as db:
        company_id = db.execute(text("select id from companies where code = 'SRT'")).scalar()
        project_seed_service.run(db, company_id=company_id)
        user_id = _uid()
        db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=f"{MARKER} Ali"))
        db.flush()
        project = register_project(
            db, company_id=company_id, actor_user_id=user_id, developer_party_id=None,
            title=f"{MARKER} Tower",
        )
        db.commit()
        actor = {"id": user_id, "email": f"{user_id}@zzt.test", "role": "superadmin"}
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: dict(actor)
        app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
        app.dependency_overrides[apply_company_scope] = lambda: None
        originals = (
            UserPermissionService.check_user_has_permission,
            UserPermissionService.get_user_permission_slugs,
        )
        UserPermissionService.check_user_has_permission = lambda self, uid, slug: True
        UserPermissionService.get_user_permission_slugs = lambda self, uid: list(ALL_SLUGS)
        try:
            with company_scope(db, frozenset({company_id})):
                yield TestClient(app, raise_server_exceptions=False), project
        finally:
            UserPermissionService.check_user_has_permission = originals[0]
            UserPermissionService.get_user_permission_slugs = originals[1]
            app.dependency_overrides.clear()


def test_AC_C3_a_padded_project_id_lists_the_projects_quotations(api):
    client, project = api
    created = client.post(f"{BASE}/projects/{project.id}/quotations", json={"scope_label": f"{MARKER} Units"})
    assert created.status_code == 201, created.text

    clean = client.get(f"{BASE}/projects/{project.id}/quotations")
    assert clean.status_code == 200, clean.text

    padded = client.get(f"{BASE}/projects/%20{project.id}/quotations")
    assert padded.status_code == 200, (padded.status_code, padded.text)
    assert [row["id"] for row in padded.json()["data"]] == [row["id"] for row in clean.json()["data"]]
    assert len(padded.json()["data"]) == 1


def test_AC_C3_a_trailing_space_and_upper_case_id_also_work(api):
    client, project = api
    client.post(f"{BASE}/projects/{project.id}/quotations", json={"scope_label": f"{MARKER} Units"})
    response = client.get(f"{BASE}/projects/{str(project.id).upper()}%20/quotations")
    assert response.status_code == 200, (response.status_code, response.text)
    assert len(response.json()["data"]) == 1
