"""CLOSED-LISTS-INDEX-MODE round 2 (owner, 20 Oct 2026): warehouse and finish short forms join the index.

Contract: documentation/plans/chatbot/PLAN-closed-lists-index-warehouse-20oct.md, IW-1..IW-6.
In index mode the "<= 4 letters is a warehouse" shape rule is gone; a warehouse is one the
per-turn index lists (code, name, or the code's last "-" segment), a typed finish short form
("frg" = the registry's "-FRG" code suffix) lists `finish = french_gold`, and grounding drops a
warehouse hint the registry does not resolve (verdict `dropped_kinds`, apply clears the axis).
Block mode is byte-identical (IW-5).

Real parser template (so the system prompt carries the real warehouse rule), real
`resolve_config`, real grounding and apply; only the provider call is stubbed. ZZ data.
Assumed (coder picks the exact words): a warehouse index line contains the word "warehouse"
and the code; the index-mode system prompt says a warehouse is one the index lists (asserted
loosely as "warehouse" + "index lists", case aside).
"""
from __future__ import annotations

import re
import uuid
from typing import Any

import pytest

import app.main  # noqa: F401  isort:skip
from app.models.inventory import Warehouse
from app.models.product_spec import ProductSpecRegistry
from app.services.chatbot.head import parser_template
from app.services.chatbot.turn import apply as apply_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot import test_closed_lists_index_mode as idx
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import _parser_output, seeded, stub_access  # noqa: F401

RULE_SENTENCE = "at most 4 characters"
WAREHOUSES = {
    "BRW": "ZZ BRW", "BRW-IB": "ZZ BRW-IB", "MWH-IB": "ZZ MWH-IB", "WH3": "ZZ WH3", "HQ": "HEADQUARTER",
    "MKTG-HQ": "ZZ MKTG-HQ", "SD-HQ": "ZZ SD-HQ", "WH3-AM": "ZZ WH3-AM", "MOCHA-WH": "ZZ MOCHA-WH", "PROJECT": "ZZ PROJECT", "PENANG": "ZZ PENANG", "NEW-WH": "ZZ NEW-WH",
}


@pytest.fixture(autouse=True)
def _real_template(monkeypatch):
    monkeypatch.setattr(idx, "TEMPLATE", parser_template.TEMPLATE)


def _seed(session_factory) -> None:
    db = session_factory()
    for code, name in WAREHOUSES.items():
        db.add(Warehouse(id=str(uuid.uuid4()), warehouse_code=code, warehouse_name=name, company_id=DEFAULT_COMPANY_ID))
    rules = [
        {"builder": {"kind": "code", "code_match": "ends_with", "texts": ["-FRG"], "value": "french_gold"}},
        {"builder": {"kind": "code", "code_match": "ends_with", "texts": ["-WH"], "value": "white"}},
    ]
    row = db.query(ProductSpecRegistry).filter(ProductSpecRegistry.spec_key == "finish").first()
    if row is None:
        row = ProductSpecRegistry(id=str(uuid.uuid4()), spec_key="finish", label="Finish", data_type="enum")
        db.add(row)
    row.allowed_values = ["french_gold", "white"]
    row.synonyms = {"french_gold": ["french gold"], "white": ["white"]}
    row.derivation_rules = rules
    db.commit()


def _wh_entity(raw: str) -> dict:
    return {"raw": raw, "hint": "warehouse", "canonical_code": None, "current_message": True, "confident": True}


def _verdict(*entities: dict) -> dict:
    return _parser_output(intent_hint="check_stock", domain_hint="inventory", user_goal="ask", entities=list(entities))


class Seen:
    """What apply's focus rules produced, per turn: (verdict, warehouse rows, rules_fired)."""

    def __init__(self) -> None:
        self.calls: list[tuple[dict, list, list[str]]] = []


def _spy(monkeypatch) -> Seen:
    seen = Seen()
    real = apply_mod._focus_rules

    def wrapper(focus, verdict, entities, decision, **kw):
        out = real(focus, verdict, entities, decision, **kw)
        seen.calls.append((verdict, list(out.warehouse), list(kw["trace"].rules_fired)))
        return out

    monkeypatch.setattr(apply_mod, "_focus_rules", wrapper)
    return seen


def _run(session_factory, stub_access, monkeypatch, turns, mode="index"):
    _seed(session_factory)
    idx._set_mode(session_factory, mode)
    seen = _spy(monkeypatch)
    return idx._turns(session_factory, stub_access, monkeypatch, turns), seen


