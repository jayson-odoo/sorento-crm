"""SALES-TOTAL-ASK (owner ruling 27 Oct 2026, "total sales should ask").

A sales total ("total sales Jan 2026", `order_status: sales_analysis`) whose message names no
basis is asked the sales ranking's own line, "Invoiced, delivered, ordered or outstanding?"
(Invoiced first), with no figure, and never runs `crm_sales_analysis` on a default (main ran it
as invoiced: `lanes/business/fetch.py`, the `crm_sales_analysis` arg builder). The answer runs the
first message's own ask with the basis picked; a named basis runs straight away.

* T1 lane: no basis -> the question, no MCP call, the slot armed with the four bases, Invoiced first.
* T2 lane: a named basis (`sales_basis` or the report key `basis`) runs, no question.
* T3 engine: "total sales Jan 2026" asks; "1" runs invoiced over Jan 2026.
* T4 engine: "invoiced" (the parser's `basis`) and "delivered" (`sales_basis`) answer it.
* T5 engine: "outstanding" runs the report ask's outstanding orders by channel (the analysis's own rows),
  never `crm_sales_analysis`.
* T6 engine: a contact in two companies is asked the basis, then the company, then it runs with both.

Engine harness: `test_sales_analysis_company_pick.Chat` (real `engine.run_turn`, Postgres; parser,
access, resolver and MCP faked). Figures and customers are fake.
"""
from __future__ import annotations

import os
import re
from typing import Any

import pytest

from app.services.chatbot.lanes.business.services import FetchServices
from tests.chatbot.test_engine import _parser_output
from tests.chatbot.test_outstanding_lane import _capturing_mcp, _qf
from tests.chatbot._sales_pick_helpers import (
    QUESTION as COMPANY_QUESTION,
    Chat,
    _calls,
    _pick,
    _reply,
)
from tests.chatbot.test_sales_analysis_lane import GRANT, _rendered

BASIS_QUESTION = "Invoiced, delivered, ordered or outstanding?"
#: REPORT-UNIFY: every sales total runs on the report ask now; the analysis tool is never called from chat.
TOOL = "crm_report_ask"
JAN_2026 = {"date_mode": "month", "date_filter_start": "2026-01-01", "date_filter_end": "2026-01-31"}


def _payload(**qf: Any) -> dict[str, Any]:
    return {
        "gate": {"compatible_entities": []},
        "tier_gate": None,
        "ctx": {
            "parse": {"output": _qf(order_status="sales_analysis", entities=[], **qf)},
            "contact": {"id": 900000008},
            "access": {"attributes": [GRANT]},
        },
    }


def _lane(**qf: Any) -> tuple[dict[str, Any], list[tuple[str, dict[str, Any]]]]:
    from app.services.chatbot.lanes.business import run_fetch

    call, captured = _capturing_mcp(_rendered())
    result = run_fetch(_payload(**qf), services=FetchServices(mcp_call=call))
    return result, captured


def _text(result: dict[str, Any]) -> str:
    return str(((result or {}).get("output") or {}).get("text") or (result or {}).get("text") or "")


# --------------------------------------------------------------------------- #
# Lane
# --------------------------------------------------------------------------- #


def test_t1_a_total_with_no_basis_is_asked_never_run(session_factory):
    result, captured = _lane(**JAN_2026)
    assert captured == [], f"no figure before the basis is answered: {captured}"
    assert BASIS_QUESTION in repr(result), f"the ranking's own basis line: {result}"
    slot = (result.get("fetch") or {}).get("required_ask") or {}
    assert slot.get("ask") == "sales_basis" and slot.get("asking") == "basis", slot
    assert [o[0] for o in slot.get("options") or []] == ["invoiced", "delivered", "ordered", "outstanding"], slot


@pytest.mark.parametrize(
    "named",
    [
        pytest.param({"sales_basis": "invoiced"}, id="sales_basis-invoiced"),
        pytest.param({"sales_basis": "ordered"}, id="sales_basis-ordered"),
        pytest.param({"basis": "delivered"}, id="basis-delivered"),
    ],
)
def test_t2_a_named_basis_runs_without_asking(session_factory, named):
    result, captured = _lane(**JAN_2026, **named)
    assert [name for name, _ in captured] == [TOOL], f"a named basis runs: {result}"
    assert captured[0][1]["basis"] == next(iter(named.values()))


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #


@pytest.fixture
def one(session_factory, monkeypatch) -> Chat:
    return Chat(session_factory, monkeypatch, ("Sorento",))


@pytest.fixture
def two(session_factory, monkeypatch) -> Chat:
    return Chat(session_factory, monkeypatch, ("Sorento", "Mocha"))


