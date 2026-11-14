"""CHATBOT-CLOSE-CODES round 10: the parser's `code_match` on the product entity decides answer vs offer (AC-37).

UAC: `documentation/plans/chatbot/chatbot-close-codes-acceptance-criteria.md` AC-36..39 (owner 14 Nov: no letter,
fuzzy or word-list rule decides answer vs offer; the model judges). With `code_match` on the product entity:
`as_typed` or `named` -> answered; `guessed` -> offered "Did you mean X?" (plus up to 2 more close codes from
retrieval). A missing or unknown value falls back to AC-36 (offered when the parser's code differs from the typed raw
by `turn_state.token_key`; answered when equal but for case, dashes and spaces).

Same harness and stubs as `test_close_codes_dealer_round3.py` (section 6): `engine.run_turn` over seeded Postgres rows
in a blank schema, the parser verdict stubbed with `raw` + `canonical_code` (+ `code_match` here). Dealer and staff.
Codes are made-up catalogue-shaped codes; no customer, phone or price appears.
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import text as sql_text

from tests.chatbot._r9_engine_console import _present_response, product, stock
from tests.chatbot._turn_helpers import verdict
from tests.chatbot.test_close_codes_dealer_round3 import (
    CLOSE3,
    GLD,
    GM,
    GRY,
    INLET,
    WHO,
    R,
    _assert_answered,
    _assert_offered_not_answered,
    _who,
)
from tests.chatbot.test_code_match_dealer_offers import TICK, Console, _console, _option_codes

from tests.chatbot.test_engine import stub_access  # noqa: F401 - a pytest fixture

pytestmark = pytest.mark.usefixtures("stub_access")

#: The catalogue each pick is seeded beside (the round 3 file's seeding for the same raws).
SEEDS = {GLD: [GLD, GRY], GRY: [GLD, GRY], GM: [GM], INLET: [INLET], CLOSE3[0]: CLOSE3[:1]}


def _picked(raw: str, canonical: str, code_match: Any, qty: int | None = None) -> dict[str, Any]:
    """A stock ask whose product entity carries the parser's `canonical_code` and its `code_match` verdict."""
    return stock({**product(raw, qty), "canonical_code": canonical, "code_match": code_match})


def _say(session_factory, monkeypatch, stub_access, who: str, raw: str, code: str, code_match: Any):  # noqa: F811
    c = _who(session_factory, monkeypatch, stub_access, who, SEEDS[code])
    return c, c.say(f"{raw} x 2 stock", _picked(raw, code, code_match, 2))


def _assert_guessed_offer(c, text: str, who: str, raw: str, code: str) -> None:
    """AC-37 `guessed`: "Did you mean X?" with X first, plus up to 2 more close codes; never answered."""
    assert TICK not in text and "Got stock" not in text, f"answered a guessed code: {text!r}"
    assert "Stock summary" not in text and "*Product Code:*" not in text, f"answered a guessed code: {text!r}"
    assert "Did you mean" in text and code in text, text
    if who == "dealer":
        assert f"Couldn't find {raw.upper()}. Did you mean" in text, text
        assert R not in text, text
        options = _option_codes(c)
        assert options and options[0] == code and len(options) <= 3, c.stored_question


# --------------------------------------------------------------------------- named / as_typed -> answered


@WHO
@pytest.mark.parametrize(
    ("raw", "code"),
    [("SRTWT8259 gold", GLD), ("SRTWT8259 grey", GRY), ("SRTWT8259 gun metal", GM)],
    ids=["gold", "grey", "gun_metal"],
)
def test_ac37_named_colour_words_are_answered_directly(session_factory, monkeypatch, stub_access, who, raw, code):  # noqa: F811
    """AC-37: the model says the customer named the code ("gold" for -GLD): answered, though the token_keys differ."""
    _c, text = _say(session_factory, monkeypatch, stub_access, who, raw, code, "named")
    _assert_answered(text, who, code, 2)
    # Lead ruling 14 Nov (d): the named code only, never its seeded sibling (staff answered -GLD and -GRY together).
    for sibling in set(SEEDS[code]) - {code}:
        assert sibling not in text, (sibling, text)


