"""CHATBOT-SET-CODES B (slice 2): a dealer's set + quantity answers each part at the typed quantity.

Plan: `documentation/plans/chatbot/PLAN-chatbot-set-quantity-13nov.md`. A dealer who types a registered set with a
quantity gets no "How many units for each?": one availability line per part, in membership order, each as the
single-code availability answer at (part quantity in the set x typed quantity). Staff, a set with no quantity and a
single product are unchanged. Synthetic codes of the real shape; same harness as `test_set_codes.py`.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.product_set import ProductSet, ProductSetMember
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests.chatbot._avail_mode_console import Stock
from tests.chatbot._r9_engine_console import product, stock
from tests.chatbot.test_code_match_dealer_offers import TICK, Console, _console, _option_codes, _word
from tests.chatbot.test_code_match_sets import _as_staff, _pick
from tests.chatbot.test_engine import stub_access  # noqa: F401 - a pytest fixture
from tests.chatbot.test_set_codes import CISTERN, EXACT, EXACT_SETS, P_RL, P_RL_MEMBERS, SIBLINGS

pytestmark = pytest.mark.usefixtures("stub_access")

PAN = "QWCX604-P-RL"
ASK_EACH = "How many units for each?"


def _set_with_quantities(session_factory, code: str, members: list[tuple[str, int]]) -> None:
    db = session_factory()
    db.info["company_scope"] = frozenset({DEFAULT_COMPANY_ID})
    try:
        product_set = ProductSet(id=str(uuid.uuid4()), set_code=code, name=f"ZZT set {code}", company_id=DEFAULT_COMPANY_ID)
        db.add(product_set)
        db.flush()
        for n, (pid, qty) in enumerate(members):
            db.add(ProductSetMember(id=str(uuid.uuid4()), product_set_id=product_set.id, product_id=pid, quantity=qty, sort_order=n))
        db.commit()
    finally:
        db.close()


def _lone(session_factory, monkeypatch, stub_access, *, cistern_qty: int = 1, **facts: Stock) -> Console:  # noqa: F811
    codes = list(P_RL_MEMBERS)
    base = {c.replace("-", "_"): Stock(on_hand=100) for c in codes}
    base.update(facts)
    c = _console(session_factory, monkeypatch, stub_access, codes, **base)
    _set_with_quantities(session_factory, P_RL, [(c.uuid_of[PAN], 1), (c.uuid_of[CISTERN], cistern_qty)])
    return c


def _single(c: Console, code: str, qty: int) -> str:
    """The single-code availability reply, in a fresh state."""
    c.state = None
    return c.say(f"{code} x {qty}", stock(product(code, qty)))


def _lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


def _in_order(text: str, lines: list[str]) -> None:
    got = _lines(text)
    assert all(line in got for line in lines), (lines, text)
    positions = [got.index(line) for line in lines]
    assert positions == sorted(positions), (lines, text)


def test_set_qty_1_a_lone_set_at_x2_answers_each_part_in_membership_order(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _lone(session_factory, monkeypatch, stub_access)
    text = c.say("QWC604-P-RL x 2", stock(product(P_RL, 2)))
    assert ASK_EACH not in text and c.stored_question is None, (text, c.stored_question)
    pan_line, cistern_line = f"{PAN} x 2: {TICK} Got stock.", f"{CISTERN} x 2: {TICK} Got stock."
    assert pan_line in _lines(_single(c, PAN, 2)), "the single-code wording moved"
    _in_order(text, [pan_line, cistern_line])


def test_set_qty_2_a_set_with_longer_siblings_answers_only_its_own_parts(session_factory, monkeypatch, stub_access):  # noqa: F811
    codes = list(dict.fromkeys(m for ms in EXACT_SETS.values() for m in ms))
    c = _console(session_factory, monkeypatch, stub_access, codes, **{m.replace("-", "_"): Stock(on_hand=100) for m in codes})
    for set_code, ms in EXACT_SETS.items():
        _set_with_quantities(session_factory, set_code, [(c.uuid_of[m], 1) for m in ms])
    text = c.say("QWC605RL x 1", stock(product("QWC605RL", 1)))
    own = EXACT_SETS[EXACT]
    assert ASK_EACH not in text, text
    _in_order(text, [f"{m} x 1: {TICK} Got stock." for m in own])
    for sibling in SIBLINGS:
        assert not _word(sibling, text) and not _word(EXACT_SETS[sibling][0], text), (sibling, text)


def test_set_qty_3_a_short_part_is_answered_as_the_single_code_answers_it(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _lone(session_factory, monkeypatch, stub_access, **{CISTERN: Stock(on_hand=1)})
    text = c.say("QWC604-P-RL x 3", stock(product(P_RL, 3)))
    assert ASK_EACH not in text, text
    single = _lines(_single(c, CISTERN, 3))
    assert f"{CISTERN} x 3: {TICK} Got stock." not in single, ("the fixture did not make the cistern short", single)
    assert f"{PAN} x 3: {TICK} Got stock." in _lines(text), text
    assert all(line in _lines(text) for line in single), (single, text)


def test_set_qty_4_a_part_with_set_quantity_2_is_answered_at_the_product(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _lone(session_factory, monkeypatch, stub_access, cistern_qty=2)
    text = c.say("QWC604-P-RL x 3", stock(product(P_RL, 3)))
    assert ASK_EACH not in text, text
    cistern_single = _lines(_single(c, CISTERN, 6))
    assert f"{CISTERN} x 6: {TICK} Got stock." in cistern_single, cistern_single
    pan_line = f"{PAN} x 3: {TICK} Got stock."
    _in_order(text, [pan_line, *cistern_single])


def test_set_qty_5_no_quantity_keeps_the_question(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _lone(session_factory, monkeypatch, stub_access)
    text = c.say("QWC604-P-RL stock", stock(product(P_RL)))
    assert ASK_EACH in text, text


def test_set_qty_6_staff_is_unchanged(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _lone(session_factory, monkeypatch, stub_access)
    _as_staff(c)
    text = c.say("QWC604-P-RL x 2", stock(product(P_RL, 2)))
    assert f"*Set {P_RL}*" in text, text
    assert f"x 2: {TICK} Got stock." not in text, text


def test_set_qty_7_picking_the_offered_set_after_x2_answers_the_same_lines(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _lone(session_factory, monkeypatch, stub_access)
    reference = c.say("QWC604-P-RL x 2", stock(product(P_RL, 2)))
    assert ASK_EACH not in reference, reference
    c.state = None
    c.say("QWC604RL x 2", stock(product("QWC604RL", 2)))
    assert _option_codes(c)[:1] == [P_RL], _option_codes(c)
    text = c.say("1", _pick(1))
    assert text == reference, (text, reference)
