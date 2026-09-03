# UAC: SCM loading plan feedback batch, 2 Sep 2026

**Status:** APPROVED 2 Sep 2026 after the markup round (plan-owned statement, Send in
the gear, third stack slot, Outline yes, Lines tab). Plan: `PLAN-scm-loading-plan-feedback-2sep.md`.
Every AC is checked in a real browser on the lane's dev server (agent-browser, sidebar navigation
from `/`) and, where a backend rule is named, by a pytest on Postgres. Tags: `[FE]` frontend,
`[BE]` backend, `[E2E]` real clicks FE to BE to DB, `[T]` pytest / vitest.

## Journey

Actor: purchasing (Ms Tee). Arrives from the sidebar: Supply Chain > Planning > Loading Plan.

1. The list shows her plans. The row itself opens the plan. A "..." menu on the row holds
   Cancel and Delete; Delete is greyed with its reason once a request has gone out. Both run
   as a countdown she can stop from the toast, no dialog.
2. Upload opens "Plan a container". She picks the supplier, an optional cut-off, and the
   document. Test reads the file and tells her how many invoice blocks and lines it found, how
   many codes are unknown, and warns when the file's own letterhead names a different supplier
   than the one she picked.
3. Confirm starts ONE plan and applies the file INTO it: every row the upload writes belongs
   to this plan, every block of the file counted as one statement. The plan opens.
4. The plan is a record: title, status, a subtitle naming ITS statement (the stock list's
   date, the invoice file and block count, or "No file"). A later upload for the same supplier
   never changes this plan. Toolbar: pager, gear, Save, Back. The gear holds the same actions
   as the row menu, Send to supplier included.
5. Three tabs: **Lines** (default: stat cards and the What-to-ask table), **Supplier codes**
   with a count of codes still unknown, **Sent** with a count of requests sent.
6. Supplier codes: unknown codes first, each with a product-or-set picker. Picking keeps the row
   where it is, shows what she picked, and offers Undo. Dismiss behaves the same way. Below,
   every code this supplier has ever been matched on, how it was matched and when, with Forget.
   This is the supplier's memory and it is consulted on her next upload.
7. A manual match also records that this supplier supplies that product, so the product enters
   the supplier's plan universe, and the product's own Suppliers tab shows the supplier's code.
