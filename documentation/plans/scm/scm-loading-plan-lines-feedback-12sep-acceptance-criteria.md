# UAC - Loading plan Lines tab feedback, 12 Sep 2026

**Status:** APPROVED 12 Sep 2026. Plan: `PLAN-scm-loading-plan-lines-feedback-12sep.md`.

## Journey

See the plan's Journey section. AC-U* trace to step 1 (what the table lists), AC-N1 to step 2, AC-N2 to step 3, AC-N3 to step 4.

## U. The universe: the file when there is one, links when not

- **AC-U1** `[BE][T]` A plan whose statement is on file (stock rows or invoice lines, bound or
  not) lists ONLY the products and sets those rows bind to. A `product_suppliers`-linked
  product with open SO need that the file does not name is absent.
- **AC-U2** `[BE][T]` A plan with no statement (document kind `none`, or legacy with nothing
  on file for the supplier) lists ONLY `product_suppliers`-linked products with open SO need.
  A product known to the supplier through an alias alone, or a set aliased to the supplier,
  is absent.
- **AC-U3** `[BE][T]` A plan whose file rows all bound to nothing lists zero rows, even when a
  linked product carries open need.
- **AC-U4** `[BE][T]` Placement is unchanged: on a file plan a bound row with open need is
  ranked; a bound row held (packed or unfinished > 0) with no need is a folded row; a bound
  row with neither is dropped.
- **AC-U5** `[BE][T]` Supersedes AC-E0 and AC-D3 of `scm-loading-plan-feedback-2sep`; the
  tests that pinned them are rewritten to this rule. Suites `tests/scm/test_container_request_*`,
  `test_plan_owned_statement.py`, `test_plan_statement_fallback.py`, `test_match_reaches_master_data.py` green.

## N. Lines tab feedback

- **AC-N1** `[FE][T]` The Product cell renders the subtitle only when `product_name` differs
  from `item_code` (trimmed, case-insensitive). A row whose name equals its code shows the
  code once. Set rows keep the "Figures from <driver code>" subtitle. Vitest on
  `ContainerRequestSection` with one row of each.
- **AC-N2** `[BE][T]` `incoming_pl` on every row of `POST /scm/container-requests/build` is the
  unreceived packing-list quantity NOT yet allocated to an SPO (`PL_UNALLOCATED_SQL`), and
  `incoming_pl_unallocated` equals it. Each entry of `incoming_pl_shipments` carries that
  same figure as `qty`, and a shipment whose lines are fully allocated to an SPO is absent.
  Pytest: one shipment line 10,000 shipped / 10,000 spo_allocated / 0 received gives
  `incoming_pl == 0` and no shipment entry; a line 100 / 40 / 0 gives 60 and one entry at 60.
- **AC-N2b** `[BE][T]` The Incoming PL lightbox (`container_request_drill`, kind
  `incoming_pl`) lists the same rows at the same figures as AC-N2, so the cell equals the sum
  of the rows it opens (the AC-G3 rule).
- **AC-N2c** `[FE]` Total supply = on hand + SPO + Incoming PL as now rendered; the formula
  tooltip is unchanged in wording.
- **AC-N3** `[FE][T]` A `ListSearchInput` ("Search product") sits in the toolbar row beside
  the Table / Schedule toggle. Typing filters the ranked rows, the folded rows and the
  Schedule view on `item_code`, `product_name`, `set_code` (case-insensitive substring). The
  stat cards, Save (N), Send and the xlsx are unaffected by the filter. No match shows
  "No product matches" in the table body. Clearing the box restores every row. Vitest.
- **AC-N4** `[E2E]` Browser evidence (agent-browser, sidebar nav from `/`) at 1280px and
  375px: the plan in the captain's screenshot shows SRTWHBWP once per cell, SPO 10,000 with
  Incoming PL 0 and Total supply 10,143, and typing `RPACC` leaves one row.
- **AC-N5** `[FE][T]` Every column of the Lines table is sortable by clicking its header
  (`DataGridColumnHeader`), including Rank, Product, Need, Project, Retail, On hand, SPO,
  Incoming PL, Total supply, PO, Packed; numeric columns sort numerically. Default order stays
  rank ascending. Vitest: clicking "Need" reorders rows by `open_so_need`.
- **AC-N6** `[FE][T]` The Excel/CSV preview in `components/common/AttachmentPreviewModal.tsx`
  carries a search box ("Search in sheet") above the table. Typing filters to rows where any
  cell contains the text (case-insensitive substring), over every row the sheet loaded (the
  physical-row cap), not only the 200 displayed; the visible slice is the first 200 matches.
  The match text is highlighted in the cell. A count "N of M rows" shows while filtering; no
  match renders "No cell matches". Clearing restores the plain preview. Switching sheets
  keeps the query and re-applies it. PDF and image slides show no box. Vitest.
- **AC-N7** `[BE][FE][T]` The loading plan's "Sales order cut-off" becomes a window, worded
  and shaped as reorder planning's: label "Sales orders needed", fields "From" and "To",
  helper "Empty = every open order counts." Column `plan_horizon_start` (Date, nullable) is
  added to `scm.loading_plan` (migration, single alembic head; existing rows NULL = no lower
  bound, so nothing changes for them). `POST /scm/loading-plans` and the change-cut-off route
  in `app/api/v1/scm/fulfilment.py` accept `plan_horizon_start` and reject start > end with
  422 (the same validator `app/schemas/scm_reorder.py` uses). `record_dict` and the build
  payload echo both dates. `build_for_plan` passes `plan_horizon_start` into `build`, which
  already threads it to `_open_need` / `_project_open_need`: a line with `required_date`
  before From is not counted, a line with no `required_date` always is. The plan header,
  the list column and the "What to ask ... to cover" heading render the window with the
  reorder wording (`describeWindow` in `scm/reorder/lib/runListing.ts`). Both the Plan a
  container dialog and the Change cut-off dialog carry From + To.
