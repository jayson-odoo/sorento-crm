"""Small helpers the customer pick tests share (not a test module).

They lived in `test_sales_analysis_company_pick.py`, whose tests pinned the sales analysis company question
("Sorento or Mocha?"). REPORT-UNIFY (owner ruling Q1) retired that question with `crm_sales_analysis` for every
axis but the Yearly comparison: a sales ask is `crm_report_ask`, which reads the contact's own companies.
"""
from __future__ import annotations

from typing import Any

ANALYSIS = "crm_sales_analysis"


def _pick(position: int) -> dict[str, Any]:
    """The parser's declared answer to an open numbered question: the option at `position`."""
    return {"mode": "pick", "items": [], "picked": [position], "qty_for_all": None}


def _calls(captured: list[tuple[str, dict[str, Any]]], tool: str) -> list[dict[str, Any]]:
    return [args for name, args in captured if name == tool]
