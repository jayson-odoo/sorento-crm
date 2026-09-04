"""`complete_turn` and `POST /chat/turn/{id}/complete` (AC-201, AC-203, AC-206, D14).

Four properties nothing else can prove:

* the tail WRITES the session, once, through `overwrite_for_contact`, with an
  `integration_log` beside it - D2's "one writer" is the whole point of S2, and after
  this ships n8n's `save-session-vars` is deleted;
* a DRY RUN writes nothing at all outside `chatbot.turns` (D14) and hands the would-be
  patch back instead, so a console or a clone turn is safe by construction;
* the turn CLOSES: status `done`, stage `remembered`, and the head's trace continues into
  `replied` / `remembered` rather than starting a second timeline;
* a second `/complete` for the same turn replays the first answer instead of re-writing
  the session, which is D15's shape one stage further on.

**`SessionLocal` must be patched by any test that drives the endpoint.** The route hands
the engine the module-level `SessionLocal`, the real `DATABASE_URL` engine, and `is_test`
suppresses business writes but not which database the turn row lands in - an earlier
version of the sibling endpoint test left a real half-written row in the shared dev
database. See `test_chat_turn_endpoint.py` for the full finding.
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import text

import app.main  # noqa: F401  isort:skip - registers every model before any query
from app.main import app
from app.dependencies import get_db
from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.contracts import Envelope
from app.services.chatbot.head import parser as parser_mod
from tests.chatbot.test_chat_turn_endpoint import api_key, client  # noqa: F401 - fixtures
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output

_COMPLETE_URL = "/api/v1/external/chat/turn/{turn_id}/complete"

PRIOR_SESSION = {"variables": {"domain_hint": "order", "response": "an earlier reply"}}


@pytest.fixture()
def seeded(session_factory):
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": CONTACT_ID, "phone": "+60000000009", "sv": json.dumps(PRIOR_SESSION)},
    )
    db.commit()
    return db


@pytest.fixture()
def stub_parser(monkeypatch):
    def fake_resolve_config(db, *, current_date):
        return parser_mod.ParserConfig(
            system_prompt="stub",
            prompt_version=1,
            provider="openai",
            model="gpt-test",
            api_key="sk-test",
        )

    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: _parser_output())
    monkeypatch.setattr(
        engine_mod,
        "check_access",
        lambda db, **kw: {"allowed": True, "decision": "allow", "agent_name": "General"},
    )
    monkeypatch.setattr(engine_mod, "default_space_id", lambda db: None)


def _head(session_factory, **envelope_overrides):
    envelope = _envelope(**envelope_overrides)
    return engine_mod.run_turn(envelope, session_factory=session_factory)


def _fragments(**over: Any) -> dict[str, Any]:
    """The `sub-output` trigger contract, minimal: an item plus a lane answer."""
    body = {
        "item": {"branch_kind": "not_supported", "allowed": True},
        "result": None,
        "resolved": None,
        "gate": None,
        "offer_hold": None,
        "suggest_offer": None,
        "not_found": None,
        "incoming_picker": None,
        "access_choice": None,
        "crossdomain_render": None,
        "answer": None,
        "clarify": None,
    }
    body.update(over)
    return body


def _session_of(session_factory, contact_id: str = CONTACT_ID) -> dict:
    db = session_factory()
    row = db.execute(
        text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :cid"),
        {"cid": contact_id},
    ).first()
    raw = row.session_vars if row is not None else {}
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


def _integration_logs(session_factory, business_table: str) -> int:
    db = session_factory()
    return db.execute(
        text("SELECT count(*) FROM integration_log WHERE business_table = :bt"),
        {"bt": business_table},
    ).scalar_one()


class TestTheTailWritesTheSession:
    def test_a_live_turn_writes_the_patch_and_logs_it(self, seeded, stub_parser, session_factory):
        """AC-206: one `overwrite_for_contact`, one `integration_log` naming the column."""
        head = _head(session_factory, is_test=False)
        done = engine_mod.complete_turn(head.turn_id, _fragments(), session_factory=session_factory)

        stored = _session_of(session_factory)
        assert stored["variables"]["domain_hint"] == "master_products", "the tail overwrote it"
        # The stored value is the WHOLE patch, not just `variables`: `save-session-vars`
        # PUT `JSON.stringify($json.reply.session_patch)`, so a variables-only write would
        # change what every existing reader of that column sees.
        assert set(stored) >= {"variables", "user_response"}
        assert stored["user_response"] == done.reply["text"]
        assert _integration_logs(session_factory, "respond_contacts.session_vars") == 1

    def test_the_reply_carries_the_four_fields_the_sender_reads(self, seeded, stub_parser, session_factory):
        """AC-201: `sub-sendmsg` and `send-attachments` each become ONE read."""
        head = _head(session_factory, is_test=False)
        answer = {"outcome_fragment": {"central-exchange": [{"url": "s3://x"}]}}
        done = engine_mod.complete_turn(
            head.turn_id, _fragments(answer=answer), session_factory=session_factory
        )
        assert set(done.reply) == {"text", "quick_replies", "result_set", "attachments_src"}
        assert done.reply["attachments_src"] == [{"url": "s3://x"}]
        assert done.reply["result_set"] == _session_of(session_factory)["variables"]["last_result_set"]

    def test_the_turn_closes_done_with_the_head_s_trace_continued(self, seeded, stub_parser, session_factory):
        head = _head(session_factory, is_test=False)
        before = len(_turn_row(session_factory, head.turn_id).trace)
        engine_mod.complete_turn(head.turn_id, _fragments(), session_factory=session_factory)
        row = _turn_row(session_factory, head.turn_id)
        assert row.status == "done"
        assert row.stage == "remembered"
        stages = [record["stage"] for record in row.trace]
        assert len(stages) == before + 2, "the tail APPENDS, it does not start a second timeline"
        assert stages[-2:] == ["replied", "remembered"]
        for record in row.trace[-2:]:
            assert record["summary"] and record["why"]
            assert "{" not in record["summary"], "the trace renders words, not JSON (D11)"


def _turn_row(session_factory, turn_id: str) -> ChatbotTurn:
    db = session_factory()
    return db.query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).one()


class TestDryRunWritesNothing:
    """D14: a test envelope does ZERO writes outside `chatbot.turns`, and the decision is
    made on the ENVELOPE at `/turn`, so a caller cannot turn a console turn into a live
    write by posting `/complete` to a different URL."""

    def test_the_session_is_untouched_and_the_patch_comes_back_instead(
        self, seeded, stub_parser, session_factory
    ):
        head = _head(session_factory, is_test=True)
        done = engine_mod.complete_turn(head.turn_id, _fragments(), session_factory=session_factory)

        assert _session_of(session_factory) == PRIOR_SESSION, "a dry run wrote the session"
        assert done.session_patch is not None
        assert done.session_patch["variables"]["domain_hint"] == "master_products"
        assert _integration_logs(session_factory, "respond_contacts.session_vars") == 0

    def test_a_live_turn_does_not_return_the_patch(self, seeded, stub_parser, session_factory):
        head = _head(session_factory, is_test=False)
        done = engine_mod.complete_turn(head.turn_id, _fragments(), session_factory=session_factory)
        assert done.session_patch is None, "the caller reads the session, it is not echoed"


class TestGuards:
    def test_an_unknown_turn_id_is_a_lookup_error_not_a_crash(self, seeded, session_factory):
        with pytest.raises(LookupError):
            engine_mod.complete_turn(
                "11111111-1111-1111-1111-111111111111",
                _fragments(),
                session_factory=session_factory,
            )

    def test_completing_twice_replays_the_first_answer_and_writes_once(
        self, seeded, stub_parser, session_factory
    ):
        head = _head(session_factory, is_test=False)
        first = engine_mod.complete_turn(head.turn_id, _fragments(), session_factory=session_factory)
        second = engine_mod.complete_turn(head.turn_id, _fragments(), session_factory=session_factory)
        assert second.reply == first.reply
        assert _integration_logs(session_factory, "respond_contacts.session_vars") == 1

    def test_a_key_outside_the_allowlist_raises_before_the_write(
        self, seeded, stub_parser, session_factory, monkeypatch
    ):
        """AC-203: the wall is on the WRITE path, so it has to stop the write."""
        from app.services.chatbot.tail import compile_state as compile_mod

        real = compile_mod.compile_current_state

        def poisoned(item, ctx, **kwargs):
            compiled = real(item, ctx, **kwargs)
            compiled.item["reply"]["session_patch"]["variables"]["dym_probe_entities"] = ["harness"]
            return compiled

        monkeypatch.setattr(
            "app.services.chatbot.tail.compile_state.compile_current_state", poisoned
        )
        head = _head(session_factory, is_test=False)
        with pytest.raises(Exception) as raised:
            engine_mod.complete_turn(head.turn_id, _fragments(), session_factory=session_factory)
        assert "dym_probe_entities" in str(raised.value)
        assert _session_of(session_factory) == PRIOR_SESSION, "it wrote before validating"


class TestTheEndpoint:
    """The route itself: auth, the module guard and `response_model` survival."""

    def _post(self, client, api_key, turn_id, body):
        return client.post(
            _COMPLETE_URL.format(turn_id=turn_id), json=body, headers={"X-API-Key": api_key}
        )

    def test_without_the_slug_the_route_is_refused(self, client, session_factory):
        resp = client.post(
            _COMPLETE_URL.format(turn_id="11111111-1111-1111-1111-111111111111"),
            json=_fragments(),
        )
        assert resp.status_code in (401, 403), resp.text

    def test_an_unknown_turn_is_a_404_naming_it(self, client, api_key, session_factory, monkeypatch):
        monkeypatch.setattr("app.api.v1.external.chat.SessionLocal", session_factory)
        resp = self._post(client, api_key, "11111111-1111-1111-1111-111111111111", _fragments())
        assert resp.status_code == 404, resp.text
        assert "11111111-1111-1111-1111-111111111111" in resp.json()["detail"]

    def test_the_body_rejects_an_undeclared_field(self, client, api_key, session_factory, monkeypatch):
        """`extra = "forbid"` on the request: a caller sending a field the tail does not
        read is a caller whose expectations have drifted, and a silent drop hides it."""
        monkeypatch.setattr("app.api.v1.external.chat.SessionLocal", session_factory)
        resp = self._post(
            client, api_key, "11111111-1111-1111-1111-111111111111", {**_fragments(), "nope": {}}
        )
        assert resp.status_code == 422, resp.text

    def test_every_response_field_survives_serialisation(
        self, client, api_key, session_factory, monkeypatch
    ):
        """`response_model` silently DROPS an undeclared field, so each one is asserted."""
        monkeypatch.setattr("app.api.v1.external.chat.SessionLocal", session_factory)
        canned = {
            "turn_id": "22222222-2222-2222-2222-222222222222",
            "reply": {"text": "hi", "quick_replies": "a,b", "result_set": [], "attachments_src": None},
            "actions": [{"kind": "update_contact_fields", "fields": {}, "dry_run": True}],
            "session_patch": {"variables": {"pending": None}},
        }

        class _Fake:
            def as_dict(self):
                return canned

        monkeypatch.setattr("app.api.v1.external.chat.complete_turn", lambda *a, **k: _Fake())
        resp = self._post(client, api_key, canned["turn_id"], _fragments())
        assert resp.status_code == 200, resp.text
        body = resp.json()
        for key in ("turn_id", "reply", "actions", "session_patch"):
            assert key in body, f"{key!r} missing from the response body: {body}"
        assert body["reply"]["attachments_src"] is None
        assert body["reply"]["quick_replies"] == "a,b"
        assert body["session_patch"] == canned["session_patch"]
