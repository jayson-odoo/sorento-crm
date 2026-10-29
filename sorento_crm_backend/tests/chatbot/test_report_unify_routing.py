"""Phase 2 RED tests - REPORT-UNIFY slice 2: the chatbot routes every sales total, breakdown and
outstanding ask to `crm_report_ask`.

`documentation/plans/reports/PLAN-report-unify-27oct.md` section 0 (rulings Q1, Q2, Q4) and section 2,
UAC AC-RU-10 to AC-RU-17, cases named after the owner messages (H) and prod turns (P) of
`CARD-report-unify-27oct.md` section 3.

Full console turns, the harness of `tests/chatbot/test_report_ask_lane.py`: the REAL engine, lane and MCP
presenter; only the parser and the MCP transport are doubles. Unlike that file's `Console.say`, this one
returns EVERY tool call of the turn as `(name, args)`, so "never `crm_sales_report`" is a plain assertion.

Readings the tester PINNED where the contract is silent (flagged to the captain):
* The outstanding KIND travels in the parser's `basis` key, the same key the sales ranking already reads:
  `outstanding` (undelivered order qty), `pending_delivery`, `unpaid`; None or absent = the message did not
  name one. A parse with `order_status: "outstanding"` and no kind asks; the reply turn's `basis` answers.
* A breakdown ("by X") whose parse carries no `measure` is asked "By quantity or by amount?" today and is left
  that way: the breakdown cases below carry `measure: "amount"` so they pin the ROUTING only. P9 as the card
  words it expects no such question; if the owner wants none for a breakdown, say so and the case moves.
* A sales TOTAL (no `group_by`) asks no measure (the total carries qty and RM) but does ask the basis when the
  parser read none (AC-RU-16). The cases below that expect a direct call therefore carry `basis: "delivered"`.
* An outstanding kind never asks a period: absent dates send NO `date_from` / `date_to` (AC-RU-8c).
* A product travels as `product_code` and a spec as `spec: ["key:value"]` (S4 of REPORT-ENGINE; plan section 1).
* Reply wording is free except: the kind question names "undelivered orders", "pending delivery" and
  "unpaid invoices"; a "Not applied:" line names the filter by its label ("Location"); no reply may carry a
  snake_case token (the harness asserts that on every turn, so a raw reason code printed as is fails).
* "Ask instead when the filter was the only subject" is pinned as: the reply is a question (ends with "?") and
  carries no figures; whether the route was called first is left free.
* The Invoiced option and the Invoiced-first order of the basis question land with PR #1916 (not on this
  branch), so the AC-RU-16 guard here asserts only that a missing basis is asked and nothing runs.
* Cases that already pass today are regression pins of routing the engine seam already does (a brand-only total,
  a month / channel / customer / product / brand / category breakdown, the fetch allow-list): listed in the
  report. The card's "can't break sales down" replies came from older parser versions.
* The analytics connector loses only `crm_top_selling_report` (plan section 2.6); the three retired chat
  tools stay in `REUSED_TOOLS` and the MCP catalog.

AC-RU-16 standing rulings that existing suites already pin, referenced and not duplicated:
one question for period + measure + basis (`test_report_ask_lane.py::test_ac_re_18c_*`, `test_report_ask_clarify.py`);
"by X" keeps the filters (`test_report_drilldown_lane.py`, `test_one_ranking_r5_axis_refine.py`);
the Sales report switch (`test_sales_domain_routing.py`); "my ..." from an ungranted salesperson
(`test_report_smart_my_sales_lane.py`). Those suites will need their `crm_sales_report` expectations moved by
the coder; that is a consequence of Q1, not a gap in this file.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

from app.services.chatbot import engine as engine_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.test_engine import CONTACT_ID, _parser_output
from tests.chatbot.test_outstanding_lane import AnswerServices, FetchServices, _present_response
from tests.chatbot.test_report_ask_lane import (  # noqa: F401  (console is a fixture)
    CUSTOMER_NAME,
    PRODUCT_CODE,
    TOOL,
    _SNAKE,
    _e,
    _fake_body,
    _rank,
    _reply,
    console,
)

if importlib.util.find_spec("sorento_crm_mcp") is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "sorento_crm_mcp"))

_LAST: dict[str, str] = {"text": ""}
RETIRED = ("crm_sales_report", "crm_outstanding_report", "crm_sales_analysis")
YEAR = {"date_filter_start": "2026-01-01", "date_filter_end": "2026-12-31"}
SEP = {"date_filter_start": "2026-09-01", "date_filter_end": "2026-09-30"}
OCT = {"date_filter_start": "2026-10-01", "date_filter_end": "2026-10-31"}
NO_DATES = {"date_filter_start": None, "date_filter_end": None}
KIND_WORDS = ("undelivered orders", "pending delivery", "unpaid invoices")
KIND_QUESTION = "Undelivered orders or pending delivery?"
MEASURE_Q = "By quantity or by amount?"
BASIS_LABELS = {
    "delivered": "delivered sales", "ordered": "ordered sales", "outstanding": "outstanding orders",
    "pending_delivery": "pending delivery", "unpaid": "unpaid invoices",
}
P_TRAP = {
    "raw": "p trap", "hint": "specification", "canonical_code": None, "spec_key": "trap_type",
    "spec_value": "p_trap", "current_message": True, "confident": True,
}


# ------------------------------------------------------------------------- harness


class Routing:
    """Console turns that return every tool call; `extra_body` is merged over the route's fake body."""

    def __init__(self, console_) -> None:
        self.console = console_
        self.extra_body: dict[str, Any] = {}

    @property
    def ids(self) -> dict[str, str]:
        return self.console.ids

    def say(self, qf: dict[str, Any], body: str) -> tuple[str, list[tuple[str, dict[str, Any]]]]:
        from app.services.chatbot import console_service
        from app.services.chatbot.head import parser as parser_mod

        c = self.console
        c.monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: qf)
        calls: list[tuple[str, dict[str, Any]]] = []
        present = _present_response()

        def _mcp(name: str, args: dict[str, Any]) -> Any:
            calls.append((name, dict(args)))
            if name != TOOL:
                return json.dumps({"has_result": False, "items": []})
            fake = _fake_body(args)
            fake["basis_label"] = BASIS_LABELS.get(args.get("basis", "delivered"), fake["basis_label"])
            fake.update(copy.deepcopy(self.extra_body))
            return present(name, json.dumps(fake))

        c.monkeypatch.setattr(engine_mod.business_services, "fetch_services", lambda db: FetchServices(mcp_call=_mcp))
        c.monkeypatch.setattr(
            engine_mod.business_services,
            "answer_services_for",
            lambda session_factory: AnswerServices(
                mcp_probe=lambda name, args: {"data": []}, family_fetch=lambda query: {"data": []}
            ),
        )
        db = c.session_factory()
        try:
            result = console_service.run_console_turn(
                db, contact_respond_id=str(CONTACT_ID), text=body,
                session_vars=copy.deepcopy(c.session_vars), run_id="zzt-report-unify-routing",
            )
        finally:
            db.close()
        c.session_vars = result.session_vars or {}
        text = result.reply_text or ""
        _LAST["text"] = text
        assert not _SNAKE.search(text), (body, text)
        assert chr(0x2014) not in text and chr(0x2013) not in text, body
        return text, calls


