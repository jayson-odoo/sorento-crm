"""CHAT-SLIM-INDEX access scoping (S2 follow-up): a spec key the contact may not see never reaches a lookup block.

Contract: `load_rows(db, *, hidden_spec_keys=frozenset())`, `number_hits(message, db, *, hidden_spec_keys=frozenset())`,
and the engine passes the contact's own hidden set (`head/access._hidden_spec_keys`, the same set
`_candidate_lines` receives). Hidden by a seeded `spec_visibility_policies` row. Postgres only, fake data.
"""
from __future__ import annotations

import json
import uuid

import app.main  # noqa: F401  isort:skip
from app.services.ai_assistant_service import MCPRuntimeClient
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import lookup_lists as ll
from app.services.chatbot.head import parser as parser_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_closed_lists_hidden_keys_entries import _hide, real_hidden_spec_keys
from tests.chatbot.test_engine import CONTACT_ID, _envelope, seeded, stub_access  # noqa: F401
from tests.chatbot.test_lookup_lists_engine import _fresh_caches, _quiet, _seed_prompt  # noqa: F401
from tests.chatbot.test_lookup_lists_s2 import HDR_SPEC, scoped, seed_world

MESSAGE = "any gunmetal basin 200mm trap"


def _spec_labels(rows) -> set[str]:
    return {r.label.casefold() for r in rows if r.list_name == "spec"}


def test_load_rows_drops_the_spec_rows_of_a_hidden_key(session_factory):
    seed_world(session_factory)
    db = scoped(session_factory)
    assert "zz finish gunmetal (zz_finish: gunmetal)" in _spec_labels(ll.load_rows(db))
    hidden = ll.load_rows(db, hidden_spec_keys=frozenset({"zz_finish"}))
    assert not any("zz finish" in s for s in _spec_labels(hidden)), _spec_labels(hidden)
    assert ll.load_rows(db, hidden_spec_keys=frozenset()) == ll.load_rows(db)


def test_hidden_key_word_is_not_offered_by_shortlist(session_factory):
    seed_world(session_factory)
    rows = ll.load_rows(scoped(session_factory), hidden_spec_keys=frozenset({"zz_finish"}))
    assert ll.shortlist("gunmetal basin", rows, None).get("spec", []) == []


def test_number_hits_skip_a_hidden_key_and_keep_the_others(session_factory):
    seed_world(session_factory)
    db = scoped(session_factory)
    got = ll.number_hits(MESSAGE, db, hidden_spec_keys=frozenset({"zz_trap_len"}))
    assert sorted(h.row.label.casefold() for h in got) == ["zz width 200mm (zz_width: 200)"], got
    assert ll.number_hits(MESSAGE, db, hidden_spec_keys=frozenset({"zz_trap_len", "zz_width"})) == []


def _turn(session_factory, stub_access, monkeypatch, *, hide: tuple[str, ...]) -> list[str]:
    _seed_prompt(session_factory, monkeypatch, marker=True)
    seed_world(session_factory)
    if hide:
        _hide(session_factory, *hide)
    monkeypatch.setattr(ll, "EMBED", None, raising=False)
    seen: list[str] = []

    def parse(config, user_block):
        seen.append(str(user_block))
        return _quiet()

    monkeypatch.setattr(parser_mod, "parse", parse)
    monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({DEFAULT_COMPANY_ID}))
    monkeypatch.setattr(MCPRuntimeClient, "call_tool", lambda self, name, args: json.dumps({"ok": True, "items": []}))
    stub_access(hidden_spec_keys=real_hidden_spec_keys(session_factory))
    message = {"event_type": "message.received", "contact": {"id": CONTACT_ID}, "message": {
        "messageId": f"ZZT-acc-{uuid.uuid4().hex[:6]}", "contactId": CONTACT_ID, "channelId": "whatsapp",
        "traffic": "incoming", "message": {"type": "text", "text": MESSAGE}}}
    engine_mod.run_turn(_envelope(message=message), session_factory=session_factory)
    return [ln.casefold() for ln in seen[-1].splitlines()]


def test_contact_that_may_see_everything_gets_the_word_and_number_lines(session_factory, seeded, stub_access, monkeypatch):
    lines = _turn(session_factory, stub_access, monkeypatch, hide=())
    assert HDR_SPEC.casefold() in lines
    for want in ("- zz finish gunmetal (zz_finish: gunmetal)", "- zz trap length 200mm (zz_trap_len: 200)", "- zz width 200mm (zz_width: 200)"):
        assert want in lines, (want, lines)


def test_contact_whose_access_hides_a_word_key_gets_no_line_for_it(session_factory, seeded, stub_access, monkeypatch):
    lines = _turn(session_factory, stub_access, monkeypatch, hide=("zz_finish",))
    assert not any("zz finish" in ln or "gunmetal" in ln for ln in lines if ln.startswith("- ")), lines
    assert "- zz trap length 200mm (zz_trap_len: 200)" in lines, lines


def test_contact_whose_access_hides_a_number_key_gets_no_line_for_it(session_factory, seeded, stub_access, monkeypatch):
    lines = _turn(session_factory, stub_access, monkeypatch, hide=("zz_trap_len",))
    assert not any("trap length" in ln for ln in lines if ln.startswith("- ")), lines
    assert "- zz width 200mm (zz_width: 200)" in lines and "- zz finish gunmetal (zz_finish: gunmetal)" in lines, lines
