"""SALES-ACCOUNT-TYPE PR 2, Phase 2 RED tests: the reply (AT-28 presenter half) and the AI panel (AT-30).

Presenter: `sorento_crm_mcp.presenters._report_ask`. Agent: `app.services.chatbot.agent.loop.run_agent_turn` over the
real catalog entry of `crm_report_ask`. Invented figures only.
"""
from __future__ import annotations

import pytest

# The backend image ships no `sorento_crm_mcp` package ("Validate backend imports"): skip there, run where the MCP
# package is importable, as tests/chatbot/test_photo_rows_by_product.py does.
CATALOG = pytest.importorskip("sorento_crm_mcp.catalog").CATALOG
_report_ask = pytest.importorskip("sorento_crm_mcp.presenters")._report_ask

from tests._pg_fixture import blank_session  # noqa: E402
from tests.chatbot.agent._seed import seed_agent_contact  # noqa: E402
from tests.chatbot.agent.test_agent_round5c import Mcp, Provider, answer_call, asks, call  # noqa: E402

PERIOD = {"date_from": "2026-01-01", "date_to": "2026-12-31"}


def _body(group_by, rows: list[dict], **over):
    body = {
        "status": "ok", "message": None, "basis": "invoiced", "basis_label": "invoiced", "measure": "amount",
        "group_by": group_by, "group_label": (group_by or "").title(), "sort": "desc", **PERIOD, "filters": [],
        "rows": rows, "more": 0, "total_count": len(rows), "total": {"qty": 30, "amount": 1200.0},
    }
    body.update(over)
    return body


# --------------------------------------------------------------------------------------------- AT-28


def test_at28_a_month_split_opens_by_month_invoiced_never_top() -> None:
    rows = [{"rank": 1, "name": "2026-01", "qty": 10, "amount": 400.0}, {"rank": 2, "name": "2026-02", "qty": 20, "amount": 800.0}]
    text = _report_ask(_body("month", rows))
    assert text.splitlines()[0] == "By month, invoiced", text
    assert "Top" not in text, text


def test_at28_a_year_split_opens_by_year_delivered_never_top() -> None:
    rows = [{"rank": 1, "name": "2025", "qty": 10, "amount": 400.0}, {"rank": 2, "name": "2026", "qty": 20, "amount": 800.0}]
    text = _report_ask(_body("year", rows, basis="delivered", basis_label="delivered"))
    assert text.splitlines()[0] == "By year, delivered", text
    assert "Top" not in text, text


def test_at28_the_lines_under_a_month_split_stay_as_they_are() -> None:
    rows = [{"rank": 1, "name": "2026-01", "qty": 10, "amount": 400.0}]
    text = _report_ask(_body("month", rows, filters=[{"label": "Brand", "values": ["Cabana"]}]))
    lines = text.splitlines()
    assert lines[1] == "Brand: Cabana" and lines[2].startswith("Period: "), lines
    assert any(ln.startswith("Jan 2026") or ln.startswith("January 2026") for ln in lines), lines
    assert lines[-1].startswith("Total "), lines


def test_at28_every_other_axis_keeps_top_n() -> None:
    rows = [{"rank": 1, "name": "CABANA", "qty": 10, "amount": 400.0}, {"rank": 2, "name": "CERAMIC", "qty": 20, "amount": 800.0}]
    for axis in ("customer", "brand", "account_type"):
        text = _report_ask(_body(axis, rows))
        assert text.splitlines()[0].startswith("Top 2 "), (axis, text)


# --------------------------------------------------------------------------------------------- AT-30


def test_at30_the_catalog_lets_the_panel_pass_account_types() -> None:
    spec = next(s for s in CATALOG if s.name == "crm_report_ask")
    assert "account_types" in spec.query_params


def test_at30_the_account_filter_reads_as_asked() -> None:
    body = _body(None, [], filters=[{"label": "Account type", "values": ["4"]}])
    text = _report_ask(body)
    assert "Account type: 4" in text.splitlines(), text


@pytest.mark.parametrize("value", [["CABANA"], ["4"]])
def test_at30_the_agent_passes_an_account_type_word_or_number_through(value) -> None:
    spec = next(s for s in CATALOG if s.name == "crm_report_ask")
    props = {k: {"type": "array", "items": {"type": "string"}} if k == "account_types" else {"type": "string"}
             for k in (*spec.query_params, "contact_id", "space_id", "view")}
    catalog = {"crm_report_ask": {"description": "r", "inputSchema": {"type": "object", "properties": props, "required": []}}}
    envelope = {"result_type": "report_ask", "response": "Sales by invoiced\nAccount type: x\nTotal RM 100,400.00", "has_result": True}
    from app.services.chatbot.agent.loop import run_agent_turn

    with blank_session() as db:
        contact = seed_agent_contact(db, slugs=("order_management.orders.view",))
        mcp = Mcp(envelope)
        provider = Provider([
            asks(call("crm_report_ask", {"basis": "invoiced", "account_types": value, "dataset": "sales"}, "c1")),
            answer_call("Sales were RM 100,400.00.", figures=[{"value": "100,400.00", "call_id": "c1"}]),
        ])
        result = run_agent_turn(
            db, contact_respond_id=contact["respond_id"], text="sales for account type", provider=provider,
            mcp_call=mcp, catalog=catalog,
        )
    sent = [a for n, a in mcp.calls if n == "crm_report_ask"]
    assert sent and sent[0]["account_types"] == value, mcp.calls
    assert result.reply_text == "Sales were RM 100,400.00.", result.reply_text
