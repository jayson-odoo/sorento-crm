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

import json
import re
from typing import Any

import pytest
from sqlalchemy import text as sql_text

from app.models.chatbot_turn import ChatbotTurn
from app.services.ai_assistant_service import MCPRuntimeClient
from app.services.chatbot import engine as engine_mod
from app.services.chatbot import turn_runtime
from app.services.chatbot.turn.task import REFER_TO_SALESMAN

from tests.chatbot._avail_mode_console import AvailConsole, Stock, _seed
from tests.chatbot._r9_engine_console import _present_response, answer, product, reply, stock
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
        """The same contact read as full-stock staff, a fresh conversation. The stock tool answers in the
        compact shape a staff contact gets (`stock_visibility.mode == "compact"`, a `stock_summary` of
        `total_on_hand` per product), the way `_r9_engine_console.EngineConsole.stock_on_hand` does, never
        the dealer's availability block."""
        self._monkeypatch.setattr(turn_runtime, "_stock_availability_only", lambda *a, **k: False)
        self.state = None
        self.stock_on_hand = 12
        present = _present_response()

        def staff_call_tool(client, name: str, args: dict[str, Any]) -> str:
            self.tool_calls.append((name, args))
            if name != "crm_inventory_stock_balance_list":
                return json.dumps({"answers": []})
            summary = [
                {
                    "product_id": pid,
                    "product_code": self.codes[pid],
                    "total_on_hand": self.stock_on_hand,
                    "locations": [{"warehouse_code": "BRW", "quantity_on_hand": self.stock_on_hand}],
                }
                for pid in args.get("product_ids") or []
                if pid in self.codes
            ]
            return present(
                name,
                json.dumps(
                    {
                        "data": [],
                        "pagination": {"total": len(summary), "page": 1, "limit": 50},
                        "stock_visibility": {"mode": "compact", "warehouse_codes": None, "source": "contact"},
                        "stock_summary": summary,
                        "last_updated_at": "2026-09-29T01:00:00",
                    }
                ),
            )

        self._monkeypatch.setattr(MCPRuntimeClient, "call_tool", staff_call_tool)

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
    c = _console(session_factory, monkeypatch, stub_access, [TARGET, *SIBLINGS, "TWC8152"])
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

    # Lead ruling 12 Nov: a staff miss with one close code (the AC-1691 yes/no offer) traces it offered.
    c.as_staff()
    c.stock_on_hand = 12
    c.say("SWTWC8152 x 1", stock(product("SWTWC8152", 1)))
    staff = c.trace_entries("code_candidates")
    assert len(staff) == 1 and staff[0]["outcome"] == "offered", staff
    assert [(row["code"], row.get("outcome")) for row in staff[0]["candidates"]][:1] == [("TWC8152", "offered")], staff


# --------------------------------------------------------------------------- AC-20


def _hide(session_factory, code: str, how: str) -> None:
    """Make `code` unanswerable in chat: inactive, its own is_searchable false, or its category's."""
    db = session_factory()
    try:
        if how == "inactive":
            db.execute(sql_text("UPDATE products SET is_active = false WHERE product_code = :c"), {"c": code})
        elif how == "product_not_searchable":
            db.execute(sql_text("UPDATE products SET is_searchable = false WHERE product_code = :c"), {"c": code})
        else:
            db.execute(
                sql_text(
                    "UPDATE product_categories SET is_searchable = false WHERE id IN "
                    "(SELECT category_id FROM products WHERE product_code = :c)"
                ),
                {"c": code},
            )
        db.commit()
    finally:
        db.close()


@pytest.mark.parametrize("how", ["inactive", "product_not_searchable", "category_not_searchable"])
def test_ac20_dealer_never_offered_an_inactive_or_chat_hidden_code(session_factory, monkeypatch, stub_access, how):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, [TARGET])
    _hide(session_factory, TARGET, how)
    text = c.say(f"{TYPO} x 3", stock(product(TYPO, 3)))
    assert REFER_TO_SALESMAN in text, text
    assert "Did you mean" not in text, text
    assert not _word(TARGET, text), text
    options = (c.stored_question or {}).get("options") or []
    assert not any(str(o.get("code")) == TARGET for o in options), c.stored_question