def _total(**overrides: Any) -> dict[str, Any]:
    """"total sales Jan 2026": the company's total, no basis named."""
    base = dict(
        domain_hint="order", intent_hint="check_order", order_status="sales_analysis",
        sales_channel=None, sales_company=None, sales_basis=None, group_by=None,
        entities=[], entity_op="replace_combine", domain_in_message=True, **JAN_2026,
    )
    base.update(overrides)
    return _parser_output(**base)


def _answer(**fields: Any) -> dict[str, Any]:
    """A reply to the basis question, as the parser reads one (the ranking's answer shape)."""
    base = dict(
        message_type="business_query", domain_hint="order", intent_hint="check_order",
        order_status="sales_ranking", entities=[], entity_op="reuse", domain_in_message=False,
        by_words=None,  # the live prompt defines `by_words`: a bare reply carries it null
    )
    base.update(fields)
    return _parser_output(**base)


#: The parser's declared answer to the open question, filling the owed basis (`sales_basis` or `basis`).
FILL = {"mode": "fill", "picked": [], "items": [], "qty_for_all": None}


def _ask(chat: Chat) -> None:
    result, captured = chat.say(_total(), "total sales Jan 2026")
    assert _reply(result).strip() == BASIS_QUESTION, f"the basis is asked: {_reply(result)!r}"
    assert captured == [], f"no tool call at all before the basis: {captured}"


def _ran(captured: list[tuple[str, dict[str, Any]]], basis: str) -> dict[str, Any]:
    calls = _calls(captured, TOOL)
    assert calls, f"the answer runs the sales total: {captured}"
    args = calls[0]
    assert args.get("basis") == basis, args
    assert args.get("date_from") == "2026-01-01" and args.get("date_to") == "2026-01-31", (
        f"the first message's period rides through the question: {args}"
    )
    return args


def test_t3_total_sales_asks_then_1_runs_invoiced(one):
    _ask(one)
    question = one.next_open_question() or {}
    assert question.get("about") == "sales_basis", question
    _result, captured = one.say(_answer(open_question_answer=_pick(1)), "1")
    _ran(captured, "invoiced")


@pytest.mark.parametrize(
    ("fields", "body", "basis"),
    [
        pytest.param({"basis": "invoiced", "open_question_answer": FILL}, "invoiced", "invoiced", id="invoiced-basis"),
        pytest.param(
            {"order_status": "sales_analysis", "sales_basis": "delivered", "open_question_answer": FILL},
            "delivered", "delivered", id="delivered-sales_basis",
        ),
    ],
)
def test_t4_a_basis_word_answers_it(one, fields, body, basis):
    _ask(one)
    _result, captured = one.say(_answer(**fields), body)
    _ran(captured, basis)


def test_t5_outstanding_runs_the_one_report_ask_total_layout(one):
    _ask(one)
    _result, captured = one.say(_answer(basis="outstanding", open_question_answer=FILL), "outstanding")
    asks = _calls(captured, "crm_report_ask")
    assert asks, f"the report ask's outstanding total runs: {captured}"
    # ONE layout (reviewer 6): the report ask total, one figure plus the header, for every basis (the analysis's
    # one-line-per-channel layout is gone with the analysis).
    assert asks[0].get("basis") == "outstanding" and not asks[0].get("group_by"), asks[0]
    assert asks[0].get("date_from") == "2026-01-01" and asks[0].get("date_to") == "2026-01-31", asks[0]


def test_t6_two_companies_basis_then_company_then_both_ride(two):
    _ask(two)
    result, captured = two.say(_answer(basis="ordered", open_question_answer=FILL), "ordered")
    assert COMPANY_QUESTION in _reply(result), f"then the company: {_reply(result)!r}"
    assert not [a for a in _calls(captured, TOOL) if a.get("company")], captured
    _result, captured = two.say(_answer(open_question_answer=_pick(2), order_status=None), "2")
    args = _ran(captured, "ordered")
    from tests._mc_lookup_seed import MOCHA_ID

    assert args.get("company") == MOCHA_ID, args  # the report ask sends the company id


# --------------------------------------------------------------------------- #
# Review round (reviewer findings 1 to 3)
# --------------------------------------------------------------------------- #


def test_t7_outstanding_named_on_a_fresh_total_is_never_the_analysis(session_factory):
    """Finding 2: "outstanding" named up front runs the report ask too, never the analysis with no basis (the
    route would default it to invoiced)."""
    from app.services.chatbot.lanes.business import run_fetch

    payload = _payload(**JAN_2026, basis="outstanding")
    payload["ctx"]["access"] = {"attributes": [GRANT, "sales_orders.outstanding"]}  # Q6: outstanding is its own reveal
    call, captured = _capturing_mcp(_rendered())
    run_fetch(payload, services=FetchServices(mcp_call=call))
    asks = _calls(captured, TOOL)
    assert asks and asks[0].get("basis") == "outstanding", captured  # the report ask runs it, no other tool


