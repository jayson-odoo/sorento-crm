"""The in-app chatbot console (Slice D final, chatbot growth r1): `POST
/api/v1/system/chatbot/console/turn` and `GET /api/v1/system/chatbot/console/prompt-versions`.

Auth mirrors `test_turns_admin_api.py`: `require_permission` is monkeypatched at
`UserPermissionService.check_user_has_permission` rather than issuing a real API key,
because both console routes sit on the SAME `system.chat_history.view` slug the trace
screen already uses.

The engine seams are the same ones `test_chat_turn_endpoint.py` patches - the parser and
`check_access` - plus ONE more this module owns: `console_service.SessionLocal`, the
service's own session factory (mirrors `chat.py`'s `SessionLocal`, patched for the same
reason: `is_test` suppresses writes, not which database a session opens).
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.main  # noqa: F401  isort:skip - registers every model before any query
from app.main import app
from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot import console_service
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import parser as parser_mod
from app.services.user_service import UserPermissionService

from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output

VIEW = "system.chat_history.view"
CONSOLE_TURN_URL = "/api/v1/system/chatbot/console/turn"
PROMPT_VERSIONS_URL = "/api/v1/system/chatbot/console/prompt-versions"

_GRANTS: set[str] = set()
_ACTOR: dict = {"id": None, "name": "ZZT Console Tester"}


@pytest.fixture(autouse=True)
def _permissions(monkeypatch):
    _GRANTS.clear()
    _GRANTS.add(VIEW)
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in _GRANTS,
    )
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    yield
    _GRANTS.clear()


@pytest.fixture()
def client(session_factory):
    def _override_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: dict(_ACTOR)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(_ACTOR)
    _ACTOR["id"] = str(uuid.uuid4())
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def stub_console_seams(monkeypatch, session_factory):
    """**Real-DB-write finding, same shape as `test_chat_turn_endpoint.py`'s own
    `stub_engine_seams`.** `console_service.py` hardcodes `SessionLocal` as the engine's
    session factory AND as the lane-switch flip/restore session; unpatched, a turn through
    this endpoint would write real rows to the shared dev database.
    """
    monkeypatch.setattr(console_service, "SessionLocal", session_factory)

    def fake_resolve_config(db, *, current_date, override_version_id=None):
        return parser_mod.ParserConfig(
            system_prompt="stub", prompt_version=1, provider="openai", model="gpt-test", api_key="sk-test",
        )

    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(
        engine_mod,
        "check_access",
        lambda db, *, agent_code, contact_id, space_id: {
            "allowed": True,
            "decision": "allow",
            "agent_name": "General Enquiries",
            "attributes": None,
            "all_attributes_allowed": None,
        },
    )
    monkeypatch.setattr(engine_mod, "default_space_id", lambda db: "364817")


@pytest.fixture()
def seeded_contact_with_a_prior_turn(session_factory):
    """A respond contact plus one prior LIVE turn carrying a stored envelope - the shape
    `console_service._borrow_envelope` reads. An unknown contact has no such row (AC-002's
    own reason for the script borrowing rather than inventing one applies here too)."""
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": CONTACT_ID, "phone": "+60000000009", "sv": json.dumps({"variables": {}})},
    )
    envelope = _envelope()
    row = ChatbotTurn(
        contact_respond_id=CONTACT_ID,
        message_id="ZZT-seed-msg",
        ingress="webhook",
        envelope=json.loads(envelope.model_dump_json()),
        is_test=False,
        status="done",
        stage="sent",
        branch_kind="business_query",
    )
    db.add(row)
    db.commit()
    return db


# The scenario `not_supported` reaches without any MCP call: an unsupported domain is a
# canned reply, so `console_service._lanes_on` forcing every branch into
# `chatbot_completed_lanes` never has to reach `services.mcp_probe`.
NOT_SUPPORTED_OUTPUT = _parser_output(
    message_type="business_query",
    intent_hint="check_product",
    domain_hint="goods_receive",
    escalation={"is_escalation_confirmation": False, "company_pick": None},
)
NOT_SUPPORTED_REPLY = (
    "Sorry, we don't support direct goods receive & SPO at the moment. "
    "You may ask about incoming stock for a specific product or container"
)


def _run_id() -> str:
    return f"ZZT-console-{uuid.uuid4().hex[:8]}"


class TestConsoleTurnZeroWrites:
    """D14 through this endpoint too: the console runs `is_test=True` turns and must
    touch nothing outside `chatbot.turns`, the same claim
    `TestDryRunEndpointZeroWrites` proves for `/external/chat/turn`."""

    def test_console_turn_touches_only_chatbot_turns(
        self, client, session_factory, seeded_contact_with_a_prior_turn, system_settings_row, stub_console_seams, monkeypatch,
    ):
        monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: NOT_SUPPORTED_OUTPUT)

        before_session_vars = session_factory().execute(
            text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :c"),
            {"c": CONTACT_ID},
        ).scalar()
        before_turns = (
            session_factory()
            .query(ChatbotTurn)
            .filter(ChatbotTurn.contact_respond_id == CONTACT_ID)
            .count()
        )

        resp = client.post(
            CONSOLE_TURN_URL,
            json={
                "contact_respond_id": CONTACT_ID,
                "text": "can I submit a goods receive here",
                "run_id": _run_id(),
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["branch_kind"] == "not_supported"
        assert NOT_SUPPORTED_REPLY in body["reply_text"] or any(
            NOT_SUPPORTED_REPLY in m for m in body["send_messages"]
        )

        after_session_vars = session_factory().execute(
            text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :c"),
            {"c": CONTACT_ID},
        ).scalar()
        after_turns = (
            session_factory()
            .query(ChatbotTurn)
            .filter(ChatbotTurn.contact_respond_id == CONTACT_ID)
            .count()
        )
        assert after_session_vars == before_session_vars, "a console turn must not touch respond_contacts"
        # The seeded prior turn, plus exactly this one new row.
        assert after_turns == before_turns + 1
        row = session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == body["turn_id"]).first()
        assert row.is_test is True
        assert row.ingress == "console"


class TestConsoleTurnCarriesSessionAcrossTurns:
    """Turn 2 must see turn 1's state: the FE sends turn 1's `session_vars` back as turn
    2's request body, and that has to reach the parser as `previous_conversation_state`
    (the harness key `engine._inject_harness_session` honours), not the contact's stored
    (empty) session.

    D8/AC-1023 retired the OLD mechanism this class used to pin - turn 1's REPLY TEXT
    riding into turn 2's parser prompt (`variables["response"]`, one of the 34 legacy
    keys, never persisted at all now; the prompt instead receives `focus_hints` /
    `open_question_hint`, L1-S2, out of scope here). What survives, and is what this
    class is actually named for, is the round trip into `engine._inject_harness_session`
    itself: turn 2's `session_vars` in the request body must land on the envelope as
    `previous_conversation_state` and become `session_vars["variables"]` for THAT turn,
    verbatim, not the contact's stored (empty) session. A `not_supported` canned reply is
    deliberately used (see the module comment on `NOT_SUPPORTED_OUTPUT`) so this stays
    independent of `resolve_gate` / focus population, which a canned, no-MCP branch never
    reaches.
    """

    def test_turn_two_carries_turn_ones_session_vars_into_the_harness_injection(
        self, client, session_factory, seeded_contact_with_a_prior_turn, system_settings_row, stub_console_seams, monkeypatch,
    ):
        injected: list[dict] = []
        real_inject = engine_mod._inject_harness_session

        def spy_inject(session_block, envelope):
            result = real_inject(session_block, envelope)
            injected.append(result)
            return result

        monkeypatch.setattr(engine_mod, "_inject_harness_session", spy_inject)
        monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: NOT_SUPPORTED_OUTPUT)

        run_id = _run_id()
        first = client.post(
            CONSOLE_TURN_URL,
            json={"contact_respond_id": CONTACT_ID, "text": "goods receive?", "run_id": run_id},
        )
        assert first.status_code == 200, first.text
        turn_one_session_vars = first.json()["session_vars"]
        assert turn_one_session_vars is not None, "turn 1 must carry a session_vars patch"

        second = client.post(
            CONSOLE_TURN_URL,
            json={
                "contact_respond_id": CONTACT_ID,
                "text": "still no?",
                "run_id": run_id,
                "session_vars": turn_one_session_vars,
            },
        )
        assert second.status_code == 200, second.text

        assert len(injected) == 2
        # Turn 2's injected session block carries turn 1's OWN five-key output verbatim -
        # the harness carried it forward, never the contact's stored (empty) session.
        assert injected[1]["session_vars"]["variables"] == turn_one_session_vars, (
            "turn 2's harness-injected session_vars is not turn 1's own response - the "
            f"round trip did not reach the engine. injected was: {injected[1]!r}"
        )


class TestConsoleTurnUnknownContact:
    def test_unknown_contact_is_a_404(self, client, stub_console_seams, monkeypatch):
        monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: NOT_SUPPORTED_OUTPUT)
        resp = client.post(
            CONSOLE_TURN_URL,
            json={"contact_respond_id": "ZZT-no-such-contact", "text": "hi", "run_id": _run_id()},
        )
        assert resp.status_code == 404, resp.text
        # `app_exception_handler` (app/main.py) returns `AppException.detail` AS the body,
        # not wrapped under a `detail` key.
        assert resp.json()["code"] == "CHATBOT_CONSOLE_NO_ENVELOPE"


class TestConsoleTurnPermissionGate:
    def test_without_the_view_permission_it_is_a_403(self, client):
        _GRANTS.discard(VIEW)
        resp = client.post(
            CONSOLE_TURN_URL,
            json={"contact_respond_id": CONTACT_ID, "text": "hi", "run_id": _run_id()},
        )
        assert resp.status_code == 403, resp.text

    def test_prompt_versions_also_needs_the_view_permission(self, client):
        _GRANTS.discard(VIEW)
        resp = client.get(PROMPT_VERSIONS_URL)
        assert resp.status_code == 403, resp.text


class TestConsolePromptVersions:
    def test_lists_newest_first_with_chars_and_label(self, client, session_factory):
        db = session_factory()
        v1 = AIPromptVersion(
            name=console_service.PARSER_PROMPT_KEY, version=1, template="a" * 10, variables=[],
        )
        v2 = AIPromptVersion(
            name=console_service.PARSER_PROMPT_KEY, version=2, template="b" * 25, variables=[],
        )
        db.add_all([v1, v2])
        db.flush()
        db.add(AIPromptLabel(name=console_service.PARSER_PROMPT_KEY, label="production", version_id=v1.id))
        db.commit()

        resp = client.get(PROMPT_VERSIONS_URL)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert [row["version"] for row in body] == [2, 1]
        by_version = {row["version"]: row for row in body}
        assert by_version[1]["label"] == "production"
        assert by_version[2]["label"] is None
        assert by_version[1]["chars"] == 10
        assert by_version[2]["chars"] == 25


class TestConsolePromptVersionBase:
    """Item 6 (8 Sep 2026): the owner's turns silently ran the compact base twice because
    the console's null choice meant "the production label", which locally sits on the
    compact lineage. Every version now says which base it is, so the FE can default to
    the newest FULL one."""

    def test_base_is_read_off_the_first_200_chars(self):
        from app.services.chatbot_parser_prompt import (
            SEMANTIC_PARSER_PROMPT,
            SEMANTIC_PARSER_PROMPT_SLIM,
        )

        assert console_service.prompt_base(SEMANTIC_PARSER_PROMPT) == "full"
        assert console_service.prompt_base(SEMANTIC_PARSER_PROMPT_SLIM) == "compact"
        # an edit further down the body keeps its lineage
        assert console_service.prompt_base(SEMANTIC_PARSER_PROMPT + "\nADDED") == "full"
        assert console_service.prompt_base(SEMANTIC_PARSER_PROMPT_SLIM[:5000] + "x") == "compact"
        assert console_service.prompt_base("You are something else entirely.") == "other"
        assert console_service.prompt_base("") == "other"
        assert console_service.prompt_base(None) == "other"

    def test_the_list_carries_base_per_version(self, client, session_factory):
        from app.services.chatbot_parser_prompt import (
            SEMANTIC_PARSER_PROMPT,
            SEMANTIC_PARSER_PROMPT_SLIM,
        )

        db = session_factory()
        db.add_all(
            [
                AIPromptVersion(name=console_service.PARSER_PROMPT_KEY, version=1, template=SEMANTIC_PARSER_PROMPT, variables=[]),
                AIPromptVersion(name=console_service.PARSER_PROMPT_KEY, version=2, template=SEMANTIC_PARSER_PROMPT_SLIM, variables=[]),
                AIPromptVersion(name=console_service.PARSER_PROMPT_KEY, version=3, template="something else", variables=[]),
            ]
        )
        db.commit()
        resp = client.get(PROMPT_VERSIONS_URL)
        assert resp.status_code == 200, resp.text
        assert {row["version"]: row["base"] for row in resp.json()} == {1: "full", 2: "compact", 3: "other"}


class TestConsoleTurnCarriesThePromptVersion:
    def test_prompt_version_is_read_off_the_understood_stage(self):
        trace = [
            {"stage": "received", "status": "ok", "facts": {}},
            {"stage": "understood", "status": "ok", "facts": {"prompt_version": 18, "model": None}},
            {"kind": "tool", "payload": {"name": "x"}},
        ]
        assert console_service.trace_prompt_version(trace) == 18
        assert console_service.trace_prompt_version([{"stage": "received", "facts": {}}]) is None
        assert console_service.trace_prompt_version([]) is None
        assert console_service.trace_prompt_version(None) is None

    def test_the_turn_response_declares_prompt_version(self, client, stub_console_seams):
        from app.schemas.chatbot_turn import ConsoleTurnResponse

        assert "prompt_version" in ConsoleTurnResponse.model_fields
        assert ConsoleTurnResponse(trace_summary=console_service._empty_trace_summary()).prompt_version is None
