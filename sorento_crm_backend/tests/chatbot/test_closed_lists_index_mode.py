"""CLOSED-LISTS-INDEX-MODE (owner, 20 Oct 2026): "test on those blocks removed, same for
attachment type or any value that should be indexed".

One setting, `system_settings.chatbot_closed_lists_mode` = 'block' (default, today) | 'index'.
In 'index' the parser SYSTEM prompt carries no full closed list ({{specs}},
{{attachment_types}}, {{certification_types}} ...) and the USER block carries only (a) the index
matches for the message's own words (file types / cert kinds / schemes, alias words included),
(b) the held product's own visible spec key=value, (c) the file types and certificate kinds /
schemes the held product actually has on record. Read per turn: a flip needs no restart.

These tests run the REAL `parser_mod.resolve_config` over a seeded prompt version (so the
system prompt is the real render) and stub only the provider call. ZZ data.
Assumed names: column/attribute `SystemSetting.chatbot_closed_lists_mode`, values "index"/"block".
"""
from __future__ import annotations

import json
import types
import uuid
from typing import Any

import pytest

import app.main  # noqa: F401  isort:skip
from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.models.lookup import LookupOption, LookupOptionKeyword, LookupSet
from app.models.product_spec import ProductSpecifications, ProductSpecRegistry
from app.models.user import SystemSetting
from app.services import ai_prompt_registry
from app.services import chatbot_prompt_vars as pv
from app.services.ai_assistant_service import MCPRuntimeClient
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import closed_lists_prompt as clp
from app.services.chatbot.head import parser as parser_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot._attach_world import World
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_closed_lists_hidden_keys_entries import _hide, real_hidden_spec_keys
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output, seeded, stub_access  # noqa: F401

HELD = "ZZIDXP1"
SPEC_LINE = "Specification zz_idxvis"
PHOTOS_LINE = "File type zz_idx_photos:"
DRAWING = "zz_idx_drawing"

TEMPLATE = (
    "Rules for {{current_date}}.\nSPECS-BEGIN\n{{specs}}\nSPECS-END\nFILES-BEGIN\n{{attachment_types}}\n"
    "FILES-END\nCERTS-BEGIN\n{{certification_types}}\nCERTS-END\n"
) + clp.SECTION


@pytest.fixture(autouse=True)
def _fresh_caches():
    ai_prompt_registry.bust_cache()
    pv.clear_cache()
    yield
    ai_prompt_registry.bust_cache()
    pv.clear_cache()


def _seed_prompt(session_factory, monkeypatch) -> None:
    from app.services import ai_assistant_service, llm_provider

    db = session_factory()
    v = AIPromptVersion(id=str(uuid.uuid4()), name=parser_mod.PROMPT_KEY, version=1, type="text",
                        template=TEMPLATE, variables=["current_date"])
    db.add(v)
    db.flush()
    db.add(AIPromptLabel(id=str(uuid.uuid4()), name=parser_mod.PROMPT_KEY, label="production", version_id=v.id))
    db.commit()
    cfg = types.SimpleNamespace(provider="openai", model="gpt-test")
    monkeypatch.setattr(ai_assistant_service, "AIAssistantConfigService", lambda d: types.SimpleNamespace(get=lambda: cfg))
    monkeypatch.setattr(llm_provider, "resolve_api_key", lambda config, provider: "sk-test")


def _seed_world(session_factory, *, held_has_files: bool = True, alias: bool = False) -> World:
    db = session_factory()
    db.add_all([
        ProductSpecRegistry(id=str(uuid.uuid4()), spec_key="zz_idxvis", label="Idx Visible", data_type="enum",
                            allowed_values=["zzvisval"], synonyms={"zzvisval": ["zzvisval"]}),
        ProductSpecRegistry(id=str(uuid.uuid4()), spec_key="zz_idxhid", label="Idx Hidden", data_type="enum",
                            allowed_values=["zzhidval"], synonyms={"zzhidval": ["zzhidval"]}),
    ])
    db.commit()
    w = World(session_factory)
    w.type("ZZ Idx Drawing", code=DRAWING)
    w.type("ZZ Idx Photos", code="zz_idx_photos")  # no live file anywhere: listed, held product lacks it
    w.type("ZZ Idx Cert", cert=True, code="zz_idx_cert")
    p = w.product(HELD)
    w.db.add(ProductSpecifications(id=str(uuid.uuid4()), product_id=p.id, values={
        "zz_idxvis": {"value": "zzvisval"}, "zz_idxhid": {"value": "zzhidval"},
    }))
    if held_has_files:
        w.file(HELD, type_name="ZZ Idx Drawing")
        w.file(HELD, type_name="ZZ Idx Cert", cert=True, scheme="ZZSCH")
    if alias:
        s = LookupSet(id=str(uuid.uuid4()), set_key="attachment_type_alias", name="Attachment Type Alias")
        w.db.add(s)
        w.db.flush()
        o = LookupOption(id=str(uuid.uuid4()), set_id=s.id, value="ZZ Idx Drawing", label="ZZ Idx Drawing", sort_order=0)
        w.db.add(o)
        w.db.flush()
        w.db.add(LookupOptionKeyword(id=str(uuid.uuid4()), option_id=o.id, keyword="zzgambar"))
    return w.commit()


