"""S1 (#1267): the business lane picks `crm_sales_analysis` for a sales analysis ask and
sends the text AND the Excel.

UAC: AC-S1-20 (the args of "compare dealer sales 2025 vs 2026 by month"), AC-S1-22 (no
period said = this calendar year, printed), AC-R4-1 (text + one attachment on the turn),
AC-R4-3 (the refusal carries none), AC-R4-5 (no `reply_format` key; nothing in the words
changes the format), plus the gate (`sales_orders.sales_report`, total denial before any
fetch) and the parser contract (`order_status "sales_analysis"`, `group_by` month/year,
`sales_basis`, `sales_company`).

Built on the harness `test_sales_report_lane.py` imports from `test_outstanding_lane.py`.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest

from app.services.chatbot.lanes.business.services import FetchServices
from tests.chatbot.test_outstanding_lane import (
    _capturing_mcp,
    _present_response,
    _qf,
    _run_turn,
    _seed_contact,
)

TOOL = "crm_sales_analysis"
GRANT = "sales_orders.sales_report"
ATT = {
    "url": "https://cdn.test.invalid/exports/report-xlsx/x/Yearly comparison-2026.xlsx",
    "filename": "Yearly comparison-2026.xlsx",
    "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "attachmentType": "file",
}
ROUTE_HIT: dict[str, Any] = {
    "status": "ready", "report": "Sales", "company": "Sorento", "channel": "Project team",
    "basis": "Delivered (transferred to DO)", "period": "01/01/2026 to 26/09/2026",
    "rows_label": "Channel", "cols_label": "Year", "count_label": "Channels",
    "columns": ["2026"],
    "rows": [{"label": "Project team", "values": ["1234.50"], "total": "1234.50"}],
    "totals": {"values": ["1234.50"], "total": "1234.50"},
    "total_count": 1, "attachments": [ATT],
}


def _rendered(payload=ROUTE_HIT) -> str:
    return _present_response()(TOOL, json.dumps(payload))


#: REPORT-UNIFY (Q1): only the Yearly comparison is left on this tool (every other axis is the report ask's), and
#: a sales total never defaults its basis (owner, 27 Oct): the asks here name both.
YEARLY = dict(group_by="year", sales_basis="delivered")


def _payload(*, attributes=(GRANT,), **qf):
    qf = {**YEARLY, **qf}
    return {
        "gate": {"compatible_entities": []},
        "tier_gate": None,
        "ctx": {
            "parse": {"output": _qf(order_status="sales_analysis", entities=[], **qf)},
            "contact": {"id": 900000008},
            "access": {"attributes": list(attributes)},
        },
    }


def _args(session_factory, **qf) -> tuple[str, dict[str, Any]]:
    from app.services.chatbot.lanes.business import run_fetch

    call, captured = _capturing_mcp(_rendered())
    run_fetch(_payload(**qf), services=FetchServices(mcp_call=call))
    assert captured, "no MCP tool was ever called"
    return captured[0]


class TestToolPickAndArgs:
    def test_a_yearly_comparison_with_no_basis_asks_the_basis_never_defaults_to_invoiced(self, session_factory):
        from app.services.chatbot.lanes.business import run_fetch

        call, captured = _capturing_mcp(_rendered())
        out = run_fetch(_payload(sales_basis=None), services=FetchServices(mcp_call=call))
        assert captured == [], captured
        assert "Invoiced, delivered, ordered or outstanding?" in str(out), out

    def test_a_total_asks_channel_by_year(self, session_factory):
        _name, args = _args(session_factory, sales_channel="project")
        assert args["rows"] == "channel" and args["cols"] == "year"
        assert args["channel"] == "project"

    def test_reviewer_r2_s1_by_year_is_named_not_defaulted(self, session_factory):
        """S1 (review round 2): "by year" is the years across, one line per channel, mapped
        on purpose rather than falling through to the default."""
        _name, args = _args(session_factory, group_by="year",
                            date_filter_start="2024-01-01", date_filter_end="2026-09-26")
        assert args["rows"] == "channel" and args["cols"] == "year"

    def test_ac_s1_22_no_period_said_is_this_calendar_year(self, session_factory):
        from app.services.reports.registry import today_malaysia

        _name, args = _args(session_factory)
        today = today_malaysia()
        assert args["date_from"] == date(today.year, 1, 1).isoformat()
        assert args["date_to"] == today.isoformat()

    def test_basis_and_company_come_from_the_parser(self, session_factory):
        _name, args = _args(session_factory, sales_basis="ordered", sales_company="Mocha")
        assert args["basis"] == "ordered"
        assert args["company"] == "Mocha"

    def test_s1_6_invoiced_reaches_the_route(self, session_factory):
        """Finance S1 (#1309): the parser's "invoiced" is the tool's basis, not Delivered."""
        _name, args = _args(session_factory, sales_basis="invoiced")
        assert args["basis"] == "invoiced"

    def test_the_outstanding_and_sales_report_picks_are_untouched(self, session_factory):
        from app.services.chatbot.lanes.business import run_fetch

        call, captured = _capturing_mcp(_rendered())
        payload = _payload()
        payload["ctx"]["parse"]["output"]["order_status"] = "outstanding"
        run_fetch(payload, services=FetchServices(mcp_call=call))
        assert not captured or captured[0][0] != TOOL


class TestGate:
    def test_no_key_denies_before_any_fetch(self, session_factory, monkeypatch):
        _seed_contact(session_factory, variables={})
        result, captured = _run_turn(
            session_factory, monkeypatch,
            qf=_qf(order_status="sales_analysis", entities=[]),
            text_body="total project sales this year", msg_id="ZZT-sa-no-key-1",
            attributes=[],
        )
        assert captured == []
        assert ((result.reply or {}).get("text") or "").strip() == (
            "Sales report is not enabled for your account."
        )


class TestTextAndFile:
    def test_ac_r4_1_the_turn_sends_the_text_and_the_file(self, session_factory, monkeypatch):
        _seed_contact(session_factory, variables={})
        result, captured = _run_turn(
            session_factory, monkeypatch,
            qf=_qf(order_status="sales_analysis", entities=[], sales_channel="project", **YEARLY),
            text_body="total project sales this year", msg_id="ZZT-sa-hit-1",
            attributes=[GRANT], mcp_response=_rendered(),
        )
        assert [c[0] for c in captured] == [TOOL]
        text = (result.reply or {}).get("text") or ""
        assert "Project team: RM 1,234.50" in text
        assert "Total: RM 1,234.50" in text
        # Found by the console run: the answer states its own scope, so the order
        # domain's generic header must not print above it.
        assert text.startswith("*Sales, Sorento*"), text
        assert "Customer: all customers" not in text and "Dates: all dates" not in text
        kinds = [a.get("kind") for a in (result.actions or [])]
        assert "send_attachments" in kinds, result.actions

    def test_ac_r4_3_a_clarify_answer_sends_no_file(self, session_factory, monkeypatch):
        _seed_contact(session_factory, variables={})
        result, _captured = _run_turn(
            session_factory, monkeypatch,
            qf=_qf(order_status="sales_analysis", entities=[], **YEARLY),
            text_body="sales this year", msg_id="ZZT-sa-clarify-1",
            attributes=[GRANT],
            mcp_response=_rendered({"status": "clarify", "message": "Sorento or Mocha?"}),
        )
        assert "Sorento or Mocha?" in ((result.reply or {}).get("text") or "")
        kinds = [a.get("kind") for a in (result.actions or [])]
        assert "send_attachments" not in kinds


class TestUnsupportedAxis:
    """S1 (review round 2): an axis the sales analysis cannot draw is said plainly, with no
    figure and no fetch, never a silent by-channel table. REPORT-SMART-1021: customer, product
    and warehouse are the report ask's now (`tests/chatbot/test_report_smart_capability.py`);
    an axis no sales tool draws is still said."""

    @pytest.mark.parametrize("group_by", ["date", "supplier", "transporter"])
    def test_an_axis_it_cannot_draw_is_said_and_nothing_is_fetched(
        self, session_factory, monkeypatch, group_by
    ):
        _seed_contact(session_factory, variables={})
        result, captured = _run_turn(
            session_factory, monkeypatch,
            qf=_qf(order_status="sales_analysis", entities=[], group_by=group_by),
            text_body=f"sales by {group_by} this year", msg_id=f"ZZT-sa-axis-{group_by}",
            attributes=[GRANT], mcp_response=_rendered(),
        )
        assert captured == []
        text = ((result.reply or {}).get("text") or "").strip()
        # REPORT-UNIFY (R2): the report ask draws month and channel now; the line names the axes it can.
        from app.services.chatbot.lanes.business import report_ask

        assert text == report_ask.UNSUPPORTED_AXIS_LINE.format(axis=group_by)
        kinds = [a.get("kind") for a in (result.actions or [])]
        assert "send_attachments" not in kinds

    def test_run_fetch_refuses_it_too(self, session_factory):
        from app.services.chatbot.lanes.business import run_fetch

        call, captured = _capturing_mcp(_rendered())
        run_fetch(_payload(group_by="customer"), services=FetchServices(mcp_call=call))
        assert captured == []


class TestParserContract:
    def test_the_schema_declares_the_new_keys_and_group_by_values(self):
        from app.services.chatbot.head.parser import PARSE_OUTPUT_JSON_SCHEMA, TOLERATED_ABSENT

        props = PARSE_OUTPUT_JSON_SCHEMA["properties"]
        assert {"month", "year"} <= set(props["group_by"]["enum"])
        assert props["sales_basis"]["enum"] == ["ordered", "delivered", "invoiced", None]
        assert "sales_company" in props
        required = set(PARSE_OUTPUT_JSON_SCHEMA["required"])
        assert {"sales_basis", "sales_company"} <= required
        assert {"sales_basis", "sales_company"} <= TOLERATED_ABSENT
        assert "reply_format" not in props

    def test_the_prompt_teaches_sales_analysis(self):
        from app.services.chatbot_parser_prompt import SEMANTIC_PARSER_PROMPT

        assert 'order_status "sales_analysis"' in SEMANTIC_PARSER_PROMPT
        assert '"sales_basis"' in SEMANTIC_PARSER_PROMPT
        assert '"sales_company"' in SEMANTIC_PARSER_PROMPT
        assert "reply_format" not in SEMANTIC_PARSER_PROMPT

    @pytest.mark.parametrize("key", ["sales_basis", "sales_company"])
    def test_the_keys_reach_the_fetch_semantic_input(self, key):
        import inspect

        from app.services.chatbot.lanes.business import _fetch_semantic_input

        assert key in inspect.getsource(_fetch_semantic_input)


def test_ac_s1_19_the_seed_rows_carry_the_same_tool():
    # Lives here, not beside the migration test: only tests/chatbot/ may import the
    # chatbot package (test_import_boundary).
    from app.services.chatbot.lanes.business.fetch import CHATBOT_READ_ONLY_TOOLS
    from app.services.chatbot.turn import policy_rows
    from app.services.mcp_tool_domains import CHATBOT_TOOL_DOMAINS as TOOL_DOMAINS

    order = next(r for r in policy_rows.DEFAULT_DOMAIN_ROWS if r["name"] == "order")
    # REPORT-UNIFY: the Yearly file is an override, not a row tool: the order row no longer lists it.
    assert TOOL not in order["tools"]
    assert TOOL in CHATBOT_READ_ONLY_TOOLS
    # (its date params ride `fetch.DATE_PARAMS`, not a row's tools)
    assert TOOL_DOMAINS[TOOL] == "sales"  # R7 (PLAN-prompt-dynamic-30sep D9)


# ------------------------------------------------ finance S1 (#1309): basis invoiced
class TestInvoicedBasis:
    """UAC S1-6: the parser can say "invoiced" and the fetch lane passes it to the route."""

    def test_s1_6_the_parser_can_say_invoiced(self):
        from app.services.chatbot.head.parser import PARSE_OUTPUT_JSON_SCHEMA
        from app.services.chatbot_parser_prompt import SEMANTIC_PARSER_PROMPT

        props = PARSE_OUTPUT_JSON_SCHEMA["properties"]
        assert props["sales_basis"]["enum"] == ["ordered", "delivered", "invoiced", None]
        assert '"invoiced", "invoices", "billed" -> "invoiced"' in SEMANTIC_PARSER_PROMPT

    def test_s1_6_the_fetch_lane_passes_invoiced_through(self):
        from app.services.chatbot.lanes.business import fetch

        assert "invoiced" in fetch.SALES_ANALYSIS_BASES


class TestANon2xxIsAnErrorOnTheTrace:
    def test_b3_a_403_from_the_route_is_an_error_fragment_and_on_the_trace(self, session_factory) -> None:
        """CHATBOT-SELFREF-SCOPE B3: the MCP client stamps a 403 with its status, the
        presenter answers an error envelope, and the lane records it as a tool ERROR
        (`kind: error`, never `has_result: true` with a friendly line) with the envelope,
        status and the route's own code on the `tool` trace event."""
        from app.services.chatbot.lanes.business import run_fetch
        from app.services.chatbot.trace import TurnTrace

        route_403 = {
            "success": False, "message": "Permission required", "code": "PERMISSION_DENIED",
            "error": "GET /api/v1/sales/analysis returned HTTP 403: PERMISSION_DENIED",
            "http_error": "GET /api/v1/sales/analysis returned HTTP 403: PERMISSION_DENIED",
            "status_code": 403, "path": "/api/v1/sales/analysis", "method": "GET",
        }
        call, captured = _capturing_mcp(_present_response()(TOOL, json.dumps(route_403)))
        trace = TurnTrace()
        fragment = run_fetch(_payload(), services=FetchServices(mcp_call=call), trace=trace)
        assert captured and captured[0][0] == TOOL
        assert fragment["kind"] == "error", fragment
        assert "HTTP 403" in fragment["error"] and "PERMISSION_DENIED" in fragment["error"], fragment
        assert (fragment.get("fetch") or {}).get("has_result") is not True
        assert "Could not run the sales report" not in json.dumps(fragment)
        (tool_event,) = [e for e in trace.events if e.get("kind") == "tool"]
        assert tool_event["envelope"]["status_code"] == 403
        assert "HTTP 403" in tool_event["envelope"]["error"]
        assert tool_event["envelope"]["detail"]["code"] == "PERMISSION_DENIED"
