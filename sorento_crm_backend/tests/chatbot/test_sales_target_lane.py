"""Phase 2 RED tests - chat routing for sales target progress (lane SALES-TARGET-CHAT, slice 1).

`documentation/plans/sales/sales-target-chat-25oct-acceptance-criteria.md` T4-1 to T4-7 and
PLAN-sales-target-chat-25oct.md "Chatbot". Written BEFORE any wiring exists.

Built on the harness the sales report tests share (`test_outstanding_lane.py::_run_turn`,
`test_sales_domain_routing.py::_picked`): parser, access, resolver and MCP faked, no live LLM.
The fake MCP returns a STRING verbatim, so the target tool's answer is whatever envelope a
test hands it; assertions read the captured `(tool, args)` list and the reply text.

Tester's choices, made explicit:

* A route 403 reaches the lane as the MCP error envelope `http_error_body` builds
  (`status_code`, `detail.code`, `has_result` false, empty `response`); T4-6 feeds exactly
  that and expects the lane to read `detail.code`.
* The new status is spelled `sales_target` (parser value) and the grant `sales.sales_target`.
* Postgres only (`session_factory`). Every row seeded here.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from tests.chatbot.test_customer_scope_lane import OWN_A, _hanlim_services, _link_customers, refusal
from tests.chatbot.test_outstanding_lane import _qf, _run_turn, _seed_contact, _session_of
from tests.chatbot.test_sales_domain_routing import _normalised, _picked

TOOL = "crm_sales_target_progress"
GRANT = "sales.sales_target"
REPORT_GRANT = "sales_orders.sales_report"
DENIAL = "Sales target is not enabled for your account."
OWN_ACCOUNTS = "I can only share targets for your own accounts."

TARGET_ANSWER = json.dumps(
    {
        "result_type": "sales_target",
        "response": (
            "Sales target Q4 2026 (1 Oct to 31 Dec)\nCounts: A/C I\n"
            "Achieved: RM 17,414.05 (provisional, incl. tax, to 23 Oct)\n"
            "Next tier: Tier 1, 3% at RM 85,000.00, RM 67,585.95 to go"
        ),
        "has_result": True,
    }
)


def _route_403(code: str) -> str:
    """What the MCP layer hands the lane for a non-2xx route answer (`http_error_body`)."""
    return json.dumps(
        {
            "has_result": False,
            "status_code": 403,
            "error": f"GET /api/v1/sales/target-progress returned HTTP 403: {code}",
            "detail": {"code": code},
            "response": "",
            "answers": [],
        }
    )


def _target_qf(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(order_status="sales_target", entities=[], self_reference=True)
    base.update(over)
    return _qf(**base)


def _turn(session_factory, monkeypatch, *, attributes, qf=None, body="how is my target this quarter?", **kw):
    return _run_turn(
        session_factory, monkeypatch, qf=qf or _target_qf(), text_body=body,
        msg_id=f"ZZT-stc-{abs(hash((body, tuple(attributes), json.dumps(qf, default=str)))) % 10**9}",
        attributes=list(attributes), **kw,
    )


def _reply(result) -> str:
    return ((result.reply or {}).get("text") or "").strip()


# --------------------------------------------------------------------------- #
# T4-1 - routing: sales domain, the new status, the target tool, never the report
# --------------------------------------------------------------------------- #


class TestTargetQuestionRoutesToTargetTool:
    @pytest.mark.parametrize("prior", ["order", "master_products", None])
    def test_the_status_is_the_sales_domain(self, prior) -> None:
        assert _normalised(domain_hint=prior, order_status="sales_target")["domain_hint"] == "sales"

    def test_the_status_is_not_a_sales_figure_status(self) -> None:
        from app.services.chatbot import contracts

        assert "sales_target" not in contracts.SALES_FIGURE_STATUSES

    def test_the_lane_picks_the_target_tool_under_sales(self, session_factory) -> None:
        captured = _picked("sales", "sales_target", [], attributes=(GRANT,), response=TARGET_ANSWER)
        assert [c[0] for c in captured] == [TOOL], captured

    @pytest.mark.parametrize("linked", [True, False], ids=["dealer-linked", "unlinked-salesperson-style"])
    def test_a_granted_target_ask_calls_the_target_tool_never_the_report(
        self, session_factory, monkeypatch, linked
    ) -> None:
        _seed_contact(session_factory, variables={})
        if linked:
            _link_customers(session_factory, OWN_A)
        result, captured = _turn(session_factory, monkeypatch, attributes=[GRANT], mcp_response=TARGET_ANSWER)
        names = [c[0] for c in captured]
        assert names == [TOOL], captured
        assert "crm_sales_report" not in names
        assert not captured[0][1].get("customer_ids"), (
            f"an unnamed target ask must not carry customer ids (the route scopes the contact): {captured[0][1]}"
        )


# --------------------------------------------------------------------------- #
# T4-2 - no grant, no tool, the fixed line
# --------------------------------------------------------------------------- #


class TestTargetWithoutGrantRefused:
    def test_target_without_grant_refused(self, session_factory, monkeypatch) -> None:
        _seed_contact(session_factory, variables={})
        result, captured = _turn(session_factory, monkeypatch, attributes=[])
        assert captured == [], captured
        assert _reply(result) == DENIAL

    def test_run_fetch_refuses_without_the_grant(self, session_factory) -> None:
        captured = _picked("sales", "sales_target", [], attributes=(), response=TARGET_ANSWER)
        assert captured == [], captured


# --------------------------------------------------------------------------- #
# T4-3 - a named period reaches the tool
# --------------------------------------------------------------------------- #


class TestTargetNamedPeriodPassed:
    def test_target_named_period_passed(self, session_factory, monkeypatch) -> None:
        _seed_contact(session_factory, variables={})
        qf = _target_qf(date_filter_start="2026-07-01", date_filter_end="2026-09-30")
        _result, captured = _turn(
            session_factory, monkeypatch, attributes=[GRANT], qf=qf, body="did we hit Q3?",
            mcp_response=TARGET_ANSWER,
        )
        assert [c[0] for c in captured] == [TOOL], captured
        args = captured[0][1]
        assert args.get("date_from") == "2026-07-01" and args.get("date_to") == "2026-09-30", args

    def test_the_fetch_date_table_names_the_pair(self) -> None:
        from app.services.chatbot.lanes.business import fetch

        assert fetch.DATE_PARAMS.get(TOOL) == ("date_from", "date_to")


# --------------------------------------------------------------------------- #
# T4-4 - the allow-list and the contract tables carry the tool
# --------------------------------------------------------------------------- #


class TestTargetToolAllowed:
    def test_target_tool_allowed(self) -> None:
        from app.services.chatbot import contracts
        from app.services.chatbot.lanes.business.fetch import CHATBOT_READ_ONLY_TOOLS, CUSTOMER_SCOPED_TOOLS
        from app.services.mcp_tool_domains import CHATBOT_TOOL_DOMAINS

        assert TOOL in CHATBOT_READ_ONLY_TOOLS
        assert TOOL in contracts.UNDOMAINED_CHATBOT_TOOLS
        assert contracts.BRAND_SCOPE_TREATMENT.get(TOOL) == "no_products"
        assert CHATBOT_TOOL_DOMAINS.get(TOOL) == "sales"
        assert TOOL in CUSTOMER_SCOPED_TOOLS

    def test_the_reveal_key_is_listed(self) -> None:
        from app.services.contact_field_reveal_service import FIELD_REVEAL_KEYS

        assert (GRANT, "Sales target") in FIELD_REVEAL_KEYS


# --------------------------------------------------------------------------- #
# T4-5 - a dealer naming another dealer
# --------------------------------------------------------------------------- #


class TestDealerOtherDealerRefused:
    def test_dealer_other_dealer_refused(self, session_factory, monkeypatch) -> None:
        _seed_contact(session_factory, variables={})
        _link_customers(session_factory, OWN_A)
        entity = {"raw": "hanlim", "hint": "customer", "canonical_code": None, "current_message": True, "confident": True}
        result, captured = _turn(
            session_factory, monkeypatch, attributes=[GRANT],
            qf=_target_qf(entities=[entity], self_reference=False), body="what is hanlim's target?",
            resolve_services=_hanlim_services(), mcp_response=TARGET_ANSWER,
        )
        assert captured == [], captured
        assert _reply(result) == refusal(OWN_A)


# --------------------------------------------------------------------------- #
# T4-6 - the route's own refusals, worded
# --------------------------------------------------------------------------- #


class TestTargetRouteRefusalsWorded:
    @pytest.mark.parametrize(
        "code,line",
        [
            ("customer_not_permitted", OWN_ACCOUNTS),
            ("sales_target_not_enabled", DENIAL),
            ("sales_target_not_available", DENIAL),
        ],
    )
    def test_target_route_refusals_worded(self, session_factory, monkeypatch, code, line) -> None:
        _seed_contact(session_factory, variables={})
        result, captured = _turn(
            session_factory, monkeypatch, attributes=[GRANT], mcp_response=_route_403(code),
        )
        assert [c[0] for c in captured] == [TOOL], captured
        assert _reply(result) == line, _reply(result)


# --------------------------------------------------------------------------- #
# T4-7 - the grant is independent of the sales report grant
# --------------------------------------------------------------------------- #


class TestTargetGrantIndependentOfSalesReport:
    def test_target_grant_alone_gets_the_target_answer(self, session_factory, monkeypatch) -> None:
        _seed_contact(session_factory, variables={})
        result, captured = _turn(session_factory, monkeypatch, attributes=[GRANT], mcp_response=TARGET_ANSWER)
        assert [c[0] for c in captured] == [TOOL], captured
        assert DENIAL not in _reply(result)
        assert "Sales report is not enabled" not in _reply(result)

    def test_sales_report_grant_alone_gets_the_target_denial(self, session_factory, monkeypatch) -> None:
        _seed_contact(session_factory, variables={})
        result, captured = _turn(session_factory, monkeypatch, attributes=[REPORT_GRANT], mcp_response=TARGET_ANSWER)
        assert captured == [], captured
        assert _reply(result) == DENIAL

    def test_a_refused_target_ask_arms_nothing(self, session_factory, monkeypatch) -> None:
        _seed_contact(session_factory, variables={})
        _turn(session_factory, monkeypatch, attributes=[])
        assert not (_session_of(session_factory).get("open_question") or {})


# --------------------------------------------------------------------------- #
# T4-8 - a salesperson contact (no links, no staff user) names a dealer
# --------------------------------------------------------------------------- #


class TestSalespersonNamedDealerReachesTargetTool:
    """Drives the real engine gate (`engine.py` granted_report_turn / unlinked_held), parser
    and MCP faked. The contact has no `respond_contact_customers` link and no staff user, so
    today the typed dealer word is refused as "isn't under your account" before any tool."""

    def _named(self, session_factory):
        from tests.chatbot.test_customer_scope_lane import _other_customer

        _seed_contact(session_factory, variables={})
        code = "ZZTD-001"
        dealer_id = _other_customer(session_factory, "ZZT DEALER SDN BHD", code=code)
        entity = {"raw": code, "hint": "customer", "canonical_code": None, "current_message": True, "confident": True}
        match = {code: {"uuid": dealer_id, "entity_type": "customer", "canonical_code": code}}
        return dealer_id, entity, match

    def test_salesperson_named_dealer_reaches_target_tool(self, session_factory, monkeypatch) -> None:
        dealer_id, entity, match = self._named(session_factory)
        result, captured = _turn(
            session_factory, monkeypatch, attributes=[GRANT], body="ZZTD-001 target this quarter?",
            qf=_target_qf(entities=[entity], self_reference=False), matches=match, mcp_response=TARGET_ANSWER,
        )
        assert [c[0] for c in captured] == [TOOL], (captured, _reply(result))
        assert dealer_id in (captured[0][1].get("customer_ids") or []), captured
        assert "isn't under your account" not in _reply(result), _reply(result)

    def test_without_the_grant_the_refusal_stays(self, session_factory, monkeypatch) -> None:
        _dealer_id, entity, match = self._named(session_factory)
        result, captured = _turn(
            session_factory, monkeypatch, attributes=[], body="ZZTD-001 target this quarter?",
            qf=_target_qf(entities=[entity], self_reference=False), matches=match, mcp_response=TARGET_ANSWER,
        )
        assert captured == [], captured
        reply = _reply(result)
        assert "isn't under your account" in reply or reply == DENIAL, reply
