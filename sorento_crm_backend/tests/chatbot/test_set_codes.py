"""CHATBOT-SET-CODES: sets typed close, spaced or exact, and family from catalogue links only.

UAC: AC-1, AC-1b, AC-2, AC-3, AC-4, AC-5, AC-7, AC-8, AC-9 in
`documentation/plans/chatbot/chatbot-set-codes-acceptance-criteria.md` (AC-6 is the re-seed of three existing files).
Same harness as `test_code_match_sets.py` (`engine.run_turn` over seeded Postgres rows). Codes are synthetic and keep
the real shape: a set `QWC604-P-RL` holds a pan member `QWCX604-P-RL` and a cistern `QWCY604` shared across sets; no
member code starts with its set code, and no letter of any code is read as a role.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text as sql_text

from app.services.chatbot.turn.task import REFER_TO_SALESMAN

from tests.chatbot._avail_mode_console import Stock
from tests.chatbot._r9_engine_console import product, stock
from tests.chatbot.test_code_match_dealer_offers import TICK, Console, _console, _option_codes, _word
from tests.chatbot.test_code_match_sets import _as_staff, _make_set, _pick, _stocked_ids
from tests.chatbot.test_engine import stub_access  # noqa: F401 - a pytest fixture

pytestmark = pytest.mark.usefixtures("stub_access")

CISTERN = "QWCY604"


def _full(codes: list[str], **discontinued: bool) -> dict[str, Stock]:
    return {c.replace("-", "_"): Stock(on_hand=100, discontinued=c in discontinued) for c in codes}


def _world(
    session_factory, monkeypatch, stub_access, sets: dict[str, list[str]], *, extra: list[str] | None = None, discontinued: list[str] | None = None  # noqa: F811
) -> Console:
    """Every code of `sets` (members) plus `extra` seeded as products with stock; each set registered."""
    members = list(dict.fromkeys(m for ms in sets.values() for m in ms))
    codes = [*members, *(extra or [])]
    facts = _full(codes)
    for code in discontinued or []:
        facts[code.replace("-", "_")] = Stock(on_hand=100, discontinued=True)
    c = _console(session_factory, monkeypatch, stub_access, codes, **facts)
    for set_code, ms in sets.items():
        _make_set(session_factory, set_code, [c.uuid_of[m] for m in ms])
    return c


def _who(c: Console, who: str) -> None:
    if who == "staff":
        _as_staff(c)


def _strings(value: Any) -> list[str]:
    """Every string in a nested trace entry, in document order."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, (list, tuple)):
        return [s for v in value for s in _strings(v)]
    return []


# --------------------------------------------------------------------------- AC-1 / AC-1b

CLOSE_SETS = ["QWC604-P-RL", "QWC604-S-RL", "QWC604-P-RL-NEW", "QWC604-S-RL-NEW"]
CLOSE_MEMBERS = {s: [f"QWCX{s[3:]}", CISTERN] for s in CLOSE_SETS}  # QWC604-P-RL -> QWCX604-P-RL
DISCONTINUED = "QWC609-RL"


