# PLAN: low stock report asks for its filters before it runs (LOWSTOCK-FILTER-ASK)

Status: planning (Step 1 trace in progress). Lane LOWSTOCK-FILTER-ASK.

## Owner report (2 Oct 2026)

"Sorento water tap low stock list" goes straight to a reorder run and returns the low stock
report with NO filters. We never collect the filters (category, supplier) nor ask whether the
user wants it grouped by supplier or by category.

Rule: never trigger a reorder run before the filters are settled; every failure ends in a clear
message (never-stuck rule).
