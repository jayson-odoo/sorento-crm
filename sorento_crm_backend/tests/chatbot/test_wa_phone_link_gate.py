"""WA-USERNAME-CONTACTS engine gate (red first). UAC WU1-WU10, WU15-WU17; plan test list 5-13.

The gate sits in `engine.run_turn` before the AI-allowed gate. Respond.io is a recording fake
(`wa_phone_link.respond_client` is the one seam) and the template send is patched at
`respond_messaging_service.send_template_for_use_case`. Nothing reaches the network, an LLM or MCP.
"""
from __future__ import annotations

import copy
import itertools
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest
from sqlalchemy import text

from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot import engine as engine_mod

from tests.chatbot.test_engine import CONTACT_ID, _envelope, seeded, stub_access, stub_parser  # noqa: F401

pytestmark = pytest.mark.usefixtures("_no_real_mcp_calls", "_stub_casual_llm")

PHONE_ID = 900000003
E164 = "60100000001"
PHONE_KINDS = {"phone_ask", "phone_linked", "phone_ignored", "phone_handoff"}
_mid = itertools.count(1)

TAP = {
    "event_type": "message.received",
    "contact": {"id": CONTACT_ID, "phone": None, "firstName": "CONTACT B"},
    "message": {
        "messageId": 1700000000000001,
        "contactId": CONTACT_ID,
        "traffic": "incoming",
        "timestamp": 1700000000000,
        "sender": {"source": "contact"},
        "message": {
            "type": "contact",
            "contact": {
                "cId": 1,
                "phone": "+60100000001",
                "origin": "contact_request",
                "payload": None,
                "firstName": "CONTACT A",
            },
        },
    },
    "channel": {"source": "whatsapp", "meta": {"wa_id": "60100000001", "user_id": "MY.0000000000000001"}},
}


def _body(kind: str = "tap", text_: str = "hello", mid: str | None = None) -> dict[str, Any]:
    body = copy.deepcopy(TAP)
    body["message"]["messageId"] = mid or f"WU-msg-{next(_mid)}"
    inner = body["message"]["message"]
    if kind == "text":
        body["message"]["message"] = {"type": "text", "text": text_}
    elif kind == "shared":
        inner["contact"].update({"phone": "+60100000002", "origin": "other"})
    elif kind == "bare":
        inner["contact"]["phone"] = "60100000001"
    return body


_KEEP = object()


def _env(
    kind: str = "tap",
    *,
    text_: str = "hello",
    mid: str | None = None,
    contact: dict | None = None,
    source: Any = _KEEP,
    **kw,
):
    body = _body(kind, text_, mid)
    if kind in ("tap", "bare") and "ingress" not in kw:
        kw["ingress"] = "respond_webhook"  # the CRM's own signed webhook (contracts.DIRECT_INGRESS)
    if source is None:
        body["channel"].pop("source", None)
    elif source is not _KEEP:
        body["channel"]["source"] = source
    return _envelope(
        message=body,
        contact=contact or {"id": CONTACT_ID, "phone": None, "firstName": "CONTACT B", "custom_fields": []},
        **kw,
    )


