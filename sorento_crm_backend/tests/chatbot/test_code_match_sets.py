"""CHATBOT-CODE-MATCH slice 3 (R3): sets through the membership table.

UAC: AC-1, AC-3, AC-23, AC-24 in `documentation/plans/chatbot/chatbot-code-match-acceptance-criteria.md`
("Slice 3"); behaviour card rule R3. Same harness as `test_code_match_dealer_offers.py` (`engine.run_turn`
over seeded Postgres rows). Sets are seeded into `product_sets` / `product_set_members`; the member codes do
not share the set code as a prefix and no letter of any code is read as a role.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.models.product_set import ProductSet, ProductSetMember
from app.services.chatbot.turn.task import REFER_TO_SALESMAN
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests.chatbot._avail_mode_console import Stock, _seed
from tests.chatbot._r9_engine_console import answer, product, reply, stock
from tests.chatbot.test_code_match_dealer_offers import TICK, Console, _console, _option_codes, _word
from tests.chatbot.test_engine import stub_access  # noqa: F401 - a pytest fixture
from tests.chatbot.test_engine_company_scope import _seed_company, _seed_product

pytestmark = pytest.mark.usefixtures("stub_access")

SET = "TWC604-P-RL"
MEMBERS = ["TWCA604-P-RL", "TWCB604-RL"]  # neither starts with the set code


def _make_set(session_factory, code: str, member_ids: list[str], *, company_id: str = DEFAULT_COMPANY_ID) -> str:
    db = session_factory()
    db.info["company_scope"] = frozenset({company_id})
    try:
        product_set = ProductSet(id=str(uuid.uuid4()), set_code=code, name=f"ZZT set {code}", company_id=company_id)
        db.add(product_set)
        db.flush()
        for n, pid in enumerate(member_ids):
            db.add(ProductSetMember(id=str(uuid.uuid4()), product_set_id=product_set.id, product_id=pid, quantity=1, sort_order=n))
        db.commit()
        return product_set.id
    finally:
        db.close()


def _as_staff(c: Console) -> None:
    c.as_staff()
    c.stock_on_hand = 12


def _stocked_ids(c: Console) -> set[str]:
    return {pid for args in c.stock_calls for pid in (args.get("product_ids") or [])}


def _set_console(session_factory, monkeypatch, stub_access, **facts: Stock) -> Console:  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, MEMBERS, **facts)
    _make_set(session_factory, SET, [c.uuid_of[m] for m in MEMBERS])
    return c


# --------------------------------------------------------------------------- AC-1


def test_ac1_a_near_set_code_offers_the_set_then_its_members_and_answers_nothing(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _set_console(session_factory, monkeypatch, stub_access)
    typed = "TWC604RL"  # folded "twc604rl" is not the set folded ("twc604prl")
    text = c.say(f"{typed} x 2", stock(product(typed, 2)))
    assert _option_codes(c) == [SET, *MEMBERS], (_option_codes(c), text)
    assert f"1. {SET}" in text, text
    assert TICK not in text and "Got stock" not in text, f"answered on a guess: {text!r}"
    payload = (c.stored_question or {}).get("payload") or {}
    assert payload.get("stock_qty") == 2, payload
    assert not _stocked_ids(c) - {c.uuid_of[m] for m in MEMBERS}, "a stock read for something other than the members"

    offered = _option_codes(c)
    _as_staff(c)
    c.say(f"{typed} x 2", stock(product(typed, 2)))
    assert _option_codes(c) == offered, (_option_codes(c), offered)


# --------------------------------------------------------------------------- AC-1b


def _full_stock_console(session_factory, monkeypatch, stub_access) -> Console:  # noqa: F811
    return _set_console(
        session_factory, monkeypatch, stub_access, **{"TWCA604_P_RL": Stock(on_hand=100), "TWCB604_RL": Stock(on_hand=100)}
    )


def _pick(*positions: int):
    return reply(reference_positions=list(positions), open_question_answer=answer("pick", picked=list(positions)))


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac1b_picking_the_offered_set_answers_the_set_at_the_carried_quantity(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _full_stock_console(session_factory, monkeypatch, stub_access)
    if who == "staff":
        _as_staff(c)
    reference = c.say("TWC604-P-RL x 2", stock(product("TWC604-P-RL", 2)))  # the exact set ask
    assert "Did you mean" not in reference and c.stored_question is None, reference

    c.state = None
    c.say("TWC604RL x 2", stock(product("TWC604RL", 2)))
    offered = _option_codes(c)
    assert offered[:1] == [SET], offered
    text = c.say("1", _pick(1))
    assert text == reference, (text, reference)


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac1b_picking_a_member_option_answers_that_member_at_the_carried_quantity(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _full_stock_console(session_factory, monkeypatch, stub_access)
    if who == "staff":
        _as_staff(c)
    reference = c.say(f"{MEMBERS[0]} x 2", stock(product(MEMBERS[0], 2)))  # the member asked exactly
    c.state = None
    c.say("TWC604RL x 2", stock(product("TWC604RL", 2)))
    offered = _option_codes(c)
    assert offered == [SET, *MEMBERS], offered
    text = c.say(str(offered.index(MEMBERS[0]) + 1), _pick(offered.index(MEMBERS[0]) + 1))
    assert text == reference, (text, reference)
    if who == "dealer":
        assert text == f"{MEMBERS[0]} x 2: {TICK} Got stock.", text


# --------------------------------------------------------------------------- AC-3


def test_ac3_a_set_typed_with_dashes_folded_is_answered_through_its_members(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _set_console(session_factory, monkeypatch, stub_access, **{"TWCA604_P_RL": Stock(on_hand=100), "TWCB604_RL": Stock(on_hand=100)})
    typed = "TWC604PRL"  # equal to the set code with dashes folded
    text = c.say(f"{typed} x 1", stock(product(typed, 1)))
    assert "Did you mean" not in text, text
    assert REFER_TO_SALESMAN not in text or TICK in text, text
    assert _stocked_ids(c) == {c.uuid_of[m] for m in MEMBERS}, (c.stock_calls, text)
    assert c.stored_question is None, c.stored_question


# --------------------------------------------------------------------------- AC-23


def _hide_member_of_another_company(session_factory, c: Console) -> None:
    """The set's second member now belongs to another company."""
    other = _seed_company(session_factory, name="ZZT Other Co Sets")
    db = session_factory()
    try:
        from sqlalchemy import text as sql_text

        db.execute(sql_text("UPDATE products SET company_id = :o WHERE product_code = :c"), {"o": other, "c": MEMBERS[1]})
        db.commit()
    finally:
        db.close()


