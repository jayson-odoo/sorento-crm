# PLAN-SO-LOCATION: Fulfilment planning shows the SO line's location better

Status: Build (on the card's recommended answers while the crew-ask is open). Track: small fix
(UI on an existing screen, expected diff under 300 lines, no migration, no RBAC change).
UAC: `so-location-29oct-acceptance-criteria.md`.

Owner, 29 Oct (prod screenshot of /project-sales/fulfilment-planning, List view, "Planning N
sales orders together"): "this page needs to show the SO line's location better". Example row:
SO428264 line 80, product SRTWT7445-LV-..., outstanding 42, suggested Buy 42.

## Behaviour card

### What "the SO line's location" is in the data

- The core sales-order line's own warehouse: `SalesOrderLine.warehouse_id`
  (`sorento_crm_backend/app/models/order.py:555`), joined to `Warehouse.warehouse_code`
  (`sorento_crm_backend/app/models/inventory.py:34`; the same row also has `warehouse_name`,
  line 35).
- The board reads it per line into `_Row.location`
  (`sorento_crm_backend/app/services/project_fulfilment_board_service.py:1701`) and ships it as
  `fulfilment_location` (`project_fulfilment_board_service.py:5663`, schema
  `app/schemas/project_board.py:678`). Only the CODE is sent; the warehouse name is not.
- FE type: `BoardContribution.fulfilment_location`
  (`sorento_crm_frontend/app/(protected)/project-sales/_shared/types/fulfilmentPlanning.types.ts:1332`).
  Null means AutoCount gave the line no location; the line is then `unplannable` ("Needs a
  location").

### Where it shows today

List view (`fulfilment-planning/components/FulfilmentBoardListView.tsx`), columns Line, Sales
order, Agent, Customer, Product, OI, Required date, Outstanding qty, Suggested, Decided, Rank,
Verdict:

- NO column for it. It appears only indirectly, inside the Suggested / Decided text, and only
  when a supply part itself names a warehouse: `describe()` in
  `_shared/lib/supplyVocabulary.ts:436` prints `Use own location 10 (BRW-BB)` for a reserve,
  but a Buy part carries no warehouse, so the owner's example row reads just `Buy 42` and the
  line's location is invisible on the row.
- Unplannable rows say "Needs a location" in Suggested (`FulfilmentBoardListView.tsx:806`).
- Row expand (`BoardLineDecisionPanel.tsx:933`) names a location only beside a Reserve input.

Grid view (`FulfilmentBoardMatrix.tsx:351-424`): each cell already carries a location pill
strip ("BRW-BB 42", one pill per distinct line location, overflow behind "+N"). The cell
breakdown dialog has its own sortable Location column (`BoardCellBreakdownDialog.tsx:736-754`,
"No location" in destructive text when null).

So the gap is the List view.

### Examples

The cloud sandbox has no access to the dev DB (crew contract), so these come from data already
quoted in committed evidence (customers masked):

| SO | Line | Product | Location | List view today |
| --- | --- | --- | --- | --- |
| SO428264 | 80 | SRTWT7445-LV-... | (owner screenshot, not in sandbox) | Suggested `Buy 42`, no location anywhere on the row |
| SO419417 | - | SRTWC8840-SC | BRW-BB | `Use own location 8 (BRW-BB)` only while the suggestion is a reserve |
| SO415103 | - | - | BRW-* | same |

Codes seen across evidence: BRW-BB, DC1-BB, WH3-BB, MWH-BB, BRW-IB, KL-WH.

### Proposals

A. (recommended) Own **Location** column in the List view, right after Product. Cell = the
   warehouse code (`truncate` + `title`), "No location" in destructive text when null, the exact
   cell `BoardCellBreakdownDialog.tsx:736-754` already renders. Sortable like every other
   column on this list. Size 100.
B. Name the line's location inside the Suggested / Decided text, e.g. `Buy 42 for BRW-BB`.
   Longer text in a column that already truncates.
C. Row expand only (a "Location: BRW-BB" line at the top of `BoardLineDecisionPanel`). Needs a
   click per row; does not help scanning.

Components reused for A: `DataGridColumnHeader` (`components/ui/data-grid-column-header.tsx`),
the cell markup of `BoardCellBreakdownDialog.tsx:736-754`, `PanelDataGrid`
(`components/common/PanelDataGrid.tsx`) for column visibility / order (listing key
`projects.projects.view::project-fulfilment-board-list-v2`), and for a filter (Q3)
`SearchableMultiSelect` (`components/common/SearchableMultiSelect.tsx`) in the existing
Filters menu next to Status. No new component, no mock needed for A beyond this card.

### Questions (sent as crew-ask)

1. Which display? (a) own Location column next to Product, (b) in the Suggested text,
   (c) row expand. Recommend (a).
2. Code only, or code with the warehouse name in the tooltip? The name needs one extra field on
   the board payload. Recommend code in the cell, name in the tooltip.
3. Add a Location filter (multi-select) to the List view's Filters menu, next to Status?
   Recommend yes.
4. Sorting: this list sorts in the browser over the whole loaded board (every existing column;
   `PanelDataGrid` without `serverSorting`, `FulfilmentBoardListView.tsx:988`) because the board
   payload is the complete set, not a server page. Recommend the new column sorts the same way;
   moving the whole board to server sorting is a separate lane.
5. Grid view: leave as is (cells already show location pills)? Recommend leave.