def test_t8_the_first_messages_axes_win_over_the_answers_own_parse(one):
    """Finding 3 (crew re-verify E2's rule for the company question): a declared answer parsed with an axis, a
    channel and a period of its own runs the FIRST message's ask: January, no channel, the channel rows."""
    _ask(one)
    _result, captured = one.say(
        _answer(open_question_answer=_pick(1), group_by="customer", sales_channel="project",
                date_filter_start="2026-02-01", date_filter_end="2026-02-28"),
        "1",
    )
    args = _ran(captured, "invoiced")
    assert not args.get("group_by") and not args.get("channel"), args  # the first message's total, no channel


def test_t9_a_new_total_while_the_question_is_open_is_its_own_ask(one):
    """Finding 1: "total delivered sales Feb 2026" while the basis question is open runs February, delivered;
    never the open question's January."""
    _ask(one)
    _result, captured = one.say(
        _total(sales_basis="delivered", date_filter_start="2026-02-01", date_filter_end="2026-02-28"),
        "total delivered sales Feb 2026",
    )
    calls = _calls(captured, TOOL)
    assert calls and calls[0].get("basis") == "delivered", captured
    assert calls[0].get("date_from") == "2026-02-01" and calls[0].get("date_to") == "2026-02-28", calls[0]


def test_t10_a_ranking_while_the_question_is_open_is_never_read_as_the_basis(one):
    """Finding 1: "top 5 dealers in feb 2026" is a ranking of its own, not a miss on the basis question."""
    _ask(one)
    result, captured = one.say(
        _answer(order_status="sales_ranking", group_by="customer", top_n=5, domain_in_message=True,
                entity_op="replace_combine", date_filter_start="2026-02-01", date_filter_end="2026-02-28"),
        "top 5 dealers in feb 2026",
    )
    assert not [a for a in _calls(captured, TOOL) if not a.get("group_by")], captured  # no total from the typed ranking
    assert "which basis" not in _reply(result), _reply(result)
    question = one.next_open_question() or {}
    assert question.get("about") != "sales_basis", question


def test_t11_a_declared_basis_with_a_stray_axis_is_still_the_answer(one):
    """Review round 2: "invoiced" the parser declared as the answer, with an axis and the window echoed (parser
    noise on an answering turn), answers the basis question; it is never a new ranking that asks its own."""
    _ask(one)
    _result, captured = one.say(
        _answer(basis="invoiced", open_question_answer=FILL, group_by="customer", **JAN_2026),
        "invoiced",
    )
    _ran(captured, "invoiced")


# --------------------------------------------------------------------------- #
# Owner rule (28 Oct): the parser alone reads the reply; code never reads the typed text
# --------------------------------------------------------------------------- #


def test_t12_a_declared_pick_with_count_noise_is_the_option_it_picked(one):
    """The parser picked option 1 of the four it was shown (`turn/question.of_required_ask`) and also set
    `top_n` 1: the pick is the answer."""
    _ask(one)
    _result, captured = one.say(_answer(open_question_answer=_pick(1), top_n=1), "1")
    _ran(captured, "invoiced")


def test_t13_a_declared_basis_marked_as_a_domain_word_is_still_the_answer(one):
    _ask(one)
    _result, captured = one.say(
        _answer(basis="invoiced", open_question_answer=FILL, domain_in_message=True), "invoiced"
    )
    _ran(captured, "invoiced")


@pytest.mark.parametrize(
    ("fields", "body"),
    [
        pytest.param({"top_n": 1}, "1", id="number-undeclared"),
        pytest.param({}, "1", id="number-nothing-read"),
        pytest.param({"basis": None, "order_status": None, "message_type": "casual", "intent_hint": None}, "invoiced",
                     id="word-undeclared"),
    ],
)
def test_t16_a_reply_the_parser_declared_no_answer_for_is_never_read_from_its_text(one, fields, body):
    """Owner rule: what the person typed is never matched to an option or read by its shape ("1" by its digits,
    "invoiced" by the option's name). With no answer declared the question is dropped, never answered; a parser
    miss is fixed in the prompt."""
    _ask(one)
    _result, captured = one.say(_answer(**fields), body)
    assert _calls(captured, TOOL) == [], f"no figure from the typed text: {captured}"
    assert (one.next_open_question() or {}).get("about") != "sales_basis"


def test_t14_another_domains_ask_while_the_question_is_open_is_its_own(one):
    """"stock for SRTWC286" names no basis and carries its own domain word: never read as a basis miss."""
    _ask(one)
    result, captured = one.say(
        _parser_output(message_type="business_query", domain_hint="inventory", intent_hint="check_stock",
                       entities=[], domain_in_message=True),
        "stock for SRTWC286",
    )
    assert _calls(captured, TOOL) == [], captured
    assert "which basis" not in _reply(result) and _reply(result).strip() != BASIS_QUESTION, _reply(result)


