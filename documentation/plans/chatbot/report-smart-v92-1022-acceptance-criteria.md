# UAC: sales reports on parser v92 (REPORT-SMART-L round S1, 22 Oct)

Plan: `PLAN-report-smart-v92-1022.md`. Script: the owner's 21 Oct script (`laneboard/scripts/1816.md`), parser v92.

- AC1 (step 4). After a ranking ran, a bare refine ("ordered", "by amount", "delivered only", zh/ms/mixed
  paraphrases) re-runs the held ranking with its period, brand and category, whatever `state_changes` op the parser
  emits (`keep`, `set`, `switch_domain` onto the held domain). Never "Which period?".
- AC2 (domain stored). A sales figure ask answered through its required-field question stores the `sales` domain, so
  the next turn's State shows `sales` over the held report.
- AC3 (step 9). A refine right after a breakdown keeps the breakdown's count and period. Never "Which period? How
  many?".
- AC4 (real switch). A message naming another domain (stock, outstanding orders) still drops the held report.
- AC5 (step 6). A brand or category word held for a sales figure ask is never offered back as a customer pick.
- AC6 (step 5, parser). A whole ranking typed again with "dealer sales only" parses with the report kind in
  `order_status`; it re-runs or asks the missing choices, never a customer picker.
- AC7 (step 8, parser). A fresh ask in a new conversation carries no channel, measure, basis or axis the message did
  not say; a missing measure / basis is asked in one reply.
- AC8 (step 13, parser). "Top 10 dealers selling <product> ..." ranks customers with no channel filter.
- AC9 (counts). "How many customers / orders / products ..." runs the count measure; "customers per sales agent" ranks
  by the count.
- AC10 (compare). "... vs last month" / "compared with last year" runs `compare_to` previous_period / last_year; a
  month-by-month breakdown is never compared (says so).
- AC11 ("my sales"). A salesperson contact (linked CRM user with the salesperson role) asking "my sales ..." gets only
  their customers' sales (customers whose sales agent is linked to that contact). A dealer gets only its linked
  customers, as today. Staff with the sales report grant get the full report. An unknown contact gets the refusal it
  gets today. The sales_agent axis and agent filters need the grant.
- AC12 (rate limit). Unchanged: per contact, System Settings value; the reply says so when it trips.
- AC13 (no regressions). The 21 Oct v77 behaviour of the lane's tests holds; touched suites green except named
  pre-existing failures.
