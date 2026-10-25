# PLAN: Flexible multi-level Group by on the stock status table (STOCK-GROUPBY)

Status: Review. Built: S1 to S3 (red 0bc39dda10, fix 5122eb0bd6), reviewer READY, fix round 1 (red a5461b0625, fix fb4fcc594f); four-screen browser pass running. #1752 merged; PR #1778 on main. Size M, standard track. Lane STOCK-GROUPBY, size M, standard track
(new behaviour + UI on an existing screen; no migration expected). Base: #1752's branch
`claude/stock-status-embed-sxgykp` at 67e87c24d; rebase onto main once #1752 merges.

## Owner request (18 Oct, verbatim)

"In 1752 how do i view the total by different dimensions like customer project?" then, after crew said it is not
possible: "by location is still needed, i think we can try to support flexible group by and multiple layers of group by
la, Odoo style".

## Target (to be confirmed by the behaviour card)

A "Group by" menu on the stock status table. The user picks one or more dimensions in order (for example
Location > Customer > Project); each level is a collapsible group header showing its row count and summed quantity
columns; levels can be removed and reordered. Location stays available and is the default first level, so today's view
is unchanged by default. One reusable capability, applied first to the four stock status screens (Fulfilment Planning
cell dialog Stock tab, OI line expand, project quotation stock popover, stand-alone Stock status page).

## 1. Discovery (branch at 67e87c24d)

Frontend paths under `sorento_crm_frontend/`; `CST` = `app/(protected)/project-sales/fulfilment-planning/components/CellStockTable.tsx`,
`P` = `.../fulfilment-planning/components/StockDocumentsPanel.tsx`, `ACS` = `app/(protected)/project-sales/_shared/lib/autoCountStock.ts`,
`SVC` = `sorento_crm_backend/app/services/stock_status_service.py`.

### 1.1 The stock table today

- Plain hand-rolled `<table>` (CST:542), deliberate non-DataGrid carve-out (CST:112-119). No toolbar of its own: an optional
  "Available for ..." caption (CST:510-517) then the table wrapper (CST:535). No column toggle, sort, right-click or row drag;
  the only drag is the Location column resize, remembered in localStorage `cellStockTable.locationWidth` (CST:46-51, 555-577).
- Rows: `withAutoCount` (ACS:33-95) overlays AutoCount figures and adds every unlisted location (same set as `group`,
  the rest as `other_group`). `sectionsOf` (CST:1192-1220) groups contiguous runs into sets; labels CST:90-95, 1246-1250.
  Location rows CST:593-776; set subtotal row CST:781-884; Total `<tfoot>` CST:921-992; Incoming PL row
  `IncomingPlRows` CST:1043-1164 (mounted CST:994 / 1009); empty state CST:472-494.
- Columns: chevron, Location, then `NUMERIC_COLUMNS` (CST:1277-1350): On hand, SO qty, SPO qty, Available, Available for
  Project, PO qty, Taken. `stockOnly` keeps On hand / SO / SPO / Available / PO (CST:249, 286-288). Available in AutoCount
  mode = on hand - SO + SPO (ACS:18-21); Available for Project = pool share for site pools (poolShare.ts:45-66, 83-89).
- Expand: `expanded` keyed by row (CST:339, 599), chevron only with product + warehouse (CST:607), opens
  `StockDocumentsPanel` (CST:753-772); set rows open it with `group=` (CST:345, 885-913).
- Callers with the AutoCount read: Fulfilment Planning cell dialog `BoardCellBreakdownDialog.tsx:1298`, OI line expand
  `OrderInquiryStockGrid.tsx:146`, quotation popover `QuotationStockChip.tsx:242`, stand-alone `StockStatusPageClient.tsx:55`.
  Without it: `QuotationStockChip.tsx:308`, `BorrowAddDialog.tsx:251` (selectable mode).

### 1.2 The data (one item per read)

