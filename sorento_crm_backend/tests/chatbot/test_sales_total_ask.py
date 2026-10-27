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

from typing import Any

import pytest

from app.services.chatbot.lanes.business.services import FetchServices
from tests.chatbot.test_engine import _parser_output
from tests.chatbot.test_outstanding_lane import _capturing_mcp, _qf
from tests.chatbot.test_sales_analysis_company_pick import (
    ANALYSIS,
    QUESTION as COMPANY_QUESTION,
    Chat,
    _calls,
    _pick,
    _reply,
)
from tests.chatbot.test_sales_analysis_lane import GRANT, _rendered

BASIS_QUESTION = "Invoiced, delivered, ordered or outstanding?"
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
    assert [name for name, _ in captured] == [ANALYSIS], f"a named basis runs: {result}"
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
    )
    base.update(fields)
    return _parser_output(**base)


def _ask(chat: Chat) -> None:
    result, captured = chat.say(_total(), "total sales Jan 2026")
    assert _reply(result).strip() == BASIS_QUESTION, f"the basis is asked: {_reply(result)!r}"
    assert _calls(captured, ANALYSIS) == [], f"no figure before the basis: {captured}"


def _ran(captured: list[tuple[str, dict[str, Any]]], basis: str) -> dict[str, Any]:
    calls = _calls(captured, ANALYSIS)
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
        pytest.param({"basis": "invoiced"}, "invoiced", "invoiced", id="invoiced-word"),
        pytest.param(
            {"order_status": "sales_analysis", "sales_basis": "delivered",
             "open_question_answer": {"mode": "fill", "picked": [], "items": [], "qty_for_all": None}},
            "delivered", "delivered", id="delivered-sales_basis",
        ),
    ],
)
def test_t4_a_basis_word_answers_it(one, fields, body, basis):
    _ask(one)
    _result, captured = one.say(_answer(**fields), body)
    _ran(captured, basis)


def test_t5_outstanding_runs_the_report_ask_never_the_analysis(one):
    _ask(one)
    _result, captured = one.say(_answer(basis="outstanding"), "outstanding")
    assert _calls(captured, ANALYSIS) == [], f"the analysis has no outstanding basis: {captured}"
    asks = _calls(captured, "crm_report_ask")
    assert asks, f"the report ask's outstanding total runs: {captured}"
    assert asks[0].get("basis") == "outstanding" and asks[0].get("group_by") == "channel", asks[0]
    assert asks[0].get("date_from") == "2026-01-01" and asks[0].get("date_to") == "2026-01-31", asks[0]


def test_t6_two_companies_basis_then_company_then_both_ride(two):
    _ask(two)
    result, captured = two.say(_answer(basis="ordered"), "ordered")
    assert COMPANY_QUESTION in _reply(result), f"then the company: {_reply(result)!r}"
    assert not [a for a in _calls(captured, ANALYSIS) if a.get("company")], captured
    _result, captured = two.say(_answer(open_question_answer=_pick(2), order_status=None), "2")
    args = _ran(captured, "ordered")
    assert args.get("company") == "Mocha", args


# --------------------------------------------------------------------------- #
# Review round (reviewer findings 1 to 3)
# --------------------------------------------------------------------------- #


def test_t7_outstanding_named_on_a_fresh_total_is_never_the_analysis(session_factory):
    """Finding 2: "outstanding" named up front runs the report ask too, never the analysis with no basis (the
    route would default it to invoiced)."""
    _result, captured = _lane(**JAN_2026, basis="outstanding")
    assert ANALYSIS not in [name for name, _ in captured], captured


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
    assert args.get("rows") == "channel" and not args.get("channel"), args


def test_t9_a_new_total_while_the_question_is_open_is_its_own_ask(one):
    """Finding 1: "total delivered sales Feb 2026" while the basis question is open runs February, delivered;
    never the open question's January."""
    _ask(one)
    _result, captured = one.say(
        _total(sales_basis="delivered", date_filter_start="2026-02-01", date_filter_end="2026-02-28"),
        "total delivered sales Feb 2026",
    )
    calls = _calls(captured, ANALYSIS)
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
    assert _calls(captured, ANALYSIS) == [], captured
    assert "which basis" not in _reply(result), _reply(result)
    question = one.next_open_question() or {}
    assert question.get("about") != "sales_basis", question


def test_t11_a_bare_basis_word_with_a_stray_axis_is_still_the_answer(one):
    """Review round 2: "invoiced" parsed with no declared answer, an axis and the window echoed (parser noise on
    an answering turn) answers the basis question; it is never a new ranking that asks its own questions."""
    _ask(one)
    _result, captured = one.say(
        _answer(basis="invoiced", group_by="customer", **JAN_2026),
        "invoiced",
    )
    _ran(captured, "invoiced")
