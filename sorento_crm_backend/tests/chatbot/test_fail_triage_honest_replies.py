"""CHATBOT-FAIL-TRIAGE batch 1, red tests (UAC AC-1 to AC-4).

Owner rule: the bot never replies "busy right now" or "ran into a problem understanding".
Every failure path gets the honest, specific reply named in the UAC tables, and the turn row
keeps the real reason in `error`.

Reasons for the AC-2 envelopes: compose only sees `env["error"]`, so the fixtures carry the
reason keywords the UAC names (`subject_required`, `customer_not_permitted`, the empty-set and
attachment-cap phrases). The coder may map them differently inside, but the replies are fixed.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

import pytest
from sqlalchemy import text

import app.main  # noqa: F401  isort:skip - registers every model before any query

from app.models.chatbot_turn import ChatbotTurn
from app.models.user import SystemSetting
from app.services.chatbot import engine as engine_mod
from app.services.chatbot import label_catalog
from app.services.chatbot.contracts import Envelope
from app.services.chatbot.head import parser as parser_mod
from app.services.chatbot.lanes import casual
from tests.chatbot import fail_triage_texts as T
from tests.chatbot import test_engine_failure_paths as fp
from tests.chatbot import test_stock_fill_predicate as sfp
from tests.chatbot.conftest import set_chatbot_switches
from tests.chatbot.test_chat_turn_endpoint import api_key, client  # noqa: F401 - fixtures
from tests.chatbot.test_engine import (  # noqa: F401  - fixtures used by name
    CONTACT_ID,
    _envelope,
    _parser_output,
    seeded,
    stub_access,
    stub_parser,
)

CODE = "SRTWC8517"


def _row(session_factory, turn_id: str) -> ChatbotTurn:
    return session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).first()


def _sent(result) -> list[str]:
    return [a["text"] for a in result.actions if a["kind"] == "send_message"]


# --------------------------------------------------------------------------- #
# AC-1a parser failed -> H-AI
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("error", "needle"),
    [
        (parser_mod.ParserError("parser provider call timed out after 30s"), "timed out"),
        (
            parser_mod.ParserError("parser provider call failed: HTTP 429 rate limit", rate_limited=True),
            "429",
        ),
        (parser_mod.ParserError("parser provider call failed: HTTP 403 forbidden"), "403"),
        (parser_mod.ParserError("parser answer was not JSON: 'Sure! here'"), "not JSON"),
    ],
    ids=["timeout", "429", "403", "non_json"],
)
def test_ac1a_parser_failure_says_the_ai_did_not_answer(
    session_factory, seeded, stub_parser, stub_access, error, needle
) -> None:
    stub_parser(error=error)
    stub_access()
    result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
    assert result.reply["text"] == T.H_AI
    assert _sent(result) == [T.H_AI]
    T.assert_no_banned_text(result.reply["text"])
    row = _row(session_factory, result.turn_id)
    assert row.status == "failed" and needle in row.error, "the turn row keeps the real reason"


# --------------------------------------------------------------------------- #
# AC-1b clarifier failed -> the canned offer
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "exc",
    [casual.ClarifierRateLimited("HTTP 429"), casual.ClarifierError("provider timeout"), ValueError("bad json")],
    ids=["rate_limited", "clarifier_error", "other"],
)
def test_ac1b_clarifier_failure_sends_the_canned_offer(
    session_factory, seeded, stub_parser, stub_access, monkeypatch, exc
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
    result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
    assert result.reply["text"] == T.H_OFFER
    T.assert_no_banned_text(result.reply["text"])
    row = _row(session_factory, result.turn_id)
    assert row.status == "failed" and row.stage == "casual_llm" and row.error


# --------------------------------------------------------------------------- #
# AC-1c lane / fetch error -> H-FETCH naming what was asked
# --------------------------------------------------------------------------- #


def test_ac1c_a_lane_that_raised_says_what_could_not_be_fetched(
    session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
) -> None:
    set_chatbot_switches(session_factory, business_lane=True)
    fp.TestTheBusinessLaneOnFetchFailure._wire_resolver(monkeypatch)
    monkeypatch.setattr(
        engine_mod.business,
        "run_fetch",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("MCP tool crm_inventory failed: timeout")),
    )
    stub_parser()
    stub_access()
    result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
    reply = result.reply["text"]
    T.assert_no_banned_text(reply)
    assert re.fullmatch(rf"I could not fetch .+ for .*{CODE}.* just now, please try again\.", reply), reply
    row = _row(session_factory, result.turn_id)
    assert row.status == "failed" and row.stage == "looked_up" and "timeout" in row.error


# --------------------------------------------------------------------------- #
# AC-1d escalation failed -> H-ESC naming the team
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "message",
    [
        "AppException: No team found for agent and team_code=customer_service",
        "AppException: SLA policy not found for the team (400)",
        "AppException: assignee is not in the team (404)",
    ],
    ids=["no_team", "no_sla_policy", "assignee_not_in_team"],
)
def test_ac1d_escalation_failure_names_the_team(
    session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch, message
) -> None:
    from app.services.chatbot.tail.outcome import pretty_team

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

    def boom(ctx, item, *, dry_run=False, session_factory=None):
        raise RuntimeError(message)

    monkeypatch.setattr(engine_mod, "run_escalation_lane", boom)
    result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
    expected = T.H_ESC.format(team=pretty_team("customer_service"))
    assert result.reply["text"] == expected
    T.assert_no_banned_text(result.reply["text"])
    assert all(a["kind"] != "assign_conversation" for a in result.actions)
    row = _row(session_factory, result.turn_id)
    assert row.status == "failed" and row.stage == "looked_up" and message.split(": ", 1)[1] in row.error


# --------------------------------------------------------------------------- #
# AC-1e any other exception -> H-ERROR
# --------------------------------------------------------------------------- #


def test_ac1e_an_unhandled_stage_error_says_h_error(
    session_factory, seeded, stub_parser, stub_access, monkeypatch
) -> None:
    stub_parser()
    stub_access()
    monkeypatch.setattr(
        engine_mod, "check_access", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("access service down"))
    )
    result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
    assert result.reply["text"] == T.H_ERROR
    assert _sent(result) == [T.H_ERROR]
    row = _row(session_factory, result.turn_id)
    assert row.status == "failed" and "access service down" in row.error


def test_ac1e_an_earlier_message_answered_ahead_that_fails_says_h_error(
    session_factory, seeded, monkeypatch
) -> None:
    """`_answer_claimed` (engine.py ~2534): an earlier-sent message that fails on its own row."""
    monkeypatch.setattr(
        engine_mod, "_run_stages", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("stage blew up"))
    )
    result = engine_mod._answer_claimed(
        _envelope(),
        session_factory=session_factory,
        turn_id=str(uuid.uuid4()),
        contact_respond_id=str(CONTACT_ID),
        contact_scope=frozenset(),
        switches=None,
        answered_ahead_by={"turn_id": "x"},
    )
    assert result.reply["text"] == T.H_ERROR


# --------------------------------------------------------------------------- #
# AC-1f queue wait / offload did not finish -> H-QUEUE
# --------------------------------------------------------------------------- #


def test_ac1f_a_previous_turn_still_running_says_h_queue(session_factory, seeded) -> None:
    result = engine_mod._worker_failed(
        _envelope(), session_factory, "the offloaded turn did not finish within 60s"
    )
    assert result.reply["text"] == T.H_QUEUE
    assert _sent(result) == [T.H_QUEUE]
    T.assert_no_banned_text(result.reply["text"])


# --------------------------------------------------------------------------- #
# AC-1g tail failed -> composed answer is sent, else H-ERROR
# --------------------------------------------------------------------------- #


class TestAc1gTail:
    @pytest.fixture()
    def delegated(self, session_factory, seeded, stub_parser, stub_access, monkeypatch):
        monkeypatch.setattr("app.api.v1.external.chat.SessionLocal", session_factory)
        monkeypatch.setattr(engine_mod, "CRM_COMPLETED_BRANCH_KINDS", frozenset())
        stub_parser(_parser_output(message_type="business_query", domain_hint="master_products"))
        stub_access()
        return engine_mod.run_turn(_envelope(), session_factory=session_factory)

    def _post(self, client, api_key, turn):
        body = {"item": turn.item, "ctx": turn.ctx}
        return client.post(
            f"/api/v1/external/chat/turn/{turn.turn_id}/complete", json=body, headers={"X-API-Key": api_key}
        )

    def test_no_composed_answer_says_h_error(self, client, api_key, delegated, monkeypatch) -> None:
        def boom(*a, **k):
            raise RuntimeError("the tail could not finish")

        monkeypatch.setattr(engine_mod, "run_tail", boom)
        resp = self._post(client, api_key, delegated)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["reply"]["text"] == T.H_ERROR
        assert [a["text"] for a in body["actions"]] == [T.H_ERROR]

    def test_a_failure_after_the_answer_was_composed_still_sends_the_answer(
        self, client, api_key, delegated, monkeypatch
    ) -> None:
        def boom(*a, **k):
            raise RuntimeError("customer asks write failed")

        monkeypatch.setattr(engine_mod, "_record_customer_asks", boom)
        resp = self._post(client, api_key, delegated)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        reply = body["reply"]["text"]
        T.assert_no_banned_text(reply)
        assert reply != T.H_ERROR, "the composed answer must be sent, the failure only logged"
        assert [a["text"] for a in body["actions"] if a["kind"] == "send_message"] == [reply]


# --------------------------------------------------------------------------- #
# AC-1h contact not found at received: one re-read, then H-ERROR
# --------------------------------------------------------------------------- #


def _not_found():
    from fastapi import HTTPException

    return HTTPException(status_code=404, detail="Respond contact not found for respond_io_id='x'.")


def test_ac1h_a_contact_that_appears_on_the_reread_gets_a_normal_answer(
    session_factory, seeded, stub_parser, stub_access, monkeypatch
) -> None:
    from app.services import conversation_variables_service as cvs

    real = cvs.get_for_contact
    calls: list[int] = []

    def flaky(db, *, respond_io_id):
        calls.append(1)
        if len(calls) == 1:
            raise _not_found()
        return real(db, respond_io_id=respond_io_id)

    monkeypatch.setattr(cvs, "get_for_contact", flaky)
    monkeypatch.setattr("time.sleep", lambda s: None)
    stub_parser()
    stub_access()
    result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
    assert result.status != "failed", result.error
    assert len(calls) >= 2
    T.assert_no_banned_text(result.reply["text"])
    assert result.reply["text"] != T.H_ERROR


def test_ac1h_a_contact_still_missing_says_h_error(session_factory, stub_parser, stub_access, monkeypatch) -> None:
    from app.services import conversation_variables_service as cvs

    def missing(db, *, respond_io_id):
        raise _not_found()

    monkeypatch.setattr(cvs, "get_for_contact", missing)
    monkeypatch.setattr("time.sleep", lambda s: None)
    stub_parser()
    stub_access()
    result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
    assert result.reply["text"] == T.H_ERROR
    row = _row(session_factory, result.turn_id)
    assert row.status == "failed" and "Respond contact not found" in row.error


# --------------------------------------------------------------------------- #
# AC-2 honest outcome per fetch reason (compose)
# --------------------------------------------------------------------------- #


def _fail_env(error: str, **over: Any) -> dict[str, Any]:
    env = sfp._empty_section(CODE, tool_has_result=False, tool_ran=True)
    env.update({"error": error, **over})
    return env


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ("the described set qualifies nothing", T.AC2_NONE_FOUND.format(label="stock", subject=CODE)),
        (
            "HTTP 422 subject_required: This report needs a subject: give at least one of product_code, "
            "customer_ids, customer_query or brand_ids",
            T.AC2_ASK_SUBJECT.format(label="stock"),
        ),
        (
            "attachments are not sent for a held set of 201 products (over the attachment cap)",
            T.AC2_ASK_PRODUCT.format(label="stock"),
        ),
        ("HTTP 403 customer_not_permitted", T.AC2_NOT_PERMITTED),
        ("MCP tool crm_inventory timed out after 10s", T.AC2_COULD_NOT_FETCH.format(label="stock")),
    ],
    ids=["ac2a_empty_set", "ac2b_subject_required", "ac2c_attachment_cap", "ac2e_not_permitted", "ac2d_timeout_text"],
)
def test_ac2_each_fetch_reason_gets_its_own_reply(error: str, expected: str) -> None:
    out = sfp._compose(_fail_env(error))
    assert expected in out, out
    T.assert_no_banned_text(out)
    if "could not fetch" not in expected:
        assert "could not fetch" not in out, f"a specific reason must not read as a generic fetch failure: {out}"


# AC-2d: one retry of the same MCP call, then the could-not-fetch text.


def _mcp_harness(monkeypatch, outcomes: list):
    from app.services import ai_assistant_service
    from app.services.chatbot.lanes.business import services as svc
    from app.services.chatbot.lanes.business.fetch import CHATBOT_READ_ONLY_TOOLS

    tool = sorted(CHATBOT_READ_ONLY_TOOLS)[0]
    calls: list[str] = []

    class FakeClient:
        def __init__(self, url, timeout_seconds=10):
            pass

        def call_tool(self, name, args):
            calls.append(name)
            outcome = outcomes[min(len(calls) - 1, len(outcomes) - 1)]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    monkeypatch.setattr(ai_assistant_service, "MCPRuntimeClient", FakeClient)
    return svc._mcp_call(None), tool, calls


def test_ac2d_a_timed_out_mcp_call_is_retried_once_then_succeeds(monkeypatch) -> None:
    call, tool, calls = _mcp_harness(monkeypatch, [TimeoutError("timed out"), json.dumps({"ok": True})])
    assert call(tool, {}) == {"ok": True}
    assert len(calls) == 2


def test_ac2d_a_still_timing_out_mcp_call_is_tried_exactly_twice(monkeypatch) -> None:
    call, tool, calls = _mcp_harness(monkeypatch, [TimeoutError("timed out")])
    with pytest.raises(TimeoutError):
        call(tool, {})
    assert len(calls) == 2


# --------------------------------------------------------------------------- #
# AC-3 price tag request portal link
# --------------------------------------------------------------------------- #


def test_ac3_the_portal_link_builder_accepts_price_tag_request(session_factory) -> None:
    from app.services.portal_service import PortalService

    url = PortalService(session_factory()).build_portal_url(
        "ZZT-no-such-token", "https://crm.example.test", "price_tag_request"
    )
    assert "type=price_tag_request" in url


def test_ac3_the_parser_form_target_includes_price_tag_request() -> None:
    from typing import get_args

    from app.schemas import ai_semantic_parser as sch

    assert "price_tag_request" in get_args(sch.FormTarget)
    assert "price_tag_request" in _schema_dump(sch)


def _schema_dump(sch) -> str:
    return json.dumps(
        {k: v for k, v in vars(sch).items() if isinstance(v, dict)}, default=str
    )


def test_ac3_the_portal_tool_offers_price_tag_request() -> None:
    from app.services.mcp_tool_capability_service import TOOL_INTENTS

    intent = TOOL_INTENTS["crm_portal_link_get"]
    assert "price_tag_request" in intent.description


# --------------------------------------------------------------------------- #
# AC-4 translations
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("english", T.NEW_EN_TEXTS)
def test_ac4_every_new_text_has_ms_and_zh(english: str) -> None:
    entry = label_catalog.LABELS.get(english)
    assert entry, f"no label_catalog entry for {english!r}"
    for lang in ("ms", "zh"):
        assert entry.get(lang, "").strip() and entry[lang] != english, (lang, english)
        assert english in label_catalog.defaults(lang), (lang, english)
    assert english in label_catalog.INLINE
