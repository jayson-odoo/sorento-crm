"""REPORT-SMART-L round S2 (owner console turns 22 Oct): red tests for items D, E, B, C.

Plan documentation/plans/chatbot/PLAN-report-smart-owner-1022.md, UAC AC-D1, AC-E1, AC-B1, AC-B2,
AC-C1. Full console turns with the State path on (the live build), parse shapes as the live
parser emits them. Fake names and codes only. Items A (channel word) and F (flyer) are paused
by the owner and live in `test_report_smart_owner_1022_af.py` when written.
"""
from __future__ import annotations

from typing import Any

import pytest

from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import (  # noqa: F401 - fixtures + helpers
    DEFAULT_COMPANY_ID,
    PERIOD_Q,
    PRODUCT_CODE,
    _e,
    _rank,
    _refine,
    console,
)
from tests.chatbot import test_report_ask_lane as lane_tests
from tests.chatbot.test_report_drilldown_lane import _body as _drill_body
from tests.chatbot.test_report_smart_step7 import KEEP, THIS_YEAR, _state_on

NO_DATES = {"date_filter_start": None, "date_filter_end": None}
SET_PRODUCT = [{"op": "set", "axis": "product", "position": None}]
SET_CUSTOMER = [{"op": "set", "axis": "customer", "position": None}]


@pytest.fixture(autouse=True)
def _rows_with_keys(monkeypatch):
    """Printed rows carry their keys, so a drill has something to scope to."""
    monkeypatch.setattr(lane_tests, "_fake_body", _drill_body)


def _seed(console, *, codes=(), customers=(), warehouse_name=None) -> dict[str, str]:
    from tests._mc_lookup_seed import customer, product, warehouse

    db = console.session_factory()
    try:
        ids: dict[str, str] = {}
        for code in codes:
            ids[code] = str(product(db, company_id=DEFAULT_COMPANY_ID, code=code).id)
        for name in customers:
            customer(db, company_id=DEFAULT_COMPANY_ID, name=name)
        if warehouse_name:
            w = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=warehouse_name.upper())
            w.warehouse_name = warehouse_name
        db.commit()
        return ids
    finally:
        db.close()


# ---------------------------------------------------------------- D (AC-D1)

MIXED = ("XA1001-ZQ6635", "ZB2002-ZQ6635", "QC3003-ZQ6635")
D_BODIES = [
    "top 5 salesppl for zq6635",
    "销售员排名前5 zq6635",
    "5 jurujual teratas untuk zq6635",
    "top 5 sales 人 for ZQ6635 lah",
]


@pytest.mark.parametrize("body", D_BODIES)
def test_d_a_word_that_fanned_out_to_unrelated_codes_never_names_one_of_them(console, body) -> None:
    ran = _state_on(console)
    ids = _seed(console, codes=MIXED)
    text, calls = console.say(
        _rank(_e("ZQ6635", "product"), top_n=5, measure="qty", basis="delivered", state_changes=SET_PRODUCT, **THIS_YEAR),
        body,
    )
    assert ran, "harness: the State path never ran"
    if calls:
        args = calls[0]
        assert set(args.get("product_ids") or []) == set(ids.values()), args
        assert "product_code" not in args, args
    else:
        assert "?" in text, text
        assert sum(code in text for code in MIXED) != 1, text


def test_d_near_miss_one_family_sharing_a_prefix_still_sends_that_prefix(console) -> None:
    ran = _state_on(console)
    _seed(console, codes=("ZYQ7001-A", "ZYQ7001-B"))
    text, calls = console.say(
        _rank(_e("ZYQ7001", "product"), top_n=5, measure="qty", basis="delivered", state_changes=SET_PRODUCT, **THIS_YEAR),
        "top 5 salesppl for zyq7001",
    )
    assert ran, "harness: the State path never ran"
    (args,) = calls
    assert str(args.get("product_code") or "").startswith("ZYQ7001"), args


# ---------------------------------------------------------------- E (AC-E1)

E_BODIES = ["for product SRTWT7408", "产品 SRTWT7408 呢", "untuk produk SRTWT7408", "how about SRTWT7408 lah"]


