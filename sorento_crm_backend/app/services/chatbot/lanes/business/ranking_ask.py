"""The one place that picks the next clarify question for a ranking (owner ruling, 4 Oct 2026).

The sales ranking (`report_ask`, every item, category and other ranking since REPORT-SMART-L)
asks the metric first and then the basis, and defaults neither. The lane keeps its own binding
(what counts as settled, where the answer lands); this decides only which line comes next.
No imports.
"""
from __future__ import annotations

METRIC_LINE = "By quantity or by amount?"
#: The sales ranking (`crm_report_ask`) has all three bases.
RANKING_BASIS_LINE = "Delivered, ordered or outstanding?"


def next_question(*, metric_settled: bool, basis_settled: bool, basis_line: str) -> tuple[str, str] | None:
    """`(axis, line)` for the first unsettled one of the metric then the basis; None when both
    are settled. `basis_line` is the lane's own basis wording."""
    if not metric_settled:
        return "metric", METRIC_LINE
    if not basis_settled:
        return "basis", basis_line
    return None