class World:
    def __init__(self):
        self.calls: list[tuple] = []
        self.sends: list[tuple[str, str]] = []
        self.template = "ok"  # or "skipped"
        self.phone_contact_id: int | None = PHONE_ID
        self.merge_error: Exception | None = None
        self.merge_survivor = "phone"  # "phone" | "turn"
        self.order: list[str] = []
        self.lookup_fails_after_merge = False
        self.send_error: Exception | None = None
        self.template_error: Exception | None = None
        self.messages: list[tuple[str, str]] = []
        self.comments: list[tuple[str, str]] = []

    def client(self):
        world = self

        class _C:
            def get_contact_by_phone(self, phone):
                world.order.append("client"); world.calls.append(("lookup", phone))
                if world.lookup_fails_after_merge and world.merges():
                    raise RuntimeError("zzt second lookup failed")
                if world.phone_contact_id is None:
                    req = httpx.Request("GET", "https://api.example.test/x")
                    raise httpx.HTTPStatusError("nf", request=req, response=httpx.Response(404, request=req))
                return {"id": world.phone_contact_id}

            def merge_contacts(self, ids):
                world.order.append("client"); world.calls.append(("merge", [int(i) for i in ids]))
                if world.merge_error:
                    raise world.merge_error
                if world.merge_survivor == "none":
                    return {}
                return {"contactId": PHONE_ID if world.merge_survivor == "phone" else CONTACT_ID}

            def send_message(self, identifier, text_):
                world.order.append("client"); world.calls.append(("send_message", str(identifier), text_))
                if world.send_error is not None:
                    raise world.send_error
                world.messages.append((str(identifier), text_))
                return {}

            def create_comment(self, identifier, text_):
                world.order.append("client"); world.calls.append(("create_comment", str(identifier), text_))
                world.comments.append((str(identifier), text_))
                return {}

            def update_contact(self, ident, payload):
                world.order.append("client"); world.calls.append(("put", str(ident), payload))
                return {}

        return _C()

    def merges(self):
        return [c for c in self.calls if c[0] == "merge"]


@pytest.fixture()
def world(monkeypatch):
    """Installed inside the test's own setup path; the imports are lazy so a missing module fails per test."""
    return World()


def _install(world: World, monkeypatch):
    from app.services import respond_messaging_service, wa_phone_link

    monkeypatch.setattr(wa_phone_link, "respond_client", lambda db: world.client())

    def fake_send(db, *, identifier, use_case, context_vars):
        if world.template == "skipped":
            raise respond_messaging_service.TemplateSendSkipped(use_case, "not mapped")
        if world.template_error is not None:
            raise world.template_error
        world.order.append("template")
        world.sends.append((str(identifier), use_case))
        return {}

    monkeypatch.setattr(respond_messaging_service, "send_template_for_use_case", fake_send)


@pytest.fixture()
def parser_calls(stub_parser, stub_access):
    calls: list[Any] = []
    stub_parser(on_call=calls.append)
    stub_access()
    return calls


def _run(session_factory, envelope):
    return engine_mod.run_turn(envelope, session_factory=session_factory)


VERIFIED = "Phone number verified, you may start using the AI"


def _seed_turn(session_factory, branch_kind: str, *, hours_ago: float = 1.0, is_test: bool = False) -> None:
    db = session_factory()
    db.add(
        ChatbotTurn(
            contact_respond_id=str(CONTACT_ID),
            message_id=f"seed-{next(_mid)}",
            envelope={},
            is_test=is_test,
            status="done",
            stage="received",
            branch_kind=branch_kind,
            created_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
        )
    )
    db.commit()


def _seed_phone_row(session_factory, *, allowed: bool) -> None:
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars, chatbot_allowed) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb), :a)"
        ),
        {"cid": str(PHONE_ID), "phone": f"+{E164}", "sv": json.dumps({"variables": {}}), "a": allowed},
    )
    db.commit()


def _row(session_factory, result) -> ChatbotTurn:
    return session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).first()


# ---------------------------------------------------------------- 5. card from a linked contact


@pytest.mark.parametrize("kind", ["tap", "shared", "bare"])
def test_wu2_card_from_linked_contact_is_ignored(session_factory, seeded, parser_calls, world, monkeypatch, kind):
    _install(world, monkeypatch)
    result = _run(session_factory, _env(kind))
    assert result.branch_kind == "phone_ignored"
    assert result.actions == []
    assert parser_calls == []
    assert world.calls == [] and world.sends == []
    assert _row(session_factory, result).branch_kind == "phone_ignored"


