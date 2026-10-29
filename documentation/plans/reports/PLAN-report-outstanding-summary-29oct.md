# PLAN: REPORT-OUTSTANDING-SUMMARY (29 Oct 2026)

Status: Build done, in review. Track: small fix track (no migration), but the diff loosens one #1922 access gate
(pending delivery without the reveal), so security-reviewer runs.

Restore the outstanding SUMMARY shape (totals, by location, by customer or product, list offer) inside the unified
report engine (`crm_report_ask`), after #1922 REPORT-UNIFY reduced an outstanding answer to a single total. The old
`crm_outstanding_report` tool is NOT restored. Behaviour card: `report-outstanding-summary-behaviour-card.md`.

## Owner rulings (29 Oct)

- Q1 (a): keep asking the kind, but "outstanding" means ONLY undelivered orders (SO) or pending delivery (DO). The
  question offers only the kinds the contact may see; one kind = run it directly (#b6e9). Unpaid invoices only when
  the user names them.
- Q2: summary with default group-bys (by location, then by customer, or by product when a customer is named), totals,
  list offer; RM on the Outstanding line. A group-by or filter the user names replaces the defaults.
- Q3: summary when a product or customer is named.
- Access (a), "minimise change management": the pre-#1922 split. SO needs `sales_orders.outstanding` (or a salesperson's
  own book, Q6 kept); DO needs no reveal. Lane rule: other #1922 outstanding differences go back to pre-#1922 unless
  the owner asked for them (listed in the PR report for the owner).

## Build

| Part | Where |
| --- | --- |
| `summary` on the route: document count, totals, date range, `groups` (default axes or the named one); a named location drops By location | `app/api/v1/order_management/report_ask.py`, `app/services/reports/ask.py` `outstanding_summary`, `app/schemas/report_ask.py` |
| SO dataset: `order_day` (SO date) and `ordered_qty` (whole qty of lines still owing) | `app/services/reports/datasets/sales_order_lines_ask.py` |
| `delivery_order` grouping on pending delivery (the DO list) | `reports/ask.py` CATALOGUE |
| Pending delivery without the reveal: office staff (all) or linked contact (own customers); unknown contacts refused | `contact_asker.pending_delivery_open`, route, `lanes/business/__init__.py` `sales_figure_decision`, `engine.py` grant seam |
| Kind question: two kinds, access-aware, single kind unasked; unpaid named only | `lanes/business/report_ask.py` (`ASKED_KINDS`, `NAMED_KINDS`, `outstanding_kinds`, `settle(kinds=)`, `as_basis_answer`) |
| Presenter: pre-#1922 line names, `*_By <axis>_*` groups, DO / SO list offer | `sorento_crm_mcp/presenters.py` `_ask_summary` |
| DO list offer arms a pick; the pick re-runs the held ask by delivery order | `lanes/business/fetch.py` `_LIST_OFFERS`, `report_ask.py` `DO_LIST`, `list_pick_kind` |

## Tests (red first)

- `tests/test_report_outstanding_summary_route.py` (route: shape, R13 axes, period, open lines, no-summary cases, DO
  list, pending delivery access, named axis, named location).
- `sorento_crm_mcp/tests/test_report_ask_outstanding_summary.py` (presenter shape, prod turn pin, caps, empty, named axis).
- `tests/chatbot/test_report_outstanding_summary_lane.py` (lane: #b6e9 DO-only contact runs pending delivery directly,
  two-kind question, DO list pick, SO list kept, unknown contact refused, named axis keeps summary and offer).
- Existing kind-question tests updated to the two-option question (owner ruling).
