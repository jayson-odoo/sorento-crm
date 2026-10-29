# Browser evidence: PLAN-SO-LOCATION

Run 2026-10-29, agent-browser 0.27.0 headless, dev server (HMR) on :3000, backend on :8000,
local `sorento_ci` Postgres seeded with made-up data (3 SOs, 4 products, warehouses BRW-BB
"Brickfields Warehouse", DC1-BB "Distribution Centre One", WH3-BB with no name, one line with no
warehouse). Signed in as a seeded superadmin, then sidebar clicks: Supply Chain > Project Demand >
Fulfilment Planning, tick all 3 orders, "Plan together" (the List view is the board that opens).

| AC | Result | Evidence |
| --- | --- | --- |
| AC-1 Location directly after Product | PASS | Header order read from the DOM: Line, Sales order, Agent, Customer, Product, Location, OI, ... (01) |
| AC-2 own warehouse code on every row | PASS | Buy-suggested rows (Buy 34 in the tiles) still show BRW-BB / DC1-BB / WH3-BB (01) |
| AC-3 tooltip `CODE · name`, code alone if no name | PASS | `title` attr read from DOM: `BRW-BB · Brickfields Warehouse`, `DC1-BB · Distribution Centre One`, `WH3-BB` (native title, so no pixel screenshot of it) |
| AC-4 "No location" in red | PASS, with a cosmetic note | Red text on SO900003 line 1 (01, 07). Note 1 below |
| AC-5 header sorts | PASS | Asc: No location, BRW, BRW, DC1, DC1, WH3 (02). Desc reverses it (03). Blank sorts first ascending |
| AC-6 multi-select Location filter, "No location" option, chip | PASS, with a note | Options: BRW-BB, DC1-BB, WH3-BB, No location (05). Picking BRW-BB + No location keeps 3 of 6 lines and shows chip `Location: BRW-BB, No location` (06, 07). Chip x clears it back to 6 rows. Note 2 below |
| AC-7 payload `fulfilment_location_name` | PASS (indirect) | Tooltips above can only come from that field; null case renders "No location". Payload JSON not inspected directly |
| AC-8 grid unchanged | PASS | Grid still shows per-cell pills (`BRW-BB 10`, `DC1-BB 5`, `No location 12` + "1 needs a location"), and only the Status filter (08, 09) |
| 1280px usable, no page h-scroll | PASS | documentElement.scrollWidth 1280 = innerWidth 1280 |
| 375px usable, no page h-scroll | PASS | documentElement.scrollWidth 360 (scrollbar) < innerWidth 375. The table scrolls inside its own scroller; Location reachable (11); filters popover shows Status and Location (12) |

Screens: 01 list 1280, 02/03 sorted asc/desc, 04 filters popover, 05 Location open,
06 two picked, 07 filtered with chip, 08 grid 1280, 09 grid 375, 10 list 375,
11 list 375 scrolled to Location, 12 filters 375.

## Anything off

1. "No location" is clipped to "No locat..." at the Location column's default 100px width, at both 1280
   and 375 (01, 07, 11). The code cells have `truncate`; the red span has neither `truncate` nor a
   `title`, so the cell clips it. The red label has no tooltip, which is consistent with AC-3 but
   means the full phrase is only readable by widening the column. Consider `size: 110+` or a
   `title="No location"`.
2. The two filters stack vertically (Status above Location) inside the popover rather than sitting
   side by side. Same at 1280 and 375. Probably fine ("beside" read loosely); flagging in case
   it was meant literally.
3. Console: only the existing Radix `DialogContent` missing-Description warning. No page errors.

## Environment notes (for whoever reruns this)

- The `.test` TLD fails the backend email validator, so the seed user is `verify@example.com`.
- The empty DB has no installed modules, so the sidebar hides the module groups until
  `install_modules(db, "__default__", all_keys, None)` runs. The seed script does this.
- `sorento_crm_frontend/.env.local` was written (gitignored, not committed).
