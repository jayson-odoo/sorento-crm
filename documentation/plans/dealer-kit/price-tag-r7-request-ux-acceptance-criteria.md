# UAC - Price Tag Request UX Round 7

Plan: `documentation/plans/dealer-kit/PLAN-price-tag-r7-request-ux.md`

Each AC is verified in a real browser (agent-browser, dev server :3081) unless marked
`pytest` / `vitest`. Portal = logged in as the linked portal contact; CRM = marketing user.

## S1 Labels, width, columns, Design Ready, Proof tab

- AC-S1-1 Portal new-request form shows "Customer" (not Debtor) and "Need by" (not Needed
  by). Same on the portal read view, CRM detail Request tab, CRM listing header, designer
  header.
- AC-S1-2 At 1440px the form column is wider than 900px; at 375px it is single column with
  no horizontal page scroll (lines table scrolls inside itself).
- AC-S1-3 Lines table (portal form, portal read view, CRM Lines tab) has NO Alternatives and
  NO Accessories column. A request created before r7 with alternatives saved still opens
  and saves without error.
- AC-S1-4 Section/tab titled "Sales Order" on the portal form, portal read view and CRM
  detail. Empty state reads "No sales order files attached."
- AC-S1-5 Status pill for `proof_ready` reads "Design Ready" (CRM listing, CRM detail,
  portal). Designer CTA reads "Mark design ready".
- AC-S1-6 CRM detail has tabs Request, Lines, Sales Order only. No Proof tab at any status.
- AC-S1-7 `vitest`: `price-tag-status` label map snapshot; CRM detail renders three tabs.

## S2 Price mode + remarks

- AC-S2-1 Portal form shows "Price" segmented control List price / Selling price under
  Promotion; default List price on a new request.
- AC-S2-2 With no promotion selected, Selling price is disabled and its tooltip says a
  promotion is required. Picking a promotion enables it. Clearing the promotion while
  Selling is chosen flips the control back to List price.
- AC-S2-3 No per-line "Promo price" switch anywhere on the form.
- AC-S2-4 Each line has a Remarks input; value survives Save Draft, reload, Submit; shows
  on portal read view, CRM Lines tab and the designer LinesRail (truncated, full text on
  hover).
- AC-S2-5 `pytest`: `PUT` header with `price_mode=selling` and `promotion_id=None` on
  submit -> 422 `PRICE_MODE_NEEDS_PROMOTION`. With a promotion -> 200 and every line's
  `show_promo_price` is True; switching back to `list` sets every line False.
- AC-S2-6 `pytest`: migration `ptag_0005` upgrade + downgrade round-trips; existing rows get
  `price_mode='list'`.
- AC-S2-7 `pytest`: `GET` request detail (portal + CRM) carries `price_mode` and each line's
  `remarks` (response_model declares both).
- AC-S2-8 Designer: a request in Selling mode with a promotion renders the promo price on a
  `price_badge`; in List mode the same request renders the list price. No canvas code
  change needed to pass.

## S3 Auto-assign on submit

- AC-S3-1 `pytest`: with an active `form_sla_configs` row for `price_tag_request` whose
  tier-1 team has one member, portal submit leaves the request with
  `assigned_to_id = that member`, `status = designing`, and an SLA tracker exists.
- AC-S3-2 `pytest`: with no active config, submit leaves `status = new`,
  `assigned_to_id = None` (Claim path unchanged).
- AC-S3-3 `pytest`: if the assignment block raises, submit still succeeds with
  `status = new` (logged, not propagated).
- AC-S3-4 Browser: submit from the portal; CRM listing shows the request as Designing,
  assigned to the configured person; detail shows no Claim button; "Open designer" works.

## S4 Portal design preview

- AC-S4-1 Portal read view of a `proof_ready` request shows "Design preview" rendering the
  marketing design (images, price badge, product block), not name/code text only.
- AC-S4-2 Zoom control offers Fit, 25, 50, 75, 100, 150, 200 percent; default Fit; the
  preview scrolls inside its container at 200 percent; page body never scrolls
  horizontally.
- AC-S4-3 `pytest`: `GET /submissions/price_tag_request/{id}/design` -> 200 for the owning
  contact at `proof_ready|changes_requested|approved|ready`; 404 at `new|designing|draft`;
  404 for another contact's request.
- AC-S4-4 The preview is also shown at `approved` and `ready` (the salesperson can look at
  what they approved).
- AC-S4-5 `vitest`: `PriceTagProofViewer` zoom levels and Fit behaviour.

## S5 Auto-export on approve

- AC-S5-1 `pytest`: transition `proof_ready -> approved` enqueues one tag-sheet export
  (`UserDownload` row created, kind `dealer_kit_tag_sheet_pdf`, source = the request).
- AC-S5-2 `pytest`: an approve where the export precondition fails (no `page_id`) still
  approves; the export failure is logged.
- AC-S5-3 Browser (worker running): approve on the portal; within the worker's run the
  portal gear "Download PDF" becomes enabled and downloads a PDF; before that it reads
  "PDF is being generated".
- AC-S5-4 CRM "Export PDF" still available at approved/ready for a re-export.

## S6 AI extract sales order lines

- AC-S6-1 Portal form Sales Order section shows "Extract lines with AI" once a file is
  attached (or dropped pre-draft). Opens the shared AI extract dialog.
- AC-S6-2 Result table lists each extracted product with code, description, qty, unit
  price, and a match state: matched product / matched set / Not found.
- AC-S6-3 Apply appends one line per matched row with qty (default 1) and remarks from the
  extracted notes; Not found rows are skipped and named in a toast. Unit price is never
  saved.
- AC-S6-4 `pytest`: `get_form_schema("price_tag_request")` returns the two header fields;
  `_form_has_line_items("price_tag_request")` is True.
- AC-S6-5 `vitest`: apply handler maps extracted rows to form lines; unmatched skipped.

## Regression

- AC-R-1 Existing pytest for price tag transitions, set guard, debtor scoping still green.
- AC-R-2 Existing vitest in `dealer-kit/**` and `portal/**` still green.
- AC-R-3 `alembic heads` = one head before PR.