def test_wu2_card_from_linked_contact_with_ai_off_is_still_ignored(
    session_factory, seeded, parser_calls, world, monkeypatch
):
    _install(world, monkeypatch)
    session_factory().execute(text("UPDATE respond_contacts SET chatbot_allowed = false"))
    session_factory().commit()
    result = _run(session_factory, _env("tap"))
    assert result.branch_kind == "phone_ignored"
    assert world.calls == [] and world.sends == []


# ---------------------------------------------------------------- 6. ask


def test_wu6_text_from_unknown_phoneless_gets_the_ask(session_factory, parser_calls, world, monkeypatch):
    _install(world, monkeypatch)
    result = _run(session_factory, _env("text", text_="price for SRTWC8517"))
    assert result.branch_kind == "phone_ask"
    assert world.sends == [(str(CONTACT_ID), "wa_phone_share")]
    assert parser_calls == []
    assert world.calls == []
    row = _row(session_factory, result)
    assert row.status == "done" and row.branch_kind == "phone_ask"


def test_wu9_typed_phone_number_is_never_accepted(session_factory, parser_calls, world, monkeypatch):
    _install(world, monkeypatch)
    result = _run(session_factory, _env("text", text_="+60100000001"))
    assert result.branch_kind == "phone_ask"
    assert world.sends == [(str(CONTACT_ID), "wa_phone_share")]
    assert world.calls == []
    assert parser_calls == []


def test_wu3_the_ask_turn_never_reaches_a_business_answer(session_factory, parser_calls, world, monkeypatch):
    _install(world, monkeypatch)
    result = _run(session_factory, _env("text", text_="price for SRTWC8517"))
    assert result.branch_kind in PHONE_KINDS
    assert "business" not in str(result.branch_kind)
    assert result.actions == []
    assert world.messages == []


# ---------------------------------------------------------------- 7. cap


def test_wu7_fourth_ask_becomes_a_handoff_then_silence(session_factory, parser_calls, world, monkeypatch):
    _install(world, monkeypatch)
    for h in (3, 2, 1):
        _seed_turn(session_factory, "phone_ask", hours_ago=h)
    fourth = _run(session_factory, _env("text"))
    assert fourth.branch_kind == "phone_handoff"
    assert fourth.actions == []
    assert len(world.comments) == 1 and world.comments[0][0] == str(CONTACT_ID)
    assert world.messages == []
    assert world.sends == []
    fifth = _run(session_factory, _env("text"))
    assert fifth.branch_kind == "phone_ignored"
    assert fifth.actions == [] and world.sends == []
    assert len(world.comments) == 1 and world.messages == []
    assert parser_calls == []


def test_wu7_asks_older_than_24h_do_not_count(session_factory, parser_calls, world, monkeypatch):
    _install(world, monkeypatch)
    for h in (30, 28, 26):
        _seed_turn(session_factory, "phone_ask", hours_ago=h)
    result = _run(session_factory, _env("text"))
    assert result.branch_kind == "phone_ask"
    assert world.sends == [(str(CONTACT_ID), "wa_phone_share")]


def test_wu7_test_turns_do_not_count_toward_the_cap(session_factory, parser_calls, world, monkeypatch):
    _install(world, monkeypatch)
    for h in (3, 2, 1):
        _seed_turn(session_factory, "phone_ask", hours_ago=h, is_test=True)
    result = _run(session_factory, _env("text"))
    assert result.branch_kind == "phone_ask"


# ---------------------------------------------------------------- 8. not mapped


def test_wu8_unmapped_template_hands_off_once(session_factory, parser_calls, world, monkeypatch):
    _install(world, monkeypatch)
    world.template = "skipped"
    first = _run(session_factory, _env("text"))
    assert first.branch_kind == "phone_handoff"
    assert first.actions == []
    assert len(world.comments) == 1 and world.comments[0][0] == str(CONTACT_ID)
    assert world.messages == []
    second = _run(session_factory, _env("text"))
    assert second.branch_kind == "phone_ignored"
    assert second.actions == []
    assert len(world.comments) == 1
    assert parser_calls == []


