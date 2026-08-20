# PLAN - a proforma invoice becomes an SPO: convert, match, net, hand to AutoCount

**Status:** BOTH halves BUILT (20-21 Aug 2026), PLUS the second amendment's planner
(21 Aug, same day). Journey + three shaping decisions approved by the captain, 20 Aug 2026
(live session, while testing the new proforma screen). AMENDED the same evening: the flow
now bends through the packing list (see the Amendment section - it supersedes parts of the
original decisions and journey below). AMENDED AGAIN 21 Aug 00:40 (surface + shape - see the
"Second amendment" section) - BUILT the same day: `spo_conversion_service.suggest` now
returns `po_takes` (earliest-first PO breakdown) and `location_options` +
`suggested_warehouse_id` (ranked destination warehouses); `create` writes the chosen
warehouse's `spo_allocations` row in the same confirm when one is given. FE: the planner
table (`SpoPlannerTable.tsx`) lives on the packing-list detail page's own "SPO Planner" tab
(`/procurement-management/packing-lists/{id}`); the proforma convert hand-off and every
"where did this go" link now route there by id. `scm/incoming`'s `CreateSpoPanel.tsx` is
unmounted (kept, unreferenced) - see that section for the full write-up. Still open:
reconciling a REAL packing-list upload onto an existing DRAFT shipment row (unstarted since
the first half - see the "STILL NOT built" note at the end of the second half's write-up),
and AutoCount book-import reconciliation of a CRM SPO by number (explicitly out of scope
both halves, noted where each is relevant).

**First half BUILT, 20 Aug 2026 (same evening):** the PI -> DRAFT INBOUND SHIPMENT convert
from the Amendment's first decision. What shipped:

- `POST /api/v1/scm/proforma-invoices/convert-to-draft-shipment` (body
  `{proforma_invoice_ids: string[]}`, permission `scm.reorder.run` - the same one the
  packing-list apply path writes under, not the proforma-upload permission). One or more
  PIs, any suppliers, become ONE `inbound_shipments` row with `shipment_status = 'draft'`
  (a new value in that column's vocabulary - migration 405 extends the live check
  constraint; deliberately NOT declared on the SQLAlchemy model, so `blank_session()` tests
  that already drive the column through dead legacy values keep passing - see the comment
  at `InboundShipment.__table_args__`). Every shipment line carries its OWN `supplier_id`
  from the PI it came from - the multi-supplier-per-container rule, migration 374 -
  matching (product, supplier) PI lines across the selected invoices are merged onto one
  shipment line (quantity summed, cost quantity-weighted-averaged), never onto the header.
- Provenance: `scm.proforma_invoice_shipment_link` (one row per PI line touched by a
  convert - unique on `proforma_invoice_line_id`), pointing at the shipment line it became,
  or carrying `unmatched_reason` when the convert could not carry it across (no catalogue
  product match, or no positive quantity - `inbound_shipment_lines.product_id` is NOT
  NULL, so these are reported, never silently dropped). A partial match still creates the
  shipment; only a selection with NOTHING convertible is refused (422).
  `proforma_invoice_service.serialize()` reads this back as `converted_shipments` (header)
  and per-line `shipment_id`/`shipment_number`/`unmatched_reason`, so a PI shows where each
  line went from its own detail page.
  - the packing-list -> SPO trail (next slice) is a SEPARATE link, per the Amendment's
    "PI line -> shipment line (draft), and shipment line -> SPO line" composition - not
    built by this slice.
- Idempotency: a PI with ANY existing link row is refused with a 409 naming the invoice and
  the shipment it already went to, rather than silently doubling what counts as incoming.
  `bulk_delete` and the single `DELETE` both refuse (never cascade) a converted PI for the
  same reason, naming the shipment.
- Also folded into this pass (captain, same evening, same files): bulk delete on
  `/scm/proforma-invoices`, mirroring the PO book's bulk delete (commit d6f048f3d) -
  `POST /api/v1/scm/proforma-invoices/bulk-delete`, row-selection + one "Actions" dropdown
  shared with Convert, AlertDialog confirmation naming the count.
- FE: the "Convert to draft shipment" action lives on BOTH the proforma-invoices LIST
  (multi-select via the shared select column + Actions dropdown - the natural surface for
  picking more than one PI into one container) AND the single-PI detail page (same action,
  one-invoice selection). Both land on `/scm/incoming?shipment=<shipment_number>` on
  success (human-readable number in the URL, never the id) - `IncomingContainersView` reads
  the param once and pre-selects the matching row.
- NOT built at the time: the "Create SPO" action off the shipment, and reconciling a REAL
  packing-list upload onto this exact draft shipment row (today a later
  `/scm/packing-lists/apply` for the same container creates its own shipment unless it
  happens to share a shipment/container number - the draft's `shipment_number` is its own
  `SHIP-DRAFT-...` series precisely so it never COLLIDES with a real upload's derived
  number, but nothing yet makes the two MERGE). That merge is STILL unstarted (see below).

**Second half BUILT, 21 Aug 2026 - "Create SPO" off a shipment.** What shipped:

- `GET /api/v1/scm/inbound-shipments/{shipment_id}/spo-suggestion` (permission
  `scm.dashboard.view`) - per shipment line: the PACKED quantity (`quantity_shipped`, the
  Amendment's own correction - never the PI's invoiced figure), what an OPEN purchase order
  to the SAME supplier already covers (matched by `product_id`; a `po_ref` stated on the PI
  line(s) this shipment line came from PINS the match to that one document - the plan's "the
  stated ref outranks inference" - via the `proforma_invoice_shipment_link` table migration
  405 added; a shipment with no PI provenance at all, i.e. a real packing-list upload,
  simply has none and falls back to plain product matching), and on hand + incoming SPO
  company-wide (the same `scm.net_position_v` figures `container_request_service` reads).
  `suggested_qty = packed - po_covered - on_hand - incoming_spo`, floored at 0, editable. A
  line with nothing left to ask for reads `covered: true` (unticked by default, `reason`
  says why); a line with no supplier recorded (the n8n PDF path) reads `cannot_convert:
  true` and cannot be selected at all. `already_converted: true` + `existing_spos` when this
  shipment already has SPOs from a prior run - `lines` is empty and the caller shows the
  existing SPOs instead of a confirm screen.
- `POST /api/v1/scm/inbound-shipments/{shipment_id}/spo` (permission `scm.reorder.run`,
  same as the packing-list apply and PI-convert writes) - body
  `{lines: [{shipment_line_id, qty, include}]}`, EVERY shipment line, ticked or not (the
  "read view and write view share a structure" rule applied to a confirm screen: a line the
  buyer left unticked still needs to be accounted for in the one action, not silently
  dropped). Writes ONE `purchase_orders` header **per supplier** represented on the
  shipment - a container is routinely several factories' goods, and AutoCount POs are per
  supplier too - status `active`, `purchase_order_lines.line_status = 'open'`, so a CRM SPO
  counts as incoming/ordered the moment it exists, per the original decision. Number series:
  `NumberingService` doc_type `purchase_order_crm_spo`, prefix `CRM-SPO-...` (or a random
  `CRM-SPO-<hex8>` fallback when no rule is configured) - distinct from every AutoCount
  pattern (`######-S####`, `SPO-####/##-####`) AND from the CRM's own canonical
  `PO-{year}/{month}-####` series (`decision_service`), so an AutoCount import can never
  collide with a number this action minted.
  - **Source marker: `crm_spo`** (`spo_conversion_service.SOURCE_SYSTEM`), on both
    `purchase_orders.source_system` and `purchase_order_lines.source_system`. Every consumer
    that reads `source_system` was checked before picking it: `scm.po_ordered_v` /
    `scm.on_order_v` (migration 337) carry NO source predicate at all - only status/line
    status - so a `crm_spo` row is admitted identically to an AutoCount row (see the
    visibility answer below); `outstanding_import_service`'s "never revive a HISTORY line"
    guard keys off `history_sources.HISTORY_SOURCE_SYSTEMS`, which `crm_spo` is correctly
    NOT a member of (a CRM SPO is a live open line, never history); `purchase_order_service.
    _source_label` now maps it to `"crm"` (FE: "Created in CRM", `PurchaseOrderDetail.tsx`'s
    `SOURCE_LABELS`) so the PO detail page names it honestly rather than folding it into
    "Manual" (nobody keyed it by hand) or "Imported history" (it did not come from
    AutoCount).
  - **Provenance:** `scm.shipment_line_spo_link` (migration 406), one row per shipment line
    "Create SPO" touched - pointing at the new SPO line, or carrying `unmatched_reason`
    ("Already covered...", "No supplier recorded...", "Not selected.") - the same shape
    `proforma_invoice_shipment_link` uses. The PI -> SPO trail the journey describes is the
    COMPOSITION of the two link tables (PI line -> shipment line -> SPO line), exactly as
    the Amendment specified; nothing merges them into one row.
  - **Idempotency:** ANY existing link row for a shipment refuses a second "Create SPO"
    with a 409 naming the SPO(s) already made - never a silent double.
  - **Draft shipments convert too** (guard #5's explicit allowance): the FE copy says so
    plainly ("Draft shipment - based on this draft's own packed quantities, not a real
    packing list yet") so nobody reads a draft-based SPO as sized off a real container.
- **`scm.po_ordered_v` / `scm.on_order_v` visibility, decided and verified:** a CRM SPO
  line is admitted to `po_ordered_v` ("ordered") IMMEDIATELY - that view has no
  `source_system` predicate, only `status IN (active, received, partial, closed)` AND
  `line_status = 'open'`, both of which `create()` sets - proven by a smoke run reading the
  view straight after `create()` (100 = 40 pre-existing PO + 60 new CRM SPO, for one
  product). It is DELIBERATELY NOT admitted to `on_order_v` - that view reads exclusively
  from `spo_allocations`, which is a separate, later, explicit WAREHOUSE decision
  (`allocation_suggestion_service.approve` / `SPOAllocationService.create_allocation`) this
  action does not take on the buyer's behalf. This mirrors the codebase's own existing
  precedent exactly: `po_history_service`'s SPO-history rows are "deliberately NOT written
  to `spo_allocations`" for the identical reason. So a fresh CRM SPO shows as ORDERED
  everywhere immediately (reorder netting's own `outstanding_po` context, the PO book, the
  container request's `outstanding_po` column) and becomes INCOMING supply only once
  somebody allocates it to a warehouse - same as any other SPO, CRM-made or AutoCount-made.
- **The AutoCount handoff worksheet:** `GET /api/v1/scm/inbound-shipments/{id}/
  spo-worksheet/export` (`.xlsx`, same `openpyxl` pattern as `consolidated_packing_list`'s
  export) - one sheet, per-supplier rows of model/description/qty/unit cost/currency plus
  the CRM SPO number for reference during reconciliation. 404 until "Create SPO" has
  actually run on the shipment - there is nothing to hand off before that.
- **Reconciliation** (the next AutoCount book import matching a CRM SPO by number) is
  explicitly OUT OF SCOPE, as this plan's design notes said - the worksheet is the handoff,
  the office keys it in by hand, and a future importer would need to decide the match key
  (this plan's own open question, never answered: number vs supplier+date+lines). Not
  extended here.
- FE: a "Create SPO" panel on `/scm/incoming` (`CreateSpoPanel.tsx`), always rendered
  beside the packing list and allocation panels once a shipment is selected - line-grain,
  pre-checked, editable qty, covered/unmatched lines visible and explained, same "panel not
  modal" convention the page already uses for `AllocationPanel`. On success: toast naming
  the created SPO number(s); "Download worksheet" becomes available once a shipment has
  been converted (`already_converted: true` swaps the confirm screen for the existing-SPO
  chips + the download button). No UUIDs in the UI - only `po_number` / `item_code` /
  `supplier_name` ever render.
- **STILL NOT built** - flagged again for whoever picks this domain back up: reconciling a
  REAL packing-list upload onto an existing DRAFT shipment row (the merge named above,
  unstarted since the first half); and any price-variance ALERTING between the PI/packing-
  list cost and a matched PO's cost (out of scope per the original design notes - the two
  prices are shown side by side on the suggestion, no gate).

**Second amendment (captain, 21 Aug 00:40, live on the shipped Create SPO panel):** the
surface and the shape both move. **BUILT 21 Aug 2026, same day.**

- **Surface - BUILT.** The journey moved to `/procurement-management/packing-lists/{id}`'s
  own "SPO Planner" tab (`SpoPlannerTable.tsx`) - the procurement packing-list book over the
  same `inbound_shipments` table `scm/incoming` already used, reached the normal way (sidebar
  Procurement -> Packing Lists -> a row -> the tab), never a query-string deep link. The PI
  convert hand-off (`ProformaInvoicesView.tsx` / `ProformaInvoiceDetail.tsx`) and every
  "where did this line go" link now route there BY ID (`result.shipment_id`, never the number
  in a query string - the id was already on every one of those response shapes). `scm/
  incoming`'s `CreateSpoPanel.tsx` is UNMOUNTED from `IncomingContainersView` (the file and
  its own test stay, deliberately unreferenced) so there is one surface, not two.
- **Shape - BUILT.** Not a checkbox list. `SpoPlannerTable` is a `DataGrid`/`DataGridTable`
  ranked table (visual precedent `ContainerRequestSection`), one row per packed product, no
  checkbox column - the SPO-qty input IS the include/exclude decision, edited to 0 drops the
  line off the confirm without hiding the row (`ContainerRequestSection.renderQtyCell`'s own
  rule). Per the three asks:
  1. **Which PO covers this quantity - BUILT.** `spo_conversion_service.suggest` now returns
     `po_takes` (earliest-first per-PO breakdown) alongside the unchanged `po_covered_qty`
     total, behind a drill popover on the "PO covers" cell.
  2. **Which location the SPO should go to - BUILT.** `location_options` +
     `suggested_warehouse_id` on each line: outstanding SO / on hand / incoming SPO per
     candidate warehouse, behind a drill popover on the "Location" cell; the AFTER figure
     (`available + qty`) is computed on screen against the LIVE edited qty, never sent stale.
  3. **Ranking - BUILT.** The shared `priority.factors_for_demand_rows` policy, project
     earlier delivery first then retail - never a second sort.
- **Reuse, not reinvention - as built:** the earliest-first PO cascade discipline is COPIED
  from `project_order_inquiry_service._cascade_take` (not imported - that class is a large
  stateful order-inquiry service; importing it for one pure algorithm would drag its whole
  graph in, the same call this file's own `_stock_context` already made about
  `container_request_service`). `priority.factors_for_demand_rows` is called directly, as
  planned. `location_stock_service.location_stock_for_product` (the reorder Buy-row popup's
  own per-location reader) supplies the candidate pool + figures, rather than reinventing a
  sibling query. `allocation_suggestion_service` is reused for its WRITE
  (`SPOAllocationService.create_allocation`, identical to what `approve()` calls) - its READ
  side (`suggest`/`_candidates`) was NOT reusable as-is: that ranks EXISTING open PO lines
  already tied to a shipment, whereas this planner ranks WAREHOUSES for a not-yet-created
  SPO, a different question - see "One confirm, two writes" below for the resulting design.
- **One confirm, two writes - not a second approve step (captain's stated preference,
  honoured).** `create`'s `lines` payload gained an OPTIONAL `warehouse_id`. When a line
  carries one, the SAME action that mints the SPO also writes its `spo_allocations` row
  (`forward_match=False` per row, one forward-match sweep per distinct SPO number after -
  `approve()`'s own pattern, for the same "several warehouses can share one SPO number"
  reason). When absent (every caller before this amendment), nothing is allocated - the
  pre-existing `test_created_spo_lines_are_absent_from_on_order_v_until_allocated` invariant
  is untouched: allocation was always a decision, not a default, and still is - it is simply
  made on the SAME screen now, because this plan puts it there. No side effect of
  `create_allocation` (cost capture, shipment-line status refresh, forward match) needed to
  be separated out to make this work.

**Serves:** the proforma UAC's own named "next task" (the PI-vs-PO verification screen this
plan absorbs) - `scm-proforma-invoice-acceptance-criteria.md`. Depends on the proforma FE
(`PLAN-scm-proforma-invoice-frontend.md`, shipped this batch).

## Decisions (captain, 20 Aug)

| Question | Decision |
| --- | --- |
| What does converting create? | **A CRM SPO record + an AutoCount handoff.** A real SPO row in the CRM's PO book, marked CRM-originated, plus an exportable worksheet the office keys into AutoCount. The next book import reconciles by number. AutoCount stays the system of record for ordering; the CRM SPO gives live visibility until the import catches up. |
| Grain? | **Line-level, pre-checked.** One screen per PI: every line pre-selected with a suggested qty; the buyer unticks or trims before converting. |
| POs and stock? | **Match PO + net stock.** A PI line matching an open PO line to the same supplier LINKS to it (already ordered - no new SPO line, shown as covered). The rest net against on hand + incoming SPO, the same arithmetic as the container request. Components visible, qty editable. |

## Amendment - the flow bends through the packing list (captain, 20 Aug evening)

Live-tested with the real documents
(`fulfilment_example_files/KAILU形式发票(Sorento)260717.xlsx` and `FSCU8103365.xlsx`), the
captain corrected the flow: **PI -> packing list -> SPO**. The SPO is built from the
PACKING LIST (what actually ships), not from the PI. Grounding from the files:

- A PI is ONE factory's invoice: model, qty, unit price, and sometimes our PO doc no
  (`202605-S0060`) on the line.
- A packing list is ONE CONTAINER consolidating SEVERAL factories' PIs (FSCU8103365 packs
  AFANNI + CAIZHOU + KAILU + IDC), with vessel dates, cartons, CBM, weights.

Two shaping decisions (captain, same session):

| Question | Decision |
| --- | --- |
| What does "convert PI to packing list" do? | **Draft shipment from PIs.** Pick one or more PIs -> the system creates a DRAFT inbound shipment (`/scm/incoming`) pre-filled with their lines. When the agent's real packing list arrives, it is uploaded onto the same shipment and replaces/reconciles the draft, showing PI-vs-packed differences. **BUILT** (20 Aug evening, this session) - see the Status line at the top for the endpoint, the `draft` status, the provenance table and where the FE action lives. The "uploaded onto the SAME shipment" half is NOT built: a real packing-list upload today creates its OWN shipment unless it happens to share a number with the draft (the draft's `SHIP-DRAFT-...` series exists precisely so it never collides) - merging the two is unstarted, flagged for whoever builds the SPO half. |
| When is the SPO created? | **Separate button after packing-list apply.** The shipment page gets a "Create SPO" action she presses when ready. Suggestion logic as originally planned (match open PO lines by product / stated po_ref / delivery date, net on hand + incoming SPO), but the BASE quantity is the PACKED qty, not the invoice qty. **NOT BUILT** - this is the remaining half of this plan. |

