"""Multi-turn carry for report asks, Phase 2 RED tests (MC-1 to MC-12).

`documentation/plans/chatbot/report-multiturn-carry-acceptance-criteria.md`, plan `PLAN-report-multiturn-carry-2nov.md`.

The owner's 14 hand-test turns (2 Nov, #2074) as scripted conversations through the REAL engine, report lane and presenter;
only the parser verdict and the MCP transport are doubles (`bot.say(verdict, message) -> (reply, tool_calls)`, the harness of
`test_sales_account_type_lane.py`). Every verdict below copies the SHAPE the live parser really emitted for that turn
(entity hints, `entity_op`, `sales_basis` vs `basis`, `order_status` label, `continuation`, `ranking_refine`, the declared
pick, the escalation company pick), with the owner's names swapped to invented ones:
two fixture agents, AGENT A and AGENT B, types CABANA / CERAMIC, companies Sorento and Mocha.

Each test replays the turns it needs and names the turn and the slot in its failure message. Invented data only (public repo).
"""
from __future__ import annotations

import uuid
from typing import Any

from app.models.product import Brand
from app.models.sales_agent import SalesAgent
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import MOCHA_ID
from tests.chatbot.test_report_unify_company_lane import _two_companies
from tests.chatbot.test_report_unify_routing import (
    YEAR,
    Routing,
    _status,
    bot,
    console,
)
from tests.chatbot.test_sales_account_type_lane import (
    BASIS_Q,
    BOOK,
    QUESTION,
    _ledger,
)

#: pytest injects these by name (`bot` needs `console`); the tuple is the use pyflakes sees.
_FIXTURES = (bot, console)

AGENT_1 = "AGENT A"  # the owner's first agent (Sorento only)
AGENT_2 = "AGENT B"  # the owner's second agent (a code in both companies)
AGENT_M = "AGENT M"  # an agent only the other company carries
MOCHA_ONLY_TYPE = "ZZTMOCHATYPE"
TOOL = "crm_report_ask"
ALL_2026 = YEAR


# ------------------------------------------------------------------------------------------ world


def _world(bot: Routing) -> tuple[str, str]:
    """The contact holds Sorento and Mocha. Sorento: AGENT A, AGENT B, brands Cabana and Sorento, types CABANA + CERAMIC.
    Mocha: AGENT B, AGENT M, types CERAMIC + a type only it carries. Returns (Sorento's name, Mocha's name)."""
    sorento, mocha = _two_companies(bot)
    db = bot.console.session_factory()
    try:
        for name, company in ((AGENT_2, DEFAULT_COMPANY_ID), (AGENT_2, MOCHA_ID), (AGENT_M, MOCHA_ID)):
            row = SalesAgent(id=str(uuid.uuid4()), sales_agent=name, company_id=company)
            db.add(row)
            bot.ids[f"{name}:{company}"] = row.id
        for code, name in (("CABANA", "Cabana"), ("SORENTO", "Sorento")):
            db.add(Brand(id=str(uuid.uuid4()), brand_code=code, brand_name=name, company_id=DEFAULT_COMPANY_ID))
        db.flush()
        for name, dtype in BOOK:
            _ledger(db, DEFAULT_COMPANY_ID, name, dtype)
        _ledger(db, MOCHA_ID, "ZZT MOCHA LEDGER ONE [A/C III]", "CERAMIC")
        _ledger(db, MOCHA_ID, "ZZT MOCHA LEDGER TWO [A/C IX]", MOCHA_ONLY_TYPE)
        db.commit()
    finally:
        db.close()
    return sorento, mocha


def _agent_b_sorento(bot: Routing) -> str:
    return bot.ids[f"{AGENT_2}:{DEFAULT_COMPANY_ID}"]


# ------------------------------------------------------------------------------------------ the parser's shapes, turn by turn


def _ent(raw: str, hint: str, code: Any = None, kind: Any = None, current: bool = True) -> dict[str, Any]:
    return {"raw": raw, "hint": hint, "canonical_code": code, "kind_said": kind, "current_message": current, "confident": True}


def _pick_of(position: int) -> dict[str, Any]:
    return {"mode": "pick", "items": [], "picked": [position], "qty_for_all": None}


NO_DATES = {"date_filter_start": None, "date_filter_end": None}


def _v(status: str, *entities: dict[str, Any], **over: Any) -> dict[str, Any]:
    """A live verdict: the order label, the entities, the slots the turn said; everything else as the parser leaves it."""
    base: dict[str, Any] = dict(
        basis=None, sales_basis=None, group_by=None, entity_op="replace_combine", continuation=None, ranking_refine=None,
        topic_reset=False, sales_company=None, domain_in_message=False, **NO_DATES,
    )
    base.update(over)
    return _status(status, *entities, **base)


