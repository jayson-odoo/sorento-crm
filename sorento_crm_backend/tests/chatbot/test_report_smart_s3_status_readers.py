"""REPORT-SMART-L round S3-4: a delivery status in `order_status` alone is read like `status`.

The parser fills the delivery status in `status` OR in `order_status`. Every reader takes the
same value: the State keeps it (a follow-up repeats it) and a named DO reaches the DO
outstanding path. Each case is a PAIR: the `status`-filled run is the expected value for the
`order_status`-filled run. Fake names and codes only; a staff contact WITH the SO grant.
"""
from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from app.services.chatbot import engine as engine_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.chatbot.lanes.business.services import AnswerServices, FetchServices
from tests.chatbot._turn_helpers import make_office_access_type, make_office_tier
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import _parser_output, seeded, stub_access  # noqa: F401
from tests.chatbot.test_outstanding_lane import CONTACT_ID
from tests.chatbot.test_report_ask_lane import Console, _console, _e, _rank
from tests.chatbot.test_report_smart_step7 import KEEP, THIS_YEAR, _state_on

SO_GRANT = "sales_orders.outstanding"
REPORT_GRANT = "sales_orders.sales_report"
OUTSTANDING_TOOL = "crm_outstanding_report"
CODES = ("SRTWT5724", "SRTWT5725")
CUSTOMER = "ZZ DEMO TRADING SDN BHD"


class Recorder(Console):
    """The report-ask console, recording every tool call (not only crm_report_ask)."""

    def say(self, qf: dict[str, Any], body: str):  # type: ignore[override]
        from app.services.chatbot import console_service
        from app.services.chatbot.head import parser as parser_mod

        self.monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: qf)
        self.all_calls = getattr(self, "all_calls", [])
        turn_calls: list[tuple[str, dict[str, Any]]] = []

        def _mcp(name: str, args: dict[str, Any]) -> Any:
            turn_calls.append((name, dict(args)))
            return json.dumps({"has_result": False, "items": []})

        self.monkeypatch.setattr(engine_mod.business_services, "fetch_services", lambda db: FetchServices(mcp_call=_mcp))
        self.monkeypatch.setattr(
            engine_mod.business_services, "answer_services_for",
            lambda session_factory: AnswerServices(mcp_probe=lambda n, a: {"data": []}, family_fetch=lambda q: {"data": []}),
        )
        db = self.session_factory()
        try:
            result = console_service.run_console_turn(
                db, contact_respond_id=str(CONTACT_ID), text=body,
                session_vars=copy.deepcopy(self.session_vars), run_id="zzt-s3-status",
            )
        finally:
            db.close()
        self.session_vars = result.session_vars or {}
        self.all_calls.extend(turn_calls)
        return result.reply_text or "", turn_calls


@pytest.fixture
def rec(session_factory, monkeypatch):
    from tests._mc_lookup_seed import customer, product

    c = _console(session_factory, monkeypatch, grants=[SO_GRANT, REPORT_GRANT])
    c.__class__ = Recorder
    make_office_tier(session_factory, CONTACT_ID)
    make_office_access_type(session_factory, CONTACT_ID)
    _state_on(c)
    db = session_factory()
    try:
        for code in CODES:
            product(db, company_id=DEFAULT_COMPANY_ID, code=code)
        customer(db, company_id=DEFAULT_COMPANY_ID, name=CUSTOMER)
        db.commit()
    finally:
        db.close()
    return c


def _when(code: str, **overrides: Any) -> dict[str, Any]:
    """'<code> when deliver to ZZ Demo Trading' as the live parser reads it."""
    base: dict[str, Any] = dict(
        domain_hint="order", intent_hint="check_order", domain_in_message=True,
        entities=[_e(code, "product"), _e("ZZ Demo Trading", "customer")],
        status=None, order_status=None, state_changes=list(KEEP),
    )
    base.update(overrides)
    return _parser_output(**base)


def _follow(code: str) -> dict[str, Any]:
    """'and SRTWT5725?': a product set, no status words, status and order_status null."""
    return _parser_output(
        domain_hint="order", intent_hint="check_order", domain_in_message=False,
        entities=[_e(code, "product")], status=None, order_status=None,
        state_changes=[{"op": "set", "axis": "product", "position": None}],
    )


def _focus_status(rec) -> Any:
    return (rec.session_vars.get("focus") or {}).get("status")


def _outstanding(calls: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    return [a for n, a in calls if n == OUTSTANDING_TOOL]


def _run_when(rec, **fields: Any):
    text, calls = rec.say(_when(CODES[0], **fields), f"{CODES[0]} when deliver to ZZ Demo Trading")
    return text, calls


# REPORT-UNIFY: an outstanding ask holding a subject is the report ask's, whichever field names it (its kind is asked),
# so the `order_status`-filled run no longer leaves an outstanding focus status; only the `status` field does.
@pytest.mark.parametrize("field", ["status"])
def test_s3_4_the_state_keeps_outstanding_whichever_field_the_parser_filled(rec, field) -> None:
    _run_when(rec, **{field: "outstanding"})
    assert _focus_status(rec) == "outstanding", rec.session_vars.get("focus")


def test_s3_4_near_miss_status_outstanding_with_no_order_status_is_as_today(rec) -> None:
    text, calls = _run_when(rec, status="outstanding")
    assert _focus_status(rec) == "outstanding", rec.session_vars.get("focus")
    # REPORT-UNIFY: a bare outstanding with a subject asks the kind (undelivered orders, pending delivery, unpaid invoices)
    assert "Undelivered orders or pending delivery?" in text and calls == [], (text, calls)


def test_s3_4_near_miss_status_delivered_is_as_today(rec) -> None:
    _run_when(rec, status="delivered")
    assert _focus_status(rec) == "delivered", rec.session_vars.get("focus")


def test_s3_4_near_miss_both_null_leaves_no_status_in_the_state(rec) -> None:
    _text, calls = _run_when(rec)
    assert not _focus_status(rec), rec.session_vars.get("focus")
    assert _outstanding(calls) == [], calls


def test_s3_4_near_miss_a_sales_ranking_verdict_still_runs_the_ranking_not_outstanding(rec) -> None:
    text, calls = rec.say(
        _rank(_e(CODES[0], "product"), top_n=5, measure="qty", basis="delivered", status=None,
              state_changes=list(KEEP), **THIS_YEAR),
        f"top 5 salesppl in 2026 for {CODES[0]}",
    )
    assert _outstanding(calls) == [], calls
    assert [a for n, a in calls if n == "crm_report_ask"], (text, calls)
    assert not _focus_status(rec), rec.session_vars.get("focus")  # a ranking is no delivery status


def test_s3_4_near_miss_a_projected_bucket_in_order_status_alone_leaves_the_focus_status_empty(rec) -> None:
    _run_when(rec, order_status="so_outstanding")
    assert not _focus_status(rec), rec.session_vars.get("focus")
