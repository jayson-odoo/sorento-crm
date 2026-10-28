"""FILTER-MULTISELECT PR2 review round (red): several entity types on the audit log are never a
"one record's history" read, so a caller without the admin audit role is refused (fails closed), even
when they hold the view permission of one of the types. Own seeding: no audit rows are deleted, so it
runs on a database whose audit_logs table is append-only.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
import app.database as app_database
from app.dependencies import get_current_user_or_api_key
from app.models.base import set_company_scope
from app.models.user import User, UserPermission, UserRole, UserRoleAssignment, UserRolePermission
from app.services.company_scope_resolver import apply_company_scope
from tests._pg_fixture import blank_session

COMPLAINT_VIEW = "complaint_management.complaints.view"


@pytest.fixture
def env():
    with blank_session() as db:
        role = UserRole(id=str(uuid.uuid4()), slug="zz_complaint_staff_mt", name="zz_complaint_staff_mt",
                        description="", is_protected=False, is_default=False)
        db.add(role)
        db.flush()
        perm = UserPermission(id=str(uuid.uuid4()), slug=COMPLAINT_VIEW, name=COMPLAINT_VIEW, description="")
        db.add(perm)
        db.flush()
        db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=role.id, permission_id=perm.id))
        staff = str(uuid.uuid4())
        db.add(User(id=staff, email=f"zz-gate-mt-{staff[:8]}@example.com", name="staff", status="ACTIVE"))
        db.flush()
        db.add(UserRoleAssignment(user_id=staff, role_id=role.id))
        db.commit()

        def _override_db():
            yield db

        async def _override_scope():
            set_company_scope(db, None)
            return None

        app.dependency_overrides[app_database.get_db] = _override_db
        app.dependency_overrides[apply_company_scope] = _override_scope
        app.dependency_overrides[get_current_user_or_api_key] = lambda: {"id": staff}
        try:
            yield TestClient(app)
        finally:
            app.dependency_overrides.clear()


def test_one_entity_type_with_its_view_permission_is_still_readable(env):
    r = env.get(f"/api/v1/audit/logs/?entity_type=complaint&entity_id={uuid.uuid4()}")
    assert r.status_code == 200, r.text


def test_several_entity_types_comma_joined_are_forbidden_to_a_non_admin(env):
    r = env.get(f"/api/v1/audit/logs/?entity_type=complaint,users&entity_id={uuid.uuid4()}")
    assert r.status_code == 403, r.text


def test_several_entity_types_repeated_are_forbidden_to_a_non_admin(env):
    r = env.get(f"/api/v1/audit/logs/?entity_type=complaint&entity_type=users&entity_id={uuid.uuid4()}")
    assert r.status_code == 403, r.text


def test_several_entity_types_without_an_id_are_forbidden_to_a_non_admin(env):
    r = env.get("/api/v1/audit/logs/?entity_type=complaint,users")
    assert r.status_code == 403, r.text
