# PLAN - Order inquiries: confirm per SO (the handshake back on), To confirm as the default view, remembered sort + filters

Status: planned (owner journey + rulings R1-R3 taken in Lavish 17 Sep 2026; awaiting owner go for the lane)
UAC: `oi-confirm-per-so-acceptance-criteria.md` (AC-CF-xx)
Branch: `feat/oi-confirm-per-so` from `origin/main` AFTER `feat/oi-worklist-one-header` merges (same
file, same lines: `OrderInquiriesClient.tsx` useReactTable block, `order_inquiry_worklist_service.py`)
Origin: go-live feedback 17 Sep 2026. Purchasing used to park the CS Excel aside once an order
inquiry was processed; the worklist has no equivalent, so nothing ever leaves their list.

## The journey the owner wants (17 Sep, verbatim shape)

1. CS confirms supply on the fulfilment board. Rows are raised and the cascade AUTO-LINKS
   them to open PO / SPO lines at once (already live: `auto_place_for_products(trigger="raise",
   include_awaiting=True)` from `project_supply_service.py:6240`).
2. Purchasing reviews the SO on the worklist. They change a link when the cascade picked
   wrong: Unlink selected, Link selected, Choose document (1) which offers PO AND SPO
   candidates for one ticked row (already live, `OrderInquiriesClient.tsx:1149-1181`).
3. They place / link in AutoCount. Upload purchase orders syncs the AutoCount linkage back
   ("the source of truth is the autocount linkage", `project_order_inquiry_import_service.py:955`).
4. Everything is in place. They **confirm the entire SO**. The SO leaves their To confirm list.
5. Only confirmed rows feed reorder planning. Already the rule: `demand.py:842-859` reads
   `ack_state IN ('acknowledged','changed')`. Everything feeds planning today ONLY because
   G4 (`_archive/scm/PLAN-scm-reorder-oi-feedback-1sep.md:107`) made rows born acknowledged.

So this is G4 + G5 reversed, on machinery that still exists end to end, plus the listing
memory the stock inquiries and sales orders grids already have.

## Measured facts (origin/main, 17 Sep)

- Model `OrderInquiryRow` (`app/models/project_so.py:911-1010`): `ack_state`
  awaiting | acknowledged | changed | rejected, `acknowledged_by/at`, `changed_at`,
  `rejected_*`. `state` raised | partly_linked | placed | actioned | cancelled is link-derived
  except actioned / cancelled. No completed column; none needed.
- Birth: `_handshake_for_raise` (`project_order_inquiry_service.py:859-887`) returns
  ACKNOWLEDGED for a new row and re-acks a changed one. Also stamped acknowledged at :788,
  :1288, :1521 (derive paths) and importer :1431 (the one-off sheet migration).
- Confirm endpoint exists: `POST /order-inquiries/acknowledge` body `row_ids` +
  `link_up_to/link_horizon` (`api/v1/projects/order_inquiries.py:521-548`), permission
  `projects.order_inquiries.acknowledge` (purchasing + purchasing manager, migration 428),
  service `acknowledge_rows` :2686-2706 (skips rejected). FE hook `useOrderInquiry().acknowledge`
  exists; the worklist does not call it.
- Filter: `ack` accepts awaiting | acknowledged | changed | rejected | to_confirm
  (`order_inquiry_worklist_service.py:110-118`, applied :891-920); summary `ack` counts
  include `to_confirm` (:1750-1753). FE: absent `?ack` = no filter; `ack=all` = cleared (:241-252, :473-476).
- Linking never waits for confirm: raise, link_now (:2932) and the worklist auto-place
  (route :913) all pass `include_awaiting=True`; group buy check :4130 includes awaiting.
  Manual place-on-po (:858) and unplace (:952) gate on `ACTION` only. Nothing to change.
- Reorder plan page already shows the awaiting count (`reorder_run_service.awaiting_acknowledgement_rows` :1137,
  `reorder_runs.py:294`).
- Selection: header checkbox = current page (`data-grid-select-column.tsx:43-50`); the
  toolbar's cross-page "Select all N records" banner (`data-grid-list-toolbar.tsx:209,613-631`,
  prop `selectAllMatching`) is not wired on this page. `bulkActions=[]`; Actions menu :1139-1222.