`GET /api/v1/inventory/stock-status?product_id=` (one product only, `stock_status.py:47`; permission any of
projects.projects.view / scm.reorder.run / scm.dashboard.view, `:26-30`). Response (`SVC:180-192`, FE types
`components/stock-status/stockStatus.types.ts:5-92`):
- locations: warehouse, on_hand, so_qty, po_qty, spo_qty, forecast (SVC:146-156), listed only if a figure is non-zero (SVC:143).
- sales_orders: so_number, debtor_code, debtor_name, project_label, salesperson, doc_date, due_date, qty, warehouse_id (SVC:241-253).
- purchase_orders: po_number, supplier_code, supplier_name, dates, qty, warehouse_id (SVC:285-294). No customer / project / agent.
- spos: spo_number, supplier_code, supplier_name, dates, container, qty, warehouse_id (SVC:346-355). No customer / project / agent.
- incoming_pl: per shipment, no warehouse, supplier, customer or project (SVC:390-396).
- project_label and salesperson live on the SO header, so every line of one SO shares them (dev DB query).

### 1.3 Shared grid grouping today

- DataGrid `renderGroupHeader` draws a label divider only, rows pre-sorted, no collapse / count / totals
  (`components/ui/data-grid.tsx:143-150`, `data-grid-table.tsx:1397-1420`). TanStack `getGroupedRowModel` is not used anywhere
  (react-table 8.21.3, `package.json:31`).
- `components/common/GroupBySelect.tsx:7,36` and `components/ui/group-by-select.tsx:27` are single-level, zero importers.
- Chat history group by: a `SearchableSelect` over a fixed enum, server-ordered, not persisted (`chat-history/page.tsx:51-56,83,143,353-364`).
- Persistence: column-config payload `UserListColumnConfigPayload` (`sorento_crm_backend/app/schemas/list_query.py:163`) silently
  drops unknown keys; a group_by field would need a schema + FE type change. URL state helpers pass unknown params through
  (`lib/listNavQuery.ts:52`).
- Menu precedent: the grid's Columns toggle is a `DropdownMenu` with `DropdownMenuCheckboxItem` (`components/ui/data-grid-column-visibility.tsx:4,42`);
  Expand all / Collapse all live beside it (`components/ui/data-grid-list-toolbar.tsx:192`).

## 2. Behaviour card (v1, posted as one crew-ask 18 Oct)

### Rules

1. A **Group by** button (Layers icon, as `components/ui/group-by-select.tsx:51`) sits above the stock table on the four
   screens that carry the AutoCount read (1.1). A table without the read (Borrow dialog, the quotation's second mount, or
   the read failed) shows no button and today's table.
2. Dimensions: **Location, Customer** (debtor name; owner round 6 "Use name instead of code"), **Project** (project_label),
   **Agent** (salesperson), **Supplier** (PO / SPO supplier name), **Type** (On hand / S/O / PO / SPO).
3. Odoo picking: click a dimension to add it as the next level, click it again to remove it; level order = click order,
   so to reorder you untick and tick again. The picked levels show as one chip `Location > Customer > Project` with an x
   that resets to the default.
4. Default = **Location** alone = today's table, unchanged (sets, set subtotals, Total, Incoming PL row, a location row
   opens today's documents drill-down).
5. Location first, more levels after it: today's table stays (sets, subtotals, Total); a location row, or a set
   subtotal row over its whole set, opens its next-level groups instead of the drill-down; the last level opens its
   document lines.
6. Location not first: the top rows are the first dimension's groups; Location further down gives plain location
   groups (no sets); the Total row and the Incoming PL row stay at the bottom with the same figures.
7. A group row shows its name, its line count, and the sums of On hand, SO qty, SPO qty and PO qty. Available
   (on hand - SO + SPO, ACS:18-21) shows on Location rows and the Total only. Available for Project and Taken stay on
   location rows only, as today.
8. A line with no value for a dimension goes to a "No customer" / "No project" / "No agent" / "No supplier" group,
   listed last. So On hand, PO and SPO lines sit under "No customer", and every column still adds up to the Total.