@pytest.fixture
def bot(console) -> Routing:
    """The harness contact as STAFF (an office access type): the prod askers of the card are staff, and an
    unlinked non-staff contact is refused any named customer by the lane's own V1-DOC-SCOPE gate before a
    report is reached (a gate this lane does not change)."""
    from tests.chatbot._turn_helpers import make_office_access_type

    make_office_access_type(console.session_factory, CONTACT_ID)
    return Routing(console)


def _named(calls, name):
    return [a for n, a in calls if n == name]


def _only_report_ask(calls) -> dict[str, Any]:
    """Exactly one tool call in the turn and it is `crm_report_ask`; its args."""
    assert [n for n, _a in calls] == [TOOL], (calls, "REPLY:", _LAST["text"])
    return calls[0][1]


def _status(status: str, *entities: dict[str, Any], **over: Any) -> dict[str, Any]:
    """The parser's reading of a sales / outstanding ask that is not a ranking."""
    base: dict[str, Any] = dict(
        domain_hint="order", intent_hint="check_order", order_status=status, entities=list(entities),
        group_by=None, top_n=None, measure=None, basis="delivered", ranking_refine=False, **YEAR,
    )
    base.update(over)
    return _parser_output(**base)


def _customer(c: Routing) -> dict[str, Any]:
    return _e(CUSTOMER_NAME, "customer")