#: The live parser text (prod v69 = dev v188 = crew's v68.txt). Not in this public repository; crew runs
#: T15 with `SALES_TOTAL_ASK_PROMPT_FILE=<path to v68.txt>`.
PROMPT_FILE = os.environ.get("SALES_TOTAL_ASK_PROMPT_FILE")


@pytest.mark.skipif(not PROMPT_FILE, reason="needs the live parser text (SALES_TOTAL_ASK_PROMPT_FILE)")
def test_t15_the_live_parser_text_needs_no_edit(one):
    """How the change reaches prod: in the lane, not the prompt. On the live text (no PARSER TEMPLATE block)
    the parser config is not the template's, the text's own sales basis rule reads "total sales" as no basis
    (null, which the lane now asks), and the next turn's parser is shown the question with its four options,
    Invoiced first, whatever the prompt says about it."""
    from app.services.chatbot.head.parser_template import MARKER

    with open(PROMPT_FILE, encoding="utf-8") as fh:
        text = fh.read()
    assert MARKER not in text, "the live text carries no PARSER TEMPLATE block"
    # PROMPT-RULES-DIET wrote it as one line, "...; none said -> null." (`chatbot_prompt_diet_edits`).
    rule = re.search(r"SALES_BASIS[^\n]*\n(?:[^\n]*\n){0,6}?[^\n]*none said -> null", text, re.IGNORECASE)
    assert rule, "the live text's sales basis rule maps no basis word to null (it never picks one itself)"
    _ask(one)
    shown: list[str] = []
    one.say(_answer(open_question_answer=_pick(1)), "1", capture_user_block=shown)
    block = "\n".join(shown)
    assert "Open question" in block and BASIS_QUESTION in block, block[-2000:]
    positions = [block.find(word) for word in ("Invoiced", "Delivered", "Ordered", "Outstanding")]
    assert -1 not in positions and positions == sorted(positions), block[-2000:]


# --------------------------------------------------------------------------- #
# Review round 3: every declared answer shape guarded
# --------------------------------------------------------------------------- #


def test_t17_a_declared_pick_of_2_runs_delivered(one):
    _ask(one)
    _result, captured = one.say(_answer(open_question_answer=_pick(2)), "2")
    _ran(captured, "delivered")


def test_t18_a_declared_pick_of_4_runs_the_outstanding_report_ask(one):
    _ask(one)
    _result, captured = one.say(_answer(open_question_answer=_pick(4)), "4")
    asks = _calls(captured, TOOL)
    assert asks and asks[0].get("basis") == "outstanding", captured


def test_t19_the_declared_pick_wins_over_a_stray_basis_key(one):
    _ask(one)
    _result, captured = one.say(_answer(open_question_answer=_pick(2), basis="invoiced"), "2")
    _ran(captured, "delivered")


def test_t20_a_declared_cancel_cancels(one):
    _ask(one)
    cancel = {"mode": "cancel", "picked": [], "items": [], "qty_for_all": None}
    result, captured = one.say(_answer(open_question_answer=cancel), "cancel")
    assert captured == [], captured
    assert "Sales report cancelled." in _reply(result), _reply(result)
    assert (one.next_open_question() or {}).get("about") != "sales_basis"


def test_t21_a_declared_answer_naming_no_option_is_asked_again_then_given_up(one):
    """A declared pick outside the four: asked again in the same words, then given up, never echoing a word."""
    _ask(one)
    result, captured = one.say(_answer(open_question_answer=_pick(9)), "zzqq")
    assert _reply(result).strip() == BASIS_QUESTION and captured == [], _reply(result)
    result, captured = one.say(_answer(open_question_answer=_pick(9)), "zzqq")
    assert "I still can't tell which basis you mean." in _reply(result) and "zzqq" not in _reply(result), _reply(result)
    assert captured == [], captured


def test_t22_outstanding_with_no_period_reads_every_date_never_a_second_question(one):
    """An outstanding kind takes no period (Q2): none said means every date, and it is never asked."""
    result, _c = one.say(_total(date_mode=None, date_filter_start=None, date_filter_end=None), "total sales")
    assert _reply(result).strip() == BASIS_QUESTION, _reply(result)
    _result, captured = one.say(_answer(open_question_answer=_pick(4)), "4")
    asks = _calls(captured, "crm_report_ask")
    assert asks and asks[0].get("basis") == "outstanding", captured
    assert "date_from" not in asks[0] and "date_to" not in asks[0], asks[0]
