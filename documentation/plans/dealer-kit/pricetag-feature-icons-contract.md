# Contract: feature icons (PRICETAG-DESIGNER-GAPS item 3, 5 Nov)

Behaviour: `CARD-pricetag-feature-icons-05nov.md` ("Owner rulings" wins). This file is the shape
the tests and the code agree on. Paths: BE = `sorento_crm_backend/`, FE = `sorento_crm_frontend/`.

## What already exists (do not rebuild)

- Library assets: `dealer_kit.asset` (BE `app/models/dealer_kit.py:241`), kinds incl. `icon`
  (`app/services/dealer_kit/asset_service.py:63`). Routes `app/api/v1/dealer_kit/assets.py`
  (list / upload / PATCH rename / delete), response `AssetResponse` (`app/schemas/price_tag.py:1562`).
  Managed in the FE `AssetPickerDialog` library tab (`app/(protected)/dealer-kit/tag-templates/components/AssetPickerDialog.tsx`); there is no other library screen.
- Specs per product on the tag payload: `product_specs` (BE `app/services/dealer_kit/tag_data_service.py:258-298`)
  returns `{key, label, value, unit}`; `value` is DISPLAY text. Combo parts reuse it (`_part_row`, `:671`).
- Layer subject: `subjectOf(data, layer)` (FE `lib/dealer-kit/product-block.ts:255-288`) honours
  `subjectSlot` / `subjectPart`; `layerShownFor` (`product-block.ts:1315`) is the existing
  subject-aware spec check (boolean Yes only, a whole layer) - read it for the pattern.
- Print media: `design_media` (BE `app/services/dealer_kit/tag_sheet_export_service.py:~518`) returns
  `{assets, images, fonts}`; `assets` is signed from `asset_service.tag_sheet_asset_ids(doc)`
  (`asset_service.py:388`). FE print `TagSheetMedia` (`app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer.tsx:122`).
- Canvas display resolver: `layerDisplay(layer, data, assetUrls)` (FE `lib/dealer-kit/product-block.ts:~1242`),
  used by `TagCanvasEditor`, `ArrangeSheetView`, `TagVersionViewer`; drawn by `KonvaTagLayer`.
- Layer doc contract: `TagLayerDoc` / `TagLayerPropsDoc` (BE `app/schemas/price_tag.py:~769`).

## Backend

B1. Migration (revision id <= 32 chars, `down_revision` = current single head, check `alembic heads`):
    `dealer_kit.asset` + `show_when_spec_key VARCHAR(64) NULL`, `show_when_values TEXT[] NULL`,
    CHECK `(show_when_spec_key IS NULL) = (show_when_values IS NULL)`
    named `ck_dealer_kit_asset_show_when_pair`. Model columns on `Asset`.
B2. `AssetResponse` + `show_when_spec_key: Optional[str] = None`,
    `show_when_values: Optional[list[str]] = None`; `_serialize` fills them.
