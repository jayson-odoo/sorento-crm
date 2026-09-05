"""S8a end-to-end coverage for the chatbot settings screen (AC-809, AC-810, issue #679).

`test_s8_settings_screen.py` and `test_s8_switches_in_settings.py` already pin the unit-level
red/green contract for the vocabulary route and the two switches. This file adds the slices
the tester's brief called out as still missing once the coder's implementation landed:

1. `PUT /settings/general` with an unknown lane names the offender AND lists the full
   vocabulary in the same 422; a valid list still saves and is echoed back.
2. `GET /settings/chatbot-lanes` through the REAL module guard (`module_guard_strict` on,
   module rows installed for the tenant), plus the two permission-denial shapes.
3. A live turn, through the real engine, with `chatbot_ordering_enabled` flipped via the
   SETTINGS ROUTE (never the row directly): the turn finishes without delegating, both
   `/complete` forms answer 410 `CHATBOT_S7_MODE_OWNS_THE_TAIL`, and flipping the switch
   back off through the same route lets the very next `/complete` call through with no
   process restart.
4. Both AC-810 switches together round-trip through `GET /settings/` - the SOLE manual
   dict builder for `system_settings` (confirmed below: there is no `GET /general` route
   at all, unlike the `get_user`/`get_me` pair the CLAUDE.md lesson warns about).

Postgres only, via `tests/_pg_fixture.py` / `tests/chatbot/conftest.py` - the shared dev
database is never touched. Every redis key a live turn might touch is cleared in a
`finally` (S7 mode with a fresh contact never reaches ordering's redis path, since the
turn fails before any ticket is taken here, but the guard costs nothing to keep).

Run:
    CHATBOT_FIXTURES_DIR=<n8n worktree>/n8n-workflows-init/tests/fixtures \
        pytest tests/chatbot/test_s8_settings_screen_e2e.py -v
"""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text

from tests._pg_fixture import TEST_PREFIX, blank_session

LANES_ENDPOINT = "/api/v1/user-management/settings/chatbot-lanes"
GENERAL_ENDPOINT = "/api/v1/user-management/settings/general"
SETTINGS_ENDPOINT = "/api/v1/user-management/settings/"
VIEW_PERMISSION = "user_management.settings.view"
EDIT_PERMISSION = "user_management.settings.edit"
_USER = {"id": str(uuid.uuid4()), "email": "chatbot-e2e-caller@zzt.test"}


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


@pytest.fixture
def api(db, monkeypatch):
    """Full `app.main.app`, JWT principal, `get_db`/`get_current_user` overridden,
    permission check monkeypatched against an `allow` set - the same shape
    `test_s8_settings_screen.py::api` uses."""
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


# --------------------------------------------------------------------------- #
# 1. PUT /settings/general: unknown lane names the offender and lists the
#    vocabulary; a valid list saves and is echoed back (AC-809)
# --------------------------------------------------------------------------- #


def test_ac809_unknown_lane_422_names_offender_and_lists_the_vocabulary(api, db):
    from app.services.chatbot.contracts import CRM_COMPLETED_BRANCH_KINDS

    client, allow = api
    allow.add(EDIT_PERMISSION)
    _seed_settings(db)

    resp = client.put(
        GENERAL_ENDPOINT, json={"chatbot_completed_lanes": ["definitely_not_a_lane"]}
    )

    assert resp.status_code == 422, resp.text
    detail = resp.text
    assert "definitely_not_a_lane" in detail, "the 422 must name the offending lane"
    for kind in CRM_COMPLETED_BRANCH_KINDS:
        assert kind in detail, (
            f"the 422 must list the full vocabulary so the caller can pick a real lane; "
            f"{kind!r} is missing from: {detail}"
        )


