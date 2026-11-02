"""Phase 2 RED tests - the MCP side of the account type filter and split (lane SALES-ACCOUNT-TYPE, AT-19).

`documentation/plans/sales/sales-account-type-acceptance-criteria.md` AT-19: the `crm_report_ask` tool lists
`account_types`, its text names `group_by` `account_type`, and the presenter prints "Account type: 4", the plural
"account types" and the refused message verbatim.
"""
from __future__ import annotations

from sorento_crm_mcp.catalog import CATALOG
from sorento_crm_mcp.presenters import _report_ask

PERIOD = {"date_from": "2026-09-01", "date_to": "2026-09-30"}
REFUSED = "No account type 9. Account types: 1, 3, 4, PROJECT."


def _spec():
    return next(s for s in CATALOG if s.name == "crm_report_ask")


def _body(**over):
    body = {
        "status": "ok", "message": None,
        "basis": "invoiced", "basis_label": "invoiced sales", "measure": "amount",
        "group_by": None, "group_label": None,
        **PERIOD,
        "filters": [{"key": "account_type", "label": "Account type", "values": ["4"]}],
        "rows": [], "more": 0, "total_count": 0,
        "total": {"qty": 10, "amount": 2100.0},
    }
    body.update(over)
    return body


def test_at_19_the_catalog_lists_account_types():
    assert "account_types" in set(_spec().query_params)


def test_at_19_the_tool_text_names_the_param_and_the_axis():
    text = " ".join(_spec().description.split())
    assert "account_types" in text, text
    assert "account_type" in text.replace("account_types", ""), text


def test_at_19_the_presenter_prints_the_account_filter_as_a_fact_line():
    lines = _report_ask(_body()).split("\n")
    assert "Account type: 4" in lines, lines


def test_at_19_a_split_by_account_type_reads_plural_account_types_in_its_head():
    rows = [
        {"rank": 1, "name": "CABANA", "qty": 6, "amount": 1500.0},
        {"rank": 2, "name": "(blank)", "qty": 4, "amount": 600.0},
    ]
    body = _body(filters=[], group_by="account_type", group_label="Account type", rows=rows, more=3, total_count=5)
    head = _report_ask(body).split("\n")[0]
    assert head == "Top 2 of 5 account types by invoiced sales", head


def test_at_19_a_refused_reply_prints_the_message_alone_with_no_figure():
    out = _report_ask(_body(status="refused", message=REFUSED, rows=[], total={"qty": 0, "amount": 0}))
    assert out == REFUSED, out
    assert "RM" not in out
