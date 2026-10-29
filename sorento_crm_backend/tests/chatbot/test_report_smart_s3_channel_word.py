"""REPORT-SMART-L round S3, AC-S3-2: a channel word of any hint is the channel.

Under a held ranking, a verdict with `sales_channel` project and an entity 'Project' hinted
brand, category, customer or sales_agent re-runs with Channel: Project; never "I don't know
'Project' as a ...", never a pick list. An entity whose raw is not the channel value still
resolves; with `sales_channel` null the entity is untouched. Fake names and codes only.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import (  # noqa: F401 - fixtures + helpers
    _e,
    _rank,
    _refine,
    console,
)
from tests.chatbot.test_report_smart_step7 import KEEP, NEW_SUBJECT, THIS_YEAR, _state_on

HINTS = ["brand", "category", "customer", "sales_agent"]
CODE = "CB6635"


def _seed(console, *codes: str) -> None:
    from tests._mc_lookup_seed import product

    db = console.session_factory()
    try:
        for code in codes:
            product(db, company_id=DEFAULT_COMPANY_ID, code=code)
        db.commit()
    finally:
        db.close()


def _hold_ranking(console) -> None:
    """'top 5 sales agents for CB6635, dealer, 2026' has run: the ranking is on screen."""
    _state_on(console)
    _seed(console, f"{CODE}-NL", f"{CODE}-PP")
    text, calls = console.say(
        _rank(_e(CODE, "product"), top_n=5, measure="qty", basis="delivered", sales_channel="dealer",
              state_changes=list(KEEP), **THIS_YEAR),
        "top 5 salesppl in 2026 for cb6635, dealer sales",
    )
    assert len(calls) == 1 and calls[0]["channel"] == "dealer", ("setup: the ranking did not run", text, calls)


def _no_refusal(console, text: str) -> None:
    assert "I don't know" not in text and "matches several" not in text, text
    assert "Which one" not in text and "(customer)" not in text and "(warehouse)" not in text, text
    assert "kind_pick" not in json.dumps(console.session_vars, default=str), console.session_vars


@pytest.mark.parametrize("hint", HINTS)
def test_s3_2_a_channel_word_of_any_hint_under_a_held_ranking_reruns_with_the_channel(console, hint) -> None:
    _hold_ranking(console)
    text, calls = console.say(
        _refine(sales_channel="project", ranking_refine=True, entities=[_e("Project", hint)],
                state_changes=[{"op": "set", "axis": "channel", "position": None}]),
        "Project is channel",
    )
    assert len(calls) == 1, (text, calls)
    args = calls[0]
    assert args["channel"] == "project", args
    assert args["group_by"] == "sales_agent" and args["top_n"] == 5, args  # the held ranking, refined
    assert not {"brand_ids", "category_ids", "customer_ids", "sales_agent_ids"} & set(args), args
    _no_refusal(console, text)


@pytest.mark.parametrize("hint", HINTS)
def test_s3_2_a_fresh_ask_with_a_channel_word_of_any_hint_runs_with_the_channel(console, hint) -> None:
    _state_on(console)
    _seed(console, "SRT102-RG")
    text, calls = console.say(
        _rank(_e("SRT102-RG", "product"), _e("Project", hint), top_n=10, measure="qty", basis="delivered",
              sales_channel="project", state_changes=list(KEEP), **THIS_YEAR),
        "Project sales top 10 srt102-rg",
    )
    assert len(calls) == 1, (text, calls)
    args = calls[0]
    assert args["channel"] == "project" and args["top_n"] == 10, args
    assert not {"brand_ids", "category_ids", "customer_ids", "sales_agent_ids"} & set(args), args
    _no_refusal(console, text)


def test_s3_2_near_miss_an_entity_that_is_not_the_channel_value_still_reaches_the_customer_path(console) -> None:
    from tests._mc_lookup_seed import customer

    _state_on(console)
    db = console.session_factory()
    try:
        cid = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZ PROJECT HARDWARE SDN BHD").id
        db.commit()
    finally:
        db.close()
    text, calls = console.say(
        _rank(_e("ZZ Project Hardware", "customer"), group_by="product", top_n=5, measure="qty", basis="delivered",
              sales_channel="project", state_changes=list(KEEP), **THIS_YEAR),
        "top 5 products of ZZ Project Hardware, project channel",
    )
    assert len(calls) == 1, (text, calls)
    assert calls[0]["channel"] == "project" and calls[0]["customer_ids"] == [str(cid)], calls


def test_s3_2_near_miss_with_no_sales_channel_the_project_brand_entity_is_untouched(console) -> None:
    _state_on(console)
    text, calls = console.say(
        _rank(_e("Project", "brand"), top_n=5, measure="qty", basis="delivered", sales_channel=None,
              state_changes=list(KEEP), **THIS_YEAR),
        "top 5 salesppl for project brand",
    )
    assert calls == [] and "I don't know 'Project' as a brand." in text, (text, calls)