def _held_ranking(console, *entities) -> None:
    text, calls = console.say(
        _rank(*entities, top_n=3, measure="qty", basis="delivered", state_changes=list(KEEP), **THIS_YEAR),
        "top 3 salesppl this year",
    )
    assert len(calls) == 1, ("setup: the ranking did not run", text, calls)


def _e_shapes() -> dict[str, Any]:
    prod = [_e(PRODUCT_CODE, "product")]
    return {
        "refine_only_changed_keys": lambda: _refine(entities=list(prod), state_changes=SET_PRODUCT),
        "refine_live_repeats_axis_count_measure": lambda: _rank(
            *prod, group_by="sales_agent", top_n=3, measure="qty", basis="delivered", ranking_refine=True,
            state_changes=SET_PRODUCT, **NO_DATES),
    }


@pytest.mark.parametrize("shape", list(_e_shapes()))
@pytest.mark.parametrize("body", E_BODIES)
def test_e_a_product_named_on_a_refine_reruns_the_held_ranking_with_it(console, body, shape) -> None:
    ran = _state_on(console)
    _held_ranking(console)
    text, calls = console.say(_e_shapes()[shape](), body)
    assert ran, "harness: the State path never ran"
    assert len(calls) == 1, ("never product cards or a question", text, calls)
    args = calls[0]
    assert args.get("product_code") == PRODUCT_CODE or args.get("product_ids") == [console.ids["product"]], args
    assert args["group_by"] == "sales_agent" and args["top_n"] == 3, args
    assert args["measure"] == "qty" and args["basis"] == "delivered", args
    assert args["date_from"] == "2026-01-01" and args["date_to"] == "2026-12-31", args


@pytest.mark.parametrize("body", ["ordered", "按下单的", "ikut order", "ordered pls"])
def test_e_near_miss_a_refine_with_no_product_keeps_the_held_product(console, body) -> None:
    ran = _state_on(console)
    _held_ranking(console, _e(PRODUCT_CODE, "product"))
    text, calls = console.say(_refine(basis="ordered", state_changes=[{"op": "set", "axis": "status", "position": None}]), body)
    assert ran, "harness: the State path never ran"
    (args,) = calls
    assert args["basis"] == "ordered" and str(args.get("product_code")) == PRODUCT_CODE, args


# ---------------------------------------------------------------- B (AC-B1, AC-B2)

PROJECT_CUSTOMERS = ("PROJECT ALPHA SDN BHD", "PROJECT BETA SDN BHD", "PROJECT GAMMA SDN BHD")
B_BODIES = [
    "Top 10 salesppl for srt102-rg project sales this year",
    "前10 销售员 srt102-rg project sales 今年",
    "10 jurujual teratas srt102-rg jualan project tahun ini",
    "top 10 sales agent srt102-rg project this year lah",
]


def _full_project_ranking() -> dict[str, Any]:
    return _rank(_e("SRT102-RG", "product"), sales_channel="project", top_n=10, measure="qty", basis="delivered",
                 ranking_refine=False, state_changes=SET_PRODUCT, **THIS_YEAR)


@pytest.mark.parametrize("body", B_BODIES)
def test_b1_a_pick_that_binds_no_row_is_not_held_and_the_next_ask_runs(console, body) -> None:
    ran = _state_on(console)
    _seed(console, codes=("SRT102-RG",), customers=PROJECT_CUSTOMERS, warehouse_name="Project")
    _held_ranking(console)
    text, calls = console.say(
        _refine(entities=[_e("Project", "customer")], state_changes=SET_CUSTOMER), "Project",
    )
    assert "Which one" in text, ("setup: the customer / warehouse pick was not armed", text)
    console.say(
        _parser_output(domain_hint="order", intent_hint="check_order", order_status="sales_ranking", group_by="customer",
                       entities=[], answers_open_question={"resolved": True, "picks": [1], "answer": "1"},
                       state_changes=[{"op": "answer", "axis": None, "position": None}]),
        "1",
    )
    text, calls = console.say(_full_project_ranking(), body)
    assert ran, "harness: the State path never ran"
    assert len(calls) == 1, ("a carried 'Project' narrowed a fully parsed ranking", text, calls)
    assert not calls[0].get("customer_ids") and "PROJECT ALPHA" not in text, (text, calls)