def t1_agent_a_cabana_2026() -> dict[str, Any]:  # "sales for agent a for cabana 2026"
    return _v("sales_report", _ent(AGENT_1, "sales_agent"), _ent("cabana", "brand", "CABANA"), domain_in_message=True, **YEAR)


def t2_invoiced() -> dict[str, Any]:  # "ivoiced"
    return _v("sales_ranking", basis="invoiced", entity_op="reuse", continuation=True, open_question_answer=_pick_of(1))


def t3_account_type() -> dict[str, Any]:  # "account type"
    return _v(
        "sales_ranking", basis="invoiced", group_by="account_type", entity_op="reuse", continuation=True,
        ranking_refine=True, open_question_answer=_pick_of(2),
    )


def t4_by_month() -> dict[str, Any]:  # "breka down by month"
    return _v(
        "sales_analysis", sales_basis="invoiced", group_by="month", entity_op="modify", continuation=True,
        domain_in_message=True,
    )


def t5_ceramic() -> dict[str, Any]:  # "for ceramic"
    return _v(
        "sales_analysis", _ent("ceramic", "account_type"), sales_basis="invoiced", group_by="month",
        entity_op="replace_combine", continuation=True, ranking_refine=True,
    )


def t6_agent_b() -> dict[str, Any]:  # "for slaes agent agent b"
    return _v(
        "sales_analysis", _ent(AGENT_2, "sales_agent"), sales_basis="invoiced", group_by="month",
        entity_op="replace_combine", continuation=True,
    )


def t7_this_year() -> dict[str, Any]:  # "this year"
    return _v(
        "sales_analysis", _ent(AGENT_2, "sales_agent", current=False), sales_basis="invoiced", group_by="month",
        entity_op="reuse", continuation=True, **YEAR,
    )


def t8_company_answer(company: str) -> dict[str, Any]:  # "sorento"
    return _v(
        "sales_ranking", entity_op="reuse", continuation=True, open_question_answer=_pick_of(1),
        escalation={"company_pick": company, "is_escalation_confirmation": False},
    )


def t9_agent_b_again(company: str) -> dict[str, Any]:  # "for slaes agent agent b" (no basis said, no continuation)
    return _v(
        "sales_analysis", _ent(AGENT_2, "sales_agent"), group_by="month", entity_op="replace_combine",
        sales_company=company, domain_in_message=True, **YEAR,
    )


def t11_ceramic_account_type() -> dict[str, Any]:  # "for ceramic account ty[e"
    return _v(
        "sales_analysis", _ent("ceramic", "account_type", None, "account type"), sales_basis="invoiced", group_by="month",
        entity_op="replace_combine", continuation=True, **YEAR,
    )


def t12_company_answer_read_as_brand(company: str) -> dict[str, Any]:  # "sorento" (also tagged a brand word)
    return _v(
        "sales_analysis", _ent("sorento", "brand", "SORENTO"), basis="invoiced", sales_basis="invoiced", group_by="month",
        entity_op="replace_combine", continuation=True, sales_company=company, open_question_answer=_pick_of(1),
    )


def t14_only_agent_b(company: str) -> dict[str, Any]:  # "breakd down by month, only sales agent agent b"
    return _v(
        "sales_analysis", _ent(AGENT_2, "sales_agent"), sales_basis="invoiced", group_by="month",
        entity_op="replace_combine", continuation=True, sales_company=company, domain_in_message=True,
    )


# ------------------------------------------------------------------------------------------ driving


class Convo:
    """Says turns in order, keeps the numbered log so a failure names its turn."""

    def __init__(self, bot: Routing) -> None:
        self.bot = bot
        self.log: list[str] = []

    def say(self, turn: int, verdict: dict[str, Any], message: str) -> tuple[str, list[tuple[str, dict[str, Any]]]]:
        text, calls = self.bot.say(verdict, message)
        ran = [a for n, a in calls if n == TOOL]
        self.log.append(f"T{turn} {message!r}: " + (f"ran {ran[0]}" if ran else f"asked {text.strip()!r}"))
        return text, calls

    def ran(self, turn: int, text: str, calls: list[tuple[str, dict[str, Any]]], slot: str = "the report") -> dict[str, Any]:
        ran = [a for n, a in calls if n == TOOL]
        assert len(ran) == 1, f"turn {turn}: {slot} did not run, the bot asked {text.strip()!r}\n" + "\n".join(self.log)
        return ran[0]


