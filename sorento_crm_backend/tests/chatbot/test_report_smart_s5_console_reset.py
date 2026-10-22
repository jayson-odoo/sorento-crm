"""REPORT-SMART-L S5-1 (AC-S5-1): a console Reset starts the parser's history fresh.

A Reset is a new test run id with empty session vars. The parser's user block then carries no
Recent exchanges, no Previous response and no Recent conversations line from before it; turns
of the current run still appear. A real (non-console) contact's history is unchanged.
Fake names only.
"""
from __future__ import annotations

import copy
from typing import Any

import pytest

from app.services.chatbot import engine as engine_mod
from app.services.chatbot.lanes.business.services import AnswerServices, FetchServices
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import CONTACT_ID, _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import Console, _console, _e, _rank, _fake_body, TOOL, GRANT
from tests.chatbot.test_report_smart_step7 import KEEP, THIS_YEAR


class Recorder(Console):
    """The report-ask console on a chosen run id, keeping the user block the parser was shown."""

    def say_in(self, run_id: str, qf: dict[str, Any], body: str) -> tuple[str, str]:
        import json

        from app.services.chatbot import console_service
        from app.services.chatbot.head import parser as parser_mod

        blocks: list[str] = []

        def _parse(config: Any, user_block: str) -> dict[str, Any]:
            blocks.append(user_block)
            return qf

        self.monkeypatch.setattr(parser_mod, "parse", _parse)
        self.monkeypatch.setattr(
            engine_mod.business_services, "fetch_services",
            lambda db: FetchServices(mcp_call=lambda name, args: json.dumps(_fake_body(args)) if name == TOOL
                                     else json.dumps({"has_result": False, "items": []})),
        )
        self.monkeypatch.setattr(
            engine_mod.business_services, "answer_services_for",
            lambda session_factory: AnswerServices(mcp_probe=lambda n, a: {"data": []}, family_fetch=lambda q: {"data": []}),
        )
        db = self.session_factory()
        try:
            result = console_service.run_console_turn(
                db, contact_respond_id=str(CONTACT_ID), text=body,
                session_vars=copy.deepcopy(self.session_vars), run_id=run_id,
            )
        finally:
            db.close()
        self.session_vars = result.session_vars or {}
        return result.reply_text or "", (blocks[-1] if blocks else "")


@pytest.fixture
def rec(session_factory, monkeypatch):
    c = _console(session_factory, monkeypatch, grants=[GRANT])
    c.__class__ = Recorder
    return c


def _ranking() -> dict[str, Any]:
    return _rank(top_n=3, measure="qty", basis="delivered", state_changes=list(KEEP), **THIS_YEAR)


def _product_ask() -> dict[str, Any]:
    return _parser_output(domain_hint="master_products", intent_hint="check_product",
                          entities=[_e("SRTWT7408", "product")])


def _history_lines(block: str) -> str:
    return "\n".join(ln for ln in block.splitlines() if ln.startswith(("Previous response", "Recent exchanges", "Recent conversations"))
                     or ln.lstrip().startswith(("- User:", "User:")))


def test_s5_1_a_reset_run_sees_nothing_from_before_the_reset(rec) -> None:
    reply1, _ = rec.say_in("zzt-run-1", _ranking(), "ZZR1 top salesman this year")
    rec.say_in("zzt-run-1", _product_ask(), "ZZR1 check SRTWT7408")
    rec.session_vars = {}  # Reset: a new run id and empty session vars
    _text, block = rec.say_in("zzt-run-2", _product_ask(), "ZZR2 first")
    assert "ZZR1" not in block, block
    assert "Previous response: \n" in block, block  # the renderer's empty form (turn/context.py)
    assert "Recent conversations" not in block, block


def test_s5_1_the_current_run_still_sees_its_own_earlier_turns(rec) -> None:
    rec.say_in("zzt-run-1", _ranking(), "ZZR1 top salesman this year")
    rec.session_vars = {}
    first_reply, _ = rec.say_in("zzt-run-2", _product_ask(), "ZZR2 first")
    _text, block = rec.say_in("zzt-run-2", _product_ask(), "ZZR2 second")
    assert "ZZR2 first" in block, block
    assert "ZZR1" not in block, block
    assert "Previous response: (none)" not in block, block


