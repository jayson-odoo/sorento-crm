"""Owner hand test 13 Nov on PR #2256 (c51157ab).

F1: "Update <phone> to no access" was recognised as dealer access, the model looked the person up
(`crm_contacts_find`, found) and then answered instead of proposing the change, so the flow showed the fixed
"Tell me the person's phone, Business Owner or Employee, the company ... and the dealer" line. A revoke needs
none of those: the found contact's accounts are unlinked (its AI replies go off with the last link, C4).
Expected: one card that removes the access.

F2: the next message on the same thread got "I am still working on your earlier message" after the first
reply had finished: the busy lock must be free once a dealer-flow turn returns.

Semantic only (owner rule): the user's words are never read by code; the model is held to the found contact
by the loop, the way the flow already refuses an answer before any dealer-access tool ran. Phones are the
agreed fake shape (public repo).
"""
from __future__ import annotations

import pytest
import redis

from app.config import settings
from app.services.chatbot.agent import loop as agent_loop
from tests.chatbot.agent.test_agent_writes import answer_, round_of, run_turn, tc
from tests.chatbot.agent.test_dealer_access_agent import (  # noqa: F401  (fixtures are used by name)
    UPDATE,
    ai_on,
    db,
    dealer,
    make_world,
    state,
)

FIND = "crm_contacts_find"
CARD = "I will make these changes when you confirm"

#: The owner's phrasing and its variants (EN + Malay, one person and two).
ONE = {
    "en": "Update {p} to no access",
    "ms": "Tukar {p} kepada tiada akses",
}
TWO = {
    "en": "Remove access for {p} and {q}",
    "ms": "Buang akses untuk {p} dan {q}",
}


def _person(db, w):
    return ai_on(db, dealer(db, w, customers=(w.cust_a,)))


def _tool_replies(provider, call: int) -> list[str]:
    return [m["content"] for m in provider.seen[call]["messages"] if m.get("role") == "tool"]


@pytest.mark.parametrize("lang", list(ONE))
def test_f1_a_found_contact_and_an_answer_is_held_to_the_access_change_once(db, lang):
    w = make_world(db)
    person = _person(db, w)
    script = [
        round_of(tc(FIND, {"phones": [person.phone_number]}, "f1")),
        answer_("Tell me the role and the company."),
        round_of(tc(UPDATE, {"contact_id": person.id, "unlink_customer_ids": [str(w.cust_a.id)]}, "u1")),
        answer_("ok"),
    ]
    result, provider = run_turn(db, w, script, text_=ONE[lang].format(p=person.phone_number), dealer_access=True)

    held = _tool_replies(provider, 2)[-1]
    assert UPDATE in held, f"the answer after a found contact was not held to the access change: {held}"
    assert result.pending_action is not None, result.reply_text
    assert result.reply_text.startswith(CARD), result.reply_text
    assert agent_loop.TELL_ME_REPLY not in result.reply_text


@pytest.mark.parametrize("lang", list(TWO))
def test_f1_two_found_contacts_get_one_card_with_both_changes(db, lang):
    w = make_world(db)
    a, b = _person(db, w), _person(db, w)
    script = [
        round_of(tc(FIND, {"phones": [a.phone_number, b.phone_number]}, "f1")),
        answer_("Which company?"),
        round_of(
            tc(UPDATE, {"contact_id": a.id, "unlink_customer_ids": [str(w.cust_a.id)]}, "u1"),
            tc(UPDATE, {"contact_id": b.id, "unlink_customer_ids": [str(w.cust_a.id)]}, "u2"),
        ),
        answer_("ok"),
    ]
    result, _ = run_turn(
        db, w, script, text_=TWO[lang].format(p=a.phone_number, q=b.phone_number), dealer_access=True
    )

    assert result.pending_action is not None, result.reply_text
    lines = result.pending_action["lines"]
    assert len(lines) == 2 and any(a.phone_number[-4:] in x for x in lines) and any(b.phone_number[-4:] in x for x in lines), lines


def test_f1_the_hold_is_once_a_second_answer_ends_the_turn(db):
    w = make_world(db)
    person = _person(db, w)
    script = [
        round_of(tc(FIND, {"phones": [person.phone_number]}, "f1")),
        answer_("one"),
        answer_("two"),
    ]
    result, provider = run_turn(db, w, script, text_=ONE["en"].format(p=person.phone_number), dealer_access=True)

    assert len(provider.seen) == 3
    assert result.pending_action is None


def test_f1_a_phone_that_is_not_found_is_not_held(db):
    """Nothing to change: the answer stands at once (no extra round)."""
    w = make_world(db)
    script = [round_of(tc(FIND, {"phones": ["0190000999"]}, "f1")), answer_("Not found.")]
    _, provider = run_turn(db, w, script, text_=ONE["en"].format(p="0190000999"), dealer_access=True)

    assert len(provider.seen) == 2


def test_f1_the_access_change_says_a_removal_needs_no_role_company_or_dealer(db):
    from app.services.chatbot.agent import writes

    description = writes.WRITES[UPDATE].schema["function"]["description"]
    assert "remove" in description.lower() and "no role" in description.lower(), description


