# PLAN: low stock report asks for its filters before it runs (LOWSTOCK-FILTER-ASK)

Status: planning, behaviour card ASKED (2 Oct 2026), waiting on owner Q1-Q5. Track: feature (chatbot lane + route param; no migration expected). Lane LOWSTOCK-FILTER-ASK.
Card: `lowstock-filter-ask-behaviour-card.md` (holds the Step 1 trace with file:line).

## Owner report (2 Oct 2026)

"Sorento water tap low stock list" goes straight to a reorder run and returns the low stock
report with NO filters. We never collect the filters (category, supplier) nor ask whether the
user wants it grouped by supplier or by category.

Rule: never trigger a reorder run before the filters are settled; every failure ends in a clear
message (never-stuck rule).