def test_s5_1_near_miss_a_non_console_contact_still_sees_its_earlier_turns(session_factory, monkeypatch) -> None:
    from app.services.chatbot.head import parser as parser_mod
    from tests.chatbot.test_outstanding_lane import _run_turn, _seed_contact

    _seed_contact(session_factory, variables={})
    blocks: list[str] = []
    qf = _product_ask()
    for n, body in enumerate(["ZZW1 first", "ZZW2 second"]):
        real = parser_mod.parse
        _run_turn(session_factory, monkeypatch, qf=qf, text_body=body, msg_id=f"zzt-s5-w{n}",
                  capture_user_block=blocks, matches={})
    assert "ZZW1 first" in blocks[-1], blocks[-1]
    assert "Previous response: (none)" not in blocks[-1], blocks[-1]


# ---------------------------------------------------------------- Recent conversations frames


def _memory_on(session_factory) -> None:
    from app.models.user import SystemSetting

    db = session_factory()
    try:
        row = db.query(SystemSetting).first()
        if row is None:
            row = SystemSetting()
            db.add(row)
        row.chatbot_memory = {"enabled": True, "default_level": "episodes"}
        db.commit()
    finally:
        db.close()


def _closed_frame(session_factory, *, summary: str, run_id: str | None, is_test: bool = True) -> None:
    """A closed conversation frame whose turn_ids are the contact's stored turns of `run_id`
    (those whose envelope carries that test_run_id); every stored turn when `run_id` is None."""
    import uuid
    from datetime import datetime, timezone

    from app.models.access import RespondContact
    from app.models.chatbot_turn import ChatbotTurn
    from app.models.conversation_frame import ConversationFrame

    db = session_factory()
    try:
        turns = db.query(ChatbotTurn).filter(
            ChatbotTurn.contact_respond_id == str(CONTACT_ID), ChatbotTurn.status == "done").all()
        ids = [str(t.id) for t in turns if run_id is None or (t.envelope or {}).get("test_run_id") == run_id]
        assert ids, ("harness: no stored turn of the run", run_id)
        contact = db.query(RespondContact).filter(RespondContact.respond_io_id == str(CONTACT_ID)).one()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        db.add(ConversationFrame(
            id=str(uuid.uuid4()), contact_id=str(CONTACT_ID), space_id="364817", channel="whatsapp",
            contact_respond_id=str(CONTACT_ID), domain="master_products", status="closed", close_reason="reset",
            summary=summary, turn_ids=ids, is_test=is_test, opened_at=now, started_at=now,
            last_activity_at=now, closed_at=now,
        ))
        db.commit()
    finally:
        db.close()


def test_s5_1_a_frame_made_of_turns_from_before_the_reset_is_not_shown(rec, session_factory) -> None:
    _memory_on(session_factory)
    rec.say_in("zzt-run-1", _product_ask(), "ZZR1 check SRTWT7408")
    _closed_frame(session_factory, summary="ZZFRAME1 asked about SRTWT7408", run_id="zzt-run-1")
    rec.session_vars = {}
    _text, block = rec.say_in("zzt-run-2", _product_ask(), "ZZR2 first")
    assert "ZZFRAME1" not in block, block


def test_s5_1_near_miss_a_frame_made_of_the_current_runs_turns_shows_on_a_later_turn(rec, session_factory) -> None:
    _memory_on(session_factory)
    rec.say_in("zzt-run-2", _product_ask(), "ZZR2 first")
    _closed_frame(session_factory, summary="ZZFRAME2 asked about SRTWT7408", run_id="zzt-run-2")
    _text, block = rec.say_in("zzt-run-2", _product_ask(), "ZZR2 second")
    assert "ZZFRAME2" in block, block


def test_s5_1_near_miss_a_non_console_contacts_frame_is_still_shown(session_factory, monkeypatch) -> None:
    from tests.chatbot.test_outstanding_lane import _run_turn, _seed_contact

    _memory_on(session_factory)
    _seed_contact(session_factory, variables={})
    blocks: list[str] = []
    _run_turn(session_factory, monkeypatch, qf=_product_ask(), text_body="ZZW1 first", msg_id="zzt-s5-f1",
              capture_user_block=blocks, matches={})
    _closed_frame(session_factory, summary="ZZFRAME3 asked about SRTWT7408", run_id=None, is_test=False)
    _run_turn(session_factory, monkeypatch, qf=_product_ask(), text_body="ZZW2 second", msg_id="zzt-s5-f2",
              capture_user_block=blocks, matches={})
    assert "ZZFRAME3" in blocks[-1], blocks[-1]