# ---------------------------------------------------------------- 9. hand-shared card


def test_wu10_hand_shared_card_from_unknown_is_answered_by_the_ask(
    session_factory, parser_calls, world, monkeypatch
):
    _install(world, monkeypatch)
    result = _run(session_factory, _env("shared"))
    assert result.branch_kind == "phone_ask"
    assert world.sends == [(str(CONTACT_ID), "wa_phone_share")]
    assert world.calls == []
    assert world.merges() == []
    assert parser_calls == []


# ---------------------------------------------------------------- 10. accepted tap


@pytest.mark.parametrize("kind", ["tap", "bare"])
def test_wu15_link_ok_and_ai_allowed_sends_the_verified_line(
    session_factory, parser_calls, world, monkeypatch, kind
):
    _install(world, monkeypatch)
    _seed_phone_row(session_factory, allowed=True)
    result = _run(session_factory, _env(kind))
    assert result.branch_kind == "phone_linked"
    assert world.merges() == [("merge", [PHONE_ID, CONTACT_ID])]
    assert result.actions == []
    assert world.messages == [(str(PHONE_ID), VERIFIED)]
    assert parser_calls == []


def test_wu15_phone_set_case_sends_the_verified_line_to_the_turn_contact(
    session_factory, parser_calls, world, monkeypatch
):
    _install(world, monkeypatch)
    world.phone_contact_id = None
    _seed_phone_row(session_factory, allowed=True)
    result = _run(session_factory, _env("tap"))
    assert result.branch_kind == "phone_linked"
    assert result.actions == []
    assert world.merges() == []
    assert world.messages == [(str(CONTACT_ID), VERIFIED)]


def test_wu15_link_ok_and_ai_off_tells_staff_only(session_factory, parser_calls, world, monkeypatch):
    _install(world, monkeypatch)
    _seed_phone_row(session_factory, allowed=False)
    result = _run(session_factory, _env("tap"))
    assert result.branch_kind == "phone_linked"
    assert result.actions == []
    assert world.messages == []
    assert len(world.comments) == 1 and world.comments[0][0] == str(PHONE_ID)
    assert world.merges() == [("merge", [PHONE_ID, CONTACT_ID])]


def test_wu16_link_failure_hands_off_without_a_customer_line(session_factory, parser_calls, world, monkeypatch):
    _install(world, monkeypatch)
    _seed_phone_row(session_factory, allowed=True)
    req = httpx.Request("POST", "https://api.example.test/v2/contact/merge")
    world.merge_error = httpx.HTTPStatusError("boom", request=req, response=httpx.Response(500, request=req))
    result = _run(session_factory, _env("tap"))
    assert result.branch_kind == "phone_handoff"
    assert result.actions == []
    assert world.messages == []
    assert len(world.comments) == 1 and world.comments[0][0] == str(CONTACT_ID)
    row = session_factory().execute(
        text("SELECT respond_io_id FROM respond_contacts WHERE phone_number = :p"), {"p": f"+{E164}"}
    ).scalar()
    assert row == str(PHONE_ID)


# ---------------------------------------------------------------- 11. phone in the envelope


def test_wu4_unknown_with_phone_in_envelope_is_not_this_flow(session_factory, parser_calls, world, monkeypatch):
    _install(world, monkeypatch)
    contact = {"id": CONTACT_ID, "phone": "+60100000005", "firstName": "CONTACT C", "custom_fields": []}
    for kind in ("text", "tap"):
        result = _run(session_factory, _env(kind, contact=contact))
        assert result.branch_kind not in PHONE_KINDS
        assert result.branch_kind == "ai_not_allowed"
    assert world.calls == [] and world.sends == []
    assert parser_calls == []


# ---------------------------------------------------------------- 12. duplicate delivery


