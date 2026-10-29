"""REPORT-OUTSTANDING-SUMMARY item 4 (owner 29 Oct, restore pre-#1922): an outstanding ask is never asked "Sorento or
Mocha?", "By quantity or by amount?" or "How many?". Pre-#1922 the outstanding report had no company, measure or count
question: it ran over the contact's own companies and listed every row."""
from __future__ import annotations

from typing import Any

import pytest

from app.services.chatbot.lanes.business import report_ask

COMPANIES = [["c-sorento", "Sorento", "SRT"], ["c-mocha", "Mocha", "MCH"]]


def _outstanding(**over: Any) -> dict[str, Any]:
    verdict = {
        "order_status": "outstanding", "domain_hint": "order", "intent_hint": "check_order", "entities": [],
        "basis": "pending_delivery", "group_by": None, "top_n": None, "measure": None, "rank_direction": None,
        "date_filter_start": None, "date_filter_end": None,
    }
    verdict.update(over)
    return report_ask.by_capability(verdict, seam=False)


@pytest.mark.parametrize("kind", ["outstanding", "pending_delivery"])
def test_a_two_company_contact_is_not_asked_the_company_on_an_outstanding_total(kind) -> None:
    outcome, line = report_ask.settle(None, _outstanding(basis=kind), [], companies=COMPANIES)
    assert line is None and outcome is not None, line
    assert outcome.done, (outcome.reply, outcome.slot)
    assert "company" not in (outcome.extras.get("args") or {}), outcome.extras


def test_an_outstanding_ranking_asks_neither_the_measure_nor_how_many() -> None:
    """"top customers pending delivery": every row, sorted by quantity as the old report ranked (R10), no question."""
    outcome, line = report_ask.settle(
        None, _outstanding(group_by="customer", rank_direction="top", by_words="customers"), [], companies=COMPANIES[:1],
    )
    assert line is None and outcome is not None and outcome.done, (line, outcome and outcome.reply)
    args = outcome.extras.get("args") or {}
    assert args.get("measure") == "qty", args


# ---------------------------------------------------------------- item 1: a dealer's location on outstanding


def _warehouse_entity() -> dict[str, Any]:
    return {"raw": "BRW", "hint": "warehouse", "canonical_code": None, "current_message": True, "confident": True}


def test_a_dealers_location_word_stays_a_location_on_an_outstanding_ask() -> None:
    """Item 1 (owner 29 Oct, as before #1922): the seam that strips a dealer's location words leaves an outstanding ask's."""
    parse = _outstanding(entities=[_warehouse_entity()])
    assert report_ask.dealer_location_words(parse) == parse
    assert not report_ask._dealer_outside(parse, "location")
    assert not report_ask._dealer_outside(parse, None)


def test_a_dealers_location_word_is_still_refused_on_a_sales_ask() -> None:
    parse = report_ask.by_capability({
        "order_status": "sales_report", "domain_hint": "order", "intent_hint": "check_order",
        "entities": [_warehouse_entity()], "basis": "delivered", "group_by": None,
    }, seam=False)
    assert report_ask._dealer_outside(report_ask.dealer_location_words(parse), None)


# ---------------------------------------------------------------- item 8: the shared resolver's products, exactly


import uuid as _uuid  # noqa: E402


def _row(code: str) -> dict[str, Any]:
    return {"entity_type": "product", "uuid": str(_uuid.uuid4()), "code": code, "canonical_code": code}


def _product_parse(*codes: str) -> dict[str, Any]:
    entities = [{"raw": c, "hint": "product", "canonical_code": c, "current_message": True, "confident": True} for c in codes]
    return _outstanding(entities=entities)


def test_an_outstanding_ask_sends_the_resolvers_rows_never_a_code_prefix() -> None:
    """Item 8 (owner 29 Oct): the products the shared resolver matched, by id, as the pre-#1922 report took its exact
    codes; never the shared prefix the route would widen to every sibling (SRT5733 -> SRT5733-A, -B, ...)."""
    rows = [_row("SRT5733-WH")]
    outcome, line = report_ask.settle(None, _product_parse("SRT5733-WH"), rows, companies=COMPANIES[:1])
    assert line is None and outcome is not None and outcome.done, (line, outcome and outcome.reply)
    args = report_ask.route_args(outcome)
    assert args.get("product_ids") == [rows[0]["uuid"]] and "product_code" not in args, args


def test_an_outstanding_ask_over_unrelated_codes_runs_them_all_with_no_question() -> None:
    rows = [_row("SRT5733-WH"), _row("CBN-200")]
    outcome, line = report_ask.settle(None, _product_parse("SRT5733-WH", "CBN-200"), rows, companies=COMPANIES[:1])
    assert line is None and outcome is not None and outcome.done, (line, outcome and outcome.reply)
    assert sorted(report_ask.route_args(outcome)["product_ids"]) == sorted(r["uuid"] for r in rows)


# ---------------------------------------------------------------- item 9: location word and period, as before #1922


def test_an_unknown_location_word_on_an_outstanding_ask_is_left_out_not_said(monkeypatch) -> None:
    """Pre-#1922 (`_resolve_report_product_and_location`): a location word that resolves to no warehouse narrows
    nothing and is not answered with "I don't know 'X' as a location." (a #1922 side effect, owner 29 Oct item 9)."""
    from app.services.chatbot.lanes.business import services as business_services

    monkeypatch.setattr(business_services, "resolve_warehouse_token", lambda db, token: [])
    outcome, line = report_ask.settle(object(), _outstanding(entities=[_warehouse_entity()]), [], companies=COMPANIES[:1])
    assert line is None and outcome is not None and outcome.done, (line, outcome and outcome.reply)
    assert "warehouse_codes" not in report_ask.route_args(outcome)
