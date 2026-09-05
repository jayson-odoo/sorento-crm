"""S8a RED tests - the owner-operated switches leave the environment (AC-810, #679).

`CHATBOT_BUSINESS_LANE_ENABLED` and `CHATBOT_ORDERING_ENABLED` become
`system_settings` columns (`chatbot_business_lane_enabled`, `chatbot_ordering_enabled`,
default false, additive migration), read by the engine PER TURN instead of once from
`app.config.settings`, and toggled on the same settings screen as AC-809.
`CHATBOT_TURN_ON_WORKER` stays a deployment property and is NOT touched here.

Written BEFORE the model gained the two columns. As of this commit
`app/models/user.py::SystemSetting` has no `chatbot_business_lane_enabled` or
`chatbot_ordering_enabled` column, `app/services/chatbot/engine.py::
_business_lane_enabled` / `_s7_mode` and `app/api/v1/external/chat.py::_s7_mode`
still read `app.config.settings` with no `db` argument, and `app/config.py` still
declares both flags. Every test below is expected to fail for one of those reasons -
a Postgres `UndefinedColumn`, a `TypeError` on an unexpected constructor keyword, or
a plain assertion against text still present in `app/config.py` - never a typo in
this file.

**A large ripple this slice creates, named so the coder does not miss it**: making
these two flags row-driven breaks every existing test that monkeypatches
`settings.chatbot_business_lane_enabled` / `chatbot_ordering_enabled` directly -
`test_engine_failure_paths.py`, `test_s3_switch_and_complete_by_body.py`,
`test_s6_s7_integration.py` (the AC-715 eight-cell exit matrix), `test_s6a_gate_
dry_run_and_seams.py`, `test_s6c_answer_lane.py`, `test_s6c_engine_paths.py`,
`test_s7_dispatch_edges.py`, `test_s7_ordering_and_offload.py`,
`test_s7_poller_batch_order.py`. None of those files are touched here; they are the
coder's follow-up, not this tester's red-test scope.

Fixture reuse: `session_factory` / `system_settings_row` (`tests/chatbot/
conftest.py`), `_set_completed_lanes` / `_wire_business_lane`
(`tests/chatbot/test_s6_s7_integration.py`), `seeded` / `_envelope` /
`_parser_output` / `stub_parser` / `stub_access` (`tests/chatbot/test_engine.py`),
`client` / `api_key` (`tests/chatbot/test_chat_turn_endpoint.py`). Postgres only.

Run: pytest tests/chatbot/test_s8_switches_in_settings.py -v
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from tests._pg_fixture import TEST_PREFIX, blank_session
from tests.chatbot.test_chat_turn_endpoint import api_key, client  # noqa: F401 - fixtures used by name
from tests.chatbot.test_engine import (  # noqa: F401 - fixtures used by name
    CONTACT_ID,
    _envelope,
    _parser_output,
    seeded,
    stub_access,
    stub_parser,
)
from tests.chatbot.test_s6_s7_integration import _set_completed_lanes, _wire_business_lane


# --------------------------------------------------------------------------- #
# 1. `system_settings` gains the two columns (model + migration)
# --------------------------------------------------------------------------- #


def test_system_setting_model_accepts_the_two_new_columns():
    from app.models.user import SystemSetting

    row = SystemSetting(
        id=str(uuid.uuid4()),
        chatbot_business_lane_enabled=True,
        chatbot_ordering_enabled=True,
    )
    assert row.chatbot_business_lane_enabled is True
    assert row.chatbot_ordering_enabled is True


def test_the_columns_exist_on_postgres_default_false_and_persist():
    with blank_session() as db:
        from app.models.user import SystemSetting

        row = SystemSetting(id=str(uuid.uuid4()), name=f"{TEST_PREFIX} Co")
        db.add(row)
        db.commit()
        db.refresh(row)

        assert row.chatbot_business_lane_enabled is False
        assert row.chatbot_ordering_enabled is False

        db.execute(
            text(
                "UPDATE system_settings SET chatbot_business_lane_enabled = true, "
                "chatbot_ordering_enabled = true WHERE id = :id"
            ),
            {"id": row.id},
        )
        db.commit()
        db.refresh(row)

        assert row.chatbot_business_lane_enabled is True
        assert row.chatbot_ordering_enabled is True


# --------------------------------------------------------------------------- #
# 2. `engine._business_lane_enabled` reads `system_settings`, per turn, never
#    `app.config.settings` (AC-810's "read by the engine per turn")
# --------------------------------------------------------------------------- #


def _set_business_lane_enabled(session_factory, row_id: str, value: bool) -> None:
    db = session_factory()
    db.execute(
        text("UPDATE system_settings SET chatbot_business_lane_enabled = :v WHERE id = :id"),
        {"v": value, "id": row_id},
    )
    db.commit()


class TestBusinessLaneEnabledReadsTheRowNotConfig:
    """Never monkeypatches `app.config.settings` anywhere in this class - the row is
    the only lever pulled, which is the opposite of every cell in
    `test_s6_s7_integration.py::TestBusinessQueryExitMatrixAc715` today."""

    def test_business_lane_on_via_the_row_completes_the_turn(
        self,
        session_factory,
        seeded,
        stub_parser,
        stub_access,
        system_settings_row,
        monkeypatch,
    ) -> None:
        from app.services.chatbot import engine as engine_mod

        _set_completed_lanes(session_factory, system_settings_row, ["business_query"])
        _set_business_lane_enabled(session_factory, system_settings_row.id, True)
        _wire_business_lane(engine_mod, monkeypatch)
        stub_parser(
            _parser_output(domain_hint="forms", entities=[], user_goal="checking a form")
        )
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.status == "done", result.error
        assert result.delegate is None

    def test_business_lane_off_via_the_row_still_delegates(
        self,
        session_factory,
        seeded,
        stub_parser,
        stub_access,
        system_settings_row,
        monkeypatch,
    ) -> None:
        from app.services.chatbot import engine as engine_mod

        _set_completed_lanes(session_factory, system_settings_row, ["business_query"])
        _set_business_lane_enabled(session_factory, system_settings_row.id, False)
        stub_parser(
            _parser_output(domain_hint="forms", entities=[], user_goal="checking a form")
        )
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.status == "delegated", result.error
        assert result.delegate == "business_query"


# --------------------------------------------------------------------------- #
# 3. `app/api/v1/external/chat.py::_s7_mode` reads the row, not `app.config`, for
#    the `/complete` 410 (AC-810's "the screen shows the S7-mode consequence")
# --------------------------------------------------------------------------- #


class TestCompleteS7GateReadsTheRow:
    """Mirrors `test_s7_dispatch_edges.py::TestCompleteGoneInS7ModeFullApp`, but the
    switch is the ROW, never `monkeypatch.setattr(settings, "chatbot_ordering_
    enabled", ...)`."""

    def test_ordering_on_via_the_row_answers_410(self, client, api_key, session_factory) -> None:
        from app.models.user import SystemSetting

        db = session_factory()
        row = SystemSetting()
        db.add(row)
        db.commit()
        db.execute(
            text("UPDATE system_settings SET chatbot_ordering_enabled = true WHERE id = :id"),
            {"id": row.id},
        )
        db.commit()

        turn_id = str(uuid.uuid4())
        resp = client.post(
            f"/api/v1/external/chat/turn/{turn_id}/complete",
            json={"item": {"branch_kind": "low_signal"}},
            headers={"X-API-Key": api_key},
        )

        assert resp.status_code == 410, resp.text
        assert resp.json().get("code") == "CHATBOT_S7_MODE_OWNS_THE_TAIL"

    def test_ordering_off_via_the_row_answers_200_not_410(
        self, client, api_key, session_factory, monkeypatch
    ) -> None:
        from app.models.user import SystemSetting

        db = session_factory()
        db.add(SystemSetting())  # chatbot_ordering_enabled defaults False once it exists
        db.commit()

        canned = {
            "turn_id": str(uuid.uuid4()),
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

        resp = client.post(
            f"/api/v1/external/chat/turn/{canned['turn_id']}/complete",
            json={"item": {"branch_kind": "business_query"}},
            headers={"X-API-Key": api_key},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["reply"]["text"] == "Here is what I found."


# --------------------------------------------------------------------------- #
# 4. Guardrail: the two flags leave `app.config` / `.env.example`;
#    `chatbot_turn_on_worker` stays (AC-810's own carve-out)
# --------------------------------------------------------------------------- #


def test_business_lane_and_ordering_flags_are_gone_from_config_and_env_example():
    from pathlib import Path

    backend_root = Path(__file__).resolve().parents[2]
    config_source = (backend_root / "app" / "config.py").read_text(encoding="utf-8")

    assert "chatbot_business_lane_enabled" not in config_source, (
        "CHATBOT_BUSINESS_LANE_ENABLED must be deleted from app/config.py - it is now "
        "system_settings.chatbot_business_lane_enabled (AC-810)"
    )
    assert "chatbot_ordering_enabled" not in config_source, (
        "CHATBOT_ORDERING_ENABLED must be deleted from app/config.py - it is now "
        "system_settings.chatbot_ordering_enabled (AC-810)"
    )
    assert "chatbot_turn_on_worker" in config_source, (
        "CHATBOT_TURN_ON_WORKER stays a deployment property, not a settings column "
        "(AC-810's own carve-out) - it must not be collateral damage of this slice"
    )

    for candidate in (
        backend_root / ".env.example",
        backend_root.parent / "sorento_crm_backend" / ".env.example",
    ):
        if candidate.is_file():
            lowered = candidate.read_text(encoding="utf-8").lower()
            assert "chatbot_business_lane_enabled" not in lowered
            assert "chatbot_ordering_enabled" not in lowered


# --------------------------------------------------------------------------- #
# 5. PUT /settings/general accepts both booleans; GET round-trips them (AC-810)
# --------------------------------------------------------------------------- #


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

    allow: set[str] = {"user_management.settings.view", "user_management.settings.edit"}

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: {
        "id": str(uuid.uuid4()),
        "email": "chatbot-switches-caller@zzt.test",
    }
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in allow,
    )
    client_ = TestClient(app)
    try:
        yield client_
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def test_put_general_roundtrips_both_switches(api, db):
    from app.models.user import SystemSetting

    db.add(SystemSetting(id=str(uuid.uuid4()), name=f"{TEST_PREFIX} Co"))
    db.commit()

    resp = api.put(
        "/api/v1/user-management/settings/general",
        json={"chatbot_business_lane_enabled": True, "chatbot_ordering_enabled": True},
    )
    assert resp.status_code == 200, resp.text

    resp = api.get("/api/v1/user-management/settings/")
    assert resp.status_code == 200, resp.text
    body = resp.json()["settings"]
    assert body["chatbot_business_lane_enabled"] is True
    assert body["chatbot_ordering_enabled"] is True
