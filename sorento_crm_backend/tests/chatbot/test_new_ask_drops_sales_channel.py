"""CHAT-PICK-QTY-STATE fix round SALES-COMPANY, defect (2): a NEW ASK that names no channel
drops the held sales channel (red tests, test-first).

Live (v63, old path, staff), recorded as the parser emitted it:

* step 5 "srt102-rg dealer sales may 2026": `sales_channel: dealer`, `order_status:
  sales_analysis`, so `focus.sales_channel` became "dealer".
* step 6 "srt102-rg sales 2026": `sales_channel: null`, `order_status: sales_report`,
  product srt102-rg (`current_message: true`), 2026-01-01..2026-12-31, `domain_hint:
  order`, `domain_in_message: true`, `entity_op: replace_combine`, `state_changes: null`.
  `decide()` filed it NEW ASK (why `domain_in_message`); the rules fired were
  replace_same_axis, new_ask_drops_date_window, domains_from_asks, date_restated_only,
  focus_settles_product, and `crm_sales_report` still ran with channel "dealer".

The rule (owner hand pass 6, 17 Sep 2026): a NEW ASK drops every axis it did not itself
name (`turn/apply.py`'s new-ask branch beside `new_ask_drops_date_window`; the top selling
precedent is `_drop_unnamed_filters`). A FOLLOW-UP keeps the channel
(PLAN-chatbot-sales-report.md S4 wiring point 2: a customer-picker answer continues the
ask with its channel).

* R1 (RED) apply level: the step 6 verdict over a held "dealer" focus leaves no channel,
  and the trace names `new_ask_drops_sales_channel` (the tester's chosen rule name).
* R2 (RED) engine level: step 5 then step 6 through `engine.run_turn`; the step 6
  `crm_sales_report` call carries no channel and the reply's Channel line reads "all".
* R3 (GREEN guard) a customer-picker answer ("1") keeps the channel the ask named.
* R4 (GREEN guard) a new ask naming its own channel sets it.
* R5 (GREEN guard) "and for june" over the held dealer report is a refine, not a new ask,
  and keeps dealer (`decide()` files it REFINE `narrows_the_open_question` under the
  report's open drill offer, and CARRY `nothing_answered` with no offer open).
* S1 (GREEN guard, finding) the state path's `new_subject` already drops the channel,
  through `apply_changes` AND `apply`, so the state path has no twin of this gap.

Engine harness: `test_outstanding_lane._run_turn` (real `engine.run_turn`, Postgres,
parser / access / resolver / MCP faked), with its `_capturing_mcp` swapped for a double
that echoes the call's own `channel` onto the route body the way
`sales_report_delivered` does when it shows the channel, then renders it through the
REAL MCP presenter. Fake customers only (public repo).
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.chatbot.lanes.business.services import ResolveGateServices
from app.services.chatbot.turn.state import Focus, Profile, State
from tests.chatbot._turn_helpers import build_policy, entity, verdict
from tests.chatbot.conftest import validating_resolve_entity
from tests.chatbot.test_engine import CONTACT_ID, _parser_output

RULE = "new_ask_drops_sales_channel"
GRANT = "sales_orders.sales_report"
PRODUCT_RAW = "srt102-rg"
PRODUCT_CODE = "SRT102-RG"
PRODUCT_UUID = "a1020000-0000-4000-8000-000000000102"
MAY_2026 = {"mode": "month", "start": "2026-05-01", "end": "2026-05-31"}

CUSTOMER_UUID_1 = "d0000000-0000-4000-8000-000000000001"
CUSTOMER_UUID_2 = "d0000000-0000-4000-8000-000000000002"
CUSTOMER_CODE_1 = "300-ZZ001"
CUSTOMER_CODE_2 = "300-ZZ002"


# --------------------------------------------------------------------------- #
# Apply-level builders (R1, R5, S1)
# --------------------------------------------------------------------------- #


def _held_product() -> dict[str, Any]:
    """The product step 5 settled: a resolved row from an earlier turn."""
    return {"raw": PRODUCT_CODE, "hint": "product", "canonical_code": PRODUCT_CODE, "uuid": PRODUCT_UUID}


def _after_step_5(**extra: Any) -> State:
    """The focus step 5 ("srt102-rg dealer sales may 2026") left behind, as measured off the
    engine run in R2 (`session_vars.focus` after step 5)."""
    focus = Focus(
        products=[_held_product()],
        domains=["sales"],
        sales_channel="dealer",
        date_window=dict(MAY_2026),
        **extra,
    )
    return State(focus=focus, pending=None, profile=Profile(), turn_no=5)


def _step_6_verdict(**overrides: Any) -> dict[str, Any]:
    """Step 6 "srt102-rg sales 2026" exactly as the parser emitted it live."""
    base = dict(
        domain_hint="order",
        intent_hint="check_order",
        order_status="sales_report",
        sales_channel=None,
        entities=[entity(PRODUCT_RAW, hint="product", canonical_code=None, current_message=True)],
        entity_op="replace_combine",
        domain_in_message=True,
        date_mode="year",
        date_filter_start="2026-01-01",
        date_filter_end="2026-12-31",
        state_changes=None,
    )
    base.update(overrides)
    return verdict(**base)


def _apply(state: State, v: dict[str, Any]):
    from app.services.chatbot.turn.apply import apply

    return apply(state, v, build_policy())


# --------------------------------------------------------------------------- #
# Engine-level harness (R2, R3, R4, R5)
# --------------------------------------------------------------------------- #

#: The sales report route's body for one product (the shape `SalesReportResponse`
#: declares; `test_sales_report_lane.SALES_REPORT_HIT`'s fields). `channel` and
#: `channel_shown` are overwritten per call by `_echoing_mcp`.
SALES_REPORT_BODY: dict[str, Any] = {
    "status": "ok",
    "message": None,
    "basis": "delivered",
    "customer_name": None,
    "customer_count": 1,
    "product_code": PRODUCT_CODE,
    "product_codes": [],
    "channel": None,
    "channel_shown": True,
    "location_token": None,
    "warehouse_codes": [],
    "date_from": None,
    "date_to": None,
    "grain": "month",
    "total": {"qty": 10, "amount": 100.0},
    "periods": [{"from": "2026-05-01", "to": "2026-05-31", "qty": 10, "amount": 100.0}],
    "group_by": None,
    "rows": [],
    "more": 0,
    "options": [
        {"key": "product", "label": "By product"},
        {"key": "delivery_order", "label": "Delivery orders"},
    ],
}

#: `crm_sales_analysis`'s route body (`test_sales_analysis_lane.ROUTE_HIT`'s shape, no file).
SALES_ANALYSIS_BODY: dict[str, Any] = {
    "status": "ready", "report": "Sales", "company": "Sorento", "channel": "Dealer",
    "basis": "Delivered (transferred to DO)", "period": "01/05/2026 to 31/05/2026",
    "rows_label": "Channel", "cols_label": "Year", "count_label": "Channels",
    "columns": ["2026"],
    "rows": [{"label": "Dealer", "values": ["100.00"], "total": "100.00"}],
    "totals": {"values": ["100.00"], "total": "100.00"},
    "total_count": 1, "attachments": [],
}


def _echoing_mcp(response: Any = None):
    """A `mcp_call(name, args)` double: records every call and answers the two sales tools
    with their route bodies pushed through the REAL presenter. The sales report body echoes
    THIS call's `channel` the way `sales_report_delivered` does when the channel line is
    shown (`channel_shown` true, `channel` the named class or None), so the reply's
    Channel line reads whatever channel the lane actually sent."""
    from tests.chatbot.test_outstanding_lane import _present_response

    present = _present_response()
    captured: list[tuple[str, dict[str, Any]]] = []

    def _call(name: str, args: dict[str, Any]) -> Any:
        captured.append((name, dict(args)))
        if name == "crm_sales_report":
            channel = args.get("channel")
            body = {
                **SALES_REPORT_BODY,
                "channel": channel if channel in ("dealer", "project") else None,
                "channel_shown": True,
                "customer_name": "ZZ Demo Trading Sdn Bhd" if args.get("customer_ids") else None,
                "product_code": args.get("product_code"),
                "date_from": args.get("date_from"),
                "date_to": args.get("date_to"),
            }
            if args.get("group_by"):
                body["group_by"] = args["group_by"]
            return present(name, json.dumps(body))
        if name == "crm_sales_analysis":
            return present(name, json.dumps(SALES_ANALYSIS_BODY))
        return json.dumps({"has_result": False, "items": []})

    return _call, captured


#: Keyed by the token the lane ASKS the resolver about (its punctuation-free token key,
#: "srt102rg"), measured: keyed by the raw "srt102-rg" it never matches and the turn misses.
_PRODUCT_MATCH = {"srt102rg": {"uuid": PRODUCT_UUID, "entity_type": "product", "canonical_code": PRODUCT_CODE}}


def _ambiguous_customer_services() -> ResolveGateServices:
    """One customer word ("zz demo") matching two accounts, so the sales report asks which."""

    def _resolve_entity(body: dict[str, Any]) -> dict[str, Any]:
        return {
            "tokens": ["zz demo"],
            "resolutions": [
                {
                    "token": "zz demo",
                    "matches": [
                        {
                            "entity_type": "customer", "canonical_code": CUSTOMER_CODE_1,
                            "uuid": CUSTOMER_UUID_1, "company_code": "SRT",
                            "display": {"customer_name": "ZZ DEMO TRADING SDN BHD"},
                        },
                        {
                            "entity_type": "customer", "canonical_code": CUSTOMER_CODE_2,
                            "uuid": CUSTOMER_UUID_2, "company_code": "SRT",
                            "display": {"customer_name": "ZZ DEMO HARDWARE SDN BHD"},
                        },
                    ],
                },
            ],
            "unresolved_tokens": [],
        }

    return ResolveGateServices(
        access_types=lambda **_: [{"name": "Sorento Dealer"}],
        resolve_entity=validating_resolve_entity(_resolve_entity),
        probe=lambda **_: {"items": [], "has_result": False},
    )


@pytest.fixture
def chat(session_factory, monkeypatch):
    """A staff contact (office access type) with the sales report grant, and a `turn(...)`
    that runs one real engine turn with the echoing MCP double."""
    from tests.chatbot import test_outstanding_lane as lane
    from tests.chatbot._turn_helpers import make_office_access_type

    monkeypatch.setattr(lane, "_capturing_mcp", _echoing_mcp)
    lane._seed_contact(session_factory, variables={})
    make_office_access_type(session_factory, CONTACT_ID)

    def turn(qf: dict[str, Any], text: str, msg_id: str, **kwargs: Any):
        kwargs.setdefault("matches", _PRODUCT_MATCH)
        return lane._run_turn(
            session_factory, monkeypatch,
            qf=qf, text_body=text, msg_id=msg_id, attributes=[GRANT], **kwargs,
        )

    def apply_event(result: Any) -> dict[str, Any]:
        """The turn's own `apply` trace event (`engine.run_turn`): what `decide()` read the
        message as, and the rules that fired."""
        from app.models.chatbot_turn import ChatbotTurn

        row = session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).first()
        events = [e for e in (row.trace or []) if isinstance(e, dict) and e.get("kind") == "apply"]
        assert len(events) == 1, events
        return events[0]

    turn.session = lambda: lane._session_of(session_factory)  # type: ignore[attr-defined]
    turn.apply_event = apply_event  # type: ignore[attr-defined]
    return turn


def _product_entity() -> dict[str, Any]:
    return {"raw": PRODUCT_RAW, "hint": "product", "canonical_code": None, "current_message": True, "confident": True}


def _step_5_qf() -> dict[str, Any]:
    """"srt102-rg dealer sales may 2026", as the parser emitted it live."""
    return _parser_output(
        domain_hint="order", intent_hint="check_order", order_status="sales_analysis",
        sales_channel="dealer", entities=[_product_entity()], entity_op="replace_combine",
        domain_in_message=True, date_mode="month",
        date_filter_start="2026-05-01", date_filter_end="2026-05-31",
    )


def _step_6_qf(**overrides: Any) -> dict[str, Any]:
    """"srt102-rg sales 2026", as the parser emitted it live (`state_changes` absent: the
    old path, the same as `null`)."""
    base = dict(
        domain_hint="order", intent_hint="check_order", order_status="sales_report",
        sales_channel=None, entities=[_product_entity()], entity_op="replace_combine",
        domain_in_message=True, date_mode="year",
        date_filter_start="2026-01-01", date_filter_end="2026-12-31",
    )
    base.update(overrides)
    return _parser_output(**base)


def _report_calls(captured: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    return [args for name, args in captured if name == "crm_sales_report"]


def _reply(result: Any) -> str:
    return (result.reply or {}).get("text") or ""


# --------------------------------------------------------------------------- #
# R1 (RED) - apply level
# --------------------------------------------------------------------------- #


class TestANewAskDropsTheHeldChannel:
    def test_r1_the_step_6_new_ask_leaves_no_channel_on_the_focus(self):
        state_out, plan = _apply(_after_step_5(), _step_6_verdict())
        fired = list(plan.trace.rules_fired)
        # Setup: the turn is read the way it was live, as a NEW ASK over the held product.
        assert plan.trace.decision == {"kind": "new_ask", "why": "domain_in_message"}, plan.trace.decision
        assert "new_ask_drops_date_window" in fired, fired
        assert state_out.focus.sales_channel is None, (
            "a NEW ASK that names no channel drops the held one (owner hand pass 6: a new ask "
            f"drops every axis it did not name); kept {state_out.focus.sales_channel!r}, rules {fired}"
        )
        assert RULE in fired, f"the drop must be named on the trace as {RULE!r}: {fired}"

    def test_r1_the_ask_itself_and_its_window_are_unchanged(self):
        """What step 6 DID name still lands (guards the fix against dropping too much)."""
        state_out, _plan = _apply(_after_step_5(), _step_6_verdict())
        focus = state_out.focus
        assert [p.get("raw") for p in focus.products] == [PRODUCT_RAW], focus.products
        assert focus.date_window == {"mode": "year", "start": "2026-01-01", "end": "2026-12-31"}, focus.date_window


# --------------------------------------------------------------------------- #
# R2 (RED) - engine level, the live two-turn sequence
# --------------------------------------------------------------------------- #


class TestTheLiveSequenceThroughTheEngine:
    def test_r2_step_6_runs_the_sales_report_over_every_channel(self, chat):
        _result5, captured5 = chat(_step_5_qf(), "srt102-rg dealer sales may 2026", "ZZT-nadc-r2-step-5")
        assert [name for name, _ in captured5] == ["crm_sales_analysis"], captured5
        assert (chat.session().get("focus") or {}).get("sales_channel") == "dealer", (
            "setup: step 5 must hold the dealer channel", chat.session().get("focus"),
        )

        result6, captured6 = chat(_step_6_qf(), "srt102-rg sales 2026", "ZZT-nadc-r2-step-6")
        event = chat.apply_event(result6)
        assert event.get("decision") == {"kind": "new_ask", "why": "domain_in_message"}, (
            "setup: step 6 is read as it was live", event.get("decision"), event.get("rules_fired"),
        )
        calls = _report_calls(captured6)
        assert calls, f"step 6 must run the sales report: {captured6}"
        args = calls[0]
        assert args.get("date_from") == "2026-01-01" and args.get("date_to") == "2026-12-31", args
        assert not args.get("channel"), (
            f"a new ask that names no channel must count every channel, not the held 'dealer': {args}"
        )
        reply = _reply(result6)
        assert "*Channel:* all" in reply, reply
        assert "*Channel:* Retail" not in reply, reply
        assert (chat.session().get("focus") or {}).get("sales_channel") is None, chat.session().get("focus")


# --------------------------------------------------------------------------- #
# R3 (GREEN guard) - a follow-up keeps the channel
# --------------------------------------------------------------------------- #


class TestAFollowUpKeepsTheChannel:
    def test_r3_a_customer_picker_answer_continues_with_the_named_channel(self, chat):
        _result1, captured1 = chat(
            _parser_output(
                domain_hint="order", intent_hint="check_order", order_status="sales_report",
                sales_channel="dealer", domain_in_message=True, entity_op="replace_combine",
                entities=[{"raw": "zz demo", "hint": "customer", "canonical_code": None,
                           "current_message": True, "confident": True}],
            ),
            "dealer sales report for zz demo", "ZZT-nadc-r3-ask-1",
            resolve_services=_ambiguous_customer_services(),
        )
        assert _report_calls(captured1) == [], captured1
        assert (chat.session().get("open_question") or {}).get("kind") == "customer_pick", (
            "setup: the customer picker must be armed", chat.session().get("open_question"),
        )

        _result2, captured2 = chat(
            _parser_output(
                message_type="casual", intent_hint=None, domain_hint=None, entities=[],
                reference_positions=[1], reference_target="dym", entity_op="reuse", order_status=None,
            ),
            "1", "ZZT-nadc-r3-pick-1",
        )
        calls = _report_calls(captured2)
        assert calls, f"the pick must run the sales report: {captured2}"
        assert calls[0].get("customer_ids") == [CUSTOMER_UUID_1], calls[0]
        assert calls[0].get("channel") == "dealer", (
            f"a picker answer is a follow-up and keeps the channel its ask named: {calls[0]}"
        )


# --------------------------------------------------------------------------- #
# R4 (GREEN guard) - a new ask that names its own channel
# --------------------------------------------------------------------------- #


class TestANewAskNamingItsOwnChannel:
    def test_r4_apply_sets_the_named_channel(self):
        state_out, plan = _apply(_after_step_5(), _step_6_verdict(sales_channel="project"))
        assert state_out.focus.sales_channel == "project", plan.trace.rules_fired

    def test_r4_the_report_runs_for_the_named_channel(self, chat):
        chat(_step_5_qf(), "srt102-rg dealer sales may 2026", "ZZT-nadc-r4-step-5")
        result, captured = chat(
            _step_6_qf(sales_channel="project"), "srt102-rg project sales 2026", "ZZT-nadc-r4-step-6",
        )
        calls = _report_calls(captured)
        assert calls, captured
        assert calls[0].get("channel") == "project", calls[0]
        assert "*Channel:* Project" in _reply(result), _reply(result)


# --------------------------------------------------------------------------- #
# R5 (GREEN guard) - a period-only refine on the held report keeps the channel
# --------------------------------------------------------------------------- #


def _june_verdict(**overrides: Any) -> dict[str, Any]:
    """"and for june": a period of its own, no domain word, no entity."""
    base = dict(
        domain_hint=None, intent_hint=None, order_status=None, sales_channel=None, entities=[],
        entity_op="reuse", domain_in_message=False, date_mode="month",
        date_filter_start="2026-06-01", date_filter_end="2026-06-30",
    )
    base.update(overrides)
    return base


class TestAPeriodOnlyRefineKeepsTheChannel:
    def test_r5_apply_with_nothing_open_is_a_carry_that_keeps_dealer(self):
        state = _after_step_5()
        state.focus.status = "sales_report"
        state.focus.date_window = {"mode": "year", "start": "2026-01-01", "end": "2026-12-31"}
        state_out, plan = _apply(state, verdict(**_june_verdict()))
        assert plan.trace.decision == {"kind": "carry", "why": "nothing_answered"}, plan.trace.decision
        assert RULE not in plan.trace.rules_fired, plan.trace.rules_fired
        assert state_out.focus.sales_channel == "dealer", plan.trace.rules_fired
        assert state_out.focus.date_window["start"] == "2026-06-01", state_out.focus.date_window

    def test_r5_and_for_june_reruns_the_dealer_report_over_june(self, chat):
        _result1, captured1 = chat(
            _step_6_qf(sales_channel="dealer"), "srt102-rg dealer sales 2026", "ZZT-nadc-r5-ask-1",
        )
        assert _report_calls(captured1), captured1
        assert _report_calls(captured1)[0].get("channel") == "dealer", captured1
        result2, captured2 = chat(
            _parser_output(message_type="business_query", **_june_verdict()),
            "and for june", "ZZT-nadc-r5-june-1",
        )
        event = chat.apply_event(result2)
        # Measured today: under the report's open drill offer, `decide()` files a period-only
        # turn as the offer's REFINE (`_answer_outstanding`'s `outstanding_refined` arm).
        assert event.get("decision") == {"kind": "refine", "why": "narrows_the_open_question"}, (
            event.get("decision"), event.get("rules_fired"),
        )
        assert RULE not in (event.get("rules_fired") or []), event.get("rules_fired")
        calls = _report_calls(captured2)
        assert calls, f"a period-only refine must re-run the report: {captured2}"
        assert calls[0].get("date_from") == "2026-06-01" and calls[0].get("date_to") == "2026-06-30", calls[0]
        assert calls[0].get("channel") == "dealer", (
            f"a refine on the held report is not a new ask and keeps its channel: {calls[0]}"
        )


# --------------------------------------------------------------------------- #
# S1 (GREEN guard, finding) - the state path's new_subject already drops the channel
# --------------------------------------------------------------------------- #


class TestTheStatePathHasNoTwin:
    def test_s1_new_subject_drops_the_channel_through_apply_changes_and_apply(self):
        from app.services.chatbot.turn import chat_state

        state = _after_step_5()
        v = _step_6_verdict(state_changes=[{"op": "new_subject", "axis": None, "position": None}])
        applied = chat_state.apply_changes(
            state, v, open_question=None,
            domains=["inventory", "incoming", "order", "sales"], kinds=["product", "customer"],
            brands=[], positions_read_elsewhere=False,
        )
        assert applied.valid is True, applied.log
        assert applied.state.state_led == "new_ask", applied.state.state_led
        state_out, plan = _apply(applied.state, applied.verdict)
        assert state_out.focus.sales_channel is None, plan.trace.rules_fired
