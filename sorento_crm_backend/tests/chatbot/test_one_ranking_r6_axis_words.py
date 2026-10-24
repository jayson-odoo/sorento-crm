"""REPORT-SMART-L R6 (AC-OR6, owner ruling A): the parser reports `axis_words`, the current message's own words
naming what is ranked or grouped, or null. A verdict whose `axis_words` key is PRESENT and null names no axis, so
its group_by is not typed (a fresh ask is a TOTAL, a refine changes no axis); a verdict WITHOUT the key (production
prompt v92 and older) behaves exactly as before. Real engine seam. Fake codes only."""
from __future__ import annotations

from typing import Any

import pytest

from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import (  # noqa: F401 - fixtures + helpers
    PRODUCT_CODE,
    TOOL,
    _e,
    _say_all,
    console,
)
from tests.chatbot.test_report_smart_step7 import KEEP, _state_on

YEAR_2026 = {"date_filter_start": "2026-01-01", "date_filter_end": "2026-12-31"}
YEAR_2025 = {"date_filter_start": "2025-01-01", "date_filter_end": "2025-12-31"}
ANSWER = [{"op": "answer", "axis": None, "position": None}]
SET = [{"op": "set", "axis": None, "position": None}]


def _ran(log):
    return [a for n, a in log if n == TOOL]


def _fresh(axis_words: Any = "ABSENT", **over: Any) -> dict[str, Any]:
    """'Top sales for <product> in 2026': the parser guessed an axis, basis left null."""
    base: dict[str, Any] = dict(
        domain_hint="order", intent_hint="check_order", order_status="sales_ranking", ranking_refine=False,
        group_by="product", top_n=None, measure=None, basis=None, rank_direction="top",
        entities=[_e(PRODUCT_CODE, "product")], domain_in_message=True, state_changes=list(KEEP), **YEAR_2026)
    base.update(over)
    if axis_words != "ABSENT":
        base["axis_words"] = axis_words
    return _parser_output(**base)


