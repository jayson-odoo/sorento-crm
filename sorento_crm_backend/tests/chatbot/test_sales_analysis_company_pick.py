"""CHAT-PICK-QTY-STATE fix round SALES-COMPANY, item (1): the reply to the bot's company
question picks the company (red tests, test-first).

Live (v63, old path, a staff contact holding TWO companies, Sorento the default and Mocha):

* turn A, a sales report, leaves its `sales_report_detail` drill offer open (By product /
  Delivery orders).
* turn B "dealer sales september 2026": `order_status: sales_analysis`,
  `sales_channel: dealer`, Sep 2026, `sales_company: null`, a product entity. The lane runs
  `crm_sales_analysis` with no company and the ROUTE answers its own clarify,
  "Sorento or Mocha?" (`app/api/v1/sales/analysis.py`), which comes back as plain result
  text: the chat layer stores no question, and the stale drill offer stays open.
* turn C "Sorento", read two ways live: (c1) `escalation.company_pick: "Sorento"`,
  `is_escalation_confirmation: true`, `open_question_answer` pick [1], answered
  out_of_scope "Routed to your PIC"; (c2) a brand entity "Sorento", which refines the
  standing subject as a brand filter.

Required (crew): the reply to a bot company question picks the company, so
`crm_sales_analysis` runs with that company, channel dealer and the Sep 2026 window;
never a brand filter, never out_of_scope, and the stale drill offer no longer answers it.

* C1 (RED) turn B with two companies asks "Sorento or Mocha?" itself and the question the
  NEXT turn's parser is shown (`turn/question.open_question` over the stored state) is that
  company question, Sorento first.
* C2 (RED) turn C shape c1 runs the analysis for Sorento, dealer, Sep 2026; not out_of_scope.
* C3 (RED) turn C shape c2 (a brand entity, no company pick): the same; no brand filter.
* C4 (RED) "Mocha" by a pick of option 2, or by `sales_company`: runs for Mocha.
* G1 (GREEN guard) a contact with ONE company: turn B runs straight away, no question.
* G2 (GREEN guard) turn B naming `sales_company: Mocha`: no question, runs for Mocha.
* G3 (GREEN guard) "stock for SRTWC286" while the company question is open is its own ask.
* G4 (pin) the company question retires the stale drill offer: a turn that leaves the
  company question unanswered and arms nothing of its own does not bring the drill offer
  back, so a later "1" picks no drill option (the engine closes the stored offer when a lane
  hands back a required ask). Its C turn arms nothing on purpose: G3's stock miss arms its
  own escalation offer, which replaces the drill offer either way and pins nothing.

Engine harness: `test_outstanding_lane._run_turn` (real `engine.run_turn`, Postgres, parser /
access / resolver / MCP faked) with its `_capturing_mcp` swapped for a double that answers the
two sales tools through the REAL MCP presenter. `crm_sales_analysis` with no company answers
the way the route does for a contact holding both companies: the clarify, never a figure.
The escalation lane's round-robin draw and SLA row are faked (`test_escalation_agent_carry`'s
own seams), so shape c1 completes today exactly as it did live: out_of_scope, "Routed to
your PIC". Companies are the tenant's own two (Sorento, Mocha); customers are fake.
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import text as sql_text

from tests.chatbot.test_engine import CONTACT_ID, _parser_output

GRANT = "sales_orders.sales_report"
ANALYSIS = "crm_sales_analysis"
REPORT = "crm_sales_report"
PRODUCT_RAW = "b2155-nl-blue"
PRODUCT_CODE = "B2155-NL-BLUE"
PRODUCT_UUID = "b2155000-0000-4000-8000-000000002155"
BRAND_UUID = "5040e000-0000-4000-8000-00000000b001"
QUESTION = "Sorento or Mocha?"
SEP_2026 = {"date_mode": "month", "date_filter_start": "2026-09-01", "date_filter_end": "2026-09-30"}

#: Keyed by the token the lane asks the resolver about (punctuation-free), measured.
_PRODUCT_MATCH = {"b2155nlblue": {"uuid": PRODUCT_UUID, "entity_type": "product", "canonical_code": PRODUCT_CODE}}

#: `crm_sales_report`'s route body for the product (turn A): a hit, so the drill offer arms.
REPORT_BODY: dict[str, Any] = {
    "status": "ok", "message": None, "basis": "delivered", "customer_name": None,
    "customer_count": 1, "product_code": PRODUCT_CODE, "product_codes": [], "channel": None,
    "channel_shown": False, "location_token": None, "warehouse_codes": [],
    "date_from": "2026-01-01", "date_to": "2026-12-31", "grain": "month",
    "total": {"qty": 10, "amount": 100.0},
    "periods": [{"from": "2026-09-01", "to": "2026-09-30", "qty": 10, "amount": 100.0}],
    "group_by": None, "rows": [], "more": 0,
    "options": [
        {"key": "product", "label": "By product"},
        {"key": "delivery_order", "label": "Delivery orders"},
    ],
}


def _analysis_body(company: str) -> dict[str, Any]:
    """`crm_sales_analysis`'s ready body (`test_sales_analysis_lane.ROUTE_HIT`'s shape)."""
    return {
        "status": "ready", "report": "Sales", "company": company, "channel": "Dealer",
        "basis": "Delivered (transferred to DO)", "period": "01/09/2026 to 30/09/2026",
        "rows_label": "Channel", "cols_label": "Year", "count_label": "Channels",
        "columns": ["2026"],
        "rows": [{"label": "Dealer", "values": ["100.00"], "total": "100.00"}],
        "totals": {"values": ["100.00"], "total": "100.00"},
        "total_count": 1, "attachments": [],
    }


def _sales_mcp(companies: tuple[str, ...]):
    """A `_capturing_mcp` stand-in over the contact's `companies` (default first). The sales
    analysis with no company answers as the route does: the only company's figures, or the
    clarify naming every company the contact holds."""

    def factory(response: Any = None):
        from tests.chatbot.test_outstanding_lane import _present_response

        present = _present_response()
        captured: list[tuple[str, dict[str, Any]]] = []

        def _call(name: str, args: dict[str, Any]) -> Any:
            captured.append((name, dict(args)))
            if name == REPORT:
                return present(name, json.dumps(REPORT_BODY))
            if name == ANALYSIS:
                company = args.get("company")
                if not company and len(companies) > 1:
                    body = {"status": "clarify", "message": f"{', '.join(companies[:-1])} or {companies[-1]}?"}
                else:
                    body = _analysis_body(company or companies[0])
                return present(name, json.dumps(body))
            return json.dumps({"has_result": False, "items": []})

        return _call, captured

    return factory


def _add_mocha(session_factory) -> None:
    """The contact's second company (`_seed_contact` links the default, Sorento)."""
    from tests._mc_lookup_seed import MOCHA_ID, seed_mocha

    db = session_factory()
    seed_mocha(db)
    db.execute(
        sql_text(
            "INSERT INTO respond_contact_companies (id, respond_contact_id, company_id) "
            "SELECT gen_random_uuid(), id, :company_id FROM respond_contacts WHERE respond_io_id = :cid"
        ),
        {"cid": str(CONTACT_ID), "company_id": MOCHA_ID},
    )
    db.commit()


