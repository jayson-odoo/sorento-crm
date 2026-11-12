"""CHATBOT-CODE-MATCH slice 1 (R1, R6, R7): dealers get did-you-mean offers, and every miss is traced.

Behaviour card: `documentation/plans/chatbot/CARD-chatbot-code-match-12nov.md`; UAC: AC-10 to AC-17 in
`documentation/plans/chatbot/chatbot-code-match-acceptance-criteria.md`.

Today a dealer (availability-only contact, `Profile.stock_availability_only`) whose typed code has no
exact match gets "Please refer to your salesman." with no suggestion, because the dealer path keeps
exact codes only (`engine._exact_codes_only`). The slice feeds the dealer pick
(`dealer_stock.did_you_mean`) the close codes of the dealer's own company.

Driven through `engine.run_turn` over `_avail_mode_console.AvailConsole` (real engine, real resolver over
seeded Postgres rows, the real stock decision; the parser and the tool read are stubbed). Every code below
is a made-up catalogue code of the real shape; no customer, phone or price appears.

Contract assumption for AC-17 (the UAC names the fields in words only): the trace entry is
`{"kind": "code_candidates", "typed": <token>, "candidates": [{"code", "tier", "similarity"}, ...] in
offered order, "outcome": "offered" | "answered"}`. Flexible about extra keys.
"""
from __future__ import annotations

import re
from typing import Any

import pytest

from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot import engine as engine_mod
from app.services.chatbot import turn_runtime
from app.services.chatbot.turn.task import REFER_TO_SALESMAN

from tests.chatbot._avail_mode_console import AvailConsole, Stock, _seed
from tests.chatbot._r9_engine_console import product, stock
from tests.chatbot.test_engine import stub_access  # noqa: F401 - a pytest fixture
from tests.chatbot.test_engine_company_scope import _seed_company, _seed_product

pytestmark = pytest.mark.usefixtures("stub_access")

TICK = "✅"
TARGET = "TWC8354-SH-UF"
TYPO = "SWTWC8354-SH-UF"
#: Near-duplicates of TARGET (trigram well above 0.30 against TYPO), in the dealer's own company.
SIBLINGS = ["TWC8354-SH-UP", "TWC8354-SH-UN", "TWC8354-SH-UX"]


class Console(AvailConsole):
    """An AvailConsole that also keeps each turn's result, so the persisted turn trace can be read."""

    def __init__(self, session_factory, monkeypatch, stub_access, *, extra_codes: list[str], **facts: Stock) -> None:  # noqa: F811
        super().__init__(session_factory, monkeypatch, stub_access, phone="+60100000911", **facts)
        self.codes.update(_seed(session_factory, extra_codes))
        self.uuid_of = {code: pid for pid, code in self.codes.items()}
        self.results: list[Any] = []
        self._monkeypatch = monkeypatch
        real = engine_mod.run_turn

        def spy(*a: Any, **k: Any):
            out = real(*a, **k)
            self.results.append(out)
            return out

        monkeypatch.setattr(engine_mod, "run_turn", spy)

    def as_staff(self) -> None:
        """The same contact read as full-stock staff (not availability-only), a fresh conversation."""
        self._monkeypatch.setattr(turn_runtime, "_stock_availability_only", lambda *a, **k: False)
        self.state = None

    def trace_entries(self, kind: str) -> list[dict[str, Any]]:
        db = self.session_factory()
        try:
            row = db.query(ChatbotTurn).filter(ChatbotTurn.id == self.results[-1].turn_id).one()
            return [r for r in (row.trace or []) if isinstance(r, dict) and r.get("kind") == kind]
        finally:
            db.close()

    def offered(self) -> list[str]:
        question = self.stored_question or {}
        assert question.get("kind") == "product_pick", question
        return [str(o.get("code")) for o in sorted(question.get("options") or [], key=lambda o: o["position"])]


def _console(session_factory, monkeypatch, stub_access, codes: list[str], **facts: Stock) -> Console:  # noqa: F811
    return Console(session_factory, monkeypatch, stub_access, extra_codes=codes, **facts)


def _word(code: str, text: str) -> bool:
    """`code` appears in `text` as a whole code, not inside a longer typed token."""
    return re.search(rf"(?<![A-Z0-9]){re.escape(code)}(?![A-Z0-9-])", text.upper()) is not None


# --------------------------------------------------------------------------- AC-10


def test_ac10_dealer_typo_code_is_offered_its_catalogue_code_with_the_quantity(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, [TARGET])
    text = c.say(f"{TYPO} x 3", stock(product(TYPO, 3)))
    assert f"Couldn't find {TYPO}. Did you mean {TARGET}?" in text, text
    assert REFER_TO_SALESMAN not in text, text
    assert "escalate" not in text.lower(), text
    question = c.stored_question or {}
    assert question.get("kind") == "product_pick", question
    assert [o.get("code") for o in question["options"]] == [TARGET], question
    assert (question.get("payload") or {}).get("stock_qty") == 3, question