def _set_mode(session_factory, mode: str) -> None:
    assert hasattr(SystemSetting, "chatbot_closed_lists_mode"), "SystemSetting.chatbot_closed_lists_mode does not exist yet"
    db = session_factory()
    row = db.query(SystemSetting).first()
    if row is None:
        row = SystemSetting()
        db.add(row)
    row.chatbot_closed_lists_mode = mode
    db.commit()


def _message(text: str, n: int) -> dict[str, Any]:
    return {"event_type": "message.received", "contact": {"id": CONTACT_ID}, "message": {
        "messageId": f"ZZT-idx-{n}-{uuid.uuid4().hex[:6]}", "contactId": CONTACT_ID, "channelId": "whatsapp",
        "traffic": "incoming", "message": {"type": "text", "text": text}}}


def _held_turn() -> dict:
    return _parser_output(intent_hint="check_stock", domain_hint="inventory", user_goal="ask", entities=[
        {"raw": HELD, "hint": "product", "canonical_code": HELD, "current_message": True, "confident": True}])


def _quiet() -> dict:
    return _parser_output(intent_hint="check_stock", domain_hint="inventory", user_goal="ask", entities=[])


def _turns(session_factory, stub_access, monkeypatch, turns, *, between=None, hidden: bool = False):
    """[(system_prompt, user_block, result)] per turn, over the REAL resolve_config."""
    _seed_prompt(session_factory, monkeypatch)
    seen: list[tuple[str, str]] = []
    queue = [v for _t, v in turns]

    def parse(config, user_block):
        seen.append((config.system_prompt, str(user_block)))
        return queue.pop(0)

    monkeypatch.setattr(parser_mod, "parse", parse)
    monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({DEFAULT_COMPANY_ID}))
    monkeypatch.setattr(MCPRuntimeClient, "call_tool", lambda self, name, args: json.dumps({"ok": True, "items": []}))
    stub_access(hidden_spec_keys=real_hidden_spec_keys(session_factory) if hidden else [])
    out = []
    for n, (text, _v) in enumerate(turns):
        if between:
            between(n)
        result = engine_mod.run_turn(_envelope(message=_message(text, n)), session_factory=session_factory)
        out.append((*seen[-1], result))
    return out


def _lines(block: str, prefix: str) -> list[str]:
    return [ln for ln in block.splitlines() if ln.startswith(prefix)]


# I1 GUARD: block (default) keeps the full lists in the system prompt.
def test_i1_block_mode_system_prompt_carries_the_full_lists(session_factory, seeded, stub_access, monkeypatch):
    _seed_world(session_factory)
    [(system, _block, _r)] = _turns(session_factory, stub_access, monkeypatch, [("zzqwerty", _quiet())])
    assert SPEC_LINE in system, system
    assert PHOTOS_LINE in system, system


# I2
def test_i2_index_mode_system_prompt_carries_no_full_list(session_factory, seeded, stub_access, monkeypatch):
    _seed_world(session_factory)
    _set_mode(session_factory, "index")
    [(system, _block, _r)] = _turns(session_factory, stub_access, monkeypatch, [("zzqwerty", _quiet())])
    assert SPEC_LINE not in system, system
    assert PHOTOS_LINE not in system, system
    assert "File type zz_idx_drawing:" not in system and "Certificate scheme ZZSCH" not in system, system


# I3
def test_i3_index_mode_user_block_carries_held_visible_spec_not_the_hidden_one(session_factory, seeded, stub_access, monkeypatch):
    _seed_world(session_factory)
    _hide(session_factory, "zz_idxhid")
    _set_mode(session_factory, "index")
    out = _turns(session_factory, stub_access, monkeypatch, [(HELD, _held_turn()), ("zzqwerty", _quiet())], hidden=True)
    block = out[1][1]
    assert any("zz_idxvis" in ln and "zzvisval" in ln for ln in block.splitlines()), block
    assert "zz_idxhid" not in block and "zzhidval" not in block, block


# I4
def test_i4_index_mode_user_block_lists_only_the_files_the_held_product_has(session_factory, seeded, stub_access, monkeypatch):
    _seed_world(session_factory)
    _set_mode(session_factory, "index")
    out = _turns(session_factory, stub_access, monkeypatch, [(HELD, _held_turn()), ("zzqwerty", _quiet())])
    block = out[1][1]
    assert DRAWING in block, block
    assert "ZZSCH" in block, block
    assert "zz_idx_photos" not in block and "ZZ Idx Photos" not in block, block


