# UAC - Fulfilment feedback: loading plan, proforma invoice, SPO planner

Status: GO, 2026-08-26 (captain: no reorder / cut; PO doc date column is `purchase_orders.issue_date`). Prior r5 GO WITH CHANGES, Q9 ruled yes (Q1-Q8 ruled, three review additions, board-vocabulary layout, F0 dropdowns). Contract for `PLAN-scm-fulfilment-feedback.md`. Every AC names the screen and a number a tester can check against the three Drive files (JINBAICHUAN stock list 27 Jul, pre-load list 31 Jul, KAILU PI 17 Jul).

## A0. Dropdowns (global)

- AC-A0.1 `SearchableSelect` / `SearchableMultiSelect` render the selected option in full: "CHAOZHOU JINBAICHUAN SANITARY WARE TECHNOLOGY CO., LTD" is readable on the loading plan's Upload popup supplier picker at 1280px; at 375px it wraps to two lines, never an ellipsis.
- AC-A0.2 Menu items wrap long text; the menu is never narrower than the trigger.
- AC-A0.3 Guard test: no `truncate` class on the selected-label element of either component.

## A. Loading plan builds with or without a stock list

- AC-A1 With no stock list and no PI for the supplier, the table lists every product the supplier is linked to (`product_suppliers`) that has open SO need, ranked; "They hold" reads "-"; the empty-state card is gone.
- AC-A2 With a PI uploaded and not yet converted, "They hold" reads the newest such PI's qty with a "PI 31/07" badge; the freshness strip shows "PI 31/07/2026".
- AC-A3 With a stock list uploaded, "Packed" reads the packed quantity only (unfinished left the grid 27 Aug; it still reads in the row dialog) and sorts on it; the PI is not consulted for that column.
- AC-A3b RETIRED 27 Aug (R23): the "Unfinished stock without a product match" block under the grid is gone. A stock-list code that matches no product is listed by the unmatched-code queue above the plan (AC-F11.1), where it can actually be answered; a second read-only list of the same codes was one nobody worked down. The screen shows no such block, and no request is made for the unfinished feed to build it.
- AC-A4 A product on the stock list or PI with no open need still gets a row (`has_demand: false`, unranked).

## A2. Loading plan layout (board vocabulary)