# --------------------------------------------------------------------------- AC-21, AC-22


def test_ac21_dealer_says_no_to_the_offer_gets_the_refer_line_and_nothing_open(session_factory, monkeypatch, stub_access):  # noqa: F811
    """Lead ruling 12 Nov: today's reply stays (the refer line alone, owner hand test ht26)."""
    c = _console(session_factory, monkeypatch, stub_access, [TARGET], **{"TWC8354_SH_UF": Stock(on_hand=100)})
    first = c.say(f"{TYPO} x 3", stock(product(TYPO, 3)))
    assert f"Did you mean {TARGET}?" in first, first
    stocked_before = len(c.stock_calls)
    text = c.say("no", reply(is_affirmative=False, open_question_answer=answer("no")))
    assert text == REFER_TO_SALESMAN, text
    assert "Got stock" not in text and TICK not in text, text
    assert len(c.stock_calls) == stocked_before, "a stock read ran after the dealer declined the offer"
    assert c.stored_question is None, c.stored_question
    assert not _word(TARGET, text), text


def test_ac22_dealer_says_yes_to_the_offer_gets_the_stock_for_the_typed_quantity(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, [TARGET], **{"TWC8354_SH_UF": Stock(on_hand=100)})
    first = c.say(f"{TYPO} x 3", stock(product(TYPO, 3)))
    assert f"Did you mean {TARGET}?" in first, first
    text = c.say("yes", reply(is_affirmative=True, open_question_answer=answer("yes")))
    assert text == f"{TARGET} x 3: {TICK} Got stock.", text


# --------------------------------------------------------------------------- AC-2b


@pytest.mark.parametrize("typed", ["TWC015SSCR", "TWC015SS CR", "twc015ss-cr"])
def test_ac2b_a_code_differing_only_by_a_dash_or_space_is_answered_directly(session_factory, monkeypatch, stub_access, typed):  # noqa: F811
    code = "TWC015SS-CR"
    c = _console(session_factory, monkeypatch, stub_access, [code], **{"TWC015SS_CR": Stock(on_hand=100)})
    text = c.say(f"{typed} x 2", stock(product(typed, 2)))
    assert text == f"{code} x 2: {TICK} Got stock.", text

    c.as_staff()
    c.stock_on_hand = 12
    staff_text = c.say(f"{typed} x 2", stock(product(typed, 2)))
    assert "Did you mean" not in staff_text, staff_text
    assert "Couldn't find" not in staff_text, staff_text
    assert code in staff_text, staff_text


# --------------------------------------------------------------------------- review round: AC-20b/c, AC-15c/d


def _dym_tail(text: str) -> str:
    """Everything from the first "Did you mean" on (empty when there is none)."""
    at = text.find("Did you mean")
    return text[at:] if at >= 0 else ""


def _option_codes(c: Console) -> list[str]:
    return [str(o.get("code")) for o in ((c.stored_question or {}).get("options") or [])]


def test_ac20b_same_family_inactive_code_is_never_offered_but_its_active_sibling_is(session_factory, monkeypatch, stub_access):  # noqa: F811
    inactive, active = "TWC8354-SH-UF", "TWC8354-SH-UP"
    c = _console(session_factory, monkeypatch, stub_access, [inactive, active])
    _hide(session_factory, inactive, "inactive")
    typed = "TWC8354-SH-UZ"
    for who in ("dealer", "staff"):
        if who == "staff":
            c.as_staff()
            c.stock_on_hand = 12
        text = c.say(f"{typed} x 3", stock(product(typed, 3)))
        assert not _word(inactive, text), (who, text)
        assert inactive not in _option_codes(c), (who, c.stored_question)
        assert _word(active, text), (who, text)
        if who == "dealer":
            assert active in _option_codes(c), (who, c.stored_question)
        else:
            # Lead ruling 12 Nov: AC-1691 stands, one option is a yes/no offer, so the staff
            # question is checked whole (any kind, options or payload) for the inactive code.
            assert inactive not in json.dumps(c.stored_question or {}, default=str), (who, c.stored_question)


