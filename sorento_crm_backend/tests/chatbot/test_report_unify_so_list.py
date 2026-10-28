"""REPORT-UNIFY AC-RU-17a (owner 28 Oct 09:30): an undelivered-orders answer offers "Reply 1 for the sales order list.";
"1" re-runs the SAME held ask grouped by sales order. Pending delivery and unpaid get no offer. Fake names only."""
from __future__ import annotations

from typing import Any

import pytest

from tests.chatbot import test_report_ask_lane as lane_tests
from tests.chatbot.test_report_ask_lane import _e
from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import TOOL, _say_all, console  # noqa: F401
from tests.chatbot.test_report_smart_step7 import KEEP, _state_on

OFFER = "Reply 1 for the sales order list."
SO_ROWS = [
    {"rank": 1, "name": "ZZT-SO-1001", "qty": 6, "amount": 600.0, "keys": []},
    {"rank": 2, "name": "ZZT-SO-1002", "qty": 5, "amount": 50.0, "keys": []},
]


def _body(args: dict[str, Any]) -> dict[str, Any]:
    group_by = args.get("group_by")
    rows = SO_ROWS if group_by == "sales_order" else []
    labels = {"outstanding": "outstanding orders", "pending_delivery": "pending delivery", "unpaid": "unpaid invoices"}
    return {
        "status": "ok", "message": None, "basis": args.get("basis", "outstanding"),
        "basis_label": labels.get(args.get("basis", "outstanding"), "delivered sales"),
        "measure": args.get("measure", "amount"), "sort": "desc", "group_by": group_by,
        "group_label": "Sales order" if group_by else None,
        "date_from": args.get("date_from"), "date_to": args.get("date_to"),
        "filters": [], "rows": rows, "more": 0, "total_count": len(rows), "total": {"qty": 11, "amount": 650.0},
    }


@pytest.fixture(autouse=True)
def _route_body(monkeypatch):
    monkeypatch.setattr(lane_tests, "_fake_body", _body)


def _outstanding(kind: str) -> dict[str, Any]:
    return _parser_output(
        domain_hint="order", intent_hint="check_order", order_status="outstanding", entities=[], group_by=None,
        top_n=None, measure=None, basis=kind, domain_in_message=True, state_changes=list(KEEP),
        date_filter_start=None, date_filter_end=None,
    )


def _pick_one() -> dict[str, Any]:
    return _parser_output(
        message_type="casual", intent_hint=None, domain_hint=None, entities=[], order_status=None,
        reference_positions=[1], open_question_answer={"mode": "pick", "picked": [1], "items": [], "qty_for_all": None},
        state_changes=[{"op": "answer", "axis": None, "position": 1}])


def _ran(log):
    return [a for n, a in log if n == TOOL]


def test_an_undelivered_orders_answer_ends_with_the_sales_order_offer(console, monkeypatch) -> None:
    _state_on(console)
    text, log = _say_all(console, monkeypatch, _outstanding("outstanding"), "undelivered orders")
    assert len(_ran(log)) == 1, (text, log)
    assert text.rstrip().endswith(OFFER), text


def test_reply_one_lists_the_open_sales_orders_of_the_same_ask(console, monkeypatch) -> None:
    _state_on(console)
    _say_all(console, monkeypatch, _outstanding("outstanding"), "undelivered orders")
    text, log = _say_all(console, monkeypatch, _pick_one(), "1")
    ran = _ran(log)
    assert len(ran) == 1, (text, log)
    assert ran[0]["group_by"] == "sales_order" and ran[0]["basis"] == "outstanding", ran
    assert "date_from" not in ran[0] and "date_to" not in ran[0], ran
    assert "ZZT-SO-1001" in text and "ZZT-SO-1002" in text, text
    assert OFFER not in text, text


@pytest.mark.parametrize("kind", ["pending_delivery", "unpaid"])
def test_pending_delivery_and_unpaid_get_no_offer(console, monkeypatch, kind) -> None:
    _state_on(console)
    text, log = _say_all(console, monkeypatch, _outstanding(kind), kind.replace("_", " "))
    assert len(_ran(log)) == 1, (text, log)
    assert OFFER not in text, text