def _close_world(session_factory, monkeypatch, stub_access) -> Console:  # noqa: F811
    return _world(session_factory, monkeypatch, stub_access, CLOSE_MEMBERS, extra=[DISCONTINUED], discontinued=[DISCONTINUED])


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac1_several_close_sets_are_offered_as_sets_only_and_nothing_is_answered(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _close_world(session_factory, monkeypatch, stub_access)
    _who(c, who)
    text = c.say("qwc604-rl x 2", stock(product("qwc604-rl", 2)))
    offered = _option_codes(c)
    assert len(offered) == 3 and set(offered) <= set(CLOSE_SETS), (offered, text)
    assert {"QWC604-P-RL", "QWC604-S-RL"} <= set(offered), (offered, text)
    assert not _word(DISCONTINUED, text), text
    assert TICK not in text and "Got stock" not in text, f"answered on a guess: {text!r}"
    if who == "dealer":
        # Staff carry the quantity under their own key (lead sign-off 13 Nov); the staff pick test covers it.
        payload = (c.stored_question or {}).get("payload") or {}
        assert payload.get("stock_qty") == 2, payload
    assert not _stocked_ids(c), "a stock read before the contact chose a set"


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac1_picking_an_offered_set_answers_it_as_typing_its_code_at_x2(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _close_world(session_factory, monkeypatch, stub_access)
    _who(c, who)
    c.say("qwc604-rl x 2", stock(product("qwc604-rl", 2)))
    offered = _option_codes(c)
    assert offered, c.stored_question
    chosen = offered[0]
    picked = c.say("1", _pick(1))

    c.state = None
    reference = c.say(f"{chosen} x 2", stock(product(chosen, 2)))
    assert c.stored_question is None, c.stored_question
    assert picked == reference, (picked, reference)


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac1b_one_close_set_is_offered_first_then_its_members(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    set_code = "QWC605-S-200-RL"
    members = ["QWCX605-S-200-RL", "QWCY605"]
    c = _world(session_factory, monkeypatch, stub_access, {set_code: members})
    _who(c, who)
    c.say("qwc605-s-rl x 1", stock(product("qwc605-s-rl", 1)))
    assert _option_codes(c) == [set_code, *members], _option_codes(c)


# --------------------------------------------------------------------------- AC-2

P_RL = "QWC604-P-RL"
P_RL_MEMBERS = ["QWCX604-P-RL", CISTERN]
NEW_PAN = "QWCX604-P-RL-NEW"


def _space_world(session_factory, monkeypatch, stub_access, *, extra: list[str] | None = None) -> Console:  # noqa: F811
    return _world(session_factory, monkeypatch, stub_access, {P_RL: P_RL_MEMBERS}, extra=[NEW_PAN, *(extra or [])])


@pytest.mark.parametrize("who", ["dealer", "staff"])
@pytest.mark.parametrize("ask", ["qwc604 p rl stock", "QWC604 P RL x 2"], ids=["stock", "x2"])
def test_ac2_a_space_typed_exact_set_is_answered_as_the_set(session_factory, monkeypatch, stub_access, who, ask):  # noqa: F811
    c = _space_world(session_factory, monkeypatch, stub_access)
    _who(c, who)
    typed = re.sub(r"\s+(stock|x 2)$", "", ask)
    text = c.say(ask, stock(product(typed, 2 if "x 2" in ask else None)))
    assert _stocked_ids(c) == {c.uuid_of[m] for m in P_RL_MEMBERS}, (c.stock_calls, text)
    assert "Did you mean" not in text and c.stored_question is None, (text, c.stored_question)
    assert not _word(NEW_PAN, text), text
    assert REFER_TO_SALESMAN not in text, text


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac2_a_space_typed_set_beside_a_found_product_code_is_answered_as_the_set(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _space_world(session_factory, monkeypatch, stub_access, extra=["ZQX5521"])
    _who(c, who)
    text = c.say("QWC604 P RL x 2, ZQX5521 x 1", stock(product("QWC604 P RL", 2), product("ZQX5521", 1)))
    assert _stocked_ids(c) == {c.uuid_of[m] for m in [*P_RL_MEMBERS, "ZQX5521"]}, (c.stock_calls, text)
    assert "Did you mean" not in text and REFER_TO_SALESMAN not in text, text
    assert not _word(NEW_PAN, text), text


# --------------------------------------------------------------------------- AC-3

EXACT = "QWC605-RL"
SIBLINGS = ["QWC605-RL-SOFT", "QWC605-RL-NEW", "QWC605-RL-WEPLS"]
EXACT_SETS = {s: [f"QWCX{s[3:]}", CISTERN] for s in [EXACT, *SIBLINGS]}


def _exact_world(session_factory, monkeypatch, stub_access) -> Console:  # noqa: F811
    return _world(session_factory, monkeypatch, stub_access, EXACT_SETS)


@pytest.mark.parametrize("who", ["dealer", "staff"])
@pytest.mark.parametrize("ask,typed", [("QWC605RL x 1", "QWC605RL"), ("qwc605-rl stock", "qwc605-rl")], ids=["folded_x1", "dashed_stock"])
def test_ac3_an_exact_set_answers_only_itself(session_factory, monkeypatch, stub_access, who, ask, typed):  # noqa: F811
    c = _exact_world(session_factory, monkeypatch, stub_access)
    _who(c, who)
    text = c.say(ask, stock(product(typed, 1)))
    foreign = {c.uuid_of[m] for s in SIBLINGS for m in EXACT_SETS[s][:1]}
    assert not _stocked_ids(c) & foreign, ("a sibling set's member was read", c.stock_calls)
    assert _stocked_ids(c) == {c.uuid_of[m] for m in EXACT_SETS[EXACT]}, c.stock_calls
    for code in [*SIBLINGS, *(EXACT_SETS[s][0] for s in SIBLINGS)]:
        assert not _word(code, text), (code, text)
    # Lead sign-off 13 Nov: a dealer's exact set ask still asks "How many units for each?" on main for a lone set
    # too (CHATBOT-CODE-MATCH R3, members carry no typed quantity); that rule is outside this lane, so the dealer
    # assertion is on the sibling sets only. Crew-ask filed on #2395.
    if who == "staff":
        assert "How many units for each?" not in text, text
    if who == "staff":
        assert len(re.findall(r"(?<![A-Z0-9])QWC605-RL(?![A-Z0-9-])", text.upper())) == 1 or text.upper().count("QWCX605-RL") == 1, text

    c.state = None
    reference = c.say("QWC605-RL x 1", stock(product("QWC605-RL", 1))) if "x 1" in ask else None
    if reference is not None:
        assert text == reference, (text, reference)


# --------------------------------------------------------------------------- AC-4


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac4_a_slash_typed_set_is_never_folded_into_the_set(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _space_world(session_factory, monkeypatch, stub_access)
    _who(c, who)
    c.say("qwc604/p/rl stock", stock(product("qwc604/p/rl")))
    assert _stocked_ids(c) != {c.uuid_of[m] for m in P_RL_MEMBERS}, "answered directly as QWC604-P-RL"


# --------------------------------------------------------------------------- AC-5


def test_ac5_the_family_read_builds_no_pattern_from_the_codes_letters_plus_a_fixed_letter():
    source = (Path(__file__).resolve().parents[2] / "app" / "services" / "product_code_family.py").read_text()
    offenders = [
        line.strip()
        for line in source.splitlines()
        if "letters" in line and re.search(r"\}X|\|\{", line) and not line.lstrip().startswith("#")
    ]
    assert not offenders, offenders


# --------------------------------------------------------------------------- AC-7


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac7_an_x_coded_variant_with_no_catalogue_link_is_never_in_the_reply(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    base, variant = "QWC7704-SC", "QWCX7704-P"
    c = _console(session_factory, monkeypatch, stub_access, [base, variant], **_full([base, variant]))
    db = session_factory()
    try:
        for code, name in {base: "ZZT seat cover", variant: "ZZT p trap pan"}.items():
            db.execute(sql_text("UPDATE products SET product_name = :n WHERE product_code = :c"), {"n": name, "c": code})
        db.commit()
    finally:
        db.close()
    _who(c, who)
    text = c.say("Qwc7704 p trap stock x 1", stock(product("Qwc7704", 1)))
    assert variant not in text, text
    assert c.uuid_of[variant] not in _stocked_ids(c), c.stock_calls


# --------------------------------------------------------------------------- AC-8 / AC-9


@pytest.mark.parametrize("who", ["dealer", "staff"])
@pytest.mark.parametrize("typed", ["QWC604-P-RL", "qwc604 p rl"], ids=["exact", "spaced"])
def test_ac8_a_turn_that_answers_a_set_traces_the_set_and_its_members_in_order(session_factory, monkeypatch, stub_access, who, typed):  # noqa: F811
    c = _space_world(session_factory, monkeypatch, stub_access)
    _who(c, who)
    c.say(f"{typed} x 1", stock(product(typed, 1)))
    entries = c.trace_entries("code_candidates")
    assert len(entries) == 1, entries
    entry = entries[0]
    assert str(entry.get("typed", "")).upper() == typed.upper(), entry
    assert entry.get("outcome") == "answered", entry
    strings = [s for key, v in entry.items() if key not in ("typed", "outcome", "kind") for s in _strings(v)]
    assert P_RL in strings, entry
    positions = [strings.index(m) for m in P_RL_MEMBERS if m in strings]
    assert len(positions) == len(P_RL_MEMBERS) and positions == sorted(positions) and positions[0] > strings.index(P_RL), entry
    dumped = json.dumps(entry)
    assert not any(pid in dumped for pid in c.uuid_of.values()), f"a row id in the trace: {entry}"


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac9_a_turn_that_offers_sets_traces_the_offered_codes_in_order(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _close_world(session_factory, monkeypatch, stub_access)
    _who(c, who)
    c.say("qwc604-rl x 2", stock(product("qwc604-rl", 2)))
    offered = _option_codes(c)
    entries = c.trace_entries("code_candidates")
    assert len(entries) == 1, entries
    assert entries[0].get("outcome") == "offered", entries
    assert [str(r.get("code")) for r in entries[0].get("candidates") or []][: len(offered)] == offered, (entries, offered)


# --------------------------------------------------------------------------- fix round: AC-2b / AC-2c / AC-8b / AC-3 dealer

SOFT = "QWC605-RL-SOFT"
SOFT_MEMBERS = [f"QWCX{SOFT[3:]}", CISTERN]  # QWCX605-RL-SOFT + the shared cistern
PLAIN_PAN = "QWCX605-RL"
SOFT_ASKS = ["qwc605 rl soft stock", "qwc605rl soft stock"]


@pytest.mark.parametrize("who", ["dealer", "staff"])
@pytest.mark.parametrize("ask", SOFT_ASKS, ids=["spaced", "folded"])
def test_ac2b_a_space_typed_set_that_has_prefix_siblings_is_answered_as_that_set(session_factory, monkeypatch, stub_access, who, ask):  # noqa: F811
    c = _exact_world(session_factory, monkeypatch, stub_access)
    _who(c, who)
    typed = ask[: -len(" stock")]  # the parser gives ONE product token: the typed code words
    text = c.say(ask, stock(product(typed)))
    assert "Couldn't find" not in text, text
    assert _stocked_ids(c) == {c.uuid_of[m] for m in SOFT_MEMBERS}, (c.stock_calls, text)
    assert c.uuid_of[PLAIN_PAN] not in _stocked_ids(c), "answered the plain set's pan"
    assert not _word(PLAIN_PAN, text), text
    if who == "staff":
        assert f"Set {SOFT}" in text, text


@pytest.mark.parametrize("who", ["dealer", "staff"])
@pytest.mark.parametrize("ask", SOFT_ASKS, ids=["spaced", "folded"])
def test_ac8b_an_answered_set_event_exists_only_when_the_set_was_answered(session_factory, monkeypatch, stub_access, who, ask):  # noqa: F811
    c = _exact_world(session_factory, monkeypatch, stub_access)
    _who(c, who)
    typed = ask[: -len(" stock")]
    text = c.say(ask, stock(product(typed)))
    for entry in c.trace_entries("code_candidates"):
        mentions_set = SOFT in [s for key, v in entry.items() if key not in ("typed", "kind") for s in _strings(v)]
        if entry.get("outcome") == "answered" and mentions_set:
            assert "Couldn't find" not in text, (entry, text)
            assert {c.uuid_of[m] for m in SOFT_MEMBERS} <= _stocked_ids(c), (entry, c.stock_calls)


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac2c_a_code_plus_a_descriptor_word_never_answers_the_plain_set_as_if_the_word_was_not_said(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    from tests.chatbot._turn_helpers import entity

    c = _exact_world(session_factory, monkeypatch, stub_access)
    _who(c, who)
    text = c.say("QWC605-RL soft x 1", stock(product("QWC605-RL", 1), entity("soft", hint="category")))
    stocked = _stocked_ids(c)
    assert c.uuid_of["QWCX605-RL-SOFT"] in stocked, (c.stock_calls, text)
    assert c.uuid_of[PLAIN_PAN] not in stocked, ("answered the plain set / pan", c.stock_calls, text)
    assert not _word(PLAIN_PAN, text), text


@pytest.mark.xfail(strict=True, reason="owner ruling 13 Nov: slice 2 (new PR) answers each part at the typed quantity")
def test_ac3_dealer_exact_set_does_not_ask_how_many_units_for_each(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _exact_world(session_factory, monkeypatch, stub_access)
    text = c.say("QWC605RL x 1", stock(product("QWC605RL", 1)))
    assert "How many units for each?" not in text, text