def test_wu17_the_same_webhook_twice_merges_once(session_factory, parser_calls, world, monkeypatch):
    _install(world, monkeypatch)
    _seed_phone_row(session_factory, allowed=True)
    first = _run(session_factory, _env("tap", mid="WU-dup-1"))
    second = _run(session_factory, _env("tap", mid="WU-dup-1"))
    assert first.branch_kind == "phone_linked"
    assert second.duplicate is True
    assert len(world.merges()) == 1


# ---------------------------------------------------------------- 13. dry run


@pytest.mark.parametrize("kind", ["text", "shared", "tap"])
def test_wu5_a_test_turn_makes_no_respond_call(session_factory, parser_calls, world, monkeypatch, kind):
    _install(world, monkeypatch)
    _seed_phone_row(session_factory, allowed=True)
    result = _run(session_factory, _env(kind, is_test=True))
    assert result.is_test is True
    assert result.branch_kind in PHONE_KINDS
    assert world.calls == []
    assert world.sends == []
    assert world.messages == [] and world.comments == []
    assert result.actions == []
    assert parser_calls == []


def test_wu5_a_test_turn_takes_the_same_decision_as_live(session_factory, parser_calls, world, monkeypatch):
    _install(world, monkeypatch)
    result = _run(session_factory, _env("text", is_test=True))
    assert result.branch_kind == "phone_ask"
    assert result.actions == []
    assert world.calls == [] and world.sends == []


# ---------------------------------------------------------------- 1. never the parser


def test_wu1_no_card_reaches_the_parser_whoever_sends_it(session_factory, seeded, parser_calls, world, monkeypatch):
    _install(world, monkeypatch)
    for kind in ("tap", "shared"):
        result = _run(session_factory, _env(kind))
        assert result.branch_kind in PHONE_KINDS
    assert parser_calls == []


# ---------------------------------------------------------------- WU20 WhatsApp only


@pytest.mark.parametrize("source", ["wechat", "facebook"])
@pytest.mark.parametrize("kind", ["text", "tap"])
def test_wu20_non_whatsapp_unknown_phoneless_closes_as_today(
    session_factory, parser_calls, world, monkeypatch, source, kind
):
    _install(world, monkeypatch)
    result = _run(session_factory, _env(kind, source=source))
    assert result.branch_kind == "ai_not_allowed"
    assert result.actions == []
    assert world.sends == []
    assert world.calls == []
    assert parser_calls == []


@pytest.mark.parametrize("source", ["whatsapp_cloud", None])
def test_wu20_whatsapp_cloud_and_absent_source_take_the_phone_flow(
    session_factory, parser_calls, world, monkeypatch, source
):
    _install(world, monkeypatch)
    result = _run(session_factory, _env("text", source=source))
    assert result.branch_kind == "phone_ask"
    assert world.sends == [(str(CONTACT_ID), "wa_phone_share")]


# ---------------------------------------------------------------- WU21 accepted tap always retries


def test_wu21_accepted_tap_links_even_with_a_handoff_in_the_window(
    session_factory, parser_calls, world, monkeypatch
):
    _install(world, monkeypatch)
    _seed_phone_row(session_factory, allowed=True)
    _seed_turn(session_factory, "phone_handoff", hours_ago=1)
    result = _run(session_factory, _env("tap"))
    assert result.branch_kind == "phone_linked"
    assert [k for k in world.calls if k[0] == "lookup"]
    assert world.merges() == [("merge", [PHONE_ID, CONTACT_ID])]
    assert world.messages == [(str(PHONE_ID), VERIFIED)]


def test_wu21_a_second_failed_link_in_the_window_writes_no_second_comment(
    session_factory, parser_calls, world, monkeypatch
):
    _install(world, monkeypatch)
    _seed_phone_row(session_factory, allowed=True)
    req = httpx.Request("POST", "https://api.example.test/v2/contact/merge")
    world.merge_error = httpx.HTTPStatusError("boom", request=req, response=httpx.Response(500, request=req))
    first = _run(session_factory, _env("tap"))
    second = _run(session_factory, _env("tap"))
    assert first.branch_kind == "phone_handoff"
    assert second.branch_kind in {"phone_handoff", "phone_ignored"}
    assert len(world.merges()) == 2
    assert len(world.comments) == 1
    assert world.messages == []


