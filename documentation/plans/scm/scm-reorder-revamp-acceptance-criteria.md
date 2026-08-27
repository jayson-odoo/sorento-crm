# UAC: Reorder planning revamp

Plan: `PLAN-scm-reorder-revamp.md`. Each criterion names its phase (P1 = FE mock, P2 = BE + real
data, P3 = browser run). A criterion is met only when its check passes on the dev server.

## A. Plans list

- A1 (P1) `/scm/reorder` renders a DataGrid of plans with columns Plan, Sales order cut-off,
  Warehouses, Products, Lines, Decided, Status, Cash if all accepted; search, Filters, Columns,
  Export, pagination present; `listingKey` saved column prefs work.
- A2 (P1) Toolbar: Actions menu holds the upload entries and Refresh; primary button reads
  "Start Plan". No "Manual plan", no "Upload data" button.
- A3 (P1) Clicking anywhere on a row opens `/scm/reorder/{id}`. Hover highlights the row.
- A4 (P2) `GET /scm/reorder-runs` honours `sort`, `dir`, `query`; rows carry `product_count`,
  `decided_product_count`, `confirmed_product_count`. Test pins each.
- A5 (P1) Status: Running / Planning / Confirmed / Failed derived per plan 4.1; the daily cron run
  shows a "daily" badge.
- A6 (P1) `/scm/reorder?plan=<id>` redirects to `/scm/reorder/<id>`. `RunHistoryPanel` no longer
  exists in the tree.

## B. Start Plan modal

- B1 (P1) Title "Start Plan"; fields in order Sales order cut-off, Warehouses, Products; no
  "Select all"; buttons Cancel / Start Plan.
- B2 (P1) Empty cut-off is allowed; a past date is rejected (existing rule).
- B3 (P2) Submitting posts the unchanged payload (`plan_horizon_date`, `warehouse_codes`,
  `product_codes`) and navigates to the new plan, which shows the progress state until completed.

## C. Plan page shell

