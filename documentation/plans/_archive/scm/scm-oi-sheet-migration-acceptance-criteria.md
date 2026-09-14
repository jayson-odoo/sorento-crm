# Acceptance criteria: order inquiry sheet as a migration tool

Companion to `PLAN-scm-oi-sheet-migration.md`. Every criterion is verified by
test and, where it has a screen, in a real browser (agent-browser, via the
sidebar).

## Journey

The actor is the purchasing or CS operator who keeps the customer's order
inquiry Excel. Sales orders, purchase orders and shipping orders are already in
the CRM from AutoCount in real time. What the CRM does not have is the
operator's own sheet: which SO line is owed where, and which PO or SPO it is
waiting on.

1. They open Reorder (`/scm/reorder`) from the sidebar and press "Upload order
   inquiry sheet". Same button as today.
2. They pick the Excel. The preview tells them, before anything is written:
   how many rows the sheet has, how many found their sales order line, how
   many are on a line that already has an order inquiry (those are left
   alone), how many name a sales order the CRM does not hold, and how many
   cited PO/SPO documents were found or not found. Nothing else to decide.
3. They confirm. The upload runs on the worker; the drawer follows the job.
4. They open Order Inquiries (`/project-sales/order-inquiries`). Every row the
   sheet raised is there, acknowledged, with its quantity, delivery date and
   stock location as the sheet stated them, and linked to the PO or SPO
   AutoCount says that line is waiting on. Where AutoCount states nothing,
   the document the sheet's remark cites is used, wherever it had room.
5. Re-uploading the same sheet writes nothing new: every line it names is
   already raised, and the result says so.

Nobody else is told anything automatically. The worklist is the handover.

## Slice S1, the importer raises rows and pairs documents [BE]

Matching a sheet row to its sales order line

