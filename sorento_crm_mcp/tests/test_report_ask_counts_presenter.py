"""REPORT-SMART-1021 step 3: a count measure reads as its count first, then the money.

"How many dealers sell this product" answers with a number of customers, not monthly totals.
The route body carries `count` on the total (and every row) when `measure` is a count.
"""
from __future__ import annotations

from sorento_crm_mcp.catalog import CATALOG
from sorento_crm_mcp.presenters import _report_ask

PERIOD = {"date_from": "2026-01-01", "date_to": "2026-09-30"}
PRODUCT = [{"key": "product", "label": "Product", "values": ["ZZTCNT-1"]}]


def _body(**over):
    body = {
        "status": "ok", "message": None, "basis": "delivered", "basis_label": "delivered sales",
        "measure": "customers", "group_by": None, "group_label": None, **PERIOD, "filters": PRODUCT,
        "rows": [], "more": 0, "total_count": 0, "total": {"qty": 17, "amount": 1700.0, "count": 2},
    }
    body.update(over)
    return body


def test_a_count_total_says_the_count_first():
    text = _report_ask(_body())
    lines = text.splitlines()
    assert lines[-1] == "Total 2 customers, RM 1,700.00, 17 pcs", text
    assert "Product: ZZTCNT-1" in lines and "Period: 1 Jan 2026 to 30 Sep 2026" in lines, text


def test_one_reads_singular():
    text = _report_ask(_body(measure="orders", total={"qty": 3, "amount": 30.0, "count": 1}))
    assert text.splitlines()[-1] == "Total 1 order, RM 30.00, 3 pcs", text


def test_a_count_ranking_prints_each_rows_count():
    text = _report_ask(_body(
        group_by="sales_agent", group_label="Sales agent", total_count=2,
        rows=[
            {"rank": 1, "name": "SA01", "qty": 15, "amount": 1500.0, "count": 2},
            {"rank": 2, "name": "SA02", "qty": 2, "amount": 200.0, "count": 1},
        ],
    ))
    lines = text.splitlines()
    assert lines[0] == "Top 2 sales agents by customers, delivered sales", text
    assert "1. SA01 2 customers, RM 1,500.00, 15 pcs" in lines, text
    assert "2. SA02 1 customer, RM 200.00, 2 pcs" in lines, text


def test_a_sum_measure_reads_as_before():
    text = _report_ask(_body(measure="amount", total={"qty": 17, "amount": 1700.0}))
    assert text.splitlines()[-1] == "Total RM 1,700.00, 17 pcs", text


def test_the_catalog_names_the_count_measures():
    spec = next(s for s in CATALOG if s.name == "crm_report_ask")
    blob = repr(spec)
    for word in ("customers", "orders", "products"):
        assert word in blob, word
