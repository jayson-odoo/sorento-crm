"""CHAT-SLIM-INDEX S2, engine coverage on Postgres: a marked version offers the Spec block (word + number values)
and the unmarked version is unchanged. Real resolve_config and run_turn; only parser.parse and the embedder are stubbed.
"""
from __future__ import annotations

import json
import uuid

import pytest

import app.main  # noqa: F401  isort:skip
from app.services.ai_assistant_service import MCPRuntimeClient
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import lookup_lists as ll
from app.services.chatbot.head import parser as parser_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import CONTACT_ID, _envelope, seeded, stub_access  # noqa: F401
from tests.chatbot.test_lookup_lists_engine import _fresh_caches, _quiet, _seed_prompt  # noqa: F401
from tests.chatbot.test_lookup_lists_s2 import HDR_SPEC, seed_world

MESSAGE = "any gunmetal basin 200mm trap"


def _turn(session_factory, stub_access, monkeypatch, *, marker: bool):
    _seed_prompt(session_factory, monkeypatch, marker=marker)
    seed_world(session_factory)
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
        "messageId": f"ZZT-s2-{uuid.uuid4().hex[:6]}", "contactId": CONTACT_ID, "channelId": "whatsapp",
        "traffic": "incoming", "message": {"type": "text", "text": MESSAGE}}}
    engine_mod.run_turn(_envelope(message=message), session_factory=session_factory)
    return seen[-1].splitlines()


def test_marked_version_lists_the_finish_and_every_200mm_spec(session_factory, seeded, stub_access, monkeypatch):
    lines = _turn(session_factory, stub_access, monkeypatch, marker=True)
    assert HDR_SPEC in lines, lines
    folded = [ln.casefold() for ln in lines]
    for want in ("- zz finish gunmetal (zz_finish: gunmetal)", "- zz trap length 200mm (zz_trap_len: 200)", "- zz width 200mm (zz_width: 200)"):
        assert want in folded, (want, lines)
    # The depth this world holds (350) is never offered for a 200 mm ask. DIMENSION-ANY (owner, 28 Oct 2026): depth
    # is still nameable at 200, after the any-dimension size line and the holders.
    assert not any("350" in ln for ln in folded), lines
    assert "- size 200mm, any dimension (size: 200)" in folded and "- zz depth 200mm (zz_depth: 200)" in folded, lines


def test_unmarked_version_has_no_spec_block(session_factory, seeded, stub_access, monkeypatch):
    lines = _turn(session_factory, stub_access, monkeypatch, marker=False)
    assert HDR_SPEC not in lines and not any("candidates (pick one only" in ln for ln in lines), lines


def test_spec_lines_end_with_the_registry_key_and_stored_value(session_factory, seeded, stub_access, monkeypatch):
    """The parser fills spec_key / spec_value from the bracket (grounding.py:698-722 reads a word value as the stored
    code and a number as the bare leading number, `float(str(value).split()[0])`)."""
    lines = [ln for ln in _turn(session_factory, stub_access, monkeypatch, marker=True) if ln.startswith("- ")]
    assert any(ln.endswith("(zz_finish: gunmetal)") for ln in lines), lines
    assert any(ln.endswith("(zz_trap_len: 200)") for ln in lines), lines
    assert any(ln.endswith("(zz_width: 200)") for ln in lines), lines
