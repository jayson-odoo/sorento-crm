"""AGENTIC-P2 review round 1 (plan "Review round 1", J1, J3-J10): red tests.

The console is gated by `system_settings.chatbot_router_enabled` (J3), so every test that expects
Jev to be asked first enables it. Assumptions are listed in the tester report.
"""
from __future__ import annotations

import json
import uuid

import pytest

from tests.chatbot.agent._seed import seed_agent_contact, seed_contact, seed_user
from tests.chatbot.test_router import FakeJev, OPEN_QUESTION, _decide, _set_vars, _setting
from tests.chatbot.test_router_console_route import (  # noqa: F401 - fixtures
    KEY,
    URL,
    _env_key,
    jev,
    turns,
)
from tests.chatbot.test_console_turn_endpoint import VIEW, _ACTOR, _GRANTS, _permissions, client  # noqa: F401

AI_CONFIG = "/api/v1/system/ai-assistant/config"
SETTINGS = "/api/v1/user-management/settings/"
SETTINGS_GENERAL = "/api/v1/user-management/settings/general"


def _payload(**over) -> dict:
    body = {
        "provider": "openai", "model": "gpt-4o-mini", "temperature": 0, "system_prompt": "",
        "enabled_tools": [], "rag_enabled": True, "is_enabled": True,
    }
    body.update(over)
    return body


def _real_actor(db):
    """The ai-assistant PUT writes updated_by_user_id (FK to users): the caller must be a real row."""
    _ACTOR["id"] = seed_user(db, contact_pk=None)
    db.commit()


from tests._pg_fixture import blank_session

LONG_AGENT = "compare Penang and Johor sales this quarter"


def _enable(session_factory):
    from app.models.user import SystemSetting

    db = session_factory()
    db.add(SystemSetting(id=str(uuid.uuid4()), name="ZZT r1 co", chatbot_router_enabled=True))
    db.commit()


def _agent_contact(session_factory, *, session_vars=None):
    from sqlalchemy import text

    db = session_factory()
    c = seed_agent_contact(db)
    if session_vars is not None:
        db.execute(
            text("UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb) WHERE id = :id"),
            {"sv": json.dumps(session_vars), "id": c["pk"]},
        )
    db.commit()
    return c


def _post(client, contact, text_=LONG_AGENT, **extra):
    return client.post(URL, json={"contact_respond_id": contact["respond_id"], "text": text_, **extra})


def _offer(ttl):
    return {
        "open_question": {
            "kind": "team_pick", "options": [], "expects": None, "team": None,
            "asked_at_turn": 3, "payload": {"ttl": ttl},
        },
        "focus": {"customers": []}, "ideation": None, "access_levels": [], "contains_flyer": False,
    }


# ------------------------------------------------------------------ J1 keep the console conversation


def test_j1_session_vars_and_run_id_pass_through_to_the_console_turn(client, session_factory, jev, turns):
    _enable(session_factory)
    c = _agent_contact(session_factory)
    jev.p_agent = 0.1
    run_id = str(uuid.uuid4())
    sv = {"focus": {"customers": []}, "open_question": None, "ideation": None, "access_levels": [], "contains_flyer": False}
    resp = _post(client, c, "stock of ABC", session_vars=sv, run_id=run_id)
    assert resp.status_code == 200, resp.text
    assert resp.json()["route"]["route"] == "chat"
    assert turns.bot[0]["session_vars"] == sv
    assert turns.bot[0]["run_id"] == run_id


def test_j1_a_bot_question_in_the_supplied_session_routes_to_the_bot(client, session_factory, jev, turns):
    _enable(session_factory)
    c = _agent_contact(session_factory)  # the stored row is empty
    body = _post(client, c, "the second one", session_vars=OPEN_QUESTION, run_id="r1").json()
    assert body["route"]["route"] == "chat" and body["route"]["reason"] == "open_question"
    assert jev.calls == []
    assert turns.bot[0]["session_vars"] == OPEN_QUESTION


def test_j1_control_with_no_question_anywhere_jev_is_asked(client, session_factory, jev, turns):
    _enable(session_factory)
    c = _agent_contact(session_factory)
    body = _post(client, c, "the second one").json()
    assert body["route"]["reason"] == "jev" and body["route"]["route"] == "agent"
    assert len(jev.calls) == 1