def _first_five(c: Convo) -> None:
    """Turns 1 to 5 of the owner's run, answering what the bot asks (the questions are asserted in MC-1)."""
    c.say(1, t1_agent_a_cabana_2026(), "sales for agent a for cabana 2026")
    c.say(2, t2_invoiced(), "ivoiced")
    c.say(3, t3_account_type(), "account type")
    c.say(4, t4_by_month(), "breka down by month")
    c.say(5, t5_ceramic(), "for ceramic")


def _slots(c: Convo, turn: int, args: dict[str, Any], **want: Any) -> None:
    for slot, value in want.items():
        assert args.get(slot) == value, f"turn {turn}: slot {slot!r} is {args.get(slot)!r}, want {value!r}\n" + "\n".join(c.log)


def _agent_is_sorento_b(c: Convo, bot: Routing, turn: int, args: dict[str, Any]) -> None:
    ids = args.get("sales_agent_ids") or []
    other = bot.ids[f"{AGENT_2}:{MOCHA_ID}"]
    assert _agent_b_sorento(bot) in ids and other not in ids, (
        f"turn {turn}: slot 'sales_agent_ids' is {ids!r}, want only {AGENT_2} of the held company\n" + "\n".join(c.log)
    )


# ------------------------------------------------------------------------------------------ MC-1, MC-2 (guards)


def test_mc1_the_basis_then_the_kind_are_asked_and_the_third_turn_runs_agent_type_year_basis(bot) -> None:
    _world(bot)
    c = Convo(bot)
    text, calls = c.say(1, t1_agent_a_cabana_2026(), "sales for agent a for cabana 2026")
    assert calls == [] and text.strip() == BASIS_Q, f"turn 1: want the basis question, got {text!r}"
    text, calls = c.say(2, t2_invoiced(), "ivoiced")
    assert calls == [] and text.strip() == QUESTION, f"turn 2: want {QUESTION!r}, got {text!r}"
    text, calls = c.say(3, t3_account_type(), "account type")
    args = c.ran(3, text, calls)
    _slots(
        c, 3, args, sales_agent_ids=[bot.ids["agent"]], account_types=["CABANA"], basis="invoiced",
        date_from="2026-01-01", date_to="2026-12-31",
    )


def test_mc2_a_breakdown_and_a_new_type_keep_the_rest(bot) -> None:
    _world(bot)
    c = Convo(bot)
    c.say(1, t1_agent_a_cabana_2026(), "sales for agent a for cabana 2026")
    c.say(2, t2_invoiced(), "ivoiced")
    c.say(3, t3_account_type(), "account type")
    text, calls = c.say(4, t4_by_month(), "breka down by month")
    args = c.ran(4, text, calls)
    _slots(
        c, 4, args, group_by="month", sales_agent_ids=[bot.ids["agent"]], account_types=["CABANA"], basis="invoiced",
        date_from="2026-01-01", date_to="2026-12-31",
    )
    text, calls = c.say(5, t5_ceramic(), "for ceramic")
    args = c.ran(5, text, calls)
    _slots(
        c, 5, args, group_by="month", sales_agent_ids=[bot.ids["agent"]], account_types=["CERAMIC"], basis="invoiced",
        date_from="2026-01-01", date_to="2026-12-31",
    )


# ------------------------------------------------------------------------------------------ MC-3 to MC-9 (the owner's failures)


def test_mc3_turn6_a_named_agent_replaces_the_agent_and_keeps_type_month_period_basis(bot) -> None:
    _world(bot)
    c = Convo(bot)
    _first_five(c)
    text, calls = c.say(6, t6_agent_b(), "for slaes agent agent b")
    args = c.ran(6, text, calls)
    _agent_is_sorento_b(c, bot, 6, args)
    _slots(
        c, 6, args, account_types=["CERAMIC"], group_by="month",
        basis="invoiced", date_from="2026-01-01", date_to="2026-12-31",
    )


def test_mc4_turn7_this_year_runs_with_the_period_and_asks_no_company(bot) -> None:
    _world(bot)
    c = Convo(bot)
    _first_five(c)
    c.say(6, t6_agent_b(), "for slaes agent agent b")
    text, calls = c.say(7, t7_this_year(), "this year")
    assert "Sorento or Mocha?" not in text, "turn 7: asked the company\n" + "\n".join(c.log)
    args = c.ran(7, text, calls)
    _agent_is_sorento_b(c, bot, 7, args)
    _slots(
        c, 7, args, account_types=["CERAMIC"], group_by="month",
        basis="invoiced", date_from="2026-01-01", date_to="2026-12-31",
    )