def test_a_one_the_live_parser_reads_with_a_stale_so_status_still_opens_the_list(console, monkeypatch) -> None:
    """The 3 Oct 2026 hand test (PR #1435, `test_so_list.py::_live`): "1" under the outstanding summary came back
    with `so_outstanding` and the SO document carried over. It is the answer to the offer, never the summary again."""
    _state_on(console)
    _say_all(console, monkeypatch, _outstanding("outstanding"), "undelivered orders")
    stale = _parser_output(
        message_type="business_query", domain_hint="order", intent_hint="check_order", order_status="so_outstanding",
        document=["SO"], self_reference=True, entities=[], entity_op="reuse", reference_positions=[1],
        reference_target="result",
        open_question_answer={"mode": "pick", "items": [], "picked": [1], "qty_for_all": None},
    )
    text, log = _say_all(console, monkeypatch, stale, "1")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == "sales_order", (text, log)
    assert "ZZT-SO-1001" in text, text


def test_a_one_the_live_parser_reads_as_a_did_you_mean_pick_still_opens_the_list(console, monkeypatch) -> None:
    """28 Oct 2026 hand test (parser v189): "1" under the outstanding summary parsed `reference_target: dym`,
    `so_outstanding`, the SO document, `entity_op: reuse`, a declared pick AND position 1, no self_reference."""
    _state_on(console)
    first = _outstanding("outstanding")
    first.update(order_status="so_outstanding", document=["SO"], entity_op="replace_combine", basis=None, entities=[{**_e("Sorento", "brand"), "hint_confident": True}])
    t0, l0 = _say_all(console, monkeypatch, first, "any outstanding mocha item in sales order")
    assert len(_ran(l0)) == 1 and OFFER in t0, (t0, l0)
    live = _parser_output(
        message_type="business_query", domain_hint="order", intent_hint="check_order", order_status="so_outstanding",
        document=["SO"], self_reference=False, entities=[], entity_op="reuse", reference_positions=[1],
        reference_target="dym", domain_in_message=False, user_goal="trying to view the sales order list",
        open_question_answer={"mode": "pick", "items": [], "picked": [1], "qty_for_all": None},
    )
    text, log = _say_all(console, monkeypatch, live, "1")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == "sales_order", (text, log)
    assert "ZZT-SO-1001" in text, text


def test_without_pick_axis_keeps_the_offers_own_status_so_the_held_frame_rides_under_the_so_list_offer() -> None:
    """Live cause (28 Oct): the seam returned `order_status: None` for the SO-list pick, but the held ranking frame rides
    only on a verdict whose `order_status == "sales_ranking"`; the pick must carry the offer's own status."""
    from app.services.chatbot.lanes.business import report_ask
    from app.services.chatbot.turn.pending import ask as pending_ask

    pending = pending_ask(
        "top_selling_pick", [{"position": 1, "label": "Sales order list", "code": "sales_order_list"}],
        team=None, asked_at_turn=1,
        payload={
            "domain": "sales", "status": "sales_ranking",
            "filters": {"tool": "crm_report_ask", "ranking": {"group_by": "sales_order_list"}},
        },
    )
    verdict = {
        "order_status": "so_outstanding", "status": "so_outstanding", "document": ["SO"], "entity_op": "reuse",
        "domain_hint": "order", "intent_hint": "check_order", "message_type": "business_query",
        "reference_target": "dym", "reference_positions": [1],
        "open_question_answer": {"mode": "pick", "items": [], "picked": [1], "qty_for_all": None},
    }
    out = report_ask.without_pick_axis(verdict, pending)
    assert out["order_status"] == "sales_ranking" and out.get("group_by") is None, out


def test_a_one_when_the_parser_emits_status_so_outstanding_on_both_turns_still_opens_the_list(console, monkeypatch) -> None:
    """Live step 13: `status: so_outstanding` on BOTH turns, so `focus.status` is carried and `lane_parse_output`'s
    document / status projection must not overwrite the `sales_ranking` the SO-list pick seam set."""
    _state_on(console)
    first = _outstanding("outstanding")
    first.update(
        order_status="so_outstanding", status="so_outstanding", document=["SO"], entity_op="replace_combine",
        basis=None, entities=[{**_e("Sorento", "brand"), "hint_confident": True}],
    )
    t0, l0 = _say_all(console, monkeypatch, first, "any outstanding mocha item in sales order")
    assert len(_ran(l0)) == 1 and OFFER in t0, (t0, l0)
    live = _parser_output(
        message_type="business_query", domain_hint="order", intent_hint="check_order", order_status="so_outstanding",
        status="so_outstanding", document=["SO"], self_reference=False, entities=[], entity_op="reuse",
        reference_positions=[1], reference_target="dym", domain_in_message=False,
        user_goal="trying to view the sales order list",
        open_question_answer={"mode": "pick", "items": [], "picked": [1], "qty_for_all": None},
    )
    text, log = _say_all(console, monkeypatch, live, "1")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == "sales_order", (text, log)
    assert "ZZT-SO-1001" in text, text