def test_j1_an_expired_escalation_offer_does_not_hold_the_contact_on_the_bot(client, session_factory, jev, turns):
    _enable(session_factory)
    c = _agent_contact(session_factory)
    body = _post(client, c, LONG_AGENT, session_vars=_offer(1), run_id="r1").json()  # ttl 1 ticks to 0: gone
    assert body["route"]["reason"] == "jev"
    assert len(jev.calls) == 1


def test_j1_a_live_escalation_offer_still_holds_it(client, session_factory, jev, turns):
    _enable(session_factory)
    c = _agent_contact(session_factory)
    body = _post(client, c, "yes", session_vars=_offer(3), run_id="r1").json()
    assert body["route"]["reason"] == "open_question" and body["route"]["route"] == "chat"
    assert jev.calls == []


def test_j1_the_stored_row_is_used_only_when_no_session_is_supplied(client, session_factory, jev, turns):
    _enable(session_factory)
    c = _agent_contact(session_factory, session_vars=OPEN_QUESTION)
    stored = _post(client, c, "the second one").json()
    assert stored["route"]["reason"] == "open_question"
    supplied = _post(client, c, "the second one", session_vars={}, run_id="r1").json()  # "remembers nothing"
    assert supplied["route"]["reason"] == "jev"
    assert len(jev.calls) == 1


# ------------------------------------------------------------------ J3 off switch


def test_j3_routing_off_is_the_default_and_goes_to_the_bot_without_jev(client, session_factory, jev, turns):
    c = _agent_contact(session_factory)  # no settings row at all
    body = _post(client, c).json()
    assert body["route"]["route"] == "chat" and body["route"]["reason"] == "routing_off"
    assert body["turn"]["reply_text"] == "BOT-REPLY"
    assert jev.calls == [] and turns.agent == []


def test_j3_an_explicit_off_setting_is_routing_off(client, session_factory, jev, turns):
    from app.models.user import SystemSetting

    db = session_factory()
    db.add(SystemSetting(id=str(uuid.uuid4()), name="ZZT r1 off", chatbot_router_enabled=False))
    db.commit()
    c = _agent_contact(session_factory)
    assert _post(client, c).json()["route"]["reason"] == "routing_off"
    assert jev.calls == []


def test_j3_enabled_asks_jev(client, session_factory, jev, turns):
    _enable(session_factory)
    c = _agent_contact(session_factory)
    body = _post(client, c).json()
    assert body["route"]["route"] == "agent" and body["route"]["reason"] == "jev"
    assert len(jev.calls) == 1


# ------------------------------------------------------------------ J7 not_eligible


@pytest.mark.parametrize("sub", ["switch_off", "ai_replies_off", "no_linked_user"])
def test_j7_an_ineligible_contact_is_not_eligible_with_the_refusal_in_detail(client, session_factory, jev, turns, sub):
    _enable(session_factory)
    db = session_factory()
    if sub == "switch_off":
        c = seed_contact(db, agent_enabled=False)
        seed_user(db, contact_pk=c["pk"])
    elif sub == "ai_replies_off":
        c = seed_contact(db, chatbot_allowed=False)
        seed_user(db, contact_pk=c["pk"])
    else:
        c = seed_contact(db)
    db.commit()
    body = _post(client, c).json()
    assert body["route"]["route"] == "chat"
    assert body["route"]["reason"] == "not_eligible"
    assert body["route"]["detail"] == sub
    assert jev.calls == []


def test_j7_an_eligible_decision_has_no_detail(client, session_factory, jev, turns):  # control
    _enable(session_factory)
    c = _agent_contact(session_factory)
    body = _post(client, c).json()
    assert body["route"]["reason"] == "jev"
    assert "detail" in body["route"] and body["route"]["detail"] is None


# ------------------------------------------------------------------ J4 trim


def test_j4_the_state_trims_the_message_and_each_earlier_text_and_reply():
    from app.services.chatbot import router

    state = router.build_state(
        "m" * 500 + "MSG-TAIL",
        [{"text": "t" * 300 + "TXT-TAIL", "reply": "r" * 300 + "RPL-TAIL", "answered_by": "bot"}],
    )
    assert "m" * 500 in state and "MSG-TAIL" not in state
    assert "t" * 300 in state and "TXT-TAIL" not in state
    assert "r" * 300 in state and "RPL-TAIL" not in state


