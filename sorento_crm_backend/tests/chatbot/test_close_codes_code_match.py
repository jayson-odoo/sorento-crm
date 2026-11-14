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

from typing import Any

import pytest

from tests.chatbot._r9_engine_console import product, stock
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
from tests.chatbot.test_code_match_dealer_offers import TICK, _option_codes

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