class Chat:
    def __init__(self, session_factory, monkeypatch, companies: tuple[str, ...]) -> None:
        from tests.chatbot import test_outstanding_lane as lane
        from tests.chatbot._turn_helpers import make_office_access_type
        from tests.chatbot.test_escalation_agent_carry import _capture_next_assignee, _capture_sla

        self.session_factory, self.monkeypatch, self.lane = session_factory, monkeypatch, lane
        monkeypatch.setattr(lane, "_capturing_mcp", _sales_mcp(companies))
        # The round-robin draw and the SLA row are faked (no SLA policy or access agent rows
        # here), so a turn the engine hands to a person completes the way it did live
        # ("Routed to your PIC"); `handoffs` records every assignment asked for.
        self.handoffs = _capture_next_assignee(monkeypatch)
        _capture_sla(monkeypatch)
        lane._seed_contact(session_factory, variables={})
        if "Mocha" in companies:
            _add_mocha(session_factory)
        make_office_access_type(session_factory, CONTACT_ID)
        self.n = 0

    def say(self, qf: dict[str, Any], body: str, **kwargs: Any):
        self.n += 1
        kwargs.setdefault("matches", _PRODUCT_MATCH)
        result, captured = self.lane._run_turn(
            self.session_factory, self.monkeypatch, qf=qf, text_body=body,
            msg_id=f"ZZT-sacp-{self.n}", attributes=[GRANT], **kwargs,
        )
        return result, captured

    def next_open_question(self) -> dict[str, Any] | None:
        """The question the NEXT turn's parser is shown, read off the stored session the way
        the engine loads it (`turn_runtime.load_state`, `turn/question.open_question`)."""
        from app.services.chatbot.turn.question import open_question
        from app.services.chatbot.turn.state import Profile
        from app.services.chatbot.turn_runtime import load_state

        state = load_state(
            {"session_vars": self.lane._session_of(self.session_factory)}, profile=Profile(), turn_no=0
        )
        return open_question(state.pending, state.focus.tasks, state.focus.required_ask)


