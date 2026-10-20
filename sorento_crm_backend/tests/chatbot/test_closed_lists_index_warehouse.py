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
WAREHOUSES = ["BRW", "BRW-IB", "MWH-IB", "WH3"]


@pytest.fixture(autouse=True)
def _real_template(monkeypatch):
    monkeypatch.setattr(idx, "TEMPLATE", parser_template.TEMPLATE)


def _seed(session_factory) -> None:
    db = session_factory()
    for code in WAREHOUSES:
        db.add(Warehouse(id=str(uuid.uuid4()), warehouse_code=code, warehouse_name=f"ZZ {code}", company_id=DEFAULT_COMPANY_ID))
    rules = [
        {"kind": "code", "code_match": "ends_with", "texts": ["-FRG"], "value": "french_gold"},
        {"kind": "code", "code_match": "ends_with", "texts": ["-WH"], "value": "white"},
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
    assert "warehouse" in (verdict.get("dropped_kinds") or []) or not [
        e for e in verdict.get("entities") or [] if e.get("hint") == "warehouse"], verdict
    assert "frg" not in _raws(warehouse), warehouse


def test_iw1_a_held_warehouse_is_cleared_when_the_hint_is_dropped(session_factory, seeded, stub_access, monkeypatch):
    _out, seen = _run(session_factory, stub_access, monkeypatch, [
        ("stock at BRW", _verdict(_wh_entity("BRW"))), ("frg stock", _verdict(_wh_entity("frg")))])
    _verdict_out, warehouse, rules = _last(seen)
    assert warehouse == [], warehouse
    assert "dropped_warehouse_clears_axis" in rules, rules


# IW-2
def test_iw2_a_real_code_is_listed_and_its_hint_survives(session_factory, seeded, stub_access, monkeypatch):
    out, seen = _run(session_factory, stub_access, monkeypatch, [("stock at BRW", _verdict(_wh_entity("BRW")))])
    lines = _wh_lines(out[0][1])
    assert any("BRW" in ln for ln in lines), out[0][1]
    verdict, warehouse, rules = _last(seen)
    assert "brw" in _raws(warehouse), warehouse
    assert "dropped_warehouse_clears_axis" not in rules, rules


def test_iw2_a_suffix_lists_every_code_it_ends(session_factory, seeded, stub_access, monkeypatch):
    out, _seen = _run(session_factory, stub_access, monkeypatch, [("IB", idx._quiet())])
    text = "\n".join(_wh_lines(out[0][1]))
    assert "BRW-IB" in text and "MWH-IB" in text, out[0][1]


# IW-3
@pytest.mark.parametrize("word", ["stok", "ada"])
def test_iw3_a_plain_short_word_gets_no_warehouse_line_and_its_hint_is_dropped(word, session_factory, seeded, stub_access, monkeypatch):
    out, seen = _run(session_factory, stub_access, monkeypatch, [(word, _verdict(_wh_entity(word)))])
    assert not _wh_lines(out[0][1]), out[0][1]
    verdict, warehouse, _rules = _last(seen)
    assert word not in _raws(warehouse), warehouse
    assert "warehouse" in (verdict.get("dropped_kinds") or []), verdict


# IW-4
def test_iw4_wh3_lists_the_warehouse_and_binds_nothing(session_factory, seeded, stub_access, monkeypatch):
    out, seen = _run(session_factory, stub_access, monkeypatch, [("wh3", idx._quiet())])
    assert any("WH3" in ln for ln in _wh_lines(out[0][1])), out[0][1]
    assert _last(seen)[1] == []


def test_iw4_wh_lists_the_finish_white_and_binds_nothing(session_factory, seeded, stub_access, monkeypatch):
    out, seen = _run(session_factory, stub_access, monkeypatch, [("wh", idx._quiet())])
    assert any("finish" in ln and "white" in ln for ln in out[0][1].splitlines()), out[0][1]
    assert _last(seen)[1] == []


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


# IW-6
def test_iw6_index_system_prompt_is_byte_equal_with_the_shape_rule_replaced(session_factory, seeded, stub_access, monkeypatch):
    out, _seen = _run(session_factory, stub_access, monkeypatch, [("frg stock", idx._quiet()), ("stock at BRW", idx._quiet())])
    assert out[0][0] == out[1][0]
    assert out[0][1] != out[1][1]
    system = out[0][0]
    assert RULE_SENTENCE not in system, system
    low = system.lower()
    assert "index lists" in low and "warehouse" in low, system
