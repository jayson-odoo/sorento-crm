"""The low-stock threshold is a SETTING, not a constant (S0, D7).

UAC `documentation/plans/chatbot/chatbot-dealer-stock-verdict-acceptance-criteria.md`
AC-1730, AC-1731. PLAN `documentation/plans/chatbot/PLAN-chatbot-dealer-stock-verdict.md`
("Setting: `system_settings.chatbot_stock_low_threshold_pct`").

Two halves, copied from `tests/test_default_uom_setting.py`'s split (the standing
`response_model` / manual-dict-builder trap - a settings column reaches the screen only if
it is on `SystemSettingUpdate` AND the `get_settings()` GET dict):

* the migration `dsv_0001` adds `system_settings.chatbot_stock_low_threshold_pct`
  (integer, not null, server default 50), chained onto main's current head
  `spec_vocab_close_couple`, and the alembic graph stays a single head;
* the settings blob round-trips the column through `PUT/POST
  /api/v1/user-management/settings/general` and `GET /api/v1/user-management/settings/`,
  and the Pydantic bound (1 to 100) refuses 0 and 101 with a 422 before either reaches the
  column.

Postgres only, blank scratch schema (`blank_session`), permission check monkeypatched the
same way `tests/scm/test_plan_grain_policy.py` and `tests/test_default_uom_setting.py` do it
- this is about the column, not about auth. `dsv_0001` does not exist yet, so
`_load_dsv_migration()` raises at the first test that calls it - that IS the expected red
state for AC-1730. The GET/PUT tests are red because `SystemSettingUpdate` has no
`chatbot_stock_low_threshold_pct` field yet, so FastAPI silently drops it and the round trip
comes back `None` instead of 40 (and the bounds test gets 200, not 422, because there is no
field to validate).
"""
from __future__ import annotations

import importlib.util
import pathlib
import uuid

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.models.user import SystemSetting
from tests._pg_fixture import blank_session

MARKER = "ZZTDSV"

_BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
_VERSIONS_DIR = _BACKEND_ROOT / "alembic" / "versions"

SETTINGS_ENDPOINT = "/api/v1/user-management/settings/"
SETTINGS_GENERAL_ENDPOINT = "/api/v1/user-management/settings/general"
# Both halves of the blob: the GET is gated on `.view` and the POST/PUT on `.edit`.
_SETTINGS_PERMISSIONS = {
    "user_management.settings.view",
    "user_management.settings.edit",
}


# --------------------------------------------------------------------- fixtures


@pytest.fixture()
def db():
    with blank_session() as s:
        yield s


@pytest.fixture()
def settings_api(db, monkeypatch):
    from app.database import get_db
    from app.dependencies import get_current_user
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    user = {"id": str(uuid.uuid4()), "email": "dsv-threshold-caller@zzt.test"}

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: user

    async def _scope():
        from app.models.base import set_company_scope

        set_company_scope(db, None)
        return None

    app.dependency_overrides[apply_company_scope] = _scope
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in _SETTINGS_PERMISSIONS,
    )
    from fastapi.testclient import TestClient

    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(apply_company_scope, None)


def _seed_settings_row(db) -> SystemSetting:
    """Seeds through the ORM, not a raw `INSERT`: several NOT NULL columns on this table
    (`active`, `language`, `timezone`, `currency`, ...) carry a Python-side `Column(...,
    default=...)` only, no `server_default` - SQLAlchemy supplies those at flush time, a raw
    SQL insert never sees them and dies on `active`'s `NotNullViolation` regardless of
    anything a new migration does. Returns the row so a caller can read back a
    server-defaulted column (AC-1730) without a second query."""
    row = SystemSetting(id=str(uuid.uuid4()), name=f"{MARKER} Co")
    db.add(row)
    db.commit()
    return row


# --------------------------------------------------------------------- migration harness


def _dsv_migration_path() -> pathlib.Path:
    matches = sorted(_VERSIONS_DIR.glob("dsv_0001*.py"))
    assert matches, (
        "migration dsv_0001 not found under alembic/versions "
        "(PLAN-chatbot-dealer-stock-verdict.md S0)"
    )
    return matches[0]


def _load_dsv_migration():
    path = _dsv_migration_path()
    spec = importlib.util.spec_from_file_location("migration_dsv_0001", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _script_directory() -> ScriptDirectory:
    cfg = Config(str(_BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    return ScriptDirectory.from_config(cfg)


# --------------------------------------------------------------------- AC-1730


def test_dsv_0001_adds_threshold_column_default_50(db):
    """AC-1730: `system_settings.chatbot_stock_low_threshold_pct` is present - integer, not
    null, server default 50 - chained onto `spec_vocab_close_couple`, with the alembic graph
    still a single head.

    `dsv_0001`'s `upgrade()` is still called here so it is exercised, but it is column-existence
    guarded: `blank_session` builds its scratch schema from the MODELS (`Base.metadata.create_
    all`), which already carry the column once the coder's migration adds it to
    `app/models/user.py`, so upgrade() is a no-op against this schema rather than what puts the
    column there. The "column exists with the right shape" assertions below check the column
    directly (`information_schema`) instead of assuming upgrade() created it from nothing.

    Seeded through the ORM (`_seed_settings_row`, the same helper AC-1731 below uses), not a raw
    `INSERT INTO system_settings (id, name)`: that raw form hits `NotNullViolation` on `active`
    (a NOT NULL column with a Python-side-only default) regardless of anything this migration
    does - reproduced identically on `origin/main` with no diff applied."""
    module = _load_dsv_migration()

    assert module.revision == "dsv_0001"
    assert module.down_revision == "spec_vocab_close_couple"

    context = MigrationContext.configure(db.connection())
    with Operations.context(context):
        module.upgrade()

    row = _seed_settings_row(db)
    db.refresh(row)
    assert row.chatbot_stock_low_threshold_pct == 50

    not_null = db.execute(
        text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'system_settings' "
            "AND column_name = 'chatbot_stock_low_threshold_pct'"
        )
    ).scalar()
    assert not_null == "NO"

    column_default = db.execute(
        text(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name = 'system_settings' "
            "AND column_name = 'chatbot_stock_low_threshold_pct'"
        )
    ).scalar()
    assert column_default is not None and "50" in column_default

    heads = _script_directory().get_heads()
    assert len(heads) == 1, f"expected a single alembic head, found {heads}"


# --------------------------------------------------------------------- AC-1731


def test_settings_put_threshold_roundtrip_and_bounds(settings_api, db):
    """AC-1731: PUT/POST the general settings blob with
    `chatbot_stock_low_threshold_pct: 40`, read it back through GET in the `settings`
    dict; 0 and 101 are refused with a 422 before either reaches the column."""
    _seed_settings_row(db)

    saved = settings_api.post(
        SETTINGS_GENERAL_ENDPOINT, json={"chatbot_stock_low_threshold_pct": 40}
    )
    assert saved.status_code == 200, saved.text

    body = settings_api.get(SETTINGS_ENDPOINT).json()["settings"]
    assert body["chatbot_stock_low_threshold_pct"] == 40

    for bad in (0, 101):
        resp = settings_api.post(
            SETTINGS_GENERAL_ENDPOINT,
            json={"chatbot_stock_low_threshold_pct": bad},
        )
        assert resp.status_code == 422, (bad, resp.text)