@pytest.fixture
def two(session_factory, monkeypatch) -> Chat:
    return Chat(session_factory, monkeypatch, ("Sorento", "Mocha"))


@pytest.fixture
def one(session_factory, monkeypatch) -> Chat:
    return Chat(session_factory, monkeypatch, ("Sorento",))


def _product() -> dict[str, Any]:
    return {"raw": PRODUCT_RAW, "hint": "product", "canonical_code": None, "current_message": True, "confident": True}


def _turn_a() -> dict[str, Any]:
    """"b2155-nl-blue sales 2026": the sales report whose drill offer stays open."""
    return _parser_output(
        domain_hint="order", intent_hint="check_order", order_status="sales_report",
        entities=[_product()], entity_op="replace_combine", domain_in_message=True,
        date_mode="year", date_filter_start="2026-01-01", date_filter_end="2026-12-31",
    )


def _turn_b(**overrides: Any) -> dict[str, Any]:
    """"dealer sales september 2026", the no-product ask (a product-naming parse runs the report). Its basis is
    named: one with none is asked the basis before the company (SALES-TOTAL-ASK, `test_sales_total_ask` T6)."""
    base = dict(
        domain_hint="order", intent_hint="check_order", order_status="sales_analysis",
        sales_channel="dealer", sales_company=None, sales_basis="delivered", group_by="year",
        entities=[], entity_op="replace_combine", domain_in_message=True, **SEP_2026,
    )
    base.update(overrides)
    return _parser_output(**base)


def _pick(position: int) -> dict[str, Any]:
    return {"mode": "pick", "picked": [position], "items": [], "qty_for_all": None}


def _turn_c_company_pick() -> dict[str, Any]:
    """"Sorento", shape c1: the escalation company pick, a confirmation, and a pick of [1]."""
    return _parser_output(
        message_type="casual", intent_hint=None, domain_hint=None, entities=[],
        entity_op="reuse", domain_in_message=False,
        escalation={"is_escalation_confirmation": True, "company_pick": "Sorento"},
        open_question_answer=_pick(1),
    )


def _turn_c_brand() -> dict[str, Any]:
    """"Sorento", shape c2: a brand entity and nothing else."""
    return _parser_output(
        message_type="business_query", intent_hint=None, domain_hint=None,
        entities=[{"raw": "Sorento", "hint": "brand", "canonical_code": None, "current_message": True, "confident": True}],
        entity_op="replace_combine", domain_in_message=False,
    )


def _calls(captured: list[tuple[str, dict[str, Any]]], tool: str) -> list[dict[str, Any]]:
    return [args for name, args in captured if name == tool]


def _reply(result: Any) -> str:
    return (result.reply or {}).get("text") or ""


def _option_words(question: dict[str, Any] | None) -> list[str]:
    return [str(o.get("label") or o.get("code") or "") for o in (question or {}).get("options") or []]


def _to_the_company_question(chat: Chat) -> None:
    """Turn B (turn A's sales report drill offer is retired with the sales report tool: REPORT-UNIFY)."""
    result, _captured = chat.say(_turn_b(), "dealer sales september 2026")
    assert QUESTION in _reply(result), f"setup: turn B asks which company: {_reply(result)!r}"


def _assert_ran_for(captured: list[tuple[str, dict[str, Any]]], company: str) -> None:
    calls = _calls(captured, ANALYSIS)
    assert calls, f"the reply to the company question must run the sales analysis: {captured}"
    args = calls[0]
    assert args.get("company") == company, f"the analysis must run for {company}: {args}"
    assert args.get("channel") == "dealer", f"turn B's channel rides through the question: {args}"
    assert args.get("date_from") == "2026-09-01" and args.get("date_to") == "2026-09-30", (
        f"turn B's window rides through the question: {args}"
    )
    assert _calls(captured, REPORT) == [], f"the stale drill offer must not answer it: {captured}"


# --------------------------------------------------------------------------- #
# C1 (RED) - turn B asks the company itself and stores the question
# --------------------------------------------------------------------------- #


def test_c1_turn_b_asks_the_company_and_stores_the_question(two):
    two.say(_turn_a(), "b2155-nl-blue sales 2026")
    result, captured = two.say(_turn_b(), "dealer sales september 2026")
    assert QUESTION in _reply(result), _reply(result)
    assert not [a for a in _calls(captured, ANALYSIS) if a.get("company")], captured
    question = two.next_open_question()
    assert [w.casefold() for w in _option_words(question)] == ["sorento", "mocha"], (
        "the question the next turn's parser is shown must be the company question, "
        f"Sorento first, not the stale drill offer: {question}"
    )


