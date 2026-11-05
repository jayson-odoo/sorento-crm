"""AC-QTSO-CRM Phase 2, RED: the admin switch and the permission in front of every write.

UAC U1, U2, U3, U4, U18, U20. Plan: `documentation/plans/autocount/PLAN-ac-qtso-crm-04nov.md`.

Check order of every route (plan, "Routes"): permission -> switch -> record -> eligibility -> SS.
So with the switch OFF the answer is 403 `ac_write_switched_off` and the fake Shared Service sees
ZERO requests, not even the capability read.

Postgres only; every chain is seeded by `tests/_ac_write_support.py`.
"""
from __future__ import annotations

import uuid

import pytest

from tests._pg_fixture import blank_session
from tests._ac_write_support import (
    BASE,
    EDIT,
    OFF_MESSAGE,
    QT_CREATE_PATH,
    SO_CREATE_PATH,
    VIEW,
    WRITE,
    DTL_1,
    add_amendment,
    api_fixture,
    done_body,
    fake_ss,  # noqa: F401  (fixture)
    put_in_autocount,
    qty_row,
    set_switch,
)

SETTINGS = "/api/v1/user-management/settings/"
APP_CONFIG = "/api/v1/user-management/settings/app-config"
FIELD = "project_autocount_write_enabled"


# --------------------------------------------------------------------------- U1 / U4: the column


def test_the_switch_column_defaults_off_on_a_fresh_settings_row():
    from app.models.user import SystemSetting

    with blank_session() as db:
        row = SystemSetting(id=str(uuid.uuid4()), name="ZZT Co")
        db.add(row)
        db.flush()
        db.refresh(row)

        assert getattr(row, FIELD) is False


def test_the_update_model_accepts_the_switch():
    from app.api.v1.user_management.settings import SystemSettingUpdate

    assert FIELD in SystemSettingUpdate.model_fields
    assert SystemSettingUpdate(**{FIELD: True}).model_dump(exclude_unset=True) == {FIELD: True}


@pytest.fixture
def settings_api(monkeypatch):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user
    from app.main import app
    from app.services.user_service import UserPermissionService

    caller = {"id": str(uuid.uuid4()), "email": "acw-settings@zzt.test"}
    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True
    )
    with blank_session() as db:
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: caller
        try:
            set_switch(db, False)
            db.commit()
            yield TestClient(app), db
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)


def test_the_settings_get_dict_carries_the_switch(settings_api):
    client, _db = settings_api

    body = client.get(SETTINGS).json()

    assert body["settings"][FIELD] is False


def test_putting_the_switch_reaches_the_get_dict_and_app_config(settings_api):
    client, _db = settings_api

    put = client.put(SETTINGS + "general", json={FIELD: True})
    assert put.status_code == 200, put.text

    assert client.get(SETTINGS).json()["settings"][FIELD] is True
    assert client.get(APP_CONFIG).json()[FIELD] is True


def test_app_config_answers_the_switch_off_by_default(settings_api):
    client, _db = settings_api

    assert client.get(APP_CONFIG).json()[FIELD] is False


# --------------------------------------------------------------------------- the routes under test
#
# (label, method, path factory taking (so_world, amendment_id, qt_world) -> url)


@pytest.fixture
def so_api_off(fake_ss):
    yield from api_fixture("so", [VIEW, EDIT, WRITE], switch=False)


@pytest.fixture
def so_api_on(fake_ss):
    yield from api_fixture("so", [VIEW, EDIT, WRITE], switch=True)


@pytest.fixture
def so_api_no_perm(fake_ss):
    yield from api_fixture("so", [VIEW, EDIT], switch=True)


@pytest.fixture
def qt_api_off(fake_ss):
    yield from api_fixture("qt", [VIEW, EDIT, WRITE], switch=False)


@pytest.fixture
def qt_api_no_perm(fake_ss):
    yield from api_fixture("qt", [VIEW, EDIT], switch=True)


def _so_urls(db, world):
    """All three SO write routes. The update route needs a published amendment to exist."""
    put_in_autocount(db, world)
    amendment = add_amendment(db, world, [qty_row(world, world.line1, "80")])
    db.commit()
    return {
        "create": f"{BASE}/sales-orders/{world.order.id}/autocount",
        "update": f"{BASE}/sales-orders/amendments/{amendment.id}/autocount",
        "cancel": f"{BASE}/sales-orders/{world.order.id}/autocount/cancel",
    }


def _qt_urls(world):
    return {
        "send": f"{BASE}/quotation-documents/{world.document.id}/autocount",
        "cancel": f"{BASE}/quotation-documents/{world.document.id}/autocount/cancel",
    }


# --------------------------------------------------------------------------- U2: switch OFF


@pytest.mark.parametrize("route", ["create", "update", "cancel"])
def test_so_write_routes_answer_403_when_the_switch_is_off_and_never_call_ss(
    so_api_off, fake_ss, route
):
    client, db, world = so_api_off
    urls = _so_urls(db, world)

    response = client.post(urls[route])

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "ac_write_switched_off"
    assert response.json()["message"] == OFF_MESSAGE
    assert fake_ss.calls == [], "the Shared Service client must not be touched while the switch is off"


