"""AVAIL-MODE-REPLIES regression scenario suite (owner, 2 Oct 2026).

Every stock-asking pattern an availability-only (dealer) contact can send, through the real
engine (`tests/chatbot/_avail_mode_console.py`). The catalogue that names each scenario, and
what full mode does instead, is `tests/chatbot/AVAIL-MODE-SCENARIOS.md`; each test's id
(`S01` ...) is its row there.

Plan: documentation/plans/chatbot/PLAN-avail-mode-replies-02oct.md (behaviour card + owner
rulings Q1-Q5).
"""
from __future__ import annotations

from datetime import date

import pytest

from tests.chatbot._avail_mode_console import AvailConsole, Stock
from tests.chatbot._r9_engine_console import OWNER_FAMILY, answer, numbered, product, reply, stock
from tests.chatbot.test_engine import stub_access  # noqa: F401 - a pytest fixture

pytestmark = pytest.mark.usefixtures("stub_access")

REFER = "Please refer to your salesman."
ETA = date(2026, 10, 19)
NOT_ALL = "Please reply with the number of the code you need."


@pytest.fixture
def console(session_factory, monkeypatch, stub_access):
    def make(**stock_facts: Stock) -> AvailConsole:
        return AvailConsole(
            session_factory, monkeypatch, stub_access, phone="+60000009301", **stock_facts
        )

    return make


# ------------------------------------------------------------------ "all" over a pick


def test_S30_all_over_a_family_pick_is_refused_and_the_list_stays_open(console):
    c = console()
    first = c.say("check stock srtwc286 x 10", stock(product("srtwc286", 10)))
    assert first.startswith("srtwc286 x 10: which one?") or first.startswith("SRTWC286 x 10: which one?"), first
    calls = len(c.stock_calls)

    out = c.say(
        "all",
        reply(broaden_axis="all", entity_op="clear", open_question_answer=answer("all")),
    )

    assert out == NOT_ALL
    assert len(c.stock_calls) == calls, "an 'all' fetches nothing"
    question = c.stored_question
    assert question is not None and question["kind"] == "product_pick"
    assert [o["code"] for o in question["options"]] == OWNER_FAMILY


def test_S31_all_as_a_broaden_alone_is_refused_too(console):
    c = console()
    c.say("check stock srtwc286 x 10", stock(product("srtwc286", 10)))

    out = c.say("all of them", reply(broaden_axis="all", entity_op="clear"))

    assert out == NOT_ALL


def test_S32_picking_every_number_is_allowed_and_answered(console):
    """Owner Q4 (b): only the explicit "all" is refused; "1,2,...,10" is answered."""
    c = console()
    c.say("check stock srtwc286 x 10", stock(product("srtwc286", 10)))

    positions = list(range(1, len(OWNER_FAMILY) + 1))
    out = c.say(
        ",".join(map(str, positions)),
        reply(reference_positions=positions, open_question_answer=answer("pick", picked=positions)),
    )

    lines = out.splitlines()
    for code in OWNER_FAMILY:
        assert any(line.startswith(f"{code} x 10:") for line in lines), (code, out)


def test_S33_all_after_a_refusal_then_a_number_answers_that_code(console):
    c = console(SRTWC286_SH_150=Stock(on_hand=50))
    c.say("check stock srtwc286 x 10", stock(product("srtwc286", 10)))
    assert c.say("all", reply(broaden_axis="all", open_question_answer=answer("all"))) == NOT_ALL

    out = c.say("2", reply(reference_positions=[2], open_question_answer=answer("pick", picked=[2])))

    assert out.startswith("SRTWC286-SH-150 x 10: ✅"), out


@pytest.mark.parametrize("typed", ["all", "All of them", "semua", "all pls"])
def test_S34_all_read_by_the_parser_as_every_position_is_still_refused(console, typed):
    """The live prompt reads "all" / "semua" over a pick as EVERY position; the engine
    reads the bare word itself, so the parser's expansion is not a way round rule 4."""
    c = console()
    c.say("check stock srtwc286 x 10", stock(product("srtwc286", 10)))
    every = list(range(1, len(OWNER_FAMILY) + 1))

    out = c.say(typed, reply(reference_positions=every, open_question_answer=answer("pick", picked=every)))

    assert out == NOT_ALL
