"""CHAT-STATE round 6, S4 (red): an unresolved Subject asks; unplaced tokens are named; the Subject
carries the contact's scope and hidden keys (AC-S4-1, AC-S4-2, AC-S1-11, AC-S1-12).

State-on turns run through the StateChat harness (apply_changes counter inside) or the Seam; the ask
is asserted as an ask (no fetch, the token named), not as exact copy. Contract for scope/hidden:
`Subject.scope` = the contact's company scope (strings), `Subject.hidden` = frozenset of hidden keys
(empty for a linked, non-staff contact whose documents are visible), both written by the applier only.
"""
from __future__ import annotations

import pytest

from tests.chatbot.test_chat_state_r6_subject import (  # noqa: F401 - fixtures used by name
    Focus, _ask_with, _entity, _op, json, seam, tchat, world,
)
from tests.chatbot.test_chat_state_r5_set_axis_keeps_held import r3world, r4world, stub_access, stub_parser  # noqa: F401
from tests.chatbot.test_chat_state_seam import _emit

STOCK_TOOLS = ("crm_inventory_stock_balance_list", "crm_incoming", "crm_master_product_attachments_list")


def _fetched(calls):
    return [c for c in calls if any(t in c["name"] for t in STOCK_TOOLS)]


TOKENS = [("en", "stock ZZ-9981?", "ZZ-9981"), ("bm", "ada stok ZZ-9982?", "ZZ-9982"), ("zh", "ZZ-9983有货吗", "ZZ-9983")]


@pytest.mark.parametrize("message,token", [c[1:] for c in TOKENS], ids=[c[0] for c in TOKENS])
def test_r6_s4_an_unresolved_subject_never_fetches_and_asks_about_the_token(tchat, world, message, token):
    text = tchat.say(message, _ask_with([_entity(token, "product")], [_op("set", "product")], message))
    assert tchat.state_log()["subject"]["source"] == "unresolved"
    assert not _fetched(tchat.calls), ("an unresolved Subject reached a fetch", tchat.calls)
    assert token.lower() in text.lower(), ("the ask does not name the token", text)


def test_r6_s4_two_codes_one_placed_the_fetch_runs_and_the_reply_names_the_unplaced_one(tchat, world):
    placed = world["close_couple"]["sorento"][0]
    text = tchat.say("two codes", _ask_with(
        [_entity(placed.product_code, "product"), _entity("ZZ-9981", "product")], [_op("set", "product")], "two"))
    ids = {pid for c in _fetched(tchat.calls) for pid in c["args"].get("product_ids") or []}
    assert ids == {str(placed.id)}, tchat.calls
    assert "zz-9981" in text.lower(), ("the unplaced code was silently dropped", text)


def _held_token_turn(seam, code, message="any promo?"):
    from app.services.chatbot.turn.state import focus_to_wire

    row = {"raw": code, "canonical_code": code, "hint": "product", "current_message": False}
    prev = {"focus": focus_to_wire(Focus(products=[row], domains=["inventory"])), "open_question": None}
    out = seam.say(message, _emit(domain_hint="inventory", intent_hint="check_stock", entities=[],
                                  state_changes=[_op("keep")]), previous=prev)
    return out, seam.turn_calls[-1]


@pytest.mark.parametrize("message", ["any promo?", "ada promosi tak", "有促销吗"])
def test_r6_s4_a_held_token_the_resolver_cannot_place_gets_an_ask_not_an_unscoped_fetch(seam, message):
    out, calls = _held_token_turn(seam, "ZZUNK-77", message)
    assert not [c for c in calls if any(t in c[0] for t in STOCK_TOOLS)], ("an unscoped fetch ran", calls)
    assert "zzunk-77" in ((out.reply or {}).get("text") or "").lower(), out.reply


def test_r6_s4_guard_a_held_token_the_resolver_places_still_fetches_as_today(seam):
    out, calls = _held_token_turn(seam, "SRTWC286-SH")
    ids = {pid for _n, a in calls for pid in a.get("product_ids") or []}
    assert ids == {seam.uuid_of["SRTWC286-SH"]}, calls


def test_r6_s4_the_subject_carries_the_contacts_company_scope_and_hidden_keys(tchat, world):
    from app.services.chatbot import engine as engine_mod

    placed = world["close_couple"]["sorento"][0]
    tchat.say(placed.product_code, _ask_with([_entity(placed.product_code, "product")], [_op("set", "product")], "x"))
    subject = tchat.state_log()["subject"]
    want = sorted(str(c) for c in engine_mod._contact_company_scope(tchat.session_factory, tchat.contact_id))
    assert want and subject["scope"] == want, ("scope not filled by the applier from the contact's scope", subject["scope"], want)
    assert isinstance(subject["hidden"], list), subject


def test_r6_s4_guard_the_fetch_scoping_is_unchanged_for_a_placed_code(tchat, world):
    placed = world["close_couple"]["sorento"][0]
    tchat.say(placed.product_code, _ask_with([_entity(placed.product_code, "product")], [_op("set", "product")], "x"))
    ids = {pid for c in _fetched(tchat.calls) for pid in c["args"].get("product_ids") or []}
    assert ids == {str(placed.id)}, tchat.calls


def test_r6_s4_state_off_twin_an_unplaced_token_behaves_as_today(session_factory, monkeypatch, stub_parser, stub_access, world):
    from tests.chatbot.test_attribute_asks_round7 import _Leena

    plain = _Leena(session_factory, monkeypatch, stub_parser, stub_access, world)
    text = plain.say("stock ZZ-9981?", _ask_with([_entity("ZZ-9981", "product")], None, "x"))
    assert "zz-9981" in text.lower() and not _fetched(plain.calls), (text, plain.calls)


# ----------------------------------------------------------------------- hidden keys (lead decision)
def _stock_turn(chat, world):
    placed = world["close_couple"]["sorento"][0]
    text = chat.say(placed.product_code, _ask_with([_entity(placed.product_code, "product")], [_op("set", "product")], "x"))
    return text, chat.state_log()["subject"]


def test_r6_s4_an_unlinked_non_staff_contact_gets_hidden_customer_and_no_customer_rows(tchat, world):
    """V1-DOC-SCOPE: a contact who may not see other customers' rows or documents (unlinked, not staff)
    has Subject.hidden == ["customer"]; the fetch is the same as today (product-scoped, no customer tool)."""
    text, subject = _stock_turn(tchat, world)
    assert subject["hidden"] == ["customer"], subject
    assert not [c for c in tchat.calls if "customer" in c["name"]], tchat.calls
    ids = {pid for c in _fetched(tchat.calls) for pid in c["args"].get("product_ids") or []}
    assert ids == {str(world["close_couple"]["sorento"][0].id)}, tchat.calls


def test_r6_s4_a_staff_contact_has_no_hidden_keys(tchat, world, session_factory):
    from tests.chatbot._turn_helpers import make_office_tier

    make_office_tier(session_factory, tchat.contact_id)
    _text, subject = _stock_turn(tchat, world)
    assert subject["hidden"] == [], subject