def test_ac809_valid_lane_list_saves_and_settings_get_echoes_it(api, db):
    from app.services.chatbot.contracts import CRM_COMPLETED_BRANCH_KINDS

    client, allow = api
    allow.add(EDIT_PERMISSION)
    allow.add(VIEW_PERMISSION)
    _seed_settings(db)

    valid_lanes = sorted(CRM_COMPLETED_BRANCH_KINDS)[:2]
    resp = client.put(GENERAL_ENDPOINT, json={"chatbot_completed_lanes": valid_lanes})
    assert resp.status_code == 200, resp.text

    # There is no dedicated `GET /general` route - confirmed directly rather than assumed,
    # since the CLAUDE.md lesson is about a column missing from ONE of two builders. Here
    # there is only ONE: `GET /settings/` (see test 4 below for the direct route-absence
    # check). It is what a save is "echoed back" through.
    resp = client.get(SETTINGS_ENDPOINT)
    assert resp.status_code == 200, resp.text
    assert resp.json()["settings"]["chatbot_completed_lanes"] == valid_lanes


# --------------------------------------------------------------------------- #
# 2. GET /settings/chatbot-lanes through the REAL module guard (AC-809)
# --------------------------------------------------------------------------- #


def _seed_module_rows(db) -> None:
    """`base` (what this route is actually gated on - `user_management.router` is
    mounted with `require_module_enabled("base")`) and `chatbot` (the module this
    settings screen configures), both installed and enabled for the default tenant.

    `tenant_modules.module_key` FKs to `app_modules_catalog.module_key` (Postgres
    enforces it, a blank sqlite schema would not have) - the catalog rows must exist
    first, the same shape `test_module_and_endpoint.py::TestGuards` uses.
    """
    from app.models.app_modules import AppModuleCatalog, TenantModule
    from app.modules.runtime.installer import DEFAULT_TENANT_ID

    db.add_all(
        [
            AppModuleCatalog(module_key="base", display_name="Base"),
            AppModuleCatalog(module_key="chatbot", display_name="Chatbot turn engine"),
        ]
    )
    db.flush()
    db.add_all(
        [
            TenantModule(tenant_id=DEFAULT_TENANT_ID, module_key="base", enabled=True),
            TenantModule(tenant_id=DEFAULT_TENANT_ID, module_key="chatbot", enabled=True),
        ]
    )
    db.commit()


def test_ac809_lanes_route_works_under_strict_module_guard_with_view_permission(
    api, db, monkeypatch
):
    from app.config import settings as app_settings

    client, allow = api
    _seed_settings(db)
    _seed_module_rows(db)
    monkeypatch.setattr(app_settings, "module_guard_strict", True, raising=False)
    allow.add(VIEW_PERMISSION)

    resp = client.get(LANES_ENDPOINT)

    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list) and resp.json(), (
        "the vocabulary route must actually answer under strict mode with the module "
        "rows installed, not merely fail to 403"
    )


def test_ac809_lanes_route_403s_the_edit_only_caller_naming_view(api, db, monkeypatch):
    from app.config import settings as app_settings

    client, allow = api
    _seed_settings(db)
    _seed_module_rows(db)
    monkeypatch.setattr(app_settings, "module_guard_strict", True, raising=False)
    allow.add(EDIT_PERMISSION)  # edit is not view

    resp = client.get(LANES_ENDPOINT)

    assert resp.status_code == 403, resp.text
    assert VIEW_PERMISSION in resp.text


def test_ac809_lanes_route_403s_a_caller_with_neither_permission(api, db, monkeypatch):
    from app.config import settings as app_settings

    client, allow = api
    assert allow == set()
    _seed_settings(db)
    _seed_module_rows(db)
    monkeypatch.setattr(app_settings, "module_guard_strict", True, raising=False)

    resp = client.get(LANES_ENDPOINT)

    assert resp.status_code == 403, resp.text
    assert VIEW_PERMISSION in resp.text


# --------------------------------------------------------------------------- #
# 3. A live turn, ordering flipped through the SETTINGS ROUTE (AC-810)
# --------------------------------------------------------------------------- #

