# PLAN: Order inquiry handover email prints the AutoCount SO document date as SO DATE (25 Sep 2026)

Status: REVIEW CLEAN 25 Sep 2026 (coder 2 rounds, reviewer kill test passed, 6 new tests), PR open, awaiting owner hand test + merge go. Small fix track (one service, two dict builders, no migration,
no auth change; one coder writes tests + fix, one reviewer, no browser pass - no screen
changes).
UAC: `oi-handover-so-date-autocount-25sep-acceptance-criteria.md`.
Lane: worktree `../sorento_crm-oi-so-date`, branch `fix/oi-handover-so-date` off
`origin/main` 76ade0ac2. Tests on private DB `sorento_osd_ci` via
`SORENTO_ENV_FILE=.env.ci-tests`.

## 1. Journey

Purchasing opens the order-inquiry handover email for SO422005 (OTM GROUP, CMG
CONSTRUCTION). The SO DATE column reads 24/09/2026 for every line, while the delivery date
reads 23/09/2026 and the OI header list on screen reads 18/09/2026 for the same order. The
owner's ruling (25 Sep 2026): SO DATE is the AutoCount sales order document date, which is
`sales_orders.order_date`, on the email and on every OI row surface alike.

## 2. Measured facts (origin/main 76ade0ac2, DB `sorento_ai_automation_0921`)

- `app/services/project_order_inquiry_service.py` `_handover_order_facts` (about line 3100)
  already outer-joins `SalesOrder` on `ProjectSalesOrder.so_id` but selects only
  `published_at` / `created_at` and builds `"so_date": published_at or created_at`.
- An adopted AutoCount order has `published_at` NULL by design (`app/models/project_so.py`
  `SO_STATUS_ADOPTED` comment), so the email falls through to `projects.sales_orders.created_at`
  = the date the CRM pulled the order, not the document date.
- SO422005 on the 0921 copy: status `adopted`, `published_at` NULL, project SO
  `created_at` 2026-09-23, `public.sales_orders.order_date` 2026-09-18.
- `serialize_rows` -> `_context_for` (about line 4750) builds the same
  `"so_date": order.published_at or order.created_at` for OI rows returned by `list_rows`.
- The OI header list and worklist already answer this correctly:
  `app/services/order_inquiry_header_service.py:88` `_SO_DATE = coalesce(SalesOrder.order_date,
  cast(published_at, Date), cast(created_at, Date))`, with the same expression in
  `order_inquiry_worklist_service.py`. The email and `serialize_rows` are the two drifted
  copies.

## 3. Change (one seam, two dict builders)

1. `_handover_order_facts`: add `SalesOrder.order_date` to the select (join already
   present); `"so_date": order_date or published_at or created_at`. `_handover_fmt_date`
   already formats a `date` or `datetime` to `DD/MM/YYYY`.
2. `_context_for`: the query joins `OrderInquiry` to `ProjectSalesOrder`; extend it to outer
   join `SalesOrder` on `ProjectSalesOrder.so_id` (or select `SalesOrder.order_date` beside
   the pair) and build `"so_date": order_date or published_at or created_at`. Keep the
   existing `date`-vs-`datetime` handling in the serializer (`_as_naive` at about line 9130
   consumes `so_date`; check that a `date` still passes through it, or normalise there).
3. Tests, in `tests/test_order_inquiry_handover_automation.py` (handover) and the existing
   `serialize_rows` test module (find it: `grep -ln "serialize_rows\|list_rows" tests/`):
   the AC list in the UAC. Test-first: write the reds, run them, then the fix.

Out of scope: the header list and worklist (already correct), the FE, the importer's
`so_date` read (`project_order_inquiry_reader.py`, a sheet cell, unrelated).

## 4. Follow-up named

`_rank_raised_rows` (`document_age` ranking input) still reads `published_at or created_at`
while `scm/priority.py` documents `document_age <- sales_orders.order_date`. Internal ranking
input, not printed; aligning it changes placement order, so it is its own lane.

## 5. Trigger for anything wider

If a third `published_at or created_at` copy turns up while doing this, list it in the PR
and fix it in the same commit only when it is an OI row surface; otherwise leave it and
name it.
