# UAC - Order inquiries: header list + OI detail page

Plan: `PLAN-oi-header-list-detail.md`
Owner rulings: 21 Sep 2026 (R1-R6, recorded in the plan)

## Journey

Actor: purchasing (holds `projects.projects.view` + `projects.order_inquiries.acknowledge`).
Arrives from the sidebar: Procurement > Supply Chain > Order Inquiries.

1. The first screen is one row per order inquiry (one OI = one sales order's instructions),
   oldest raised first, the Outstanding toggle on. The system already knows the OI number, who
   raised it and when, the sales order, customer, project, agent, SO date, how many lines and how
   much quantity it holds, and whether anything in it still waits for a confirm. Decision: which
   OI to open (normally the top one).
2. They click the row and land on the OI detail page, Lines tab: product, quantity, delivery
   date, supplier, PO, SPO, location, instruction per line. Decision: is every link right.
3. When a link is wrong they tick the line and fix it from the gear menu (Choose document, Link,
   Unlink, Reject), without leaving the page. Related PO and Related SPO tabs show which
   documents this OI sits on.
4. They press Confirm. With nothing ticked the whole OI is confirmed; with lines ticked only
   those. When no line waits any more the OI reads Completed and leaves the Outstanding list.
   Next takes them to the next outstanding OI.
5. When CS reconfirms the sales order later, the OI keeps its number and its raised date, returns
   to Outstanding, and its General tab shows every raise with who and when.

Nobody else is told anything new: the handover / changed / undone emails stay as they are, their
link now opens the OI detail page.

The line-level worklist purchasing uses today (cards, delivery-month chips, bulk link actions
across many sales orders) stays, one toggle away, unchanged.

## Phase 1 - frontend against mocks

- **AC-HL-01 [FE]** Given the Order Inquiries page, when it opens, then a `Documents | Lines`
  toggle shows with Documents selected, and Lines renders today's worklist unchanged (same cards,
  chips, filters, Actions, Confirm). The chosen view is kept in the URL as `?display=lines` (`view` is already the worklist's own List | Schedule key and existing links carry it).
- **AC-HL-02 [FE]** Given the Documents view, then the grid shows one row per OI with columns in
  this order: Raised at, OI no, S/O no, Raised by, Lines, Qty, Customer, Project, Agent, SO date,
  Status. Every column has an explicit size, long text truncates with a `title`, the table is
  `width: 'fixed'` + resizable, `listingKey = projects.projects.view::order-inquiry-headers`.
- **AC-HL-03 [FE]** Given the Documents view, then an `All | Outstanding | Completed`
  `ToggleGroup` (the PO / SPO allocations control) sits in the toolbar, default Outstanding, and
  the default sort is Raised at ascending. Toggle, sort, search and page are URL-synced.
- **AC-HL-04 [FE]** Status renders as a `Badge`: Outstanding (warning tone), Completed (neutral
  tone). An Outstanding row's Lines cell reads `<to confirm> / <total>` in its `title`.
- **AC-HL-05 [FE]** Search matches OI no, S/O no, customer, project, agent, and the product or
  location of any line inside the OI, through the shared `ListSearchInput`; filters are Raised by, Agent, Project, each a clearable `SearchableSelect`.
- **AC-HL-06 [FE]** A row is a link (`rowHref`) to `/project-sales/order-inquiries/<id>` carrying
  the list state through `buildDetailSearch`. S/O no is its own link to the SCM sales order.
  No UUID is visible anywhere.
- **AC-HL-07 [FE]** Empty states: Outstanding with zero rows reads "Nothing to confirm" with a
  CTA switching to All; All with zero rows reads "No order inquiries yet".
- **AC-DP-01 [FE]** Given the detail page, then the shell is the SO detail shell: `PageHeader`
  "Order Inquiry" + `BackToList`, a header card with the OI number, the status Badge, raised by
  and raised at, then `DetailActions` with the pager ("n / total" over the same filtered list),
  a gear menu, and ONE primary button, Confirm.
- **AC-DP-02 [FE]** Tabs in order: Lines, General, Related PO, Related SPO (line tabs, `?tab=`
  in the URL). Lines is the default tab.
- **AC-DP-03 [FE]** Lines tab: a DataGrid with columns Product, Qty, Delivery date, Supplier,
  PO, SPO, Location, Instruction, State (the existing `OrderInquiryStatePill`), a select column,
  product search, a Columns button, pagination (10 / 25 / 50) and a footer total under Qty.
  Cancelled lines are hidden, as on the worklist. `listingKey =
  projects.projects.view::order-inquiry-lines`. The Qty cell keeps the Was/Now (i). The Product
  cell shows the product code ONLY, one line, no name or description under it (owner, 21 Sep:
  in Sorento the product code is the product name).
- **AC-DP-04 [FE]** PO and SPO cells open the existing `OrderInquiryDocumentDialog`.
- **AC-DP-05 [FE]** Confirm reads `Confirm` with nothing ticked and `Confirm (n)` with n lines
  ticked. It is disabled when no line in scope waits for a confirm, and hidden without
  `projects.order_inquiries.acknowledge`.
- **AC-DP-06 [FE]** The gear menu carries, reusing today's dialogs and hooks: Auto link (owner,
  21 Sep: always enabled; runs the auto-link cascade over the ticked lines, else over every line
  of this OI, and reports linked / left over the way the worklist's Auto link all does), Choose
  document (exactly one line ticked), Link selected, Unlink selected, Reject selected, Unconfirm, Export
  Excel. Items needing a selection are disabled without one. Unlink is a deferred pending action
  (countdown + Cancel), never a confirm dialog. Cancel leaves the ticked lines ticked; the
  selection clears only when the unlink commits.
- **AC-DP-07 [FE]** General tab: an Order card (S/O no as link, SO date, agent, project, order
  type) and a Customer card (customer, customer code), the SO General layout, plus a Raise
  history card: one entry per raise, newest first, each with kind (Raised / Reconfirmed), person
  and time, rendered with `EventTimeline`. One raise = one entry.
- **AC-DP-08 [FE]** Related PO tab: one row per purchase order this OI's lines are linked to:
  PO no (link to `/scm/purchase-orders/<id>`), Supplier, PO date, Lines linked, Qty linked.
  Related SPO tab: SPO no (link to the SPO document page), Supplier, Lines linked, Qty linked.
  Both are the shared `DataGrid` (owner markup 21 Sep): sortable headers, search, Columns button,
  pagination, explicit column sizes, `width: 'fixed'` + resizable, `listingKey =
  projects.projects.view::order-inquiry-related-po` / `...::order-inquiry-related-spo`, a footer
  total under Qty linked. Each has an empty state ("No purchase orders linked yet" / "No SPOs linked yet").
- **AC-DP-09 [UX]** Both screens are usable and unclipped at 375px and 1280px: the header card
  wraps, the toggle and toolbar wrap, grids scroll inside their card, the primary button stays
  reachable.
- **AC-DP-10 [UX]** No new motion. Only what the shared primitives already do (tabs underline,
  Badge, DataGrid, pending-action countdown). Reduced motion is inherited.
- **AC-DP-11 [FE]** Loading, error (extracted message through `extractApiError`), not-found
  ("This order inquiry no longer exists" + back to list) states exist on the detail page.

## Phase 2 - backend

- **AC-NO-01 [BE]** Given a new OI header raised in September 2026 (Asia/Kuala_Lumpur date),
  then its `inquiry_no` is `OI-2609-NNNN`, four digits, the next free number of that company and
  month; the first of a month is `-0001`.
- **AC-NO-02 [BE]** Given two headers inserted in one flush, then they take consecutive numbers.
- **AC-NO-03 [BE]** Given a header whose number is already set, then it is never re-minted: a
  reconfirm in a later month keeps the original number.
- **AC-NO-04 [BE]** Given the migration, then every existing header is renumbered per company and
  per month of its first raise, ordered by first raise then id, with no gap and no duplicate
  (0921 copy: `OI-2609-0001` .. `OI-2609-0735`), and downgrade restores the old numbers.
- **AC-RD-01 [BE]** Given a header, then `raised_at` / `raised_by` are the FIRST raise and a
  reconfirm never changes them; every raise and reconfirm adds one row to
  `projects.order_inquiry_raises` (kind, person, time). Two writes inside one confirmation add
  one row, not two.
- **AC-RD-02 [BE]** Given the migration, then each existing header gets a `raised` history row at
  the earlier of its current `raised_at` and its earliest row's `created_at`, plus a
  `reconfirmed` row at its pre-migration `raised_at` / `raised_by` when that is more than a
  minute later; the header's `raised_at` becomes the first of the two.
- **AC-RD-03 [BE]** Given a raise and two reconfirms, then the header detail's `raise_history`
  holds three entries (`raised`, `reconfirmed`, `reconfirmed`) with person name and time, newest
  first. A header that predates the migration holds at least its first raise and, when it
  differs, its last reconfirm.
- **AC-LS-01 [BE]** `GET /api/v1/project-sales/order-inquiry-headers` returns one item per header
  with the contract fields (plan, "Contract"), paged, permission `projects.projects.view`; 403
  without it.
- **AC-LS-02 [BE]** `state=outstanding` returns exactly the headers having a non-cancelled row
  with `ack_state` in (`awaiting`, `changed`); `completed` the complement; `all` both. Default
  `outstanding`. A header with only cancelled rows is Completed. An unknown value is a 422.
- **AC-LS-03 [BE]** Default order is `raised_at` asc with `id` as tiebreaker; `sort` accepts
  `raised_at, inquiry_no, so_number, raised_by, lines_total, qty_total, customer, project, agent,
  so_date, status`; anything else is a 422.
- **AC-LS-04 [BE]** `query` matches inquiry no, legacy inquiry no, SO number, customer name,
  project title, agent name, and the `item_code` or `stock_location` of any non-cancelled row of
  the header (one header returned once, however many rows match), case-insensitive; `raised_by`, `agent`, `project_id` filter exactly.
- **AC-LS-05 [BE]** `lines_total`, `lines_to_confirm` and `qty_total` ignore cancelled rows.
- **AC-LS-06 [BE]** The list runs in a bounded number of queries regardless of page size (no
  per-row query), asserted with a query counter.
- **AC-LS-07 [BE]** A user scoped to another company sees none of this company's headers.
- **AC-DT-01 [BE]** `GET /order-inquiry-headers/{id}` returns the header, the Order and Customer
  blocks, counts, status and `raise_history`; 404 for an unknown id or another company's header.
- **AC-DT-02 [BE]** `GET /order-inquiries?inquiry_id=<id>` returns only that header's rows, with
  every field the worklist already returns (supplier, PO, SPO, location, instruction).
- **AC-DT-03 [BE]** `GET /order-inquiry-headers/{id}/related-documents` returns the purchase
  orders and SPOs reached through `order_inquiry_links` of that header's non-cancelled rows, one
  entry per document, with `lines_linked` and `qty_linked`; empty lists when nothing is linked.
- **AC-CF-01 [BE]** `POST /order-inquiries/acknowledge` with `filter: {inquiry_id}` confirms every
  awaiting / changed row of that header and nothing outside it; with `row_ids` only those rows.
  Rejected and cancelled rows are skipped as today. After a whole-OI confirm the header lists
  under `completed`.
- **AC-AL-01 [BE]** `POST /order-inquiries/auto-place` with `filter: {inquiry_id}` runs the cascade
  over that header's linkable rows only and touches no row of another header; with `row_ids` only
  those rows. Same permission as today (`projects.order_inquiry.action`), 403 without it.
- **AC-CF-02 [BE]** Given a Completed header, when a row turns `changed` or a new row is raised
  `awaiting`, then the header lists under `outstanding` again.
- **AC-LK-01 [BE]** `build_order_inquiry_link` (emails) points at
  `/project-sales/order-inquiries/<header id>`; the SO detail payload carries the header `id` so
  the SO page links to the same place.
- **AC-FE-01 [FE]** Mocks swapped for the real endpoints; vitest covers the list params builder,
  the toggle-to-param mapping, the Confirm label / disabled rules and the status Badge mapping.
- **AC-E2E-01 [E2E]** agent-browser, from the sidebar, 1280px and 375px, real data: open
  Outstanding, open the top OI, land on Lines, open Related PO, press Confirm, see Completed, go
  back, the OI is gone from Outstanding and present under Completed; Unconfirm restores it.
  Lines view still works. Console and errors clean.
