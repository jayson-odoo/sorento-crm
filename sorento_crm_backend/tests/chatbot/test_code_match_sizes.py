"""CHATBOT-CODE-MATCH slice 4 (R4): a size comes only from a stored value.

UAC: AC-4, AC-5, AC-6, AC-7, AC-25, AC-26 in `documentation/plans/chatbot/chatbot-code-match-acceptance-criteria.md`
("Slice 4"); behaviour card rule R4 (owner 12 Nov: no size is ever assumed). A number in a typed code counts as a size
ONLY when it equals a value stored on a candidate under the category's size key, in that key's registry unit; such a
candidate is OFFERED with its stored size ("Size: 300 mm"), a candidate with no stored value shows "Size: not
recorded", and nothing is answered on a guess.

Generic: each test seeds its OWN registry size key (numeric, mm, scoped to the test category's class through
`applies_when.class`, `matches_bare_size`) and `product_specifications` values. No seeded key and no company letter
is read. Dealer halves run on the AvailConsole; staff halves on the real staff console (`Console.as_staff()`).

Reply layout of the "Size:" line is the contract assumed here: it sits in the candidate's own entry (the option's line
or the lines under it, before the next numbered option).
"""
from __future__ import annotations

import re
import uuid
from typing import Any

import pytest
from sqlalchemy import text as sql_text

from app.models.product_spec import ProductSpecifications, ProductSpecRegistry

from tests.chatbot._avail_mode_console import Stock
from tests.chatbot._r9_engine_console import product, stock
from tests.chatbot.test_code_match_dealer_offers import TICK, Console, _console, _option_codes
from tests.chatbot.test_engine import stub_access  # noqa: F401 - a pytest fixture

pytestmark = pytest.mark.usefixtures("stub_access")

#: The class the AvailConsole's seeded category carries (`_avail_mode_console._seed`: class_label "am").
CLASS = "am"
FAM = "TWC8152-SH-UF"
FAM_300 = "TWC8152-SH-UF-300"


def _seed_sizes(
    c: Console,
    session_factory,
    keys: list[tuple[str, str, str]],
    stored: dict[str, dict[str, float]],
) -> None:
    """Registry keys `(spec_key, label, unit)` scoped to the test class, then each code's stored values."""
    db = session_factory()
    try:
        for spec_key, label, unit in keys:
            db.add(
                ProductSpecRegistry(
                    id=str(uuid.uuid4()), spec_key=spec_key, label=label, data_type="numeric", unit=unit,
                    synonyms={"_self": [label.lower()]}, applies_when={"class": [CLASS]},
                )
            )
        db.flush()
        db.execute(sql_text("UPDATE product_spec_registry SET matches_bare_size = true WHERE spec_key = ANY(:k)"), {"k": [k[0] for k in keys]})
        unit_of = {k[0]: k[2] for k in keys}
        for code, values in stored.items():
            db.add(
                ProductSpecifications(
                    id=str(uuid.uuid4()), product_id=c.uuid_of[code],
                    values={"class": {"value": CLASS}, **{k: {"value": v, "unit": unit_of[k]} for k, v in values.items()}},
                )
            )
        db.commit()
    finally:
        db.close()


def _entry(text: str, code: str) -> str:
    """The candidate's own entry: the line holding `code` as a whole code, and the lines under it up to the next
    numbered option. Empty when the code is not in the reply."""
    lines = text.splitlines()
    pattern = re.compile(rf"(?<![A-Za-z0-9-]){re.escape(code)}(?![A-Za-z0-9-])")
    for i, line in enumerate(lines):
        if pattern.search(line):
            out = [line]
            for follower in lines[i + 1 :]:
                if re.match(r"\s*\d+[.)]\s", follower):
                    break
                out.append(follower)
            return "\n".join(out)
    return ""


def _as_staff(c: Console) -> None:
    c.as_staff()
    c.stock_on_hand = 12


def _size_console(session_factory, monkeypatch, stub_access, codes, stored, keys=None):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, codes, **{k.replace("-", "_"): Stock(on_hand=100) for k in codes})
    _seed_sizes(c, session_factory, keys or [("zz_size", "Size", "mm")], stored)
    return c


