"""REPORT-CHANNEL-FILTER (owner ruling 24 Oct ~19:50; PLAN-report-channel-filter-1024.md): "<channel> sales only"
after a held ranking FILTERS that ranking to the channel and keeps its axis, period, product and measure; never a new
channel axis across all. EVAL-BENCH gate 4 rows 15 and 16 (v63, turn 054cc123). Real engine seam, the v63 shapes
(no State block, `state_changes` null). The route body is stubbed the way the route answers (rows with their keys,
the channel echoed as a filter). Fake codes."""
from __future__ import annotations

from typing import Any

import pytest

from tests.chatbot import test_report_ask_lane as lane_tests
from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import PRODUCT_CODE, TOOL, _e, _say_all, console  # noqa: F401

YEAR_2026 = {"date_filter_start": "2026-01-01", "date_filter_end": "2026-12-31"}
OTHER_CODE = "ZZTCF102-RG"
CHANNEL_LABELS = {"dealer": "Dealer", "project": "Project team"}
AGENTS_TOTAL = 12


def _body(args: dict[str, Any]) -> dict[str, Any]:
    """The route's body for the lane's args: a ranking's rows carry their keys, the channel is echoed as a filter."""
    group_by = args.get("group_by")
    if group_by == "channel":
        names = [CHANNEL_LABELS[args["channel"]]] if args.get("channel") else ["Dealer", "Project team"]
    elif group_by:
        names = [f"AGENT {i}" for i in range(1, min(int(args.get("top_n") or 5), AGENTS_TOTAL) + 1)]
    else:
        names = []
    rows = [{"rank": i, "name": n, "qty": 30 - i, "amount": 1000.0 - i, "keys": [f"zzk-{i}"]} for i, n in enumerate(names, 1)]
    filters = [{"key": "channel", "label": "Channel", "values": [CHANNEL_LABELS[args["channel"]]]}] if args.get("channel") else []
    return {
        "status": "ok", "message": None, "basis": args.get("basis", "delivered"),
        "basis_label": "ordered sales" if args.get("basis") == "ordered" else "delivered sales",
        "measure": args.get("measure", "amount"), "sort": args.get("sort", "desc"), "group_by": group_by,
        "group_label": (group_by or "").replace("_", " ").title() or None,
        "date_from": args.get("date_from"), "date_to": args.get("date_to"), "filters": filters, "rows": rows,
        "more": 0, "total_count": AGENTS_TOTAL if group_by == "sales_agent" else len(rows),
        "total": {"qty": 300, "amount": 12000.0},
    }


@pytest.fixture(autouse=True)
def _route_body(monkeypatch):
    monkeypatch.setattr(lane_tests, "_fake_body", _body)


