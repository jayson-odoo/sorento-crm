# Browser evidence: PLAN-SO-LOCATION (head 59590013, owner answers applied)

Run 2026-10-29 by the captain, agent-browser 0.27.0 headless, `npm run dev` on :3000, backend
on :8000, local `sorento_ci` Postgres seeded with made-up data (3 SOs, 6 lines at BRW-BB,
DC1-BB, WH3-BB and one line with no warehouse). Signed in as a seeded superadmin. Navigated by
sidebar: Supply Chain > Project Demand > Fulfilment Planning, select all 3 orders, Plan together.

| AC | Result | Evidence |
| --- | --- | --- |
| AC-1 Location directly after Product | PASS | DOM header order: Line, Sales order, Agent, Customer, Product, Location, OI, ... (01) |
| AC-1 hide/show from Columns menu | PASS | Unticked: header list has no Location (02). Ticked again: back after Product |
| AC-1 drag to reorder | PASS | Dragged the Location header onto Customer: order became ..., Agent, Location, Customer, ... (03) |
| AC-2 code on every row, Buy rows included | PASS | Cells: BRW-BB, DC1-BB, DC1-BB, WH3-BB, No location, BRW-BB (01) |
| AC-3 code only | PASS | Every cell's text and `title` are the bare code. Board JSON (`/api/v1/project-sales/fulfilment-planning/board`, 200) has no `fulfilment_location_name`; `fulfilment_location` values BRW-BB, DC1-BB, WH3-BB, null |
| AC-4 "No location" in red | PASS | Computed colour is the destructive red; full text shows, no clipping (01) |
| AC-5 sorts | PASS, see note 1 | DOM click on the header button: asc No location, BRW, BRW, DC1, DC1, WH3; desc reverses it (04, 05) |
| AC-6 multi-select filter + chip | PASS | Options BRW-BB, DC1-BB, WH3-BB, No location (06). BRW-BB + No location keeps 3 of 6 lines, chip `Location: BRW-BB, No location` (07). The chip's clear brings back all 6 |
| Filter survives Grid/List switch | PASS | After Grid and back to List, still 3 filtered rows |
| AC-7 cancelled line names its location | N/A here | No cancelled line in the seed; covered by `test_c8b_a_cancelled_line_still_names_its_location` |
| AC-8 grid unchanged | PASS | Per-cell pills (`BRW-BB 10 DC1-BB 5`, `WH3-BB 8`, `No location 12`); grid filter strip has Status only (08) |
| 1280 / 375 no page h-scroll | PASS | 1280: as the first run. 375: scrollWidth 360 < innerWidth 375; table scrolls in its own scroller (09, 10) |

## Notes

1. In this session agent-browser's synthetic mouse click on a header did not change the sort,
   for Location AND for Required date alike, while a DOM `click()` on the same button sorted
   both. Not specific to this column. The first run of this pass (pre-answer head) sorted with
   agent-browser clicks. The owner's hand test sorts with a real mouse.
2. Moving Location back after Product by drag did not land; that only touches the seeded
   user's saved column order in the sandbox DB.