@WHO
@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("SRTWT8259-GLD", GLD),
        ("srtwt 8259 gld", GLD),
        ("SRTWT8259-GLD gold", GLD),
        ("SRTWT8259 GDL", GLD),  # offered without code_match (AC-36); the model's judgement wins (AC-39)
    ],
    ids=["exact", "spaces", "code_and_colour_word", "model_says_as_typed_over_a_letter_swap"],
)
def test_ac37_as_typed_is_answered_directly(session_factory, monkeypatch, stub_access, who, raw, code):  # noqa: F811
    """AC-37: `as_typed` -> answered; no letter-order rule second-guesses the model (AC-39)."""
    _c, text = _say(session_factory, monkeypatch, stub_access, who, raw, code, "as_typed")
    _assert_answered(text, who, code, 2)


# --------------------------------------------------------------------------- guessed -> offered


@WHO
@pytest.mark.parametrize(
    ("raw", "code"),
    [("SRTUB668-BACK INLT", INLET), ("SRTWT8259 gold", GLD)],
    ids=["inlt_typo_word", "gold_guessed"],
)
def test_ac37_guessed_is_offered_did_you_mean(session_factory, monkeypatch, stub_access, who, raw, code):  # noqa: F811
    """AC-37: `guessed` -> offered "Did you mean X?", never answered (the same raw `named` is answered above)."""
    c, text = _say(session_factory, monkeypatch, stub_access, who, raw, code, "guessed")
    _assert_guessed_offer(c, text, who, raw, code)


# --------------------------------------------------------------------------- missing / unknown -> AC-36


@WHO
@pytest.mark.parametrize("code_match", ["maybe", None, ""], ids=["unknown_maybe", "none", "empty"])
def test_ac37_an_unknown_code_match_falls_back_to_ac36_offer(session_factory, monkeypatch, stub_access, who, code_match):  # noqa: F811
    """AC-37 -> AC-36: an unknown value is no verdict; "gold" -> -GLD differs from the typed raw, so it is offered."""
    raw = "SRTWT8259 gold"
    c, text = _say(session_factory, monkeypatch, stub_access, who, raw, GLD, code_match)
    _assert_offered_not_answered(c, text, who, raw, GLD)


@WHO
@pytest.mark.parametrize("code_match", ["maybe", None], ids=["unknown_maybe", "none"])
def test_ac37_an_unknown_code_match_with_spaces_only_is_answered(session_factory, monkeypatch, stub_access, who, code_match):  # noqa: F811
    """AC-37 -> AC-36: equal but for case, dashes and spaces is answered."""
    raw = "srtwc 8354 sh uf"
    _c, text = _say(session_factory, monkeypatch, stub_access, who, raw, CLOSE3[0], code_match)
    _assert_answered(text, who, CLOSE3[0], 2)


# --------------------------------------------------------------------------- round 11 (reviewer on eb71a65f)
#
# R11-1 (blocker): AC-36/37 decide answer vs offer on stock and incoming asks only. On any OTHER ask the family
# narrowing (`product_code_family.narrow_code_tokens`) must read the parser's guessed variant as main does: a code
# typed bare ("SRTWT8259 price") or with a word naming no variant ("golf") is the family, not the parser's guess.
# Measured on origin/main a447d916 with this harness: the staff price ask lists -GLD and -GM for both raws.
# (The dealer price ask on main answers the parser's variant alone, so it is not pinned here.)

PRICE_FAMILY = [GM, GLD]


