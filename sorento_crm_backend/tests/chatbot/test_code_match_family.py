"""CHATBOT-CODE-MATCH slice 5 (AC-24, crew ruling 12 Nov): the family also comes from catalogue data.

The "insert an X after the letters" rule (`product_code_family._family_rows`) STAYS as a fallback, but a family is
also what `products.family_code` says (derived: the text before the first dash, `product_family.family_code_for`;
or set by hand with `family_code_manual`). The codes below have NO X shape: ABD7604-SC is the base, QRS-7604P a
variant whose family_code is (24a) hand-set to ABD7604, or (24b) left derived (no digit before its first dash, so
no family). The control pair TWC7604-SC / TWCX7604-P is today's X-insert family: the data-driven pair must reach its
variant the same way the X insert reaches TWCX7604-P, for dealer and for staff.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text as sql_text

from tests.chatbot._avail_mode_console import Stock
from tests.chatbot._r9_engine_console import product, stock
from tests.chatbot.test_code_match_dealer_offers import Console, _console
from tests.chatbot.test_engine import stub_access  # noqa: F401 - a pytest fixture

pytestmark = pytest.mark.usefixtures("stub_access")

BASE, VARIANT = "ABD7604-SC", "QRS-7604P"
CONTROL_BASE, CONTROL_VARIANT = "TWC7604-SC", "TWCX7604-P"
NAMES = {BASE: "ZZT seat cover", VARIANT: "ZZT p trap pan", CONTROL_BASE: "ZZT seat cover", CONTROL_VARIANT: "ZZT p trap pan"}


def _world(session_factory, monkeypatch, stub_access, *, hand_set: bool) -> Console:  # noqa: F811
    codes = [BASE, VARIANT, CONTROL_BASE, CONTROL_VARIANT]
    c = _console(session_factory, monkeypatch, stub_access, codes, **{k.replace("-", "_"): Stock(on_hand=100) for k in codes})
    db = session_factory()
    try:
        for code, name in NAMES.items():
            db.execute(sql_text("UPDATE products SET product_name = :n WHERE product_code = :c"), {"n": name, "c": code})
        if hand_set:
            db.execute(
                sql_text("UPDATE products SET family_code = 'ABD7604', family_code_manual = true WHERE product_code = :c"),
                {"c": VARIANT},
            )
        db.commit()
    finally:
        db.close()
    return c


def _family_codes(session_factory, word: str) -> list[str]:
    from app.services import product_code_family
    from tests.chatbot.test_rearch_s3_attribute_first import SORENTO

    db = session_factory()
    db.info["company_scope"] = frozenset({SORENTO})
    try:
        return [code for code, _values, _text in product_code_family._family_rows(db, word)]
    finally:
        db.close()


def _ask(c: Console, word: str) -> str:
    c.state = None
    return c.say(f"{word} p trap stock x 1", stock(product(word, 1)))


def _as_data_pair(text: str) -> str:
    """The control family's reply read as the data-driven pair's: its codes and typed word swapped."""
    return (
        text.replace(CONTROL_VARIANT, VARIANT).replace(CONTROL_BASE, BASE).replace("TWC7604", "ABD7604").replace("Twc7604", "Abd7604")
    )


# --------------------------------------------------------------------------- AC-24a


def test_ac24a_the_family_read_includes_a_variant_whose_family_code_was_set_by_hand(session_factory, monkeypatch, stub_access):  # noqa: F811
    _world(session_factory, monkeypatch, stub_access, hand_set=True)
    codes = _family_codes(session_factory, "ABD7604")
    assert BASE in codes, codes
    assert VARIANT in codes, codes


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac24a_a_hand_set_family_variant_is_reached_the_way_the_x_insert_reaches_its_variant(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _world(session_factory, monkeypatch, stub_access, hand_set=True)
    if who == "staff":
        c.as_staff()
    control = _ask(c, "Twc7604")
    reply = _ask(c, "Abd7604")
    assert reply == _as_data_pair(control), (reply, control)
    if who == "staff":
        # Today the X insert reaches the variant for staff; so must the family field.
        assert CONTROL_VARIANT in control and VARIANT in reply, (control, reply)
    assert f"Couldn't find: \"Abd7604\"" not in reply or f"Couldn't find: \"Twc7604\"" in control, reply


# --------------------------------------------------------------------------- AC-24b


def test_ac24b_a_variant_whose_family_code_is_derived_elsewhere_is_not_in_the_family(session_factory, monkeypatch, stub_access):  # noqa: F811
    _world(session_factory, monkeypatch, stub_access, hand_set=False)
    codes = _family_codes(session_factory, "ABD7604")
    assert BASE in codes, codes
    assert VARIANT not in codes, f"guessed into the family: {codes}"


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac24b_a_derived_variant_is_never_guessed_into_the_answer(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _world(session_factory, monkeypatch, stub_access, hand_set=False)
    if who == "staff":
        c.as_staff()
    reply = _ask(c, "Abd7604")
    assert VARIANT not in reply, reply


# --------------------------------------------------------------------------- AC-24d, AC-24e: family through a registered set

SET_WORD = "FAM8826"
SET_CODE = "FAM8826-P"
SET_BASE, MEMBER, OTHER_MEMBER = "FAM8826-SC", "MEMBQ-26P", "HIDQ-26P"  # no member code shares the set's prefix
SET_NAMES = {SET_BASE: "ZZT seat cover", MEMBER: "ZZT p trap pan", OTHER_MEMBER: "ZZT p trap pan"}


def _set_world(session_factory, monkeypatch, stub_access, member_codes: list[str], hide: str | None = None) -> Console:  # noqa: F811
    from tests.chatbot.test_code_match_sets import _make_set

    codes = [SET_BASE, MEMBER, OTHER_MEMBER, CONTROL_BASE, CONTROL_VARIANT]
    c = _console(session_factory, monkeypatch, stub_access, codes, **{k.replace("-", "_"): Stock(on_hand=100) for k in codes})
    db = session_factory()
    try:
        for code, name in {**SET_NAMES, CONTROL_BASE: "ZZT seat cover", CONTROL_VARIANT: "ZZT p trap pan"}.items():
            db.execute(sql_text("UPDATE products SET product_name = :n WHERE product_code = :c"), {"n": name, "c": code})
        if hide == "other_company":
            from tests.chatbot.test_engine_company_scope import _seed_company

            other = _seed_company(session_factory, name="ZZT Other Co Family")
            db.execute(sql_text("UPDATE products SET company_id = :o WHERE product_code = :c"), {"o": other, "c": OTHER_MEMBER})
        elif hide == "hidden_from_chat":
            db.execute(sql_text("UPDATE products SET is_searchable = false WHERE product_code = :c"), {"c": OTHER_MEMBER})
        db.commit()
    finally:
        db.close()
    _make_set(session_factory, SET_CODE, [c.uuid_of[m] for m in member_codes])
    return c


def _as_set_pair(text: str) -> str:
    return (
        text.replace(CONTROL_VARIANT, MEMBER).replace(CONTROL_BASE, SET_BASE).replace("TWC7604", SET_WORD).replace("Twc7604", "Fam8826")
    )


def test_ac24d_the_family_read_includes_a_member_of_a_registered_set_headed_by_the_word(session_factory, monkeypatch, stub_access):  # noqa: F811
    _set_world(session_factory, monkeypatch, stub_access, [MEMBER])
    codes = _family_codes(session_factory, SET_WORD)
    assert SET_BASE in codes and MEMBER in codes, codes


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac24d_a_set_member_is_reached_the_way_the_x_insert_reaches_its_variant(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _set_world(session_factory, monkeypatch, stub_access, [MEMBER])
    if who == "staff":
        c.as_staff()
    control = _ask(c, "Twc7604")
    reply = _ask(c, "Fam8826")
    assert reply == _as_set_pair(control), (reply, control)
    if who == "staff":
        assert MEMBER in reply, reply


@pytest.mark.parametrize("hide", ["other_company", "hidden_from_chat"])
def test_ac24e_a_set_member_the_contact_cannot_see_is_not_in_the_family_read(session_factory, monkeypatch, stub_access, hide):  # noqa: F811
    _set_world(session_factory, monkeypatch, stub_access, [MEMBER, OTHER_MEMBER], hide=hide)
    codes = _family_codes(session_factory, SET_WORD)
    assert OTHER_MEMBER not in codes, codes


@pytest.mark.parametrize("who", ["dealer", "staff"])
@pytest.mark.parametrize("hide", ["other_company", "hidden_from_chat"])
def test_ac24e_a_set_member_the_contact_cannot_see_never_appears_in_the_reply(session_factory, monkeypatch, stub_access, who, hide):  # noqa: F811
    c = _set_world(session_factory, monkeypatch, stub_access, [MEMBER, OTHER_MEMBER], hide=hide)
    if who == "staff":
        c.as_staff()
    reply = _ask(c, "Fam8826")
    assert OTHER_MEMBER not in reply, reply
    assert OTHER_MEMBER not in str(c.stored_question), c.stored_question