# I5
def test_i5_index_mode_alias_word_matches_the_file_type_line(session_factory, seeded, stub_access, monkeypatch):
    _seed_world(session_factory, alias=True)
    _set_mode(session_factory, "index")
    [(_system, block, _r)] = _turns(session_factory, stub_access, monkeypatch, [("zzgambar", _quiet())])
    assert _lines(block, f"File type {DRAWING}:"), block
    assert not _lines(block, PHOTOS_LINE), block


# I6 (likely GUARD)
def test_i6_index_mode_a_word_matching_nothing_gets_no_line_and_the_turn_answers(session_factory, seeded, stub_access, monkeypatch):
    _seed_world(session_factory, held_has_files=False)
    _set_mode(session_factory, "index")
    [(_system, block, result)] = _turns(session_factory, stub_access, monkeypatch, [("zzqwerty", _quiet())])
    for prefix in ("File type", "Certificate kind", "Certificate scheme"):
        assert not _lines(block, prefix), block
    assert not [ln for ln in block.splitlines() if ln.startswith("- ") and "zzqwerty" in ln], block
    assert (result.reply or {}).get("text"), result


# I7
def test_i7_flipping_the_mode_between_turns_needs_no_restart(session_factory, seeded, stub_access, monkeypatch):
    _seed_world(session_factory)
    _set_mode(session_factory, "index")
    out = _turns(
        session_factory, stub_access, monkeypatch, [("zzqwerty", _quiet()), ("zzqwerty again", _quiet())],
        between=lambda n: _set_mode(session_factory, "block") if n == 1 else None,
    )
    assert SPEC_LINE not in out[0][0] and PHOTOS_LINE not in out[0][0], out[0][0]
    assert SPEC_LINE in out[1][0] and PHOTOS_LINE in out[1][0], out[1][0]


# I8: the system prompt must not vary per turn (cache rule); only the user block does.
def test_i8_index_mode_system_prompt_is_byte_equal_across_different_turns(session_factory, seeded, stub_access, monkeypatch):
    _seed_world(session_factory, alias=True)
    _set_mode(session_factory, "index")
    out = _turns(session_factory, stub_access, monkeypatch, [(HELD, _held_turn()), ("zzgambar", _quiet())])
    assert out[0][0] == out[1][0]
    assert out[0][1] != out[1][1]


# I9: held lines sit under their own heading, never under the message's candidates HEADER.
def _held_header() -> str:
    from app.services.chatbot.head import closed_lists_index

    header = getattr(closed_lists_index, "HELD_HEADER", None)
    assert header, "closed_lists_index.HELD_HEADER does not exist yet (the held lines' own heading constant)"
    return header


def _nearest_heading(lines: list[str], idx: int, headings: set[str]) -> str | None:
    for ln in reversed(lines[:idx]):
        if ln in headings:
            return ln
    return None


def test_i9a_held_lines_with_no_word_match_sit_under_their_own_heading(session_factory, seeded, stub_access, monkeypatch):
    from app.services.chatbot.head import candidates

    held_header = _held_header()
    _seed_world(session_factory)
    _set_mode(session_factory, "index")
    out = _turns(session_factory, stub_access, monkeypatch, [(HELD, _held_turn()), ("zzqwerty", _quiet())])
    lines = out[1][1].splitlines()
    first = next((i for i, ln in enumerate(lines) if "zz_idxvis" in ln or DRAWING in ln or "ZZSCH" in ln), None)
    assert first is not None, lines
    assert held_header != candidates.HEADER
    assert first > 0 and lines[first - 1] == held_header, lines


def test_i9b_word_line_under_candidates_header_held_lines_under_held_header(session_factory, seeded, stub_access, monkeypatch):
    from app.services.chatbot.head import candidates

    held_header = _held_header()
    _seed_world(session_factory, alias=True)
    _set_mode(session_factory, "index")
    out = _turns(session_factory, stub_access, monkeypatch, [(HELD, _held_turn()), ("zzgambar", _quiet())])
    lines = out[1][1].splitlines()
    headings = {candidates.HEADER, held_header}
    word = next((i for i, ln in enumerate(lines) if ln.startswith(f"File type {DRAWING}:")), None)
    spec = next((i for i, ln in enumerate(lines) if "zz_idxvis" in ln and "zzvisval" in ln), None)
    assert word is not None and spec is not None, lines
    assert _nearest_heading(lines, word, headings) == candidates.HEADER, lines
    assert _nearest_heading(lines, spec, headings) == held_header, lines