B3. `PUT /api/v1/dealer-kit/assets/{asset_id}/show-when`, permission `dealer_kit.library.manage`
    (the route file's `_MANAGE`). Body `{"spec_key": str | null, "values": list[str]}`.
    - `spec_key` null -> clears both columns. 200 with the `AssetResponse`.
    - 404 `ASSET_NOT_FOUND` for an unknown / deleted asset.
    - 422 `NOT_AN_ICON` when the asset's kind is not `icon`.
    - 422 `UNKNOWN_SPEC` when `spec_key` is not an ACTIVE key in the spec registry
      (`product_spec_registry` table, `ProductSpecRegistry` model in `app/models/product_spec.py`).
    - 422 `UNKNOWN_SPEC_VALUE` when the key has `allowed_values` and a value is not one of them.
    - 422 `VALUES_REQUIRED` when `spec_key` is set and `values` is empty. Values are de-duplicated,
      order kept.
B4. Tag payload: every `product_specs` entry gains `raw`: the stored value as a string
    (`str(raw)`; a bool stored value -> `"true"` / `"false"`). Display `value` unchanged.
B5. Print / preview media: when the doc (template or tag sheet) has any layer of type
    `feature_icons`, `design_media` adds `feature_icons: [{id, name, spec_key, values}]` for every
    icon asset that carries a rule (scoped like any asset query), ordered by name, and their ids are
    added to the `assets` signed-URL map. No such layer -> no `feature_icons` key change beyond
    `[]` (always present as a list). Every route that forwards `design_media`'s media to the print
    page or a preview forwards the new key (`app/api/v1/public/print.py`,
    `app/api/v1/public/portal_price_tag.py`; grep for others).
B6. Doc contract: `FeatureIconsLayerPropsDoc` (`_StrictProps`): `kind: Literal["feature_icons"]`,
    `iconSize_mm: float (gt 0, le 200)`, `gap_mm: float (ge 0, le 100)`,
    `align: Literal["left","center","right"] = "left"`, `order: list[str] = []` (asset ids),
    `subjectPart: Optional[int]`, `subjectSlot: Optional[SubjectSlotDoc]`. Added to
    `TagLayerPropsDoc` and to `TagLayerDoc.type`.

## Frontend

F1. Types (`lib/dealer-kit/tag-template-types.ts`): `FeatureIconsLayerProps` mirroring B6,
    `defaultFeatureIconsProps()` = `{kind:'feature_icons', iconSize_mm: 8, gap_mm: 1.5, align: 'left', order: []}`;
    layer type `'feature_icons'`; `TagSpecValue.raw?: string`.
F2. `lib/dealer-kit/feature-icons.ts` (pure, the ONE rule used by canvas, preview and print):
    - `interface FeatureIcon { id: string; name: string; spec_key: string; values: string[] }`
    - `iconsFromAssets(assets)`: library rows with `kind === 'icon'` and a rule -> `FeatureIcon[]`.
    - `featureIconsFor(specs, icons, order = [])`: an icon matches when `specs` has a row with
      `key === spec_key` whose `raw` is in `values` (no `raw` -> no match; display text is never
      matched). Result order: ids in `order` first, in that order; then the rest by `name`
      (case-insensitive). Each icon at most once.
    - `featureIconRow(count, props, boxWidth_mm)` -> `x_mm[]` of each icon's left edge inside the
      box: icons `iconSize_mm` wide, `gap_mm` apart, packed (Q5: no gaps for missing facts), aligned
      left / center / right; an icon that would not fit entirely inside the box is dropped (the
      returned array is shorter). Icons are vertically centred in the box (`y = (h - size) / 2`).
B7 (FE equivalents of B5): `TagSheetMedia.featureIcons?: FeatureIcon[]`, passed by the print page
    and every preview that forwards `assets`.
F3. Canvas: `layerDisplay(layer, data, assetUrls, featureIcons?)` gains an optional 4th parameter;
    for a `feature_icons` layer it returns `{ icons: {id, url}[] }` from `featureIconsFor(subject
    specs, featureIcons, props.order)` (subject via `subjectOf`), url from `assetUrls`.
    `KonvaTagLayer` draws each icon at `featureIconRow`; no icons -> the dashed outline with the
    label "Feature icons" (designer only, like an unbound `product_slot`).
    Hosts: `TagCanvasEditor` (icons from its library via `iconsFromAssets`), `ArrangeSheetView`,
    `RequestTagDesigner`; `TagVersionViewer` may show the placeholder.
F4. Print: `TagSheetRenderer` draws a `feature_icons` layer as absolutely positioned `<img>`s
    (alt = icon name) at `featureIconRow`, with the subject's specs; nothing printed when no icon
    matches. Same `layerShownFor` gate as other layers.
F5. Editor: the layer can be added from the canvas wherever the other layer kinds are inserted
    (label "Feature icons"). Inspector `FeatureIconsInspector`: Icon size (mm), Spacing (mm),
    Align (left / centre / right), Reads from (the same subject picker image layers have), and
    the order of the rule-carrying icons (move up / down), written to `order`.
F6. Asset library (`AssetPickerDialog`, library tab): an icon asset shows "Show when" - a spec
    select (active registry keys, `GET /api/v1/master-data/spec-registry`) and the value(s)
    (`SearchableMultiSelect` over `allowed_values`, labelled by `value_labels`), saved through B3
    via a dealer-kit service function and a mutation hook (toast on success / error). Clearable.
    Every select clearable; `SearchableSelect` / `SearchableMultiSelect` only. No UUIDs shown.

## Out of scope

Warranty and anti-bacteria (static assets, Q3/Q4), a separate rules screen, per-template rule
copies, hot-only taps (no data).
