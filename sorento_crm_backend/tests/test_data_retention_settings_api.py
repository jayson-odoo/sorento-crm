"""DB-RETENTION security review: who may change the retention settings, and what a null does.

Retention settings decide how much history the nightly jobs delete, so they are
admin-only: `user_management.settings.edit` (also held by warehouse_manager and the
integration API-key roles) is not enough. The bar is the runtime-secrets slug
(`RUNTIME_SETTINGS_PERMISSION`, which admin passes through its bypass), the gate the SMTP
fields already sit behind.

Pattern copied from tests/test_settings_write_gates.py: admin goes through the REAL
`check_user_has_permission` with only the role lookup pinned; every other caller pins
`check_user_has_permission` against an `allow` set. Postgres `blank_session()` only.

Keys covered: the 11 retention settings added by this lane plus
`import_job_rows_retention_days`, the only older retention setting that rides
`SystemSettingUpdate` (downloads / api_call_log retention are not on that schema).
"""
from __future__ import annotations

import uuid

import pytest

from tests._pg_fixture import TEST_PREFIX, blank_session

BASE = "/api/v1/user-management/settings"
EDIT = "user_management.settings.edit"
VIEW = "user_management.settings.view"
SECRETS = "user_management.settings.secrets"

# key -> a valid value that differs from the column default.
RETENTION_WRITES = {
    "import_job_rows_retention_days": 7,
    "integration_log_payload_retention_days": 7,
    "integration_log_row_retention_days": 7,
    "chatbot_turn_trace_retention_days": 7,
    "scheduled_task_run_retention_days": 7,
    "reorder_run_retention_days": 7,
    "embedding_superseded_retention_days": 7,
    "plan_exception_superseded_grace_days": 7,
    "data_retention_dry_run": True,
    "data_retention_batch_size": 7,
    "data_retention_batch_sleep_ms": 7,
    "data_retention_max_run_minutes": 7,
}
KEYS = list(RETENTION_WRITES)


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


@pytest.fixture
def caller(db):
    from app.models.user import User

    user = User(
        id=str(uuid.uuid4()),
        email=f"{TEST_PREFIX}-drs-caller-{uuid.uuid4().hex[:6]}@zzt.test".lower(),
        name=f"{TEST_PREFIX} DRS Caller",
        avatar_storage_provider="s3",
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def settings_row(db):
    from app.models.user import SystemSetting

    row = SystemSetting(id=str(uuid.uuid4()), name=f"{TEST_PREFIX} Co")
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def client(db, caller):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app

    def _override_db():
        yield db

    who = {"id": caller.id, "email": caller.email}
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: who
    app.dependency_overrides[get_current_user_or_api_key] = lambda: who
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_user_or_api_key, None)


@pytest.fixture
def allow(monkeypatch):
    from app.services.user_service import UserPermissionService

    granted: set[str] = set()
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in granted,
    )
    return granted


@pytest.fixture
def as_admin(caller, monkeypatch):
    from app.services.user_service import UserPermissionService

    # Only the role lookup is pinned; the permission check itself is real, so this goes
    # through the same admin bypass production does.
    monkeypatch.setattr(
        UserPermissionService,
        "get_user_role_slugs",
        lambda self, uid: {"admin"} if str(uid) == str(caller.id) else set(),
    )


def _column(db, name):
    from app.models.user import SystemSetting

    db.expire_all()
    return getattr(db.query(SystemSetting).first(), name)


@pytest.mark.parametrize("method", ["put", "post"])
@pytest.mark.parametrize("key", KEYS)
def test_retention_settings_need_admin(client, allow, db, settings_row, method, key):
    """A settings editor without admin / the secrets slug is refused, and nothing is
    applied - not even a plain field sent in the same body."""
    allow.update({EDIT, VIEW})
    before = _column(db, key)

    resp = getattr(client, method)(
        f"{BASE}/general", json={key: RETENTION_WRITES[key], "name": "zzt-renamed"}
    )

    assert resp.status_code == 403, resp.text
    assert _column(db, key) == before
    assert _column(db, "name") == f"{TEST_PREFIX} Co", "the refusal must not half-apply the body"


@pytest.mark.parametrize("key", KEYS)
def test_retention_settings_admin_can_change(client, as_admin, db, settings_row, key):
    resp = client.put(f"{BASE}/general", json={key: RETENTION_WRITES[key]})

    assert resp.status_code == 200, resp.text
    assert _column(db, key) == RETENTION_WRITES[key]


@pytest.mark.parametrize("key", KEYS)
def test_retention_settings_secrets_slug_holder_can_change(client, allow, db, settings_row, key):
    """RUNTIME_SETTINGS_PERMISSION is the bar, not the admin role as such."""
    allow.update({EDIT, VIEW, SECRETS})

    resp = client.put(f"{BASE}/general", json={key: RETENTION_WRITES[key]})

    assert resp.status_code == 200, resp.text
    assert _column(db, key) == RETENTION_WRITES[key]


def test_plain_general_settings_still_save_for_a_settings_editor(client, allow, db, settings_row):
    """The gate is on the retention keys only; the rest of /general is unchanged."""
    allow.update({EDIT, VIEW})

    resp = client.put(f"{BASE}/general", json={"name": "zzt-renamed"})

    assert resp.status_code == 200, resp.text
    assert _column(db, "name") == "zzt-renamed"


@pytest.mark.parametrize("key", KEYS)
def test_retention_setting_null_is_422(client, as_admin, db, settings_row, key):
    """Every one of these columns is NOT NULL: an explicit JSON null is a validation
    error (422), not a database IntegrityError surfacing as a 500."""
    before = _column(db, key)

    resp = client.put(f"{BASE}/general", json={key: None})

    assert resp.status_code == 422, resp.text
    assert _column(db, key) == before