def test_j4_short_texts_are_left_whole():  # control
    from app.services.chatbot import router

    state = router.build_state("m" * 500, [{"text": "t" * 300, "reply": "r" * 300, "answered_by": "bot"}])
    assert "m" * 500 in state and "t" * 300 in state and "r" * 300 in state


# ------------------------------------------------------------------ J8 model on the label


def _label(db, provider, model):
    from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
    from app.services import ai_prompt_registry

    version = AIPromptVersion(
        name="chatbot_router", version=1, template=ai_prompt_registry.PROMPT_KEYS["chatbot_router"].fallback()
    )
    db.add(version)
    db.flush()
    db.add(AIPromptLabel(name="chatbot_router", label="production", version_id=version.id, provider=provider, model=model))
    db.flush()


@pytest.mark.parametrize(
    "provider, model, expected",
    [
        ("gemini", "gemini-2.5-flash", "jev-latest"),
        ("openai", "gpt-4o-mini", "jev-latest"),
        ("", "jev-custom", "jev-custom"),
        (None, "jev-custom", "jev-custom"),
        ("jev", "jev-custom", "jev-custom"),
        ("jev", None, "jev-latest"),
    ],
)
def test_j8_the_label_model_is_used_only_for_an_empty_or_jev_provider(provider, model, expected):
    with blank_session() as db:
        c = seed_agent_contact(db)
        _setting(db, chatbot_router_enabled=True)
        _label(db, provider, model)
        fake = FakeJev(0.9)
        _decide(db, c, fake)
        assert fake.calls[0]["model"] == expected


# ------------------------------------------------------------------ J10 tie and nulls


def _probs(agent, chat):
    def fake(*args, **kw):
        return {"choice": "agent", "confidence": agent, "probabilities": {"chat": chat, "agent": agent},
                "input_tokens": 10, "output_tokens": 1}

    return fake


@pytest.mark.parametrize(
    "agent, chat, route, reason",
    [
        (0.5, 0.5, "chat", "low_confidence"),
        (0.45, 0.45, "chat", "low_confidence"),  # P(agent) >= P(chat), both under 0.5
        (0.55, 0.3, "chat", "low_confidence"),
        (0.4, 0.6, "chat", "jev"),  # chat clearly larger
        (0.7, 0.3, "agent", "jev"),
    ],
)
def test_j10_low_confidence_is_defined_against_p_chat(agent, chat, route, reason):
    with blank_session() as db:
        c = seed_agent_contact(db)
        _setting(db, chatbot_router_enabled=True)
        d = _decide(db, c, _probs(agent, chat))
        assert (d.route, d.reason) == (route, reason)


def test_j10_null_for_each_new_setting_saves_the_default(client, session_factory):
    from app.models.user import SystemSetting

    _GRANTS.update({"user_management.settings.view", "user_management.settings.edit"})
    db = session_factory()
    db.add(SystemSetting(id=str(uuid.uuid4()), name="ZZT r1 nulls"))
    db.commit()
    set_ = {"chatbot_router_enabled": True, "chatbot_router_min_score": 0.9, "chatbot_agent_daily_turns": 7}
    assert client.put(SETTINGS_GENERAL, json=set_).status_code == 200
    assert client.get(SETTINGS).json()["settings"]["chatbot_agent_daily_turns"] == 7  # control
    resp = client.put(SETTINGS_GENERAL, json={k: None for k in set_})
    assert resp.status_code == 200, resp.text
    body = client.get(SETTINGS).json()["settings"]
    assert body["chatbot_router_enabled"] is False
    assert body["chatbot_router_min_score"] == 0.7
    assert body["chatbot_agent_daily_turns"] == 50


# ------------------------------------------------------------------ J9 non-ASCII key


@pytest.fixture()
def wire(monkeypatch):
    import httpx

    seen = []

    def handle(self, request):
        request.read()
        seen.append(request)
        return httpx.Response(200, json={
            "answers": {"route": {"type": "choice", "choice": "agent", "confidence": 0.9,
                                  "probabilities": {"chat": 0.1, "agent": 0.9}}},
            "usage": {"input_tokens": 1, "output_tokens": 1}})

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle)
    return seen


def test_j9_a_non_ascii_key_is_a_jev_error_without_the_key(wire):
    from app.services.chatbot import jev_client

    bad = "ZZT-kéy-ü-1234"
    with pytest.raises(jev_client.JevError) as exc:
        jev_client.choose(bad, state="s", instructions="i", criteria={"chat": "a", "agent": "b"})
    assert bad not in str(exc.value) and bad not in repr(exc.value)
    assert wire == []  # nothing was sent


