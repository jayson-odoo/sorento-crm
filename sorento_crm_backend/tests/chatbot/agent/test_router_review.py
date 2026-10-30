"""AGENTIC-P2-ROUTE review fix round: red tests for the seven review findings (BE side).

Items are numbered as in the coordinator's contract: 1 text length, 2 transport errors and key
hygiene, 3 confidence validation, 4 reply cut, 5 missing operator, 6 media route record,
7 key clear, 8 global cap in the contact response.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.models.chatbot_turn import ChatbotTurn
from tests._pg_fixture import blank_session
from tests.chatbot.agent._seed import seed_agent_contact
from tests.chatbot.agent.test_router import (  # noqa: F401 - helpers + fixtures
    JEV_KEY,
    _fresh_prompt_cache,
    arm,
    jev,
    jev_answer,
    route,
    seed_agent_turn,
)
from tests.chatbot.agent.test_router_console import (  # noqa: F401 - fixtures
    AGENT_REPLY,
    agent_calls,
    bot_parser,
    eligible,
    jev as console_jev,
    _post,
)
from tests.chatbot.agent.test_router_settings_key import (  # noqa: F401 - fixtures + helpers
    BASE,
    KEY,
    _GRANTS,
    _payload,
    _permissions,
    _seed_contact,
    _settings_row,
    client as settings_client,
    db as settings_db,
)
from tests.chatbot.test_console_turn_endpoint import (  # noqa: F401 - fixtures
    _ACTOR,
    _GRANTS as _CONSOLE_GRANTS,
    _permissions as _console_permissions,
    client,
    seeded_contact_with_a_prior_turn,
    stub_console_seams,
)


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


# ------------------------------------------------------------------ 1: text length


@pytest.mark.parametrize("text_", ["", "   ", "\n\t ", "x" * 4001, " " + "x" * 4001])
def test_1_text_of_zero_or_over_4000_chars_goes_to_chat_without_a_jev_call(db, jev, text_):
    contact = seed_agent_contact(db)
    arm(db)
    decision = route(db, contact["respond_id"], text_)
    assert (decision.side, decision.reason) == ("chat", "text_length")
    assert jev.calls == []


@pytest.mark.parametrize("text_", ["x", "x" * 4000])
def test_1_the_length_edges_still_reach_jev(db, jev, text_):
    contact = seed_agent_contact(db)
    arm(db)
    assert route(db, contact["respond_id"], text_).reason == "classified"
    assert len(jev.calls) == 1


# ------------------------------------------------------------------ 2: transport errors


def _chain(err):
    seen, cur = [], err
    while cur is not None and cur not in seen:
        seen.append(cur)
        cur = cur.__cause__ or cur.__context__
    return seen


def _no_network(monkeypatch, exc):
    def boom(*a, **k):
        raise exc

    monkeypatch.setattr(httpx, "post", boom)


def test_2_a_generic_transport_failure_is_a_transport_jev_error(monkeypatch):
    from app.services.chatbot import jev_client

    _no_network(monkeypatch, RuntimeError(f"transport blew up with {JEV_KEY}"))
    with pytest.raises(jev_client.JevError) as exc:
        jev_client.classify(JEV_KEY, model="jev-1.14.0", instructions="i", criteria={"chat": "c"}, state={})
    assert exc.value.kind == "transport"
    for err in _chain(exc.value):
        assert JEV_KEY not in str(err) and JEV_KEY not in repr(err)
    assert exc.value.__cause__ is None and exc.value.__context__ is None


def test_2_a_non_ascii_key_is_a_transport_error_that_never_shows_the_key(monkeypatch):
    from app.services.chatbot import jev_client

    key = "jev-kéy-secret-5555"
    monkeypatch.setattr(
        httpx.HTTPTransport, "handle_request", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no network"))
    )
    with pytest.raises(jev_client.JevError) as exc:
        jev_client.classify(key, model="jev-1.14.0", instructions="i", criteria={"chat": "c"}, state={})
    assert exc.value.kind == "transport"
    for err in _chain(exc.value):
        assert key not in str(err) and key not in repr(err)
    assert exc.value.__cause__ is None and exc.value.__context__ is None


def test_2_decide_route_answers_chat_router_failed_transport(db, jev):
    from app.services.chatbot.jev_client import JevError

    contact = seed_agent_contact(db)
    arm(db)
    jev.error = JevError("transport")
    decision = route(db, contact["respond_id"])
    assert (decision.side, decision.reason) == ("chat", "router_failed:transport")


# ------------------------------------------------------------------ 3: confidence validation


class _Resp:
    status_code = 200

    def __init__(self, confidence):
        self._c = confidence

    def json(self):
        return {
            "answers": {"route": {"choice": "agent", "confidence": self._c, "probabilities": {}}},
            "usage": {"input_tokens": 10, "output_tokens": 0},
            "model": "jev-1.14.0",
        }


@pytest.mark.parametrize(
    "confidence", [float("nan"), float("inf"), float("-inf"), -0.1, 1.5, "abc", None, [0.9], {"v": 1}]
)
def test_3_an_invalid_confidence_is_malformed(monkeypatch, confidence):
    from app.services.chatbot import jev_client

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp(confidence))
    with pytest.raises(jev_client.JevError) as exc:
        jev_client.classify(JEV_KEY, model="jev-1.14.0", instructions="i", criteria={"chat": "c"}, state={})
    assert exc.value.kind == "malformed"


@pytest.mark.parametrize("confidence", [0, 0.0, 0.5, 1, 1.0])
def test_3_a_confidence_inside_zero_to_one_is_accepted(monkeypatch, confidence):
    from app.services.chatbot import jev_client

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp(confidence))
    answer = jev_client.classify(JEV_KEY, model="jev-1.14.0", instructions="i", criteria={"chat": "c"}, state={})
    assert answer.confidence == pytest.approx(float(confidence))


# ------------------------------------------------------------------ 4: reply cut


def test_4_agent_replies_are_cut_to_300_chars_too(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    base = datetime.now(timezone.utc) - timedelta(minutes=10)
    seed_agent_turn(db, contact["respond_id"], created_at=base, ingress="agent", text_="q", reply="a" * 900)
    seed_agent_turn(
        db, contact["respond_id"], created_at=base + timedelta(minutes=1), ingress="console", text_="q2", reply="b" * 900
    )
    db.commit()
    route(db, contact["respond_id"], "next")
    recent = jev.calls[0]["state"]["recent_exchanges"]
    assert {r["answered_by"] for r in recent} == {"agent", "bot"}
    assert all(len(r["reply"]) <= 300 for r in recent)


# ------------------------------------------------------------------ 5: missing operator


@pytest.mark.parametrize("operator", [None, ""])
def test_5_no_operator_refuses_the_agent_side_and_never_runs_it(
    eligible, console_jev, agent_calls, stub_console_seams, bot_parser, session_factory, monkeypatch, operator,
):
    from app.services.chatbot import console_service
    from app.services.chatbot import engine as engine_mod

    engine_calls = []
    monkeypatch.setattr(console_service, "run_turn", lambda *a, **k: engine_calls.append(1))
    monkeypatch.setattr(engine_mod, "run_turn", lambda *a, **k: engine_calls.append(1))
    console_jev.answer = jev_answer("agent", 0.95)
    result = console_service.run_console_turn(
        session_factory(),
        contact_respond_id=eligible["respond_id"],
        text="why did Selangor sales drop",
        run_id=f"ZZT-{uuid.uuid4().hex[:8]}",
        operator_user_id=operator,
    )
    assert agent_calls.calls == []
    assert engine_calls == []
    assert result.route["side"] == "agent"
    assert result.reply_text and "could not answer" in result.reply_text.lower()


# ------------------------------------------------------------------ 6: media route record


def test_6_a_media_turn_carries_a_media_route_and_the_trace_stage(
    client, eligible, console_jev, agent_calls, monkeypatch, session_factory,
):
    from app.services.chatbot import console_service

    _GRANTS.add("system.chat_history.view")  # the other suite's autouse patch is active too
    _CONSOLE_GRANTS.add("system.chat_history.view")
    db = eligible["db"]
    turn = ChatbotTurn(
        id=str(uuid.uuid4()), contact_respond_id=eligible["respond_id"], ingress="console", is_test=True,
        status="done", envelope={"text": "look"}, response={"reply_text": "ok"}, trace=[],
    )
    db.add(turn)
    db.commit()

    def fake_media(db_, **kwargs):
        return console_service.ConsoleTurnResult(
            turn_id=turn.id, reply_text="ok", quick_replies=[], send_messages=[], trace_summary={},
            media_status="done",
        )

    monkeypatch.setattr(console_service, "_run_console_media_turn", fake_media)
    resp = _post(
        client, eligible, "look at this",
        media={"kind": "image", "filename": "a.png", "mime": "image/png", "content_base64": "aGk="},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["route"] == {"side": "chat", "reason": "media", "score": None, "model": None, "ms": None, "error": None}
    assert console_jev.calls == [] and agent_calls.calls == []
    db.expire_all()
    stages = [s for s in (db.get(ChatbotTurn, turn.id).trace or []) if s.get("stage") == "route"]
    assert stages and "media" in str(stages[0])


# ------------------------------------------------------------------ 7: key clear


def test_7_clear_true_removes_the_stored_key():
    from app.schemas.ai_assistant import AIAssistantConfigUpdate
    from app.services.ai_assistant_service import AIAssistantConfigService
    from app.services.llm_provider import resolve_typesafe_key

    with blank_session() as session:
        service = AIAssistantConfigService(session)
        service.update(_payload(typesafe_api_key=KEY), user_id=None)
        row = service.update(_payload(typesafe_api_key_clear=True), user_id=None)
        assert not service.to_response_dict(row)["typesafe_api_key_masked"]
        assert resolve_typesafe_key(row) == ""
        assert isinstance(row, object) and AIAssistantConfigUpdate.model_fields["typesafe_api_key_clear"]


@pytest.mark.parametrize("extra", [{"typesafe_api_key_clear": False}, {}, {"typesafe_api_key": "  "}])
def test_7_false_absent_or_blank_keeps_the_stored_key(extra):
    from app.services.ai_assistant_service import AIAssistantConfigService
    from app.services.llm_provider import resolve_typesafe_key

    with blank_session() as session:
        service = AIAssistantConfigService(session)
        service.update(_payload(typesafe_api_key=KEY), user_id=None)
        row = service.update(_payload(**extra), user_id=None)
        assert resolve_typesafe_key(row) == KEY
        assert service.to_response_dict(row)["typesafe_api_key_masked"] == "****1234"


# ------------------------------------------------------------------ 8: global cap in the contact response

GLOBAL = "chatbot_agent_daily_turns_global"


def test_8_get_carries_the_global_cap_default(db, settings_client):
    contact_id = _seed_contact(db)
    assert settings_client.get(f"{BASE}/{contact_id}").json()[GLOBAL] == 50


def test_8_get_and_put_carry_the_system_setting_value(db, settings_client):
    _settings_row(db, chatbot_agent_daily_turns=33)
    contact_id = _seed_contact(db)
    assert settings_client.get(f"{BASE}/{contact_id}").json()[GLOBAL] == 33
    resp = settings_client.put(f"{BASE}/{contact_id}/chatbot", json={"chatbot_agent_daily_turns": 4})
    assert resp.status_code == 200, resp.text
    assert resp.json()[GLOBAL] == 33
    assert resp.json()["chatbot_agent_daily_turns"] == 4


def test_8_the_global_value_is_read_only_on_put(db, settings_client):
    _settings_row(db, chatbot_agent_daily_turns=33)
    contact_id = _seed_contact(db)
    settings_client.put(f"{BASE}/{contact_id}/chatbot", json={GLOBAL: 5})
    assert settings_client.get(f"{BASE}/{contact_id}").json()[GLOBAL] == 33


# ------------------------------------------------------------------ diagnostics: JevError.detail, one log line, route error

import logging

FAKE_KEY = "jev-fake-secret-key-424242"


def _failing_post(monkeypatch, exc):
    def boom(*a, **k):
        raise exc

    monkeypatch.setattr(httpx, "post", boom)


def _classify(key=FAKE_KEY):
    from app.services.chatbot import jev_client

    return jev_client.classify(key, model="jev-1.14.0", instructions="i", criteria={"chat": "c"}, state={})


@pytest.mark.parametrize(
    "exc, kind, detail",
    [
        (RuntimeError(f"boom {FAKE_KEY}"), "transport", "RuntimeError"),
        (httpx.ConnectError(f"refused {FAKE_KEY}"), "transport", "ConnectError"),
        (httpx.LocalProtocolError(f"bad header {FAKE_KEY}"), "transport", "LocalProtocolError"),
        (httpx.ReadTimeout(f"slow {FAKE_KEY}"), "timeout", "ReadTimeout"),
        (httpx.ConnectTimeout(f"slow {FAKE_KEY}"), "timeout", "ConnectTimeout"),
    ],
)
def test_diag_detail_is_the_exception_class_name_only(monkeypatch, exc, kind, detail):
    from app.services.chatbot import jev_client

    _failing_post(monkeypatch, exc)
    with pytest.raises(jev_client.JevError) as err:
        _classify()
    assert err.value.kind == kind
    assert err.value.detail == detail
    for e in _chain(err.value):
        assert FAKE_KEY not in str(e) and FAKE_KEY not in repr(e)
    assert FAKE_KEY not in str(err.value.detail)
    assert err.value.__cause__ is None and err.value.__context__ is None


def test_diag_a_non_ascii_key_detail_is_unicodeencodeerror(monkeypatch):
    from app.services.chatbot import jev_client

    key = "jev-kéy-424242"
    monkeypatch.setattr(
        httpx.HTTPTransport, "handle_request", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no network"))
    )
    with pytest.raises(jev_client.JevError) as err:
        _classify(key)
    assert err.value.kind == "transport" and err.value.detail == "UnicodeEncodeError"


class _Status:
    def __init__(self, code):
        self.status_code = code

    def json(self):
        return {}


@pytest.mark.parametrize("code, kind", [(429, "rate_limited"), (500, "http_500"), (401, "http_401")])
def test_diag_http_errors_have_no_detail(monkeypatch, code, kind):
    from app.services.chatbot import jev_client

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Status(code))
    with pytest.raises(jev_client.JevError) as err:
        _classify()
    assert err.value.kind == kind and err.value.detail is None


def test_diag_malformed_has_no_detail(monkeypatch):
    from app.services.chatbot import jev_client

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp(float("nan")))
    with pytest.raises(jev_client.JevError) as err:
        _classify()
    assert err.value.kind == "malformed" and err.value.detail is None


@pytest.mark.parametrize(
    "exc, kind, name",
    [
        (httpx.ConnectError(f"refused {FAKE_KEY}"), "transport", "ConnectError"),
        (httpx.ReadTimeout(f"slow {FAKE_KEY}"), "timeout", "ReadTimeout"),
    ],
)
def test_diag_one_warning_with_kind_and_class_name_and_no_key_or_message(monkeypatch, caplog, exc, kind, name):
    from app.services.chatbot import jev_client

    _failing_post(monkeypatch, exc)
    with caplog.at_level(logging.DEBUG, logger="app.services.chatbot.jev_client"):
        with pytest.raises(jev_client.JevError):
            _classify()
    records = [r for r in caplog.records if r.name == "app.services.chatbot.jev_client"]
    assert len(records) == 1 and records[0].levelno == logging.WARNING
    text_ = records[0].getMessage()
    assert kind in text_ and name in text_
    assert FAKE_KEY not in text_ and "refused" not in text_ and "slow" not in text_
    assert FAKE_KEY not in str(records[0].exc_info) and records[0].exc_info is None


def test_diag_decide_route_carries_the_detail_as_error(db, jev):
    from app.services.chatbot.jev_client import JevError

    contact = seed_agent_contact(db)
    arm(db)
    err = JevError("transport")
    err.detail = "ConnectError"
    jev.error = err
    decision = route(db, contact["respond_id"])
    assert decision.reason == "router_failed:transport"
    assert decision.error == "ConnectError"
    assert decision.as_response()["error"] == "ConnectError"


def test_diag_error_is_none_without_a_jev_failure(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    decision = route(db, contact["respond_id"])
    assert decision.reason == "classified" and decision.error is None
    state = route(db, "ZZT-nobody")
    assert state.error is None


def test_diag_the_console_route_and_trace_carry_the_error(
    client, eligible, console_jev, agent_calls, stub_console_seams, bot_parser,
):
    from app.services.chatbot.jev_client import JevError

    err = JevError("transport")
    err.detail = "ConnectError"
    _GRANTS.add("system.chat_history.view")
    _CONSOLE_GRANTS.add("system.chat_history.view")
    console_jev.error = err
    body = _post(client, eligible, "can I submit a goods receive here").json()
    assert body["route"]["reason"] == "router_failed:transport"
    assert body["route"]["error"] == "ConnectError"
    row = eligible["db"].query(ChatbotTurn).filter(ChatbotTurn.id == body["turn_id"]).one()
    stage = [s for s in (row.trace or []) if s.get("stage") == "route"][0]
    assert stage["facts"]["error"] == "ConnectError"


def test_diag_the_console_route_error_is_null_when_there_is_none(
    client, eligible, console_jev, agent_calls, stub_console_seams, bot_parser,
):
    console_jev.answer = jev_answer("chat", 0.95)
    _GRANTS.add("system.chat_history.view")
    _CONSOLE_GRANTS.add("system.chat_history.view")
    body = _post(client, eligible, "can I submit a goods receive here").json()
    assert "error" in body["route"] and body["route"]["error"] is None
    row = eligible["db"].query(ChatbotTurn).filter(ChatbotTurn.id == body["turn_id"]).one()
    stage = [s for s in (row.trace or []) if s.get("stage") == "route"][0]
    assert "error" in stage["facts"] and stage["facts"]["error"] is None
