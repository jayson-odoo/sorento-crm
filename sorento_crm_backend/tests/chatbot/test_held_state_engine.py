"""STUCK-QTY-LOOP: the owner's live sequence (4 Oct 2026, 02:56-03:00), through the real
engine (`engine.run_turn`, `tests/chatbot/_r9_engine_console.py`: parser verdict and the
tool reads stubbed, everything else real).

An availability contact with an open "How many units for each?" question asked for a low
stock report, was switched to compact, and sent "clear": every reply was the same stored
quantity question. Each test below is one leg of that sequence.
"""
from __future__ import annotations

import json

import pytest

from app.services.chatbot import turn_runtime

from tests.chatbot._r9_engine_console import EngineConsole, product, reply, stock
from tests.chatbot._turn_helpers import entity, verdict
from tests.chatbot.test_engine import stub_access  # noqa: F401 - a pytest fixture

pytestmark = pytest.mark.usefixtures("stub_access")

ASK = "How many units"
A, B = "SRTWC286-SH-150", "SRTWC286-SH-200"


@pytest.fixture
def console(session_factory, monkeypatch, stub_access):
    return EngineConsole(session_factory, monkeypatch, stub_access, phone="+60000009471")


def _open_the_question(c: EngineConsole) -> None:
    text = c.say(f"check stock {A} {B}", stock(product(A), product(B)))
    assert text.startswith("How many units for each?"), text


def _low_stock_ask():
    return verdict(
        intent_hint="low_stock_report",
        domain_hint="inventory",
        entities=[entity("Sorento", hint="brand"), entity("water tap", hint="category")],
    )


def test_a_low_stock_report_is_never_answered_with_the_quantity_question(console):
    _open_the_question(console)
    first = console.say("low stock report for sorento water tap", _low_stock_ask())
    again = console.say("low stock report for sorento water tap", _low_stock_ask())
    assert ASK not in first, first
    assert ASK not in again, again


def test_the_switch_to_compact_drops_the_question_built_under_availability(console, monkeypatch):
    _open_the_question(console)
    monkeypatch.setattr(turn_runtime, "_stock_availability_only", lambda *a, **k: False)
    console.stock_on_hand = 40
    text = console.say("stock?", reply())
    assert ASK not in text, text


def test_clear_as_a_reset_ends_the_question(console):
    _open_the_question(console)
    text = console.say("clear", verdict(topic_reset=True))
    assert ASK not in text, text
    again = console.say("low stock report for sorento water tap", _low_stock_ask())
    assert ASK not in again, again


def test_clear_the_parser_did_not_flag_never_replays_the_question(console):
    _open_the_question(console)
    text = console.say("clear", verdict(domain_hint="inventory"))
    assert ASK not in text, text


def test_a_genuine_quantity_still_answers_the_question(console):
    _open_the_question(console)
    console.say("10", reply(demand_qty=10))
    calls = [args for name, args in console.tool_calls if name == "crm_inventory_stock_balance_list"]
    assert len(calls) == 2
    sent = calls[-1].get("requested_quantities")
    sent = json.loads(sent) if isinstance(sent, str) else sent
    assert sorted(sent.values()) == [10, 10]