# ---------------------------------------------------------------- WU10/WU22 signed ingress only


@pytest.mark.parametrize("ingress", ["webhook", "poller", "retry"])
@pytest.mark.parametrize("kind", ["tap", "bare"])
def test_wu22_a_tap_that_did_not_arrive_signed_is_never_linked(
    session_factory, parser_calls, world, monkeypatch, ingress, kind
):
    _install(world, monkeypatch)
    _seed_phone_row(session_factory, allowed=True)
    result = _run(session_factory, _env(kind, ingress=ingress))
    assert result.branch_kind == "phone_ask"
    assert world.calls == []
    assert world.sends == [(str(CONTACT_ID), "wa_phone_share")]
    assert parser_calls == []


def test_wu22_the_same_tap_over_the_signed_webhook_is_linked(session_factory, parser_calls, world, monkeypatch):
    _install(world, monkeypatch)
    _seed_phone_row(session_factory, allowed=True)
    result = _run(session_factory, _env("tap", ingress="respond_webhook"))
    assert result.branch_kind == "phone_linked"


def test_wu10_a_signed_card_without_wa_id_is_not_accepted(session_factory, parser_calls, world, monkeypatch):
    _install(world, monkeypatch)
    env = _env("tap", ingress="respond_webhook")
    del env.message["channel"]["meta"]["wa_id"]
    result = _run(session_factory, env)
    assert result.branch_kind == "phone_ask"
    assert world.calls == []


# ---------------------------------------------------------------- survivor named by the merge response


def test_wu12_verified_line_goes_to_the_survivor_the_merge_response_names(
    session_factory, parser_calls, world, monkeypatch
):
    _install(world, monkeypatch)
    world.merge_survivor = "turn"
    _seed_phone_row(session_factory, allowed=True)
    result = _run(session_factory, _env("tap"))
    assert result.branch_kind == "phone_linked"
    assert world.messages == [(str(CONTACT_ID), VERIFIED)]
    rid = session_factory().execute(
        text("SELECT respond_io_id FROM respond_contacts WHERE phone_number = :p"), {"p": f"+{E164}"}
    ).scalar()
    assert rid == str(CONTACT_ID)


# ---------------------------------------------------------------- 7. origin guard at the engine


def test_wu10_signed_card_with_origin_other_and_matching_wa_id_is_not_linked(
    session_factory, parser_calls, world, monkeypatch
):
    _install(world, monkeypatch)
    _seed_phone_row(session_factory, allowed=True)
    env = _env("tap", ingress="respond_webhook")
    env.message["message"]["message"]["contact"]["origin"] = "other"
    assert env.message["channel"]["meta"]["wa_id"] == "60100000001"
    result = _run(session_factory, env)
    assert result.branch_kind == "phone_ask"
    assert world.calls == []


# ---------------------------------------------------------------- WU25 drain order and failure


def _queued_row(session_factory, envelope) -> str:
    db = session_factory()
    row = ChatbotTurn(
        contact_respond_id=str(CONTACT_ID),
        message_id=str(envelope.message["message"]["messageId"]),
        ingress=envelope.ingress,
        envelope=envelope.model_dump(mode="json"),
        status="queued",
    )
    db.add(row)
    db.commit()
    return str(row.id)


