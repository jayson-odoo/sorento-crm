"""UI-V2 phase 0, slice S1: the per-user version switch (UAC B-1 .. B-6).

Plan: documentation/plans/design-system/PLAN-ui-v2-phase0-12nov.md (section 3 "Backend (S1)",
section 4 "Test list"). UAC: documentation/plans/design-system/ui-v2-phase0-12nov-acceptance-criteria.md.

The caller holds exactly the permissions each test passes to ``api_client``; ``ui.v2.preview`` is
the slug that unlocks v2. The caller is a REAL ``users`` row (the ``/me`` builders read it), so
every test seeds its own user and settings row on the blank Postgres schema.

Run:
    SORENTO_ENV_FILE=.env.ci-tests venv/bin/python -m pytest tests/test_ui_v2_version.py -q
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.models.user import SystemSetting, User, UserRole, UserRolePermission
from tests._ai_usage_client import api_client
from tests._pg_fixture import TEST_PREFIX, blank_session

PREVIEW = "ui.v2.preview"
SETTINGS_EDIT = "user_management.settings.edit"
USERS_VIEW = "user_management.users.view"

USERS = "/api/v1/user-management/users"
ME = f"{USERS}/me"
UI_VERSION = f"{ME}/ui-version"
SETTINGS = "/api/v1/user-management/settings"

UI_KEYS = ("ui_version", "ui_version_stored", "ui_v2_available", "theme_mode")

MIGRATION = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "uiv2_0001_version_theme_views.py"
)


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _seed(db, client) -> str:
    """The caller's own users row plus the one company settings row (kill switch defaults on)."""
    uid = client.actor["id"]
    db.add(
        User(
            id=uid,
            email=client.actor["email"],
            name=f"{TEST_PREFIX} UiV2 User",
            status="ACTIVE",
        )
    )
    db.add(SystemSetting(id=str(uuid.uuid4()), name=f"{TEST_PREFIX} UiV2 Co"))
    db.commit()
    return uid


def _stored(db, uid: str):
    """The raw stored column, read past every ORM and builder."""
    return db.execute(text("SELECT ui_version FROM users WHERE id = :i"), {"i": uid}).scalar()


# --------------------------------------------------------------------------- #
# B-1 - every builder carries the four fields                                  #
# --------------------------------------------------------------------------- #


def test_me_has_ui_fields_default_v1(db):
    with api_client(db, []) as client:
        _seed(db, client)
        r = client.get(ME)
    assert r.status_code == 200
    body = r.json()
    assert body["ui_version"] == "v1"
    assert body["ui_v2_available"] is False


def test_me_ui_v2_available_with_permission(db):
    with api_client(db, [PREVIEW]) as client:
        _seed(db, client)
        r = client.get(ME)
    assert r.status_code == 200
    body = r.json()
    assert body["ui_v2_available"] is True
    assert body["ui_version"] == "v1"  # holding the slug does not switch anyone


def test_get_user_and_profile_builders_carry_ui_fields(db):
    """LESSONS 93: /me, get_user and PUT /me/profile are three hand-built dicts."""
    with api_client(db, [PREVIEW, USERS_VIEW]) as client:
        uid = _seed(db, client)
        assert client.put(UI_VERSION, json={"ui_version": "v2"}).status_code == 200
        me = client.get(ME)
        by_id = client.get(f"{USERS}/{uid}")
        profile = client.put(f"{ME}/profile", json={"name": f"{TEST_PREFIX} Renamed"})
    for label, r in (("GET /me", me), ("GET /{id}", by_id), ("PUT /me/profile", profile)):
        assert r.status_code == 200, label
        body = r.json()
        for key in UI_KEYS:
            assert key in body, f"{label} is missing {key}"
        assert body["ui_version"] == "v2", label
        assert body["ui_version_stored"] == "v2", label
        assert body["ui_v2_available"] is True, label
        assert body["theme_mode"] == "system", label


# --------------------------------------------------------------------------- #
# B-2 / B-3 / B-4 - PUT /me/ui-version                                         #
# --------------------------------------------------------------------------- #


