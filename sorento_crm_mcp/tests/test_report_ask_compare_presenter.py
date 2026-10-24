"""REPORT-SMART-1021 step 4: a compared report prints the earlier figure and the change."""
from __future__ import annotations

from sorento_crm_mcp.catalog import CATALOG
from sorento_crm_mcp.presenters import _report_ask


def _body(**over):
    body = {
        "status": "ok", "message": None, "basis": "delivered", "basis_label": "delivered sales",
        "measure": "amount", "group_by": "sales_agent", "group_label": "Sales agent",
        "date_from": "2026-09-01", "date_to": "2026-09-30", "filters": [],
        "compare_to": "previous_period", "compare_from": "2026-08-02", "compare_until": "2026-08-31",
        "rows": [
            {"rank": 1, "name": "SA01", "qty": 10, "amount": 1000.0,
             "prev": {"qty": 5, "amount": 500.0}, "change_pct": 100.0},
            {"rank": 2, "name": "SA02", "qty": 6, "amount": 600.0,
             "prev": {"qty": 0, "amount": 0.0}, "change_pct": None},
        ],
        "more": 0, "total_count": 2,
        "total": {"qty": 16, "amount": 1600.0, "prev": {"qty": 14, "amount": 1400.0}, "change_pct": 14.29},
    }
    body.update(over)
    return body


def test_each_row_and_the_total_name_the_earlier_figure_and_the_change():
    lines = _report_ask(_body()).splitlines()
    assert "Compared with: 2 Aug 2026 to 31 Aug 2026" in lines, lines
    assert "1. SA01 RM 1,000.00, 10 pcs (before RM 500.00, +100.0%)" in lines, lines
    assert "2. SA02 RM 600.00, 6 pcs (before RM 0.00, new)" in lines, lines
    assert lines[-1] == "Total RM 1,600.00, 16 pcs (before RM 1,400.00, +14.3%)", lines


def test_a_fall_reads_negative_on_the_sort_measure():
    body = _body(measure="qty", group_by=None, rows=[],
                 total={"qty": 8, "amount": 900.0, "prev": {"qty": 10, "amount": 1000.0}, "change_pct": -20.0})
    assert _report_ask(body).splitlines()[-1] == "Total 8 pcs, RM 900.00 (before 10 pcs, -20.0%)"


def test_no_compare_reads_as_before():
    body = _body(compare_to=None, compare_from=None, compare_until=None,
                 rows=[{"rank": 1, "name": "SA01", "qty": 10, "amount": 1000.0}], total={"qty": 10, "amount": 1000.0})
    text = _report_ask(body)
    assert "before" not in text and "Compared" not in text, text


def test_the_catalog_passes_compare_to():
    spec = next(s for s in CATALOG if s.name == "crm_report_ask")
    assert "compare_to" in spec.query_params, spec.query_params
