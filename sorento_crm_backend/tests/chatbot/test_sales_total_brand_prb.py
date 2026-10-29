"""Phase 2 RED tests - chat fix PR-B S5 (AC-B7): a sales total whose parse carries a brand is
filtered to that brand (R15 dealer: "Mocha" entity, hint brand, confident), never silently
unfiltered.  Lane half here; route half in tests/test_sales_report_brand_prb.py; MCP catalog
half in sorento_crm_mcp/tests/test_catalog_sales_report_brand_prb.py."""
from __future__ import annotations

import pytest

from app.services.chatbot.lanes.business.services import FetchServices
from tests.chatbot.test_outstanding_lane import (
    CUSTOMER_NAME, CUSTOMER_UUID, _capturing_mcp, _qf, _run_turn, _seed_contact,
)
from tests.chatbot.test_sales_report_lane import SALES_REPORT_HIT

BRAND_UUID = "bbbbbbbb-1111-4000-8000-0000000000b1"
OTHER_BRAND_UUID = "bbbbbbbb-1111-4000-8000-0000000000b2"
GRANT = "sales_orders.sales_report"
TOOL = "crm_report_ask"  # REPORT-UNIFY: a sales total is the report ask
#: A total names its basis and period (neither is defaulted).
_SALES = dict(order_status="sales_report", basis="delivered", date_filter_start="2026-09-01", date_filter_end="2026-09-30")


def _payload(entities, parse_entities=()):
    if not parse_entities:
        # The kinds the message named come off the verdict's own entities.
        parse_entities = [
            {"raw": e["canonical_code"], "hint": e["entity_type"], "canonical_code": None, "current_message": True, "confident": True}
            for e in entities
        ]
    return {
        "gate": {"compatible_entities": entities},
        "tier_gate": None,
        "ctx": {
            "parse": {"output": _qf(**_SALES, entities=list(parse_entities))},
            "contact": {"id": 900000008},
            "access": {"attributes": [GRANT]},
        },
    }


def _run(entities, parse_entities=()):
    from app.services.chatbot.lanes.business import run_fetch

    call, captured = _capturing_mcp(SALES_REPORT_HIT)
    run_fetch(_payload(entities, parse_entities), services=FetchServices(mcp_call=call))
    assert captured, "no MCP tool was called"
    assert captured[0][0] == TOOL, captured
    return captured[0][1]


CUSTOMER = {"uuid": CUSTOMER_UUID, "entity_type": "customer", "canonical_code": CUSTOMER_NAME}
BRAND = {"uuid": BRAND_UUID, "entity_type": "brand", "canonical_code": "MOCHA"}


def test_b7_near_miss_no_brand_entity_sends_no_brand_param() -> None:
    args = _run([CUSTOMER])
    assert "brand_ids" not in args, args


def test_b7_near_miss_a_customer_entity_is_never_sent_as_a_brand() -> None:
    args = _run([CUSTOMER])
    assert not args.get("brand_ids")


# M2 (review): production-shaped. Under order/sales the brand word is kept OFF the shared resolver
# (it is NOT in `matches`); the lane resolves it against the LIVE brand rows
# (`_resolve_outstanding_brand_ids` -> `outstanding_brand_ids` -> fetch.py crm_sales_report arm).
# Removing that arm must turn these red.


def _live_brand(session_factory, name: str) -> str:
    import uuid

    from app.models.product import Brand
    from app.services.company_scope import DEFAULT_COMPANY_ID

    db = session_factory()
    try:
        row = Brand(id=str(uuid.uuid4()), brand_code=f"ZZT{name.upper()}", brand_name=name, company_id=DEFAULT_COMPANY_ID)
        db.add(row)
        db.commit()
        return str(row.id)
    finally:
        db.close()


def _brand_turn(session_factory, monkeypatch, *, brand_entities, tag):
    entities = [
        {"raw": "ZZT Customer", "hint": "customer", "canonical_code": None, "current_message": True, "confident": True},
        *brand_entities,
    ]
    _seed_contact(session_factory, variables={})
    _result, captured = _run_turn(
        session_factory, monkeypatch,
        qf=_qf(**_SALES, entities=entities, domain_hint="order"),
        text_body="delivered sales for mocha september", msg_id=f"ZZT-b7-live-{tag}", attributes=[GRANT],
        matches={"ZZT Customer": {"uuid": CUSTOMER_UUID, "entity_type": "customer", "canonical_code": CUSTOMER_NAME}},
        mcp_response=SALES_REPORT_HIT,
    )
    return [a for n, a in captured if n == TOOL], ((_result.reply or {}).get("text") or "")


def test_b7_live_brand_word_not_in_resolver_matches_still_filters_the_total(session_factory, monkeypatch) -> None:
    brand_id = _live_brand(session_factory, "Mocha")
    calls, _reply = _brand_turn(
        session_factory, monkeypatch, tag="live",
        brand_entities=[{"raw": "Mocha", "hint": "brand", "canonical_code": "MOCHA", "current_message": True, "confident": True}],
    )
    assert len(calls) == 1, calls
    assert calls[0].get("brand_ids") == [brand_id], calls


def test_b7_live_near_miss_a_brand_word_matching_no_live_brand_is_said_never_dropped(session_factory, monkeypatch) -> None:
    """REPORT-UNIFY: a brand word that matches no brand is said, never run as an unfiltered total. Owner Q4 (a),
    27 Oct 2026: beside an applied filter (the customer this turn names) the total runs on that filter with a
    "Not applied:" line naming the word; never a total with the brand silently dropped."""
    _live_brand(session_factory, "Sorento")
    calls, reply = _brand_turn(
        session_factory, monkeypatch, tag="nomatch",
        brand_entities=[{"raw": "Zzzunknown", "hint": "brand", "canonical_code": None, "current_message": True, "confident": True}],
    )
    assert len(calls) == 1 and not calls[0].get("brand_ids"), calls
    assert calls[0].get("customer_ids"), calls
    assert "Not applied:" in reply and "Zzzunknown" in reply, reply