9. Order: locations in today's order; every other dimension A to Z by name, the "No ..." group last (same as
   `groupRowsBy`, `components/common/GroupBySelect.tsx:36`). A group exists only if it holds a line, except the
   locations today's table already lists (they stay, at zero, without a chevron).
10. Document lines (last level), Odoo style inside the same table: the Location cell shows the type and document number
    (links as today: S/O, PO and SPO, P:458-492), with a muted second line carrying the values not already grouped and the
    due / expected date; the quantity sits in its own column (S/O in SO qty, PO in PO qty, SPO in SPO qty, On hand in On hand).
11. Groups start closed; each has a chevron; Expand all / Collapse all sit beside Group by.
12. The last choice is remembered per browser and used on all four screens (localStorage, like the Location column
    width CST:51).
13. Negative sums are signed and red, as today (P:754, 914-916).
14. The Fulfilment Planning dialog's search keeps today's meaning: it narrows the document lines (document no.,
    customer / supplier, agent, P:312) and opens the groups holding a match; group figures do not change with it.
15. 375px: the button and chip wrap above the table; the table scrolls sideways as today (CST:535).

### Edge cases

- SO line with no project: 1,955 of 20,419 outstanding lines (dev DB) -> "No project".
- SO line with no salesperson: 9 lines (all with sales_agent_id NULL) -> "No agent".
- PO / SPO / On hand under Customer or Project -> "No customer" / "No project" (rule 8).
- Incoming PL has no location, customer or supplier (SVC:390-396): its row stays under the Total, never grouped.
- Two lines of one SO (SRT6651-GM, Customer A 3 + 8) stay two lines under the same group.
- Inactive locations holding stock only (SRTWC8357-RL WH3-HOLD 44): listed as today, and a Location group when grouped.
- AutoCount mode has no Hold rows (P:1061), so Hold never appears in a grouping.
- No stock and no documents: today's empty state (CST:472-494), no button.

### Examples (dev DB `sorento_cagent_stack`, raw SQL with the service's predicates; names masked; not yet checked against the endpoint itself, UNVERIFIED)

Columns are On hand / SO / PO / SPO.

1. **CKS4238, Location > Customer > Project.** BRW-BB 17 / 396 / 144 / 0, Available -379 (red) -> Customer B 396
   (Project 2: 144 on one line; Project 3: 252 on three lines 100 + 76 + 76) and No customer (On hand 17, PO 144).
   BRW-IB 1 / 333 / 330 / 0, Available -332 -> Customer A 2, Customer C 330, Customer D 1, No customer.
2. **CKS4238, Customer > Project (Location removed).** Customer A 2, Customer B 396 (Project 2: 144, Project 3: 252),
   Customer C 330, Customer D 1, Customer E 1 (No project), Customer F 1; No customer = all on hand and PO. Customers
   add up to SO 731, the Total's SO.
3. **SRTWC8357-RL, Location > Project.** BRW-IB 4 / 7 / 0 / 0 (Available -3) -> Project 1: 3, Project 2: 3, Project 4: 1,
   No project (On hand 4). BRW 18 / 1 / 0 / 50 -> No project holds the S/O line of 1, On hand 18 and SPO 50.
4. **SRT6651-GM, Agent > Customer.** BRW 0 / 37 / 300 / 0 -> Agent 2: Customer D 24; Agent 3: Customer E 1;
   Agent 4: Customer B 1; Agent 5: Customer A 11 (two lines, 3 + 8); No agent: PO 300.

### Questions (max 5)

1. Dimensions offered: (a) Location, Customer, Project, Agent, Supplier, Type; (b) Location, Customer, Project only.
   Recommendation (a): every field is already in the read (SVC:241-253, 285-294, 346-355); Supplier does for PO / SPO
   what Customer does for S/O.
