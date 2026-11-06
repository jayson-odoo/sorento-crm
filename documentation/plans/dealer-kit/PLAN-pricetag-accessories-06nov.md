# PLAN: price tag "Accessories included" (PRICETAG-ACCESSORIES, 6 Nov)

Status: Review. Card answered 6 Nov ~10:00 (`CARD-pricetag-accessories-06nov.md`, rules A1-A16
incl. the 10:45 product-entry addendum), mock approved 10:23 (`pricetag-accessories-mock.html`),
build complete on PR #2211. Track: full (migration + new master data).
Q-M1 / Q-M2 unanswered at build start: built on the recommendations (split old text on line
breaks, commas and " + "; one card width per horizontal box).

## Data (migration `ptag_0016_accessories`, additive)

- `accessories` (CompanyScopedMixin): `id`, `company_id`, `name` String(100) NOT NULL, `spec`
  String(200) NULL, `image_attachment_id` FK attachments SET NULL, `created_by`, timestamps.
  Unique index `(company_id, lower(name))`.
- `product_accessories`: `id`, `product_id` FK products CASCADE, `accessory_id` FK accessories
  RESTRICT NULL, `item_product_id` FK products RESTRICT NULL (exactly one set, CHECK), `sort_order`;
  unique `(product_id, accessory_id)` and `(product_id, item_product_id)`.
- `product_combo_accessories`: same shape keyed by `combo_id` FK product_combos CASCADE.
- Attachment type `accessory_image` seeded by code (insert only). Stored with `entity_type =
  'general'` (no CHECK rebuild).
- Data step (A12): every non-blank `product_combos.free_items` and
  `price_tag_request_lines.included_accessories` is split (`\n`, `,`, ` + `), trimmed,
  de-duplicated by `lower(name)` per company into `accessories`, then linked in written order:
  combo text -> that combo (only if its list is empty); line text -> the line's combo if it has one
  and that list is empty, else the line's product if its list is empty. Lines are taken oldest
  first, so the oldest line's text fills an empty list and later lines are left in the NOTICE log.
  Idempotent (re-run inserts nothing). Old columns stay, unread. `price_tag_request_lines.
  included_accessories` is still accepted by the request API (and carried by portal revisions) but
  nothing reads it any more; a later lane drops the column and the field together.

## API (all under `/api/v1/master-data`, products permission: view `master_data.products.view`,
## write `master_data.products.edit`)

- `GET /accessories?page&limit&query` -> `ListResponse[AccessoryOut]` ordered by name.
  `AccessoryOut = {id, name, spec, image: {attachment_id, url} | null, product_count, combo_count}`.
- `POST /accessories {name, spec?}` -> 201 AccessoryOut. Duplicate name (ignoring case) -> 409.
- `GET /accessories/{id}` -> AccessoryOut. `PATCH /accessories/{id} {name?, spec?}` -> AccessoryOut.
- `DELETE /accessories/{id}` -> 204; 409 while listed: "Used on N products and M combos: remove
  it there first."
- `POST /accessories/{id}/image` (multipart `file`, jpg/jpeg/png/webp, 10 MB) -> `{attachment_id,
  url}`; `DELETE /accessories/{id}/image` -> 204.
- `GET /products/{id}/accessories` -> `{data: Entry[]}` in order, Entry = AccessoryOut plus
  `kind: 'accessory'|'product'`, `code`, `list_price` (product entries: id = product id, name =
  description else name, live LP and lead photo).
  `PUT /products/{id}/accessories {items: [{accessory_id}|{product_id}]}` -> same, replaces the
  ordered list (duplicates or an entry naming both/neither -> 422, the host itself -> 422, unknown
  or other-company id -> 404).
- `GET|PUT /product-combos/{id}/accessories`, same shapes; a product that is a part of the combo
  -> 422. `ProductComboOut` gains `accessories`; `free_items` is no longer read or written.
- Library delete is the deferred record action `accessory.delete` (products edit permission).

## Tag payload

`TagAccessory = {kind, id, name, spec, image: {attachment_id, url} | null, code, list_price}`.
- `product_tag_data` (and every part row) gains `accessories` = the product's own list.
- `_combo_object` gains `accessories` = the combo's own list; its `free_items` becomes the names
  joined with ", " (keeps the `combo.free_items` merge field and the data-change diff working).
- A request line row gains `accessories` = its combo's list when it has a combo, else its
  product's list; `included_accessories` = those names joined with ", ".
- Pinned rows keep the pinned list (A9); image URLs re-signed on read. A row pinned before this
  lane (no `accessories` key) keeps its pinned text and reads `accessories: []`.
- Importer `scripts/import_product_combos.py` fills the combo's list (find-or-create by name)
  instead of `free_items`.

## Designer

- Layer type `accessories`, props `AccessoriesLayerProps`: `direction: 'vertical'|'horizontal'`,
  `headerText`, `showBadge`, `badgeAssetId?`, `fill`, `stroke`, `strokeWidth_mm`, `cornerRadius_mm`,
  `headerFontSize`, `headerColor`, `imageSize_mm`, `nameFontSize`, `specFontSize`, `textColor`,
  `gap_mm`, `cardWidth_mm` (horizontal), `subjectSlot?`.
- `lib/dealer-kit/accessory-box.ts`: `accessoriesOf(binding, layer)` (combo list on a combo tag,
  else the product's; a combo position reads that product's own) and `accessoryBoxLayout(count,
  props, w, h)` -> `{cards[], shown, dropped, boxWidth_mm, boxHeight_mm}` (whole cards only; box
  closes up from bottom/right; 0 -> nothing). Used by the Konva canvas (editor + DesignViewer) and
  `TagSheetRenderer`.
- Inspector: AccessoriesInspector + "N of M accessories do not fit this box" warning; sheet toast
  beside the feature-icon one.
- Toolbar: "Accessories" adds the layer; "Add accessories strip" removed.

## Master data screens

- `master-data-management/accessories` list (DataGrid) + modal create/edit + deferred delete.
- Product page Overview: "Accessories included" (`AccessoryListField`) after Combos.
- Combo block: "Free items" becomes `AccessoryListField` (replaces the text field).

## Tests

BE: `tests/test_accessories.py` (CRUD, 409s, lists, permissions, tag payload, pinned),
`tests/test_migration_ptag_0016_accessories.py` (split, dedupe, linking rules, idempotence),
importer test updates. FE: `lib/dealer-kit/accessory-box.test.ts`, inspector warning test.
