"""The audit read API is superadmin/admin only (issue #1281, section 6.2).

`GET /api/v1/audit/logs/` and `GET /api/v1/audit/activity` depended only on
`get_current_user_or_api_key`: any staff login or API key could read every audited
change, its before/after values and the actor's IP address. The superadmin gate
lived only in the FE menu. Both now require the `superadmin` or `admin` role on the
resolved principal (a login, or an API key's act-as user).

One narrow exception keeps the detail pages' Audit Trail panels working: a read
filtered to ONE record (`entity_type` + `entity_id`) of a type with a detail-page
panel is allowed with that record's view permission. Every other shape 403s.

Real roles, permissions and assignments are seeded on a blank schema, so the check
runs through the real `UserPermissionService`, not a stub.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from fastapi.testclient import TestClient

from app.main import app
import app.database as app_database
from app.dependencies import get_current_user_or_api_key
from app.models.audit import AuditLog
from app.models.user import (
    User,
    UserPermission,
    UserRole,
    UserRoleAssignment,
    UserRolePermission,
)
from tests._pg_fixture import blank_session

COMPLAINT_VIEW = "complaint_management.complaints.view"


def _role(db, slug, permission_slugs=()):
    role = UserRole(
        id=str(uuid.uuid4()), slug=slug, name=slug, description="",
        is_protected=False, is_default=False,
    )
    db.add(role)
    db.flush()
    for p in permission_slugs:
        perm = UserPermission(id=str(uuid.uuid4()), slug=p, name=p, description="")
        db.add(perm)
        db.flush()
        db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=role.id, permission_id=perm.id))
    return role


def _user(db, label, role=None):
    uid = str(uuid.uuid4())
    db.add(User(id=uid, email=f"zz-gate-{label}-{uid[:8]}@example.com", name=label, status="ACTIVE"))
    db.flush()
    if role is not None:
        db.add(UserRoleAssignment(user_id=uid, role_id=role.id))
    return uid


@pytest.fixture
def env():
    with blank_session() as db:
        ids = {
            "superadmin": _user(db, "superadmin", _role(db, "superadmin")),
            "admin": _user(db, "admin", _role(db, "admin")),
            "staff": _user(db, "staff", _role(db, "zz_complaint_staff", [COMPLAINT_VIEW])),
            "plain": _user(db, "plain"),
        }
        db.commit()
        # The seed users' own CREATE rows are not under test. audit_logs is append-only
        # (#1281 S0), so the wipe runs under the maintenance flag.
        db.execute(text("SET LOCAL sorento.audit_maintenance = 'on'"))
        db.query(AuditLog).delete()
        complaint_id = str(uuid.uuid4())
        db.add(AuditLog(
            id=str(uuid.uuid4()), entity_type="complaint", entity_id=complaint_id,
            action="UPDATE", old_values={"status": "pending"}, new_values={"status": "resolved"},
            ip_address="10.0.0.9",
        ))
        db.commit()

        caller = {"id": None}

        def _override_db():
            yield db

        app.dependency_overrides[app_database.get_db] = _override_db
        app.dependency_overrides[get_current_user_or_api_key] = lambda: {"id": caller["id"]}

        def as_(who):
            caller["id"] = ids[who]
            return TestClient(app)

        try:
            yield as_, complaint_id
        finally:
            app.dependency_overrides.clear()


# --- the full listing and the activity feed ------------------------------------

@pytest.mark.parametrize("who", ["plain", "staff"])
def test_audit_logs_listing_is_forbidden_to_a_non_admin(env, who):
    as_, _ = env
    r = as_(who).get("/api/v1/audit/logs/")
    assert r.status_code == 403, r.text


@pytest.mark.parametrize("who", ["plain", "staff"])
def test_activity_feed_is_forbidden_to_a_non_admin(env, who):
    as_, _ = env
    r = as_(who).get("/api/v1/audit/activity")
    assert r.status_code == 403, r.text


@pytest.mark.parametrize("who", ["superadmin", "admin"])
def test_superadmin_and_admin_read_both(env, who):
    as_, complaint_id = env
    client = as_(who)
    logs = client.get("/api/v1/audit/logs/")
    assert logs.status_code == 200, logs.text
    assert [row["entity_id"] for row in logs.json()["data"]] == [complaint_id]
    feed = client.get("/api/v1/audit/activity")
    assert feed.status_code == 200, feed.text


# --- the per-record Audit Trail panel ------------------------------------------

def test_one_record_history_is_readable_with_that_records_view_permission(env):
    as_, complaint_id = env
    r = as_("staff").get(f"/api/v1/audit/logs/?entity_type=complaint&entity_id={complaint_id}")
    assert r.status_code == 200, r.text
    assert [row["entity_id"] for row in r.json()["data"]] == [complaint_id]


def test_one_record_history_is_forbidden_without_that_view_permission(env):
    as_, complaint_id = env
    r = as_("plain").get(f"/api/v1/audit/logs/?entity_type=complaint&entity_id={complaint_id}")
    assert r.status_code == 403, r.text


def test_a_view_permission_does_not_open_another_entity_types_history(env):
    as_, _ = env
    # `users` history carries IP addresses and account changes; no detail-page panel reads it.
    r = as_("staff").get(f"/api/v1/audit/logs/?entity_type=users&entity_id={uuid.uuid4()}")
    assert r.status_code == 403, r.text


def test_an_entity_type_without_an_entity_id_is_a_listing_not_a_record(env):
    as_, _ = env
    r = as_("staff").get("/api/v1/audit/logs/?entity_type=complaint")
    assert r.status_code == 403, r.text