# --------------------------------------------------------------------------- AC-11


def test_ac11_dealer_four_close_codes_offers_exactly_three_numbered(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, [TARGET, *SIBLINGS])
    text = c.say(f"{TYPO} x 3", stock(product(TYPO, 3)))
    assert f"Couldn't find {TYPO}. Did you mean:" in text, text
    offered = c.offered()
    assert len(offered) == 3, offered
    assert set(offered) <= {TARGET, *SIBLINGS}, offered
    for i, code in enumerate(offered, 1):
        assert f"{i}. {code}" in text, text
    assert "4." not in text, text
    assert REFER_TO_SALESMAN not in text, text


# --------------------------------------------------------------------------- AC-12


def test_ac12_dealer_close_code_in_another_company_is_never_offered(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, [])
    other = _seed_company(session_factory, name="ZZT Other Co Dym")
    _seed_product(session_factory, company_id=other, code=TARGET)
    text = c.say(f"{TYPO} x 3", stock(product(TYPO, 3)))
    assert REFER_TO_SALESMAN in text, text
    assert "Did you mean" not in text, text
    assert not _word(TARGET, text), text
    question = c.stored_question
    assert not any(TARGET == str(o.get("code")) for o in (question or {}).get("options") or []), question


# --------------------------------------------------------------------------- AC-13


def test_ac13_dealer_no_close_code_keeps_todays_reply(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, [TARGET])
    typed = "QQXZ9917-ZZ"
    text = c.say(f"{typed} x 1", stock(product(typed, 1)))
    assert text == f'Couldn\'t find: "{typed}" (product).\n\n{REFER_TO_SALESMAN}', text
    assert "Did you mean" not in text


# --------------------------------------------------------------------------- AC-14


def test_ac14_staff_miss_offers_the_same_codes_in_the_same_order_as_the_dealer(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, [TARGET, *SIBLINGS])
    dealer_text = c.say(f"{TYPO} x 3", stock(product(TYPO, 3)))
    assert "Did you mean" in dealer_text, dealer_text
    dealer_offered = c.offered()
    assert len(dealer_offered) == 3, dealer_offered

    c.as_staff()
    c.stock_on_hand = 12
    staff_text = c.say(f"{TYPO} x 3", stock(product(TYPO, 3)))
    assert "Did you mean" in staff_text, staff_text
    assert c.offered() == dealer_offered, (c.offered(), dealer_offered)


# --------------------------------------------------------------------------- AC-15


def test_ac15_dealer_two_codes_answers_the_exact_one_and_offers_for_the_miss(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _console(
        session_factory, monkeypatch, stub_access, [TARGET, "TWC8152"], **{"TWC8354_SH_UF": Stock(on_hand=100)}
    )
    text = c.say(
        "TWC8354-SH-UF x 2, SWTWC8152 x 1",
        stock(product(TARGET, 2), product("SWTWC8152", 1)),
    )
    assert f"{TARGET} x 2: {TICK} Got stock." in text, text
    assert "Couldn't find SWTWC8152. Did you mean TWC8152?" in text, text
    assert "Did you mean" in text and text.count("Did you mean") == 1, text


# --------------------------------------------------------------------------- AC-16


def test_ac16_exact_code_is_answered_with_no_offer_for_dealer_and_staff(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _console(
        session_factory, monkeypatch, stub_access, [TARGET, *SIBLINGS], **{"TWC8354_SH_UF": Stock(on_hand=100)}
    )
    text = c.say(f"{TARGET} x 3", stock(product(TARGET, 3)))
    assert text == f"{TARGET} x 3: {TICK} Got stock.", text
    assert c.stored_question is None, c.stored_question

    c.as_staff()
    c.stock_on_hand = 12
    staff_text = c.say(f"{TARGET} x 3", stock(product(TARGET, 3)))
    assert "Did you mean" not in staff_text, staff_text
    assert "Couldn't find" not in staff_text, staff_text
    assert TARGET in staff_text, staff_text


# --------------------------------------------------------------------------- AC-17


def test_ac17_a_miss_writes_a_code_candidates_trace_entry(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, [TARGET, *SIBLINGS])
    c.say(f"{TYPO} x 3", stock(product(TYPO, 3)))
    offered = c.offered()
    entries = c.trace_entries("code_candidates")
    assert len(entries) == 1, entries
    entry = entries[0]
    assert str(entry.get("typed", "")).upper() == TYPO, entry
    candidates = entry.get("candidates")
    assert isinstance(candidates, list) and candidates, entry
    assert [str(row.get("code")) for row in candidates][: len(offered)] == offered, (candidates, offered)
    for row in candidates:
        assert row.get("tier"), row
        assert isinstance(row.get("similarity"), (int, float)) and 0 < row["similarity"] <= 1, row
    assert entry.get("outcome") in ("offered", "answered"), entry
    assert entry["outcome"] == "offered", entry
