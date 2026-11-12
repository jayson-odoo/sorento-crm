# UAC: List search chips (SEARCH-CHIPS), slice 1

Status: draft on the recommended answers (Q1a, Q2a, Q3a, Q4a, Q5b); re-cut once the owner answers.
Plan: `PLAN-search-chips-12nov.md`.

## Backend: `GET /api/v1/scm/sales-orders`

- B1. `query` accepts repeated values (`query=A&query=B`); a single `query=A` behaves exactly as
  today (same rows, same total).
- B2. Several values: a row is returned when it matches ANY value, each value matched over the
  same fields as today (SO number, debtor name, linked customer name, project, PO ref, folded PO
  ref key, a line's product code/name, agent code/person).
- B3. An order matching two values (or matching on two lines) is ONE row; `total` counts it once.
- B4. A value containing a comma is one value (never split): `query=Acme, Trading` matches the
  text "Acme, Trading".
- B5. Blank and duplicate values are ignored (case-insensitive duplicates count once).
- B6. More than 200 values -> 422 with "at most 200 values".
- B7. Values combine with every filter (status, customer, dates, ...) as AND, and with sort and
  paging unchanged; page 2 of a multi-value search continues the same order.
- B8. One SQL statement for the list regardless of the number of values (no per-value query);
  the WHERE uses `ILIKE ANY (ARRAY[...])` per column, not one OR branch per value.

## Frontend: shared `ListSearchInput` (chips mode)

- F1. Without the `chips` prop the box behaves exactly as today (existing tests stay green).
- F2. Enter or comma turns the typed text into a chip and empties the text; blank text makes no
  chip; a duplicate (case-insensitive) is not added.
- F3. Paste with commas or new lines -> one chip per non-blank piece; paste with only spaces ->
  split on spaces only if every piece contains a digit, else one chip.
- F4. Each chip has an x labelled "Remove <value>"; Backspace in empty text removes the last chip;
  the box's clear x removes all chips and the text.
- F5. Typed text not yet Entered is searched live (debounced) together with the chips, under the
  same rule.
- F6. Chips that do not fit on one line collapse into "+N"; focusing the box shows every chip.
- F7. Keyboard only: Tab reaches the box, chips are removable by Backspace / arrow + Delete.
- F8. At 375 px the box fills the row and nothing clips.
- F9. Over 200 values: the first 200 are kept and the box says so.

## Frontend: Sales Orders list

- S1. The request carries one `query` param per chip (plus the typed text).
- S2. Opening a row and coming Back restores the chips; prev/next on the record walks the
  chip-filtered list (`parseDetailSearch` reads every `query`).
- S3. Adding or removing a chip returns to page 1; sort and filters are kept.
- S4. Refresh keeps the chips (Q5b): the chips are in the address bar as they change.
- S5. Ticked-row export exports the rows the chip result shows.

## Standing rules that apply

Lists & grids: server-side sort holds on page 2; one toolbar row. Filters & search: search
survives prev/next and Back, the page and its search are in the address bar. Wording: no "how
this works" text. 375 + 1280 usable.