- Listing memory: `useListingViewPreferences` (`lib/listing-column-preferences/useListingViewPreferences.ts:79-90`)
  stores `sorting` + opaque `filters` on the same per-user column-config row DataGrid uses
  (`PUT /list-query/column-config/{listing_key}`); used by `StockInquiriesList.tsx:85-99` and
  `SalesOrdersGrid.tsx:283-310`. Page + search deliberately not remembered. The OI worklist
  uses `listingKey="projects.projects.view::order-inquiry-worklist"` for columns only
  (:1445); sort is component state (:411); 11 filters URL-synced (:443-490), 6 in memory only
  (supplier, project, raised date, raised by, linked, kind).

## Rulings (owner, Lavish 17 Sep 2026)

- **R1 Existing rows at deploy.** "Excel come in is confirmed, but those that flowed from
  fulfilment planning shouldn't be confirmed yet; the user should go and confirm." Sheet
  rows (importer, `supply_decision_id IS NULL`) stay acknowledged. Board rows
  (`supply_decision_id IS NOT NULL`, ack acknowledged, state not cancelled / actioned) flip
  to awaiting at migration. Measured on the 0915 copy: 74 board rows open (36 raised, 5
  partly linked, 33 placed) against 11,809 sheet rows. Book-change derived rows have no
  decision either and count as Excel-origin for the backfill.
- **R2 CS change after confirm.** "Change is inevitable ... need to change that back to be
  To confirm; our plan about how change propagates to order inquiries stays intact." The
  row returns to To confirm as `changed` with Was/Now; every propagation rule (settle in
  place, redirect, cascade, DELAY / ADVANCE rows) is untouched; planning still counts a
  changed row, as today.
- **R3 Confirm scope.** "I should be able to tick line by line also, just like fulfilment
  planning" + tick header + Select all N matching. No per-header button. The page's
  PRIMARY button becomes **Confirm (N)**, built like the board's
  (`FulfilmentBoardPanel.tsx:1404-1416`): disabled at 0 ticked, count = eligible ticked
  rows (or the matching total once Select all N is taken), a confirm-all dialog stating
  the count, then the press. "Upload purchase orders" moves into the Actions menu.
- **Manual link UI** (owner asked): it is "Choose document (1)" in Actions for exactly one
  ticked row, opening `OrderInquiryDocumentDialog` with PO and SPO candidates (screenshots
  in `.lavish/oi-choose-document.png`, `.lavish/oi-actions-menu.png`). Unchanged by this lane.

## Slices

### S1 Rows born awaiting
- `_handshake_for_raise`: new row = `(ACK_AWAITING, None, None, None)`; carried = prior;
  changing a confirmed line = `(ACK_CHANGED, prior.acknowledged_by, prior.acknowledged_at, now)`
  with NO re-ack. Same at :788, :1288, :1521 (derive_for_book_change rows born awaiting).
  Sheet-migration importer (:1431) unchanged (one-off, already-worked sheet).
- Comments that say "born acknowledged" / "no manual confirm exists" are rewritten at the
  seam, not left to lie (:641, :1313, :5316, :5397 reference the S1 proxy `_only_cascade_links`;
  that proxy STAYS, it is the right test for "did purchasing buy it").
- Migration per R1 (data only; no schema): `UPDATE projects.order_inquiry_rows SET ack_state='awaiting', acknowledged_by=NULL, acknowledged_at=NULL WHERE supply_decision_id IS NOT NULL AND ack_state='acknowledged' AND state NOT IN ('cancelled','actioned')`. Downgrade re-acks the same set with system attribution.

### S2 Confirm on the worklist
- Primary button **Confirm (N)** replaces Upload purchase orders (which moves into Actions).
  N = ticked rows with ack_state in awaiting | changed and state not cancelled; disabled at
  0 with the reason in `title`; permission = acknowledge grant (CS never sees it). Press
  opens the same confirm-all dialog shape as the board, then calls the existing endpoint
  with `row_ids`.