- C1 (P1) Header shows "Plan dd/mm/yyyy HH:mm" and "Sales order cut-off dd/mm/yyyy" (or "no
  cut-off") and nothing else; a "Plans" back link.
- C2 (P1) Grid toolbar right side, in order: Actions, Save (N), Confirm (N). Actions holds Order
  summary, Plan exceptions, PO worklist, Reset planning. No reset icon, no Manual plan, no Upload.
- C3 (P1) Expand all / Collapse all buttons on the toolbar; Expand all opens every row on the page;
  Collapse all closes them; each disabled when it has nothing to do.
- C4 (P1) Collapsed columns exactly: #, Product, Suggested qty, Reorder level, Reorder qty, Project,
  Retail, On hand, SPO, PO, Decision. Total cost exists but hidden by default. No MOQ / Price /
  Supplier / Level / Health columns.
- C5 (P1) Fits 1280 px without horizontal scroll; usable at 375 px (columns scroll inside the grid).
- C6 (P1) Decision cell is a pill only (Suggested / Unsaved / Saved / Confirmed / Skipped + mix
  words). No buttons in the cell.
- C7 (P1) Tiles remain above the grid; "N of Total made" counts products.

## D. Expanded panel

- D1 (P1) Clicking a row opens the panel; several rows can be open at once.
- D2 (P1) Cover zone: From stock, From PO, Buy inputs with caps shown; SPO arriving read-only;
  MOQ input with master beside; hint "N over / N short" only when the mix differs from suggested;
  Use suggestion and Skip buttons.
- D3 (P1) Buy re-rounds to MOQ and multiple on blur (existing `roundBuyQty`).
- D4 (P1) Price zone: last price with PO ref + date; last supplier select over the shortlist;
  amber "Cheaper on file" line when an alternative beats it by the policy threshold; radio Use
  last price / Get new price; line cost shown. Never purchased: "No price on file", radio defaults
  to Get new price.
- D5 (P1) Level zone: suggestion badge, Level input, Reorder qty input, terms line, chart link
  opens the existing chart in a dialog.
- D6 (P1) Health zone: verdict badge, radio Keep selling / Discontinue.
- D7 (P1) Any edit turns the pill Unsaved and increments Save (N) by product; leaving the page with
  drafts prompts.
- D8 (P1) Legacy run: panel renders, every input disabled, lock reason shown once.
- D9 (P1) No "Live stock as of" line and no location table inside the panel.

## E. Save and Confirm

- E1 (P2) Save sends one `PUT /scm/reorder-runs/{run}/plan-edits`; all changed fields land
  (decision, moq, level, reorder_qty, lifecycle); pills turn Saved; test per field, one transaction
  (a failing row rolls back the batch), 404 for a rec outside the run, 409 on a legacy run.
- E2 (P2) Grouped product rows fan out to every member rec (existing behaviour, test pinned).
- E3 (P2) Confirm = Save then confirm; untouched products confirm as the suggestion; skipped are
  excluded; draft POs created as today. Test: 3 products, 1 amended, 1 untouched, 1 skipped -> 2
  confirmed lines.
- E4 (P2) `decided_count` / `total_count` and the Confirm (N) label count distinct products. Test:
  one product across 3 bins decided once reads 1 / 1, not 3 / 3.
- E5 (P1) Confirm dialog states product count and cash before proceeding.

## F. Lightboxes

- F1 (P1) Suggested qty, Project, Retail, On hand, SPO, PO numbers are clickable and open a
  Dialog; no hover popovers or (i) icons remain on those cells.
- F2 (P2) Project dialog: tab "Order inquiries (N open)" with Inquiry, Customer, Project, Agent,
  Price, Qty, Needed; tab "SO history" with SO, Customer, Project, Agent, Price, Qty, Date.
  Backed by `demand?channel=project`, `scope=location` / `scope=product`; rows carry
  `project_title`.
- F3 (P2) Retail dialog: same shape with `channel=retail`.
- F4 (P2) On hand dialog: site-pool locations only (`is_pool`), columns Location, On hand,
  Reserved, Free, SO qty, SPO qty, Available, PO qty; rows expand into documents; header "Stock as
  of <last stock upload>". The as_of equals `MAX(stock.updated_at)` for the product (test), not
  the request time.
- F5 (P2) SPO dialog: tabs Open to BRW / History to BRW; columns SPO, Supplier, Qty, Received,
  ETA, Arrived, Status; new endpoint tested with one open + one received shipment, a DC1-bound
  shipment excluded.
- F6 (P2) PO dialog: tabs Open to BRW / History to BRW; columns PO, Supplier, Qty, Unit price,
  Issued, ETA, Status; BRW pool key only; a BRW-BB-bound or destination-less line excluded (test).
- F7 (P2) Panel last price / last supplier equal the PO dialog's newest history row (same source).

## I. Pool-only on hand, cover and channels (R16-R18, 28 Aug)

- I1 (P2) `GET /reorder-runs/location-stock` lists EVERY active site pool for the product,
  zeros included, and drops an all-zero project bin. Rows come back pools-first, each set
  by warehouse code. Test: two empty pools are listed at 0; an empty project bin is not.
- I2 (P2) Product-health `on_hand` counts site pools only. Test: 34 units in a project bin
  beside 120 in the pool reads 120.
- I3 (P1) The collapsed column header and the lightbox title read "On hand BRW"; the
  lightbox renders every pool row it is given, zeros included, and no project bin - with
  no fall-back to the whole list when the payload flags none as a pool.
- I4 (P1) The product-health factor reads "On hand: N in the pool" (or "nothing in the
  pool"), and the ledger's On-hand-by-location aside lists pools only.
- I5 (P2) `cover_service.free_stock_by_product` offers no project location. Test: 34 free
  in BRW-IB (`segment = 'project'`) with 0 in the BRW pool yields NO source, and a
  shortage of 100 is bought in full.
- I6 (P1/P2) `sources_in_scope` / `sourcesInScope` drop a project source whatever the
  cover scope says; `cross_segment` and the `line_segment` argument no longer exist on
  either side.
- I7 (P1) The panel lists the per-pool split under From stock when the take spans more
  than one location; a single source states none.
- I8 (P1) No demand channel is derived from a warehouse segment anywhere in reorder
  planning: `grep -rn channelOf app/(protected)/scm/reorder` is empty, the group meta
  carries `PLAN_CHANNEL_ORDER`, and the ungrouped grid has no "Order type" column or
  filter.

## G. Regressions guarded

- G1 (P2) Engine output for a run is byte-identical before and after this lane (existing golden
  tests pass).
- G2 (P2) Per-row endpoints (`/decision`, `/moq`, level, lifecycle) still work unchanged.
- G3 (P2) Order summary, Plan exceptions, PO worklist views open from Actions and render as before.
- G4 (P2) `alembic heads` = one head against origin/main if any migration is added.

## H. Verification run (P3)

- H1 agent-browser from `/` via the sidebar: SCM -> Reorder planning -> Start Plan -> plan opens ->
  Expand all -> edit Buy on one row, MOQ on another, Discontinue on a third -> Save (3) -> Confirm
  -> draft POs exist -> pills read Confirmed.
- H2 Same run at 375 px for the list, the modal and one expanded row.
- H3 Evidence (screenshots + command log) attached to the PR.
