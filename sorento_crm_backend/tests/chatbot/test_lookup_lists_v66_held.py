"""CHAT-V66-REGRESSIONS case 1: a value the conversation already holds stays nameable on a turn that does not repeat it.

Prod 26 Oct (v66, contacts masked): "please share new mocha promotion" -> the bot asked dealer or end user -> "dealer".
The answer turn's own words name no brand, so the per-turn Brand candidates block was empty and the list-free prompt's
BRAND CANDIDATES rule ("the ONLY valid brand names are the ones it lists THIS turn") left the parser no way to name the
held brand: parser A/B, v185 emitted every brand's dealer level in 6 of 7 runs, v63 (every brand on the Known brands
line) named the held one in 6 of 7. The lookup now also lists the rows the State subject holds, by exact name.
Fake data only (ZZ prefix).
"""
from __future__ import annotations

import json
import uuid

import pytest

import app.main  # noqa: F401  isort:skip
from app.services.chatbot import answer_bridge
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import lookup_lists as ll
from app.services.chatbot.head import parser as parser_mod
from app.services.chatbot.turn import pending as turn_pending
from app.services.chatbot.turn.state import Focus, focus_to_wire
from app.services.ai_assistant_service import MCPRuntimeClient
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import CONTACT_ID, _envelope, seeded, stub_access  # noqa: F401
from tests.chatbot.test_lookup_lists_engine import _fresh_caches, _quiet, _seed_prompt, _seed_world  # noqa: F401

HDR_BRAND = "Brand candidates (pick one only if the message means it):"
BRAND = ll.LookupRow("brand", "b1", "ZZ Brand (ZZBR)", ("ZZ Brand", "ZZBR"))
OTHER_BRAND = ll.LookupRow("brand", "b2", "ZZ Other (ZZOT)", ("ZZ Other", "ZZOT"))
WAREHOUSE = ll.LookupRow("location", "w1", "ZZ Store (ZZW1)", ("ZZ Store", "ZZW1"))
CUSTOMER = ll.LookupRow("customer", "c1", "ZZ Trading", ("ZZ Trading",))
DEALER = ll.LookupRow("sales_channel", "dealer", "dealer", ("dealer",))
ROWS = [BRAND, OTHER_BRAND, WAREHOUSE, CUSTOMER, DEALER]


def _labels(hits, name):
    return [h.row.label for h in hits.get(name) or []]


def test_a_held_brand_is_offered_on_a_turn_whose_words_do_not_name_it():
    hits = ll.shortlist("dealer", ROWS, None, held={"brand": ("ZZ Brand",)})
    assert _labels(hits, "brand") == ["ZZ Brand (ZZBR)"], hits
    assert _labels(hits, "sales_channel") == ["dealer"], hits
    assert HDR_BRAND in ll.render(hits)


def test_a_held_value_matches_its_own_row_by_exact_name_only():
    # A held value is a name the conversation already settled: no near spelling, no meaning.
    hits = ll.shortlist("dealer", ROWS, None, held={"brand": ("ZZ Bran",), "location": ("ZZ Stor",)})
    assert "brand" not in hits and "location" not in hits, hits
    # Code or name, case aside, each held value reaches its own list only.
    hits = ll.shortlist("dealer", ROWS, None, held={"brand": ("zzbr",), "location": ("ZZW1",), "customer": ("zz trading",)})
    assert _labels(hits, "brand") == ["ZZ Brand (ZZBR)"], hits
    assert _labels(hits, "location") == ["ZZ Store (ZZW1)"], hits
    assert _labels(hits, "customer") == ["ZZ Trading"], hits


def test_without_held_values_the_shortlist_is_unchanged():
    assert ll.shortlist("dealer", ROWS, None) == ll.shortlist("dealer", ROWS, None, held={})


def test_held_values_come_from_the_state_subject_lists_only():
    subject = {
        "domain": ["promotion"], "product": ["ZZP1"], "tier": ["dealer"], "status": "outstanding",
        "brand": ["ZZ Brand"], "warehouse": ["ZZW1"], "customer": ["ZZ Trading"], "channel": "dealer",
        "category": ["water closet"], "attachment_type": ["photo"],
    }
    assert ll.held_values(subject) == {
        "brand": ("ZZ Brand",), "location": ("ZZW1",), "customer": ("ZZ Trading",), "sales_channel": ("dealer",),
        "category": ("water closet",), "file_type": ("photo",),
    }
    assert ll.held_values({}) == {}


def _tier_state(brands: list[str]) -> dict:
    rows = [{"code": v, "label": label, "value": v} for v, label in (("dealer", "Dealer"), ("end_user", "End user"))]
    pending = answer_bridge._tier_options(rows, asked_at_turn=1)
    return {"focus": focus_to_wire(Focus(domains=["promotion"], brands=brands)), "open_question": turn_pending.to_wire(pending),
            "ideation": None, "access_levels": [], "contains_flyer": False, "reply_language": None}


def _answer_turn(session_factory, stub_access, monkeypatch, text: str, prev: dict) -> str:  # noqa: F811
    _seed_prompt(session_factory, monkeypatch, marker=True)
    _seed_world(session_factory)
    monkeypatch.setattr(ll, "EMBED", None, raising=False)
    seen: list[str] = []

    def parse(config, user_block):
        seen.append(str(user_block))
        return _quiet()

    monkeypatch.setattr(parser_mod, "parse", parse)
    monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({DEFAULT_COMPANY_ID}))
    monkeypatch.setattr(MCPRuntimeClient, "call_tool", lambda self, name, args: json.dumps({"ok": True, "items": []}))
    stub_access()
    message = {"event_type": "message.received", "contact": {"id": CONTACT_ID}, "message": {
        "messageId": f"ZZT-v66-{uuid.uuid4().hex[:6]}", "contactId": CONTACT_ID, "channelId": "whatsapp",
        "traffic": "incoming", "message": {"type": "text", "text": text}}}
    engine_mod.run_turn(_envelope(is_test=True, message=message, previous_conversation_state=prev), session_factory=session_factory)
    assert seen, "the parser was never called"
    return seen[-1]


def test_the_clarify_answer_turn_offers_the_held_brand(session_factory, seeded, stub_access, monkeypatch):  # noqa: F811
    block = _answer_turn(session_factory, stub_access, monkeypatch, "dealer", _tier_state(["ZZ Brand"]))
    lines = block.splitlines()
    assert HDR_BRAND in lines and "- ZZ Brand (ZZBR)" in lines, block


def test_nothing_held_means_no_brand_block_on_the_same_answer(session_factory, seeded, stub_access, monkeypatch):  # noqa: F811
    block = _answer_turn(session_factory, stub_access, monkeypatch, "dealer", _tier_state([]))
    assert HDR_BRAND not in block, block
