# PLAN: spec icon picker - select, then Done; one asset library (SPEC-ICON-PICKER-UX)

Status: in progress (small fix track: FE only, no migration, no auth/RBAC change)

## Journey

Master Data > Product Specifications > a spec > "Choices and words" tab (edit) > Icons "+" opens
"Icons for <choice>". Today a tile click appends the icon to the draft at once, the dialog shows
no selection, and closing keeps the change.

## Findings (owner question 2: is it the designer's asset library?)

It is the same library: one table, one endpoint, one dialog component.

- Spec dialog: `ValuesAndWordsTab.tsx:660` renders the designer's own `AssetPickerDialog`
  (`dealer-kit/tag-templates/components/AssetPickerDialog.tsx`) with `libraryKind="icon"`.
- Both read `listAssets` (`dealer-kit/services/assetService.ts:59`) -> `GET /api/v1/dealer-kit/assets`
  (`sorento_crm_backend/app/api/v1/dealer_kit/assets.py:67`) -> `asset_service.list_assets`
  (`app/services/dealer_kit/asset_service.py:326`), one `Asset` table.
- The difference was the filter: the spec dialog narrows by `kind=icon` (`AssetPickerDialog.tsx:96`),
  the designer's "Icons" filter narrowed by `tag=icon` (`AssetPickerDialog.tsx:97`, `LIBRARY_TAGS`).
  A designer "Choose an image" upload is `kind=decorative` with no tags (`AssetPickerDialog.tsx:128`,
  paste `TagCanvasEditor.tsx:3323`), so it shows under "All artwork" in the designer but never in
  the icon picker, which only offers `kind=icon` (the spec save requires live icons,
  `asset_service.clean_value_icons`).
- Fix: the designer's filter narrows by KIND (Badges / Icons / Diagrams / Logos are kinds,
  `asset_service.py:63`), so "Icons" in the designer is exactly what the spec picker lists.

## Change

1. `AssetPickerDialog` gains a multi-select mode (`selectedIds` + `onDone(ids)`): a tile click
   toggles a selected state (check + ring), order = order of selection, pre-selected from the
   choice's current icons; Done applies; Cancel / X / click-away discard. An upload in this mode
   adds the asset to the grid and selects it (applied only on Done).
2. `ValuesAndWordsTab` uses it: Done replaces the choice's icon list in the draft.
3. Designer library filter uses `kind`, not `tag`.

## Tests (red first)

- `AssetPickerDialog.select.test.tsx`: toggle shows selected, order kept, pre-selected, Done
  returns ids, Cancel returns nothing, upload pre-selects, designer filter sends `kind`.
- `ValuesAndWordsTab.icons.test.tsx`: Done replaces the draft list; cancel leaves it unchanged.