def test_j9_control_an_ascii_key_goes_through(wire):
    from app.services.chatbot import jev_client

    assert jev_client.choose("ZZT-ascii-key", state="s", instructions="i", criteria={"chat": "a", "agent": "b"})["choice"] == "agent"
    assert len(wire) == 1


def test_j9_the_settings_save_refuses_a_non_ascii_jev_key(client, session_factory):
    _GRANTS.update({"system.ai_assistant_settings.view", "system.ai_assistant_settings.edit"})
    _real_actor(session_factory())
    ok = client.put(AI_CONFIG, json=_payload(jev_api_key="ZZT-ascii-key-0001"))
    assert ok.status_code == 200, ok.text  # control
    bad = "ZZT-k\u00e9y-\u00fc-9999"
    resp = client.put(AI_CONFIG, json=_payload(jev_api_key=bad))
    assert resp.status_code in (400, 422), resp.text
    assert bad not in resp.text
    assert client.get(AI_CONFIG).json()["jev_api_key_masked"] == "****0001"  # unchanged


# ------------------------------------------------------------------ J6 key rotation


def test_j6_reencrypt_covers_the_jev_column():
    from scripts import reencrypt_field_secrets as mod

    assert ("ai_assistant_configs", "jev_api_key_ciphertext", True) in mod.COLUMNS
    assert ("ai_assistant_configs", "gemini_api_key_ciphertext", True) in mod.COLUMNS  # control


# ------------------------------------------------------------------ J5 eval survives a failed call


from tests.chatbot_eval.test_router_eval import (  # noqa: E402
    ITEMS,
    FakeChoose,
    _env as _eval_env,  # noqa: F401
    _results,
    _run,
    _summary,
)


class _FailsOn(FakeChoose):
    def __init__(self, failing_text, exc):
        super().__init__()
        self.failing_text, self.exc = failing_text, exc

    def __call__(self, *args, **kw):
        if self.failing_text in kw["state"]:
            self.calls.append(dict(kw))
            raise self.exc
        return super().__call__(*args, **kw)


def test_j5_a_jev_error_item_is_recorded_as_a_router_failure(tmp_path):
    from app.services.chatbot.jev_client import JevError

    fake = _FailsOn("why did Penang drop", JevError("boom"))
    rc, out = _run(tmp_path, choose=fake)
    assert rc == 0
    rows = {r["id"]: r for r in _results(out)}
    assert len(rows) == len(ITEMS)  # the run went on
    assert rows["g2"]["route"] == "chat" and rows["g2"]["reason"] == "router_failed"
    assert rows["g1"].get("reason") != "router_failed"
    s = _summary(out)
    assert s["failures"] == 1
    assert s["missed_agent_rate"] == pytest.approx(1 / 4)  # g2 is labelled agent, routed chat


def test_j5_a_clean_run_has_zero_failures(tmp_path):  # control
    _, out = _run(tmp_path, choose=FakeChoose())
    assert _summary(out)["failures"] == 0


def test_j5_results_are_written_line_by_line_so_a_crash_keeps_earlier_rows(tmp_path):
    fake = _FailsOn("stock of ABC123", RuntimeError("crash"))  # the third item
    try:
        _run(tmp_path, choose=fake)
    except Exception:  # noqa: BLE001 - the harness may raise or return non-zero
        pass
    lines = (tmp_path / "out" / "results.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["id"] for line in lines if line] == ["g1", "g2"]


def test_j5_the_summary_gives_missed_and_wasted_rates_per_language(tmp_path):
    _, out = _run(tmp_path, choose=FakeChoose())
    per = _summary(out)["per_language"]
    assert per["en"]["missed_agent_rate"] == pytest.approx(1 / 2)  # g2 of g1, g2
    assert per["en"]["wasted_agent_rate"] == pytest.approx(1 / 2)  # g4 of g3, g4
    assert per["ms"]["missed_agent_rate"] == pytest.approx(0.0)
    assert per["ms"]["wasted_agent_rate"] == pytest.approx(0.0)
    assert per["zh"]["missed_agent_rate"] == pytest.approx(0.0)
    assert per["zh"]["wasted_agent_rate"] == pytest.approx(1.0)  # g7
    assert per["en"]["agreement"] == pytest.approx(2 / 4)  # existing key stays
