# PLAN: PRICETAG-ACC-PICTURE-PICKER - accessory picture choice shows thumbnails; the row follows the pick

Status: Build. Track: small fix (expected diff under 300 lines, no migration, no auth/RBAC change).
UAC: `pricetag-acc-picture-picker-acceptance-criteria.md`.

## Owner ask (9 Nov ~11:20 MYT)

"the selection of picture here need to like got the preview of the image otherwise idk what to
choose, and after i save it is not immediately reflected here"

## Where (measured)

- Screen: product detail (and combo) "Accessories included" list, built in #2237 (price tag
  accessories card layout) on top of PRICETAG-ACCESSORIES.
- Row thumbnail: `AccessoryThumb`, `app/(protected)/master-data-management/products/[id]/components/AccessoryListField.tsx:50`,
  reads `accessory.image`.
- Picture choice: `AccessoryEntryDialog.tsx:56-69`, a `SearchableSelect` with text options only.
- Save: `AccessoryListField.tsx:298-302` writes `{...a, entry: overrides}` through
  `useReplaceOwnerAccessories` (optimistic, then `setQueryData(saved)`), the same path every edit
  on this screen uses.

## Causes

1. Options carry a label only; `SearchableSelect` already takes `renderOption` and
   `renderTriggerLabel` (`components/common/SearchableSelect.tsx:142-145`).
2. The row thumbnail reads `accessory.image`, which is ALWAYS the accessory's own first picture:
   the master-data serializer calls `tag_accessory(..., link=None, ...)`
   (`sorento_crm_backend/app/services/accessory_service.py:329`) and keeps a list row's overrides
   in `entry`, never merged in. So the chosen picture (`entry.image_id`) never reaches the row,
   neither optimistically nor from the server reply (nor after a reload).

## Fix

- FE: the row thumbnail resolves `entry.image_id` against `images` (falls back to `image`). The
  existing optimistic write already carries `entry`, so the row changes on Save with no refetch.
- BE: the master-data serializer adds `thumb_url` to each picture through the ONE rendition
  service (`image_thumbnailer.rendition_urls`, size `thumb`); `AccessoryImageOut` declares it.
  Tag/PDF payloads (`_picture_rows` for `tag_accessory`) are untouched.
- FE image component: IMAGE-UNIFY P3's `components/common/AttachmentImage.tsx` does not exist on
  main yet (`PLAN-image-unify-03nov.md` "Frontend"). This lane adds it in the plan's shape
  (`thumbUrl`, `url`, lazy, `decoding="async"`, falls back to the original then a placeholder,
  never builds a URL) and uses it for the option, the selected value and the row thumbnail.

## Tests (red first)

- vitest: a Picture choice option renders a thumbnail (`img` with the picture's thumb_url) and so
  does the selected value; after Save the row thumbnail shows the chosen picture with no refetch.
- pytest: the owner list reply carries `thumb_url` per picture.