# --------------------------------------------------------------------------- #
# C2 / C3 / C4 (RED) - the reply picks the company
# --------------------------------------------------------------------------- #


def test_c2_a_company_pick_reply_runs_the_analysis_for_sorento(two):
    _to_the_company_question(two)
    result, captured = two.say(_turn_c_company_pick(), "Sorento")
    reply = _reply(result)
    assert result.branch_kind == "business_query", (result.branch_kind, reply)
    assert "Routed to your PIC" not in reply, reply
    assert two.handoffs == [], f"a company answer is never handed to a person: {two.handoffs}"
    _assert_ran_for(captured, "Sorento")


def test_c3_a_brand_word_reply_runs_the_analysis_for_sorento_with_no_brand_filter(two):
    _to_the_company_question(two)
    # "Sorento" is a live brand as well as a company, so the resolver places it as one.
    matches = {**_PRODUCT_MATCH, "sorento": {"uuid": BRAND_UUID, "entity_type": "brand", "canonical_code": "SORENTO"}}
    result, captured = two.say(_turn_c_brand(), "Sorento", matches=matches)
    assert result.branch_kind == "business_query", (result.branch_kind, _reply(result))
    for name, args in captured:
        assert not [k for k, v in args.items() if "brand" in k and v], (
            f"the company answer is never a brand filter: {name} {args}"
        )
    _assert_ran_for(captured, "Sorento")
    focus = two.lane._session_of(two.session_factory).get("focus") or {}
    assert "sorento" not in [str(b).casefold() for b in focus.get("brands") or []], (
        f"the company answer is never held as a brand: {focus.get('brands')}"
    )


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param({"open_question_answer": _pick(2)}, id="picked-2"),
        pytest.param({"sales_company": "Mocha"}, id="sales-company"),
    ],
)
def test_c4_mocha_runs_the_analysis_for_mocha(two, answer):
    _to_the_company_question(two)
    qf = _parser_output(
        message_type="business_query", intent_hint=None, domain_hint=None, entities=[],
        entity_op="reuse", domain_in_message=False, **answer,
    )
    result, captured = two.say(qf, "Mocha")
    assert result.branch_kind == "business_query", (result.branch_kind, _reply(result))
    _assert_ran_for(captured, "Mocha")


# --------------------------------------------------------------------------- #
# G1 / G2 / G3 (GREEN guards)
# --------------------------------------------------------------------------- #


def test_g1_one_company_runs_straight_away(one):
    one.say(_turn_a(), "b2155-nl-blue sales 2026")
    result, captured = one.say(_turn_b(), "dealer sales september 2026")
    calls = _calls(captured, ANALYSIS)
    assert calls, captured
    assert calls[0].get("channel") == "dealer", calls[0]
    assert calls[0].get("date_from") == "2026-09-01" and calls[0].get("date_to") == "2026-09-30", calls[0]
    assert QUESTION not in _reply(result) and "*Sales, Sorento*" in _reply(result), _reply(result)


def test_g2_a_named_company_needs_no_question(two):
    two.say(_turn_a(), "b2155-nl-blue sales 2026")
    result, captured = two.say(_turn_b(sales_company="Mocha"), "dealer sales september 2026 mocha")
    calls = _calls(captured, ANALYSIS)
    assert calls and calls[0].get("company") == "Mocha", captured
    assert calls[0].get("channel") == "dealer", calls[0]
    assert QUESTION not in _reply(result), _reply(result)


def test_g3_another_ask_while_the_question_is_open_is_its_own_ask(two):
    _to_the_company_question(two)
    stock = _parser_output(
        message_type="business_query", intent_hint="check_stock", domain_hint="inventory",
        entities=[{"raw": "SRTWC286", "hint": "product", "canonical_code": None, "current_message": True, "confident": True}],
        entity_op="replace_combine", domain_in_message=True,
    )
    result, captured = two.say(stock, "stock for SRTWC286", matches={})
    assert _calls(captured, ANALYSIS) == [] and _calls(captured, REPORT) == [], captured
    assert QUESTION not in _reply(result), _reply(result)
    assert result.branch_kind == "business_query", (result.branch_kind, _reply(result))


# --------------------------------------------------------------------------- #
# E (RED) - crew re-verify of :3101 on a6ed31d89e: the company reply carried the parser's own
# `group_by: "date"`, which the axis check read BEFORE the slot's carried axes applied
# --------------------------------------------------------------------------- #


