"""CHAT-CLOSED-LISTS UNSURE-CODE-KEEPS-DYM (TRAIN cp0-2ab2f7ccc9 "csk11b, got stock ?"; synthetic codes).

Under the gate, an unsure (confident false) product token that HAS resolver neighbours gets the
did-you-mean (`Couldn't find "<word>" (product). Did you mean:` + the neighbour codes), never the
vague "I captured ... couldn't tell which part is which" clarify. An unsure token with no
neighbours keeps the vague clarify. Gate off: unchanged.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import app.main  # noqa: F401  isort:skip
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.ai_assistant_service import MCPRuntimeClient
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import parser as parser_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._pg_fixture import unique_code
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output, seeded, stub_access  # noqa: F401

NEIGHBOURS = ("ZZCSK11", "ZZCSK11A", "ZZCSK11A-BL")


def _seed(session_factory) -> None:
    db = session_factory()
    cat = ProductCategory(
        id=str(uuid.uuid4()), category_code=unique_code("CAT")[:50], category_name="ZZT cat", company_id=DEFAULT_COMPANY_ID,
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each", company_id=DEFAULT_COMPANY_ID)
    db.add_all([cat, uom])
    db.flush()
    for code in NEIGHBOURS:
        db.add(Product(
            id=str(uuid.uuid4()), product_code=code, product_name=f"Name {code}", category_id=cat.id, base_uom_id=uom.id,
            list_price=1, company_id=DEFAULT_COMPANY_ID,
        ))
    db.commit()


def _message(text: str, n: int) -> dict[str, Any]:
    return {
        "event_type": "message.received",
        "contact": {"id": CONTACT_ID},
        "message": {
            "messageId": f"ZZT-usc-{n}-{uuid.uuid4().hex[:6]}", "contactId": CONTACT_ID, "channelId": "whatsapp",
            "traffic": "incoming", "message": {"type": "text", "text": text},
        },
    }


def _turns(session_factory, stub_access, monkeypatch, turns, *, gate: bool):
    def fake_resolve_config(db, *, current_date, override_version_id=None):
        return parser_mod.ParserConfig(
            system_prompt="stub", prompt_version=1, provider="openai", model="m", api_key="k", closed_lists=gate,
        )

    queue = [verdict for _text, verdict in turns]
    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: queue.pop(0))
    monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({DEFAULT_COMPANY_ID}))
    monkeypatch.setattr(
        MCPRuntimeClient, "call_tool", lambda self, name, args: json.dumps({"ok": True, "items": []})
    )
    stub_access()
    return [
        engine_mod.run_turn(_envelope(message=_message(text, n)), session_factory=session_factory)
        for n, (text, _verdict) in enumerate(turns)
    ]


def _unsure(word: str) -> dict:
    return {"raw": word, "hint": "product", "canonical_code": None, "listed_item": None, "current_message": True,
            "confident": False, "hint_confident": True}


def _ask(*entities: dict) -> dict:
    return _parser_output(intent_hint="check_stock", domain_hint="inventory", user_goal="stock", entities=list(entities))


def _text(result) -> str:
    return (result.reply or {}).get("text") or ""


def _assert_did_you_mean(text: str, word: str) -> None:
    assert f'Couldn\'t find "{word}" (product). Did you mean:' in text, text
    assert all(code in text for code in NEIGHBOURS), text
    assert "couldn't tell which part is which" not in text, text


def test_an_unsure_token_with_neighbours_gets_the_did_you_mean_fresh(session_factory, seeded, stub_access, monkeypatch):
    _seed(session_factory)

    [r] = _turns(session_factory, stub_access, monkeypatch, [("zzcsk11b stock?", _ask(_unsure("zzcsk11b")))], gate=True)

    _assert_did_you_mean(_text(r), "zzcsk11b")


def test_an_unsure_token_after_its_own_did_you_mean_gets_the_did_you_mean_again(session_factory, seeded, stub_access, monkeypatch):
    """The s6 lane trace: the previous bot message was the did-you-mean for the same word (an
    open product_pick), the parser re-sends the word unsure."""
    _seed(session_factory)

    [_r1, r2] = _turns(
        session_factory, stub_access, monkeypatch,
        [("zzcsk11b", _ask(_unsure("zzcsk11b"))), ("zzcsk11b, got stock ?", _ask(_unsure("zzcsk11b")))],
        gate=True,
    )

    _assert_did_you_mean(_text(r2), "zzcsk11b")


def test_an_unsure_token_with_no_neighbours_keeps_the_vague_clarify(session_factory, seeded, stub_access, monkeypatch):
    _seed(session_factory)

    [r] = _turns(session_factory, stub_access, monkeypatch, [("qqxjv stock?", _ask(_unsure("qqxjv")))], gate=True)

    text = _text(r)
    assert 'I captured "qqxjv" but couldn\'t tell which part is which' in text, text
    assert "Did you mean" not in text, text


def test_gate_off_the_vague_clarify_is_unchanged(session_factory, seeded, stub_access, monkeypatch):
    _seed(session_factory)

    [r] = _turns(session_factory, stub_access, monkeypatch, [("zzcsk11b stock?", _ask(_unsure("zzcsk11b")))], gate=False)

    assert 'I captured "zzcsk11b" but couldn\'t tell which part is which' in _text(r), _text(r)


def test_control_a_confident_token_gets_the_did_you_mean_so_the_seed_has_neighbours(session_factory, seeded, stub_access, monkeypatch):
    _seed(session_factory)

    [r] = _turns(
        session_factory, stub_access, monkeypatch,
        [("zzcsk11b stock?", _ask({**_unsure("zzcsk11b"), "confident": True}))], gate=True,
    )

    _assert_did_you_mean(_text(r), "zzcsk11b")
