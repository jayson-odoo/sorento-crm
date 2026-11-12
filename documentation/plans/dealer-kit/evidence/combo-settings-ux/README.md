# COMBO-SETTINGS-UX browser verification (10 Nov 2026)

Run on a cloud sandbox, headless agent-browser 0.27.0 (session `combo-verify`), FE `npm run dev` on :3000,
BE uvicorn on :8000, private Postgres DB `sorento_dev` (synthetic rows, nothing shared). Branch
claude/combo-settings-ux-dg0qy2. Signed in through the normal /signin form (seeded staff user, superadmin role).

Setup notes: `alembic upgrade head` does not run from a blank DB (fails at an early revision with
`relation "system_settings" does not exist`), so the DB was built with `Base.metadata.create_all` plus the six
extra schemas, the Sorento company row, then `alembic stamp head` (combo_0001_part_labels). A fresh DB also has no
tenant module rows enabled, so the sidebar showed only OVERVIEW until all 24 modules were installed through
`app.modules.runtime.installer.install_modules`.

Navigation: `/` -> sidebar Products -> Products -> All Products -> row -> product page (breadcrumb "All Products"
for the second product). The Combos tab needed a second click after the product page loaded (first click on the
tab did nothing both times; see report).

| Step | Result | Evidence |
| --- | --- | --- |
| 1 Combos (1) tab, Overview has no combos card | PASS | 01-overview-1280.png (h3s on Overview: Basic Information, Pricing Summary, Specifications, Tracking Flags, Accessories included, Price tag templates, Sold with) , 03-combos-tab-1280.png |
| 2 One "Add accessory or product" picker, groups Accessories / Products, no "Box style" | PASS | 02-accessory-picker-1280.png; `/box style/i` test on page text = false on Overview and Combos tab |
| 3 Preview TAP starts on No pick, pick redraws with RM 899, nothing saved | PASS | 04 (no pick: all 5 options listed via `{{line.parts}}`, sell price blank), 05 (SRTKT1634SS-BL: only that tap, RM 899). After reload the picker reads No pick; the only PATCH in the log is the description I inserted |
| 4 Labels persist, Insert field dialog, All parts as a list | PASS | 04b, 06a-insert-field-dialog-1280.png, 06-bf11829-parts-1280.png: "SRTBF11829 (CABINET)" bold, "L780xW480xH400mm", "SRTWB2380 (BASIN)", "SRTMCB8083-BL (MIRROR CABINET)", "L800xW130xH700mm", "SRTWT6203-GM (BASIN COLD TAP)", "SRTW2600", no "( )", no blank line. 4 PATCHes fired on blur; reload re-read all 4 labels |
| 5 Each part prints as popover, Insert part field menu, custom line | PASS | 07-parts-line-popover-1280.png (default line), 08-insert-part-field-menu-1280.png (Code, Label, Name, Price tag description, Dimensions (L780xW480xH400mm), Dimensions (780 x 480 x 400 mm)), 09-bf11829-custom-line-1280.png ("- SRTWT6203-GM (Basin Cold Tap Brass Gunmetal)") |
| 6 375px no clipping, no page horizontal scroll | PASS | 10-combos-375-{top,a,b,c,d}.png, 11-parts-line-popover-375.png; scrollWidth 360 <= innerWidth 375, 0 elements past the right edge |

Screenshots pruned to the two kept by policy (05 picked tap, 06 parts list); the other steps are logged above.
