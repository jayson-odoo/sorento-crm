# UAC: PLAN-SO-LOCATION (fulfilment planning shows the SO line's location)

Plan: `PLAN-so-location-29oct.md`. Owner answers to the behaviour card, 29 Oct: Q1 (a) own
column after Product, a normal PanelDataGrid column (reorder, hide/show); Q2 code only, no
warehouse name; Q3 multi-select Location filter; Q4 sorts like the other columns.

- AC-1: The List view of /project-sales/fulfilment-planning has a Location column directly after
  Product. It is an ordinary PanelDataGrid column: it hides and shows from the Columns menu and
  drags to a new place like the others.
- AC-2: The cell prints the SO line's own warehouse code (`fulfilment_location`) on every row,
  whatever the suggestion is. A Buy row (for example SO428264 line 80, `Buy 42`) still shows
  its location.
- AC-3: Code only (e.g. BRW-BB). No warehouse name anywhere; the cell's tooltip is the code.
- AC-4: A line AutoCount gave no location reads "No location" in red.
- AC-5: The Location header sorts the list by code, like every other column on this list.
- AC-6: The Filters menu carries a multi-select Location filter beside Status: one option per
  code on the board plus "No location" when any line has none. Picking several keeps the lines
  at any of them. The active filter shows as a "Location: ..." chip that clears it.
- AC-7: A line CS cancelled still names its location (it does not read "No location").
- AC-8: The grid view is unchanged.
