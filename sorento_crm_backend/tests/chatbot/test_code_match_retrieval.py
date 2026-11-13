"""CHATBOT-CODE-MATCH, replay findings (crew's US$0 replay): retrieval that misses and an unintended change.

AC-27: a typed code whose every part is in a catalogue code, in another order, is OFFERED (never answered) although
prefix, substring and trigram all miss it. AC-27b: a typed code that is a substring of one catalogue code is offered,
not answered (behaviour card example `C21120UW-2-MY`). AC-28: a quantity typed with a family code reaches the answer
for the product picked. AC-29: registering a set must not change a family listing's List Price lines.

Dealer halves run on the AvailConsole, staff halves on the real staff console (`Console.as_staff()`).
Codes are made-up catalogue codes of the real shape; no price is real.
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import text as sql_text

from tests.chatbot._avail_mode_console import Stock
from tests.chatbot._r9_engine_console import answer, product, reply, stock
from tests.chatbot._turn_helpers import verdict
from tests.chatbot.test_code_match_dealer_offers import TICK, Console, _console, _option_codes
from tests.chatbot.test_engine import stub_access  # noqa: F401 - a pytest fixture

pytestmark = pytest.mark.usefixtures("stub_access")


def _facts(codes: list[str]) -> dict[str, Stock]:
    return {c.replace("-", "_"): Stock(on_hand=100) for c in codes}


def _pick(*positions: int):
    return reply(reference_positions=list(positions), open_question_answer=answer("pick", picked=list(positions)))


def _requested(c: Console) -> list[Any]:
    out: list[Any] = []
    for args in c.stock_calls:
        wanted = args.get("requested_quantities") or {}
        wanted = json.loads(wanted) if isinstance(wanted, str) else wanted
        out.extend(wanted.values())
    return out


# --------------------------------------------------------------------------- AC-27


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac27_a_code_holding_every_typed_part_in_another_order_is_offered_never_answered(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    target, other_family, unrelated = "SRTWC8152-SH-300", "SRTWC8152-SH-UF", "ZQX5521"  # no stored size on any of them
    codes = [target, other_family, unrelated]
    c = _console(session_factory, monkeypatch, stub_access, codes, **_facts(codes))

    # The gap this test proves: prefix and substring miss it, and the trigram is below the 0.40 floor.
    db = session_factory()
    try:
        sim = db.execute(sql_text("SELECT similarity('8152300sh', 'srtwc8152sh300')")).scalar()
    finally:
        db.close()
    assert sim < 0.40, sim

    if who == "staff":
        c.as_staff()
    typed = "8152-300-SH"
    text = c.say(f"{typed} stock", stock(product(typed)))
    assert target in text and "Did you mean" in text, text
    assert TICK not in text and "Got stock" not in text and "Stock summary" not in text, f"answered on a guess: {text!r}"
    assert other_family not in text, f"offered on 8152 and SH alone, without the 300: {text!r}"
    if who == "dealer":
        assert _option_codes(c) == [target], (_option_codes(c), text)


# --------------------------------------------------------------------------- AC-27b


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac27b_a_code_inside_one_catalogue_code_is_offered_not_answered(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    code = "BRC21120UW-2-MY"
    codes = [code, "ZQX5521"]
    c = _console(session_factory, monkeypatch, stub_access, codes, **_facts(codes))
    if who == "staff":
        c.as_staff()
    typed = "C21120UW-2-MY"
    text = c.say(f"{typed} stock", stock(product(typed)))
    assert f"Did you mean {code}" in text or ("Did you mean" in text and code in text), text
    assert "How many units of" not in text and "Stock summary" not in text and TICK not in text, f"answered: {text!r}"


# --------------------------------------------------------------------------- AC-28

FAMILY = ["SRTWC8608-RL-200", "SRTWC8608-P-RL-200"]


# Staff half removed (lead sign-off, 12 Nov): main (b54b6cc629) also drops the 10 for staff, so it is not this lane's.
@pytest.mark.parametrize("who", ["dealer"])
def test_ac28_the_quantity_typed_with_a_family_code_reaches_the_answer_for_the_picked_product(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, FAMILY, **_facts(FAMILY))
    if who == "staff":
        c.as_staff()
    first = c.say("SRTWC8608 x 10", stock(product("SRTWC8608", 10)))
    offered = _option_codes(c) if c.stored_question and c.stored_question.get("kind") == "product_pick" else []
    if offered:
        picked = offered[0]
        text = c.say("1", _pick(1))
        if who == "dealer":
            assert f"{picked} x 10" in text, (first, text)
    assert 10 in _requested(c), f"quantity 10 never reached a stock read: {c.stock_calls}"


# --------------------------------------------------------------------------- AC-29


def _price_console(session_factory, monkeypatch, stub_access) -> Console:  # noqa: F811
    """Staff console whose product tool answers a price ask the way `presenters._products` does."""
    from app.models.product import Product
    from app.services.ai_assistant_service import MCPRuntimeClient

    c = _console(session_factory, monkeypatch, stub_access, FAMILY, **_facts(FAMILY))
    db = session_factory()
    try:
        for n, code in enumerate(FAMILY, 1):
            db.execute(sql_text("UPDATE products SET list_price = :p WHERE product_code = :c"), {"p": 100 * n, "c": code})
        db.commit()
    finally:
        db.close()
    c.as_staff()
    stock_tool = MCPRuntimeClient.call_tool

    from tests.chatbot._r9_engine_console import _present_response

    present = _present_response()

    def call(client, name: str, args: dict[str, Any]) -> str:
        if "stock" in name or "inventory" in name or "incoming" in name:
            return stock_tool(client, name, args)
        from tests.chatbot.test_rearch_s3_attribute_first import SORENTO

        c.tool_calls.append((name, args))
        db = session_factory()
        db.info["company_scope"] = frozenset({SORENTO})
        try:
            ids = list(args.get("product_ids") or [])
            rows = db.query(Product).filter(Product.id.in_(ids)).order_by(Product.product_code).all() if ids else []
            data = [
                {"id": p.id, "product_code": p.product_code, "product_name": p.product_name, "list_price": float(p.list_price or 0)}
                for p in rows
            ]
        finally:
            db.close()
        return present(name, json.dumps({"data": data, "pagination": {"total": len(data), "page": 1, "limit": 50}}))

    monkeypatch.setattr(MCPRuntimeClient, "call_tool", call)
    return c


def test_ac29_registering_a_set_does_not_change_a_family_listings_list_price_lines(session_factory, monkeypatch, stub_access):  # noqa: F811
    from tests.chatbot.test_code_match_sets import _make_set

    c = _price_console(session_factory, monkeypatch, stub_access)
    ask = verdict(
        domain_hint="master_products", intent_hint="check_product", match_mode="and", user_goal="Srtwc8608 price",
        requested_attributes=["price"], entities=[product("Srtwc8608")],
    )
    before = c.say("Srtwc8608 price", ask)
    assert "List Price" in before, f"control: the listing prints its price lines without a set: {before!r}"
    for code in FAMILY:
        assert code in before, before

    _make_set(session_factory, "SRTWC8608-RL-200", [c.uuid_of[code] for code in FAMILY])
    c.state = None
    after = c.say("Srtwc8608 price", ask)
    prices = lambda t: [line for line in t.splitlines() if "List Price" in line]  # noqa: E731
    assert prices(after) == prices(before), (before, after)


# --------------------------------------------------------------------------- replay review: the offer's order and bound

TARGET = "TWC8152-SH-300"
DECOYS = [f"AAB1{n:02d}300-SH-K" for n in range(25)]  # sort first, hold 300, SH and K, but in the wrong order
#: Closer to "K-300-SH" by trigram than any AAB decoy (0.36 against 0.18), yet sorting after all of them. They hold
#: 300 and SH but no K, so none of the 28 codes holds every typed part in order.
NEAR = ["ZL300-SH", "ZM300-SH", "ZN300-SH"]


def _crowded(session_factory, monkeypatch, stub_access, who: str) -> Console:  # noqa: F811
    codes = [TARGET, *DECOYS, *NEAR]
    c = _console(session_factory, monkeypatch, stub_access, codes, **_facts([TARGET]))
    if who == "staff":
        c.as_staff()
    return c


def _offered_in_order(text: str, known: list[str]) -> list[str]:
    """The catalogue codes the offer names, in the order it names them (the typed echo before "Did you mean" skipped)."""
    at = text.find("Did you mean")
    tail = text[at:] if at >= 0 else ""
    hits = []
    for code in known:
        pos = tail.find(code)
        if pos >= 0:
            hits.append((pos, code))
    return [code for _pos, code in sorted(hits)]


def _folded_similarity(session_factory, folded_typed: str, codes: list[str]) -> dict[str, float]:
    db = session_factory()
    try:
        return {
            code: float(
                db.execute(
                    sql_text("SELECT similarity(regexp_replace(lower(:c), '[^a-z0-9]', '', 'g'), :t)"), {"c": code, "t": folded_typed}
                ).scalar()
            )
            for code in codes
        }
    finally:
        db.close()


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac27c_a_two_part_token_held_by_one_code_is_offered_that_code_first(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _crowded(session_factory, monkeypatch, stub_access, who)
    text = c.say("SH 300 stock", stock(product("SH 300")))
    # "SH 300" folds to "sh300", a substring of exactly one code (the AAB decoys hold "300sh"): a single offer.
    offered = _offered_in_order(text, [TARGET, *DECOYS, *NEAR])
    assert offered == [TARGET], (offered, text)
    assert "AAB" not in text, text
    assert "AAB" not in str(c.stored_question), c.stored_question
    assert TICK not in text and "Stock summary" not in text and "How many units of" not in text, f"answered: {text!r}"


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac27d_the_offer_is_the_closest_codes_by_similarity_not_the_first_alphabetically(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _crowded(session_factory, monkeypatch, stub_access, who)
    catalogue = [TARGET, *DECOYS, *NEAR]
    sims = _folded_similarity(session_factory, "k300sh", catalogue)
    cutoff = sorted(sims.values(), reverse=True)[2]
    assert sims[NEAR[0]] > max(sims[d] for d in DECOYS), sims  # the seed discriminates: closest codes sort last
    text = c.say("K-300-SH stock", stock(product("K-300-SH")))
    offered = _offered_in_order(text, catalogue)
    assert len(offered) == 3, (offered, text)
    assert set(offered) == set(NEAR), (offered, text)  # the three closest sort after all 25 decoys: none cut by a code-ordered limit
    assert all(sims[code] >= cutoff - 1e-9 for code in offered), ({code: sims[code] for code in offered}, cutoff, text)


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac27e_a_typo_the_trigram_tier_already_finds_is_offered_that_code_first(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _crowded(session_factory, monkeypatch, stub_access, who)
    text = c.say("TWC8125-SH-300 stock", stock(product("TWC8125-SH-300")))
    offered = _offered_in_order(text, [TARGET, *DECOYS, *NEAR])
    assert offered[:1] == [TARGET], (offered, text)