@pytest.mark.parametrize("route", ["send", "cancel"])
def test_quotation_write_routes_answer_403_when_the_switch_is_off_and_never_call_ss(
    qt_api_off, fake_ss, route
):
    client, _db, world = qt_api_off

    response = client.post(_qt_urls(world)[route])

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "ac_write_switched_off"
    assert response.json()["message"] == OFF_MESSAGE
    assert fake_ss.calls == []


def test_the_capabilities_route_says_disabled_with_empty_maps_and_no_ss_call(so_api_off, fake_ss):
    client, _db, _world = so_api_off

    response = client.get(f"{BASE}/autocount-write/capabilities")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "enabled": False, "sales_orders": {}, "quotations": {}, "book": None,
    }
    assert fake_ss.calls == []


# --------------------------------------------------------------------------- U3: switch ON


def test_the_capabilities_route_reaches_ss_when_the_switch_is_on(so_api_on, fake_ss):
    client, _db, _world = so_api_on

    response = client.get(f"{BASE}/autocount-write/capabilities")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["enabled"] is True
    assert body["sales_orders"]["create_doc"] == {"enabled": True, "reason": None}
    assert len(fake_ss.calls) == 1
    assert fake_ss.calls[0].url.params["companyCode"] == "SRT"


def test_the_so_create_route_reaches_the_client_when_the_switch_is_on(so_api_on, fake_ss):
    client, _db, world = so_api_on
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (200, done_body())

    response = client.post(f"{BASE}/sales-orders/{world.order.id}/autocount")

    assert response.status_code == 200, response.text
    assert len(fake_ss.to("POST", SO_CREATE_PATH)) == 1


def test_the_quotation_route_reaches_the_client_when_the_switch_is_on(fake_ss):
    gen = api_fixture("qt", [VIEW, EDIT, WRITE], switch=True)
    client, _db, world = next(gen)
    try:
        fake_ss.answers[("POST", QT_CREATE_PATH)] = (200, done_body(doc_no="QT000777"))

        response = client.post(_qt_urls(world)["send"])

        assert response.status_code == 200, response.text
        assert len(fake_ss.to("POST", QT_CREATE_PATH)) == 1
    finally:
        gen.close()


# --------------------------------------------------------------------------- U18: the permission


@pytest.mark.parametrize("route", ["create", "update", "cancel"])
def test_so_write_routes_answer_403_without_the_permission_even_with_the_switch_on(
    so_api_no_perm, fake_ss, route
):
    client, db, world = so_api_no_perm
    urls = _so_urls(db, world)

    response = client.post(urls[route])

    assert response.status_code == 403, response.text
    assert WRITE in response.text
    assert fake_ss.calls == []


@pytest.mark.parametrize("route", ["send", "cancel"])
def test_quotation_write_routes_answer_403_without_the_permission(qt_api_no_perm, fake_ss, route):
    client, _db, world = qt_api_no_perm

    response = client.post(_qt_urls(world)[route])

    assert response.status_code == 403, response.text
    assert WRITE in response.text
    assert fake_ss.calls == []


def test_the_permission_is_checked_before_the_switch(fake_ss):
    """No permission AND switch off: the caller learns nothing about the setting."""
    gen = api_fixture("so", [VIEW, EDIT], switch=False)
    client, _db, world = next(gen)
    try:
        response = client.post(f"{BASE}/sales-orders/{world.order.id}/autocount")

        assert response.status_code == 403
        assert response.json().get("code") != "ac_write_switched_off"
    finally:
        gen.close()


def test_the_capabilities_route_needs_the_permission_too(so_api_no_perm, fake_ss):
    client, _db, _world = so_api_no_perm

    response = client.get(f"{BASE}/autocount-write/capabilities")

    assert response.status_code == 403
    assert fake_ss.calls == []


def test_the_permission_slug_is_registered_with_its_plain_name():
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    by_slug = {entry["slug"]: entry["name"] for entry in PERMISSION_REGISTRY}
    assert by_slug.get(WRITE) == "Send quotations and sales orders to AutoCount"


def test_the_migration_adds_the_switch_the_columns_and_the_grant():
    """`acqs_0001_project_ac_write` chains onto main's head."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "acqs_0001_project_ac_write.py"
    assert path.exists(), "migration acqs_0001_project_ac_write is missing"
    spec = importlib.util.spec_from_file_location("acqs_0001", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "acqs_0001_project_ac_write"
    # The parent moves whenever main gains a head (scripts/alembic-reparent.sh), so pin that it
    # chains onto a real committed revision rather than one id.
    assert module.down_revision and (path.parent / f"{module.down_revision}.py").exists()
    source = path.read_text()
    for needle in (
        "project_autocount_write_enabled",
        "autocount_doc_key",
        "autocount_last_modified",
        "autocount_issue_id",
        WRITE,
    ):
        assert needle in source, needle
