"""REPORT-SMART-L R9 (EVAL-BENCH gate round 3, production parser v63, gpt-5.4-mini; crew ruling):

(1) The `Sales channels:` line prints only when the prompt in use names it (owner ruling 22 Oct 23:20,
    PLAN-report-smart-owner-1022.md:40-45: the line pairs with the template rule that names it; v63 names none).
(2) An axis-less ranking reply to a held sales figure runs the TOTAL on the held product and period.
(3) Ruling A on v63: a ranking parse with no typed axis and no count, right after a sales report total (its drill
    offer open), answers that total: delivered (or no basis) re-runs the sales report; ordered or outstanding runs
    the report-ask total on the held product and period.

Real engine seam, the v63 shapes (no State block, `state_changes` null), row 1 the sales report total rendered by
the MCP presenter (so its drill offer is armed, as live). Fake codes."""
from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import parser as parser_mod
from tests.chatbot.test_engine import CONTACT_ID, _parser_output, seeded, stub_access  # noqa: F401
from tests.chatbot.test_one_ranking_r5_axis_refine import YEAR_2026, _ran
from tests.chatbot.test_one_ranking_r8_v63_carry import BASIS_Q, FILL, HOW_MANY, PERIOD_Q, _row1, _row2, _v63
from tests.chatbot.test_outstanding_lane import AnswerServices, FetchServices, _present_response
from tests.chatbot.test_report_ask_lane import PRODUCT_CODE, TOOL, _e, _fake_body, console  # noqa: F401

SALES_REPORT_TOOL = "crm_sales_report"
SALES_BODY = {
    "status": "ok", "customer_name": None, "product_code": PRODUCT_CODE, "product_codes": [PRODUCT_CODE],
    "channel": None, "channel_shown": False, "date_from": "2026-01-01", "date_to": "2026-12-31", "grain": "month",
    "group_by": None, "total": {"qty": 30, "amount": 1200.0},
    "periods": [{"from": "2026-03-01", "to": "2026-03-31", "qty": 30, "amount": 1200.0}],
    "options": [
        {"key": "customer", "label": "By customer"}, {"key": "product", "label": "By product"},
        {"key": "sales_agent", "label": "By sales agent"}, {"key": "delivery_order", "label": "Delivery orders"},
    ],
}


@pytest.fixture(autouse=True)
def _fresh_caches():
    """The registry caches a prompt per (name, label) for a minute: a template left by an earlier test would answer."""
    from app.services import ai_prompt_registry
    from app.services import chatbot_prompt_vars as pv

    ai_prompt_registry.bust_cache()
    pv.clear_cache()
    yield
    ai_prompt_registry.bust_cache()
    pv.clear_cache()


def _turn(
    console, monkeypatch, qf: dict[str, Any], body: str, *, sales_body: dict[str, Any] | None = None
) -> tuple[str, list[tuple[str, dict[str, Any]]]]:
    """One console turn: the parse is `qf`; the sales report and the report ask answer through the MCP presenter."""
    from app.services.chatbot import console_service

    log: list[tuple[str, dict[str, Any]]] = []
    present = _present_response()

    def _mcp(name: str, args: dict[str, Any]) -> Any:
        log.append((name, dict(args)))
        if name == SALES_REPORT_TOOL:
            return present(name, json.dumps(sales_body or SALES_BODY))
        if name == TOOL:
            return present(name, json.dumps(_fake_body(args)))
        return json.dumps({"has_result": False, "items": []})

    monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: qf)
    monkeypatch.setattr(engine_mod.business_services, "fetch_services", lambda db: FetchServices(mcp_call=_mcp))
    monkeypatch.setattr(
        engine_mod.business_services, "answer_services_for",
        lambda session_factory: AnswerServices(mcp_probe=lambda n, a: {"data": []}, family_fetch=lambda q: {"data": []}),
    )
    db = console.session_factory()
    try:
        result = console_service.run_console_turn(
            db, contact_respond_id=str(CONTACT_ID), text=body,
            session_vars=copy.deepcopy(console.session_vars), run_id="zzt-r9-total",
        )
    finally:
        db.close()
    console.session_vars = result.session_vars or {}
    return result.reply_text or "", log


def _calls(log, name: str) -> list[dict[str, Any]]:
    return [a for n, a in log if n == name]


def _total(console, monkeypatch) -> tuple[str, dict[str, Any]]:
    # REPORT-UNIFY: a sales report total is the report ask's total (the retired sales report tool and its drill offer).
    text, log = _turn(console, monkeypatch, _row1(), f"Top sales for {PRODUCT_CODE.lower()} in 2026")
    (args,) = _ran(log)
    assert not args.get("group_by") and not _calls(log, SALES_REPORT_TOOL), ("setup", text, log)
    return text, args


def _top_selling(**over: Any) -> dict[str, Any]:
    """v63's other reading of "qty, delivered": the top selling label, no count, no grain."""
    base: dict[str, Any] = dict(order_status="top_selling", top_n=None, rank_by="quantity", basis="delivered",
                                rank_group=None, rank_direction=None, open_question_answer=dict(FILL))
    base.update(over)
    return _v63(**base)


