"""R5-1 SIZE-KEYS-BY-DATA, (b) the held family first (TRAIN es-0db8cf0a48; synthetic ZZ codes).

"150mm?" over a held WC: the key the held product's family_code family holds with that number
(trap_length 150 on a sibling) must come first in the size word's candidate line, ahead of keys
other products hold. The candidate block the parser sees is read from its user turn.
"""
from __future__ import annotations

import json
import uuid

import app.main  # noqa: F401  isort:skip
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecifications, ProductSpecRegistry
from app.services.ai_assistant_service import MCPRuntimeClient
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import parser as parser_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._pg_fixture import unique_code
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_closed_lists_spec_over_held import _message, _stock_ask
from tests.chatbot.test_engine import _envelope, seeded, stub_access  # noqa: F401

MM_KEYS = ("board_thickness", "depth", "diameter", "dim_height", "dim_length", "dim_width", "trap_length")
HELD = {"raw": "ZZWC560-SH-UF", "hint": "product", "canonical_code": "ZZWC560-SH-UF", "current_message": True, "confident": True}


def _seed(session_factory) -> None:
    db = session_factory()
    for key in MM_KEYS:
        db.add(ProductSpecRegistry(id=str(uuid.uuid4()), spec_key=key, label=key.title(), data_type="numeric", unit="mm"))
    cat = ProductCategory(
        id=str(uuid.uuid4()), category_code=unique_code("WC")[:50], category_name="ZZT WC", class_label="Water Closet",
        company_id=DEFAULT_COMPANY_ID,
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each", company_id=DEFAULT_COMPANY_ID)
    db.add_all([cat, uom])
    db.flush()
    rows = (
        # code, specs; ZZWC560-LF is a family_code sibling (not prefixed by the held code), 3 others hold dim_length 150
        ("ZZWC560-SH-UF", {"trap_length": 120}),
        ("ZZWC560-LF", {"trap_length": 150}),
        ("ZZWC701", {"dim_length": 150}),
        ("ZZWC702", {"dim_length": 150}),
        ("ZZWC703", {"dim_length": 150}),
    )
    for code, specs in rows:
        p = Product(
            id=str(uuid.uuid4()), product_code=code, product_name=f"Name {code}", category_id=cat.id, base_uom_id=uom.id,
            list_price=1, company_id=DEFAULT_COMPANY_ID,
        )
        db.add(p)
        db.flush()
        db.add(ProductSpecifications(
            id=str(uuid.uuid4()), product_id=p.id, values={k: {"value": v} for k, v in specs.items()},
        ))
    db.commit()


def test_the_held_familys_key_comes_first_in_the_size_words_candidate_line(session_factory, seeded, stub_access, monkeypatch):
    _seed(session_factory)
    blocks: list[str] = []
    queue = [_stock_ask(HELD), _stock_ask()]

    def fake_resolve_config(db, *, current_date, override_version_id=None):
        return parser_mod.ParserConfig(
            system_prompt="stub", prompt_version=1, provider="openai", model="m", api_key="k", closed_lists=True,
        )

    def parse(config, user_block):
        blocks.append(str(user_block))
        return queue.pop(0)

    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", parse)
    monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({DEFAULT_COMPANY_ID}))
    monkeypatch.setattr(MCPRuntimeClient, "call_tool", lambda self, name, args: json.dumps({"ok": True, "items": []}))
    stub_access()

    for n, text in enumerate(("ZZWC560-SH-UF", "is there a 150 mm one?")):
        engine_mod.run_turn(_envelope(message=_message(text, n)), session_factory=session_factory)

    line = next((ln for ln in blocks[1].splitlines() if ln.startswith('- "150 mm"')), "")
    assert line.startswith('- "150 mm": spec trap_length = 150'), (line, blocks[1][-600:])
