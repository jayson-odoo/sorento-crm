"""REPORT-SMART-L S3 review round: pins for the reviewer's findings on dd535e7c81.

1. The field-word drop (`report_ask.drop_field_words`) runs AFTER `names_its_own_ask`, which
   reads a stray year / channel entity as "named", so the open ranking slot was dropped.
3. `lane_parse_output` reads the delivery status from `order_status` alone (mutation guard).
4. The year rule needs BOTH period ends in the year (mutation guard).
Fake names and codes only.
"""
from __future__ import annotations

import json
from typing import Any

from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import _e, _reply, console  # noqa: F401 - fixtures + helpers
from tests.chatbot.test_report_smart_s3_period import FAMILY, _first, _seed_family
from tests.chatbot.test_report_smart_s3_year import (
    DECOYS,
    _resolver_raws,
    _seed,
    _verdict,
    _year_entity,
)
from tests.chatbot.test_report_smart_step7 import KEEP, THIS_YEAR, _state_on


def _stated_reply(*entities: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    """'2026, top 5, by qty, delivered' as the parser reads it with the ranking question open."""
    base: dict[str, Any] = dict(
        domain_hint="order", intent_hint="check_order", order_status="sales_ranking", entities=list(entities),
        top_n=5, measure="qty", basis="delivered", state_changes=list(KEEP),
        open_question_answer={"mode": "fill", "picked": [], "items": [], "qty_for_all": None}, **THIS_YEAR,
    )
    base.update(overrides)
    return _reply(**base)


def _ask_first(console) -> None:
    _state_on(console)
    _seed_family(console)
    text, calls = console.say(
        _first(date_filter_start=None, date_filter_end=None), "top salesppl for cb6635")
    assert calls == [], ("setup: the first ask must ask", text, calls)


def _family_only(console_ids: dict[str, str] | None, args: dict[str, Any]) -> None:
    assert args.get("group_by") == "sales_agent" and args.get("top_n") == 5, args
    assert str(args.get("product_code", "")).upper().startswith("CB6635"), args


def test_review_1_control_the_answer_reply_with_no_stray_entity_runs_the_ranking(console) -> None:
    _ask_first(console)
    text, calls = console.say(_stated_reply(), "2026, top 5, by qty, delivered")
    assert len(calls) == 1, (text, calls)
    _family_only(None, calls[0])
    assert calls[0]["date_from"] == "2026-01-01" and calls[0]["date_to"] == "2026-12-31", calls[0]


def test_review_1a_a_stray_year_entity_in_the_answer_does_not_drop_the_open_slot(console) -> None:
    _state_on(console)
    ids = _seed(console, *FAMILY, *DECOYS)
    text, calls = console.say(
        _first(date_filter_start=None, date_filter_end=None), "top salesppl for cb6635")
    assert calls == [], ("setup: the first ask must ask", text, calls)
    text, calls = console.say(_stated_reply(_year_entity(DECOYS[0])), "2026, top 5, by qty, delivered")
    assert len(calls) == 1, (text, calls)  # today: "I can rank sales by customer, product, ..." and nothing runs
    args = calls[0]
    _family_only(None, args)
    assert args["date_from"] == "2026-01-01" and args["date_to"] == "2026-12-31", args
    assert not any(ids[d] in json.dumps(args) or d in json.dumps(args) for d in DECOYS), args


def test_review_1b_a_stray_channel_entity_in_the_answer_does_not_drop_the_open_slot(console) -> None:
    _ask_first(console)
    text, calls = console.say(
        _stated_reply(_e("Project", "brand"), sales_channel="project"), "project, 2026, top 5, by qty, delivered")
    assert len(calls) == 1, (text, calls)  # today: an ungrouped channel total, cb6635 lost
    args = calls[0]
    _family_only(None, args)
    assert "channel" not in args, args  # AC-HT8-16: an answer's channel is ignored


def test_review_4_the_year_rule_needs_both_period_ends_in_the_year(console) -> None:
    _state_on(console)
    _seed(console, *FAMILY, *DECOYS)
    seen = _resolver_raws(console)
    span = {"date_filter_start": "2025-12-01", "date_filter_end": "2026-01-31"}
    for year in ("2025", "2026"):
        seen.clear()
        entity = {**_e(year, "product"), "canonical_code": None}
        console.say(_verdict(entity, _e("cb6635", "product"), **span), f"Top 5 salesppl Dec to Jan for {year} cb6635")
        assert any(year in raws for raws in seen), (year, seen)  # kept: one end is outside the year


def test_review_3_lane_parse_output_reads_the_delivery_status_from_order_status_alone() -> None:
    from app.services.chatbot.turn_runtime import lane_parse_output

    verdict = _parser_output(
        domain_hint="order", intent_hint="check_order", status=None, order_status="outstanding", document=["DO"])
    out = lane_parse_output(verdict, focus=None)
    assert out["order_status"] == "do_outstanding", out["order_status"]