def _axisless(**over: Any) -> dict[str, Any]:
    """'qty, delivered' read as a sales ranking with no axis: group_by null, measure qty, basis delivered, reuse."""
    return _row2(**{"group_by": None, **over})


def _no_question(text: str) -> None:
    for q in (HOW_MANY, PERIOD_Q, BASIS_Q):
        assert q not in text, text


# ------------------------------------------------ (1) the Sales channels line follows the prompt


@pytest.mark.parametrize("names_it", [True, False], ids=["template_names_it", "v63_names_none"])
@pytest.mark.parametrize("mode", ["block", "index"])
def test_r9_1_the_sales_channels_line_prints_only_when_the_prompt_names_it(
    session_factory, seeded, stub_access, monkeypatch, mode, names_it
) -> None:
    from tests.chatbot import test_closed_lists_index_mode as idx

    if names_it:
        monkeypatch.setattr(idx, "TEMPLATE", idx.TEMPLATE + "\nThe Sales channels line lists the channel values.\n")
    idx._seed_world(session_factory)
    idx._set_mode(session_factory, mode)
    [(_system, block, _r)] = idx._turns(session_factory, stub_access, monkeypatch, [("zzqwerty", idx._quiet())])
    lines = idx._lines(block, "Sales channels")
    assert lines == (["Sales channels: dealer, project"] if names_it else []), block


# ------------------------------------------------ (3) ruling A: the reply answers the held sales report total


def test_r9_2_an_axisless_ranking_reply_re_runs_the_sales_report(console, monkeypatch) -> None:
    first, args = _total(console, monkeypatch)
    text, log = _turn(console, monkeypatch, _axisless(), "qty, delivered")
    ran = _ran(log)  # the held total again (the reply adds its measure)
    assert len(ran) == 1 and _calls(log, SALES_REPORT_TOOL) == [], (text, log)
    assert not ran[0].get("group_by") and ran[0]["product_code"] == args["product_code"], ran
    assert ran[0]["date_from"] == args["date_from"] and ran[0]["basis"] == "delivered", ran
    assert "Total" in text, text
    _no_question(text)


def test_r9_3_a_top_selling_reply_with_no_count_and_no_grain_re_runs_the_sales_report(console, monkeypatch) -> None:
    first, args = _total(console, monkeypatch)
    text, log = _turn(console, monkeypatch, _top_selling(), "qty, delivered")
    ran = _ran(log)  # the held total again (the reply adds its measure)
    assert len(ran) == 1 and _calls(log, SALES_REPORT_TOOL) == [], (text, log)
    assert not ran[0].get("group_by") and ran[0]["product_code"] == args["product_code"], ran
    assert ran[0]["date_from"] == args["date_from"] and ran[0]["basis"] == "delivered", ran
    assert "Total" in text, text


def test_r9_4_an_ordered_basis_runs_the_report_ask_total_on_the_held_product_and_period(console, monkeypatch) -> None:
    _total(console, monkeypatch)
    text, log = _turn(console, monkeypatch, _axisless(basis="ordered"), "qty, ordered")
    ran = _ran(log)
    assert len(ran) == 1 and not _calls(log, SALES_REPORT_TOOL), (text, log)
    args = ran[0]
    assert not args.get("group_by") and "top_n" not in args, args
    assert args["product_code"] == PRODUCT_CODE and args["basis"] == "ordered" and args["measure"] == "qty", args
    assert args["date_from"] == "2026-01-01" and args["date_to"] == "2026-12-31", args
    _no_question(text)


def test_r9_4b_an_outstanding_top_selling_reply_runs_the_report_ask_total(console, monkeypatch) -> None:
    _total(console, monkeypatch)
    text, log = _turn(console, monkeypatch, _top_selling(basis="outstanding"), "qty, outstanding")
    ran = _ran(log)
    assert len(ran) == 1 and not ran[0].get("group_by") and ran[0]["basis"] == "outstanding", (text, log)
    assert ran[0]["product_code"] == PRODUCT_CODE and ran[0]["date_from"] == "2026-01-01", ran
    _no_question(text)


# ------------------------------------------------ guards


def test_r9_guard_a_typed_axis_keeps_r8_and_asks_only_the_count(console, monkeypatch) -> None:
    _total(console, monkeypatch)
    text, log = _turn(console, monkeypatch, _row2(), "qty, delivered")
    assert _ran(log) == [] and not _calls(log, SALES_REPORT_TOOL), (text, log)
    assert text == HOW_MANY, text


def test_r9_guard_a_typed_count_keeps_the_ranking(console, monkeypatch) -> None:
    _total(console, monkeypatch)
    v = _v63(group_by="customer", top_n=5, ranking_refine=False, measure="qty", rank_by="quantity", basis="delivered")
    text, log = _turn(console, monkeypatch, v, "top 5 by customer")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == "customer" and ran[0]["top_n"] == 5, (text, log)
    assert not _calls(log, SALES_REPORT_TOOL), log


