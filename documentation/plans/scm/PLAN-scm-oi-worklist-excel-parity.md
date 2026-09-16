# PLAN: order inquiries worklist, Excel parity batch (16 Sep 2026)

Status: BUILDING. Owner go 16 Sep 2026 08:15 MYT. Lane `feat/oi-worklist-excel-parity`, stack :3086/:8086 on the shared 0907 dev DB (no migration in this lane), pytest DB `sorento_oiwp_ci`. Phase 1 mock committed (`a1c51ca68`, `e8bab3916`); Phase 2 red tests in progress.

The purchasing team keeps its order book in `JAN - DEC ORDER 2027.xlsx` (12 sheets, one per
delivery month, columns SO DATE / S/O NO / ITEM CODE / QTY / TOTAL QTY / DELIVERY DATE /
PROJECT/CUSTOMER / SUPPLIER / PO NO). `/project-sales/order-inquiries` is to replace it. The
owner's screenshots of 16 Sep name nine gaps; this plan covers all nine in one lane.

UAC: `scm-oi-worklist-excel-parity-acceptance-criteria.md`.

## 0. Measured before writing (0915 prod copy, 8,308 rows)

| Links on the row | Rows | Meaning |
| --- | --- | --- |
| SPO only | 4,918 | importer rows; PO shown via the SPO's `from_po_number` |
| PO only, PO already has an SPO for the same product | 227 | shipment exists, page cannot show it |
| PO only, no SPO on that PO yet | 505 | bought, container not booked |
| PO + SPO | 198 | qty split across both |
| no link | 2,460 | Buy |

- `spo_allocations.po_line_id` is populated on 0 of 77,278 rows; `from_po_number` on 64,048.
  A derived SPO therefore matches on `from_po_number = purchase_orders.po_number` AND
  `spo_allocations.product_id = purchase_order_lines.product_id`.
- Measured 16 Sep with the real openness rule (`open_incoming_clauses`: line open, receipt not
  received, shipment not landed, plus `retired_at IS NULL` and `allocated > received`): only
  **37** PO-linked rows have an open SPO on their PO (29 with one SPO number, 8 with two). The
  227 first quoted counted allocations that had already landed. So: derive OPEN allocations
  only (what the planner counts as supply); a landed shipment is not "incoming". Rows with two
  open SPOs show both (the `+1` pill the column already has); no tie-break needed.
- 919 PO-linked rows sit on a PO that has two or more lines of the same product; the match is
  by PO number + product, so a derived SPO can belong to a sibling line of the same PO. Accepted:
  AutoCount does not say which line a container serves either.
- 5,250 rows are `actioned`; `enableRowSelection` blocks them, so bulk Unlink never reaches a
  fully linked row today.
- Delivery months 2026-01 to 2026-12 hold 418 to 782 rows each; 2027 holds 429; 2030-01 holds
  24 placeholders; 5 rows have no delivery date.
- The Schedule view fetches the list once with `limit=1000` (`MATRIX_FETCH_LIMIT`, and
  `MAX_PAGE_LIMIT` on the API is 1,000), sorted by delivery date ascending, and groups
  client-side. The matrix ends wherever row 1,000 falls.
- The 25 Aug "an SPO answers only an ORDER BACK row" rule is NOT in force: 27 Aug
  (`PLAN-scm-oi-draft-links.md` R5) widened `_SPO_LINKABLE_VERBS` to every linkable verb.
  Only the docstrings still say otherwise.
- Search today matches item code, `spo_ref` (legacy column), inquiry no, SO number, product
  name/code, customer name, project title/code, raiser name. Not the link documents, not the
  agent.

## 1. Rulings (owner, 16 Sep, Lavish)

- R-A Every row except `cancelled` ticks. Each Action counts its own eligible subset and
  says so in its label: "Link selected (2 of 3)". No per-row disabled checkbox.
- R-B "Link selected (N)" is the auto-link for the ticked rows (`POST /order-inquiries/auto-place`
  with `row_ids`). "Choose document (1)" is today's manual dialog and needs exactly one row.