# --------------------------------------------------------------------------- AC-4


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac4_a_typed_size_nothing_holds_is_not_answered_and_each_candidate_shows_its_stored_size(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _size_console(session_factory, monkeypatch, stub_access, [FAM, FAM_300], {FAM_300: {"zz_size": 300}})
    if who == "staff":
        _as_staff(c)
    typed = "TWC8152-SH-UF-250"
    text = c.say(f"{typed} x 1", stock(product(typed, 1)))
    assert "Couldn't find" in text and typed in text.split("\n")[0].upper().replace('"', ""), text
    assert TICK not in text and "Got stock" not in text and "Stock summary" not in text, f"answered on a guess: {text!r}"
    assert set(_option_codes(c)) == {FAM, FAM_300}, (_option_codes(c), text)
    assert "Size: not recorded" in _entry(text, FAM), (text, _entry(text, FAM))
    assert "Size: 300 mm" in _entry(text, FAM_300), (text, _entry(text, FAM_300))
    assert "250" not in _entry(text, FAM) and "250" not in _entry(text, FAM_300).replace(typed, ""), text


# --------------------------------------------------------------------------- AC-5


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac5_a_number_in_the_code_equal_to_a_stored_value_is_offered_with_that_size(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    code = "TWC8152-SH-300"
    c = _size_console(session_factory, monkeypatch, stub_access, [code], {code: {"zz_size": 300}})
    if who == "staff":
        _as_staff(c)
    typed = "8152-300-SH"
    text = c.say(f"{typed} x 1", stock(product(typed, 1)))
    if who == "dealer":
        assert _option_codes(c) == [code], (_option_codes(c), text)
    # Staff (AC-1691): the offer is "Reply with a code to continue, or ... escalate?", its pending question the
    # escalation yes/no, which holds no code; the text carries the offer.
    assert code in text and "Size: 300 mm" in text, text
    assert TICK not in text and "Got stock" not in text and "Stock summary" not in text, f"answered on a guess: {text!r}"


# --------------------------------------------------------------------------- AC-6


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac6_a_number_in_the_code_equal_to_no_stored_value_is_not_a_size(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _size_console(session_factory, monkeypatch, stub_access, [FAM, FAM_300], {FAM_300: {"zz_size": 300}})
    if who == "staff":
        _as_staff(c)
    typed = "TWC8152-SH-UF-777"  # 777 is stored on nothing
    text = c.say(f"{typed} x 1", stock(product(typed, 1)))
    assert _option_codes(c), text  # matched as a code only: the family is offered
    assert "777" not in text.replace(typed, ""), text
    assert "None with size" not in text, text
    assert "Size: 777" not in text, text


# --------------------------------------------------------------------------- AC-7


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac7_a_typed_size_no_candidate_holds_names_the_close_codes_with_their_stored_sizes(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _size_console(session_factory, monkeypatch, stub_access, [FAM, FAM_300], {FAM_300: {"zz_size": 300}})
    if who == "staff":
        _as_staff(c)
    typed = "TWC8152-SH-UF-400"
    text = c.say(f"{typed} x 1", stock(product(typed, 1)))
    assert "Couldn't find" in text and typed in text.upper(), text
    assert "None with size" not in text, text
    assert "Size: 300 mm" in _entry(text, FAM_300) and "Size: not recorded" in _entry(text, FAM), text


# --------------------------------------------------------------------------- AC-25


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac25_a_number_stored_under_two_keys_offers_every_match_with_the_key_it_matched(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    long_code, wide_code = "TWC8152-SH-A", "TWC8152-SH-B"
    c = _size_console(
        session_factory, monkeypatch, stub_access, [long_code, wide_code],
        {long_code: {"zz_len": 300}, wide_code: {"zz_wid": 300}},
        keys=[("zz_len", "Length", "mm"), ("zz_wid", "Width", "mm")],
    )
    if who == "staff":
        _as_staff(c)
    typed = "TWC8152-SH-300"
    text = c.say(f"{typed} x 1", stock(product(typed, 1)))
    assert set(_option_codes(c)) == {long_code, wide_code}, (_option_codes(c), text)
    assert "Length: 300 mm" in _entry(text, long_code), (text, _entry(text, long_code))
    assert "Width: 300 mm" in _entry(text, wide_code), (text, _entry(text, wide_code))
    assert TICK not in text and "Stock summary" not in text, text


# --------------------------------------------------------------------------- AC-7b, AC-26: a size the parser read apart from the code


def _closed_lists(monkeypatch) -> None:
    """The parser config the spec-entity turns need (closed lists, the state gate), as the near-code tests set it."""
    import dataclasses

    from app.services.chatbot.head import parser as parser_mod

    real = parser_mod.resolve_config
    monkeypatch.setattr(
        parser_mod, "resolve_config", lambda db, **k: dataclasses.replace(real(db, **k), closed_lists=True, state_block=True)
    )


def _head_plus_size(value: float, unit: str) -> dict[str, Any]:
    head = {"raw": FAM, "hint": "product", "canonical_code": FAM, "current_message": True, "confident": True}
    size = {
        "raw": f"{value:g}{unit}", "hint": "specification", "canonical_code": None, "spec_key": "size",
        "spec_value": value, "spec_unit": unit, "current_message": True, "confident": True,
    }
    return stock(head, size)


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac7b_a_size_the_parser_read_that_no_candidate_holds_is_never_the_bare_none_with_size_line(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _size_console(session_factory, monkeypatch, stub_access, [FAM, FAM_300], {FAM_300: {"zz_size": 300}})
    _closed_lists(monkeypatch)
    if who == "staff":
        _as_staff(c)
    text = c.say(f"{FAM} 400mm stock", _head_plus_size(400, "mm"))
    # A "None with size ..." clause may appear only inside a reply that leads with "Couldn't find" and offers the close
    # codes with their stored sizes; never bare, never followed by an answer for the code with no stored size.
    assert text.startswith("Couldn't find"), text
    assert "Size: 300 mm" in _entry(text, FAM_300) and "Size: not recorded" in _entry(text, FAM), text
    assert "Stock summary" not in text and "How many units of" not in text and TICK not in text, text


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac26_the_none_with_size_line_takes_its_unit_from_the_registry_key(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    """A size key held in centimetres: 30 cm is held by nothing (the variant stores 40), and the line says cm."""
    c = _size_console(
        session_factory, monkeypatch, stub_access, [FAM, FAM_300], {FAM_300: {"zz_size": 40}}, keys=[("zz_size", "Size", "cm")]
    )
    _closed_lists(monkeypatch)
    if who == "staff":
        _as_staff(c)
    text = c.say(f"{FAM} 30cm stock", _head_plus_size(30, "cm"))
    assert text.startswith("Couldn't find"), text
    assert "None with size 30 cm." in text, text
    assert "Size: 40 cm" in _entry(text, FAM_300) and "Size: not recorded" in _entry(text, FAM), text
    assert "Stock summary" not in text and "How many units of" not in text and TICK not in text, text
    assert " mm" not in text, text