# ================================================================ AC-RU-10: a sales total is crm_report_ask


def test_h4_sales_agent_total_for_a_product_is_one_report_ask_with_the_agent_and_no_grouping(bot) -> None:
    """AC-RU-10 / H4 "sales agent yu total sale for SRTSP231 in 2026": agent filter kept, never crm_sales_report."""
    text, calls = bot.say(
        _status("sales_report", _e("AGENT A", "sales_agent"), _e(PRODUCT_CODE, "product")),
        "sales agent agent a total sale for SRTWT7408 in 2026",
    )
    args = _only_report_ask(calls)
    assert args["sales_agent_ids"] == [bot.ids["agent"]], args
    assert args["product_code"] == PRODUCT_CODE, args
    assert not args.get("group_by"), args
    assert args["basis"] == "delivered", args
    assert args["date_from"] == "2026-01-01" and args["date_to"] == "2026-12-31", args
    assert "AGENT A" in text or "1,200" in text, text


@pytest.mark.parametrize(
    "entities, key",
    [
        (lambda b: [_e(CUSTOMER_NAME, "customer")], "customer_ids"),
        (lambda b: [_e("Sorento", "brand")], "brand_ids"),
        (lambda b: [_e("ZZT CATEGORY", "category")], "category_ids"),
        (lambda b: [_e("AGENT A", "sales_agent")], "sales_agent_ids"),
        (lambda b: [_e(PRODUCT_CODE, "product")], "product_code"),
    ],
    ids=["customer", "brand", "category", "agent", "product"],
)
def test_ac_ru_10_a_sales_total_naming_one_subject_is_report_ask_with_no_grouping(bot, entities, key) -> None:
    """AC-RU-10: a customer, product, agent, brand or category total: crm_report_ask, no group_by."""
    _text, calls = bot.say(_status("sales_report", *entities(bot)), "total sales this year")
    args = _only_report_ask(calls)
    assert key in args and args[key], args
    assert not args.get("group_by") and "top_n" not in args, args


def test_p5_customer_total_for_october_is_report_ask_with_the_customer_and_no_breakdown_refusal(bot) -> None:
    """AC-RU-10 / P5 "Dealer <Customer B> oct total sales": customer filter, October, total; no refusal line."""
    text, calls = bot.say(_status("sales_report", _customer(bot), **OCT), "dealer zzt rank customer oct total sales")
    args = _only_report_ask(calls)
    assert args["customer_ids"] == [bot.ids["customer"]], args
    assert not args.get("group_by"), args
    assert args["date_from"] == "2026-10-01" and args["date_to"] == "2026-10-31", args
    assert "break sales down" not in text.lower() and "can't break" not in text.lower(), text


# ================================================================ AC-RU-12: "by X" is crm_report_ask with that grouping


def test_p9_total_sale_for_all_sale_agents_is_report_ask_grouped_by_sales_agent(bot) -> None:
    """AC-RU-12 / P9 "Total sale for all sale agents on September 2026": group_by sales_agent, no refusal."""
    text, calls = bot.say(
        _status("sales_report", group_by="sales_agent", measure="amount", **SEP),
        "Total sale for all sale agents on September 2026"
    )
    args = _only_report_ask(calls)
    assert args["group_by"] == "sales_agent", args
    assert args["date_from"] == "2026-09-01" and args["date_to"] == "2026-09-30", args
    assert args.get("top_n"), "a breakdown lists every row, so the route is given a count (it needs one)"
    assert "break sales down" not in text.lower() and "can't break" not in text.lower(), text


