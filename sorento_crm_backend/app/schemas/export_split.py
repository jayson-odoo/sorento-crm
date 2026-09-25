"""The workbook split ANY export accepts (PLAN-low-stock-export-split-25sep, "second case"
of PLAN-stock-debt-filters-totals-export-24sep R5/A7): None / Supplier / Category /
Supplier x Category. One `Literal`, shared by `stock_debt.py` and `scm_order_summary.py` so
neither declares its own copy that could drift from the other.
"""
from __future__ import annotations

from typing import Literal

#: One sheet for `none`. `app.services.scm.workbook_split.SPLIT_VALUES` is the runtime
#: tuple of the same four values.
ExportSplit = Literal["none", "supplier", "category", "supplier_category"]
