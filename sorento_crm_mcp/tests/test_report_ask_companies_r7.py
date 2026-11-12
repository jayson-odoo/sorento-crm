"""Round 7 RED test (O-R2, presenter): a body carrying `companies` (2 or more) prints one line per company, "<Company name>
<figures as _ask_figures prints them>", right before the "Total" line; 1 entry or no key prints byte-for-byte what it did.

Pinned shape (flagged to the captain): `companies` = [{"name": str, "amount": number, "qty": number}, ...], the same
figure keys a row and the total carry.
"""
from __future__ import annotations

import pytest

from sorento_crm_mcp.presenters import _report_ask
from tests.test_report_ask_presenter import _body

TWO = [
    {"name": "Sorento", "amount": 1500.0, "qty": 40},
    {"name": "Mocha", "amount": 600.0, "qty": 15},
]
LINES = ["Sorento RM 1,500.00, 40 pcs", "Mocha RM 600.00, 15 pcs"]


def _sales_total(**over):
    return _body(group_by=None, group_label=None, rows=[], more=0, total_count=0, **over)


def _outstanding_total(**over):
    return _body(group_by=None, group_label=None, rows=[], more=0, total_count=0, basis="outstanding",
                 basis_label="outstanding orders", **over)


def _ranking(**over):
    return _body(more=0, total_count=3, **over)


def _before_total(text: str) -> list[str]:
    lines = text.split("\n")
    idx = next(i for i, ln in enumerate(lines) if ln.startswith("Total "))
    return lines[idx - len(LINES): idx]


@pytest.mark.parametrize("make", [_sales_total, _ranking, _outstanding_total], ids=["sales-total", "ranking", "outstanding-total"])
def test_two_companies_print_one_line_each_right_before_the_total(make) -> None:
    text = _report_ask(make(companies=TWO))
    assert _before_total(text) == LINES, f"O-R2: want {LINES} right before the Total line, got:\n{text}"


@pytest.mark.parametrize("make", [_sales_total, _ranking, _outstanding_total], ids=["sales-total", "ranking", "outstanding-total"])
def test_one_company_or_no_key_changes_nothing(make) -> None:
    plain = _report_ask(make())
    assert _report_ask(make(companies=TWO[:1])) == plain
    assert _report_ask(make(companies=[])) == plain
    assert _report_ask(make(companies=None)) == plain
    assert "Mocha" not in plain


def test_the_combined_total_line_is_unchanged_by_the_company_lines() -> None:
    text = _report_ask(_sales_total(companies=TWO))
    assert text.split("\n")[-1] == "Total RM 2,100.00, 55 pcs", text