from tests.chatbot.test_chat_turn_endpoint import (  # noqa: E402,F401 - fixtures used by name
    api_key,
    client,
    seeded_contact,
    stub_engine_seams,
)
from tests.chatbot.test_engine import CONTACT_ID, _envelope  # noqa: E402


def _admin_override(monkeypatch) -> None:
    """The PUT /settings/general call in this test goes through the SETTINGS ROUTE as an
    admin, not through the row directly - so it needs `get_current_user` +
    `check_user_has_permission` overridden on the SAME `app.main.app` the `client`
    fixture already has `get_db` overridden on. The chat turn routes authenticate via
    `X-API-Key` (`get_external_api_user`) and their OWN permission grant
    (`integration.chat_turn.submit`, seeded for real on the `api_key` fixture's
    integration role) - `check_user_has_permission` is the SAME method both paths call
    (`require_permission` and `require_external_permission`), so the fake must fall
    through to the real lookup for every uid/slug that is not this test's fake admin,
    or the chat turn call 403s on a grant that really exists in the DB.
    """
    from app.dependencies import get_current_user
    from app.main import app
    from app.services.user_service import UserPermissionService

    admin_id = str(uuid.uuid4())
    monkeypatch.setitem(
        app.dependency_overrides,
        get_current_user,
        lambda: {"id": admin_id, "email": "chatbot-e2e-admin@zzt.test"},
    )
    original_check = UserPermissionService.check_user_has_permission

    def _fake_check(self, uid, slug):
        if uid == admin_id and slug in (VIEW_PERMISSION, EDIT_PERMISSION):
            return True
        return original_check(self, uid, slug)

    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", _fake_check)


def test_ac810_live_turn_via_settings_route_then_complete_gated_then_restored(
    client, api_key, session_factory, seeded_contact, stub_engine_seams, monkeypatch
):
    from app.models.chatbot_turn import ChatbotTurn
    from app.models.user import SystemSetting

    _admin_override(monkeypatch)

    db = session_factory()
    db.add(SystemSetting(id=str(uuid.uuid4()), name=f"{TEST_PREFIX} Co"))
    db.commit()

    # 1. Flip ordering ON through the settings ROUTE, as an admin - never the row.
    flip_on = client.put(GENERAL_ENDPOINT, json={"chatbot_ordering_enabled": True})
    assert flip_on.status_code == 200, flip_on.text

    # 2. A live turn through the real engine (parser/access stubbed at the LLM/roster
    #    seam by `stub_engine_seams`, nothing else). `chatbot_completed_lanes` is still
    #    the column default (`[]`), so the default parser stub's `business_query` lane
    #    is one the CRM cannot complete - which is exactly what proves S7 mode is now
    #    live: the turn must FINISH (done or failed), never sit `delegated` waiting for
    #    n8n to run a lane that no longer exists on this build's tail.
    envelope = _envelope()
    envelope.message["message"]["messageId"] = "ZZT-msg-s8a-e2e-live-turn"
    turn_resp = client.post(
        "/api/v1/external/chat/turn",
        json={"envelope": json.loads(envelope.model_dump_json())},
        headers={"X-API-Key": api_key},
    )
    assert turn_resp.status_code == 200, turn_resp.text
    turn_body = turn_resp.json()
    assert turn_body["delegate"] is None, (
        "S7 mode owns the tail - a live turn must never come back delegated"
    )
    turn_id = turn_body["turn_id"]

    row = db.query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).first()
    assert row is not None
    assert row.status in ("done", "failed"), (
        f"a live S7-mode turn must finish one way or the other, got {row.status!r}"
    )

    # 3. Both /complete forms are gone while ordering is on.
    by_id = client.post(
        f"/api/v1/external/chat/turn/{turn_id}/complete",
        json={"item": {"branch_kind": "low_signal"}},
        headers={"X-API-Key": api_key},
    )
    assert by_id.status_code == 410, by_id.text
    assert by_id.json().get("code") == "CHATBOT_S7_MODE_OWNS_THE_TAIL", by_id.json()

    by_body = client.post(
        "/api/v1/external/chat/turn/complete",
        json={"item": {"branch_kind": "low_signal"}},
        headers={"X-API-Key": api_key},
    )
    assert by_body.status_code == 410, by_body.text
    assert by_body.json().get("code") == "CHATBOT_S7_MODE_OWNS_THE_TAIL", by_body.json()

    # 4. Flip it back OFF through the same settings route.
    flip_off = client.put(GENERAL_ENDPOINT, json={"chatbot_ordering_enabled": False})
    assert flip_off.status_code == 200, flip_off.text

    # 5. The very next /complete answers non-410, with no process restart in between -
    # the gate reads the row fresh on every request. The tail composition itself is
    # monkeypatched here (same pattern as `test_s8_switches_in_settings.py`'s
    # `test_ordering_off_via_the_row_answers_200_not_410`): this test's job is the GATE,
    # not re-proving the tail already covered elsewhere.
    canned = {
        "turn_id": turn_id,
        "reply": {
            "text": "Here is what I found.",
            "quick_replies": None,
            "result_set": [],
            "attachments_src": None,
        },
        "actions": [{"kind": "send_message", "text": "Here is what I found."}],
        "session_patch": None,
    }

    class _FakeResult:
        def as_dict(self) -> dict:
            return dict(canned)

    monkeypatch.setattr(
        "app.api.v1.external.chat.complete_turn", lambda *a, **k: _FakeResult()
    )

    after_flip = client.post(
        f"/api/v1/external/chat/turn/{turn_id}/complete",
        json={"item": {"branch_kind": "low_signal"}},
        headers={"X-API-Key": api_key},
    )
    assert after_flip.status_code != 410, after_flip.text
    assert after_flip.status_code == 200, after_flip.text
    assert after_flip.json()["reply"]["text"] == "Here is what I found."