@pytest.mark.parametrize("exc_name", ["ClaimLost", "TurnYielded"])
@pytest.mark.parametrize("kind", ["text", "tap"])
def test_wu25_a_lost_or_yielded_claim_makes_no_respond_call(
    session_factory, parser_calls, world, monkeypatch, exc_name, kind
):
    from app.services.chatbot import inbox_queue

    _install(world, monkeypatch)
    _seed_phone_row(session_factory, allowed=True)
    env = _env(kind)
    turn_id = _queued_row(session_factory, env)

    def _gone(tid=None):
        raise getattr(inbox_queue, exc_name)()

    monkeypatch.setattr(inbox_queue, "checkpoint", _gone)
    with pytest.raises((inbox_queue.ClaimLost, inbox_queue.TurnYielded)):
        engine_mod.run_turn(env, session_factory=session_factory, offload=False, queued_turn_id=turn_id)
    assert world.calls == []
    assert world.sends == []
    assert world.order == []


@pytest.mark.parametrize("kind", ["text", "tap"])
def test_wu25_checkpoint_runs_before_the_first_respond_call(
    session_factory, parser_calls, world, monkeypatch, kind
):
    from app.services.chatbot import inbox_queue

    _install(world, monkeypatch)
    _seed_phone_row(session_factory, allowed=True)
    env = _env(kind)
    turn_id = _queued_row(session_factory, env)
    monkeypatch.setattr(inbox_queue, "checkpoint", lambda tid=None: world.order.append(f"checkpoint:{tid}"))
    result = engine_mod.run_turn(env, session_factory=session_factory, offload=False, queued_turn_id=turn_id)
    assert result.branch_kind in PHONE_KINDS
    assert world.order, "the phone flow made no call at all"
    assert world.order[0] == f"checkpoint:{turn_id}", world.order


def test_wu25_an_unexpected_error_closes_the_turn_failed_not_processing(
    session_factory, parser_calls, world, monkeypatch
):
    from app.services import wa_phone_link

    _install(world, monkeypatch)

    def _boom(body):
        raise RuntimeError("zzt unexpected")

    monkeypatch.setattr(wa_phone_link, "accepted_card_phone", _boom)
    result = None
    try:
        result = _run(session_factory, _env("tap", mid="WU-boom-1"))
    except Exception:
        pass
    if result is not None:
        assert result.actions == []
    rows = (
        session_factory()
        .query(ChatbotTurn)
        .filter(ChatbotTurn.contact_respond_id == str(CONTACT_ID), ChatbotTurn.message_id == "WU-boom-1")
        .all()
    )
    assert len(rows) == 1
    assert rows[0].status == "failed", rows[0].status
    assert rows[0].finished_at is not None
    assert rows[0].error
    monkeypatch.undo()
    _install(world, monkeypatch)
    second = _run(session_factory, _env("tap", mid="WU-boom-1"))
    assert not (second.duplicate and second.status == "processing")


# ---------------------------------------------------------------- WU24 outbox rows


def _logs(session_factory):
    from app.models.integration import IntegrationLog

    return (
        session_factory()
        .query(IntegrationLog)
        .filter(IntegrationLog.integration_channel == "respond_io")
        .order_by(IntegrationLog.created_at)
        .all()
    )


def _no_phone_in(rows):
    for r in rows:
        blob = " ".join(
            str(getattr(r, f) or "")
            for f in ("endpoint", "request_headers", "request_payload", "response_payload", "error_message", "external_reference")
        )
        assert E164 not in blob, blob


def test_wu24_a_successful_ask_writes_an_outbox_row(session_factory, parser_calls, world, monkeypatch):
    _install(world, monkeypatch)
    result = _run(session_factory, _env("text"))
    assert result.branch_kind == "phone_ask"
    rows = _logs(session_factory)
    assert len(rows) == 1 and rows[0].status == "success"
    _no_phone_in(rows)


def test_wu24_a_failed_ask_send_writes_a_failed_row_with_the_phone_masked(
    session_factory, parser_calls, world, monkeypatch
):
    _install(world, monkeypatch)
    world.template_error = RuntimeError(f"zzt respond down for +{E164}")
    _run(session_factory, _env("text"))
    rows = _logs(session_factory)
    assert len(rows) == 1 and rows[0].status == "failed"
    _no_phone_in(rows)


