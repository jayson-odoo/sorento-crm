# UAC: product-grain plan buys confirmed project demand without a reorder level (#794)

- AC-1 A product on the reorder_level basis with NO level (no buyer override, master 0) and
  N units of confirmed unplaced Order Inquiry Buy suggests N (MOQ/multiple applied), reason
  "project buy: N confirmed unplaced Buy", on a `buy` row; the order sheet row shows
  Suggested qty N, Project N.
- AC-2 The same product still shows the level as unset (panel "none set today", "Set
  AutoCount level to X" offered); no `needs_level` row is emitted beside the buy.
- AC-3 A no-level product with retail-only demand still emits `needs_level` and no buy.
- AC-4 A no-level product with confirmed Buy and no linked supplier emits `exception`
  carrying the project need; the summary row still states suggested = project need.
- AC-5 Products WITH a level plan byte-identical to before (existing per-product tests green).
- AC-6 No data change on prod is required; CSK2800-QT reads Suggested 914 on the next plan
  after deploy.
