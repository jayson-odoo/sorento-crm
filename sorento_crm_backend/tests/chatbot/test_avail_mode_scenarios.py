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


# ------------------------------------------------------------------ one code


def test_S01_exact_code_covered(console):
    c = console(SRT5674=Stock(on_hand=100))
    assert c.say("SRT5674 x 50 got stock?", stock(product("SRT5674", 50))) == f"SRT5674 x 50: ✅ {REFER}"


def test_S02_exact_code_short_within_the_cap_names_the_count(console):
    c = console(SRT5674=Stock(on_hand=30, x=100))
    assert c.say("SRT5674 x 50", stock(product("SRT5674", 50))) == f"SRT5674 x 50: ✅ 30 available. {REFER}"


def test_S03_exact_code_none_on_hand_shipment_due(console):
    c = console(SRTW2000=Stock(on_hand=0, x=200, eta=ETA))
    assert c.say("SRTW2000 x 150", stock(product("SRTW2000", 150))) == "SRTW2000 x 150: ❌ ETA 19/10/2026."


def test_S04_exact_code_none_on_hand_nothing_incoming(console):
    c = console(SRT5674=Stock(on_hand=0))
    assert c.say("SRT5674 x 5", stock(product("SRT5674", 5))) == f"SRT5674 x 5: ❌ No incoming. {REFER}"


def test_S05_above_the_category_max_says_nothing_of_our_stock(console):
    c = console(CWCX604=Stock(on_hand=30, x=200))
    assert c.say("CWCX604 x 300", stock(product("CWCX604", 300))) == (
        f"CWCX604 x 300: the quantity is more than what I can confirm here. {REFER}"
    )


def test_S06_exact_code_without_a_quantity_asks_for_it(console):
    c = console(SRT5674=Stock(on_hand=100))
    assert c.say("SRT5674 got stock?", stock(product("SRT5674"))) == "How many units of SRT5674?"
    assert c.say("50", reply(demand_qty=50)) == f"SRT5674 x 50: ✅ {REFER}"


# ------------------------------------------------------------------ several codes


def test_S10_all_exact_with_quantities_one_line_each_in_asked_order(console):
    c = console(SRT5674=Stock(on_hand=100), CWCX604=Stock(on_hand=30, x=200), SRTW2000=Stock(eta=ETA))
    out = c.say(
        "SRT5674 x 50, CWCX604 x 40, SRTW2000 x 10",
        stock(product("SRT5674", 50), product("CWCX604", 40), product("SRTW2000", 10)),
    )
    assert out.split("\n\n") == [
        f"SRT5674 x 50: ✅ {REFER}",
        f"CWCX604 x 40: ✅ 30 available. {REFER}",
        "SRTW2000 x 10: ❌ ETA 19/10/2026.",
    ]


def test_S11_exact_and_not_found(console):
    c = console(SRT5674=Stock(on_hand=100))
    out = c.say("SRT5674 x 5, FOO99 x 1", stock(product("SRT5674", 5), product("FOO99", 1)))
    assert out.split("\n\n") == [f"SRT5674 x 5: ✅ {REFER}", "Couldn't find: FOO99."]


def test_S12_exact_and_a_prefix_of_exactly_one_code(console):
    c = console(SRT5674=Stock(on_hand=100), SRTWC287_S_150=Stock(on_hand=9))
    out = c.say("SRT5674 x 5, SRTWC287-S x 3", stock(product("SRT5674", 5), product("SRTWC287-S", 3)))
    assert out.split("\n\n") == [f"SRT5674 x 5: ✅ {REFER}", f"SRTWC287-S-150 x 3: ✅ {REFER}"]


def test_S13_exact_and_vague_answers_the_exact_and_picks_the_vague(console):
    c = console(SRT5674=Stock(on_hand=100), SRTWC286_SH_150=Stock(on_hand=50))
    out = c.say("SRT5674 x 5, srtwc286 x 10", stock(product("SRT5674", 5), product("srtwc286", 10)))
    answered, picker = out.split("\n\n")
    assert answered == f"SRT5674 x 5: ✅ {REFER}"
    assert picker == numbered("srtwc286 x 10: which one?", OWNER_FAMILY[:5]) + (
        "\nand 5 others, reply with the full code."
    ) or picker.splitlines()[0].lower() == "srtwc286 x 10: which one?", picker
    assert c.stored_question["kind"] == "product_pick"
    # The pick answers the vague code alone; the exact one is not asked again.
    out = c.say("2", reply(reference_positions=[2], open_question_answer=answer("pick", picked=[2])))
    assert out == f"SRTWC286-SH-150 x 10: ✅ {REFER}"


def test_S14_vague_and_not_found(console):
    c = console()
    out = c.say("srtwc286 x 10, FOO99 x 1", stock(product("srtwc286", 10), product("FOO99", 1)))
    parts = out.split("\n\n")
    assert parts[0] == "Couldn't find: FOO99."
    assert parts[1].lower().startswith("srtwc286 x 10: which one?"), out


def test_S15_all_not_found(console):
    c = console()
    out = c.say("FOO99 x 1, BAR12 x 2", stock(product("FOO99", 1), product("BAR12", 2)))
    assert out.startswith("Couldn't find: FOO99, BAR12."), out


def test_S16_a_code_named_twice_adds_up_into_one_line(console):
    """Owner Q2 (a)."""
    c = console(SRT5674=Stock(on_hand=100))
    out = c.say("SRT5674 x 2, SRT5674 x 3", stock(product("SRT5674", 2), product("SRT5674", 3)))
    assert out == f"SRT5674 x 5: ✅ {REFER}"


def test_S17_several_codes_without_quantities_ask_point_form_and_name_the_miss(console):
    c = console()
    out = c.say("SRT5674, CWCX604, FOO99 got stock?", stock(product("SRT5674"), product("CWCX604"), product("FOO99")))
    assert out.split("\n\n") == [
        "Couldn't find: FOO99.",
        "How many units for each?\n1. SRT5674 - \n2. CWCX604 - ",
    ]


def test_S18_some_with_quantities_some_without_answers_the_ones_given(console):
    c = console(SRT5674=Stock(on_hand=100), CWCX604=Stock(on_hand=100, x=200))
    out = c.say("SRT5674 x 5 and CWCX604", stock(product("SRT5674", 5), product("CWCX604")))
    assert out.split("\n\n") == [f"SRT5674 x 5: ✅ {REFER}", "How many units of CWCX604?"]
    assert c.say("7", reply(demand_qty=7)) == f"CWCX604 x 7: ✅ {REFER}"


def test_S19_two_vague_codes_one_picker_at_a_time(console):
    """Owner Q3 (a)."""
    c = console()
    out = c.say("srtwc286 x 10, srtwc287 x 4", stock(product("srtwc286", 10), product("srtwc287", 4)))
    assert out.lower().startswith("srtwc286 x 10: which one?"), out
    assert "srtwc287" not in out.lower()


# ------------------------------------------------------------------ ETA asks


def test_S20_eta_ask_several_codes_one_line_each(console):
    c = console(SRTW2000=Stock(eta=ETA))
    out = c.say(
        "ETA SRTW2000 and MWT5727SS-CR",
        reply(entities=[product("SRTW2000"), product("MWT5727SS-CR")], domain_hint="incoming", intent_hint="check_incoming"),
    )
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert "SRTW2000: ETA 19/10/2026" in lines, out
    assert "MWT5727SS-CR: ETA not confirmed yet" in lines, out