# --------------------------------------------------------------------------- #
# 4. Both AC-810 switches, saved together, round-trip through the ONE manual
#    dict builder there is - and there is no GET /general to also check
# --------------------------------------------------------------------------- #


def test_ac810_no_dedicated_get_general_route_exists(api, db):
    """Confirms the CLAUDE.md "both manual dict builders" lesson does not apply here:
    unlike `get_user`/`get_me`, `system_settings` has exactly ONE GET builder
    (`GET /settings/`). A `GET /general` is not registered at all - 405, since `PUT` and
    `POST` ARE registered on that path."""
    client, allow = api
    allow.add(VIEW_PERMISSION)
    allow.add(EDIT_PERMISSION)
    _seed_settings(db)

    resp = client.get(GENERAL_ENDPOINT)

    assert resp.status_code == 405, (
        f"expected no GET handler on {GENERAL_ENDPOINT} (only PUT/POST), got "
        f"{resp.status_code}: {resp.text}"
    )


def test_ac810_both_switches_saved_together_round_trip_through_settings_get(api, db):
    client, allow = api
    allow.add(EDIT_PERMISSION)
    allow.add(VIEW_PERMISSION)
    _seed_settings(db)

    resp = client.put(
        GENERAL_ENDPOINT,
        json={
            "chatbot_ordering_enabled": True,
            "chatbot_business_lane_enabled": True,
        },
    )
    assert resp.status_code == 200, resp.text

    resp = client.get(SETTINGS_ENDPOINT)
    assert resp.status_code == 200, resp.text
    body = resp.json()["settings"]
    assert body["chatbot_ordering_enabled"] is True
    assert body["chatbot_business_lane_enabled"] is True

    # And the row itself, directly - belt and braces against a GET-side leak that would
    # make the two assertions above pass for the wrong reason (e.g. a stale cached body).
    from app.models.user import SystemSetting

    db.expire_all()
    row = db.query(SystemSetting).first()
    assert row.chatbot_ordering_enabled is True
    assert row.chatbot_business_lane_enabled is True
