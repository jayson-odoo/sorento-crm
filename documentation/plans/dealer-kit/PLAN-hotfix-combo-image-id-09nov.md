# PLAN: HOTFIX-COMBO-IMAGE-ID (prod hotfix, 9 Nov 2026)

Status: implemented (small fix track: BE only, 1 schema line + 1 test, no migration, no auth change)

UAC: `hotfix-combo-image-id-acceptance-criteria.md`

## Problem

Prod, product SRTWB7065: the Combos card shows "Internal server error" / "Could not load combos".
`GET /api/v1/master-data/products/{id}/combos`, `GET|PUT /product-combos/{combo_id}/accessories` and
`GET|PUT /products/{id}/accessories` 500 with `ResponseValidationError` at
`('response', ..., 'images', 0, 'id') Field required`.

Cause: a catalogue product listed as a free item (#2237) is built by
`app/services/accessory_service.py` `tag_product_entry`, whose `images` carry the product's lead photo
as `{attachment_id, url, colour_name, colour_hex}`: a product photo is not an accessory picture row, so
it has no picture id. `app/schemas/accessory.py` `AccessoryImageOut.id: str` requires one. Only a free
product WITH a photo trips it (empty `images` otherwise).

## Fix (simplest thing)

`AccessoryImageOut.id: Optional[str] = None`. The response then carries `"id": null` for a product
photo, as the legacy single-picture branch already builds (`tag_accessory`, `"id": None`).

Rejected: inventing `id = attachment_id` in `tag_product_entry`. That id would masquerade as an
accessory picture id (the `entry.image_id` override references `accessory_images.id`) and would change
the price tag payload for pinned rows. The schema change touches only the CRUD read response.

## Architecture

- Layer: BE response schema only (`app/schemas/accessory.py`). No service, route, model or FE change.
- FE: the picture choice lists pictures only for `kind === 'accessory'`
  (`AccessoryEntryDialog.tsx:47`), whose ids come from `_picture_rows` and are always set.
  PRICETAG-ACC-PICTURE-PICKER (#2273) resolves `entry.image_id` against `images`, falling back to
  `images[0]`; a product entry resolves to its one photo either way.

## Tests

`tests/test_accessories.py::test_hotfix_a_free_product_with_a_photo_reads_200_on_every_list`
(red-first), then the accessory / combo / price tag suites touched by the schema.