@pytest.mark.parametrize("body", B_BODIES)
def test_b2_a_carried_customer_is_not_renarrowed_before_a_sales_ranking(console, body) -> None:
    ran = _state_on(console)
    _seed(console, codes=("SRT102-RG",), customers=PROJECT_CUSTOMERS)
    carried = dict(_e("Project", "customer"), current_message=False)
    qf = _rank(carried, _e("SRT102-RG", "product"), sales_channel="project", top_n=10, measure="qty",
               basis="delivered", ranking_refine=False, state_changes=SET_PRODUCT, **THIS_YEAR)
    text, calls = console.say(qf, body)
    assert ran, "harness: the State path never ran"
    assert len(calls) == 1 and not calls[0].get("customer_ids"), (text, calls)


@pytest.mark.parametrize("body", ["top 10 salesppl for Project customer this year", "前10 销售员 Project customer 今年",
                                  "10 jurujual teratas untuk customer Project", "top 10 agents of Project customer lah"])
def test_b_near_miss_a_ranking_that_names_the_customer_this_message_still_narrows(console, body) -> None:
    ran = _state_on(console)
    _seed(console, customers=PROJECT_CUSTOMERS)
    text, calls = console.say(
        _rank(_e("Project", "customer"), top_n=10, measure="qty", basis="delivered", state_changes=SET_CUSTOMER, **THIS_YEAR),
        body,
    )
    assert ran, "harness: the State path never ran"
    assert calls == [] and "PROJECT ALPHA SDN BHD" in text, (text, calls)


# ---------------------------------------------------------------- C (AC-C1)

SCOPE_Q = "of the 3 sales agents above, or across all customers?"
FAILED_ASKS = {
    "unknown_axis": lambda: _rank(group_by="weather", top_n=5, measure="qty", basis="delivered",
                                  state_changes=list(KEEP), **THIS_YEAR),
    "unknown_brand": lambda: _rank(_e("Zzzbrand", "brand"), top_n=5, measure="qty", basis="delivered",
                                   state_changes=list(KEEP), **THIS_YEAR),
    "unknown_agent": lambda: _rank(_e("ZZTNOBODY", "sales_agent"), group_by="product", top_n=5, measure="qty",
                                   basis="delivered", state_changes=list(KEEP), **THIS_YEAR),
}


def _customers_ask(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(group_by="customer", top_n=10, measure="qty", basis="delivered", ranking_refine=False,
                                ranking_drill=None, state_changes=list(KEEP), **THIS_YEAR)
    base.update(over)
    return _rank(**base)


@pytest.mark.parametrize("failed", list(FAILED_ASKS))
@pytest.mark.parametrize("body", ["top 10 customers this year by qty", "前10 客户 今年 数量", "10 pelanggan teratas tahun ini",
                                  "top 10 customer lah"])
def test_c_a_new_axis_after_a_failed_ask_is_its_own_ask_never_the_scope_question(console, body, failed) -> None:
    ran = _state_on(console)
    _held_ranking(console)
    text, calls = console.say(FAILED_ASKS[failed](), "top 5 for zzt")
    assert calls == [], ("setup: the failing ask ran", text, calls)
    text, calls = console.say(_customers_ask(), body)
    assert ran, "harness: the State path never ran"
    assert "across all customers" not in text, text
    assert calls and calls[0]["group_by"] == "customer" and not calls[0].get("customer_agent_ids"), (text, calls)


def test_c_near_miss_the_parsers_unsure_runs_across_all_not_the_scope_question(console) -> None:
    # Owner ruling B (23 Oct, reverses the old unsure scope question): unsure runs across all.
    ran = _state_on(console)
    _held_ranking(console)
    console.say(FAILED_ASKS["unknown_axis"](), "top 5 for zzt")
    text, calls = console.say(_customers_ask(ranking_drill="unsure"), "top 10 customers")
    assert ran, "harness: the State path never ran"
    assert SCOPE_Q not in text, (text, calls)
    assert calls and calls[0]["group_by"] == "customer" and not calls[0].get("customer_agent_ids"), (text, calls)
