# PRICETAG-ACC-LABELS browser pass (agent-browser, headless, sandbox), 07/11/2026

Branch `claude/pricetag-accessories-labels-f9lv8o`, head 99103bd6. Sandbox DB `sorento_browse` (bootstrapped with
`scripts.bootstrap_env`), seeded by `harness/seed_browse.py` (all names invented). Backend uvicorn :8000, frontend
`npm run dev` :3000 (`.env.local` written for the pass, gitignored, removed afterwards). Navigation by sidebar
clicks from `/`. Two isolated agent-browser sessions (`accl` superadmin, `accl2` view-only user).

Seed: products SRTKS7846 (own list: CHOPPING BOARD, DRAINER, ZZDRAINER product), SRTWB7065 (host), SRTWT7202 (part),
SRTW5000, COLANDER; combo "3 in 1" on SRTWB7065 (part SRTWT7202, combo list SRTW5000 + COLANDER); published template
"ZZ Basin accessories tag" (148 x 105 mm, one Accessories box 40 x 40 mm, default product props) linked to the combo
as default LP and SP. A 40 mm box holds 1 of the 2 product cards (3-line cards, 21.3 mm each).
Read-only user (not in the harness): role `zz_viewer` with `master_data.products.view`, `dealer_kit.page.view`,
`dealer_kit.tag_templates.view`, inserted by SQL, user `browse.viewer@example.com`, so `master_data.products.edit` is
absent and the `canEdit={false}` branch (ProductCombosSection.tsx:584) renders.

| # | Check | Screenshot | Result |
|---|---|---|---|
| 1a | SRTWB7065 Overview > Combos, editable view (superadmin): "Accessories included" with SRTW5000 and COLANDER, no "Free items" in the page text | 01, 02 | PASS |
| 1b | Same, read-only view (view-only user): "Accessories included" with both items, no "Free items" | 10 | PASS |
| 1c | Product Edit page (`/edit`) has no Combos card and no "Free items" | 03 | PASS (n/a) |
| 2 | Combo "Tag preview" shows "Tag 1a: 1 accessory does not fit its box" (drawn box holds SRTW5000 only) | 02 | PASS |
| 3 | Designer, Accessories box selected: Product select lists "This tag's list (combo or product)" (selected), "Main product's list", "Fixed part 1..4 product's list", "Upgrade 1..2 product's list", "Choice group N, pick M product's list" | 05 | PASS |
| 4 | Designer, Preview combo "3 in 1": "1 accessory does not fit its box" under the Preview combo bar; H 40 to 70 mm and it disappears (restored to 40 afterwards; draft in DB is 40) | 06, 07 | PASS |
| 5 | SRTKS7846 page: "Accessories included" lists CHOPPING BOARD, DRAINER, ZZDRAINER Drainer item | 12 | PASS |
| 6a | 375px: designer warning (check 4) fits, scrollWidth 360 = clientWidth 360 | 08 | PASS |
| 6b | 375px: combo card, read-only view, no horizontal overflow (360 = 360) | 11 | PASS |
| 6c | 375px: combo card, editable view: document scrollWidth 390 vs 360, the combo's price/description/Tag preview/accessory rows run 30 px past the right edge (accessory remove X clipped) | 09-combo-card-375 | FAIL (pre-existing, see below) |

Check 6c cause: the lane's diff on `ProductCombosSection.tsx` is the two label strings only (lines 572 and 584), so this
overflow is not from the lane. The overflowing nodes are the editable branch's `grid gap-3 border-b p-3 sm:grid-cols-2`
block (price inputs, `Description`/`Tag preview` grid, 340 px wide starting at x=50), i.e. the editable combo card sits
wider than the 360 px viewport. Not bisected against main.

Console: no `[error]` entries and no uncaught page errors. Warnings only: tiptap "Duplicate extension names ['link']",
react-resizable-panels "Panel canvas-left(-rail) has an invalid configuration", Radix DialogContent missing Description.
Network: designer fetched `/api/v1/dealer-kit/products/<id>/tag-data?combo_id=<combo>` (200) when the combo was previewed.

Harness note: the sandbox tenant has no module rows, so the module guard sends every page home; the seed installs every
module for the default tenant.