def test_put_ui_version_v2_with_permission(db):
    with api_client(db, [PREVIEW]) as client:
        uid = _seed(db, client)
        to_v2 = client.put(UI_VERSION, json={"ui_version": "v2"})
        after_v2 = client.get(ME)
        to_v1 = client.put(UI_VERSION, json={"ui_version": "v1"})
        after_v1 = client.get(ME)
    assert to_v2.status_code == 200
    assert after_v2.json()["ui_version"] == "v2"
    assert to_v1.status_code == 200
    assert after_v1.json()["ui_version"] == "v1"
    assert _stored(db, uid) == "v1"


def test_put_ui_version_v2_without_permission_forbidden(db):
    with api_client(db, []) as client:
        uid = _seed(db, client)
        r = client.put(UI_VERSION, json={"ui_version": "v2"})
        me = client.get(ME)
    assert r.status_code == 403
    assert me.json()["ui_version"] == "v1"
    assert _stored(db, uid) == "v1"


def test_put_ui_version_v1_always_allowed(db):
    with api_client(db, []) as client:
        _seed(db, client)
        r = client.put(UI_VERSION, json={"ui_version": "v1"})
    assert r.status_code == 200


@pytest.mark.parametrize("bad", ["v3", "", None])
def test_put_ui_version_invalid_422(db, bad):
    with api_client(db, [PREVIEW]) as client:
        uid = _seed(db, client)
        r = client.put(UI_VERSION, json={"ui_version": bad})
    assert r.status_code == 422
    assert _stored(db, uid) == "v1"


# --------------------------------------------------------------------------- #
# B-5 - the company kill switch                                                #
# --------------------------------------------------------------------------- #


def test_kill_switch_forces_v1(db):
    with api_client(db, [PREVIEW, SETTINGS_EDIT]) as client:
        _seed(db, client)
        assert client.put(UI_VERSION, json={"ui_version": "v2"}).status_code == 200

        off = client.put(f"{SETTINGS}/general", json={"ui_v2_enabled": False})
        assert off.status_code == 200
        me_off = client.get(ME).json()

        on = client.put(f"{SETTINGS}/general", json={"ui_v2_enabled": True})
        assert on.status_code == 200
        me_on = client.get(ME).json()

    assert me_off["ui_version"] == "v1"
    assert me_off["ui_v2_available"] is False
    assert me_off["ui_version_stored"] == "v2"  # the choice is kept
    # turned back on, the stored choice takes effect again
    assert me_on["ui_version"] == "v2"
    assert me_on["ui_v2_available"] is True


def test_kill_switch_blocks_put_v2(db):
    with api_client(db, [PREVIEW, SETTINGS_EDIT]) as client:
        uid = _seed(db, client)
        assert client.put(f"{SETTINGS}/general", json={"ui_v2_enabled": False}).status_code == 200
        r = client.put(UI_VERSION, json={"ui_version": "v2"})
        back = client.put(UI_VERSION, json={"ui_version": "v1"})
    assert r.status_code == 403
    assert _stored(db, uid) == "v1"
    assert back.status_code == 200  # a way back never needs anything


# --------------------------------------------------------------------------- #
# B-6 - the migration: slug seeded and ungranted, defaults                     #
# --------------------------------------------------------------------------- #


