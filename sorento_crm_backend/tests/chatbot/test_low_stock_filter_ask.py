"""LOWSTOCK-FILTER-ASK: a chat low stock ask settles its product category before any run.

`documentation/plans/chatbot/lowstock-filter-ask-behaviour-card.md`, "Ruled behaviour":

* the product category is the ONE required field: taken from the message (a category word,
  narrowed by a brand word, or a brand alone), else asked, and nothing runs until it is
  settled ("all" settles it as the whole book);
* supplier and group-by are never asked: taken in when the message names them, otherwise
  no supplier filter and no grouping;
* every failure ends in a clear line (unknown twice ends the ask; "cancel" cancels).

Full console turns: the REAL engine, lane and MCP presenter; only the parser and the MCP
transport are doubles. Each `say` returns the reply text and every tool call it made, so
"no reorder run before the category is settled" is pinned as "no `crm_low_stock_report`
call on that turn".
"""
from __future__ import annotations

import copy
import json
import re
import uuid
from typing import Any

import pytest

from app.services.chatbot import engine as engine_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.test_engine import CONTACT_ID, _parser_output
from tests.chatbot.test_outstanding_lane import (
    AnswerServices,
    FetchServices,
    _present_response,
    _seed_contact,
)
from tests.chatbot.test_top_selling_round6 import _seed_borrowable_envelope

TOOL = "crm_low_stock_report"
GRANT = "scm.low_stock_report"
SUPPLIER_KEY = "purchase_orders.supplier"
QUESTION = 'Which product category? Reply with a category (e.g. water tap) or "all".'
_SNAKE = re.compile(r"\b[a-z]+_[a-z0-9_]+\b")

READY = {
    "status": "ready",
    "low_count": 3,
    "all_count": 10,
    "as_of": "2026-10-02T08:00:00+08:00",
    "attachments": [{
        "url": "https://cdn.example.com/exports/low-stock/x/low-stock-02102026.xlsx",
        "filename": "low-stock-02102026.xlsx",
        "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "attachmentType": "file",
    }],
}


def _e(raw: str, hint: str) -> dict[str, Any]:
    return {"raw": raw, "hint": hint, "canonical_code": None, "current_message": True, "confident": True}


