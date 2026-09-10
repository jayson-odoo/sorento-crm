# Local supplier OI routing - Phase 3 evidence run (10 Sep 2026)

Lane stack: FE http://localhost:3080 -> BE :8080 -> DB `sorento_ai_automation_lsor` (prod copy,
migrations 510/511 applied, 249 countries seeded). agent-browser session `lsor-p3`, headless,
`npx -y agent-browser@0.27.0`. Login via E2E_EMAIL/E2E_PASSWORD (superadmin), sidebar navigation
from `/` throughout, no deep URLs typed by hand (only `back`/reload during the flow).

## Backfill (`scripts/backfill_supplier_country.py`, run from `sorento_crm_backend/` with the
primary venv python, against the lane DB via its own `.env`)

```
$ venv/bin/python scripts/backfill_supplier_country.py --dry-run
company scope: incumbent (00000000-0000-0000-0000-000000000001)
mode: DRY-RUN (no writes)
matched: 480
changed: 0

$ venv/bin/python scripts/backfill_supplier_country.py --apply
company scope: incumbent (00000000-0000-0000-0000-000000000001)
mode: APPLY
matched: 480
changed: 480

$ venv/bin/python scripts/backfill_supplier_country.py --dry-run
company scope: incumbent (00000000-0000-0000-0000-000000000001)
mode: DRY-RUN (no writes)
matched: 0
changed: 0
```

Idempotent as required (second dry-run: 0/0). Post-backfill: `countries` = 249 rows,
480 suppliers now carry `country_id = MY` (`select count(*) from suppliers where country_id =
(select id from countries where code='MY')` = 480).

## AC-3.1 - Master Data > Countries

Navigated: sidebar Products > Reference Data > Countries (`/master-data-management/countries`).

- 249 rows confirmed (DB `select count(*) from countries` = 249; grid paginates 50/page, 5 pages).
- Search "mala" -> Guatemala, Malawi, **Malaysia** (contains-match on name, finds Malaysia).
- Edit: opened Malawi, renamed to "Malawi ZZT TEST" (`PUT .../countries/{id}` 200), reopened,
  reverted to "Malawi" (`PUT` 200 again). Grid shows "Malawi" after revert.
