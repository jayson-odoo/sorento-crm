"""The customer's own stock or incoming word decides between the two domains (owner
ruling, hand test 28 Sep 2026: "stock is stock, incoming is incoming"; AC-EO13, AC-EO14).

`domain_words.stock_or_incoming` reads the message BEFORE `apply()`, the same seam
`order_list.order_list_verdict` reads a brand word at. Pure: no database.
"""
from __future__ import annotations

import pytest

from app.services.chatbot.domain_words import stock_or_incoming

from tests.chatbot._turn_helpers import entity, verdict

CODE = "SRTWC286-SH-NEW"


def _v(domain=None, intent=None, **extra):
    quantity = extra.pop("quantity", None)
    return verdict(
        domain_hint=domain,
        intent_hint=intent,
        entities=[entity(CODE, hint="product", quantity=quantity)],
        **extra,
    )


@pytest.mark.parametrize(
    "text",
    [
        f"stock {CODE}",
        f"check stock {CODE}",
        f"stoick {CODE}",
        f"stcok {CODE}",
        f"stok {CODE}",
        f"any stocks for {CODE}?",
        f"{CODE} inventory",
        f"STOCK {CODE}",
    ],
)
def test_a_stock_word_over_an_incoming_reading_is_a_stock_ask(text):
    out, rule = stock_or_incoming(_v("incoming", "check_incoming"), text, carried=[])
    assert out["domain_hint"] == "inventory"
    assert out["intent_hint"] == "check_stock"
    assert rule == "stock_word"


def test_a_stock_word_over_a_carried_incoming_focus_is_a_stock_ask():
    out, rule = stock_or_incoming(_v(), f"stoick {CODE}", carried=["incoming"])
    assert out["domain_hint"] == "inventory"
    assert rule == "stock_word"


def test_a_quantity_over_a_carried_incoming_focus_is_a_stock_ask():
    out, rule = stock_or_incoming(_v(quantity=150), f"{CODE} x 150", carried=["incoming"])
    assert out["domain_hint"] == "inventory"
    assert rule == "stock_quantity"


@pytest.mark.parametrize(
    "text", [f"stick {CODE}", f"stack {CODE}", f"stocking {CODE}", f"sock {CODE}", f"stoc {CODE}"]
)
def test_a_near_word_that_is_another_word_is_not_stock(text):
    v = _v("incoming", "check_incoming")
    out, rule = stock_or_incoming(v, text, carried=[])
    assert out is v and rule is None


@pytest.mark.parametrize(
    "text", [f"incoming {CODE}", f"ETA {CODE}", f"when arriving {CODE}", f"{CODE} shipment"]
)
def test_an_incoming_word_over_a_stock_reading_is_an_incoming_ask(text):
    out, rule = stock_or_incoming(_v("inventory", "check_stock"), text, carried=[])
    assert out["domain_hint"] == "incoming"
    assert out["intent_hint"] == "check_incoming"
    assert rule == "incoming_word"


def test_an_incoming_word_over_a_carried_stock_focus_is_an_incoming_ask():
    out, rule = stock_or_incoming(_v(), f"eta {CODE}", carried=["inventory"])
    assert out["domain_hint"] == "incoming"
    assert rule == "incoming_word"


def test_both_words_leave_the_parser_reading_alone():
    for domain in ("incoming", "inventory"):
        v = _v(domain)
        out, rule = stock_or_incoming(v, f"incoming stock {CODE}", carried=[])
        assert out is v and rule is None
        out, rule = stock_or_incoming(v, f"stock and eta for {CODE}", carried=[])
        assert out is v and rule is None


def test_a_multi_domain_ask_swaps_only_the_wrong_one():
    v = _v(asks=[{"domain": "incoming"}, {"domain": "purchase_order"}])
    out, rule = stock_or_incoming(v, f"stock and PO for {CODE}", carried=[])
    assert [a["domain"] for a in out["asks"]] == ["inventory", "purchase_order"]
    assert rule == "stock_word"


@pytest.mark.parametrize("carried", [[], ["order"], ["incoming"]])
def test_a_stock_word_the_parser_gave_no_domain_is_a_stock_ask(carried):
    """ "stoick X" as the first message: the parser reads no domain off the typo."""
    out, rule = stock_or_incoming(_v(), f"stoick {CODE}", carried=carried)
    assert out["domain_hint"] == "inventory"
    assert rule == "stock_word"


def test_a_parser_reading_of_another_domain_is_never_touched():
    for domain in ("order", "promotion", "master_products", "purchase_order"):
        v = _v(domain)
        out, rule = stock_or_incoming(v, f"stock {CODE}", carried=[])
        assert out is v and rule is None


def test_a_quantity_with_no_carried_incoming_is_left_to_the_parser():
    v = _v(quantity=150)
    out, rule = stock_or_incoming(v, f"{CODE} x 150", carried=["order"])
    assert out is v and rule is None
