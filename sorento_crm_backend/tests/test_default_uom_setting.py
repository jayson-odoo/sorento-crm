"""The default unit of measure is a SETTING, not a constant in the code.

`ProductService._get_default_uom_id` hardcoded `EA`, and the fallback before it took
whatever unit the database happened to return first - which is how 11,415 products came to
be stamped `L`. Correcting that with a backfill script means guessing what an admin can
simply state, so the admin states it here and a re-import of the product list applies it.

Two halves, and they fail differently:

* the settings blob carries the column BOTH ways - the standing `response_model` /
  manual-dict-builder trap, which is exactly how a new settings column reaches the API and
  never reaches the screen;
* the product service reads it, falling back to the built-in `EA` when nobody has chosen.

Postgres only, on a blank scratch schema, and the permission check is monkeypatched the same
way `tests/scm/test_plan_grain_policy.py` does it - this is about the column, not about auth.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.models.product import UnitOfMeasure
from app.models.user import SystemSetting
from app.services import product_service as product_service_mod
from app.services.product_service import ProductService
from tests._pg_fixture import blank_session

SETTINGS_ENDPOINT = "/api/v1/user-management/settings/"
SETTINGS_GENERAL_ENDPOINT = "/api/v1/user-management/settings/general"
_SETTINGS_PERMISSION = "user_management.settings.view"

MARKER = "ZZTUOM"


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

    user = {"id": str(uuid.uuid4()), "email": "default-uom-caller@zzt.test"}

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: user

    # `units_of_measure` is company-scoped, and a principal with no grants resolves to
    # UNSET - fail-closed, zero rows - so the unit this test seeds would be invisible to
    # the route that validates it. `None` is the documented "no predicate" state: this
    # test is about the column, not about isolation, which has its own suite.
    async def _scope():
        from app.models.base import set_company_scope

        set_company_scope(db, None)
        return None

    app.dependency_overrides[apply_company_scope] = _scope
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug == _SETTINGS_PERMISSION,
    )
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(apply_company_scope, None)


def _seed_settings_row(db) -> None:
    db.add(SystemSetting(id=str(uuid.uuid4()), name=f"{MARKER} Co"))
    db.commit()


def _seed_uom(db, code: str, name: str) -> UnitOfMeasure:
    row = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=code, uom_name=name)
    db.add(row)
    db.commit()
    return row


# --- the settings blob ------------------------------------------------------

def test_the_blob_carries_the_column_before_anybody_sets_it(settings_api, db):
    """`None`, and the resolved code `None` beside it - the screen reads "Automatic" from
    the absence, and would render a stale value if the key were simply missing."""
    _seed_settings_row(db)

    body = settings_api.get(SETTINGS_ENDPOINT).json()["settings"]

    assert body["default_uom_id"] is None
    assert body["default_uom_code"] is None


def test_the_setting_round_trips_and_reports_the_code(settings_api, db):
    """A new settings column has to be on the GET dict AND on `SystemSettingUpdate`, or it
    reaches the API and never the screen. The CODE rides along because the UI may not show
    a bare UUID."""
    _seed_settings_row(db)
    ctn = _seed_uom(db, f"{MARKER}-CTN", "Carton")

    saved = settings_api.post(SETTINGS_GENERAL_ENDPOINT, json={"default_uom_id": ctn.id})
    assert saved.status_code == 200, saved.text

    body = settings_api.get(SETTINGS_ENDPOINT).json()["settings"]
    assert body["default_uom_id"] == ctn.id
    assert body["default_uom_code"] == f"{MARKER}-CTN"


def test_the_setting_can_be_cleared_back_to_automatic(settings_api, db):
    _seed_settings_row(db)
    ctn = _seed_uom(db, f"{MARKER}-CTN", "Carton")
    settings_api.post(SETTINGS_GENERAL_ENDPOINT, json={"default_uom_id": ctn.id})

    cleared = settings_api.post(SETTINGS_GENERAL_ENDPOINT, json={"default_uom_id": None})
    assert cleared.status_code == 200, cleared.text

    assert settings_api.get(SETTINGS_ENDPOINT).json()["settings"]["default_uom_id"] is None


def test_a_unit_that_does_not_exist_is_refused(settings_api, db):
    """Named at the point of writing rather than accepted and discovered later by an import
    that silently falls back - the same guard the default supplier already has."""
    _seed_settings_row(db)

    resp = settings_api.post(
        SETTINGS_GENERAL_ENDPOINT, json={"default_uom_id": str(uuid.uuid4())}
    )

    assert resp.status_code == 400, resp.text
    assert "unit" in resp.text.lower()


# --- what the product service does with it ----------------------------------

@pytest.fixture(autouse=True)
def _isolate_side_effects(monkeypatch):
    """Supplier linking and embedding publishing are irrelevant here and enqueue RQ jobs."""
    monkeypatch.setattr(
        product_service_mod.ProductService,
        "_bulk_publish_product_embedding_events",
        lambda self, *a, **kw: None,
    )
    monkeypatch.setattr(
        product_service_mod.ProductService,
        "_resolve_default_supplier_for_new_product",
        lambda self: None,
    )
    monkeypatch.setattr(
        product_service_mod.ProductService,
        "_default_standard_lead_time_days",
        lambda self: None,
    )


def test_the_service_uses_the_configured_unit(db):
    settings = SystemSetting(id=str(uuid.uuid4()), name=f"{MARKER} Co")
    db.add(settings)
    ctn = _seed_uom(db, f"{MARKER}-CTN", "Carton")
    settings.default_uom_id = ctn.id
    db.commit()

    assert ProductService(db)._get_default_uom_id() == ctn.id


def test_the_service_falls_back_to_ea_when_nobody_has_chosen(db):
    """Unchanged behaviour, asserted so the fallback claim is not just a comment."""
    _seed_settings_row(db)

    resolved = ProductService(db)._get_default_uom_id()

    assert db.query(UnitOfMeasure).filter(UnitOfMeasure.id == resolved).one().uom_code == "EA"


def test_deleting_the_configured_unit_puts_the_setting_back_to_automatic(db):
    """`ondelete="SET NULL"`, so the import falls back rather than pointing at nothing.
    Written as a test because the alternative - a defensive existence check in the service -
    is machinery for a case the FK already answers."""
    settings = SystemSetting(id=str(uuid.uuid4()), name=f"{MARKER} Co")
    db.add(settings)
    ctn = _seed_uom(db, f"{MARKER}-CTN", "Carton")
    settings.default_uom_id = ctn.id
    db.commit()

    db.delete(ctn)
    db.commit()
    db.refresh(settings)

    assert settings.default_uom_id is None
    resolved = ProductService(db)._get_default_uom_id()
    assert db.query(UnitOfMeasure).filter(UnitOfMeasure.id == resolved).one().uom_code == "EA"
