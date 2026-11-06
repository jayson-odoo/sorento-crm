# PLAN: spec icon picker - select, then Done; one asset library (SPEC-ICON-PICKER-UX)

Status: in review (small fix track: FE + one BE route, no migration, no auth/RBAC change)

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

## Add-on (owner, PROD 6 Nov): "Products are still being updated" on an Icon order save

Findings:

- The message is `CATALOGUE_READ_BUSY` (`app/services/product_spec_preview.py:286`), the ONE
  catalogue-read slot (in-process token + Postgres advisory lock) that a spec PATCH, a rule/value
  remove and a rules preview share.
- `icon_order` / `value_icons` are not reading fields (`spec_registry.py` `_READING_FIELDS`) and
  never start a re-read, but the PATCH took the slot whenever any reading field was in the
  payload, and the record page (`useSpecKeyRecord.ts` `buildPatchBody`) always sends the rules,
  cap and taken-away choices. So an Icon order save queued behind another key's re-read, which
  runs synchronously in that key's save request while holding the slot.
- The AutoCount / SS item pull takes neither the slot nor its lock (no caller outside the spec
  screens); it cannot have held it.
- Stale icon order on Details: the registry GET said `private, max-age=60`, so a refetch inside
  that minute could come from the browser's copy and overwrite the saved row in the cache.

Fix: the PATCH takes the slot only when the applied save really changes the reading (before the
commit; a refused save rolls back). A refusal names the running spec and when it started (the
holder labels its lock connection). The GET revalidates on every read (`no-cache`, ETag 304).

Tests: `sorento_crm_backend/tests/test_spec_display_only_save.py`.
