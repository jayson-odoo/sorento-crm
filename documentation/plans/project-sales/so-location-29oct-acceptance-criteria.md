# UAC: PLAN-SO-LOCATION (fulfilment planning shows the SO line's location)

Plan: `PLAN-so-location-29oct.md`. Written on the recommended answers to the behaviour card's
five questions (crew-ask on the lane PR); revise if the owner chooses otherwise.

- AC-1: The List view of /project-sales/fulfilment-planning has a Location column directly after
  Product.
- AC-2: The cell prints the SO line's own warehouse code (`fulfilment_location`) on every row,
  whatever the suggestion is. A Buy row (for example SO428264 line 80, `Buy 42`) still shows
  its location.
- AC-3: The cell's tooltip reads `<code> · <warehouse name>`, or the code alone when the
  warehouse has no name.
- AC-4: A line AutoCount gave no location reads "No location" in red.
- AC-5: The Location header sorts the list by code, like every other column on this list.
- AC-6: The Filters menu carries a multi-select Location filter beside Status: one option per
  code on the board plus "No location" when any line has none. Picking several keeps the lines
  at any of them. The active filter shows as a "Location: ..." chip that clears it.
- AC-7: The board payload carries `fulfilment_location_name` per contribution, through the
  response model; null for a line with no location.
- AC-8: The grid view is unchanged.