def test_f1_a_revoke_proposes_the_unlink_and_ai_off_and_confirm_removes_the_access(db):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    person = _person(db, w)
    script = [
        round_of(tc(FIND, {"phones": [person.phone_number]}, "f1")),
        round_of(tc(UPDATE, {"contact_id": person.id, "unlink_customer_ids": [str(w.cust_a.id)]}, "u1")),
        answer_("ok"),
    ]
    result, _ = run_turn(db, w, script, text_=ONE["en"].format(p=person.phone_number), dealer_access=True)
    assert result.pending_action is not None, result.reply_text
    assert "unlinked from" in result.reply_text and "AI replies on -> off" in result.reply_text

    outcome = actions.confirm(db, w.respond_id, result.pending_action["id"], via="console")
    assert outcome.status == "executed", outcome.steps
    after = state(db, person.phone_number)
    assert after["links"] == [] and after["chatbot_allowed"] is False


# ------------------------------------------------------------------ F2: the busy lock after a dealer-flow turn


@pytest.fixture
def redis_up():
    try:
        redis.from_url(settings.redis_url).ping()
    except Exception:  # noqa: BLE001
        pytest.skip("Redis is not reachable")


def _held(contact_key: str) -> bool:
    return bool(redis.from_url(settings.redis_url).exists(f"{agent_loop.BUSY_LOCK_PREFIX}{contact_key}"))


@pytest.mark.parametrize("variant", ["found-then-answer", "not-found", "proposed"])
def test_f2_the_lock_is_free_after_a_dealer_flow_turn_and_the_next_message_runs(db, redis_up, variant):
    w = make_world(db)
    person = _person(db, w)
    first = {
        "found-then-answer": [round_of(tc(FIND, {"phones": [person.phone_number]}, "f1")), answer_("a"), answer_("b")],
        "not-found": [round_of(tc(FIND, {"phones": ["0190000999"]}, "f1")), answer_("a")],
        "proposed": [
            round_of(tc(FIND, {"phones": [person.phone_number]}, "f1")),
            round_of(tc(UPDATE, {"contact_id": person.id, "unlink_customer_ids": [str(w.cust_a.id)]}, "u1")),
            answer_("ok"),
        ],
    }[variant]
    run_turn(db, w, first, text_=ONE["en"].format(p=person.phone_number), dealer_access=True)
    assert not _held(w.respond_id), "the busy lock outlived the turn"

    second, _ = run_turn(db, w, [answer_("Hello.")], text_=f"Phone number {person.phone_number}")
    assert second.reply_text != "I am still working on your earlier message in this chat. Try again in a moment."
    assert not _held(w.respond_id)


# ------------------------------------------------------------------ F2 through the panel (the owner's path)

from tests.chatbot.test_panel_agent_side import (  # noqa: E402,F401  (fixtures are used by name)
    agent_model,
    audit_listeners,
    jev,
    panel_key,
)
from tests.chatbot.test_panel_agent_side import answer_ as panel_answer  # noqa: E402
from tests.chatbot.test_panel_agent_side import round_of as panel_round  # noqa: E402
from tests.chatbot.test_panel_agent_side import tc as panel_tc  # noqa: E402
from tests.chatbot.test_panel_principal import (  # noqa: E402,F401
    grants,
    run_panel,
    staff,
    world,
)
from tests.chatbot.agent.test_router import jev_answer  # noqa: E402


def _side(yes: bool):
    from app.services.llm_provider import ChatResult

    return ChatResult(
        content=f'{{"dealer_access": {"true" if yes else "false"}}}', prompt_tokens=1, completion_tokens=1,
        total_tokens=2, cached_tokens=0, tool_calls=[],
    )


@pytest.mark.parametrize("second_route", ["agent", "chat"])
def test_f2_a_panel_dealer_flow_turn_leaves_the_thread_free_for_the_next_message(
    session_factory, monkeypatch, staff, grants, world, jev, agent_model, redis_up, second_route
):
    from app.services.chatbot.agent.writes import CONTACT_EDIT
    from app.services.chatbot.panel_service import BUSY_REPLY

    grants.add(CONTACT_EDIT)
    jev.answer = jev_answer("agent", 0.95)
    agent_model.set([
        _side(True),
        panel_round(panel_tc(FIND, {"phones": ["0190000998"]}, "f1")),
        panel_answer("Not found."),
    ])
    first = run_panel(session_factory, monkeypatch, staff, "Update 0190000998 to no access")
    assert first.route == "agent" and first.reply_text != BUSY_REPLY, first.reply_text
    assert [c["name"] for c in (first.agent or {}).get("tool_calls") or []] == [FIND], first.agent
    assert not _held(panel_key(staff)), "the busy lock outlived the panel turn"

    jev.answer = jev_answer(second_route, 0.95)
    agent_model.set([_side(False), panel_answer("ZZT next answer.")])
    second = run_panel(session_factory, monkeypatch, staff, "Phone number 0190000998")
    assert second.reply_text != BUSY_REPLY
    assert not _held(panel_key(staff))
