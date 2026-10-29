"""REPORT-OUTSTANDING-SUMMARY item 6 (owner 29 Oct, as before #1922): a "more" under an outstanding summary whose
breakdown was cut at 20 rows re-runs the SAME held ask at the next page (`group_offset`), on the report ask. The
pre-#1922 report's own "more" (`_outstanding_report_output`, `_answer_outstanding(more=)`) is the model; it rides on the
same CHAT-COMPOSER carry and gate."""
from __future__ import annotations

from app.services.chatbot.lanes.business import fetch, report_ask
from tests.chatbot.test_composers_stock_xd import _set_gate

FRAME = {"basis": "pending_delivery", "product_code": "ZZT-A", "measure": "amount"}


def _envelope(window):
    return {"response": "Product: ZZT-A\n...", "has_result": True, **({"group_window": window} if window else {})}


def _ctx():
    return {"semantic_input": {"report_ask_args": dict(FRAME)}}


def test_the_summary_output_arms_the_more_carry(monkeypatch):
    _set_gate(monkeypatch, True)
    out = fetch._report_ask_output(_envelope({"offset": 0, "shown": 20, "total": 45}), _ctx())
    assert out["set_window"]["carry"] == {"report_groups": True, "total": 45, "shown": 20}, out.get("set_window")
    _set_gate(monkeypatch, False)
    assert "set_window" not in fetch._report_ask_output(_envelope({"offset": 0, "shown": 20, "total": 45}), _ctx())


def test_more_under_the_list_offer_is_a_page_of_the_held_summary(monkeypatch):
    from app.services.chatbot.turn.apply import _answer_top_selling_pick
    from app.services.chatbot.turn.decide import Decision
    from app.services.chatbot.turn.pending import ask as pending_ask
    from app.services.chatbot.turn.plan import Trace
    from app.services.chatbot.turn.state import Focus
    from app.services.chatbot.turn_runtime import SET_CONTINUE_KEY

    pending = pending_ask(
        "top_selling_pick", [{"position": 1, "label": "Delivery order list", "code": report_ask.DO_LIST}],
        team=None, asked_at_turn=1,
        payload={"domain": "sales", "status": "sales_ranking",
                 "filters": {"tool": "crm_report_ask", "ranking": {"group_by": report_ask.DO_LIST}}},
    )
    _set_gate(monkeypatch, True)
    focus = Focus(domains=["sales"])
    focus.set_page = {"set_key": {"report_groups": True, "total": 45, "shown": 20, "domain": "sales"}}
    verdict = {SET_CONTINUE_KEY: True}
    out = _answer_top_selling_pick(pending, Decision("carry", "nothing_answered"), focus, Trace(), verdict)
    assert out is not None, "a 'more' under the summary is the next page, never the generic roster path"
    focus_out, pending_out, _q, handled = out
    assert handled is True and pending_out is pending, "the list offer stays open"
    assert verdict["ranking_detail"] == {"group_by": report_ask.MORE_PAGE, "offset": 20}, verdict
    assert focus_out.status == "sales_ranking" and focus_out.set_page is None


def test_settle_reruns_the_held_frame_at_the_offset():
    parse = {
        "order_status": report_ask.ASK_NAME, "ranking_detail": {"group_by": report_ask.MORE_PAGE, "offset": 20},
        "sales_ranking_frame": dict(FRAME),
    }
    outcome, line = report_ask.settle(None, parse, [])
    assert line is None and outcome is not None and outcome.done, (line, outcome and outcome.reply)
    args = report_ask.route_args(outcome)
    assert args["group_offset"] == 20 and args["basis"] == "pending_delivery" and args["product_code"] == "ZZT-A", args
    assert not args.get("group_by"), args


def test_the_page_is_read_under_its_frames_kind():
    parse = {
        "order_status": report_ask.ASK_NAME, "ranking_detail": {"group_by": report_ask.MORE_PAGE, "offset": 20},
        "sales_ranking_frame": dict(FRAME),
    }
    assert report_ask.list_pick_kind(parse) == "pending_delivery"
    assert report_ask.grant_key(parse) == report_ask.OUTSTANDING_GRANT


# ================================================================ eval send-back hard guard: a document list pages too