def _load_migration():
    assert MIGRATION.exists(), f"migration file missing: {MIGRATION.name}"
    spec = importlib.util.spec_from_file_location("uiv2_0001", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_permission_slug_seeded_ungranted(db):
    """Run the migration over a pre-migration shape, then read what it left behind."""
    module = _load_migration()
    assert len(module.revision) <= 32

    legacy_id = str(uuid.uuid4())
    db.add(
        User(
            id=legacy_id,
            email=f"{TEST_PREFIX.lower()}-legacy-{legacy_id[:8]}@test.invalid",
            name=f"{TEST_PREFIX} Legacy",
            status="ACTIVE",
        )
    )
    db.add(SystemSetting(id=str(uuid.uuid4()), name=f"{TEST_PREFIX} Legacy Co"))
    db.commit()
    db.expunge_all()

    # Rewind to the shape before this lane, however the metadata built the blank schema.
    db.execute(text("DELETE FROM user_permissions WHERE slug = :s"), {"s": PREVIEW})
    db.execute(text("DROP TABLE IF EXISTS ui_page_views"))
    db.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS ui_version"))
    db.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS theme_mode"))
    db.execute(text("ALTER TABLE system_settings DROP COLUMN IF EXISTS ui_v2_enabled"))
    db.execute(text("ALTER TABLE system_settings DROP COLUMN IF EXISTS theme"))

    with Operations.context(MigrationContext.configure(db.connection())):
        module.upgrade()

    slug_rows = db.execute(
        text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": PREVIEW}
    ).fetchall()
    assert len(slug_rows) == 1
    perm_id = slug_rows[0][0]

    granted = db.execute(
        text("SELECT count(*) FROM user_role_permissions WHERE permission_id = :p"),
        {"p": perm_id},
    ).scalar()
    assert granted == 0

    # the legacy rows take the server defaults, no backfill script
    assert _stored(db, legacy_id) == "v1"
    assert (
        db.execute(text("SELECT theme_mode FROM users WHERE id = :i"), {"i": legacy_id}).scalar()
        == "system"
    )
    row = db.execute(text("SELECT ui_v2_enabled, theme FROM system_settings")).one()
    assert row[0] is True
    assert row[1] == {"preset": "sorento-blue", "custom_hex": None}
    assert db.execute(text("SELECT to_regclass('ui_page_views')")).scalar() is not None

    # grantable like any other slug
    role = UserRole(slug=f"{TEST_PREFIX.lower()}-uiv2-{uuid.uuid4().hex[:6]}", name=f"{TEST_PREFIX} UiV2 {uuid.uuid4().hex[:6]}")
    db.add(role)
    db.commit()
    db.add(UserRolePermission(role_id=role.id, permission_id=perm_id))
    db.commit()
    assert (
        db.execute(
            text("SELECT count(*) FROM user_role_permissions WHERE permission_id = :p"),
            {"p": perm_id},
        ).scalar()
        == 1
    )


# --------------------------------------------------------------------------- #
# Journey step 1: only an explicit holder of ui.v2.preview gets v2. The admin   #
# and superadmin shortcut of check_user_has_permission must NOT open it.        #
# --------------------------------------------------------------------------- #


def _role_user(db, role_slug: str, *, grant_preview: bool) -> str:
    from app.models.user import UserPermission, UserRoleAssignment
    db.add(SystemSetting(id=str(uuid.uuid4()), name=f"{TEST_PREFIX} UiV2 Co"))
    role = db.query(UserRole).filter(UserRole.slug == role_slug).first()
    if role is None:
        role = UserRole(slug=role_slug, name=f"{TEST_PREFIX} {role_slug} {uuid.uuid4().hex[:6]}")
        db.add(role)
    uid = str(uuid.uuid4())
    db.add(User(id=uid, email=f"{uid[:8]}@example.com", name=f"{TEST_PREFIX} {role_slug}", status="ACTIVE"))
    db.flush()
    db.add(UserRoleAssignment(user_id=uid, role_id=role.id))
    if grant_preview:
        perm = db.query(UserPermission).filter(UserPermission.slug == PREVIEW).first()
        if perm is None:
            perm = UserPermission(slug=PREVIEW, name="Preview UI v2")
            db.add(perm)
            db.flush()
        db.add(UserRolePermission(role_id=role.id, permission_id=perm.id))
    db.commit()
    return uid


@pytest.mark.parametrize("role_slug", ["admin", "superadmin"])
def test_admin_without_explicit_preview_grant_gets_no_v2(db, role_slug):
    from app.services.ui_version_service import v2_available

    uid = _role_user(db, role_slug, grant_preview=False)
    assert v2_available(db, db.get(User, uid)) is False


@pytest.mark.parametrize("role_slug", ["admin", "superadmin"])
def test_admin_with_explicit_preview_grant_gets_v2(db, role_slug):
    from app.services.ui_version_service import v2_available

    uid = _role_user(db, role_slug, grant_preview=True)
    assert v2_available(db, db.get(User, uid)) is True
