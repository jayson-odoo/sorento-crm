# ACC-COPY-TO-PRODUCTS browser pass (agent-browser, headless, cloud sandbox), 09/11/2026

Branch `claude/acc-copy-to-products-kxcij3`, PR #2280, head dd27a83e plus the two fixes this pass found (committed
with this file). Sandbox DB `sorento_browse` (bootstrapped with `scripts.bootstrap_env`), seeded by
`harness/seed_browse.py` (all names invented). Backend uvicorn :8000 (`SORENTO_ENV_FILE=.env.browse`), frontend
`npm run dev` :3000 (`.env.local` written for the pass, gitignored, removed afterwards). Navigation by sidebar
clicks from `/` (Products > Products > All Products, then the row). Two isolated sessions: `acc` (superadmin),
`accv` (role `zz_viewer`: `master_data.products.view` only).

Seed: ZZBT-1001 (source: PRESSURE PUMP with name override "Pressure pump 30PC" + remark, SOAP AND BATH BOMB SET,
FREESTANDING MIXER TAP; box style "ZZ FREE box"), ZZBT-1002 (no list), ZZBT-1003 (own list SOAP with its own
remark + TOWEL RAIL; box style "ZZ Own box"), ZZBT-1004 (no list), ZZBS-2001 (basin, other category).

| # | Check | Screenshot | Result |
|---|---|---|---|
| 1 | ZZBT-1001, editor: "Copy to other products" in the Accessories included header | 01 | PASS |
| 2 | Dialog "Copy 3 entries to other products": product grid (Code, Name, Category, Brand), search, Filters; the source row's box is disabled | 02 | PASS (after fix A) |
| 3 | Filters > Category "ZZ Bathtub": the basin leaves the grid, the dialog stays open, "Filters 1" | - | PASS |
| 4 | Header tick on a page holding every match: "3 products picked" (source left out); no "Select all 4" banner, since nothing is on another page | - | PASS |
| 5 | Tick ZZBT-1002 + ZZBT-1003, Next: dry run (POST .../accessories/copy 200, nothing written) and the confirm sentences: 2 picked, 1 with no list gets the whole list, 1 already has a list, 5 entries added, 1 left as it is, box style set on 1 | 04 | PASS (wording fix B after) |
| 6 | Copy: toast "Accessories copied to 2 products", dialog closes | 05 | PASS |
| 7 | DB after: ZZBT-1002 = PUMP (override + remark kept), SOAP, TAP, box "ZZ FREE box"; ZZBT-1003 = SOAP (its own remark), TOWEL RAIL, PUMP, TAP, box "ZZ Own box" kept; ZZBT-1004 and the basin untouched | - | PASS |
| 8 | ZZBT-1003's page lists SOAP, TOWEL RAIL, PRESSURE PUMP, FREESTANDING MIXER TAP, Box style ZZ Own box | 06 | PASS |
| 9 | Brand header sorts on the server (`GET /master-data/products/?sort=brand_name&dir=asc&status=active` 200) | - | PASS |
| 10 | 375px: button fits (07); dialog 343px wide inside 375, document scrollWidth 375 = clientWidth 375, the grid scrolls sideways inside the dialog | 07, 08 | PASS |
| 11 | View-only user: the list renders, no "Copy to other products" button | 09 | PASS |
| 12 | Console with the dialog open: no errors, no warnings | - | PASS |

Fixes this pass found:
- A. Category and Brand cells read "-": the list endpoint sends them nested (`category.category_name`,
  `brand.brand_name`), as ProductsList already reads them. The dialog now falls back the same way (vitest
  "reads Category and Brand from the nested objects").
- B. "1 product already has a list: their entries stay" now reads "its entries stay" for one product
  (screenshot 04 predates it).

Not covered here: a "Select all N" over more than one page (vitest covers the fetch, the cap and the source
exclusion), shift/drag range ticks (the shared `buildSelectColumn`, unchanged), the 422 / 404 refusals (pytest).