LIST_ARGS = {**FRAME, "group_by": "delivery_order", "top_n": 1000}
WINDOW = {"offset": 0, "shown": 20, "total": 2000}


def test_the_reply_one_list_arms_a_more_that_pages_the_list(monkeypatch):
    """"1" under a summary prints the delivery orders as a detail (the summary stays held); its "more" is the list's."""
    _set_gate(monkeypatch, True)
    ctx = {"semantic_input": {"report_ask_args": dict(LIST_ARGS), "report_ask_detail": True}}
    out = fetch._report_ask_output(_envelope(WINDOW), ctx)
    assert out["set_window"]["carry"] == {
        "report_groups": True, "total": 2000, "shown": 20, "list": report_ask.DO_LIST,
    }, out.get("set_window")


def test_the_no_subject_list_arms_more_and_a_pick_to_answer_it(monkeypatch):
    """Item 3's list (no subject) is the frame on screen: "more" needs an open pick to reach it (`_answer_top_selling_pick`)."""
    _set_gate(monkeypatch, True)
    out = fetch._report_ask_output(_envelope(WINDOW), {"semantic_input": {"report_ask_args": dict(LIST_ARGS)}})
    assert out["set_window"]["carry"]["report_groups"] is True, out.get("set_window")
    assert out["outstanding_ask"] and out["outstanding_ask"]["kind"] == "top_selling_pick", out.get("outstanding_ask")


def test_more_under_the_reply_one_list_carries_the_list(monkeypatch):
    from app.services.chatbot.turn.apply import _answer_top_selling_pick
    from app.services.chatbot.turn.decide import Decision
    from app.services.chatbot.turn.pending import ask as pending_ask
    from app.services.chatbot.turn.plan import Trace
    from app.services.chatbot.turn.state import Focus
    from app.services.chatbot.turn_runtime import SET_CONTINUE_KEY

    pending = pending_ask(
        "top_selling_pick", [{"position": 1, "label": "Delivery order list", "code": report_ask.DO_LIST}],
        team=None, asked_at_turn=1,
        payload={"domain": "sales", "status": "sales_ranking",
                 "filters": {"tool": "crm_report_ask", "ranking": {"group_by": report_ask.DO_LIST}}},
    )
    _set_gate(monkeypatch, True)
    focus = Focus(domains=["sales"])
    focus.set_page = {"set_key": {"report_groups": True, "total": 2000, "shown": 20, "list": report_ask.DO_LIST}}
    verdict = {SET_CONTINUE_KEY: True}
    _answer_top_selling_pick(pending, Decision("carry", "nothing_answered"), focus, Trace(), verdict)
    assert verdict["ranking_detail"] == {"group_by": report_ask.MORE_PAGE, "offset": 20, "list": report_ask.DO_LIST}


def test_settle_pages_the_list_under_a_held_summary():
    parse = {
        "order_status": report_ask.ASK_NAME,
        "ranking_detail": {"group_by": report_ask.MORE_PAGE, "offset": 20, "list": report_ask.DO_LIST},
        "sales_ranking_frame": dict(FRAME),
    }
    outcome, line = report_ask.settle(None, parse, [])
    args = report_ask.route_args(outcome)
    assert args["group_by"] == "delivery_order" and args["group_offset"] == 20, args
    assert outcome.extras.get("detail") is True  # the summary stays the frame on screen


def test_settle_pages_a_list_frame():
    parse = {
        "order_status": report_ask.ASK_NAME, "ranking_detail": {"group_by": report_ask.MORE_PAGE, "offset": 40},
        "sales_ranking_frame": dict(LIST_ARGS),
    }
    outcome, _line = report_ask.settle(None, parse, [])
    args = report_ask.route_args(outcome)
    assert args["group_by"] == "delivery_order" and args["group_offset"] == 40, args


def test_a_short_no_subject_list_arms_no_pick(monkeypatch):
    """Review nit: with no page to continue, the list arms nothing (a "1" there is not a hidden re-list)."""
    _set_gate(monkeypatch, True)
    out = fetch._report_ask_output(_envelope(None), {"semantic_input": {"report_ask_args": dict(LIST_ARGS)}})
    assert out["outstanding_ask"] is None and "set_window" not in out, out