def test_mc5_turn8_a_company_answer_keeps_every_other_slot_of_the_open_ask(bot) -> None:
    """The owner's flow: turns 1 to 7, then "sorento" if (and only if) the company is still asked."""
    sorento, mocha = _world(bot)
    c = Convo(bot)
    _first_five(c)
    c.say(6, t6_agent_b(), "for slaes agent agent b")
    text, calls = c.say(7, t7_this_year(), "this year")
    if not [a for n, a in calls if n == TOOL]:
        assert f"{sorento} or {mocha}?" in text, f"turn 7: neither ran nor asked the company: {text!r}\n" + "\n".join(c.log)
        text, calls = c.say(8, t8_company_answer(sorento), "sorento")
    args = c.ran(8, text, calls, "the answered ask")
    _agent_is_sorento_b(c, bot, 8, args)
    _slots(
        c, 8, args, company=DEFAULT_COMPANY_ID, account_types=["CERAMIC"], group_by="month", basis="invoiced",
        date_from="2026-01-01", date_to="2026-12-31",
    )


def test_mc5b_a_company_answer_to_an_open_question_keeps_the_rest_of_that_ask(bot) -> None:
    """Rule R4 on its own: the open question is the company one, built by a type both companies carry."""
    sorento, mocha = _world(bot)
    c = Convo(bot)
    ask = _v(
        "sales_analysis", _ent("ceramic", "account_type", None, "account type"), sales_basis="invoiced", group_by="month",
        domain_in_message=True, **YEAR,
    )
    text, calls = c.say(1, ask, "ceramic account type by month 2026 invoiced")
    assert calls == [] and f"{sorento} or {mocha}?" in text, f"setup: want the company question, got {text!r}"
    text, calls = c.say(8, t8_company_answer(sorento), "sorento")
    args = c.ran(8, text, calls, "the answered ask")
    _slots(
        c, 8, args, company=DEFAULT_COMPANY_ID, account_types=["CERAMIC"], group_by="month", basis="invoiced",
        date_from="2026-01-01", date_to="2026-12-31",
    )


def test_mc6_turn9_a_follow_up_naming_an_agent_never_asks_the_basis_again(bot) -> None:
    sorento, _mocha = _world(bot)
    c = Convo(bot)
    _first_five(c)
    text, calls = c.say(9, t9_agent_b_again(sorento), "for slaes agent agent b")
    assert text.strip() != BASIS_Q, "turn 9: asked the basis again, it was set at turn 2\n" + "\n".join(c.log)
    args = c.ran(9, text, calls)
    _agent_is_sorento_b(c, bot, 9, args)
    _slots(c, 9, args, basis="invoiced")


def test_mc7_turn11_an_account_type_with_the_company_held_keeps_it_and_asks_nothing(bot) -> None:
    sorento, _mocha = _world(bot)
    c = Convo(bot)
    first = _v(
        "sales_report", _ent(AGENT_1, "sales_agent"), basis="invoiced", sales_company=sorento, domain_in_message=True, **YEAR
    )
    text, calls = c.say(1, first, "sorento sales for agent a invoiced 2026")
    c.ran(1, text, calls, "setup, the Sorento report")
    text, calls = c.say(11, t11_ceramic_account_type(), "for ceramic account ty[e")
    assert "Sorento or Mocha?" not in text, "turn 11: asked the company, Sorento is held\n" + "\n".join(c.log)
    assert QUESTION.replace("Cabana", "Ceramic") != text.strip(), "turn 11: asked brand or account type, it was said\n" + "\n".join(c.log)
    args = c.ran(11, text, calls)
    _slots(c, 11, args, company=DEFAULT_COMPANY_ID, account_types=["CERAMIC"], group_by="month")


def test_mc9_turn12_a_company_answer_also_read_as_a_brand_word_is_the_company_answer(bot) -> None:
    sorento, mocha = _world(bot)
    c = Convo(bot)
    ask = _v(
        "sales_analysis", _ent("ceramic", "account_type", None, "account type"), sales_basis="invoiced", group_by="month",
        domain_in_message=True, **YEAR,
    )
    text, calls = c.say(1, ask, "ceramic account type by month 2026 invoiced")
    assert calls == [] and f"{sorento} or {mocha}?" in text, f"setup: want the company question, got {text!r}"
    text, calls = c.say(12, t12_company_answer_read_as_brand(sorento), "sorento")
    assert "brand or account type?" not in text, f"turn 12: asked brand or account type: {text!r}\n" + "\n".join(c.log)
    args = c.ran(12, text, calls, "the answered ask")
    _slots(c, 12, args, company=DEFAULT_COMPANY_ID, account_types=["CERAMIC"], group_by="month")
    assert not args.get("brand_ids"), f"turn 12: the company word became a brand filter {args}"