@pytest.mark.parametrize("axis", ["month", "channel"])
def test_ac_ru_12_sales_analysis_by_month_or_channel_is_report_ask_never_crm_sales_analysis(bot, axis) -> None:
    """AC-RU-12: a sales analysis by month / channel runs crm_report_ask with that grouping."""
    _text, calls = bot.say(
        _status(
            "sales_analysis", group_by=axis, measure="amount", sales_basis="delivered", sales_company=None, basis=None
        ),
        f"sales analysis by {axis} 2026",
    )
    args = _only_report_ask(calls)
    assert args["group_by"] == axis, args
    assert args["basis"] == "delivered", args
    assert not _named(calls, "crm_sales_analysis"), calls


@pytest.mark.parametrize("axis", ["customer", "product", "brand", "category"])
def test_ac_ru_12_a_sales_report_by_any_axis_the_old_tool_could_not_draw_is_report_ask(bot, axis) -> None:
    """AC-RU-12: by customer / product / brand / category: crm_report_ask, no 'cannot break down' reply."""
    text, calls = bot.say(_status("sales_report", group_by=axis, top_n=10, measure="amount"), f"sales by {axis} 2026")
    args = _only_report_ask(calls)
    assert args["group_by"] == axis, args
    assert "can't break" not in text.lower(), text


# ================================================================ AC-RU-11: outstanding is never defaulted


def test_ac_ru_11_an_outstanding_ask_naming_no_kind_asks_the_three_kinds_and_runs_nothing(bot) -> None:
    """AC-RU-11 / P7, P12, R: order_status outstanding with a customer and no kind: no tool call, the kinds asked."""
    text, calls = bot.say(
        _status("outstanding", _customer(bot), basis=None, **NO_DATES), "outstanding for zzt rank customer"
    )
    assert calls == [], calls
    lowered = text.lower()
    assert all(word in lowered for word in KIND_WORDS), text
    assert "?" in text, text


def test_ac_ru_11_the_kind_question_is_the_owners_wording(bot) -> None:
    """AC-RU-11: the question reads "Undelivered orders or pending delivery?"."""
    text, calls = bot.say(_status("outstanding", _customer(bot), basis=None, **NO_DATES), "outstanding")
    assert calls == [] and KIND_QUESTION in text, text


def test_ac_ru_11_the_kind_is_folded_into_the_one_question_with_the_measure_of_a_ranking(bot) -> None:
    """AC-RU-11: a ranking that also lacks its measure gets ONE reply asking both (the plan's folded question)."""
    text, calls = bot.say(
        _status("outstanding", group_by="customer", top_n=5, measure=None, basis=None, **NO_DATES),
        "top 5 customers outstanding",
    )
    assert calls == [], calls
    assert KIND_QUESTION in text and MEASURE_Q in text, text


def test_ac_ru_11_the_reply_naming_the_kind_runs_the_first_ask_with_its_filters_kept(bot) -> None:
    """AC-RU-11: the answer ("unpaid invoices") calls crm_report_ask basis unpaid with the customer; the
    period is not asked."""
    text, calls = bot.say(_status("outstanding", _customer(bot), basis=None, **NO_DATES), "outstanding for zzt rank customer")
    assert calls == [] and KIND_QUESTION in text, text
    _text, calls = bot.say(_reply(basis="unpaid", open_question_answer={"mode": "fill", "picked": [], "items": [], "qty_for_all": None}), "unpaid invoices")
    args = _only_report_ask(calls)
    assert args["basis"] == "unpaid", args
    assert args["customer_ids"] == [bot.ids["customer"]], args
    assert "date_from" not in args and "date_to" not in args, args