def _price_console(session_factory, monkeypatch, stub_access, who: str, codes: list[str]) -> Console:  # noqa: F811
    """`test_code_match_retrieval._price_console` over `codes`: the product tool answers a price ask the way
    `presenters._products` does; stock tools stay the console's own."""
    from app.models.product import Product
    from app.services.ai_assistant_service import MCPRuntimeClient
    from tests.chatbot.test_rearch_s3_attribute_first import SORENTO

    c = _console(session_factory, monkeypatch, stub_access, codes, **_facts(codes))
    db = session_factory()
    try:
        for n, code in enumerate(codes, 1):
            db.execute(sql_text("UPDATE products SET list_price = :p WHERE product_code = :c"), {"p": 100 * n, "c": code})
        db.commit()
    finally:
        db.close()
    if who == "staff":
        c.as_staff()
    stock_tool = MCPRuntimeClient.call_tool
    present = _present_response()

    def call(client, name: str, args: dict[str, Any]) -> str:
        if "stock" in name or "inventory" in name or "incoming" in name:
            return stock_tool(client, name, args)
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


def _facts(codes: list[str]):
    from tests.chatbot._avail_mode_console import Stock

    return {code.replace("-", "_"): Stock(on_hand=100) for code in codes}


@pytest.mark.parametrize(
    ("raw", "guessed"), [("SRTWT8259", GM), ("SRTWT8259 golf", GLD)], ids=["bare_code_gm_guessed", "golf_gld_guessed"]
)
def test_r11_1_a_price_ask_with_a_guessed_variant_lists_the_family_as_main(session_factory, monkeypatch, stub_access, raw, guessed):  # noqa: F811
    c = _price_console(session_factory, monkeypatch, stub_access, "staff", PRICE_FAMILY)
    msg = f"{raw} price"
    ask = verdict(
        domain_hint="master_products", intent_hint="check_product", match_mode="and", user_goal=msg,
        requested_attributes=["price"], entities=[{**product(raw), "canonical_code": guessed}],
    )
    text = c.say(msg, ask)
    for code in PRICE_FAMILY:
        assert f"*Product Code:* {code}" in text, f"answered the parser's guess {guessed} alone, main lists the family: {text!r}"
    asked = {c.codes[pid] for name, args in c.tool_calls if "stock" not in name for pid in args.get("product_ids") or []}
    assert asked == set(PRICE_FAMILY), asked


# R11-2: the catalogue-name check (`grounding.picked_code_verdict`'s `name`) must not answer a typed code because the
# picked product's NAME happens to hold the typed words. "SRTWT8259 gold" against a product named "Basin SRTWT8259 Gold
# Finish" (code -GLD), no code_match: the parser's code differs from the typed raw, so it is offered (AC-36). The name
# ask guard (`test_near_code_typo_dym.py::test_q1w_guard_a_name_ask_with_a_parser_pick_is_answered_directly`, raw =
# the whole name, no code typed) stays answered.


@WHO
def test_r11_2_a_typed_code_inside_the_catalogue_name_is_still_offered(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _who(session_factory, monkeypatch, stub_access, who, [GLD])
    db = session_factory()
    try:
        db.execute(sql_text("UPDATE products SET product_name = :n WHERE product_code = :c"),
                   {"n": "Basin SRTWT8259 Gold Finish", "c": GLD})
        db.commit()
    finally:
        db.close()
    raw = "SRTWT8259 gold"
    text = c.say(f"{raw} x 2 stock", stock({**product(raw, 2), "canonical_code": GLD}))
    _assert_offered_not_answered(c, text, who, raw, GLD)
    if who == "staff":
        # Reviewer should-fix: an offer naming -GLD, never a stock answer for it (the staff offer shape is
        # "Did you mean:" then "1. <code> - has stock details").
        assert "Did you mean" in text and GLD in text.split("Did you mean", 1)[1], f"no offer of {GLD}: {text!r}"
        assert "Stock summary" not in text and f"*Product Code:* {GLD}" not in text, f"answered {GLD}: {text!r}"
