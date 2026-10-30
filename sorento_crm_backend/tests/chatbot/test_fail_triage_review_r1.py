"""CHATBOT-FAIL-TRIAGE review round 1, red tests (UAC "Review round 1 findings" R1-R7 + nit N1).

Every test asserts the reply the UAC promises, never an internal. Fixtures and helpers come from
the batch 1 file (`test_fail_triage_honest_replies.py`) and the engine failure-path helpers.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

import app.main  # noqa: F401  isort:skip - registers every model before any query

from app.models.user import SystemSetting
from app.services.chatbot import engine as engine_mod
from app.services.chatbot import label_catalog
from app.services.chatbot.lanes import casual
from app.services.chatbot_reply_copy import CHATBOT_REPLY_FALLBACK_OFFER
from tests.chatbot import fail_triage_texts as T
from tests.chatbot import test_stock_fill_predicate as sfp
from tests.chatbot.conftest import set_chatbot_switches
from tests.chatbot.test_carried_miss import LINK, _portal_calls, portal_console  # noqa: F401 - fixture
from tests.chatbot.test_chat_turn_endpoint import api_key, client  # noqa: F401 - fixtures
from tests.chatbot.test_engine import (  # noqa: F401  - fixtures used by name
    _envelope,
    _parser_output,
    seeded,
    stub_access,
    stub_parser,
)
from tests.chatbot.test_fail_triage_honest_replies import _mcp_harness, _sent
from tests.chatbot._r9_engine_console import reply as parser_reply

MS_TEXT = "tolong ya saya nak tahu"
ZH_TEXT = "你好吗"


def _envelope_saying(text: str):
    env = _envelope()
    env.message["message"]["message"]["text"] = text
    return env


# --------------------------------------------------------------------------- #
# R1 price tag request link on the chatbot path
# --------------------------------------------------------------------------- #


def _grant_price_tag_form(session_factory) -> None:
    """The real grant shape (`portal_form_visibility_service.switched_form_types` step 3): a
    per-contact override row. Price tag is not one of the base kinds."""
    from sqlalchemy import text

    from app.models.price_tag import ContactPortalFormOverride

    db = session_factory()
    contact_id = db.execute(text("SELECT id FROM respond_contacts LIMIT 1")).scalar_one()
    db.add(ContactPortalFormOverride(contact_id=contact_id, form_type="price_tag_request", is_enabled=True))
    db.commit()


def _price_tag_turn() -> dict[str, Any]:
    return parser_reply(
        domain_hint="portal_link", intent_hint="get_portal_link", entities=[], portal_form="price_tag_request"
    )


def test_r1_a_price_tag_request_ask_gets_the_price_tag_portal_link(portal_console, session_factory) -> None:
    c = portal_console("+60100000615")
    _grant_price_tag_form(session_factory)
    c.state = {"focus": None, "open_question": None}
    out = c.say("I want to request price tags", _price_tag_turn())
    calls = _portal_calls(c)
    assert len(calls) == 1, c.tool_calls
    assert calls[0].get("submission_type") == "price_tag_request", calls
    assert LINK in out, out
    assert T.PORTAL_COULD_NOT_FIND not in out.lower(), out


FORM_NOT_AVAILABLE = "That form is not available on your account."


def test_ac3_a_contact_without_the_price_tag_grant_gets_no_link(portal_console) -> None:
    c = portal_console("+60100000616")
    c.state = {"focus": None, "open_question": None}
    out = c.say("I want to request price tags", _price_tag_turn())
    assert out == FORM_NOT_AVAILABLE, out
    assert LINK not in out
    assert _portal_calls(c) == [], c.tool_calls


def test_ac3_the_form_not_available_text_has_ms_and_zh() -> None:
    entry = label_catalog.LABELS.get(FORM_NOT_AVAILABLE)
    assert entry, "no label_catalog entry"
    for lang in ("ms", "zh"):
        assert entry.get(lang, "").strip() and entry[lang] != FORM_NOT_AVAILABLE, lang
        assert FORM_NOT_AVAILABLE in label_catalog.defaults(lang), lang


# --------------------------------------------------------------------------- #
# R2 AC-2c real case: tool answered, 201-product set withheld
# --------------------------------------------------------------------------- #


def test_r2_a_withheld_attachment_set_over_201_products_asks_which_product() -> None:
    codes = [f"ZZTP{i:04d}" for i in range(201)]
    env = sfp._empty_section(codes[0], tool_has_result=True, tool_ran=True)
    env.update(
        {
            "domain": "master_products",
            "entities": codes,
            "product_codes": codes,
            "miss": [],
            "attachment_types": ["datasheet"],
        }
    )
    out = sfp._compose(env)
    assert "Which product do you want the" in out and "Send me the code." in out, out
    assert "could not fetch" not in out, out
    T.assert_no_banned_text(out)


# --------------------------------------------------------------------------- #
# R3 AC-1b localized canned offer
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("lang", "message"), [("ms", MS_TEXT), ("zh", ZH_TEXT)])
@pytest.mark.parametrize("exc", [casual.ClarifierError("provider timeout"), casual.ClarifierRateLimited("HTTP 429")])
def test_r3_clarifier_failure_offer_is_in_the_contacts_language(
    session_factory, seeded, stub_parser, stub_access, monkeypatch, lang, message, exc
) -> None:
    set_chatbot_switches(session_factory)
    db = session_factory()
    db.add(SystemSetting(chatbot_completed_lanes=["low_signal"]))
    db.commit()
    stub_parser(_parser_output(message_type="casual", domain_hint=None, intent_hint=None, entities=[]))
    stub_access()
    monkeypatch.setattr(casual, "resolve_for_prompt", lambda db, *, ctx: {"resolutions": []})
    monkeypatch.setattr(casual, "resolve_clarifier_config", lambda db, **_: object())

    def boom(config, prompt):
        raise exc

    monkeypatch.setattr(casual, "call_clarifier", boom)
    result = engine_mod.run_turn(_envelope_saying(message), session_factory=session_factory)
    assert result.reply["text"] == CHATBOT_REPLY_FALLBACK_OFFER[lang], result.reply["text"]


# --------------------------------------------------------------------------- #
# R4 AC-1f: only the queue-wait timeout says H-QUEUE
# --------------------------------------------------------------------------- #


def _offload(session_factory, monkeypatch, status: dict[str, Any]):
    from app.config import settings

    monkeypatch.setattr(settings, "chatbot_turn_wait_seconds", 0.1, raising=False)
    monkeypatch.setattr(engine_mod, "WORKER_POLL_INTERVAL_SECONDS", 0.02, raising=False)

    class _Job:
        id = "ZZT-job-r4"

    monkeypatch.setattr(engine_mod, "enqueue_job", lambda *a, **k: _Job())
    monkeypatch.setattr(engine_mod, "get_job_status", lambda job_id: status)
    monkeypatch.setattr(engine_mod, "cancel_job", lambda job_id: True)
    return engine_mod._run_on_worker(_envelope(), session_factory=session_factory)


def test_r4_a_job_that_returned_no_turn_says_h_error(session_factory, seeded, monkeypatch) -> None:
    result = _offload(session_factory, monkeypatch, {"status": "finished", "result": None, "exc_info": None})
    assert result.reply["text"] == T.H_ERROR, result.reply["text"]


def test_r4_a_job_that_crashed_says_h_error(session_factory, seeded, monkeypatch) -> None:
    result = _offload(session_factory, monkeypatch, {"status": "failed", "result": None, "exc_info": "Traceback boom"})
    assert result.reply["text"] == T.H_ERROR, result.reply["text"]


def test_r4_a_queue_wait_timeout_still_says_h_queue(session_factory, seeded, monkeypatch) -> None:
    result = _offload(session_factory, monkeypatch, {"status": "started", "result": None, "exc_info": None})
    assert result.reply["text"] == T.H_QUEUE, result.reply["text"]


# --------------------------------------------------------------------------- #
# R5 MCP retry guard
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("tool", ["crm_low_stock_report", "crm_portal_link_get", "crm_sales_analysis"])
def test_r5_a_side_effecting_tool_is_never_retried_on_timeout(monkeypatch, tool) -> None:
    call, _unused, calls = _mcp_harness(monkeypatch, [TimeoutError("timed out")])
    with pytest.raises(TimeoutError):
        call(tool, {})
    assert len(calls) == 1, f"{tool} creates something per call, one attempt only: {calls}"


def test_r5_a_call_with_the_agent_loops_own_timeout_is_not_retried(monkeypatch) -> None:
    from app.services.chatbot.lanes.business import services as svc

    _unused, tool, calls = _mcp_harness(monkeypatch, [TimeoutError("timed out")])
    call = svc._mcp_call(None, timeout_seconds=5)
    with pytest.raises(TimeoutError):
        call(tool, {})
    assert len(calls) == 1, calls


def test_r5_a_read_only_tool_without_a_caller_timeout_still_retries_once(monkeypatch) -> None:
    call, tool, calls = _mcp_harness(monkeypatch, [TimeoutError("timed out"), json.dumps({"ok": True})])
    assert call(tool, {}) == {"ok": True}
    assert len(calls) == 2


# --------------------------------------------------------------------------- #
# R6 AC-1d localized, and the OFFERED team
# --------------------------------------------------------------------------- #


def _escalation_boom(monkeypatch) -> None:
    def boom(ctx, item, *, dry_run=False, session_factory=None):
        raise RuntimeError("No team found for agent")

    monkeypatch.setattr(engine_mod, "run_escalation_lane", boom)


def test_r6_escalation_failure_for_a_ms_contact_gets_the_ms_text(
    session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
) -> None:
    db = session_factory()
    setting = db.query(SystemSetting).filter(SystemSetting.id == system_settings_row.id).one()
    setting.chatbot_completed_lanes = ["out_of_scope"]
    db.commit()
    stub_parser(
        _parser_output(
            message_type="request_for_help",
            entities=[],
            routing={"suggested_team": "customer_service", "suggested_agent": "general_enquiries", "team_source": "inferred"},
            escalation={"is_escalation_confirmation": True, "company_pick": None},
        )
    )
    stub_access()
    _escalation_boom(monkeypatch)
    result = engine_mod.run_turn(_envelope_saying(MS_TEXT), session_factory=session_factory)
    expected = label_catalog.LABELS[T.H_ESC]["ms"].format(team="customer service")
    assert result.reply["text"] == expected, result.reply["text"]


def test_r6_the_team_named_is_the_one_offered_to_the_contact(session_factory, seeded, monkeypatch) -> None:
    _escalation_boom(monkeypatch)
    import uuid

    from app.services.chatbot import trace as trace_mod

    item = {"team": "technical_support"}
    result = engine_mod._run_escalation_arm(
        turn_id=str(uuid.uuid4()),
        ctx={},
        item=item,
        actions=[],
        dry_run=False,
        session_factory=session_factory,
        turn_trace=trace_mod.TurnTrace(),
        stage=["looked_up"],
        verdict={"routing": {"suggested_team": "customer_service"}},
    )
    assert result.reply["text"] == T.H_ESC.format(team="technical support"), result.reply["text"]


# --------------------------------------------------------------------------- #
# R7 casual lane setup failure says H-AI
# --------------------------------------------------------------------------- #


def test_r7_a_clarifier_setup_failure_says_h_ai(
    session_factory, seeded, stub_parser, stub_access, monkeypatch
) -> None:
    set_chatbot_switches(session_factory)
    db = session_factory()
    db.add(SystemSetting(chatbot_completed_lanes=["low_signal"]))
    db.commit()
    stub_parser(_parser_output(message_type="casual", domain_hint=None, intent_hint=None, entities=[]))
    stub_access()
    monkeypatch.setattr(casual, "resolve_for_prompt", lambda db, *, ctx: {"resolutions": []})

    def no_config(db, **_):
        raise RuntimeError("clarifier AI config is not set")

    monkeypatch.setattr(casual, "resolve_clarifier_config", no_config)
    result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
    assert result.reply["text"] == T.H_AI, result.reply["text"]
    assert "can't reply to that right now" not in result.reply["text"]


# --------------------------------------------------------------------------- #
# N1 tail failure after composing keeps the attachments
# --------------------------------------------------------------------------- #


def test_n1_a_tail_failure_after_the_answer_keeps_the_attachments_action(
    session_factory, seeded, stub_parser, stub_access, client, api_key, monkeypatch
) -> None:
    monkeypatch.setattr("app.api.v1.external.chat.SessionLocal", session_factory)
    monkeypatch.setattr(engine_mod, "CRM_COMPLETED_BRANCH_KINDS", frozenset())
    stub_parser(_parser_output(message_type="business_query", domain_hint="master_products"))
    stub_access()
    turn = engine_mod.run_turn(_envelope(), session_factory=session_factory)

    real_tail = engine_mod.run_tail

    def tail_with_files(*a, **k):
        reply, patch = real_tail(*a, **k)
        reply = {**reply, "attachments_src": [{"url": "https://files.example.test/zzt.pdf"}]}
        return reply, patch

    def boom(*a, **k):
        raise RuntimeError("customer asks write failed")

    monkeypatch.setattr(engine_mod, "run_tail", tail_with_files)
    monkeypatch.setattr(engine_mod, "_record_customer_asks", boom)
    body = {
        "item": {**turn.item, "branch_kind": "offer_hold"},
        "ctx": turn.ctx,
        "offer_hold": {"clarify_text": "Which one do you mean?"},
    }
    resp = client.post(
        f"/api/v1/external/chat/turn/{turn.turn_id}/complete", json=body, headers={"X-API-Key": api_key}
    )
    assert resp.status_code == 200, resp.text
    kinds = [a["kind"] for a in resp.json()["actions"]]
    assert kinds == ["send_message", "send_attachments"], kinds