- AC-A2.1 Four stat cards above the grid: Outstanding, BRW On Hand, From SPO, To request (with estimated cbm); "They can pack now" removed (captain, 27 Aug); no sub-captions except the Plan-until date and the cbm estimate (captain, 27 Aug); To request follows the Ask edits live.
- AC-A2.2 Grid columns: Rank, Product, Suggested (editable), Need, Project, Retail, On hand, SPO, Incoming PL, PO, Earliest need-by, Packed, Project peak, Retail peak. No Open SOs column (captain, 27 Aug): the SO-lines drill sits on the Project and Retail figures, each listing its own channel (retail drill includes unclassified lines, which that figure counts). No Unclassified column. No legend row: the cards carry the swatches.
- AC-A2.3 Clicking the product opens the row popover: Quantity needed box, Suggestion box, location table (BRW / MWH / WH3 / DC1 / RSW + one muted group-locations row), Ordered 12 months box (two series), Incoming-for-reference box, contributing SO lines earliest first.
- AC-A2.4 Legend and colours match the fulfilment board: pool stock emerald, SPO violet, ask rose.
- AC-A2.5 Usable at 375px and 1280px: the grid scrolls inside its container, the popover becomes a full-height sheet on mobile.
- AC-A2.6 Loading plan toolbar (captain, 27 Aug): ONE primary blue CTA "Upload". It opens a popup whose first step asks Supplier (`SearchableSelect`, server-searched, required), Plan until (date, optional, clearable) and Document (Stock list / Proforma invoice, Stock list by default), with Continue (to that document's existing upload dialog, supplier fixed) and "Plan without a file" (applies the two picks and closes). Continue and "Plan without a file" are disabled until a supplier is chosen. The page itself shows Supplier and Plan until as read-only text ("No supplier chosen" and "-" before anything is picked, the supplier name and dd/mm/yyyy after), never as inputs. A gear button (`Settings` icon, outline, `aria-label="More actions"`, disabled until a supplier is chosen) holds the secondary actions: "View uploaded list" (only when a stock-list attachment exists), "Refresh matching", "Change supplier / plan until" (re-opens the popup on step 1). The request section's own empty-state CTAs open the popup straight on the matching document's upload. At 375px the text block sits above the buttons and the popup's fields stack.

## B. The numbers on the row

- AC-B1 On hand = sum over site pools only (`segment <> 'project'`). 200 at BRW + 50 at BRW-BB reads 200; popover lists BRW 200 and "In group locations 50".
- AC-B2 SPO = open `spo_allocations` at site pools only; an allocation bound for BRW-BB is excluded from the cell and listed muted in the popover.
- AC-B3 Popovers per site: BRW / MWH / WH3 / DC1 / RSW rows, zero rows shown.
- AC-B4 Column "Incoming PL" = unreceived packing-list qty across shipments not yet arrived; popover lists shipment (or "draft"), ETA, qty. It is never subtracted.
- AC-B5 Suggested qty = Need - On hand (pool) - SPO (pool), floored at 0; the cell title states the formula and says Incoming PL is a reference.
- AC-B6 Two history columns per product, "Project peak" and "Retail peak", each reading "{peak qty} {Mon yy}" (a dash when the series has no orders); a click opens that series' twelve bars (captain, 27 Aug, second pass: the combined cell was hard to read). From the last 12 full months of `sales_order_lines.qty_ordered` by `order_date`, project vs retail by `sales_orders.demand_class` (corrected 26 Aug during F3, was "by warehouse segment": measured on the dev copy, 100% of the last twelve months' SO lines carry a demand_class while 6,004 lines carry no warehouse at all and would have been counted as project by the segment reading, and the row's own Project / Retail columns are counted on demand_class, so a segment-based history would contradict the columns beside it - `trajectory_service` splits its channels the same way); no orders reads "No orders in 12 months". The twelve buckets end at the LAST FULL month: the current, part-finished month is excluded, the same window rule `trajectory_service` uses (`until` = the first of this month).
- AC-B7 History popover per row: two bar series (project, retail), 12 months zero-filled, labelled "Ordered qty (SO booked)", each series' peak highlighted, avg and total per series. SRTWB241, SRTWB243 and SRTWB246 each open their own.
- AC-B8 The history sidecar is fetched for the visible page's product ids only.

## C. Send to supplier

- AC-C1 Send produces three things in one email: the PDF, `container-request-{supplier}-{stamp}.xlsx`, and a link `/c/{company}/supplier-request/{token}`.
- AC-C2 The xlsx has the supplier's own header row as uploaded (序号 / 型号 / 商标 / 规格 / 品名 / 包装好库存 / 空瓷 / 体积(cbm) / 总体积(cbm) / 备注) plus `需装数量 / Qty to load`; every stock-list row in their order; requested rows not on their list appended below.
- AC-C3 Rows with Suggested qty 0 carry an empty Qty-to-load cell.
- AC-C4 "Requests sent" card: PDF, XLSX and "Copy link" per notice.
- AC-C5 With no stock list, the xlsx falls back to item code / product name / packed / unfinished / qty to load.
- AC-C6 The public page shows, without login: supplier name, request date, the lines (item code, name, qty to load, their packed / unfinished), zh + en labels, PDF and XLSX download. No prices, no other suppliers, no navigation.
- AC-C7 Unknown token and expired token (30 days) return the same "This link is no longer available" page; resending the request issues a new token and the old one expires.
- AC-C8 ONE token per send, on BOTH channel rows (R23): the email row and the chat row of one send carry the same `public_token` and the same expiry, and the "Requests sent" card offers "Copy link" on each of them - the chat row is the one Ms Tee copies for WeChat. Still one live link per supplier: a resend retires the previous send's token, and its rows then read a muted "Link retired" instead of a button (a copied dead link is worse than none) while a notice that never carried a link says nothing at all. The payload carries `link_retired`; `public_url` is null once the token is dead. The database refuses a token reused by a second send (unique on `(public_token, channel)`, migration 434), and the chat row of a send whose link is still live is backfilled by that migration.
- AC-C9 The gear on the "What to ask X for" header (R23, `Settings` icon, outline, icon size, `aria-label="Plan actions"`) holds: "Refresh suggestion" (the build's own refetch - the standalone button is gone), "Copy link" (the supplier's current live link, disabled with the title "No link sent yet" when there is none), "Download XLSX" and "Download PDF". The two downloads render the lines currently on screen (edits included) through `POST /api/v1/scm/container-requests/document?format=xlsx|pdf` behind `scm.dashboard.view`: the same bytes the notice's own document route would produce, the file named `container-request-<supplier code>-<yyyymmdd>.<ext>` through the RFC-5987 header helper, and NO notice, token or email created. Both items are disabled when every quantity is 0. "Send to supplier" stays the one primary button beside the gear.

## D. Proforma invoice carries volume

- AC-D1 Importing the pre-load list stores per line cartons, cbm per unit, total cbm; the KAILU PI stores nulls, never 0.
- AC-D2 PI detail header: "Volume {Σ cbm_total} cbm of 65 ({pct}% full)" with the container size named; null cbm lines counted as "N unmeasured".
- AC-D3 The five JINBAICHUAN blocks read 69.36 / 67.68 / 67.82 / 67.4 / 27.1 cbm; the first four read over capacity in rose.
- AC-D4 Container size defaults to 40HQ 65 after the migration and is changeable on the PI; a loading plan built before the migration keeps its stored capacity.

## E. Sorento adjusts the PI

- AC-E1 PI detail edits in place (same layout as view): qty per line editable, a line removable (confirm dialog); "Supplier: 408" shown beside once the figures differ.
- AC-E2 Saving stamps adjusted by / at; `supplier_qty` never changes.
- AC-E3 Fill bar recomputes on save; over capacity reads "over by N cbm".
- AC-E4 "Export adjusted PI" downloads an xlsx in the pre-load block layout with the adjusted qty, cartons, total cbm and amount recomputed, and the supplier's qty in 备注 where it differs.
- AC-E5 Convert on an over-capacity PI is refused with the figures unless "Convert anyway" + reason.

## E2. PI revisions

- AC-E6 Uploading a file whose supplier matches and whose item codes overlap an un-converted PI by >= 50% offers "Revision of PI-x" in the dialog, pre-selected; the user may choose "New PI" instead.
- AC-E7 A revision supersedes the prior: prior `status = superseded`, read-only, still listed under the current one as "Revision 1 of 2".
- AC-E8 PI detail shows a diff vs the previous revision: qty, unit price, amount per line; added and removed lines; header "Price changed on N lines".
- AC-E9 "Last incoming cost" (MCP cost answer, PO worklist) reads the current revision's unit price only; a superseded price never surfaces.
- AC-E10 Convert to packing list uses the current revision; a superseded PI cannot be converted.
- AC-E11 "Mark as revision of" on a PI detail links a wrongly-created new PI to its predecessor.

## E3. The PI list and detail read like every other record (R24, captain 27 Aug)

- AC-E2.1 The proforma-invoice LIST renders on `DataGridListToolbar`: one search box (PI
  number, supplier, container or BL, reaching the list endpoint's `query`), ONE Filters
  popover holding the Supplier and Packing list selects with a count on the button, Columns,
  and "Upload proforma invoice" anchored right as the only primary action.
- AC-E2.2 The active filter is STATED above the grid as a chip with a clear affordance - the
  default is "Not converted", and a sticky default the reader did not set this session is
  otherwise indistinguishable from missing data.
- AC-E2.3 The whole row opens the invoice, carrying the list's own query into the detail URL;
  the PI-number cell stays a real anchor and stops its own click propagating. There is no
  per-row Delete: deleting is a bulk action on the selection, behind an `AlertDialog`.
- AC-E2.4 The Supplier column shows the supplier NAME once, with no second normalised-code
  line under it. Pagination renders whether or not there are rows.
- AC-E2.5 The DETAIL page carries a record header: PI number plus its badges (currency,
  "Revision n of m", "Superseded", and where the goods are) on the left; on the right, in
  this order, the prev/next pager, ONE primary CTA ("Convert to packing list", or "Convert
  the rest" when split, hidden when fully placed, superseded, or the reader lacks
  `scm.reorder.run`), a gear menu (`aria-label="More actions"`) holding Edit / Export
  adjusted PI / Mark as revision of / Delete invoice, and Back to proforma invoices.
- AC-E2.6 Read-only provenance (source file, uploaded by and when, adjusted by and when) is a
  muted meta line under the header title, never inside a tab body.
- AC-E2.7 Four tabs in this order, the SAME set in view and in edit: General (Invoice,
  Supplier and Volume cards), Lines, Revisions, Packing lists. Every one renders, with an
  explicit empty state; the Packing lists empty state offers the Convert CTA as its next step.
- AC-E2.8 Editing is a LOCAL DRAFT: nothing is written until Save. `pi_number` is editable and
  is the first field of the Invoice card; a removed line is struck through with an Undo and is
  only deleted on Save; "Add line" inserts a draft row with a server-searched product select,
  item code defaulting to the product code, description, qty, UOM, cartons, CBM per unit, unit
  price and both weights. Cancel discards the draft. The header states "Nothing is written
  until you press Save." beside Cancel and Save, and offers nothing else.
- AC-E2.9 Save is ONE `PUT /scm/proforma-invoices/{id}` carrying the number, the container
  size and the whole `lines` array: rows with an `id` update, rows without create, and a line
  the array no longer names is deleted. A rename onto a number the supplier already uses is
  refused with `duplicate_pi_number`; a converted or superseded invoice refuses the whole save.
- AC-E2.10 The line grid renders the same columns in the same order in both modes: Item code,
  Product, Description, Qty, UOM, Cartons, CBM/unit, CBM total, Unit price, Amount, Net wt,
  Gross wt, Match. The reader maps 净重 / 毛重 / N.W. / G.W. onto the two new columns.
- AC-E2.11 The upload dialog is the SAME two-step as the order uploads: supplier, dropzone,
  Test / Cancel / Confirm. Test shows the standard verdict card. There is no Currency field
  and nothing is read when a file is picked; where neither the document nor the price list
  states a currency, the verdict names the invoices as an error and Confirm is disabled.
  Revision candidates are applied as revisions by default, and undone on the detail page.

## F. Packing list carries volume and edits in place

- AC-F1 Converting PIs to a draft shipment copies each line's total cbm into `inbound_shipment_lines.cbm`.
- AC-F2 Lines tab shows a CBM column and a footer total; null reads "-".
- AC-F3 `/procurement-management/packing-lists/{id}/edit` no longer exists; the Details tab and the Lines tab carry a primary Edit CTA that swaps values for inputs in place, same field order; Save calls `PUT /{id}`; Cancel restores.
- AC-F4 Lines tab edit: qty, supplier, cartons, cbm per line; add line via the searchable product select; remove with confirm.
- AC-F5 `/new` still uses the create form.

## F2. PI and packing list see each other

- AC-F6 PI list has a "Packing list" column: Not converted / PL number with "n of n" and shipment status / Split with each packing list and qty / Superseded (faded revision rows); a filter "Packing list" defaults to Not converted.
- AC-F7 A converted PI's checkbox is disabled with the tooltip "In FSCU8103365"; Convert on a mixed selection names the ones skipped.
- AC-F8 PI detail header reads In packing list PL-x n of n (link), or Split with each; every line shows "In packing list" qty and remainder.
- AC-F9 Packing list Details tab carries "Source proforma invoices": PI, supplier, invoice date, revision, lines, qty from this PI of its total, amount, Open; Lines tab has "From PI"; Timeline has "Created from PI-x, PI-y by {user}"; Documents tab lists the PI files.
- AC-F10 Convert dialog pre-fills each line with its remaining qty  and offers "Add to existing draft packing list" listing this supplier's draft shipments; the link row stores the qty; a PI with any remainder reads Split, none reads converted.

## F11. Supplier codes: one matching format (R16, R17)

- AC-F11.1 The loading plan's "n codes match nothing we hold" queue is a DataGrid (fixed layout, resizable columns): Code | Supplier says | Packed | Product | Dismiss, with the count title and the "n packed" badge in the header. Usable and non-clipped at 375px (the grid scrolls in its own container) and at 1280px.
- AC-F11.2 The Product cell is a server-searched, paginated, clearable `SearchableSelect`; picking a product records the match for THAT row's code straight away and the row leaves the queue. No "Match to product" dialog on this screen; the PI detail keeps the dialog for its Matched cell.
- AC-F11.3 Dismiss on a row records a ruling with no product (`source = 'dismissed'`), takes the code out of the queue and UNBINDS the stock rows and PI lines already carrying it. It asks no confirmation: it deletes nothing and detaches nothing, and it is reversible.
- AC-F11.4 The ladder refuses a dismissed code: the next stock-list or PI upload leaves it unmatched, with no automatic bind and no badge.
- AC-F11.5 Below the grid, "n dismissed" with a Show toggle lists each dismissed code with an Undo (the existing Forget). Undo puts the code back in the queue and the ladder answers it again on the next upload; nothing else changes. Queue empty AND nothing dismissed renders no panel at all.
- AC-F11.6 `POST /api/v1/scm/supplier-code-aliases/dismiss` takes `{supplier_id, supplier_code}` behind `scm.reorder.run`, answers 201 with `source: 'dismissed'`, `product_id: null` and the rebind counts; the database refuses a dismissal carrying a product and a match carrying none.
- AC-F11.7 Refresh matching (R18) sits in the queue's header and in the loading-plan toolbar beside Upload proforma invoice, disabled until a supplier is chosen and while the pass is in flight. `POST /api/v1/scm/supplier-code-aliases/rematch` with `{supplier_id}` behind `scm.reorder.run` re-runs the ladder over the supplier's UNBOUND stock rows and the lines of their current, un-converted PIs, binding what master data can now answer and writing the auto aliases an upload would write; a bound row and a dismissed code are untouched. It answers `{inventory_bound, invoice_lines_bound, still_unmatched}` and the toast reports those counts.
- AC-F11.8 The queue collapses (R23): its header row is the toggle (chevron, title, "n packed" badge), expanded by default whenever the queue is non-empty, collapsed showing the header row alone - grid and the dismissed line both hidden - and Refresh matching stays reachable on the header either way. The choice is remembered per viewer in `localStorage` under `scm.loadingPlan.unmatchedCollapsed`; a store that refuses to read or write leaves the panel open rather than failing.

## G. SPO planner: choose the PO and the SO

- AC-G1 PO covers drill lists takes ordered by `purchase_orders.issue_date` ascending, then line expected date, then PO number; each has a checkbox, default ticked.
- AC-G2 Unticking a take lowers "PO covers" and the qty clamp; the cell reads "n of m POs".
- AC-G3 SO covered drill lists open demand lines with a checkbox each: project lines by required date, then retail by required date; default ticks in that order until packed is consumed.
- AC-G4 The location split derives from the ticked lines; the remainder sits at the suggested warehouse labelled "Unassigned".
- AC-G5 SPO qty = min(packed, PO covers, ticked + unassigned); Create SPO disabled when ticked exceeds packed, figures shown.
- AC-G6 `POST /spo` receives `po_take_ids` and `so_line_ids`; the create writes link rows on the part 2 I links table: one per (source PO line, SPO allocation, qty) and one per (SO line, SPO allocation, qty).
- AC-G7 PO detail "Allocated to" (part 1 G table) shows an SPO row per take: document pill SPO, SPO number, packing list, qty, landing warehouses with qty, arrival date, Unlink. SO detail Lines tab "Linked to" (part 1 I column) lists the SPO under the PO it fulfils with qty and arrival date, Unlink. Unlink confirms, removes the link row and reverses the qty on the SPO planner.
- AC-G8 Schedule view's "SO coverage" mode reflects the ticks.
- AC-G9 The worksheet export lists the chosen SOs per line.

## H. Unchanged (guard tests)

- AC-H1 Rank order and the priority policy call unchanged (existing `test_container_request_*` green).
- AC-H2 Outstanding PO still shown, still not subtracted.
- AC-H3 Existing PI import / list / detail / bulk delete / convert tests green; a PI without cbm converts as before.
- AC-H4 Existing SPO creation with no ticks changed produces the same allocations as today (golden fixture shipment).
- AC-H5 Existing public tokenised pages (quotation sign, purchase request view) unchanged.

## F12. Product sets on the loading plan (R19, R20, R21)

- AC-F12.1 A supplier code spelled as one of our active set codes (exact, separator-normalised or token-reordered) binds to that set automatically on stock-list and PI upload and on Refresh matching; the alias row carries `product_set_id`, rung `set_exact` / `set_separator` / `set_token_set`. `CWC605-RL` binds; `CWC605-RL-180` does not (no size rung for sets) and sits in the unmatched queue.
- AC-F12.2 The inline picker (unmatched queue) and the PI detail Match dialog offer products and sets in one server-searched list, sets badged "Set"; picking a set writes a manual alias with `product_set_id` and binds the stock rows and PI lines to the set.
- AC-F12.3 The loading-plan row for a set shows the set code with a "Set" badge and its driver member's code beneath; Need, Project, Retail, On hand, SPO, Incoming PL, PO, Earliest need-by, Project peak, Retail peak and both SO drills are the driver member's figures. Driver = the member in the fewest sets, ties by `sort_order` then product code. Worked example: `CWC605-RL` reads `CWCX605-RL`'s figures, never `CWCY605`'s.
- AC-F12.4 A driver product does not appear twice: when the supplier's statement names the set, the set row stands and no separate row for the driver product is emitted from that statement.
- AC-F12.5 Suggested qty for a set row = driver need - driver site-pool on hand - driver site-pool incoming SPO, floor 0; the header tooltip and the per-row title read the same rule.
- AC-F12.6 Send to supplier carries the set line under the supplier's own code; the xlsx and the tokenised supplier page print it as the supplier wrote it.
- AC-F12.7 Converting a PI whose line is bound to a set writes one inbound shipment line per member, qty x member quantity, each pointing at the same PI line; the PI detail still shows one set line with its placed qty; Unwind reverses all member lines together.
- AC-F12.8 Company scope: a set of another company never binds (a Sorento supplier list naming `MWC...` codes stays unmatched under Sorento).
- AC-F12.9 Migration 433 is the single alembic head; the CHECK refuses an alias naming both a product and a set, and one naming neither unless dismissed.