def test_wu24_a_successful_verified_line_writes_an_outbox_row(
    session_factory, parser_calls, world, monkeypatch
):
    _install(world, monkeypatch)
    _seed_phone_row(session_factory, allowed=True)
    result = _run(session_factory, _env("tap"))
    assert result.branch_kind == "phone_linked"
    rows = _logs(session_factory)
    assert len(rows) == 1 and rows[0].status == "success"
    _no_phone_in(rows)


def test_wu24_a_failed_verified_line_writes_a_failed_row(session_factory, parser_calls, world, monkeypatch):
    _install(world, monkeypatch)
    _seed_phone_row(session_factory, allowed=True)
    world.send_error = RuntimeError(f"zzt send failed for +{E164}")
    _run(session_factory, _env("tap"))
    rows = _logs(session_factory)
    assert len(rows) == 1 and rows[0].status == "failed"
    _no_phone_in(rows)


# ---------------------------------------------------------------- WU26 comment to the survivor


@pytest.mark.parametrize("survivor,expected", [("phone", PHONE_ID), ("turn", CONTACT_ID)])
def test_wu26_crm_write_failing_after_a_merge_comments_on_the_survivor(
    session_factory, parser_calls, world, monkeypatch, survivor, expected
):
    from app.services.contact_service import ContactService

    _install(world, monkeypatch)
    world.merge_survivor = survivor

    def _boom(self, data):
        raise RuntimeError("zzt crm write failed")

    monkeypatch.setattr(ContactService, "create_contact", _boom)
    result = _run(session_factory, _env("tap"))
    assert result.branch_kind == "phone_handoff"
    assert world.merges() == [("merge", [PHONE_ID, CONTACT_ID])]
    assert len(world.comments) == 1
    assert world.comments[0][0] == str(expected)
    assert world.messages == []


# ---------------------------------------------------------------- round 4


def test_wu24_an_ask_skipped_for_no_template_writes_one_skipped_row(
    session_factory, parser_calls, world, monkeypatch
):
    _install(world, monkeypatch)
    world.template = "skipped"
    result = _run(session_factory, _env("text"))
    assert result.branch_kind == "phone_handoff"
    rows = _logs(session_factory)
    skipped = [r for r in rows if r.status == "skipped"]
    assert len(skipped) == 1, [r.status for r in rows]
    _no_phone_in(rows)


def test_wu18_an_unexpected_error_leaks_no_full_phone_to_logs_or_the_turn_row(
    session_factory, parser_calls, world, monkeypatch, caplog
):
    import logging

    from app.services import wa_phone_link

    _install(world, monkeypatch)
    caplog.set_level(logging.DEBUG)

    def _boom(body):
        raise RuntimeError(f"zzt crm phone query failed for +{E164} and {E164}")

    monkeypatch.setattr(wa_phone_link, "accepted_card_phone", _boom)
    try:
        _run(session_factory, _env("tap", mid="WU-leak-1"))
    except Exception:
        pass
    assert E164 not in caplog.text
    rows = (
        session_factory()
        .query(ChatbotTurn)
        .filter(ChatbotTurn.contact_respond_id == str(CONTACT_ID), ChatbotTurn.message_id == "WU-leak-1")
        .all()
    )
    assert len(rows) == 1
    assert E164 not in str(rows[0].error or "")
    assert E164 not in json.dumps(rows[0].trace or [])


def test_wu26_no_contactid_and_a_failing_second_lookup_comments_on_the_phone_contact(
    session_factory, parser_calls, world, monkeypatch
):
    _install(world, monkeypatch)
    world.merge_survivor = "none"
    world.lookup_fails_after_merge = True
    _seed_phone_row(session_factory, allowed=True)
    result = _run(session_factory, _env("tap"))
    assert result.branch_kind == "phone_handoff"
    assert len(world.merges()) == 1
    assert len(world.comments) == 1
    assert world.comments[0][0] == str(PHONE_ID)
    assert world.messages == []