- Line by line = tick one row, Confirm (1). No per-row menu exists on this worklist (parity lane R8) and none is added.
- `selectAllMatching` wired: banner "Select all N records" after a page tick; Confirm then
  sends `filter` (the list's own query params) instead of `row_ids`; the endpoint applies
  `_base` and confirms every eligible row in scope. One body, two mutually exclusive keys.
- Toast "Confirmed N rows" and query invalidation (list + summary).
- **Ruling (review round):** `filter: {}` stays ALLOWED - it is Select all N on an
  unfiltered list, the owner's own explicit press, and it still resolves through the
  SAME `_base` predicate as every other filter, so `CompanyScopedMixin` still confines
  it to the caller's own company (AC-CF-8g).

### S3 To confirm is the default view
- Absent `?ack` = `to_confirm`; `ack=all` stays the cleared value; every other value as today.
- Stat tile "To confirm N" from `summary.ack.to_confirm`, tile click sets the filter.
- Filter option labels: To confirm / Confirmed / Changed / Rejected / All.

### S4 Changed rows (R2)
- No code beyond S1 if R2 recommended: `changed` already sits in `to_confirm` and the
  column already renders Was/Now.

### S5 Planning reads confirmed rows only
- No predicate change. Tests: an awaiting row is absent from `horizon_committed_select_sql`
  and from the plan run; confirming it puts it in; a changed row stays in.

### S6 Remembered sort + filters
- `useListingViewPreferences({ listingKey: 'projects.projects.view::order-inquiry-worklist',
  defaultSorting: [{ id: 'delivery_date', desc: false }], filtersVersion: 1 })`.
- Remembered: sorting + all 17 filters (incl. `ack`, `view`, `granularity`, `link_up_to`).
  Not remembered: page, search text (same rule as the two existing grids).
- URL still wins for the visit when a param is present (handover email deep links), and
  is written to the memory; absent params fall back to the memory, then the default.
- Data query gated on `!isViewPrefsLoading` so the first fetch is not the default view.

### S8 Choose document on a linked row, one press (owner hand test 17 Sep)
Owner: "we should be able to link to document manually for those that are linked, so it is
1 step instead of two", and the dialog's Document column truncates ("I can't see what is
the LA...") so it becomes a DataGrid. Measured: `_assert_linkable` (about :6944) refuses
`state not in (raised, partly_linked)`; on the 0915 copy CKSW015 qty 3 exists as an
`actioned` sheet row and as a `placed` board row with 0 links, both refused. A PO
contributes one candidate per LINE (202605-S0060 had eight), and the cell shows only the
truncated number.
- Backend: `_assert_linkable` state gate = not cancelled. `po_candidates_for_row` returns
  the row's own live links as candidates too (`current_take`, `remaining` counted as if the
  row's take were free), header `still_to_link`. The place-on-po route becomes SET
  semantics: the submitted takes are the row's links on those lines; an existing link on a
  submitted line is adjusted, on an omitted line retired; state recomputed from links.
- Frontend: `OrderInquiryDocumentDialog` table = `DataGrid` (`tableLayout fixed,
  columnsResizable, columnResizeMode onChange`, explicit sizes), Document column 260 wide
  with the full number + "line N of M", Current mark + prefilled Take on linked lines;
  Actions "Choose document (1)" enabled for any non-cancelled ticked row.
- Tests: pytest gate + candidates + set-semantics move; vitest grid + prefilled takes.

### S7 Guide + archive
- Outline guide page for order inquiries: Confirm step, To confirm default, remembered view.

## Tests (tester writes first)

pytest (`tests/scm/test_oi_confirm_per_so.py`, private DB `sorento_oicf_ci`):
- born awaiting on raise; carried keeps; change of a confirmed row = changed, not re-acked
- acknowledge by row_ids; by filter (query = SO number) confirms every eligible row of that
  SO and none of another; rejected + cancelled skipped; CS principal 403
- list default `ack` absent = to_confirm rows only; `ack=all` = every row
- summary `to_confirm` count matches
- demand: awaiting row out, confirmed in, changed in
- migration R1 backfill: board row flips, sheet row stays, cancelled / actioned board row stays

vitest: Confirm (N) label + disabled at 0 + count follows Select all N; Actions holds Upload purchase orders; select-all-matching banner; default filter
seeding from memory vs URL; sort persisted through the hook (mock the service).

Browser (agent-browser): search SO, tick header, Select all N, Confirm, list empties, tile
count drops, reload keeps sort + filters, page + search reset.