def test_ac20c_the_inactive_filter_is_chat_only_list_search_still_resolves_a_typo_to_an_inactive_code(session_factory):  # noqa: F811
    """`resolve_entities_to_filters` (list search tools) reaches the same `_trgm_lookup` through its
    Tier 2.5. A typo of an inactive code resolved to that code there before the slice and must still."""
    from app.services import entity_resolver as er
    from tests.chatbot.test_rearch_s3_attribute_first import SORENTO

    inactive = "TWC8354-SH-UF"
    _seed(session_factory, [inactive])
    _hide(session_factory, inactive, "inactive")
    db = session_factory()
    db.info["company_scope"] = frozenset({SORENTO})
    try:
        buckets = er.resolve_entities_to_filters(db, ["TWC8354SHUZ"], allowed_entity_types=["product"])
    finally:
        db.close()
    assert inactive in buckets.product_codes, (buckets.product_codes, buckets.unresolved, buckets.resolved)


def test_ac15c_a_code_already_answered_is_not_offered_again_for_dealer_and_staff(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, [TARGET], **{"TWC8354_SH_UF": Stock(on_hand=100)})
    ask = f"{TARGET} x 2, {TYPO} x 1"
    parsed = stock(product(TARGET, 2), product(TYPO, 1))
    text = c.say(ask, parsed)
    assert f"{TARGET} x 2: {TICK} Got stock." in text, text
    assert TARGET not in _dym_tail(text), f"dealer: the answered code was offered again: {text!r}"
    assert TARGET not in _option_codes(c), c.stored_question

    c.as_staff()
    c.stock_on_hand = 12
    staff_text = c.say(ask, stock(product(TARGET, 2), product(TYPO, 1)))
    assert TARGET in staff_text, staff_text
    assert TARGET not in _dym_tail(staff_text), f"staff: the answered code was offered again: {staff_text!r}"
    assert TARGET not in _option_codes(c), c.stored_question


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac15d_two_misses_each_get_their_did_you_mean_in_one_numbered_on_reply(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    first, second = "TWC8354-SH-UF", "TWC8152"
    c = _console(session_factory, monkeypatch, stub_access, [first, second])
    if who == "staff":
        c.as_staff()
        c.stock_on_hand = 12
    text = c.say("SWTWC8354-SH-UF x 1, SWTWC8152 x 2", stock(product(TYPO, 1), product("SWTWC8152", 2)))
    assert text.count("Did you mean") == 2, text
    assert f"1. {first}" in text and f"2. {second}" in text, text
    if who == "dealer":
        assert "escalate" not in text.lower(), text
    assert _option_codes(c) == [first, second], c.stored_question
    assert [o["position"] for o in c.stored_question["options"]] == [1, 2], c.stored_question


# --------------------------------------------------------------------------- round 3: two-list pick, near pick, escalation


FIRST, SECOND = "TWC8354-SH-UF", "TWC8152"
TWO_MISSES = f"{TYPO} x 1, SWTWC8152 x 2"


def _two_lists(session_factory, monkeypatch, stub_access) -> tuple[Console, str]:  # noqa: F811
    c = _console(
        session_factory, monkeypatch, stub_access, [FIRST, SECOND],
        **{"TWC8354_SH_UF": Stock(on_hand=100), "TWC8152": Stock(on_hand=100)},
    )
    text = c.say(TWO_MISSES, stock(product(TYPO, 1), product("SWTWC8152", 2)))
    assert text.count("Did you mean") == 2 and _option_codes(c) == [FIRST, SECOND], text
    return c, text


def _group_qtys(c: Console) -> list[Any]:
    payload = (c.stored_question or {}).get("payload") or {}
    return [g.get("qty") for g in payload.get("groups") or []]


def _pick_positions(*positions: int):
    return reply(reference_positions=list(positions), open_question_answer=answer("pick", picked=list(positions)))


def test_ac22b_yes_over_the_two_lists_answers_both_or_re_asks_them_with_both_quantities(session_factory, monkeypatch, stub_access):  # noqa: F811
    c, _ = _two_lists(session_factory, monkeypatch, stub_access)
    text = c.say("yes", reply(is_affirmative=True, open_question_answer=answer("yes")))
    answered_both = f"{FIRST} x 1: {TICK} Got stock." in text and f"{SECOND} x 2: {TICK} Got stock." in text
    if answered_both:
        return
    assert text.count("Did you mean") == 2, f"neither answered nor re-asked as before: {text!r}"
    assert _group_qtys(c) == [1, 2], f"the re-asked pick lost the typed quantities: {c.stored_question}"
    # "1 and 2" after that "yes" answers both, each at its own quantity.
    both = c.say("1 and 2", _pick_positions(1, 2))
    assert f"{FIRST} x 1: {TICK} Got stock." in both, both
    assert f"{SECOND} x 2: {TICK} Got stock." in both, both


def test_ac21b_no_over_the_two_lists_records_both_typed_codes_for_the_salesman(session_factory, monkeypatch, stub_access):  # noqa: F811
    from app.services.chatbot import refer_asks
    from app.services.chatbot.turn.pending import Pending
    from app.services.chatbot.turn.plan import Plan, Trace

    c, _ = _two_lists(session_factory, monkeypatch, stub_access)
    q = c.stored_question
    pending = Pending(
        kind=q["kind"], expects=q.get("expects"), options=q["options"], team=q.get("team"),
        payload=q["payload"], asked_at_turn=q.get("asked_at_turn"),
    )
    trace = Trace()
    trace.rules_fired.append("stock_pick_declined")
    entries = refer_asks.referred_entries(
        referred=True,
        reply_text=REFER_TO_SALESMAN,
        envelopes=[],
        plan=Plan(domains=[], fetch=[], ask=None, denied=[], trace=trace),
        pending_before=pending,
        message_text="no",
        answered=[],
    )
    recorded = {str(e["product_code"]).upper(): e.get("requested_qty") for e in entries}
    assert recorded == {TYPO: 1, "SWTWC8152": 2}, recorded


def test_ac22c_pick_one_over_the_two_lists_answers_it_and_re_asks_the_other_as_a_did_you_mean(session_factory, monkeypatch, stub_access):  # noqa: F811
    c, _ = _two_lists(session_factory, monkeypatch, stub_access)
    text = c.say("1", _pick_positions(1))
    assert f"{FIRST} x 1: {TICK} Got stock." in text, text
    assert "Couldn't find SWTWC8152. Did you mean" in text, text
    assert "which one?" not in text, text
    assert _option_codes(c) == [SECOND], c.stored_question
    payload = (c.stored_question or {}).get("payload") or {}
    assert payload.get("stock_qty") == 2 or 2 in _group_qtys(c), f"quantity 2 was lost: {payload}"


def test_ac20d_the_parsers_near_pick_never_offers_an_inactive_code(session_factory, monkeypatch, stub_access):  # noqa: F811
    inactive, active = "TWC8354-SH-UF", "TWC8354-SH-UP"
    c = _console(session_factory, monkeypatch, stub_access, [inactive, active])
    _hide(session_factory, inactive, "inactive")
    typed = "TWC8354-SH-UZ"
    for who in ("dealer", "staff"):
        if who == "staff":
            c.as_staff()
            c.stock_on_hand = 12
        picked = {**product(typed, 3), "canonical_code": inactive}  # the parser's correction is the inactive code
        text = c.say(f"{typed} x 3", stock(picked))
        assert not _word(inactive, text), (who, text)
        assert inactive not in _option_codes(c), (who, c.stored_question)


def test_ac20e_the_escalation_lanes_product_suggestions_never_list_an_inactive_code(session_factory):  # noqa: F811
    from app.services.chatbot.lanes.escalation_services import product_suggestions
    from tests.chatbot.test_rearch_s3_attribute_first import SORENTO

    inactive, active = "TWC8354-SH-UF", "TWC8354-SH-UP"
    _seed(session_factory, [inactive, active])
    _hide(session_factory, inactive, "inactive")
    db = session_factory()
    db.info["company_scope"] = frozenset({SORENTO})
    try:
        codes = product_suggestions(db, "TWC8354-SH-UZ")
    finally:
        db.close()
    assert active in codes, codes
    assert inactive not in codes, codes