def _wh_lines(block: str) -> list[str]:
    return [ln for ln in block.splitlines() if "warehouse" in ln.lower()]


def _raws(rows: list) -> list[str]:
    return [str(r.get("raw") or r.get("canonical_code") or "").lower() for r in rows]


def _last(seen: Seen) -> tuple[dict, list, list[str]]:
    assert seen.calls, "apply._focus_rules never ran"
    return seen.calls[-1]


# IW-1
def test_iw1_frg_lists_the_finish_and_no_warehouse(session_factory, seeded, stub_access, monkeypatch):
    out, _seen = _run(session_factory, stub_access, monkeypatch, [("frg stock", idx._quiet())])
    block = out[0][1]
    assert any("finish" in ln and "french_gold" in ln for ln in block.splitlines()), block
    assert not _wh_lines(block), block


def test_iw1_a_warehouse_hint_frg_is_dropped_and_never_written(session_factory, seeded, stub_access, monkeypatch):
    _out, seen = _run(session_factory, stub_access, monkeypatch, [("frg stock", _verdict(_wh_entity("frg")))])
    verdict, warehouse, _rules = _last(seen)
    assert not [e for e in verdict.get("entities") or [] if e.get("hint") == "warehouse"], verdict
    assert "warehouse" not in (verdict.get("dropped_kinds") or []), verdict
    assert "frg" not in _raws(warehouse), warehouse


def test_iw1_a_held_warehouse_is_kept_when_a_finish_short_form_hint_is_dropped(session_factory, seeded, stub_access, monkeypatch):
    _out, seen = _run(session_factory, stub_access, monkeypatch, [
        ("stock at BRW", _verdict(_wh_entity("BRW"))), ("frg stock", _verdict(_wh_entity("frg")))])
    verdict, warehouse, rules = _last(seen)
    assert "warehouse" not in (verdict.get("dropped_kinds") or []), verdict
    assert "dropped_warehouse_clears_axis" not in rules, rules
    assert "frg" not in _raws(warehouse), warehouse
    assert "brw" in _raws(warehouse), warehouse


# IW-2 (option B: no warehouse lines; the hint side stays)
def test_iw2_a_real_code_hint_survives_and_no_warehouse_line_is_listed(session_factory, seeded, stub_access, monkeypatch):
    out, seen = _run(session_factory, stub_access, monkeypatch, [("stock at BRW", _verdict(_wh_entity("BRW")))])
    assert not _wh_lines(out[0][1]), out[0][1]
    verdict, warehouse, rules = _last(seen)
    assert "brw" in _raws(warehouse), warehouse
    assert "dropped_warehouse_clears_axis" not in rules, rules


# IW-12 (option B): a word-code warehouse in a normal sentence is never made a warehouse by our code
@pytest.mark.parametrize("message,word", [
    ("outstanding SO for project SRTWC286", "PROJECT"),
    ("penang customer outstanding SO for SRTSC05", "PENANG"),
])
def test_iw12_a_word_code_warehouse_is_neither_listed_nor_written(message, word, session_factory, seeded, stub_access, monkeypatch):
    out, seen = _run(session_factory, stub_access, monkeypatch, [(message, idx._quiet())])
    block = out[0][1]
    assert not _wh_lines(block), block
    assert not [ln for ln in block.splitlines() if word.lower() in ln.lower() and "warehouse" in ln.lower()], block
    verdict, warehouse, rules = _last(seen)
    assert warehouse == [], warehouse
    assert not [e for e in verdict.get("entities") or [] if e.get("hint") == "warehouse"], verdict


# IW-3 (amended, lead sign-off): an unresolved non-finish word is KEPT, as in block mode
@pytest.mark.parametrize("word", ["stok", "ada", "BRWW"])
def test_iw3_an_unresolved_warehouse_hint_is_kept_and_no_line_is_listed(word, session_factory, seeded, stub_access, monkeypatch):
    out, seen = _run(session_factory, stub_access, monkeypatch, [(word, _verdict(_wh_entity(word)))])
    assert not _wh_lines(out[0][1]), out[0][1]
    verdict, warehouse, rules = _last(seen)
    assert word.lower() in _raws(warehouse), warehouse
    assert "warehouse" not in (verdict.get("dropped_kinds") or []), verdict
    assert "dropped_warehouse_clears_axis" not in rules, rules


