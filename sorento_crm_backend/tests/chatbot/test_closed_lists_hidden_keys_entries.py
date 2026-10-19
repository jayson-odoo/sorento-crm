"""H1 HIDDEN-KEYS-AT-THE-ENTRIES (crew ruling a29310107 (3)(a), 20 Oct; ZZ data).

A contact-hidden spec key is applied at the parser's two entries: what the parser is SHOWN (the
candidate block) and what it EMITTED (the grounding output). The hidden set comes from the real
`spec_visibility_policies` through head/access, as the R6-6 tests do. Downstream drops stay as a
safety net.
"""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text

import app.main  # noqa: F401  isort:skip
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecifications, ProductSpecRegistry
from app.services.ai_assistant_service import MCPRuntimeClient
from app.services.chatbot import engine as engine_mod
from app.services.chatbot import trace as trace_mod
from app.services.chatbot.head import parser as parser_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._pg_fixture import unique_code
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_closed_lists_spec_over_held import _message, _stock_ask
from tests.chatbot.test_engine import _envelope, seeded, stub_access  # noqa: F401


def _seed(session_factory) -> None:
    db = session_factory()
    for key, label in (("dim_width", "Width"), ("dim_length", "Length")):
        db.add(ProductSpecRegistry(id=str(uuid.uuid4()), spec_key=key, label=label, data_type="numeric", unit="mm"))
    db.add(ProductSpecRegistry(
        id=str(uuid.uuid4()), spec_key="zz_is_tall", label="Tall bowl", data_type="boolean", allowed_values=[],
        synonyms={"true": ["zz tall bowl"]}, value_labels={},
    ))
    db.execute(text("ALTER TABLE product_spec_registry ADD COLUMN IF NOT EXISTS matches_bare_size boolean NOT NULL DEFAULT false"))
    db.execute(text("UPDATE product_spec_registry SET matches_bare_size = true WHERE spec_key IN ('dim_width', 'dim_length')"))
    cat = ProductCategory(
        id=str(uuid.uuid4()), category_code=unique_code("C")[:50], category_name="ZZ Wash Basin", class_label="ZZ Wash Basin",
        company_id=DEFAULT_COMPANY_ID,
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each", company_id=DEFAULT_COMPANY_ID)
    db.add_all([cat, uom])
    db.flush()
    # only dim_width holds 600
    p = Product(
        id=str(uuid.uuid4()), product_code="ZZHK-W", product_name="ZZHK-W", category_id=cat.id, base_uom_id=uom.id,
        list_price=1, company_id=DEFAULT_COMPANY_ID,
    )
    db.add(p)
    db.flush()
    db.add(ProductSpecifications(
        id=str(uuid.uuid4()), product_id=p.id,
        values={"class": {"value": "ZZ Wash Basin"}, "dim_width": {"value": 600}, "zz_is_tall": {"value": True}},
    ))
    db.commit()


def _hide(session_factory, *keys: str) -> None:
    db = session_factory()
    db.execute(
        text("INSERT INTO spec_visibility_policies (id, spec_keys, excluded_spec_keys) VALUES (gen_random_uuid(), NULL, :ex)"),
        {"ex": list(keys)},
    )
    db.commit()


def _run(session_factory, stub_access, monkeypatch, message: str, verdict: dict, *, gate: bool = True):
    """(parser user block, trace records) of one turn."""
    blocks: list[str] = []
    traces: list = []
    real = trace_mod.TurnTrace.persisted

    def fake_resolve_config(db, *, current_date, override_version_id=None):
        return parser_mod.ParserConfig(
            system_prompt="stub", prompt_version=1, provider="openai", model="m", api_key="k", closed_lists=gate,
        )

    def parse(config, user_block):
        blocks.append(str(user_block))
        return verdict

    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", parse)
    monkeypatch.setattr(trace_mod.TurnTrace, "persisted", lambda self: (traces.append(real(self)) or traces[-1]))
    monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({DEFAULT_COMPANY_ID}))
    monkeypatch.setattr(MCPRuntimeClient, "call_tool", lambda self, name, args: json.dumps({"ok": True, "items": []}))
    stub_access()
    engine_mod.run_turn(_envelope(message=_message(message, 0)), session_factory=session_factory)
    return blocks[0], traces[-1] if traces else []


def _candidate_lines(block: str) -> list[str]:
    return [ln for ln in block.splitlines() if ln.startswith("- ")]


QUIET = _stock_ask()


def test_a_hidden_dim_width_is_never_shown_to_the_parser(session_factory, seeded, stub_access, monkeypatch):
    _seed(session_factory)
    _hide(session_factory, "dim_width")

    block, _t = _run(session_factory, stub_access, monkeypatch, "600mm zz basin", QUIET)

    lines = _candidate_lines(block)
    assert not any("dim_width" in ln for ln in lines), lines
    assert not any(ln.startswith('- "600mm"') and "size 600" in ln for ln in lines), lines


def test_a_hidden_boolean_key_gets_no_candidate_line(session_factory, seeded, stub_access, monkeypatch):
    _seed(session_factory)
    _hide(session_factory, "zz_is_tall")

    block, _t = _run(session_factory, stub_access, monkeypatch, "do you have a zz tall bowl basin", QUIET)

    assert not any("zz_is_tall" in ln for ln in _candidate_lines(block)), block[-500:]


def test_a_spec_the_parser_emits_on_a_hidden_key_is_stripped_before_any_consumer(session_factory, seeded, stub_access, monkeypatch):
    _seed(session_factory)
    _hide(session_factory, "dim_width")
    spec = {"raw": "600mm", "hint": "specification", "canonical_code": None, "spec_key": "dim_width", "spec_value": 600,
            "current_message": True, "confident": True}
    cat = {"raw": "zz basin", "hint": "category", "canonical_code": None, "current_message": True, "confident": True}

    _block, records = _run(session_factory, stub_access, monkeypatch, "600mm wide zz basin", _stock_ask(cat, spec))

    applied = [r for r in records if r.get("kind") == "apply"]
    assert applied, [r.get("kind") or r.get("stage") for r in records]
    entities = (applied[-1].get("verdict") or {}).get("entities") or []
    assert not any(e.get("spec_key") == "dim_width" for e in entities), entities


def test_guard_a_visible_key_is_still_shown_with_its_size_line(session_factory, seeded, stub_access, monkeypatch):
    _seed(session_factory)
    _hide(session_factory, "dim_length")

    block, _t = _run(session_factory, stub_access, monkeypatch, "600mm zz basin", QUIET)

    lines = _candidate_lines(block)
    assert any("spec dim_width = 600" in ln for ln in lines), lines
    assert not any("dim_length" in ln for ln in lines), lines


def test_guard_a_contact_with_no_policy_sees_every_key(session_factory, seeded, stub_access, monkeypatch):
    _seed(session_factory)

    block, _t = _run(session_factory, stub_access, monkeypatch, "600mm zz basin", QUIET)

    assert any("spec dim_width = 600" in ln for ln in _candidate_lines(block)), block[-500:]


def test_gate_off_the_hidden_key_turn_is_unchanged(session_factory, seeded, stub_access, monkeypatch):
    _seed(session_factory)
    _hide(session_factory, "dim_width")

    block, _t = _run(session_factory, stub_access, monkeypatch, "600mm zz basin", QUIET, gate=False)

    assert "Candidates for words" not in block, block[-300:]