def _ask(*entities: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    """The parser's reading of a low stock ask (LOW_STOCK_ADDENDUM)."""
    return _parser_output(
        domain_hint="inventory", intent_hint="low_stock_report", entities=list(entities), **overrides
    )


def _reply(*entities: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    """The parser's reading of a short reply: whatever it makes of the bare words."""
    base = dict(message_type="business_query", domain_hint="master_products", intent_hint="check_product",
                entities=list(entities))
    base.update(overrides)
    return _parser_output(**base)


def _stock_ask() -> dict[str, Any]:
    return _parser_output(domain_hint="inventory", intent_hint="check_stock",
                          entities=[_e("CB100", "product"), _e("BRW", "warehouse")])


class Console:
    def __init__(self, session_factory, monkeypatch) -> None:
        self.session_factory, self.monkeypatch = session_factory, monkeypatch
        self.session_vars: dict[str, Any] = {}

    def say(self, qf: dict[str, Any], body: str) -> tuple[str, list[dict[str, Any]]]:
        from app.services.chatbot import console_service
        from app.services.chatbot.head import parser as parser_mod

        self.monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: qf)
        captured: list[tuple[str, dict[str, Any]]] = []
        present = _present_response()

        def _mcp(name: str, args: dict[str, Any]) -> Any:
            captured.append((name, dict(args)))
            if name == TOOL:
                return present(name, json.dumps(READY))
            return json.dumps({"has_result": False, "items": []})

        self.monkeypatch.setattr(engine_mod.business_services, "fetch_services", lambda db: FetchServices(mcp_call=_mcp))
        self.monkeypatch.setattr(
            engine_mod.business_services,
            "answer_services_for",
            lambda session_factory: AnswerServices(
                mcp_probe=lambda name, args: {"data": []}, family_fetch=lambda query: {"data": []}
            ),
        )
        db = self.session_factory()
        try:
            result = console_service.run_console_turn(
                db, contact_respond_id=str(CONTACT_ID), text=body,
                session_vars=copy.deepcopy(self.session_vars), run_id="zzt-lowstock-filter-ask",
            )
        finally:
            db.close()
        self.session_vars = result.session_vars or {}
        text = result.reply_text or ""
        assert not _SNAKE.search(text), (body, text)
        assert "—" not in text and "–" not in text, body
        return text, [args for name, args in captured if name == TOOL]


def _seed(session_factory) -> None:
    from app.models.procurement import Supplier
    from app.models.product import ProductCategory
    from app.services.product_class_signal import CLASS_SYNONYMS
    from tests._mc_lookup_seed import product

    db = session_factory()
    try:
        product(db, company_id=DEFAULT_COMPANY_ID, code="SRTWT7408")
        for code, label, brand in (
            ("SRT-FT", "Tap", "Sorento"),
            ("CB-FT", "Tap", "Cabana"),
            ("SRT-WC", "Water Closet", "Sorento"),
        ):
            db.add(ProductCategory(
                id=str(uuid.uuid4()), category_code=code, category_name=code, class_label=label,
                brand_hint=brand, search_synonyms=CLASS_SYNONYMS[label], company_id=DEFAULT_COMPANY_ID,
            ))
        for code, name in (
            ("JBC", "JINBAICHUAN"),
            ("JBCH", "JINBAICHUAN HARDWARE"),
            ("XTT", "XIAMEN TAIYANG TECHNOLOGY"),
        ):
            db.add(Supplier(id=str(uuid.uuid4()), supplier_code=code, supplier_name=name,
                            company_id=DEFAULT_COMPANY_ID, is_active=True))
        db.commit()
    finally:
        db.close()


@pytest.fixture
def console(session_factory, monkeypatch):
    return _console(session_factory, monkeypatch, grants=[GRANT, SUPPLIER_KEY])


@pytest.fixture
def console_no_supplier_key(session_factory, monkeypatch):
    return _console(session_factory, monkeypatch, grants=[GRANT])


def _console(session_factory, monkeypatch, *, grants: list[str]) -> Console:
    from app.services.chatbot import console_service
    from app.services.chatbot.head import parser as parser_mod

    _seed_contact(session_factory, variables={})
    _seed_borrowable_envelope(session_factory)
    _seed(session_factory)
    monkeypatch.setattr(console_service, "SessionLocal", session_factory)
    monkeypatch.setattr(
        engine_mod,
        "check_access",
        lambda db, *, agent_code, contact_id, space_id: {
            "allowed": True, "decision": "allow", "agent_name": "General",
            "attributes": grants, "all_attributes_allowed": None,
        },
    )
    monkeypatch.setattr(engine_mod, "default_space_id", lambda db: "364817")
    monkeypatch.setattr(
        parser_mod,
        "resolve_config",
        lambda db, *, current_date, override_version_id=None: parser_mod.ParserConfig(
            system_prompt="stub", prompt_version=39, provider="openai", model="gpt-test", api_key="sk-test",
        ),
    )
    return Console(session_factory, monkeypatch)


def _filter_line(text: str) -> str:
    lines = [line for line in text.splitlines() if line.startswith("Category: ")]
    assert len(lines) == 1, text
    return lines[0]


# --------------------------------------------------------------------------- #
# Taken from the message: no question
# --------------------------------------------------------------------------- #


class TestNamedInTheMessage:
    def test_the_owner_example_runs_at_once_scoped_to_the_brand_and_category(self, console) -> None:
        text, calls = console.say(
            _ask(_e("Sorento", "brand"), _e("water tap", "category")), "Sorento water tap low stock list"
        )
        (args,) = calls
        assert args.get("categories") == ["SRT-FT"], args
        assert not args.get("suppliers"), args
        assert args.get("split", "none") == "none", args
        assert QUESTION not in text
        assert _filter_line(text) == "Category: SRT-FT | Supplier: all | Grouping: none"
        assert "Low: 3 of 10 planned products" in text

    def test_a_category_word_alone_takes_every_brand(self, console) -> None:
        _text, calls = console.say(_ask(_e("water tap", "category")), "water tap low stock")
        (args,) = calls
        assert sorted(args["categories"]) == ["CB-FT", "SRT-FT"], args

    def test_a_brand_alone_settles_the_category_as_that_brand(self, console) -> None:
        _text, calls = console.say(_ask(_e("Sorento", "brand")), "Sorento low stock")
        (args,) = calls
        assert sorted(args["categories"]) == ["SRT-FT", "SRT-WC"], args

    def test_all_categories_in_the_message_runs_the_whole_book(self, console) -> None:
        text, calls = console.say(_ask(), "low stock report all categories")
        (args,) = calls
        assert not args.get("categories"), args
        assert _filter_line(text) == "Category: all | Supplier: all | Grouping: none"

    def test_a_supplier_and_a_grouping_in_the_message_are_taken(self, console) -> None:
        text, calls = console.say(
            _ask(_e("water tap", "category")), "low stock water tap jinbaichuan hardware by supplier"
        )
        (args,) = calls
        assert args.get("suppliers") == ["JINBAICHUAN HARDWARE"], args
        assert args.get("split") == "supplier", args
        assert _filter_line(text) == "Category: CB-FT, SRT-FT | Supplier: JINBAICHUAN HARDWARE | Grouping: supplier"

    @pytest.mark.parametrize("words,split", [
        ("by category", "category"),
        ("group by category", "category"),
        ("by supplier and category", "supplier_category"),
        ("by supplier x category", "supplier_category"),
    ])
    def test_grouping_words(self, console, words, split) -> None:
        _text, calls = console.say(_ask(_e("water closet", "category")), f"low stock water closet {words}")
        (args,) = calls
        assert args.get("split") == split, args

    def test_a_product_code_ask_names_its_own_scope(self, console) -> None:
        _text, calls = console.say(_ask(_e("SRTWT7408", "product")), "low stock for SRTWT7408")
        (args,) = calls
        assert args.get("product_codes") == ["SRTWT7408"], args
        assert not args.get("categories"), "a product-code ask is scoped by its code; no category"


# --------------------------------------------------------------------------- #
# Asked: nothing runs until the category is settled
# --------------------------------------------------------------------------- #


class TestAsked:
    def test_a_bare_ask_asks_the_category_and_runs_nothing(self, console) -> None:
        text, calls = console.say(_ask(), "low stock report")
        assert text == QUESTION
        assert calls == [], "no reorder run before the category is settled"

    def test_the_reply_settles_it_and_runs(self, console) -> None:
        console.say(_ask(), "low stock report")
        text, calls = console.say(_reply(_e("water closet", "product")), "water closet")
        (args,) = calls
        assert args.get("categories") == ["SRT-WC"], args
        assert _filter_line(text) == "Category: SRT-WC | Supplier: all | Grouping: none"

    def test_all_runs_the_whole_book(self, console) -> None:
        console.say(_ask(), "low stock report")
        _text, calls = console.say(_reply(intent_hint=None, message_type="casual"), "all")
        (args,) = calls
        assert not args.get("categories"), args

    def test_a_grouping_from_the_first_message_survives_the_question(self, console) -> None:
        console.say(_ask(), "low stock report by supplier")
        _text, calls = console.say(_reply(_e("water closet", "product")), "water closet")
        (args,) = calls
        assert args.get("split") == "supplier", args

    def test_an_unknown_reply_is_said_and_asked_again(self, console) -> None:
        console.say(_ask(), "low stock report")
        text, calls = console.say(_reply(_e("spaceship", "product")), "spaceship")
        assert calls == []
        assert text == f"I don't know 'spaceship' as a category.\n\n{QUESTION}"

    def test_two_misses_end_the_ask_and_free_the_next_message(self, console) -> None:
        console.say(_ask(), "low stock report")
        console.say(_reply(_e("spaceship", "product")), "spaceship")
        text, calls = console.say(_reply(_e("rocket", "product")), "rocket")
        assert calls == []
        assert text == (
            "I still can't place 'rocket'. Ask for the low stock report again with a category or \"all\"."
        )
        _text, calls = console.say(_reply(intent_hint=None, message_type="casual"), "all")
        assert calls == [], "the ask ended; a later 'all' must not start a run"

    def test_cancel(self, console) -> None:
        console.say(_ask(), "low stock report")
        text, calls = console.say(_reply(intent_hint=None, message_type="casual"), "cancel")
        assert calls == [] and text == "Low stock report cancelled."

    def test_a_different_ask_drops_the_question(self, console) -> None:
        console.say(_ask(), "low stock report")
        text, calls = console.say(_stock_ask(), "how many CB100 in BRW")
        assert calls == []
        assert QUESTION not in text
        _text, calls = console.say(_reply(intent_hint=None, message_type="casual"), "all")
        assert calls == [], "the question was dropped; 'all' must not start a run"

    def test_a_category_word_unknown_in_the_message_is_said_and_asked(self, console) -> None:
        text, calls = console.say(_ask(_e("spaceship", "category")), "spaceship low stock")
        assert calls == []
        assert text == f"I don't know 'spaceship' as a category.\n\n{QUESTION}"


# --------------------------------------------------------------------------- #
# Numbered pick on a supplier word naming several suppliers (crew Q5 (a))
# --------------------------------------------------------------------------- #


class TestSupplierPick:
    def test_several_suppliers_are_listed_and_a_number_picks(self, console) -> None:
        text, calls = console.say(_ask(_e("water tap", "category")), "low stock water tap jinbaichuan")
        assert calls == []
        assert text == (
            "Which supplier do you mean? Reply with a number:\n1. JINBAICHUAN\n2. JINBAICHUAN HARDWARE"
        )
        _text, calls = console.say(_reply(intent_hint=None, message_type="casual"), "1")
        (args,) = calls
        assert args.get("suppliers") == ["JINBAICHUAN"], args
        assert sorted(args.get("categories")) == ["CB-FT", "SRT-FT"], args


# --------------------------------------------------------------------------- #
# A contact that may not see suppliers
# --------------------------------------------------------------------------- #


class TestWithoutTheSupplierKey:
    def test_supplier_words_are_not_taken(self, console_no_supplier_key) -> None:
        text, calls = console_no_supplier_key.say(
            _ask(_e("water tap", "category")), "low stock water tap jinbaichuan hardware by supplier and category"
        )
        (args,) = calls
        assert not args.get("suppliers"), args
        assert args.get("split") == "category", args
        assert "JINBAICHUAN" not in text
        assert _filter_line(text) == "Category: CB-FT, SRT-FT | Grouping: category"