- R-C No explanatory sub-lines in the Actions menu, none under the cards. Counts only.
- R-D Both PO lines and SPO allocations are candidates for every linkable row. Already live;
  the stale docstrings and the error code `order_inquiry_spo_not_order_back` are cleaned up.
- R-E The SPO column is derived as well as linked: the row's own SPO links plus the SPO
  allocations of its linked PO line (match above), marked "via PO". Symmetric with the PO
  column reading `from_po_number` off an SPO link (marked "via SPO"). No link is written;
  `committed_v` and every demand read stay on real links only.
- R-F The three cards become stages, left to right: Buy, Purchased (on a PO line, no
  shipment), Incoming (on an SPO, own link or via its PO). Qty sums, one unit in one stage
  only, the furthest it reached. The Linked filter follows: none / PO only / on SPO.
- R-G Month tab strip above the grid (and the matrix): one tab per delivery month that has
  rows, count on the tab, "All" first, the current month scrolled into view on first open.
  The "Delivery month" select leaves the Filters popover.
- R-H List / Schedule toggle moves to the PageHeader right slot. The "Plan until" subtitle
  goes; the date stays in the Auto link all dialog.
- R-I Schedule view renders the same toolbar as List (search, Filters, month tabs) above the
  Rows / By selects, and shows every row, next year included.
- R-J Planner ("Planning N sales orders together"): one search box, the one beside the title,
  drives Grid and List alike; the panel's own search goes. List is the default view; Grid is
  `?view=grid`. "Plan selected" from the sales orders list lands on List.
- R-K New filters: Location, Agent, SO month, PO number, SPO number. Search also matches link
  documents (`document`, `source_po_number`) and the agent code / name.
