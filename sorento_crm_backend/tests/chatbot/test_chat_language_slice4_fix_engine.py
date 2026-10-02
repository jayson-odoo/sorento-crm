"""CHAT-LANGUAGE slice 4 fix round, engine side: the stored row and trace carry what was sent,
and a message answered ahead keeps the language its own turn chose."""
from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot import engine, label_catalog, turn_runtime
from app.services.chatbot.label_catalog import Localizer
from tests.chatbot._r9_engine_console import EngineConsole, product, stock
from tests.chatbot.test_chat_language_slice4_engine import MS_ASK, MS_OFFER, _staff_console
from tests.chatbot.test_engine import CONTACT_ID, stub_access  # noqa: F401 - a pytest fixture


def _latest_row(session_factory) -> ChatbotTurn:
    db = session_factory()
    return (
        db.query(ChatbotTurn)
        .filter(ChatbotTurn.contact_respond_id == str(CONTACT_ID))
        .order_by(ChatbotTurn.started_at.desc())
        .first()
    )


def test_item2_the_stored_reply_the_parser_reads_next_turn_is_the_localized_one(
    session_factory, monkeypatch, stub_access
):
    c = _staff_console(session_factory, monkeypatch, stub_access, "+60000009701")
    assert c.say(MS_ASK, stock(product("ZZNOPE999"))) == MS_OFFER
    row = _latest_row(session_factory)
    assert row.response["reply"]["text"] == MS_OFFER
    assert [a["text"] for a in row.response["actions"] if a.get("kind") == "send_message"] == [MS_OFFER]
    db = session_factory()
    assert (
        turn_runtime.previous_reply_text(
            db, contact_respond_id=str(CONTACT_ID), ingress="webhook", is_test=True
        )
        == MS_OFFER
    )


def test_item3_the_trace_records_show_what_was_sent(session_factory, monkeypatch, stub_access):
    c = _staff_console(session_factory, monkeypatch, stub_access, "+60000009702")
    c.say(MS_ASK, stock(product("ZZNOPE999")))
    row = _latest_row(session_factory)
    stages = {r.get("stage"): r for r in row.trace if isinstance(r, dict)}
    sent = stages["sent"]["raw"]["actions"]
    assert [a["text"] for a in sent if a.get("kind") == "send_message"] == [MS_OFFER]
    assert stages["replied"]["raw"]["reply"]["text"] == MS_OFFER


def _result(item, text):
    return SimpleNamespace(
        turn_id=str(uuid.uuid4()),
        item=item,
        duplicate=False,
        reply={"text": text},
        actions=[{"kind": "send_message", "text": text}],
    )


def test_item6_a_result_is_localized_with_its_own_items_language(session_factory):
    ms = _result({"reply_language": "ms"}, "Would you like me to escalate?")
    engine._localize_result(ms, session_factory, True)
    assert ms.reply["text"] == "Adakah anda mahu saya rujuk kepada pasukan kami?"
    assert ms.actions[0]["text"] == ms.reply["text"]
    # An item with no language (or an English one) is left as composed.
    none = _result({}, "Would you like me to escalate?")
    engine._localize_result(none, session_factory, True)
    assert none.reply["text"] == "Would you like me to escalate?"
    en = _result({"reply_language": "en"}, "Would you like me to escalate?")
    engine._localize_result(en, session_factory, True)
    assert en.actions[0]["text"] == "Would you like me to escalate?"


def test_item7_the_accepted_escalation_confirmation_is_malay(session_factory, monkeypatch, stub_access):
    from tests.chatbot.test_chat_language_slice4_engine import _confirmation
    from tests.chatbot.test_escalation_agent_carry import _capture_next_assignee, _capture_sla

    c = _staff_console(session_factory, monkeypatch, stub_access, "+60000009703")
    _capture_next_assignee(monkeypatch)
    _capture_sla(monkeypatch)
    assert c.say(MS_ASK, stock(product("ZZNOPE999"))) == MS_OFFER
    c.say("ya", _confirmation())
    sent = [a["text"] for a in _latest_row(session_factory).response["actions"] if a.get("kind") == "send_message"]
    assert any("Pertanyaan ini telah diserahkan kepada pegawai bertanggungjawab (PIC) daripada pasukan" in t for t in sent), sent
    assert not any("routed" in t for t in sent), sent