def _turn_e1() -> dict[str, Any]:
    """"dealer sales september 2026", as the parser emitted it live (v63, gpt-5.4-mini), with its basis named
    (one with none is asked the basis before the company: SALES-TOTAL-ASK)."""
    return _parser_output(
        domain_hint="sales", intent_hint="check_order", order_status="sales_analysis",
        sales_channel="dealer", sales_company=None, sales_basis="delivered", group_by="year",
        entities=[], entity_op="reuse", domain_in_message=True, **SEP_2026,
    )


def _turn_e2() -> dict[str, Any]:
    """"Sorento", as the parser emitted it live: the company, a pick of [1], and an axis of
    its own (`group_by: "date"`) that the bare reply never asked for."""
    return _parser_output(
        message_type="business_query", intent_hint="check_order", domain_hint="order",
        order_status="sales_analysis", group_by="date", sales_channel="dealer",
        sales_company="Sorento", sales_basis="delivered", entities=[], entity_op="reuse",
        reference_positions=[1], open_question_answer=None, domain_in_message=False,
        date_mode=None, date_filter_start=None, date_filter_end=None,
    )


def test_e_the_company_reply_runs_the_asked_analysis_whatever_axis_it_carries(two):
    result, _captured = two.say(_turn_e1(), "dealer sales september 2026")
    assert QUESTION in _reply(result), f"setup: turn 1 asks which company: {_reply(result)!r}"
    result, captured = two.say(_turn_e2(), "Sorento")
    assert "break sales down by" not in _reply(result), _reply(result)
    calls = _calls(captured, ANALYSIS)
    assert calls, f"the company reply must run the sales analysis: {captured}"
    args = calls[0]
    assert args.get("company") == "Sorento", args
    assert args.get("channel") == "dealer", f"the asked channel rides the question: {args}"
    assert args.get("date_from") == "2026-09-01" and args.get("date_to") == "2026-09-30", (
        f"the asked window rides the question: {args}"
    )
    assert args.get("rows") == "channel" and args.get("cols") == "year", (
        f"the asked axis (the Yearly comparison) rides the question, not the reply's own: {args}"
    )


# --------------------------------------------------------------------------- #
# E2 (RED, reviewer round E): no axis check is run on the reply to the company question
# --------------------------------------------------------------------------- #


def _held_slot(chat: Chat) -> dict[str, Any]:
    return (chat.lane._session_of(chat.session_factory).get("focus") or {}).get("required_ask") or {}


def test_e_b1_an_ask_with_no_axis_still_runs_for_the_picked_company(two):
    first = _turn_e1()
    first["group_by"] = "year"  # REPORT-UNIFY: only the Yearly comparison keeps the company question
    result, _c = two.say(first, "dealer sales september 2026")
    assert QUESTION in _reply(result), f"setup: turn 1 asks which company: {_reply(result)!r}"
    result, captured = two.say(_turn_e2(), "Sorento")
    assert "break sales down by" not in _reply(result), _reply(result)
    calls = _calls(captured, ANALYSIS)
    assert calls and calls[0].get("company") == "Sorento", captured
    assert calls[0].get("channel") == "dealer", calls[0]
    assert calls[0].get("date_from") == "2026-09-01" and calls[0].get("date_to") == "2026-09-30", calls[0]


def _unsettled(**answer: Any) -> dict[str, Any]:
    reply = _turn_e2()
    reply.update(sales_company=None, **answer)
    return reply


@pytest.mark.parametrize(
    "reply, text, expect",
    [
        pytest.param(
            _unsettled(reference_positions=[5],
                       open_question_answer={"mode": "pick", "picked": [5], "items": [], "qty_for_all": None}),
            "5", "reask", id="out-of-range-pick",
        ),
        pytest.param(
            _unsettled(reference_positions=[],
                       open_question_answer={"mode": "cancel", "picked": [], "items": [], "qty_for_all": None}),
            "cancel", "cancelled", id="cancel",
        ),
    ],
)
def test_e_s1_an_unsettled_reply_gets_the_questions_own_line(two, reply, text, expect):
    result, _c = two.say(_turn_e1(), "dealer sales september 2026")
    assert QUESTION in _reply(result), f"setup: turn 1 asks which company: {_reply(result)!r}"
    result, captured = two.say(reply, text)
    assert "break sales down by" not in _reply(result), _reply(result)
    assert _calls(captured, ANALYSIS) == [], captured
    if expect == "reask":
        assert _held_slot(two).get("ask") == "sales_company", (
            "an out-of-range pick re-asks: the company question stays open", _held_slot(two), _reply(result),
        )
    else:
        assert "Sales report cancelled." in _reply(result), _reply(result)