- R-L (16 Sep, from the owner's opening brief "ease their transition") the default column order
  mirrors the Excel: SO date, S/O no, Item code, Qty, Delivery date, Project / customer,
  Supplier, PO, SPO, then Agent, Location, Order inquiry, then the rest. Saved personalisation
  still wins.

## 2. Slices

### S1 Filters and search (R-K)

Backend, `GET /order-inquiries` and `/export`:
- `location` (warehouse code, equality on the row's `_LOCATION` expression),
- `agent` (sales agent id, equality on `_AGENT_ID`),
- `so_month` (`YYYY-MM` on `_SO_DATE`),
- `po_number`, `spo_number` (prefix, case-insensitive, EXISTS on `order_inquiry_links.document`;
  `po_number` also matches an SPO link's `source_po_number`).
- `query` gains three OR arms: `order_inquiry_links.document`, the SPO link's
  `source_po_number`, `SalesAgent.code` / `SalesAgent.name`.
- `/summary` gains `locations` and `agents` facets, same shape as `suppliers`
  (`[{id, label, rows}]`), each computed with its own filter dropped.

Frontend: five controls in the existing Filters popover (`SearchableSelect`, clearable, URL
synced), Clear filters resets them, `worklistParams` forwards them, the search placeholder
reads "Search S/O, item, PO, SPO, customer, agent".

### S2 Month tabs, header, Schedule toolbar (R-G, R-H, R-I first half)

Frontend only. `summary.by_month` already carries `{month, label, rows, qty}`; the strip is a
horizontal scroll of buttons that set the existing `delivery_month` state. Tabs for months
with rows only; "All" first; on first open with no `delivery_month` in the URL the strip
scrolls the current month into view but does NOT select it (All stays the default, the owner
did not ask for a pre-filter). The toggle becomes the PageHeader `actions` slot. The
`oi-plan-until` paragraph is removed. The toolbar (`ListSearchInput` + Filters + Columns +
refresh, Actions, Upload) renders in both views; the month strip sits between the cards and
the toolbar in both.

### S3 Schedule matrix endpoint (R-I second half)

Backend: `GET /order-inquiries/matrix?axis=product|sales_order|customer|agent&by=day|week|month|year`
plus every list filter. One GROUP BY over `_base(**filters)`:
`[{axis_key, axis_label, period (ISO date of the bucket start), qty, buy, po, spo, rows}]`,
where `buy` / `po` / `spo` are the stage sums of R-F. Sorted by `axis_label`, then `period`.
No limit. Week buckets start Monday, as `buildOrderInquiryMatrix` does today.

Frontend: `useOrderInquiryMatrix(params)` replaces the unpaged list fetch; the matrix builder
consumes cells instead of rows. The cell drilldown keeps calling the list with the cell's
axis + period as filters (add `delivery_from` / `delivery_to` to the list params for the
period, replacing the client-side slice).

### S4 Every row ticks; Action counts (R-A, R-B, R-C)

Frontend: `enableRowSelection` becomes `state !== 'cancelled'`. Selection-derived counts:
- `selectedLinkable` = ticked rows with `state in (raised, partly_linked, placed)` and unlinked
  qty > 0 and `ack_state` not `rejected`,
- `selectedLinked` = ticked rows with at least one link (unchanged),
- `selectedRejectable` (unchanged), `selectedConfirmable` (unchanged).
Menu labels: "Link selected (a of n)", "Unlink selected (a of n)", "Reject selected (a of n)",
"Confirm selected (a of n)"; `n` omitted when `a === n`. `disabledReason` stays a tooltip on
the menu item (the harness shows it on hover, not as a sub-line). New item "Choose document
(1)" opens `LinkDocumentDialog`; "Link selected" calls `auto-place` with
`row_ids = selectedLinkable`, toasts the result counts (`placed`, `skipped`, `after_horizon`),
invalidates the list + summary, clears the selection.

Backend: none. `auto_place_for_products(row_ids=...)` already skips rows with nothing left.

### S5 Derived SPO, stage cards, stale docstrings (R-D, R-E, R-F)

Backend:
- `links_for_rows` gains derived entries: for each PO link, the SPO allocations matching
  `from_po_number = po_number AND product_id = line.product_id`, open per
  `spo_supply.open_incoming_clauses` AND `retired_at IS NULL` AND
  `allocated_quantity > quantity_received`, emitted as `{kind: 'spo', derived: true, document,
  qty: allocation open qty, location, expected_date, ...}`. The existing SPO link's
  `source_po_number` is the mirror; the serializer marks it `derived_po: true` so the PO
  column can print "via SPO".
- `_kinds` becomes stages. Per row (corrected 16 Sep after review, the first formula double
  counted): `spo_real` = sum of the row's real SPO link qty; `cover` = sum over DISTINCT open
  allocations derived from the row's PO links (`derived_spo_open_clauses`), EXCLUDING any
  allocation the row already links to, counted once even when the row holds two PO links on
  the same PO + product; `derived_cover = least(po_linked, cover)`;
  `incoming = least(qty, spo_real + derived_cover)`;
  `purchased = least(qty - incoming, greatest(0, po_linked - derived_cover))`;
  `buy = _UNLINKED_QTY` as today. Sum over the matching set, `_NOT_OWED_STATES` dropped as
  today. `kind` filter values stay `spo | po | buy` on the wire and select rows with a
  positive stage amount. The matrix stage sums use the same per-row expressions, computed
  ONCE per row in a subquery (not three nested correlated aggregates), and drop `cancelled`
  rows only.
- The derived-SPO join carries the company predicate
  (`build_company_predicate(SPOAllocation, get_company_scope(db))`, precedent
  `spo_last_receipt_service.py`), so the expressions are built per call on the service, not
  at import time. `links_for_rows` keeps every (PO number, product) pair per row, not the last.
- `linked` filter values `po` / `spo` / `none` keep their names; `spo` now includes derived.
- Docstring and error-code cleanup: `order_inquiry_spo_not_order_back` becomes
  `order_inquiry_spo_not_linkable`; the four comment blocks quoting the 25 Aug rule are
  rewritten to state R5 of 27 Aug. No behaviour change, one test renames the code.

Frontend: cards render Buy / Purchased / Incoming in that order with the stage colours
(red / blue / purple, today's palette). `DocumentsCell` prints a "via PO" / "via SPO" tag
after a derived number; the lightbox lists derived documents under the same table with a
"via" column. A PO-linked row with no SPO prints "awaiting shipment" in the SPO column; a row
with no link prints a hyphen in both (the "Not found (new order)" string goes, per the owner's
"no explanation in the UI" rule; the bundled "Included with" headline stays).

### S6 Planner: one search, List default (R-J)

Frontend only, `FulfilmentBoardPanel.tsx` + `FulfilmentBoardListView.tsx`:
`boardViewFrom` defaults to `'list'`, URL writes `view=grid` for Grid and deletes it for
List. `productSearch` is passed into `FulfilmentBoardListView` as `externalSearch`;
`PanelDataGrid` gets `hideSearch` (or the list view filters `contributions` before handing
them over, whichever `PanelDataGrid` already supports; the coder checks). The panel's own
search box is removed. `rowMatchesSearch` and the list filter use the same matcher (SO number,
customer, agent code, item code, product name).

## 3. Order of work

Phase 1 (frontend against mocks): S2, S4, S6, then S1 controls, S5 cards + column, S3 matrix
consumer against a fixture. Phase 2 (tester-first backend): S1 params + facets, S3 endpoint,
S5 serializer + stages + cleanup. Phase 3: reviewer + security-reviewer (S1 adds five query
params to a permission-gated route; nothing else touches auth) + browser verification.

## 4. Tests

Backend (pytest, `tests/_pg_fixture.py`):
- S1: each new param filters; `po_number` prefix hits `document` and `source_po_number`;
  `query` hits a link document and an agent name; facets `locations` / `agents` drop their
  own filter; export honours the params.
- S3: matrix cells sum to the list's qty per axis × period; week bucket starts Monday; no row
  cap (seed 1,200 rows, all present); `by=year`.
- S5: derived SPO appears for a PO-linked row whose PO has an SPO for the same product; not
  for a different product; not when the allocation is received; `derived: true`; stage sums
  count a unit once (PO-linked 8 with a derived SPO of 5 = incoming 5, purchased 3); `kind=spo`
  selects the derived row; `committed_v` unchanged by a derived SPO; error code renamed.
Frontend (vitest):
- S2: strip renders one tab per month with rows, All first, click sets `delivery_month`;
  toggle in the header; no `oi-plan-until`; toolbar present in schedule view.
- S4: every non-cancelled row selectable; labels "(a of n)"; Link selected posts `row_ids`
  of the linkable subset only; Choose document needs exactly one.
- S5: "via PO" / "via SPO" tag; "awaiting shipment"; cards order and values.
- S6: default List; one search box; the search narrows the List rows.
Browser (agent-browser, via the sidebar): the UAC's B-series, evidence under
`documentation/plans/scm/evidence/oi-worklist-excel-parity/`.

## 5. Out of scope

- Moving a real link from the PO line to the SPO allocation at conversion (the owner chose the
  derived display; revisit only if the derived SPO proves wrong on prod).
- Editing qty / delivery date inline in the grid (Excel parity beyond filtering).
- Re-pointing the importer; the 14 Sep pairing rules stand.

## 6. Contract shapes

```
GET /order-inquiries?location=&agent=&so_month=YYYY-MM&po_number=&spo_number=&delivery_from=&delivery_to=
GET /order-inquiries/summary -> { ..., locations: [{id,label,rows}], agents: [{id,label,rows}],
                                  kinds: {buy, po, spo} }
GET /order-inquiries/matrix?axis=&by=&<list filters> -> { data: [{axis_key, axis_label, period, qty, buy, po, spo, rows}] }
row.links[] += { kind: 'spo', derived: true, document, qty, location, expected_date }
row.links[] (spo link) += { derived_po: true } when source_po_number is shown as the PO
```