@pytest.mark.parametrize(
    "kind, group_by, top_n",
    [("outstanding", "product", 10), ("pending_delivery", "product", 10), ("unpaid", None, None)],
)
def test_p7_a_named_kind_runs_report_ask_with_the_customer_and_brand_kept_and_no_period(
    bot, kind, group_by, top_n
) -> None:
    """AC-RU-11 / P7 "<Customer C> any outstanding mocha item in sales order": the kind named in the message is
    not asked; basis = that kind; customer and brand ride along; no date is sent or asked."""
    text, calls = bot.say(
        # (A ranking by an axis names its measure, phase 3 S5: one question for everything missing, card section 3.)
        _status("outstanding", _customer(bot), _e("Sorento", "brand"), basis=kind, group_by=group_by, top_n=top_n,
                measure="amount" if group_by else None, **NO_DATES),
        f"{kind} for zzt rank customer sorento",
    )
    args = _only_report_ask(calls)
    assert args["basis"] == kind, args
    assert args["customer_ids"] == [bot.ids["customer"]], args
    assert args["brand_ids"] == [bot.ids["brand"]], args
    assert (args.get("group_by") or None) == group_by, args
    assert "date_from" not in args and "date_to" not in args, args
    assert KIND_QUESTION not in text and "Which period" not in text, text
    assert not _named(calls, "crm_outstanding_report"), calls


def test_p12_dealers_outstanding_for_a_product_is_report_ask_by_customer(bot) -> None:
    """AC-RU-11 / P12 "dealers outstanding for srtub206": kind named (undelivered), product, by customer."""
    _text, calls = bot.say(
        _status("outstanding", _e(PRODUCT_CODE, "product"), basis="outstanding", group_by="customer", top_n=10,
                measure="amount", **NO_DATES),  # a ranking names its measure (phase 3 S5)
        "dealers outstanding for srtwt7408",
    )
    args = _only_report_ask(calls)
    assert args["basis"] == "outstanding" and args["group_by"] == "customer", args
    assert args["product_code"] == PRODUCT_CODE, args


def test_ac_ru_11_an_outstanding_period_the_message_names_is_sent(bot) -> None:
    """AC-RU-8c via the lane: a named period filters (dates sent); only an ABSENT one means all dates."""
    _text, calls = bot.say(
        _status("outstanding", _customer(bot), basis="pending_delivery", **SEP), "pending delivery for zzt rank customer in Sep"
    )
    args = _only_report_ask(calls)
    assert args["date_from"] == "2026-09-01" and args["date_to"] == "2026-09-30", args


# ================================================================ AC-RU-13: a spec is a route param


def test_h1_brand_category_and_spec_run_the_ranking_with_the_spec_param_and_no_generic_gate(bot) -> None:
    """AC-RU-13 / H1 "top 100 hot selling sorento p trap wc in 2026, by delivered qty": spec ["trap_type:p_trap"],
    brand and category kept, the "need a filter" reply never replaces the ranking."""
    text, calls = bot.say(
        _rank(
            _e("Sorento", "brand"), _e("ZZT CATEGORY", "category"), dict(P_TRAP),
            group_by="product", top_n=100, measure="qty", basis="delivered", **YEAR,
        ),
        "top 100 hot selling sorento p trap wc in 2026, by delivered qty",
    )
    args = _only_report_ask(calls)
    assert args["spec"] == ["trap_type:p_trap"], args
    assert args["brand_ids"] == [bot.ids["brand"]] and args["category_ids"] == [bot.ids["category"]], args
    assert args["group_by"] == "product" and args["top_n"] == 100, args
    assert "at least one filter" not in text and "every sales order" not in text, text
    assert "AGENT A" in text or "1,200" in text, text