def test_r9_guard_a_top_selling_reply_with_a_count_keeps_the_ranking(console, monkeypatch) -> None:
    _total(console, monkeypatch)
    text, log = _turn(console, monkeypatch, _top_selling(top_n=5), "top 5")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == "product" and ran[0]["top_n"] == 5, (text, log)
    assert not _calls(log, SALES_REPORT_TOOL), log


@pytest.mark.parametrize("fresh, expected", [
    # A new subject re-types the ask whole (`restates_the_ask`): no axis and nothing to total is the catalogue line.
    ({"state_changes": [{"op": "new_subject", "axis": None, "position": None}]}, "I can rank sales by"),
], ids=["new_subject"])
def test_r9_guard_a_new_subject_stays_a_fresh_ask(console, monkeypatch, fresh, expected) -> None:
    _total(console, monkeypatch)
    text, log = _turn(console, monkeypatch, _axisless(**fresh), "qty, delivered")
    assert not _calls(log, SALES_REPORT_TOOL) and _ran(log) == [] and expected in text, (text, log)


def test_r9_guard_an_order_list_window_still_asks_the_period(console, monkeypatch) -> None:
    order_list = _v63(order_status=None, document=["DO"], entities=[_e(PRODUCT_CODE, "product")],
                      entity_op="replace_combine", domain_in_message=True, **YEAR_2026)
    text, log = _turn(console, monkeypatch, order_list, f"delivery orders for {PRODUCT_CODE} in 2026")
    assert not _calls(log, SALES_REPORT_TOOL) and _ran(log) == [], ("setup", text, log)
    text, log = _turn(console, monkeypatch, _axisless(), "qty, delivered")
    assert not _calls(log, SALES_REPORT_TOOL) and _ran(log) == [] and PERIOD_Q in text, (text, log)


def test_r9_guard_a_held_report_ask_frame_keeps_its_own_rules(console, monkeypatch) -> None:
    total = _v63(order_status="sales_ranking", ranking_refine=False, entities=[_e(PRODUCT_CODE, "product")],
                 entity_op="replace_combine", measure="qty", basis="delivered", domain_in_message=True, **YEAR_2026)
    text, log = _turn(console, monkeypatch, total, f"total qty of {PRODUCT_CODE} in 2026 delivered")
    assert len(_ran(log)) == 1, ("setup", text, log)
    text, log = _turn(console, monkeypatch, _axisless(basis="ordered"), "qty, ordered")
    ran = _ran(log)  # the refine re-runs the held frame with the basis it changed
    assert len(ran) == 1 and not ran[0].get("group_by") and ran[0]["basis"] == "ordered", (text, log)
    assert ran[0]["product_code"] == PRODUCT_CODE and not _calls(log, SALES_REPORT_TOOL), (text, log)


# ------------------------------------------------ review round 1


@pytest.mark.parametrize("qf, body", [
    (dict(top_n=5, ranking_refine=False), "top 5"),
    (dict(top_n=5, ranking_refine=False, measure="qty", rank_by="quantity", basis="ordered"), "top 5 qty ordered"),
], ids=["top_5", "top_5_qty_ordered"])
def test_r9_review_a_typed_count_with_no_axis_keeps_today_s_reply(console, monkeypatch, qf, body) -> None:
    """AC-OR9: a typed count keeps the ranking. With no axis that is today's catalogue line, never a total."""
    from app.services.chatbot.lanes.business.report_ask import CATALOGUE_LINE

    _total(console, monkeypatch)
    text, log = _turn(console, monkeypatch, _v63(**qf), body)
    assert text == CATALOGUE_LINE, (text, log)
    assert _ran(log) == [] and not _calls(log, SALES_REPORT_TOOL), log


def test_r9_review_after_a_sales_analysis_total_the_reply_is_not_a_sales_report(console, monkeypatch) -> None:
    # SALES-TOTAL-ASK: the total names its basis, or it is asked one first (`test_sales_total_ask`).
    analysis = _v63(order_status="sales_analysis", entities=[], entity_op="replace_combine", domain_in_message=True,
                    sales_basis="invoiced", **YEAR_2026)
    text, log = _turn(console, monkeypatch, analysis, "total invoiced sales in 2026")
    assert not _calls(log, SALES_REPORT_TOOL) and _ran(log) == [], ("setup", text, log)
    from app.services.chatbot.lanes.business.report_ask import CATALOGUE_LINE

    text, log = _turn(console, monkeypatch, _axisless(), "qty, delivered")
    # REPORT-UNIFY: the analysis total is a held report-ask total: the reply re-runs it (period kept, no product).
    ran = _ran(log)
    assert len(ran) == 1 and not ran[0].get("group_by") and "product_code" not in ran[0], (text, log)
    assert ran[0]["date_from"] == "2026-01-01", ran