- Add: created `ZZ` / "ZZ Testland" (`POST .../countries` 201). Searched "ZZ Testland", found the
  row, clicked its Delete icon -> deferred-countdown toast appeared ("Deleting in 4s Cancel
  Malaysia" pattern, here for ZZ Testland) backed by `POST /api/v1/pending-actions` (202) and
  `GET /api/v1/pending-actions/current` polling. Did not cancel; let the countdown lapse via
  ordinary tool round-trips (no manual sleep). Confirmed via DB: `ZZ` row gone, count back to 249.
- Delete on Malaysia (480 referencing suppliers post-backfill): clicked Delete -> same
  deferred-countdown flow started (`POST /api/v1/pending-actions` 202, entity_id =
  `3574a138-85ff-406f-bffd-822bc5101a28` = Malaysia's id). Let it lapse. Malaysia is STILL in the
  DB afterwards (`select code,name from countries where code='MY'` -> `MY | Malaysia`) - the
  server-side commit was refused per AC-2.4 (409, referenced-supplier count), proven by the row
  surviving the window rather than by inspecting the (in-memory, not DB-backed) pending-action
  record's own error text.

No console errors at any point on this screen.

## AC-3.2 - Procurement > Suppliers > MOCHA SDN BHD

Navigated: sidebar Procurement > Suppliers (`/procurement-management/suppliers`).

- Search "MOCHA" -> list column **Country = Malaysia** for `401-M004 MOCHA SDN BHD` (and for
  `404-R010 RELATED CREDITOR - MOCHA SDN BHD`).
- Opened MOCHA SDN BHD detail, clicked Edit: Country `SearchableSelect` shows **Malaysia**
  (clearable combobox, value bound to `country_id`).
- Search "XIAMEN TAIYANG" (a China supplier, `400-X008`/`400-X006`, no country row created by the
  name-heuristic backfill): list Country column shows **"-"** (blank), confirming the negative
  case.

No console errors.

## AC-3.3 - Fulfilment planning, List view - SO369758

Query used to find the order (lane DB, `sorento_ai_automation_lsor`):

```sql
WITH last_po AS (
  SELECT DISTINCT ON (pol.product_id) pol.product_id, po.supplier_id
  FROM purchase_order_lines pol JOIN purchase_orders po ON po.id = pol.purchase_order_id
  ORDER BY pol.product_id, po.issue_date DESC NULLS LAST, po.created_at DESC
)
SELECT DISTINCT so.so_number, p.product_code
FROM last_po lp
JOIN products p ON p.id = lp.product_id
JOIN projects.sales_order_lines psl ON psl.product_id = p.id
JOIN projects.sales_orders pso ON pso.id = psl.project_sales_order_id
JOIN sales_order_lines csol ON csol.id = psl.core_sales_order_line_id
JOIN sales_orders so ON so.id = csol.sales_order_id
WHERE lp.supplier_id = '81dbcdbf-4391-4aa2-aad3-42493869002c'  -- 401-M004 MOCHA SDN BHD
  AND so.status = 'open';
```

**SO369758** (JUBIN BMS (1990) SDN BHD (PROJECT)) has both a local line (`MAB7049-WH`, newest-PO
+ primary link both MOCHA SDN BHD / MY) and overseas lines (`B2154-NL`, `CB6622`, etc., Chinese
suppliers with no country).

Navigated: sidebar Supply Chain > Planning > Project Demand > Fulfilment Planning, searched
`SO369758`, checked its row checkbox, clicked "Plan SO369758" (bulk "Plan together" action) ->
opened the board at `?orders=SO369758`, switched to **List** view.

- Line 41 (`MAB7049-WH`, local): Suggested cell reads **"Buy 50 Local"** - `Buy N` + `Local` pill,
  present on Decided cell too once decided/confirmed. AC-1.1 satisfied.
- Line 31 (`B2154-NL`, overseas): Suggested cell reads **"Buy 100"** - no pill. AC-1.1 negative
  case satisfied.
- Expanded Line 41's OPTIONS table: RESERVE / BORROW / BUY / DECISION rows render with no
  `ladder-option-reason-*` sub-line under any option label (AC-1.2); the OPTIONS mini-table
  (RESERVE/BORROW/BUY/Order back) shows **"Buy Local"** on the Buy row (AC-1.3). Line 31's
  equivalent OPTIONS table shows plain **"Buy"**, no pill.
- Saved decision on Line 41 (`PUT .../fulfilment-planning/lines/{pso_id}|41|MAB7049-WH|2026-12-28
  /draft` 200) and Line 31 (`PUT .../lines/{pso_id}|31|B2154-NL|2026-12-28/draft` 200). Both cells
  moved to Decided = "Buy 50 Local" / "Buy 100" respectively.
- Clicked **Confirm (2)** -> modal "Confirm 2 lines across 1 order?" -> Confirm ->
  `POST /api/v1/project-sales/fulfilment-planning/confirm-all` 200. Both rows now show
  "Confirmed".
- **Order Inquiry worklist** (sidebar Procurement > Supply Chain > Order Inquiries, searched
  nothing extra - the row already carried SO369758): exactly **one** row present,
  `B2154-NL on SO369758` (`OI-000018`, supplier XIAMEN TAIYANG TECHNOLOGY CO.,LTD, "Confirmed by
  Teh Jayson"). The local `MAB7049-WH` line is **absent** - grep for "MAB7049" over the worklist
  snapshot returns nothing; only one `Select ... on SO369758` row exists in the grid.
- **Decision trail**: opened the board Grid view, clicked into the `MAB7049-WH` / 28 Dec 2026 cell
  (`BoardCellBreakdownDialog`) - it reads `Suggestion: Buy 50` / `Decision: Buy 50`, "Decided rev
  1" marker. The equivalent `B2154-NL` cell (visible on the same Grid, `28 Dec 2026` column)
  carries its own green "Decided" checkmark reading `Buy 100`. Both lines' Buy decisions are
  visible on the board this way. The `BoardTrailPopover` ("How this decision was reached") is
  gated on suggestion/decision DIVERGING (it renders inside the row's "WHY THIS DIFFERS" section)
  - since both lines here were confirmed exactly as suggested, that specific sub-component never
  mounts; the cell dialog's own Suggestion/Decision pair is what actually carries "both Buys" on
  this data, and is reported as such rather than forcing the divergence case.

No console errors at any point in this flow.

## AC-3.4 - Add a borrow

Same board/List view, `SO369758` Line 5 (`B2154-NL`, "BRW 40 (BRW)" suggested, undecided,
candidates present). Expanded row, clicked **Add a borrow**.

- Source table columns: **Location, Where, On hand, SO qty, SPO qty, Available, Available for
  Project, PO qty, Taken** - nine columns, a radio per row, no Free / Committed / After borrow
  columns (AC-1.4/AC-3.4 satisfied exactly).
- First row `BRW-NTC` carries the **Recommended** badge and is pre-selected (radio checked=true).
- Expanded `BRW-NTC` -> `StockDocumentsPanel` ledger renders (Type/Document/Customer-supplier/
  Agent/Doc date/Delivery-expected/Quantity), 3 S/O rows against `SO365271` (OTM GROUP SDN BHD,
  117 each, total 351). No row carried a `This line` badge for this particular donor - that badge
  marks a row belonging to the CURRENT line's own sales order, and this donor's ledger happens to
  hold none of SO369758's own rows on this real data; the badge mechanism itself was not directly
  observed lit up, reported honestly rather than claimed.
- Changed Quantity 117 -> 50: the sentence updated live to **"After borrowing 50: BRW-NTC goes
  short by 284 - an Order Inquiry will be raised for BRW-NTC on confirm."** (AC-1.6).
- Screenshot at **1280px**: `borrow-modal-1280.png` (modal widens to fit the table, no horizontal
  page scroll).
- Screenshot at **375px**: `borrow-modal-375.png` (scrolls inside its own container; Quantity,
  After-borrowing sentence, Reason and actions all reachable).
- Filled Reason, clicked **Add the borrow** -> succeeded (dialog closed, no page error); the
  row's OPTIONS/DECISION updated in place to `Borrow (other) 50 BRW-NTC` (client-side draft
  state - the row's own top-level status stayed "Not decided" since only "Save decision" persists
  a line, which was intentionally NOT clicked). Reloaded the page afterwards and confirmed Line 5
  reverted to its original "Suggested" state, so no stray write was left on this real order.

No console errors from this flow; a pre-existing, lane-unrelated Radix `AlertDialogContent`
missing-description a11y warning and a `Demo1Layout` React key warning were present in the
console throughout the session (shell-level, unrelated to this feature, not introduced by this
change).

## Summary (pass/fail)

| AC | Result |
| --- | --- |
| AC-3.1 | PASS |
| AC-3.2 | PASS |
| AC-3.3 | PASS (decision-trail read via the cell breakdown dialog's Suggestion/Decision pair, not the divergence-only `BoardTrailPopover`) |
| AC-3.4 | PASS (`This line` ledger badge not observed on this donor's real data - noted, not a defect claim) |
