"""AGENT-PANEL-FIXES F: steps, route and trace in the AI panel are for admins only (owner, 11 Nov).

The gate was the `system.ai_assistant_settings.view` slug, which any role can be handed in the role editor. It is
now the admin roles (`superadmin`, `admin`), read from the user's own role rows.
"""
from __future__ import annotations

import uuid

import pytest

import app.main  # noqa: F401
from app.models.user import UserRole, UserRoleAssignment
from app.services.chatbot.panel_service import sees_trace
from tests._pg_fixture import blank_session, unique_code
from tests.chatbot.agent._seed import seed_user


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def _with_role(db, slug: str, *slugs: str) -> str:
    uid = seed_user(db, contact_pk=None, slugs=slugs)
    role = db.query(UserRole).filter(UserRole.slug == slug).first()
    if role is None:
        role = UserRole(id=str(uuid.uuid4()), slug=slug, name=unique_code("Role"))
        db.add(role)
        db.flush()
    db.add(UserRoleAssignment(id=str(uuid.uuid4()), user_id=uid, role_id=role.id))
    db.flush()
    return uid


@pytest.mark.parametrize("slug", ["admin", "superadmin"])
def test_an_admin_role_sees_the_trace(db, slug):
    assert sees_trace(db, _with_role(db, slug)) is True


def test_the_settings_slug_alone_does_not(db):
    uid = seed_user(db, contact_pk=None, slugs=("system.ai_assistant_settings.view", "system.chat_history.view"))
    assert sees_trace(db, uid) is False


def test_another_role_does_not(db):
    assert sees_trace(db, _with_role(db, unique_code("sales").lower(), "system.ai_assistant_settings.view")) is False