* AC-S1-1 [BE] Given a sheet row (SO, item, qty, location) and an AutoCount
  sales order line for that SO and item whose warehouse code equals the sheet
  location and whose ordered quantity is at least the row's qty, when the
  sheet is applied, then one order inquiry row is raised against that line's
  mirror line with the sheet's qty, delivery date and location. The line's
  status does not matter: open, closed and fully delivered lines all match
  (owner, 13 Sep: "those historical sales orders won't have outstanding
  already ... just need to match the quantity").
* AC-S1-2 [BE] Given two sheet rows for the same SO and item whose quantities
  together fit inside one line's ordered quantity, when applied, then both
  are raised against that line (the line is split by the sheet, never by the
  importer).
* AC-S1-3 [BE] Given the line has NO warehouse, when the sheet row names a
  location, then the line still matches and the raised row carries the
  sheet's location.
* AC-S1-4 [BE] Given the only line for the SO and item is at a different
  warehouse than the sheet row, when applied, then no row is raised and the
  row is reported under `rows_line_not_found` with reason `location_differs`.
* AC-S1-5 [BE] Given the sheet row's qty exceeds what the line has left after
  earlier rows of the same file took their share of its ordered quantity,
  when applied, then no row is raised and the row is reported with reason
  `qty_exceeds_ordered`.
* AC-S1-6 [BE] Given the sheet names a sales order the CRM does not hold, when
  applied, then nothing is created (no sales order, no line) and the SO number
  is listed under `sales_orders_not_found`.
* AC-S1-7 [BE] Given the sales order is not project class, when applied, then
  its rows are reported under `orders_not_plannable` with code
  `sales_order_not_project_class` and nothing is raised. A CLOSED or fully
  delivered project-class sales order is NOT refused: it is adopted for the
  migration with every line mirrored, and its rows are raised.
* AC-S1-8 [BE] When several lines for the SO and item match, the line whose
  required date equals the sheet's delivery date is taken; otherwise an open
  line before a closed one; otherwise the earliest required date.
* AC-S1-9 [BE] A row whose delivery-date cell reads `ORDER BACK` is raised
  with verb `ORDER_BACK`; every other row is raised with verb `ORDER`. Both
  are raised; the cell no longer decides whether a row is raised at all.

Skipping lines that already have an order inquiry

* AC-S1-10 [BE] Given the matched line's mirror line already carries any
  non-cancelled order inquiry row (raised by the board, or by an earlier
  upload), when applied, then the sheet row is NOT raised and is counted under
  `rows_already_raised`. The existing row is untouched, links included.
* AC-S1-11 [BE] Applying the same sheet twice raises rows the first time and
  zero rows the second time, with `rows_already_raised` equal to the first
  run's `rows_raised`.

Pairing to the cited PO/SPO

* AC-S1-12 [BE] Given AutoCount states no pairing for the line and the
  remark cites a PO number whose line for the same item has capacity at
  least the row's qty, when applied, then one order
  inquiry link is written from the raised row to that PO line for the row's
  full qty, `linked_by` is the uploader, and the row reads `placed`. Capacity
  is `qty_ordered` less what OTHER links already claim on that line, never
  the outstanding quantity: a closed, fully received PO line links exactly
  like an open one (the same rule `relink_to_matching_lines` uses).
* AC-S1-13 [BE] Given the remark cites an SPO number whose allocation for the
  same item has capacity (`allocated_quantity` less other links), when
  applied, then the link targets the SPO allocation. A row with verb `ORDER`
  may link to an SPO (every linkable verb may, per R5 of
  `PLAN-scm-oi-draft-links.md`). A received allocation links like a pending
  one.
* AC-S1-14 [BE] Given the cited line has LESS capacity than the row needs,
  when applied, then the link is written for the capacity, the row reads
  `partly_linked`, and the row is counted under `links_partial`.
* AC-S1-15 [BE] Given the cited document is not in the CRM, or has no line
  for that item, or its line has no capacity left, when applied, then the row
  is raised unlinked, its `cited_document` still names the document, and the
  document number is listed under `documents_not_linkable`.
* AC-S1-16 [BE] Given the remark cites two documents (`A & B`), when applied,
  then A is tried first for the whole need and B for whatever A left.
* AC-S1-17 [BE] Given the row's core line has no AutoCount-stated pairing
  (AC-S1-30) AND the remark is the literal `ORDER` or empty, when applied,
  then the row is raised unlinked and no automatic cascade over "whatever
  fits" runs for it. Auto-link stays a worklist button.
* AC-S1-18 [BE] A cited line that another SO's claim dedicates, or an
  unattributed project-bin line, is still linked when the sheet names it: the
  sheet is a person naming a document (manual semantics), not the automatic
  pass.

What the importer no longer does

* AC-S1-19 [BE] The importer creates no `sales_orders` or `sales_order_lines`
  rows under any input. `_create_orders` and the sheet-owned refresh and
  withdrawal paths are removed, with their tests.
* AC-S1-20 [BE] The importer never writes `warehouse_id` on a sales order
  line.
* AC-S1-21 [BE] The importer writes no `order_link_claim` row of its own; the
  link write's own claim (`claim_placed_on_po`) is the only one.

Result and outcomes

* AC-S1-22 [BE] The apply result carries exactly (17 keys): `ok`, `problems`
  (the reader's verdict travels on the same dict, ruling 14 Sep),
  `orders_adopted` (planning records this upload creates; 0 on re-upload),
  `orders_stamped` (headers that received the origin / project-label stamp;
  security review SF2, 14 Sep), `rows`, `rows_raised`,
  `rows_already_raised`, `rows_line_not_found` (count) with
  `line_not_found` (list of `{so_number, item_code, qty, reason}` capped at
  200), `sales_orders_not_found` (list, capped at 200),
  `orders_not_plannable` (list of `{so_number, code}`), `links_written`,
  `links_partial`, `links_from_autocount`, `documents_not_linkable` (list of
  document numbers, capped at 200), `sheets_read`, `sheets_skipped`. The retired keys
  (`orders_created`, `lines_created`, `lines_refreshed`, `lines_withdrawn`,
  `orders_owned_elsewhere`, `locations_written`, `claims_written`,
  `lines_matched`, `lines_unmatched`, `instalments`, `po_claims`,
  `rows_linked`, `link_error`) are gone.
* AC-S1-23 [BE] Every sheet row records exactly one per-row outcome on the
  job: `created` (raised), `skipped` with code `already_raised`,
  `line_not_found` reason codes (`no_line_for_item`, `location_differs`,
  `qty_exceeds_ordered`), `order_not_found`, `order_not_plannable`, or
  `unchanged` with code `restates_an_instalment` (AC-S1-38). A raised row that could not be linked is still
  `created`, with the document under the outcome's detail.
* AC-S1-24 [BE] `preview` computes the same match without writing anything
  and returns the same keys as apply (the link counts are the counts that
  WOULD be written). A second preview after an apply shows every line as
  already raised.
* AC-S1-25 [BE] Preview and apply both refuse a file whose header lacks
  `SO NO` or `ITEM CODE` with `ok: false` and a `problems` entry naming both
  columns (unchanged behaviour of the reader; there is no `missing_columns`
  key, ruling 14 Sep). The key set is still exactly AC-S1-22.

History migrates too

* AC-S1-26 [BE] Given a project-class sales order whose status is closed and
  whose every line is fully delivered, when the sheet names one of its lines
  with a fitting qty and location, then the order is adopted (a planning
  record whose mirror lines are the order's OPEN lines, as `adopt` mirrors
  them, plus the lines this upload matched, closed ones included, `qty` =
  ordered), the row is raised against that mirror line, and nothing about
  the core order or line changes. A record the board already owns gains
  ONLY the matched lines it does not yet carry, never every closed line
  (review finding 4, 14 Sep: `_authored_line_totals` sums mirror qty with
  no status filter, so unasked-for mirror lines move the reconciliation
  row's outstanding figures).
* AC-S1-27 [BE] Given a sheet row cites a PO whose only line for the item is
  closed and fully received, when applied, then the link is still written
  for min(row qty, `qty_ordered` less other links) and the row reads `placed`
  or `partly_linked` accordingly.
* AC-S1-28 [BE] Every row this importer raises carries the note stamp
  `Migrated from order inquiry sheet <file name>` (prefixed to the remark
  when there is one), so a migrated row is tellable from a board-raised one
  on the worklist without a new column. `apply` gains a `file_name` kwarg
  and the task (`process_order_inquiry_import`) passes its `filename`
  (ruling 14 Sep); with no file name the stamp ends after "sheet".
* AC-S1-29 [BE] A row raised against a line that is NOT open demand
  (`is_open_demand()` false: closed, fully delivered or covered) does not
  change `scm.committed_v`. Ruling 14 Sep: the view's project leg
  (migration 424) counts every `raised` / `partly_linked` inquiry row with no
  supply decision regardless of its line's status, so the importer raises
  such a row, writes its links, runs `refresh_link_state` (so `po_ref` /
  `spo_ref` are derived), and THEN sets `state = actioned`, `actioned_by` =
  uploader, `actioned_at` = now. The instruction is history: purchasing has
  dealt with it, the goods were delivered. Its links stay visible through
  `links_for_rows`. A row on an open line keeps the derived state. Asserted
  by querying the view before and after apply, and by the row's state.

The pairing AutoCount already states (owner, Lavish note 2, 13 Sep: "even
for those closed PO / SPO we also need to find the link based on the linkage
specified in autocount data ingested to us")

* AC-S1-30 [BE] Given the row's core sales order line has a RESOLVED
  `order_link_claim` (both `so_line_id` and a purchase side set) whose
  source is `autocount`, `po_history` or `po_upload`, when applied, then the
  row is linked to that claim's target FIRST, whatever the remark says, for
  min(row need, capacity), with the same capacity rule as AC-S1-12, and the
  link's note stamp names the claim source (`auto: autocount linkage`).
  AutoCount's linkage is the source of truth (owner, Lavish note 3, 13 Sep:
  "we don't trust the remark column in the sheet, we can refer but the
  source of truth is the autocount linkage").
* AC-S1-31 [BE] Given AutoCount's pairings leave need uncovered (or state
  nothing for the line) and the remark cites a document, when applied, then
  the cited documents are tried next for the remainder, in citation order.
  The remark is a reference, never the first word.
* AC-S1-31b [BE] Given AutoCount states a pairing to document A and the
  remark cites document B, when applied, then the row is linked to A; B is
  used only for need A left, and B stays on the row as `cited_document`
  either way so the difference is visible on the worklist.
* AC-S1-32 [BE] When several AutoCount-stated pairings exist for one core
  line, an SPO allocation is taken before a PO line (R5 of
  `PLAN-scm-oi-draft-links.md`: "SPO first then PO"), and within a kind the
  earliest `claimed_at` first (`order_link_service._claim_rows` gains
  `claimed_at` in its projection, additive, ruling 14 Sep).
* AC-S1-37 [BE] Rule 1 of `PLAN-so-project-label.md` survives: for every
  sales order the sheet names and the CRM holds, `apply_project_label(order,
  label_from_inquiry_cell(row.project), "inquiry")` is applied under the
  existing precedence gate. This is a header UPDATE on an existing order,
  not a creation, and is the only sales-order write the importer keeps.
  `tests/test_project_label_order_inquiry_import.py` moves its seam from
  `_create_orders` to `apply()` with the sales order seeded; its assertions
  stand.
* AC-S1-38 [BE] (D7) Two sheet rows identical on `(SO, item, qty, delivery
  date, location, remark)` within one upload, whatever tab each sits on,
  raise ONE row: the second records outcome `unchanged` with code
  `restates_an_instalment`, is counted in `rows`, is not raised and does not
  consume the line's ordered quantity. The customer's workbook restates its
  rows across month, roll-up and snapshot tabs.

Security review, 14 Sep (SF1, N1, N2, N3, N5, N6)

* AC-S1-39 [BE] The header stamps (`demand_origin`, project-label rule 1)
  are applied ONLY to sales orders that are not refused and have at least one
  raisable row in this upload. A sheet of 400 retail SO numbers stamps
  nothing and `orders_stamped == 0`. Preview reports the same
  `orders_adopted` / `orders_stamped` apply would produce.
* AC-S1-40 [BE] A row whose qty is not greater than zero is never matched,
  never touches the line ledger, and records outcome `skipped` with code
  `invalid_quantity`.
* AC-S1-41 [BE] A STOCK LOCATION cell longer than 80 characters cannot be a
  warehouse code: the row is reported `line_not_found` with reason
  `location_differs` and the upload does not fail.
* AC-S1-42 [BE] `apply` with no actor and no configured act-as principal
  raises nothing and links nothing: the result carries `ok: false` and a
  `problems` entry saying the upload has nobody to attribute it to. The
  route always has an actor, so this guards direct callers only.
* AC-S1-43 [BE] Two companies hold the same SO number. An upload under
  company A matches, adopts, stamps and links only A's order; B's is
  untouched and B's rows would list the number under
  `sales_orders_not_found` when uploaded under B with no such order there.
* AC-S1-44 [BE] `label_from_inquiry_cell` caps its input at 200 characters
  before the slash normalisation (the sibling `label_from_note` already has
  its caps).
* AC-S2-8 [FE] The preview panel gains a seventh tile, "Orders adopted",
  from `orders_adopted`. `orders_stamped` is on the job result only.
* AC-S1-33 [BE] A claim whose source is `order_inquiry`, `crm_supply` or
  `planner` is NOT used as a pairing source by this importer: the first is
  this feature's own output and the others are the CRM's own decisions, not
  AutoCount's record.
* AC-S1-35 [BE] Given AutoCount states SO line -> PO line, and an SPO
  allocation for the same item carries that PO's number as `from_po_number`
  (the PO was converted to an SPO in AutoCount), when applied, then the row
  is linked to the SPO allocation, not the PO line, so the worklist shows
  the SPO with its source PO beside it (`source_po_number`). The PO line is
  used only for need the SPO allocations from that PO cannot cover.
* AC-S1-36 [BE] Given the SPO allocation itself carries `from_so_line_ref`
  for the row's line (the ingest wrote a direct SO-to-SPO claim), when
  applied, then that direct claim wins and AC-S1-35's chain is not needed;
  the same allocation is never linked twice.
* AC-S1-34 [BE] The result carries `links_from_autocount` (count of rows
  that gained at least one link from AC-S1-30/31) beside `links_written`, so
  the operator can see how much the book paired versus the sheet.

## Slice S2, the upload dialog shows the new preview [FE]

* AC-S2-1 [FE] The preview panel shows seven count tiles: Rows, Will raise,
  Already raised, No SO line, Orders adopted, Rows linked (`links_written`,
  a per-row count; review finding 6, 14 Sep), Documents not found. No tile
  for scheduled deliveries, matched lines, PO links, or not-ordered. Reason
  words for `line_not_found` come from the same sentences as
  `import_outcome_codes.LABELS` so the dialog and the job page agree.
* AC-S2-2 [FE] Two chip lists below the tiles: "Sales orders not in the CRM"
  (from `sales_orders_not_found`) and "Documents we could not link" (from
  `documents_not_linkable`). Each renders its empty state as absent, not as
  an empty box. Neither heading prints a count: the server caps both lists
  at 200 and a capped count reads as a small closed problem (review finding
  11, 14 Sep; no count keys added).
* AC-S2-3 [FE] A third list, "Rows with no matching line", shows
  `line_not_found` entries as `SO · item · qty · reason` one per line, capped
  at 20 with a "+N more" tail, using the existing chip list primitive.
* AC-S2-4 [FE] The confirm button is enabled whenever `ok` is true and
  `rows_raised > 0` in the preview; disabled with the existing disabled style
  when nothing would be raised.
* AC-S2-5 [FE] The service types in `orderInquiryService.ts` match the result
  keys of AC-S1-22 exactly; the retired keys are removed from the type.
* AC-S2-6 [E2E] Uploading a two-row fixture through the dialog from the
  sidebar, confirming, and opening Order Inquiries shows the two rows, one
  placed on its cited PO and one unlinked with its citation, at 1280 and at
  375.
* AC-S2-7 [UX] No new motion. The dialog keeps its existing open/close preset;
  the tiles and lists render without entrance animation.
