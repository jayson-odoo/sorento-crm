"""REPORT-SMART-L one ranking, round R0 (AC-OR0): a widened axis is dropped from the held ranking.

The refine / across-all hold keeps product, channel, period, count, measure and basis, but never
read the parser's `broaden_axis` / `broaden_to` (template R-P3-09): widening one axis keeps the
rest, and `broaden_to` "all" drops that axis. Fake names and codes only.
"""
from __future__ import annotations

from typing import Any

import pytest

from tests.chatbot import test_report_ask_lane as lane_tests
from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import PRODUCT_CODE, _e, _rank, _refine, console  # noqa: F401
from tests.chatbot.test_report_drilldown_lane import _body, _drill
from tests.chatbot.test_report_smart_step7 import KEEP, THIS_YEAR, _state_on


@pytest.fixture(autouse=True)
def _route_body(monkeypatch):
    monkeypatch.setattr(lane_tests, "_fake_body", _body)


def _ranking(console) -> None:
    """Top 5 sales agents, product, dealer, 2026, qty, delivered: the ranking on screen."""
    text, calls = console.say(
        _rank(_e(PRODUCT_CODE, "product"), top_n=5, measure="qty", basis="delivered", sales_channel="dealer",
              state_changes=list(KEEP), **THIS_YEAR),
        f"top 5 salesppl in 2026 for {PRODUCT_CODE}, dealer sales",
    )
    assert len(calls) == 1, ("setup: the ranking did not run", text, calls)


def _widen(shape: str, axis: str | None, to: str | None) -> dict[str, Any]:
    if shape == "refine":
        return _refine(group_by="sales_agent", top_n=5, measure="qty", basis="delivered", ranking_refine=True,
                       broaden_axis=axis, broaden_to=to, state_changes=list(KEEP))
    return _drill(group_by="customer", top_n=None, measure=None, basis=None, ranking_drill=None,
                  broaden_axis=axis, broaden_to=to, state_changes=list(KEEP))


def _held(args: dict[str, Any], *, drop: str | None) -> None:
    """Everything on screen is held except the widened axis."""
    assert (args.get("channel") == "dealer") is (drop != "channel"), args
    assert (args.get("product_code") == PRODUCT_CODE) is (drop != "product"), args
    dated = args.get("date_from") == "2026-01-01" and args.get("date_to") == "2026-12-31"
    assert dated is (drop != "date"), args
    if drop == "date":
        assert not args.get("date_from") and not args.get("date_to"), args
    assert args.get("measure") == "qty" and args.get("basis") == "delivered" and args.get("top_n") == 5, args


@pytest.mark.parametrize("shape", ["refine", "new_axis"])
@pytest.mark.parametrize("axis", ["channel", "product", "date"])
def test_or0_a_widened_axis_is_dropped_and_the_rest_is_held(console, shape, axis) -> None:
    _state_on(console)
    _ranking(console)
    text, calls = console.say(_widen(shape, axis, "all"), f"all {axis}s")
    assert len(calls) == 1, (text, calls)
    _held(calls[0], drop=axis)


@pytest.mark.parametrize("shape", ["refine", "new_axis"])
def test_or0_near_miss_no_broadening_holds_everything_as_today(console, shape) -> None:
    _state_on(console)
    _ranking(console)
    text, calls = console.say(_widen(shape, None, None), "same again")
    assert len(calls) == 1, (text, calls)
    _held(calls[0], drop=None)