def test_mc8_turn14_only_an_agent_by_month_keeps_the_period_and_asks_no_period(bot) -> None:
    sorento, _mocha = _world(bot)
    c = Convo(bot)
    first = _v(
        "sales_report", _ent("ceramic", "account_type", None, "account type"), basis="invoiced", sales_company=sorento,
        domain_in_message=True, **YEAR,
    )
    text, calls = c.say(13, first, "sorento ceramic account type invoiced 2026")
    c.ran(13, text, calls, "setup, the Sorento report")
    text, calls = c.say(14, t14_only_agent_b(sorento), "breakd down by month, only sales agent agent b")
    assert "Which period?" not in text, "turn 14: asked the period, 2026 was on screen\n" + "\n".join(c.log)
    args = c.ran(14, text, calls)
    _slots(
        c, 14, args, group_by="month", sales_agent_ids=[_agent_b_sorento(bot)], basis="invoiced",
        date_from="2026-01-01", date_to="2026-12-31", company=DEFAULT_COMPANY_ID,
    )


# ------------------------------------------------------------------------------------------ MC-11 (Q1, the held company)


def _sorento_held(c: Convo, sorento: str) -> None:
    first = _v(
        "sales_report", _ent(AGENT_1, "sales_agent"), basis="invoiced", sales_company=sorento, domain_in_message=True, **YEAR
    )
    text, calls = c.say(1, first, "sorento sales for agent a invoiced 2026")
    c.ran(1, text, calls, "setup, the Sorento report")


def test_mc11a_a_held_company_stays_for_a_subject_that_exists_in_it(bot) -> None:
    sorento, mocha = _world(bot)
    c = Convo(bot)
    _sorento_held(c, sorento)
    text, calls = c.say(
        2,
        _v("sales_analysis", _ent(AGENT_2, "sales_agent"), sales_basis="invoiced", entity_op="replace_combine",
           continuation=True, **YEAR),
        "for slaes agent agent b",
    )
    assert f"{sorento} or {mocha}?" not in text, f"turn 2: asked the company though {AGENT_2} exists in the held one\n" + "\n".join(c.log)
    args = c.ran(2, text, calls)
    _slots(c, 2, args, company=DEFAULT_COMPANY_ID, sales_agent_ids=[_agent_b_sorento(bot)])


def test_mc11b_a_subject_only_the_other_company_carries_drops_the_company_and_asks(bot) -> None:
    sorento, mocha = _world(bot)
    c = Convo(bot)
    _sorento_held(c, sorento)
    text, calls = c.say(
        2,
        _v("sales_analysis", _ent(AGENT_M, "sales_agent"), sales_basis="invoiced", entity_op="replace_combine",
           continuation=True, **YEAR),
        "for slaes agent agent m",
    )
    assert calls == [] and f"{sorento} or {mocha}?" in text, (
        f"turn 2: want the company question for a subject only {mocha} carries, got {text!r}\n" + "\n".join(c.log)
    )


# ------------------------------------------------------------------------------------------ MC-12 and the basis guard


def test_mc12_a_follow_up_of_another_report_kind_carries_no_report_slot(bot) -> None:
    sorento, _mocha = _world(bot)
    c = Convo(bot)
    _first_five(c)
    stock = _v(
        "none", _ent("cabana", "brand", "CABANA"), domain_hint="inventory", intent_hint="check_stock", order_status=None,
        entity_op="replace_combine", continuation=True,
    )
    text, calls = c.say(15, stock, "cabana stock")
    carried = [a for n, a in calls if n == TOOL]
    assert not carried, f"turn 15: a stock ask ran a report with {carried}\n" + "\n".join(c.log)
    for n, args in calls:
        for slot in ("sales_agent_ids", "account_types", "basis", "group_by", "date_from", "date_to"):
            assert slot not in args, f"turn 15: stock call {n} carries report slot {slot}={args[slot]!r}\n" + "\n".join(c.log)


def test_mc10_the_first_sales_ask_of_a_fresh_conversation_with_no_basis_asks_the_basis(bot) -> None:
    _world(bot)
    c = Convo(bot)
    ask = _v("sales_report", _ent(AGENT_1, "sales_agent"), domain_in_message=True, **YEAR)
    text, calls = c.say(1, ask, "sales for agent a 2026")
    assert calls == [] and text.strip() == BASIS_Q, f"turn 1: want the basis question, got {text!r}"
