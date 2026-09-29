"""Null-email guards (#1280 S0, plan 4.1/9.1 Q6): one test per row of
`documentation/plans/identity/s0-email-readers.md`.

A phone-only user (`email=None`) must not break the Users list/detail/select, an SLA
tracking response carrying that user as assignee, the Respond agent sync compare, or
resend-invite. None of the guards exist yet: `UserBase.email`/`UserSimple.email` are
still `str` (not `Optional`), so FastAPI's response-model validation 500s before the
route body even matters, and `_send_invitation_link_for_user` sends "to None." instead
of refusing. `users.email` is still NOT NULL, so seeding needs `contact_number` set
too (AC-02, tested in test_identity_s0_model.py) - a NOT NULL failure here is the same
right-reason red, one layer earlier than intended.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models.notification import Notification
from app.models.user import User, UserRole, UserRoleAssignment
from tests._pg_fixture import blank_session, unique_code


def _phone() -> str:
    return f"+6011{uuid.uuid4().int % 10_000_000:07d}"


def _seed_phone_only_user(db, *, name: str = "Phone Only") -> User:
    user = User(id=str(uuid.uuid4()), email=None, name=name, status="ACTIVE", contact_number=_phone())
    db.add(user)
    db.commit()
    return user


def _seed_admin(db) -> User:
    role = UserRole(id=str(uuid.uuid4()), slug="admin", name="Admin", is_protected=False, is_default=False)
    db.add(role)
    db.flush()
    admin = User(id=str(uuid.uuid4()), email=f"{unique_code('admin')}@example.com".lower(), name="Admin", status="ACTIVE")
    db.add(admin)
    db.flush()
    db.add(UserRoleAssignment(user_id=admin.id, role_id=role.id))
    db.commit()
    return admin


@pytest.fixture()
def client_and_db():
    from app.dependencies import get_current_user

    with blank_session() as db:
        admin = _seed_admin(db)

        def _override_user():
            return {"id": admin.id, "email": admin.email, "name": admin.name, "status": "ACTIVE"}

        def _override_db():
            yield db

        app.dependency_overrides[get_current_user] = _override_user
        app.dependency_overrides[get_db] = _override_db
        with TestClient(app) as client:
            yield client, db
        app.dependency_overrides.clear()


def test_users_list_does_not_break_on_a_phone_only_user(client_and_db):
    client, db = client_and_db
    _seed_phone_only_user(db)
    resp = client.get("/api/v1/user-management/users/")
    assert resp.status_code == 200, resp.text


def test_user_detail_does_not_break_on_a_phone_only_user(client_and_db):
    client, db = client_and_db
    user = _seed_phone_only_user(db)
    resp = client.get(f"/api/v1/user-management/users/{user.id}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] is None


def test_users_select_does_not_break_on_a_phone_only_user(client_and_db):
    client, db = client_and_db
    _seed_phone_only_user(db)
    resp = client.get("/api/v1/user-management/users/select")
    assert resp.status_code == 200, resp.text


def test_sla_user_simple_schema_accepts_a_phone_only_assignee():
    from app.schemas.sla import UserSimple

    with blank_session() as db:
        user = _seed_phone_only_user(db)
        # Must not raise a pydantic ValidationError over the missing email.
        simple = UserSimple.model_validate(user)
        assert simple.id == user.id


def test_respond_agent_sync_compare_does_not_raise_for_a_phone_only_user(monkeypatch):
    from app.services.integration_service import RespondClient
    from app.services.user_service import UserService

    with blank_session() as db:
        user = _seed_phone_only_user(db)
        user.respond_user_id = "respond-123"
        db.commit()

        monkeypatch.setattr(
            RespondClient, "get_user_by_id", lambda self, respond_id: {"email": "someone@example.com"}
        )

        result = UserService(db).sync_respond_user(user.id)  # must not raise AttributeError

        assert result["status"] == "failed"
        assert "no email" in result["message"].lower()


def test_resend_invite_for_a_phone_only_user_is_400_and_queues_nothing(client_and_db):
    client, db = client_and_db
    user = _seed_phone_only_user(db)
    before_notifications = db.query(Notification).filter(Notification.user_id == user.id).count()

    resp = client.post(f"/api/v1/user-management/users/{user.id}/resend-invite")

    assert resp.status_code == 400, resp.text
    after_notifications = db.query(Notification).filter(Notification.user_id == user.id).count()
    assert after_notifications == before_notifications, "no notification/email must be queued for a user with no email"