def _v63(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(
        domain_hint="order", intent_hint="check_order", order_status="sales_ranking", entities=[], entity_op="reuse",
        state_changes=None, ranking_refine=None, ranking_drill=None, group_by=None, top_n=None, measure=None,
        basis=None, rank_by=None, sales_channel=None, date_filter_start=None, date_filter_end=None,
        topic_reset=False, domain_in_message=False,
    )
    base.update(over)
    return _parser_output(**base)


def _ran(log) -> list[dict[str, Any]]:
    return [a for n, a in log if n == TOOL]


def _agent_ranking(console, monkeypatch) -> None:
    """'Top 5 salesppl in 2026 for <product>, by delivered qty': the ranking on screen (frame, shown rows)."""
    v = _v63(group_by="sales_agent", top_n=5, ranking_refine=False, measure="qty", rank_by="quantity",
             basis="delivered", entities=[_e(PRODUCT_CODE, "product")], entity_op="replace_combine",
             domain_in_message=True, **YEAR_2026)
    text, log = _say_all(console, monkeypatch, v, f"Top 5 salesppl in 2026 for {PRODUCT_CODE}, by delivered qty")
    assert len(_ran(log)) == 1 and "Top 5 of 12 sales agents" in text, ("setup", text, log)


def _dealer_only(**over: Any) -> dict[str, Any]:
    """Row 15's live parse of "Dealer sales only"."""
    return _v63(**{"group_by": "channel", "sales_channel": "dealer", "ranking_refine": True, **over})


def test_cf1_dealer_sales_only_filters_the_held_agent_ranking(console, monkeypatch) -> None:
    _agent_ranking(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _dealer_only(), "Dealer sales only")
    ran = _ran(log)
    assert len(ran) == 1, (text, log)
    args = ran[0]
    assert args["group_by"] == "sales_agent" and args["top_n"] == 5 and args["channel"] == "dealer", args
    assert args["product_code"] == PRODUCT_CODE and args["date_from"] == "2026-01-01" and args["date_to"] == "2026-12-31", args
    assert args["measure"] == "qty" and args["basis"] == "delivered", args
    assert "Top 5 of 12 sales agents" in text and "Channel: Dealer" in text, text
    assert "Top 1 channel" not in text and "Across all" not in text, text


def test_cf2_project_sales_top_10_for_a_product_keeps_the_agent_axis(console, monkeypatch) -> None:
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from tests._mc_lookup_seed import product

    db = console.session_factory()
    try:
        product(db, company_id=DEFAULT_COMPANY_ID, code=OTHER_CODE)
        db.commit()
    finally:
        db.close()
    _agent_ranking(console, monkeypatch)
    v = _v63(group_by="channel", sales_channel="project", top_n=10, entities=[_e(OTHER_CODE, "product")],
             entity_op="replace_combine", domain_in_message=True)
    text, log = _say_all(console, monkeypatch, v, f"Project sales top 10 {OTHER_CODE.lower()}")
    ran = _ran(log)
    assert len(ran) == 1, (text, log)
    args = ran[0]
    assert args["group_by"] == "sales_agent" and args["top_n"] == 10 and args["channel"] == "project", args
    assert args["product_code"] == OTHER_CODE and args["date_from"] == "2026-01-01", args
    assert "Top 10 of 12 sales agents" in text and "Channel: Project team" in text, text
    assert "Top 1 channel" not in text and "Across all" not in text, text


# ------------------------------------------------ guards: today's behaviour


def test_cf3_guard_sales_by_channel_stays_a_channel_ranking(console, monkeypatch) -> None:
    _agent_ranking(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _v63(group_by="channel", ranking_refine=True), "sales by channel")
    ran = _ran(log)  # owner ruling B: a new axis runs across all, and the header says so
    assert len(ran) == 1 and ran[0]["group_by"] == "channel" and "channel" not in ran[0], (text, log)
    assert ran[0]["product_code"] == PRODUCT_CODE and ran[0]["date_from"] == "2026-01-01", ran
    assert text.startswith("Across all sales agents\n\nTop 2 channels by delivered sales"), text


def test_cf4_guard_with_nothing_held_the_parse_is_today_s(console, monkeypatch) -> None:
    text, log = _say_all(console, monkeypatch, _dealer_only(), "Dealer sales only")
    assert _ran(log) == [], (text, log)
    assert text == (
        "1. Which period? For example this month, September, 2026, or 1 to 15 Sep.\n2. How many? For example top 5.\n"
        "3. By quantity or by amount?\n4. Invoiced, delivered, ordered or outstanding?"
    ), text


def test_cf5_guard_a_stale_frame_gives_today_s_reply(console, monkeypatch) -> None:
    _agent_ranking(console, monkeypatch)
    failed = _v63(group_by="weather", top_n=5, ranking_refine=False, measure="qty", basis="delivered",
                  entity_op="replace_combine", domain_in_message=True, **YEAR_2026)
    text, log = _say_all(console, monkeypatch, failed, "top 5 by weather")
    assert _ran(log) == [], ("setup: the failing ask ran", text, log)
    text, log = _say_all(console, monkeypatch, _dealer_only(), "Dealer sales only")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == "channel" and ran[0]["channel"] == "dealer", (text, log)
    assert text.startswith("Top 1 channel by delivered sales\nChannel: Dealer"), text


def test_cf6_dealer_sales_only_filters_a_held_report_ask_total(console, monkeypatch) -> None:
    """A total is one row by construction too: the channel filters the held total, never a channel ranking."""
    total = _v63(group_by=None, ranking_refine=False, measure="qty", rank_by="quantity", basis="delivered",
                 entities=[_e(PRODUCT_CODE, "product")], entity_op="replace_combine", domain_in_message=True, **YEAR_2026)
    text, log = _say_all(console, monkeypatch, total, f"total qty of {PRODUCT_CODE} in 2026 delivered")
    assert len(_ran(log)) == 1 and not _ran(log)[0].get("group_by"), ("setup", text, log)
    text, log = _say_all(console, monkeypatch, _dealer_only(), "Dealer sales only")
    ran = _ran(log)
    assert len(ran) == 1, (text, log)
    args = ran[0]
    assert not args.get("group_by") and "top_n" not in args and args["channel"] == "dealer", args
    assert args["product_code"] == PRODUCT_CODE and args["date_from"] == "2026-01-01" and args["date_to"] == "2026-12-31", args
    assert args["measure"] == "qty" and args["basis"] == "delivered", args
    assert text.startswith("Sales by delivered sales\nChannel: Dealer\n") and "?" not in text, text