def test_ac_ru_13_a_spec_alone_on_a_total_is_a_spec_param_and_the_header_names_it(bot) -> None:
    """AC-RU-13: the route echoes the spec; the reply header names it ("Spec: Trap type: P-trap")."""
    bot.extra_body = {
        "filters": [{"key": "spec", "label": "Spec", "values": ["Trap type: P-trap"]}],
    }
    text, calls = bot.say(_status("sales_report", dict(P_TRAP)), "p trap sales 2026")
    args = _only_report_ask(calls)
    assert args["spec"] == ["trap_type:p_trap"], args
    assert "P-trap" in text, text


# ================================================================ AC-RU-14: Not applied


def test_ac_ru_14_a_filter_the_route_could_not_apply_prints_a_not_applied_line_and_keeps_the_figures(bot) -> None:
    """AC-RU-14: not_applied [{location, per_document}] -> a line "Not applied: Location ..." under the header;
    the unpaid figure is still printed."""
    bot.extra_body = {
        "not_applied": [{"filter": "location", "value": "BRW", "reason": "per_document"}],
        "total": {"qty": 0, "amount": 1200.0},
    }
    text, calls = bot.say(
        _status("outstanding", _customer(bot), _e("BRW", "warehouse"), basis="unpaid", **NO_DATES),
        "unpaid invoices for zzt rank customer in BRW",
    )
    _only_report_ask(calls)
    lines = [ln for ln in text.splitlines() if ln.startswith("Not applied:")]
    assert len(lines) == 1, text
    assert "location" in lines[0].lower(), lines
    assert "1,200" in text, text


def test_ac_ru_14_a_not_applied_filter_that_was_the_only_subject_asks_instead_of_answering(bot) -> None:
    """AC-RU-14 / Q4: unpaid invoices are per document, so a product as the ONLY subject is a question, no figures."""
    bot.extra_body = {
        "not_applied": [{"filter": "product", "value": PRODUCT_CODE, "reason": "per_document"}],
        "total": {"qty": 0, "amount": 1200.0},
    }
    text, _calls = bot.say(
        _status("outstanding", _e(PRODUCT_CODE, "product"), basis="unpaid", **NO_DATES), "unpaid invoices for srtwt7408"
    )
    assert text.strip().endswith("?"), text
    assert "1,200" not in text and not text.startswith("Not applied:"), text
    lowered = text.lower()
    # A real question about the ask, not the old "no orders found / escalate" miss.
    assert "escalate" not in lowered and "no orders found" not in lowered and "couldn't find" not in lowered, text
    assert "unpaid" in lowered or "invoice" in lowered, text


def test_ac_ru_14_a_reply_with_nothing_not_applied_has_no_not_applied_line(bot) -> None:
    """AC-RU-14 control: no `not_applied` from the route, no line."""
    text, calls = bot.say(_status("sales_report", _customer(bot)), "total sales for zzt rank customer 2026")
    _only_report_ask(calls)
    assert "Not applied" not in text, text


# ================================================================ AC-RU-15: a product named now replaces a carried one


def _second_product(session_factory, code: str) -> None:
    from tests._mc_lookup_seed import product

    db = session_factory()
    try:
        product(db, company_id=DEFAULT_COMPANY_ID, code=code)
        db.commit()
    finally:
        db.close()


def test_p4_a_product_named_this_turn_replaces_the_carried_product(bot) -> None:
    """AC-RU-15 / P4: turn 1 is a total on PRODUCT_CODE; turn 2 "per agent for <other> in Sept" is a refine
    that names another product and carries the first: the args hold the NAMED product only."""
    other = "SRTWT9999"
    _second_product(bot.console.session_factory, other)
    _text, calls = bot.say(
        _rank(_e(PRODUCT_CODE, "product"), group_by=None, top_n=None, **YEAR), f"total sales for {PRODUCT_CODE}"
    )
    _only_report_ask(calls)
    carried = dict(_e(PRODUCT_CODE, "product"), current_message=False)
    _text, calls = bot.say(
        _rank(_e(other, "product"), carried, group_by="sales_agent", top_n=10, ranking_refine=True, **SEP),
        f"how many {other} each salesman sold in September",
    )
    args = _only_report_ask(calls)
    assert args["product_code"] == other, args
    assert PRODUCT_CODE not in json.dumps(args), args