2. Available on a Customer / Project / Agent / Supplier / Type group row: (a) blank; (b) the signed net
   (= minus that customer's SO). Recommendation (a): a customer holds no stock, and "Customer B -396" reads like a
   shortage at Customer B.
3. On hand, PO and SPO lines when grouping by Customer: (a) a "No customer" group, last, so every column adds up to the
   Total (Odoo's "None"); (b) left out, so the customer view lists S/O only while the Total still counts everything.
   Recommendation (a): nothing disappears and the columns foot.
4. Where the choice lives: (a) remembered per browser, the same on all four screens; (b) never remembered, every open
   starts at Location; (c) per user on the server, follows the user to any machine (needs a group_by field on the
   column-config schema, `list_query.py:163`). Recommendation (a): no backend, same mechanism as the Location column
   width the table already remembers (CST:51).
5. The last level's lines: (a) document lines inside the same table, Odoo style, quantity under its own column;
   (b) today's drill-down (Type, Document, Customer / supplier, Agent, dates, Quantity) filtered to the group.
   Recommendation (a): one table, one set of columns, and it works when Location is not a level (today's drill-down is
   per location or set, P:93-122).

### Answers (crew, 18 Oct; owner can override on the mock)

Crew: "owner asked for 'flexible group by, multiple layers, Odoo style'; all five recs fit that, so crew rules".
Q1 (a) all six dimensions; Q2 (a) Available blank on non-location group rows; Q3 (a) "No customer" (etc.) group last,
columns foot; Q4 (a) remembered per browser, same on all four screens; Q5 (a) document lines inside the same table.

### Build shape (after answers + mock OK)

One reusable capability in `components/common/`: a pure `groupByLevels(lines, levels)` (tree of groups with count and
sums, "No ..." groups last) and a `GroupByMenu` (DropdownMenu with checkbox items, as the Columns toggle). Applied first
inside `CellStockTable` (so all four screens get it at once); other grids only if the owner asks. No backend change,
no migration.

## 3. Mock

`documentation/mockups/STOCK-GROUPBY/index.html`, v1 (18 Oct): item CKS4238 from the dev DB, every customer, project,
agent, supplier and document number masked. Frames: (1) default Location only with the menu open, (2) Location >
Customer > Project with BRW-BB opened, (3) Customer > Project with Location removed and the "No customer" group,
(4) 375px Location > Customer. Element-to-component map at the bottom of the mock. Lines inside a group keep the read's
order (due / expected date, SVC:254, 295); with Location not picked, a line's location moves to its muted second line;
the first column's heading names the first level.

## 4. Slices (build starts only after the owner OKs mock v1)

UAC: `stock-groupby-18oct-acceptance-criteria.md` (AC-1 to AC-23). Frontend only, no backend, no migration.
Lead pattern: tester writes every red test first (one `test(red):` commit), coder makes them green, reviewer once.

- S1 Shared capability (`components/common/group-by/`): a pure `groupByLevels(lines, levels, options)` returning a tree
  of groups (key, label, count, sums, children or lines; `No ...` groups last; exact decimal sums via minor units as
  `autoCountStock.ts` does) and a `GroupByMenu` (DropdownMenu + `DropdownMenuCheckboxItem`, level numbers, chip with x,
  Expand all / Collapse all). AC-3 to AC-7, AC-11, AC-15, AC-16.
- S2 The stock table: `stockLinesOf(read, locationOrder)` next to `withAutoCount` (`_shared/lib/autoCountStock.ts`), the
  grouped rendering inside `CellStockTable` (Location first keeps today's rows, sets and subtotals; otherwise group rows,
  then lines), localStorage `cellStockTable.groupBy`, the dialog search and jumps in grouped mode. AC-1, AC-2, AC-8 to
  AC-10, AC-12 to AC-14, AC-17 to AC-19, AC-21, AC-22.
- S3 The four screens: no caller change expected (each already passes the read); one render check per screen. AC-20, AC-23.
- S4 Reviewer, kill test, browser pass 1280 + 375 on the stand-alone page and the FP cell dialog, hand-test script.

### Test list (for the tester)

- `components/common/group-by/groupByLevels.test.ts`: one level; three levels (CKS4238-shaped fixture: BRW-BB ->
  Customer B -> Project 2 / Project 3); `No ...` last; A to Z case-insensitive; Type order; counts; decimal sums
  (`0.1 + 0.2` style); top-level sums equal totals for every level list; empty levels = flat lines.
- `components/common/group-by/GroupByMenu.test.tsx`: six ticks in order; add appends; remove shifts; level numbers; chip
  text and x; no x on Location alone; `Group by: none`.
- `.../fulfilment-planning/components/CellStockTable.groupBy.test.tsx`: default unchanged (location row opens the
  drill-down); Location > Customer > Project rows and figures; Customer first (heading, `No customer` last, Total
  unchanged, Incoming PL row); set subtotal row opens the set's groups; Expand all / Collapse all; line links and muted
  line; negative red; blank Available on group rows; no bar without the read; localStorage read, write, invalid and
  throwing storage; dialog search narrows lines without changing sums; jump opens the target location's groups.
- `_shared/lib/autoCountStock.test.ts` (extend): `stockLinesOf` builds one line per document and per non-zero on hand,
  no Incoming PL line, values per AC-2.
- One render check each: `StockStatusPageClient.test.tsx`, `OrderInquiryStockGrid.test.tsx`,
  `QuotationStockChip.test.tsx` (bar on the AutoCount mount only), `BoardCellBreakdownDialog.test.tsx`.

## 5. Contract (tester and coder both build to this; paths under `sorento_crm_frontend/`)

### 5.1 `components/common/group-by/groupByLevels.ts` (pure, generic)

```ts
export type Measure<T> = (line: T) => string | number | null | undefined;
export interface GroupDimension<T> {
  id: string;                 // 'customer'
  label: string;              // 'Customer' (menu, chip, first-column heading)
  noneLabel: string;          // 'No customer'
  valueOf: (line: T) => string | null | undefined; // trimmed; '' / whitespace / null / undefined = none
  rank?: (value: string) => number; // fixed order when given (lower first, unranked after ranked, A to Z); else A to Z
}
export interface GroupNode<T> {
  key: string;                // path, e.g. 'customer=Customer B/project=Project 2'; none = 'project=' (empty value)
  dimension: string;          // the level's id
  label: string;              // the value, or noneLabel
  isNone: boolean;
  depth: number;              // 0 = top level
  count: number;              // lines beneath
  sums: Record<string, string>; // measure id -> exact decimal string via toMinor/fromMinor ('396', '0.3', '-2')
  children: GroupNode<T>[];   // [] at the last level
  lines: T[];                 // every line beneath, in input order
}
export function groupByLevels<T>(
  lines: readonly T[], levels: readonly GroupDimension<T>[], measures: Record<string, Measure<T>>,
): GroupNode<T>[]; // [] when levels is empty; siblings: ranked/A-Z (case-insensitive), none group last
```

Decimal helpers: `toMinor` / `fromMinor` in `app/(protected)/project-sales/_shared/lib/supplyComposition.ts:32,44`.

### 5.2 `components/common/group-by/GroupByMenu.tsx`

```ts
export interface GroupByOption { id: string; label: string }
export interface GroupByMenuProps {
  options: GroupByOption[]; value: string[]; defaultValue: string[];
  onChange: (next: string[]) => void; onExpandAll?: () => void; onCollapseAll?: () => void; className?: string;
}
```

DOM: root `data-testid="group-by-bar"` (flex-wrap). Chip `group-by-chip`: text `Group by` then the labels joined by
` > ` (e.g. contains `Location > Customer > Project`), or `none` when empty. Reset button `group-by-chip-clear`
(aria-label `Reset group by`), absent when value equals defaultValue. `group-by-expand-all` (`Expand all`) and
`group-by-collapse-all` (`Collapse all`) render only when their handler is given. Trigger `group-by-trigger`
(`Group by`, Layers icon). Items: `DropdownMenuCheckboxItem` `group-by-option-<id>` (role menuitemcheckbox,
aria-checked) in options order; a ticked item shows its level number in `group-by-level-<id>` ('1', '2', ...).
A click toggles the item (add = append, remove = later levels move up) and the menu stays open.

### 5.3 `app/(protected)/project-sales/_shared/lib/stockGroupLines.ts`

```ts
export type StockLineType = 'On hand' | 'S/O' | 'PO' | 'SPO';
export interface StockLine {
  key: string;      // 'on-hand:<warehouse_id>' | 'so:<line_id>' | 'po:<line_id>' | 'spo:<allocation_id>'
  type: StockLineType;
  location: string; // warehouse code
  customer: string | null; project: string | null; agent: string | null; supplier: string | null;
  docNo: string | null;  // null for On hand
  href: string | null;   // S/O /scm/sales-orders/{sales_order_id}; PO /scm/purchase-orders/{purchase_order_id};
                         // SPO spoDetailHref(spo_number) (`lib/spo-detail`); On hand null
  date: string | null;   // S/O due_date; PO expected_date; SPO arrival_date; On hand null
  onHand: string; so: string; spo: string; po: string; // its qty in its own column, '0' in the others
}
export function stockLinesOf(status: StockStatus, locationOrder: readonly string[]): StockLine[]; // AC-1, AC-2, AC-5
export const STOCK_GROUP_OPTIONS: GroupByOption[]; // location Location, customer Customer, project Project,
                                                   // agent Agent, supplier Supplier, type Type (this order)
export function stockGroupDimensions(locationOrder: readonly string[]): Record<string, GroupDimension<StockLine>>;
export const STOCK_LINE_MEASURES: Record<'on-hand' | 'so' | 'spo' | 'po', Measure<StockLine>>; // CellStockTable column keys
export const STOCK_GROUP_STORAGE_KEY = 'cellStockTable.groupBy';
export const DEFAULT_STOCK_GROUP_LEVELS: readonly string[]; // ['location']
export function readStockGroupLevels(storage?: Storage | null): string[];  // AC-19 fallbacks, never throws
export function writeStockGroupLevels(levels: readonly string[], storage?: Storage | null): void; // never throws
```

### 5.4 `CellStockTable` (grouping only when `autoCount` is non-null)

- `GroupByMenu` above the table, options `STOCK_GROUP_OPTIONS`, default `['location']`, levels read on mount and
  written on change.
- Group row `<tr data-testid="stock-group-<key>">`, chevron `stock-group-toggle-<key>` (aria-expanded), sums
  `stock-group-<column>-<key>` for on-hand / so / spo / po; available / available-for-project / taken cells empty.
  The label cell holds the label and `1 line` / `n lines`.
- Keys under a parent row carry its prefix: under a location row `location=<code>/...`, under a set subtotal row
  `set=<section key>/...`; with Location not first the keys are `groupByLevels`' own (`customer=Customer B/location=BRW-BB`).
- Line row `stock-line-<line key>`; its document number is a link (href as 5.3); muted second line
  `stock-line-meta-<line key>`; qty cells `stock-line-<column>-<line key>`, only its own column filled.
- Location first + more levels: existing `stock-expand-<loc>` / `stock-set-expand-<section>` open the next-level
  groups; the `StockDocumentsPanel` drill-down does not mount. Location alone: today's behaviour exactly.
- Location not first: first-column heading = first level's label; no `cell-location-*` and no `stock-subtotal-*` rows;
  `stock-total-*` and `stock-incoming-pl` unchanged.

## 6. As built (18 Oct)

- Red 0bc39dda10 (46 failing) -> fix 5122eb0bd6; harness fix 4b81ee7f0d. Reviewer READY (2 should-fix + nits).
- Fix round 1 (reviewer 1-5 + browser pass on :3115): red a5461b0625 (11 failing) -> fix fb4fcc594f. R1 late read lands once;
  R2 no chevron on a location without lines; R3 stockOnly Location alone has no Expand / Collapse all; R4 a search re-opens a
  closed location; R5 aria names; F1 long names: label cells `max-w-0` + truncate/title, count outside, meta wraps.
  Skipped: reviewer nit 6 (group rows keep the subtotal style, per the mock's component map).
- origin/main merged at b077675c31 (#1752 squash): conflicts were #1752's own files, resolved as main + this lane's diff.