def _hide_member_from_chat(session_factory, c: Console) -> None:
    db = session_factory()
    try:
        from sqlalchemy import text as sql_text

        db.execute(sql_text("UPDATE products SET is_searchable = false WHERE product_code = :c"), {"c": MEMBERS[1]})
        db.commit()
    finally:
        db.close()


@pytest.mark.parametrize("hide", [_hide_member_of_another_company, _hide_member_from_chat], ids=["other_company", "hidden_from_chat"])
@pytest.mark.parametrize("typed", ["TWC604PRL", "TWC604RL"], ids=["exact", "near"])
def test_ac23_a_set_with_a_member_the_dealer_cannot_see_is_neither_answered_nor_offered(session_factory, monkeypatch, stub_access, hide, typed):  # noqa: F811
    c = _set_console(session_factory, monkeypatch, stub_access, **{"TWCA604_P_RL": Stock(on_hand=100)})
    hide(session_factory, c)
    text = c.say(f"{typed} x 1", stock(product(typed, 1)))
    assert not _word(SET, text), text
    assert SET not in _option_codes(c) if c.stored_question else True, c.stored_question
    assert c.uuid_of[MEMBERS[1]] not in _stocked_ids(c), "the hidden member was stocked through the set"
    assert f"{MEMBERS[0]} x 1: {TICK}" not in text, f"the set was answered through its visible member alone: {text!r}"


# --------------------------------------------------------------------------- AC-24

#: A family and an X-prefixed sibling the old rule reached by inserting an "X" after the letters.
FAMILY = ["TWC7604-SC", "TWCX7604-P"]


def test_ac24_the_family_rule_no_longer_inserts_an_x_after_the_letters(session_factory):  # noqa: F811
    from app.services import product_code_family
    from tests.chatbot.test_rearch_s3_attribute_first import SORENTO

    _seed(session_factory, FAMILY)
    db = session_factory()
    db.info["company_scope"] = frozenset({SORENTO})
    try:
        codes = [code for code, _values, _text in product_code_family._family_rows(db, "TWC7604")]
    finally:
        db.close()
    assert "TWC7604-SC" in codes, codes
    assert "TWCX7604-P" not in codes, codes


def _family_console(session_factory, monkeypatch, stub_access) -> Console:  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, FAMILY, **{"TWC7604_SC": Stock(on_hand=100), "TWCX7604_P": Stock(on_hand=100)})
    db = session_factory()
    try:
        from sqlalchemy import text as sql_text

        for code, name in (("TWC7604-SC", "ZZT seat cover"), ("TWCX7604-P", "ZZT p trap pan")):
            db.execute(sql_text("UPDATE products SET product_name = :n WHERE product_code = :c"), {"n": name, "c": code})
        db.commit()
    finally:
        db.close()
    return c


def _option_codes_safe(c: Console) -> list[str]:
    return [str(o.get("code")) for o in ((c.stored_question or {}).get("options") or [])]


def test_ac24_without_a_set_the_x_sibling_is_not_silently_picked_and_with_one_it_is_reached(session_factory, monkeypatch, stub_access):  # noqa: F811
    """Staff, "Twc7604 p trap": the family word plus the words that name the X-prefixed sibling. Today only the
    "insert an X after the letters" rule reaches TWCX7604-P (the reply asks "How many units of TWCX7604-P?").
    Without that rule it is offered as a close code or not found, never taken as the answer; with a registered
    set linking the code to that member the message reaches it through the membership table."""
    c = _family_console(session_factory, monkeypatch, stub_access)
    _as_staff(c)
    x_sibling = c.uuid_of["TWCX7604-P"]
    text = c.say("Twc7604 p trap stock x 1", stock(product("Twc7604", 1)))
    assert "How many units of" not in text and f"TWCX7604-P x 1: {TICK}" not in text, f"picked through the X insert: {text!r}"
    assert "Couldn't find" in text, text

    _make_set(session_factory, "TWC7604-P", [x_sibling])
    c.state = None
    text = c.say("Twc7604 p trap stock x 1", stock(product("Twc7604", 1)))
    assert "TWCX7604-P" in text or "TWCX7604-P" in _option_codes_safe(c), text