# ================================================================ AC-RU-16: standing rulings (guard)


def test_ac_ru_16_a_sales_total_with_no_basis_is_asked_and_nothing_runs(bot) -> None:
    """AC-RU-16: the basis is never defaulted on a total either. (Invoiced-first wording lands with #1916.)"""
    text, calls = bot.say(_status("sales_report", _e(PRODUCT_CODE, "product"), basis=None), "total sales for srtwt7408 2026")
    assert calls == [], calls
    lowered = text.lower()
    assert "delivered" in lowered and "ordered" in lowered and "?" in text, text
    # Owner ruling 27 Oct ~23:35 (lane SALES-TOTAL-ASK): Invoiced is offered, and offered first.
    assert "invoiced" in lowered and lowered.index("invoiced") < lowered.index("delivered"), text


def test_ac_ru_16_a_total_naming_no_subject_and_no_basis_is_asked_never_defaulted_to_invoiced(bot) -> None:
    """AC-RU-16 (owner ruling 27 Oct ~23:35): "total sales 2026" with no basis is asked, Invoiced first; the
    old sales analysis default (invoiced) never answers it."""
    text, calls = bot.say(
        _status("sales_analysis", group_by=None, measure=None, sales_basis=None, sales_company=None, basis=None),
        "total sales 2026",
    )
    assert calls == [], calls
    lowered = text.lower()
    assert "?" in text and "invoiced" in lowered and "delivered" in lowered, text
    assert lowered.index("invoiced") < lowered.index("delivered"), text


# ================================================================ AC-RU-17: the retired tools are gone


@pytest.mark.parametrize("row_name", ["order", "sales"])
def test_ac_ru_17_the_order_and_sales_policy_rows_no_longer_list_the_retired_chat_tools(row_name) -> None:
    """AC-RU-17: turn/policy_rows.py `order` and `sales` rows drop crm_sales_report, crm_outstanding_report and
    crm_sales_analysis, and keep crm_report_ask."""
    from app.services.chatbot.turn.policy_rows import DEFAULT_DOMAIN_ROWS

    (row,) = [r for r in DEFAULT_DOMAIN_ROWS if r["name"] == row_name]
    assert not set(RETIRED) & set(row["tools"]), row["tools"]
    assert "crm_report_ask" in row["tools"], row["tools"]


def test_ac_ru_17_the_mcp_catalog_has_no_top_selling_tool() -> None:
    """AC-RU-17: sorento_crm_mcp's CATALOG no longer carries crm_top_selling_report."""
    from sorento_crm_mcp.catalog import CATALOG

    assert "crm_top_selling_report" not in {spec.name for spec in CATALOG}


def test_ac_ru_17_the_mcp_report_ask_tool_takes_the_spec_param() -> None:
    """Plan section 1 + 2: the route's `spec` param is declared on the MCP tool the lane calls."""
    from sorento_crm_mcp.catalog import CATALOG

    (spec,) = [s for s in CATALOG if s.name == "crm_report_ask"]
    assert "spec" in spec.query_params, spec.query_params


def test_ac_ru_17_the_analytics_connector_no_longer_reuses_the_top_selling_tool() -> None:
    """AC-RU-17: services/analytics_connector/reused_tools.py drops crm_top_selling_report."""
    from app.services.analytics_connector.reused_tools import REUSED_TOOLS

    assert "crm_top_selling_report" not in {t["name"] for t in REUSED_TOOLS}


def test_ac_ru_17_the_fetch_allow_list_no_longer_names_the_top_selling_tool() -> None:
    """AC-RU-17: the chatbot's read-only allow-list (pinned equal to the MCP catalog by CI) has no top selling."""
    from app.services.chatbot.lanes.business.fetch import CHATBOT_READ_ONLY_TOOLS

    assert "crm_top_selling_report" not in CHATBOT_READ_ONLY_TOOLS