# IW-4 (option B): the code reading is the lane's (resolve_warehouse_token), not an index line
def test_iw4_wh3_hint_is_kept_and_resolves_to_wh3_only(session_factory, seeded, stub_access, monkeypatch):
    from app.services.chatbot.lanes.business.services import resolve_warehouse_token

    out, seen = _run(session_factory, stub_access, monkeypatch, [("at wh3", _verdict(_wh_entity("wh3")))])
    assert not _wh_lines(out[0][1]), out[0][1]
    verdict, warehouse, _rules = _last(seen)
    assert "warehouse" not in (verdict.get("dropped_kinds") or []) and warehouse, verdict
    assert resolve_warehouse_token(session_factory(), "wh3") == ["WH3"]


def _has_code(text: str, code: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(code)}(?![\w-])", text) is not None


# IW-8
def test_iw8_a_warehouse_name_is_not_listed(session_factory, seeded, stub_access, monkeypatch):
    out, _seen = _run(session_factory, stub_access, monkeypatch, [("stock at headquarter", idx._quiet())])
    assert not _wh_lines(out[0][1]), out[0][1]


# IW-9 (option B): "hq" resolves to HQ only; the hint is kept
def test_iw9_hq_hint_is_kept_and_resolves_to_hq_only(session_factory, seeded, stub_access, monkeypatch):
    from app.services.chatbot.lanes.business.services import resolve_warehouse_token

    out, seen = _run(session_factory, stub_access, monkeypatch, [("hq", _verdict(_wh_entity("hq")))])
    assert not _wh_lines(out[0][1]), out[0][1]
    verdict, warehouse, _rules = _last(seen)
    assert "warehouse" not in (verdict.get("dropped_kinds") or []) and warehouse, verdict
    assert resolve_warehouse_token(session_factory(), "hq") == ["HQ"]


# IW-7 (guard)
def test_iw7_a_suffix_hint_is_kept(session_factory, seeded, stub_access, monkeypatch):
    _out, seen = _run(session_factory, stub_access, monkeypatch, [("stock at IB", _verdict(_wh_entity("IB")))])
    verdict, warehouse, rules = _last(seen)
    assert "warehouse" not in (verdict.get("dropped_kinds") or []), verdict
    assert warehouse, warehouse
    held = str(warehouse).lower()
    assert "ib" in _raws(warehouse) or ("brw-ib" in held and "mwh-ib" in held), warehouse
    assert "dropped_warehouse_clears_axis" not in rules, rules


# IW-10 (option B)
def test_iw10_wh_lists_the_finish_white_keeps_the_hint_and_lists_no_warehouse(session_factory, seeded, stub_access, monkeypatch):
    out, seen = _run(session_factory, stub_access, monkeypatch, [("wh", _verdict(_wh_entity("wh")))])
    block = out[0][1]
    assert any("finish" in ln and "white" in ln for ln in block.splitlines()), block
    assert not _wh_lines(block), block
    verdict, warehouse, _rules = _last(seen)
    assert "warehouse" not in (verdict.get("dropped_kinds") or []), verdict
    assert "wh" in _raws(warehouse), warehouse  # resolves as a suffix (MOCHA-WH, NEW-WH): a resolvable code beats the finish reading


# IW-5 (GUARD, green today): block mode is unchanged.
def test_iw5_block_mode_keeps_the_shape_rule_and_does_not_drop_the_hint(session_factory, seeded, stub_access, monkeypatch):
    out, seen = _run(session_factory, stub_access, monkeypatch, [("frg stock", _verdict(_wh_entity("frg")))], mode="block")
    system, block, _r = out[0]
    assert RULE_SENTENCE in system, system
    assert not _wh_lines(block), block
    assert not any("french_gold" in ln for ln in block.splitlines()), block
    verdict, warehouse, rules = _last(seen)
    assert "frg" in _raws(warehouse), warehouse
    assert not verdict.get("dropped_kinds"), verdict
    assert "dropped_warehouse_clears_axis" not in rules, rules


# IW-6 (option B): the warehouse rule stays word for word; byte-equal across turns
def test_iw6_index_system_prompt_keeps_the_original_rule_line_and_is_byte_equal(session_factory, seeded, stub_access, monkeypatch):
    out, _seen = _run(session_factory, stub_access, monkeypatch, [("frg stock", idx._quiet()), ("stock at BRW", idx._quiet())])
    assert out[0][0] == out[1][0]
    assert out[0][1] != out[1][1]
    system = out[0][0]
    line = next(ln for ln in parser_template.TEMPLATE.splitlines() if RULE_SENTENCE in ln)
    assert line in system, system
    assert "index lists" not in system.lower(), system