def _refine(axis_words: Any = "ABSENT", **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(
        domain_hint="order", intent_hint="check_order", order_status="sales_ranking", ranking_refine=True,
        group_by=None, top_n=None, measure=None, basis=None, entities=[], domain_in_message=False,
        state_changes=list(SET), date_filter_start=None, date_filter_end=None)
    base.update(over)
    if axis_words != "ABSENT":
        base["axis_words"] = axis_words
    return _parser_output(**base)


# 1. schema ------------------------------------------------------------------------------------------------------


def test_r6_1_the_parser_schema_declares_axis_words_as_string_or_null() -> None:
    from app.services.chatbot.head.parser import (
        DECLARED_KEYS,
        PARSE_OUTPUT_JSON_SCHEMA,
        PARSE_OUTPUT_JSON_SCHEMA_WITH_STATE,
        closed_lists_schema,
    )

    for schema in (PARSE_OUTPUT_JSON_SCHEMA, PARSE_OUTPUT_JSON_SCHEMA_WITH_STATE, closed_lists_schema(["x"])):
        assert schema["properties"]["axis_words"] == {"type": ["string", "null"]}, schema["properties"].get("axis_words")
        assert "axis_words" in schema["required"]
    assert "axis_words" in DECLARED_KEYS


# 2. ruling A, fresh state ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("guessed", ["product", "sales_agent"])
def test_r6_2_an_axis_less_top_sales_ask_is_a_total_whatever_axis_the_model_guessed(console, monkeypatch, guessed) -> None:
    _state_on(console)
    text, log = _say_all(console, monkeypatch, _fresh(None, group_by=guessed), "Top sales for CB6635 in 2026")
    assert _ran(log) == [], (text, log)
    assert "How many" not in text and "top 5" not in text.lower() and "by quantity" not in text.lower(), text
    low = text.lower()
    assert "delivered" in low and "ordered" in low, text  # the basis is the one question
    assert "which period" not in low and "by customer" not in low and "which axis" not in low, text
    text, log = _say_all(
        console, monkeypatch,
        _fresh(None, group_by=guessed, basis="delivered", entities=[], domain_in_message=False, state_changes=ANSWER,
               date_filter_start=None, date_filter_end=None),
        "delivered")
    ran = _ran(log)
    assert len(ran) == 1, (text, log)
    assert not ran[0].get("group_by"), ran
    assert ran[0]["product_code"] == PRODUCT_CODE, ran
    assert ran[0]["date_from"] == "2026-01-01" and ran[0]["date_to"] == "2026-12-31", ran


# 3. axis kept ---------------------------------------------------------------------------------------------------


def test_r6_3_a_named_axis_keeps_its_group_by(console, monkeypatch) -> None:
    _state_on(console)
    qf = _fresh("salesppl", group_by="sales_agent", top_n=5, measure="qty", basis="delivered")
    text, log = _say_all(console, monkeypatch, qf, "Top 5 salesppl in 2026 for CB6635")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == "sales_agent" and ran[0]["top_n"] == 5, (text, log)


def test_r6_3b_a_ranked_noun_keeps_its_axis(console, monkeypatch) -> None:
    _state_on(console)
    qf = _fresh("item", entities=[], domain_in_message=True, group_by="product", top_n=30, measure="qty",
                basis="delivered")
    text, log = _say_all(console, monkeypatch, qf, "Top 30 selling item this year")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == "product" and ran[0]["top_n"] == 30, (text, log)


# 4. key absent: today's behaviour --------------------------------------------------------------------------------


@pytest.mark.parametrize("guessed", ["product", "sales_agent"])
def test_r6_4_guard_a_verdict_without_the_key_keeps_its_guessed_axis(console, monkeypatch, guessed) -> None:
    _state_on(console)
    text, log = _say_all(console, monkeypatch, _fresh(group_by=guessed), "Top sales for CB6635 in 2026")
    assert "axis_words" not in _fresh(group_by=guessed)
    assert _ran(log) == [], (text, log)
    assert "How many" in text, text  # the guessed axis is a ranking, so the count is owed as today
    text, log = _say_all(
        console, monkeypatch,
        _fresh(group_by=guessed, basis="delivered", measure="qty", top_n=5, entities=[], domain_in_message=False, state_changes=ANSWER,
               date_filter_start=None, date_filter_end=None), "top 5 delivered")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == guessed and ran[0]["top_n"] == 5, (text, log)


# 5. refine --------------------------------------------------------------------------------------------------------


def _held_agent_ranking(console, monkeypatch) -> None:
    _state_on(console)
    qf = _parser_output(
        domain_hint="order", intent_hint="check_order", order_status="sales_ranking", ranking_refine=False,
        group_by="sales_agent", top_n=5, measure="qty", basis="delivered", entities=[], domain_in_message=True,
        state_changes=list(KEEP), **YEAR_2026)
    text, log = _say_all(console, monkeypatch, qf, "top 5 salesppl in 2026 delivered qty")
    assert len(_ran(log)) == 1 and _ran(log)[0]["group_by"] == "sales_agent", ("setup", text, log)


def test_r6_5a_a_refine_with_null_axis_words_changes_no_axis(console, monkeypatch) -> None:
    _held_agent_ranking(console, monkeypatch)
    qf = _refine(None, group_by="customer", **YEAR_2025)
    text, log = _say_all(console, monkeypatch, qf, "only 2025")
    ran = _ran(log)
    assert len(ran) == 1, (text, log)
    assert ran[0]["group_by"] == "sales_agent", ran
    assert ran[0]["date_from"] == "2025-01-01" and ran[0]["date_to"] == "2025-12-31", ran


def test_r6_5b_a_refine_naming_its_axis_changes_the_axis(console, monkeypatch) -> None:
    _held_agent_ranking(console, monkeypatch)
    qf = _refine("by customer", group_by="customer")
    text, log = _say_all(console, monkeypatch, qf, "by customer")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == "customer", (text, log)


# 6. slot answer ---------------------------------------------------------------------------------------------------


def _open_how_many(console, monkeypatch) -> None:
    _state_on(console)
    first = _parser_output(
        domain_hint="order", intent_hint="check_order", order_status="sales_ranking", ranking_refine=False,
        group_by=None, top_n=None, measure="qty", basis="delivered", entities=[_e(PRODUCT_CODE, "product")],
        domain_in_message=True, state_changes=list(KEEP), **YEAR_2026)
    _say_all(console, monkeypatch, first, f"total qty of {PRODUCT_CODE} in 2026 delivered")
    text, log = _say_all(console, monkeypatch, _refine("by salesppl", group_by="sales_agent"), "by salesppl")
    assert _ran(log) == [] and "How many?" in text, ("setup", text, log)


def test_r6_6a_under_an_open_how_many_a_named_new_axis_still_swaps(console, monkeypatch) -> None:
    _open_how_many(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _refine("by customer", group_by="customer"), "by customer")
    assert _ran(log) == [] and "How many?" in text, (text, log)
    text, log = _say_all(console, monkeypatch, _refine(top_n=5, ranking_refine=False, state_changes=ANSWER), "top 5")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == "customer" and ran[0]["top_n"] == 5, (text, log)


def test_r6_6b_under_an_open_how_many_a_guessed_axis_with_null_axis_words_does_not_swap(console, monkeypatch) -> None:
    _open_how_many(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _refine(None, group_by="customer"), "ok")
    assert _ran(log) == [], (text, log)
    text, log = _say_all(console, monkeypatch, _refine(None, top_n=5, ranking_refine=False, state_changes=ANSWER), "top 5")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == "sales_agent" and ran[0]["top_n"] == 5, (text, log)