Consequences for the sections below:

- The original decision "converting creates a CRM SPO + AutoCount handoff" STANDS, but its
  source document is now the packing list; the journey's screen moves from the PI detail
  page to the inbound shipment page.
- The original "Out of scope: auto-creating inbound shipments" is REVERSED - creating the
  draft shipment from PIs is exactly the convert function.
- PI-line links now run PI line -> shipment line (draft) - BUILT, `scm.proforma_invoice_
  shipment_link` - and shipment line -> SPO line - NOT BUILT, next slice; the PI -> SPO
  trail is the composition of the two.

## Journey (original - screen placement superseded by the Amendment above)

Actor: Ms Tee, on a proforma detail page (`/scm/proforma-invoices/{id}`) - the supplier has
sent the PI for what they are packing.

1. She presses **Convert to SPO**. The screen shows the PI's lines, every one pre-checked,
   each with: the invoice qty, any **matching open PO line** to this supplier (by product,
   then by the PI line's `po_ref` when it names one - the stated ref outranks inference),
   on hand, incoming SPO, and the **suggested SPO qty** = invoice qty, minus what a matched
   PO already covers, minus stock/incoming surplus - floored at 0, editable.
2. Lines fully covered by a PO or by stock read as covered (kept visible, unchecked by
   default, one line each says why). Unmatched-product lines (no catalogue product) cannot
   convert and say so.
3. She confirms. The system creates ONE SPO in the CRM PO book (CRM-originated source
   marker, supplier, currency and prices from the PI lines, expected date from the PI or
   asked once), writes the PI-line -> SPO-line links, and hands her the **AutoCount
   worksheet** (exportable file listing exactly what to key).
4. What she holds: a live SPO the planning views count as incoming the moment it exists,
   the worksheet for AutoCount, and a PI whose lines each show where they went (SPO line,
   linked PO line, or covered/skipped). The next AutoCount book import reconciles the CRM
   SPO by number - a match flips it to book-confirmed; a mismatch surfaces on the existing
   diff surface, never silently.

Nothing is asked that can be derived: supplier, currency, prices, quantities and the PO
matches all come off the PI and the books. Her decisions: which lines, final quantities,
and the expected date when no source states one.

## Design notes for the implementing session (verify all against code)

- **SPO record:** a `purchase_orders` header + lines with a CRM-originated `source_system`
  marker (existing rows use `scm_po_history` / `scm_spo_history` - pick a new value, e.g.
  `crm_spo`, and check every consumer that filters by source before choosing). SPO number:
  generated in a clearly-CRM series so an AutoCount import can never collide with it.
- **Reconciliation:** decide match key with the diff/import owner (number vs supplier+date
  +lines). The outstanding-import diff surface already exists; extend, do not fork.
- **PI-line links:** a link column/table from `scm.proforma_invoice_line` to the created
  SPO line / matched PO line - the audit trail step 4 renders. Prefer a small link table
  over columns if a line can split across targets.
- **PO matching:** open PO lines to the same supplier, matched by product_id; a stated
  `po_ref` on the PI line pins the match. Show remaining (ordered - received) as the
  covered qty.
- **Netting:** reuse the container-request arithmetic (open need context differs: here the
  base is the INVOICE qty, not SO need). State the formula on screen.
- **Worksheet:** follow the consolidated-packing-list export pattern
  (`consolidated_packing_list.py` + its export route) for the AutoCount handoff file.
- **Permissions:** conversion is a write to the PO book - new slug or an existing
  procurement write slug; sweep like migration 375 did if new.
- **Out of scope:** auto-creating inbound shipments (the packing list channel owns
  arrival); price variance vs PO (the verification screen ambition stays absorbed but
  variance ALERTING can land later - show the two prices side by side, no gate).
