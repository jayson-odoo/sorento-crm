"""Small helpers the customer pick tests and the sales total ask tests share (not a test module). The `Chat` harness
(real `engine.run_turn`, faked sales tools) is #1931's, kept here after its company-question tests retired.

Small helpers the customer pick tests share.

They lived in `test_sales_analysis_company_pick.py`, whose tests pinned the sales analysis company question
("Sorento or Mocha?"). REPORT-UNIFY (owner ruling Q1) retired that question with `crm_sales_analysis` for every
axis but the Yearly comparison: a sales ask is `crm_report_ask`, which reads the contact's own companies.
"""
from __future__ import annotations

from typing import Any

import json

import pytest  # noqa: F401
from sqlalchemy import text as sql_text

from tests.chatbot.test_engine import CONTACT_ID, _parser_output  # noqa: F401

GRANT = "sales_orders.sales_report"


def _pick(position: int) -> dict[str, Any]:
    """The parser's declared answer to an open numbered question: the option at `position`."""
    return {"mode": "pick", "items": [], "picked": [position], "qty_for_all": None}


def _calls(captured: list[tuple[str, dict[str, Any]]], tool: str) -> list[dict[str, Any]]:
    return [args for name, args in captured if name == tool]


ANALYSIS = "crm_sales_analysis"
REPORT = "crm_sales_report"
PRODUCT_RAW = "b2155-nl-blue"
PRODUCT_CODE = "B2155-NL-BLUE"
PRODUCT_UUID = "b2155000-0000-4000-8000-000000002155"
BRAND_UUID = "5040e000-0000-4000-8000-00000000b001"
QUESTION = "Sorento or Mocha?"
SEP_2026 = {"date_mode": "month", "date_filter_start": "2026-09-01", "date_filter_end": "2026-09-30"}

#: Keyed by the token the lane asks the resolver about (punctuation-free), measured.
_PRODUCT_MATCH = {"b2155nlblue": {"uuid": PRODUCT_UUID, "entity_type": "product", "canonical_code": PRODUCT_CODE}}

#: `crm_sales_report`'s route body for the product (turn A): a hit, so the drill offer arms.
REPORT_BODY: dict[str, Any] = {
    "status": "ok", "message": None, "basis": "delivered", "customer_name": None,
    "customer_count": 1, "product_code": PRODUCT_CODE, "product_codes": [], "channel": None,
    "channel_shown": False, "location_token": None, "warehouse_codes": [],
    "date_from": "2026-01-01", "date_to": "2026-12-31", "grain": "month",
    "total": {"qty": 10, "amount": 100.0},
    "periods": [{"from": "2026-09-01", "to": "2026-09-30", "qty": 10, "amount": 100.0}],
    "group_by": None, "rows": [], "more": 0,
    "options": [
        {"key": "product", "label": "By product"},
        {"key": "delivery_order", "label": "Delivery orders"},
    ],
}


def _analysis_body(company: str) -> dict[str, Any]:
    """`crm_sales_analysis`'s ready body (`test_sales_analysis_lane.ROUTE_HIT`'s shape)."""
    return {
        "status": "ready", "report": "Sales", "company": company, "channel": "Dealer",
        "basis": "Delivered (transferred to DO)", "period": "01/09/2026 to 30/09/2026",
        "rows_label": "Channel", "cols_label": "Year", "count_label": "Channels",
        "columns": ["2026"],
        "rows": [{"label": "Dealer", "values": ["100.00"], "total": "100.00"}],
        "totals": {"values": ["100.00"], "total": "100.00"},
        "total_count": 1, "attachments": [],
    }


def _sales_mcp(companies: tuple[str, ...]):
    """A `_capturing_mcp` stand-in over the contact's `companies` (default first). The sales
    analysis with no company answers as the route does: the only company's figures, or the
    clarify naming every company the contact holds."""

    def factory(response: Any = None):
        from tests.chatbot.test_outstanding_lane import _present_response

        present = _present_response()
        captured: list[tuple[str, dict[str, Any]]] = []

        def _call(name: str, args: dict[str, Any]) -> Any:
            captured.append((name, dict(args)))
            if name == REPORT:
                return present(name, json.dumps(REPORT_BODY))
            if name == ANALYSIS:
                company = args.get("company")
                if not company and len(companies) > 1:
                    body = {"status": "clarify", "message": f"{', '.join(companies[:-1])} or {companies[-1]}?"}
                else:
                    body = _analysis_body(company or companies[0])
                return present(name, json.dumps(body))
            return json.dumps({"has_result": False, "items": []})

        return _call, captured

    return factory


def _add_mocha(session_factory) -> None:
    """The contact's second company (`_seed_contact` links the default, Sorento)."""
    from tests._mc_lookup_seed import MOCHA_ID, seed_mocha

    db = session_factory()
    seed_mocha(db)
    db.execute(
        sql_text(
            "INSERT INTO respond_contact_companies (id, respond_contact_id, company_id) "
            "SELECT gen_random_uuid(), id, :company_id FROM respond_contacts WHERE respond_io_id = :cid"
        ),
        {"cid": str(CONTACT_ID), "company_id": MOCHA_ID},
    )
    db.commit()


class Chat:
    def __init__(self, session_factory, monkeypatch, companies: tuple[str, ...]) -> None:
        from tests.chatbot import test_outstanding_lane as lane
        from tests.chatbot._turn_helpers import make_office_access_type
        from tests.chatbot.test_escalation_agent_carry import _capture_next_assignee, _capture_sla

        self.session_factory, self.monkeypatch, self.lane = session_factory, monkeypatch, lane
        monkeypatch.setattr(lane, "_capturing_mcp", _sales_mcp(companies))
        # The round-robin draw and the SLA row are faked (no SLA policy or access agent rows
        # here), so a turn the engine hands to a person completes the way it did live
        # ("Routed to your PIC"); `handoffs` records every assignment asked for.
        self.handoffs = _capture_next_assignee(monkeypatch)
        _capture_sla(monkeypatch)
        lane._seed_contact(session_factory, variables={})
        if "Mocha" in companies:
            _add_mocha(session_factory)
        make_office_access_type(session_factory, CONTACT_ID)
        self.n = 0

    def say(self, qf: dict[str, Any], body: str, **kwargs: Any):
        self.n += 1
        kwargs.setdefault("matches", _PRODUCT_MATCH)
        result, captured = self.lane._run_turn(
            self.session_factory, self.monkeypatch, qf=qf, text_body=body,
            msg_id=f"ZZT-sacp-{self.n}", attributes=[GRANT], **kwargs,
        )
        return result, captured

    def next_open_question(self) -> dict[str, Any] | None:
        """The question the NEXT turn's parser is shown, read off the stored session the way
        the engine loads it (`turn_runtime.load_state`, `turn/question.open_question`)."""
        from app.services.chatbot.turn.question import open_question
        from app.services.chatbot.turn.state import Profile
        from app.services.chatbot.turn_runtime import load_state

        state = load_state(
            {"session_vars": self.lane._session_of(self.session_factory)}, profile=Profile(), turn_no=0
        )
        return open_question(state.pending, state.focus.tasks, state.focus.required_ask)



def _reply(result: Any) -> str:
    return (result.reply or {}).get("text") or ""
