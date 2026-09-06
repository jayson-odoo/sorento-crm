"""S8a RED tests - the chatbot settings screen (AC-809, issue #679).

Written BEFORE the route/validation exist. As of this commit
`GET /api/v1/user-management/settings/chatbot-lanes` is not mounted anywhere -
`app/api/v1/user_management/settings.py` has no `chatbot-lanes` route - and
`_update_general_settings_impl`'s own docstring for `chatbot_completed_lanes`
(the field on `SystemSettingUpdate`) says explicitly that an unknown branch kind is
"the ENGINE's problem to ignore-and-warn, not this endpoint's to reject" - the exact
opposite of AC-809's "the save is refused with a 422 naming the lane". Every test
below is expected to fail for one of those two reasons; none should error on a typo
in the test file itself.

Dependency-override pattern from `tests/test_settings_app_config_gate.py` (overrides
`get_db` / `get_current_user`, monkeypatches `UserPermissionService.
check_user_has_permission` against an `allow` set of granted slugs). Postgres
`blank_session()` for the DB, per PRINCIPLES.md - never sqlite.

Run: pytest tests/chatbot/test_s8_settings_screen.py -v
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from tests._pg_fixture import TEST_PREFIX, blank_session

LANES_ENDPOINT = "/api/v1/user-management/settings/chatbot-lanes"
GENERAL_ENDPOINT = "/api/v1/user-management/settings/general"
SETTINGS_ENDPOINT = "/api/v1/user-management/settings/"
VIEW_PERMISSION = "user_management.settings.view"
EDIT_PERMISSION = "user_management.settings.edit"
_USER = {"id": str(uuid.uuid4()), "email": "chatbot-settings-caller@zzt.test"}


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


@pytest.fixture
def api(db, monkeypatch):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user
    from app.main import app
    from app.services.user_service import UserPermissionService

    allow: set[str] = set()

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _USER
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in allow,
    )
    client = TestClient(app)
    try:
        yield client, allow
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def _seed_settings(db, **overrides):
    from app.models.user import SystemSetting

    row = SystemSetting(id=str(uuid.uuid4()), name=f"{TEST_PREFIX} Co", **overrides)
    db.add(row)
    db.commit()
    return row


def _items(resp) -> list[dict]:
    """Tolerates either a bare list or an `{"items": [...]}` envelope - the AC does
    not pin the wrapper, only the vocabulary and the per-kind shape."""
    body = resp.json()
    return body["items"] if isinstance(body, dict) and "items" in body else body


# --------------------------------------------------------------------------- #
# GET /settings/chatbot-lanes - the vocabulary, single source
# contracts.CRM_COMPLETED_BRANCH_KINDS, each with a built/not-built flag (AC-809)
# --------------------------------------------------------------------------- #


def test_lanes_denied_without_view_permission(api, db):
    client, _allow = api
    _seed_settings(db)

    resp = client.get(LANES_ENDPOINT)

    assert resp.status_code == 403
    assert VIEW_PERMISSION in str(resp.json())


def test_lanes_vocabulary_is_exactly_crm_completed_branch_kinds(api, db):
    from app.services.chatbot.contracts import CRM_COMPLETED_BRANCH_KINDS

    client, allow = api
    allow.add(VIEW_PERMISSION)
    _seed_settings(db)

    resp = client.get(LANES_ENDPOINT)

    assert resp.status_code == 200, resp.text
    items = _items(resp)
    kinds = {item["kind"] for item in items}
    assert kinds == set(CRM_COMPLETED_BRANCH_KINDS), (
        "AC-809: the vocabulary served is contracts.CRM_COMPLETED_BRANCH_KINDS, the "
        "single source - not a hand-picked subset, and not BRANCH_KINDS either"
    )
    for item in items:
        assert "built" in item, item


def test_lanes_non_business_kinds_are_always_built(api, db):
    """Only the three business arms (business_query, check_promotion, stock_denied)
    have an extra deployment gate (`chatbot_business_lane_enabled`, S6a); the other
    ten kinds in CRM_COMPLETED_BRANCH_KINDS have no such gate and are built
    unconditionally."""
    from app.services.chatbot.contracts import BUSINESS_BRANCH_KINDS

    client, allow = api
    allow.add(VIEW_PERMISSION)
    _seed_settings(db)  # chatbot_business_lane_enabled defaults False

    resp = client.get(LANES_ENDPOINT)
    assert resp.status_code == 200, resp.text
    for item in _items(resp):
        if item["kind"] not in BUSINESS_BRANCH_KINDS:
            assert item["built"] is True, item


def test_lanes_business_kinds_built_flag_follows_the_business_lane_switch(api, db):
    """The exact predicate this build gates a business arm's completion on
    (`engine._business_lane_enabled`, see `engine.py` around the `business.handles`
    override): checking `business_query` in `chatbot_completed_lanes` does nothing
    at all until this switch is also on, so the settings screen must say so via
    `built` rather than let the owner discover it by pressing Save."""
    from app.services.chatbot.contracts import BUSINESS_BRANCH_KINDS

    client, allow = api
    allow.add(VIEW_PERMISSION)
    row = _seed_settings(db)

    resp = client.get(LANES_ENDPOINT)
    assert resp.status_code == 200, resp.text
    items = {item["kind"]: item["built"] for item in _items(resp)}
    for kind in BUSINESS_BRANCH_KINDS:
        assert items[kind] is False, (kind, items)

    db.execute(
        text(
            "UPDATE system_settings SET chatbot_business_lane_enabled = true WHERE id = :id"
        ),
        {"id": row.id},
    )
    db.commit()

    resp = client.get(LANES_ENDPOINT)
    assert resp.status_code == 200, resp.text
    items = {item["kind"]: item["built"] for item in _items(resp)}
    for kind in BUSINESS_BRANCH_KINDS:
        assert items[kind] is True, (kind, items)


# --------------------------------------------------------------------------- #
# PUT /settings/general - a lane outside the vocabulary, or one the build cannot
# complete, is refused with a 422 naming it (AC-809)
# --------------------------------------------------------------------------- #


def test_put_general_rejects_a_branch_kind_outside_the_vocabulary(api, db):
    client, allow = api
    allow.add(EDIT_PERMISSION)
    _seed_settings(db)

    resp = client.put(
        GENERAL_ENDPOINT, json={"chatbot_completed_lanes": ["not_a_real_kind"]}
    )

    assert resp.status_code == 422, resp.text
    assert "not_a_real_kind" in resp.text


def test_put_general_rejects_a_kind_the_build_cannot_complete(api, db, monkeypatch):
    """Today `CRM_COMPLETED_BRANCH_KINDS == BRANCH_KINDS` (every one of the 13 arms is
    code-completable), so there is no naturally-occurring kind that is a real branch
    kind but not build-completable. Per the brief, construct one by shrinking the
    vocabulary the validator reads at call time, the same lazy-import pattern every
    other validator in this function already uses (see
    `_update_general_settings_impl`'s `from app.services.form_sla_service import
    FORM_SLA_TYPES` for the precedent)."""
    import app.services.chatbot.contracts as contracts

    client, allow = api
    allow.add(EDIT_PERMISSION)
    _seed_settings(db)

    shrunk = contracts.CRM_COMPLETED_BRANCH_KINDS - {"ideate"}
    monkeypatch.setattr(contracts, "CRM_COMPLETED_BRANCH_KINDS", shrunk)

    resp = client.put(GENERAL_ENDPOINT, json={"chatbot_completed_lanes": ["ideate"]})

    assert resp.status_code == 422, resp.text
    assert "ideate" in resp.text


# --------------------------------------------------------------------------- #
# GET /settings - the manual dict builder already carries the three fields.
# Expected to already be GREEN today (AC-304 landed them at S3); kept here as the
# regression net AC-809 leans on rather than re-deriving.
# --------------------------------------------------------------------------- #


def test_get_settings_returns_the_three_existing_chatbot_fields(api, db):
    client, allow = api
    allow.add(VIEW_PERMISSION)
    _seed_settings(
        db,
        chatbot_completed_lanes=["low_signal"],
        chatbot_stock_denial_enabled=True,
        chatbot_unsupported_domains=["goods_receive"],
    )

    resp = client.get(SETTINGS_ENDPOINT)

    assert resp.status_code == 200, resp.text
    body = resp.json()["settings"]
    assert body["chatbot_completed_lanes"] == ["low_signal"]
    assert body["chatbot_stock_denial_enabled"] is True
    assert body["chatbot_unsupported_domains"] == ["goods_receive"]