8. Lines: every candidate (supplier link, this plan's file, remembered code, set driver); those with open demand ranked on top. Products the supplier holds that nobody currently needs sit in
   one collapsed line under the ranked rows, expandable.
9. Send. The Sent tab logs it.

Derived, never asked: the supplier codes come off the file, the memory off past matches, the
block count off the file, the statement date off the snapshot, the product-supplier link off
the match.

## A. Row actions, one action set (S1)

- **AC-A1** `[FE]` `/scm/loading-plan` rows carry a "..." cell (`RowActionsMenu`) and no bare
  icon buttons. Items in order: Send to supplier, Cancel plan, then a separator, then Delete plan
  in red.
- **AC-A2** `[FE]` The plan record's gear (`DetailActions`) renders the SAME array from one
  `usePlanActions(plan)` hook: View uploaded list, Refresh matching, Refresh suggestion, Copy
  link, Download XLSX, Download PDF, Send to supplier, Change cut-off, Cancel plan, separator,
  Delete plan. The toolbar right cluster is pager, gear, Save (N), Back to loading plans; no
  standalone Send button remains (captain's markup, 2 Sep). Send to supplier from the row menu
  opens the same Send dialog for that plan.
- **AC-A3** `[E2E]` Cancel plan from a row parks a 5s deferred action: the row dims
  (`data-pending`), a toast counts down with Cancel; letting it lapse sets status Cancelled and
  the row leaves the Active filter; pressing Cancel in the toast leaves the plan untouched.
- **AC-A4** `[E2E]` Delete plan from a row parks a 10s deferred action; on commit the plan is
  hard-deleted with its edits and the row is gone; stopping it keeps the row.
- **AC-A5** `[FE]` On a plan with a sent request, Delete plan is disabled in both menus with the
  reason "Sent plans are cancelled, not deleted". Cancel plan stays enabled on a sent plan and
  is disabled only on a cancelled one ("Already cancelled").
- **AC-A6** `[FE]` Nothing under `scm/loading-plan/` imports `ConfirmDeleteDialog` or a raw
  `AlertDialog`: Cancel and Delete are deferred countdowns and reach for no dialog at all.
  The three DATA-LOSS prompts (Refresh suggestion with edits present - "Drop your N typed
  quantities?" - a new cut-off, and leaving with typed quantities) keep asking, through the
  SHARED `ConfirmActionDialog`, because they are data-loss questions rather than destructive
  record actions (the D7 carve-out). A local copy of that dialog is not an alternative: one
  component, one place for its behaviour to live (SF-2, 3 Sep).
- **AC-A7** `[BE][T]` The deferred-action engine knows `loading_plan.cancel` (5s) and
  `loading_plan.delete` (10s); a delete parked on a plan that has `sent_at` is refused at park
  time with 409 `plan_sent`; a cancel on a cancelled plan is refused with 409 `plan_cancelled`.

## B. Tabs on the record (S2)

- **AC-B1** `[FE]` `/scm/loading-plan/{id}` renders `Tabs` (`variant="line"`) in order Lines
  · Supplier codes (N) · Sent (N); N = unknown codes still needing a decision, and requests
  sent. A zero count renders as "Supplier codes" / "Sent" with no badge.
- **AC-B2** `[FE]` Lines is the default tab and holds the stat cards plus the What-to-ask
  card (Table / Schedule toggle unchanged). The tab is in the URL (`?tab=codes`, `?tab=sent`)
  and survives reload and prev/next navigation.
- **AC-B3** `[FE]` The toolbar (title, subtitle, status badge, pager, gear, Save, Back)
  sits above the tabs and does not move between tabs. Save (N) and Send to supplier act on the
  Lines tab's edits from any tab.
- **AC-B4** `[FE]` Every tab renders when empty with an explicit empty state: "Every code on
  file is matched" (codes), "Nothing sent yet" plus the Send button (sent).
- **AC-B5** `[FE]` Tab strip scrolls, never wraps, at 375px; the record stays usable at 375px
  and 1280px.

## C. Matching stays put, with Undo, and the memory is visible (S3)

- **AC-C1** `[E2E]` Picking a product or set on an unknown code writes the alias as today and
  the row STAYS in place showing the chosen product (code, name) with an "Undo" link; it does
  not vanish and no other row moves. Undo deletes the alias (existing DELETE) and the row shows
  the picker again.
- **AC-C2** `[E2E]` Dismiss behaves the same: the row stays, reads "Dismissed" with Undo, and
  Undo restores the picker.
- **AC-C3** `[FE]` The "Supplier codes" tab body is two groups: "Needs a decision (N)" on top
  (unknown codes: Code, Supplier says, Packed, Product picker, Dismiss), then "Remembered (M)":
  every alias for this supplier (Code, Matched to product or set, How: Manual / Exact after
  separators / Same tokens / Trap size dropped / Dismissed, When, by whom) with a Forget action.
  Decided-this-visit rows join Remembered on the next load, not immediately.
- **AC-C4** `[FE]` Forget on a remembered row is a 5s deferred action (toast countdown), after
  which the ladder re-runs and the code reappears under Needs a decision if nothing resolves.
- **AC-C5** `[BE][T]` `GET /api/v1/scm/supplier-code-aliases?supplier_id=` returns every alias
  for the supplier, dismissed included, with `matched_by`, `source`, `created_at`, `created_by`
  (a name, never a UUID), `product_code` / `product_name` / `set_code` / `set_name` (the flat
  shape the endpoint already ships, kept on purpose); ordered `created_at desc`, newest first.
- **AC-C6** `[BE][T]` The next stock list or proforma upload for the same supplier resolves a
  remembered code without asking again (rung 0 of the ladder), and a code remembered under
  supplier A is NOT applied to supplier B.
- **AC-C7** `[BE][T]` "Needs a decision" is scoped to THIS plan: `GET
  /supplier-code-aliases/unmatched?plan_id=` returns only unknown codes on rows stamped with
  the plan (stock list rows or invoice lines); `POST /supplier-code-aliases/rematch
  {plan_id}` rebinds only those rows. A "No file" plan returns an empty list even when the
  supplier has a snapshot from another plan (the ROYAL MIRROR case).

## D. The match reaches master data (S4)

- **AC-D1** `[BE][T]` A MANUAL match to a product (not a set) upserts `product_suppliers`
  (product, supplier) when no link exists: `standard_lead_time_days` = the most common lead
  time among the supplier's existing links (ties: the larger), `is_primary_supplier` false. A
  supplier with NO existing links gets no row (there is no honest lead time to write); the plan
  universe still includes the product through the alias (AC-D3). An automatic (ladder) match
  never creates a link.
- **AC-D2** `[E2E]` Product detail > Suppliers tab shows a "Their code" value per supplier row,
  read from the alias table (no column added to `product_suppliers`); blank renders per
  ADR 1e. `GET /procurement/product-suppliers/product/{id}` and `ProductSupplierResponse` carry
  `supplier_item_code` (asserted in a pytest, since `response_model` drops undeclared fields).
- **AC-D3** `[BE][T]` The container-request universe for a supplier includes every product
  or set that has a non-dismissed alias for that supplier, in addition to `product_suppliers`
  links and the statement on file.
- **AC-D4** `[BE][T]` Undo of a manual match (alias delete) does NOT delete the
  `product_suppliers` link it created; the link is sourcing data and is removed from the
  supplier's own screen.

## E. Held-but-not-needed rows fold (S5)

- **AC-E0** `[BE][T]` Membership and placement are separate: the candidate set is links ∪
  this plan's statement ∪ non-dismissed aliases ∪ set drivers; a candidate with open demand is
  a ranked row, a candidate without is a folded row; a product with open demand and none of
  the four memberships is absent (pytest seeds one of each).

- **AC-E1** `[FE]` Rows with `has_demand: false` leave the ranked table body and sit under one
  line beneath it: "N products held with no open demand" with a chevron; expanded, they render
  in the same columns, muted, rank "-", Need "No open demand", exactly as today.
- **AC-E2** `[FE]` Collapsed is the default on every load; the state is per session (not
  persisted). The line is absent when N = 0.
- **AC-E3** `[FE]` The stat cards, Save (N), Send and the xlsx/PDF are unaffected: a typed qty
  on a folded row still counts as an edit and still ships.

## F. A plan owns its statement (S6)

- **AC-F1** `[BE][T]` Migration 454 adds `loading_plan_id` (UUID, FK `scm.loading_plan.id` ON
  DELETE SET NULL, nullable, indexed) to BOTH `scm.proforma_invoice` and
  `scm.supplier_inventory`, and re-keys the stock snapshot's unique index to `(company,
  supplier, coalesce(loading_plan_id, nil), item_code)`. Existing rows keep NULL. Single
  alembic head.
- **AC-F2** `[E2E]` Confirm in "Plan a container" creates the plan FIRST, then applies the
  file with `loading_plan_id`, then opens the plan. A failing apply deletes the just-created
  plan and shows the verdict error; no empty plan is left behind (pytest + browser with a
  broken file).
- **AC-F3** `[BE][T]` `supplier_inventory_service.apply(..., loading_plan_id)` replaces only
  that plan's rows; the standalone upload page (no plan id) keeps replacing the supplier-wide
  snapshot. `proforma_invoice_service.apply(..., loading_plan_id)` stamps every created or
  revised invoice.
- **AC-F4** `[BE][T]` The container-request build reads holdings from the plan's OWN rows:
  stock-list rows for `stock_list`, ALL bound invoices (current revision, summed per product
  or set) for `proforma`, nothing for `none`. The holding cell reads "PI dd/mm/yyyy · 5
  blocks" and the drill lists the per-block split (block, pi_number, qty). A legacy plan with
  no stamped rows still resolves through today's supplier-wide rule.
- **AC-F5** `[E2E]` Uploading the committed fixture `2026-7-31 SORENTO 预装清单.xlsx` (five
  stacked blocks) lands on ONE plan whose Packed figures are the sums across blocks
  (SRTWC8354-SH-250 = 100 = 60 + 40) and whose subtitle names the file and "5 blocks".
  Confirming the same file again for the same supplier creates a second plan bound to the R2
  invoices; the first plan still reads its own.
- **AC-F6** `[E2E]` Uploading a newer stock list for the same supplier from a NEW plan leaves
  an older open plan's Packed figures, codes tab and subtitle unchanged (supersedes p4
  AC-A17). A "No file" plan for a supplier that has rows under another plan shows no codes and
  no Packed figures.
- **AC-F7** `[BE][T]` `document_label` is computed from the plan's own rows: "Stock list
  dd/mm/yyyy", "Proforma invoice <pi_number>" for one bound invoice, "Proforma invoice <file
  stem> · N blocks" for several, "No file" for none. Never re-looked-up from the supplier.

## G. The statement in use is named, and a wrong supplier is caught (S7)

- **AC-G1** `[BE][T]` `record_dict` exposes `statement_as_of` (the plan rows' `as_of` or max
  invoice date; null for "No file"). A "No file" plan's label stays "No file" and it reads no
  statement at all (AC-F6).
- **AC-G2** `[FE]` The Supplier codes tab header names the plan's statement ("Codes from the
  stock list of 28/08/2026" / "Codes from 2026-7-31 SORENTO 预装清单, 5 blocks" / "No file
  on this plan").
- **AC-G3** `[BE][T]` The stock-list and proforma readers capture the first non-empty text
  cell above the first header row as `letterhead`. Preview / validate compare it against the
  chosen supplier: when the chosen supplier's `supplier_name` (case-folded, NFKC) does not
  occur in the letterhead but ANOTHER active supplier's name does, the verdict carries a
  warning `supplier_mismatch` naming both; when no supplier name occurs, no warning. Matching is
  exact substring of master-data names, never fuzzy.
- **AC-G4** `[E2E]` The Test verdict card for a proforma reads "5 invoice blocks · 30 lines ·
  12 codes unknown" and, for the fixture uploaded under KAIPING KAIXIN, shows the warning
  "File header names CHAOZHOU JINBAICHUAN SANITARY WARE CO., LTD, you picked KAIPING KAIXIN
  SANITARY CO., LTD." Confirm is still allowed (a warning, not a refusal).

## H. Acceptable input formats are written down (S8)

- **AC-H1** `[FE]` `documentation/reference/SCM-UPLOAD-FORMATS.md` documents, for stock list
  and proforma invoice: accepted file types and size, which sheet is read, how the header row
  is found, required and optional columns with every seeded alias, stacked blocks, date
  formats, totals rows, what makes a row skipped and how that is reported, how codes are
  matched, currency rules, and that the supplier always comes from the dialog. Same content is
  offered for the Outline user guide (captain's call to publish).
- **AC-H2** `[FE]` The upload dialog links nowhere and explains nothing (no on-screen feature
  explanation); the verdict card's counts and warnings are the only in-product guidance.

## I. Guardrails

- **AC-I1** `[T]` A vitest asserts that no import statement under `scm/loading-plan/` names
  `ConfirmDeleteDialog` or `@/components/ui/alert-dialog` (the two ways a destructive dialog
  gets built), reading whole import STATEMENTS rather than single lines so a multi-line
  import cannot slip past it (SF-7). `ConfirmActionDialog` is allow-listed: it is the vehicle
  for the three data-loss prompts AC-A6 names.
- **AC-I2** `[T]` Existing loading-plan, container-request, proforma and alias pytest/vitest
  suites stay green except the tests that pinned p4 AC-A17 (older plan's figures move on a
  newer upload), which are rewritten to AC-F6 and the p4 UAC line is marked superseded.
- **AC-I3** `[FE]` The formats doc is published to the Outline user guide (captain: yes,
  2 Sep) with the same content as the repo file.

## J. The row lightbox matches the SPO document detail's design (S9, captain's markup 3 Sep)

- **AC-J1** `[FE]` Every dialog opened off a loading-plan or reorder-planning figure
  (`scm/components/PlanRowDialog.tsx`, `scm/reorder/components/PlanRowDialogs.tsx`) uses
  `TabsList variant="line"` for its tab strip, the same trigger styling
  `SPODocumentDetail.tsx` uses - never `variant="default"` pills. Counts stay in the trigger
  labels (`Open to pools (2)`, `History (0)`, etc).
- **AC-J2** `[FE]` Every table inside those dialogs is a `DataGrid`/`DataGridTable`, not a
  plain `<table>`: `tableLayout: { width: 'fixed', columnsResizable: true }`,
  `columnResizeMode: 'onChange'`, an explicit `size` per column, `truncate` + `title` on long
  text, right-aligned tabular numbers on every quantity/money/date column. No pagination (the
  caller already holds every row) and no `listingKey` persistence (a dialog's columns are not
  a personal preference - every grid passes `listingKey={null}`). The grid's own horizontal
  scroll stays inside the dialog body; the dialog itself never grows past `max-h-[85vh]`.
- **AC-J3** `[FE]` Every tab that lists a quantity ends with a footer TOTAL row (the `DataGrid`
  column `footer`, styled like the family's existing `TotalRow`), open and history tabs alike.
  The 12-month history tab (`ProjectRetailTabs`) foots BOTH series - the sum of the twelve
  months for Project and for Retail - under the peak-month line, which stays. `PoTakesPicker`
  keeps its "n of m POs · covers X of packed Y" sentence AND gains a footer total on the Taken
  column. `SoCoveragePicker` keeps its "Unassigned N" sentence AND gains a footer total on the
  Open column.
- **AC-J4** `[FE]` Usable and non-clipped at 375px and 1280px: the dialog's `sm:max-w-[95vw]`
  and `max-h-[85vh]` are unchanged: a wide grid scrolls sideways inside the dialog body, the
  page itself never scrolls sideways.

## K. Captain's live-testing feedback batch, 3 Sep (S10)

- **AC-K1** `[FE][T]` `SearchableSelect` identifies each option by `opt.value` (the id), not
  `searchText ?? label + description`: two options sharing a label - 21 suppliers literally
  named "Testing Company" is the real case - hover/arrow to only ONE of them, and the OTHER
  never highlights alongside it; selecting either returns its own id (`keywords={[opt.label,
  opt.description ?? '']}` carries the searchable text instead, for parity with cmdk's
  contract - `shouldFilter={false}` means neither `value` nor `keywords` drives filtering
  here, `visibleOptions` does). A `SearchableSelect` popover opened from inside an open
  `Dialog` also scrolls on a real wheel gesture, the same as a popover outside any dialog: the
  `Popover` `SearchableSelect` renders goes `modal` WHEN its trigger sits inside an open
  Dialog (detected once from the trigger's own DOM position via `isInsideOpenDialog`,
  `components/common/floatingAncestry.ts`), so it owns its own `react-remove-scroll` lock
  (last-mounted wins on the shared lock stack) instead of sitting outside the Dialog's own
  lock target and having every wheel event over it silently swallowed. Verified in "Plan a
  container" (Supplier) and in one non-dialog consumer (a listing filter) at 375px and 1280px;
  no change to focus-trap / outside-pointer behaviour beyond what `Select`/`DropdownMenu`
  already do while open. `SearchableMultiSelect` gets the same conditional-`modal` Popover
  fix (its `CommandItem` `value` was already `opt.value`, so only the dialog-scroll half
  applied); verified in `role-edit-dialog.tsx` (Dialog) and `ScmFilterBar.tsx` (non-dialog).
  **Amended (S10 follow-up, item 1 of the CI-red batch):** `modal` shipped unconditional
  first, then turned out to break `InlineLineTable`'s freshly-added-row guard - Radix's
  `hideOthers` (which `modal` also pulls in, to trap focus / block outside pointer events)
  marks EVERYTHING outside the popover `aria-hidden`, including the rest of the same table
  row the popover's own trigger sits in, the instant it opens; a row is not a Dialog, so
  hiding the fields beside the one just opened is wrong there. A first pass kept `modal`
  but made it conditional on `isInsideOpenDialog`; that was still only half enough - the
  same `hideOthers` also broke a REAL Dialog case
  (`ContactAccessTypesAdmin.portalForms.test.tsx`, `SearchableMultiSelect`'s "Portal forms"
  field, whose list stays open across multiple picks), because Radix Dialog is itself
  portalled, so `hideOthers` reads the Dialog's own content - including its own Update
  button - as just another sibling to hide. Neither component asks Radix `Popover` for
  `modal` at all now, in either context: `components/common/PopoverScrollLock.tsx` applies
  ONLY the scroll-lock half by hand, wrapping `PopoverContent` in `RemoveScroll`
  (`react-remove-scroll`, the library Radix's own modal Popover already uses internally)
  via `Slot`, `active` = the same `isInsideOpenDialog` detection (`renderTrigger` callers
  keep the wrap unconditionally, since it carries no aria/focus side effect to weigh
  against defaulting it on). `dialog.tsx`'s outside-click guard and `InlineLineTable`'s
  row-commit guard now share one selector, `focusIsInsideFloating`
  (`components/common/floatingAncestry.ts`), which also recognises
  `[data-radix-focus-guard]` and `[cmdk-root]`.
- **AC-K2** `[FE][T]` The Supplier codes tab's "Needs a decision" header carries a **Confirm
  (N)** button, left of Refresh matching, where N = codes decided (matched or dismissed) THIS
  VISIT and still present in the unmatched queue - disabled at N = 0. Clicking it writes
  nothing (the aliases a pick or a dismiss makes already exist) and only invalidates the
  unmatched-codes and alias queries, so the decided rows move into Remembered, the tab's own
  badge drops, and Confirm's own count falls back to 0 as soon as the refetch lands - without
  waiting for a reload or for the operator to leave the tab (AC-C3's other two triggers are
  unchanged). Undo stays available on a row until it is confirmed; once confirmed, Forget is
  what reaches it, on the Remembered list.
- **AC-K3** `[FE][T]` The Blocks table in a loading plan's Packed drill (`BlocksTable` in
  `ContainerRequestSection.tsx`) is a `DataGrid` through the shared `DrillTable` helper
  (`scm/components/PlanRowDialog.tsx`, exported for this reuse - AC-J1/J2 parity), with a
  footer TOTAL row on the Packed column summing the blocks shown, matching every other S9
  drill body.
