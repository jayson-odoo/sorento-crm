# PLAN: price tag accessory card layout, designed inside the Tag Template designer (PRICETAG-ACCESSORY-DESIGNER, 07/11/2026)

Status: PR+CI (build, review READY, security review fixed, cloud browser PASS 8/8, hand test pending; owner OK on mock v3 07/11/2026 22:18). Track: full (migration + new table + new page).

Behaviour card: `CARD-pricetag-accessory-designer-07nov.md` (rules D1-D5, A1-A4, P1, F1-F3, V1-V9; v1 rulings
win where they differ). UAC: `pricetag-accessory-designer-acceptance-criteria.md`. Mocks: v1, v2 (click by click),
v3 (one layout for any list), same folder.

## Binding decisions (owner)

- Q1 live link + Detach. Q2 shrink together to 70% minimum, then whole cards only + warning. Q3 picture chosen
  on the list entry, default the first; dots show all colours. Q4 dots are a freely placed element on card and
  footer. Q5 Accessories menu in the designer AND a management page. v3 Q1 every card in a box the same height.
  v3 Q2 no per-accessory own layout.
- **Existing tags print the same**: a box with no `card` keeps the legacy code path untouched
  (`accessoryBoxLayout` / `accessoryCardInner`). Only "Edit card" (or applying a saved template) gives a box a
  `card`; that conversion builds a card from the legacy settings (`cardFromLegacy`).
- Coordination: #2235 (PRICETAG-ACC-LABELS) owns the label wording and the canvas drop warning; this lane feeds
  the new path's `dropped` count into the same warning hook and does not touch the labels.

## Slices (one lane, one PR)

- S1 BE data + API + tag payload + presets (migration `ptag_0017_acc_designer`).
- S2 FE lib: types, card layout function, legacy conversion, renderers (canvas + print).
- S3 FE designer: card / footer editing mode, element inspectors, box inspector, Accessories menu, live link, Detach.
- S4 FE master data: accessory pictures with colours, rich spec, remark; list-entry pencil.
- S5 FE management page `/dealer-kit/accessory-templates` + sidebar entry.

## S1 Backend contract

### Migration `ptag_0017_acc_designer` (additive; down_revision = main's head at build start)

- `accessory_images`: `id` UUID PK, `accessory_id` FK accessories CASCADE NOT NULL, `attachment_id` FK
  attachments CASCADE NOT NULL, `colour_name` String(40) NULL, `colour_hex` String(7) NULL (`^#[0-9a-fA-F]{6}$`,
  CHECK), `sort_order` Integer NOT NULL default 0, `created_at`. Index on accessory_id.
  Data step: every `accessories.image_attachment_id` not null and not already copied -> one row, sort 0, no
  colour. Idempotent. `accessories.image_attachment_id` stays (unread).
- `accessories.spec` String(200) -> Text (rich HTML or plain, sanitised by `app/utils/tag_rich_text.py`, max
  4000 chars after sanitising). `accessories.remark` Text NULL (same rules, max 1000).
- `product_accessories` and `product_combo_accessories` gain: `image_id` FK accessory_images SET NULL NULL,
  `name_override` String(200) NULL, `spec_override` Text NULL, `remark_override` Text NULL.
- `dealer_kit.accessory_box_preset` (CompanyScopedMixin, like `TagSizePreset`): `id`, `company_id`, `name`
  String(100) NOT NULL, `design` JSONB NOT NULL, `created_by` String, `updated_by` String, `created_at`,
  `updated_at`; unique `(company_id, lower(name))`.

### Accessory pictures (permission `master_data.products.view` / `.edit`, under `/api/v1/master-data`)

- `AccessoryOut` gains `images: AccessoryImageOut[]` (ordered) where AccessoryImageOut =
  `{id, attachment_id, url, colour_name, colour_hex}`; `image` = first image (kept for old callers);
  `remark: str | null`; `spec` may be rich HTML.
- `POST /accessories/{id}/images` multipart `file` (+ optional form `colour_name`, `colour_hex`) -> 201
  AccessoryImageOut, appended last. jpg/jpeg/png/webp, 10 MB (same checks as today's `/image`). Max 12 per
  accessory (422).
- `PATCH /accessories/{id}/images/{image_id}` `{colour_name?, colour_hex?}` (null clears) -> AccessoryImageOut.
  Bad hex -> 422. Image of another accessory -> 404.
- `DELETE /accessories/{id}/images/{image_id}` -> 204 (entries pointing at it fall back to the first).
- `PUT /accessories/{id}/images/order` `{ids: [...]}` -> AccessoryImageOut[]; must be exactly the current set
  (422 otherwise).
- Old `POST/DELETE /accessories/{id}/image` keep working: POST replaces image 1 (or creates it), DELETE removes
  image 1. (No caller after S4; kept so an old tab does not 404.)
- `POST/PATCH /accessories` accept `remark`; `spec` and `remark` sanitised with `tag_rich_text` (script, style,
  on* attributes, links stripped).

### List entries (`GET|PUT /products/{id}/accessories`, `GET|PUT /product-combos/{id}/accessories`)

- Entry in: `{accessory_id | product_id, image_id?, name?, spec?, remark?}` (blank string = no override).
  `image_id` must belong to that entry's accessory (422); on a product entry it must be null (422).
- Entry out (AccessoryOut + `entry: {image_id, name, spec, remark}` = the stored overrides, nulls when none).
- Overrides are per list row; replacing the list replaces them (FE always sends the whole list back).

### Tag payload (`TagAccessory`, `tag_data_service` / `accessory_service.tag_*`)

`{kind, id, name, spec, remark, image, images, colours, code, list_price}` where
- `images` = all pictures `[{attachment_id, url, colour_name, colour_hex}]`; `image` = the entry's chosen
  picture, else the first; `colours` = distinct `{name, hex}` of `images` with a hex, in picture order.
- Library accessory: `name`/`spec`/`remark` = entry override when non-blank, else the accessory's.
- Product entry: `name` unchanged (description else name) unless overridden; `spec` = override, else the
  product's `price_tag_description` (legacy cards never print a product's spec, so old tags are unchanged);
  `remark` = override; `images` = [lead photo] (no colour); `colours` = [].
- Pinned rows: the new keys are pinned with the rest; `_resign_accessories` re-signs `image` AND every
  `images[].url`. A row pinned before this lane reads `images: []`, `colours: []`, `remark: null`.

### Accessory templates (presets) under `/api/v1/dealer-kit/accessory-templates`
(view `dealer_kit.tag_templates.view` with API key, manage `dealer_kit.tag_templates.manage`, like tag-sizes)

- `GET ""` -> `AccessoryTemplateOut[]` ordered by name: `{id, name, design, used_in, created_by_name,
  updated_at, created_at}`; `used_in` = number of tag templates (drafts) with a linked box.
- `POST ""` `{name, design}` -> 201. Duplicate name ignoring case -> 409 `{code: 'DUPLICATE_NAME'}`. Blank name
  422. `design` must be an object, <= 64 KB serialized, `design.kind` ignored; the keys `kind`, `subjectSlot`,
  `subjectPart`, `presetId` are stripped before storing.
- `GET /{id}` -> out. `GET /{id}/usage` -> `{templates: [{id, name}]}` (tag templates whose draft links it).
- `PUT /{id}` `{name?, design?}` -> out. A new `design` is written into EVERY linked box (layer `type ==
  'accessories'` with `props.presetId == id`) in every `tag_template.doc`, `tag_template_version.doc`,
  `page.draft_doc` and `page_version.doc` of the same company: `props = {**design, kind: 'accessories',
  presetId: id, subjectSlot/subjectPart kept from the layer}`. Walk both doc shapes (bare `layers`, and
  `sheets[].tags[].layers`), like `asset_service._rewrite_font_family_in_doc`. Response carries
  `rewritten: int`.
- `DELETE /{id}` -> 204 immediate; deferred action `accessory_box_preset.delete` (WINDOW_DESTRUCTIVE, manage
  permission, entity_type `accessory_box_preset`) calls the same service. Delete removes `presetId` from every
  linked box (each keeps its current design) then deletes the row.
- Company scoping: every query through the CompanyScopedMixin session filter; docs of another company are never
  read or rewritten (test with two companies).

## S2 Frontend lib contract (`lib/dealer-kit/tag-template-types.ts`, `lib/dealer-kit/accessory-card.ts` NEW)

```ts
export type CardField = 'picture' | 'name' | 'code' | 'spec' | 'remark' | 'price' | 'colours';
export interface CardElement {
  id: string;
  kind: 'picture' | 'text' | 'colour_dots' | 'shape';
  x_mm: number; y_mm: number; width_mm: number; height_mm: number;   // inside the card / footer
  hidden?: boolean;
  field?: CardField | null;   // text: name|code|spec|remark|price, null = fixed `text`; picture: 'picture';
                              // colour_dots: 'colours' (card: that accessory's; footer: all in the box)
  text?: string;              // fixed text, plain or rich (lib/dealer-kit/rich-text.ts)
  fontFamily?: string | null; fontSize?: number; fontWeight?: number; italic?: boolean; underline?: boolean;
  color?: string; align?: 'left' | 'center' | 'right'; lineHeight?: number;
  fit?: 'contain' | 'cover';
  dotSize_mm?: number; dotGap_mm?: number; dotDirection?: 'row' | 'column'; dotOutline?: string;
  colours?: string[] | null;  // hand-picked hex; null/absent = from data
  shape?: 'rect' | 'rounded_rect' | 'ellipse' | 'line'; fill?: string; stroke?: string;
  strokeWidth_mm?: number; cornerRadius_mm?: number;
}
export interface CardLayout { width_mm: number; height_mm: number; elements: CardElement[] }
export interface FooterLayout { show: boolean; height_mm: number; elements: CardElement[] }
// AccessoriesLayerProps gains: card?: CardLayout; footer?: FooterLayout; shrinkMin?: number (default 0.7);
// presetId?: string | null.
// TagAccessory gains: remark?: string | null; images?: {attachment_id,url,colour_name,colour_hex}[];
// colours?: {name: string|null, hex: string}[].
```

Functions (pure, unit tested, used by canvas AND print so they cannot disagree, card rule A10):
- `cardBoxLayout(count, props, boxW, boxH)` -> `{cards: Rect[], scale, shown, dropped, boxWidth_mm,
  boxHeight_mm, frame, header, badge, footer: Rect | null}`. Vertical: cards stack at
  `card.width_mm * scale` wide, left aligned at the pad; horizontal: run left to right. `scale = min(1, fit)`;
  below `shrinkMin` (default 0.7) the scale stays at `shrinkMin` and only whole cards are kept. Header and frame
  geometry exactly as `accessoryBoxLayout`. Footer (when `footer.show`) sits under the cards at
  `footer.height_mm` (not scaled), full inner width. Box closes up like today. 0 items -> nothing.
- `cardElementsFor(item, card)` -> visible elements with resolved content and final rect (card mm, unscaled):
  an element whose field is empty for `item` is dropped (picture with no image; text whose value is blank;
  price with no list_price; colour_dots with no colours and no hand-picked colours); every element whose top is
  at or below a dropped element's bottom AND whose horizontal span overlaps it moves up by
  (nearest such element's top - the dropped element's top), processed top to bottom. Hidden elements are
  dropped without moving anything. Card height never changes (v3 Q1 (a)).
- `cardFieldValue(item, field)`: name -> name; code -> code; spec -> spec; remark -> remark; price ->
  `LP: ${formatTagPrice(list_price)}`; colours -> hexes.
- `boxColours(items)` -> distinct hexes in order of first appearance (footer dots default).
- `cardFromLegacy(props, lines)` -> a CardLayout reproducing the legacy card for that box (picture, code,
  name, spec, price as text elements with the box's name / spec styles), sized from `accessoryCardInner`.
- `accessoryDesign(props)` -> props without `kind`, `subjectSlot`, `subjectPart`, `presetId`;
  `applyAccessoryDesign(props, design, presetId)` -> merged props keeping the per-box keys.
- `cardDropped(...)` feeds the existing drop warning (#2235 canvas warning, inspector warning,
  `accessory-drops.ts` toast) when the box has a `card`.

Renderers: `KonvaTagLayer.tsx` AccessoriesContent and `TagSheetRenderer.tsx` take the card path when
`props.card` is set, else the legacy path byte for byte.

## S3 Designer (TagCanvasEditor / CanvasToolbar / InspectorPanel)

- Box inspector: Edit card, Edit footer, Footer show, Gap, Shrink to fit (On, smallest 70% fixed for now: shown,
  not editable), Save as accessories template, linked note `Linked: <name> (used in N tag templates)` + Detach.
- Editing mode state `accessoryEdit: {layerId, target: 'card' | 'footer', elementId | null}`: entered by
  double-click on a selected accessories box, Enter, or the buttons; left by Done, Escape, or a click outside
  the box. The toolbar shows `Editing card: Picture | Text | Colour dots | Shape | Done` (footer: no Picture).
  Card 1 is drawn editable with its elements selectable, draggable and resizable (Konva Transformer as for
  layers); other cards drawn at 45% opacity. Entering a box without `card` converts it with `cardFromLegacy`
  (one undo step). Element inspector: Shows (field), text controls (TypographyControls), picture fit,
  dot size / gap / row-column / outline / colours (from data or picked), shape fill / stroke / radius, hide
  (eye), Delete key removes.
- Toolbar "Accessories" becomes a menu: Default box, then saved accessories templates (searchable, used-in
  count). Picking one inserts a box with that design and `presetId`.
- Live link: after the tag template saves, every linked box whose design differs from the preset loaded on open
  is PUT to its preset. While a linked box is being edited a bar reads "Linked to <name>: changes here update N
  tag templates" with Detach.
- "Save as accessories template" dialog (SaveAsSizeDialog shape): name -> POST, the box gets `presetId`.

## S4 Master data

- AccessoryFormDialog: pictures list (AccessoryPictureControl per picture, add, remove, drag order with
  @dnd-kit, colour select Black #1f2937 / Grey #9ca3af / Silver #c0c0c0 / White #ffffff / Gold #d4af37 /
  Gunmetal #2c3539 / Custom hex / None); Spec lines and Remark with `components/ui/rich-text-editor.tsx`.
- AccessoryListField row pencil -> dialog: picture choice (accessory entries with more than one picture), name,
  spec, remark overrides, "Use the accessory's own" clears them. Row shows a pill "Own text" when any override.

## S5 Management page

`app/(protected)/dealer-kit/accessory-templates/` copied from `tag-sizes/` (page, list, rename dialog, hooks,
service `services/accessoryTemplateService.ts`): DataGrid (fixed layout, resizable) columns Preview (mini
render via the lib), Name, Used in (count, opens a popover listing template names), Updated (dd/mm/yyyy), By.
Rename modal; Delete = deferred action `accessory_box_preset.delete`. Sidebar entry "Accessory Templates"
under Dealer Kit after Tag Sizes (`config/menu.config.tsx`), same permission as Tag Sizes.

## Test list (tester writes these red first)

BE (pytest, Postgres): migration additive + idempotent data copy; images CRUD + order + colour validation +
limit; entry overrides round trip + image of another accessory 422 + product entry image 422; tag payload
(images, colours, chosen image, overrides, product spec = price_tag_description, pinned resign of images);
presets CRUD, duplicate name 409, design key stripping, size cap, PUT propagation into draft/version/page docs
of the same company only (other company untouched), DELETE detaches, deferred action registered, permissions
(view vs manage, 403 without).
FE (vitest): `cardBoxLayout` (fits at 100%, shrinks, clamps at 70% + drops whole cards, horizontal, footer,
0 items), `cardElementsFor` (empty field hides + move up, hidden element no move, card height constant),
`boxColours`, `cardFromLegacy`, `accessoryDesign/applyAccessoryDesign`; legacy path unchanged (existing
accessory tests stay green); KonvaTagLayer card path renders dots for colander and none for chopping board;
InspectorPanel box section (Edit card, Save as template, Detach); AccessoryListField pencil; management list.

## Open / later

- Per-accessory own layout (v3 Q2): later lane when a real tag needs it.
- Shrink minimum editable per box: shown fixed at 70% until asked.

## S6 Layout flexibility (owner ruling 08/11/2026 ~02:10, option (a))

Built after the hand-test fix (card layout lost after Done). No new mock (existing components).

### Columns
- `AccessoriesLayerProps.columns?: 'auto' | 1 | 2 | 3 | 4`. Absent = today's behaviour (vertical = 1 column,
  horizontal = one row), so saved boxes do not move. Card path only; the inspector shows "Columns" with a
  SearchableSelect (Auto, 1, 2, 3, 4); choosing one on a box without a card converts it (cardFromLegacy, as Edit card).
- Grid: cards fill left to right, then wrap to the next row (7 items in 4 columns = 4 + 3). Rows are left aligned,
  every card the same size. Auto: the most columns that fit the box's inner width at scale 1 (`floor((innerW + gap) /
  (cardW + gap))`), at least 1, at most the item count.
- Fit is the same rule as today: one uniform scale for every card so the grid fits width AND height (footer under the
  grid), never below 70%; below that only whole cards print, in reading order, and the drop warning shows.
- One layout function: `cardBoxLayout` gains the grid; canvas, request preview and print keep calling it.

### Hide when empty
Already the rule (V7): picture, name, code, spec, remark, price and colour dots each hide for an accessory with no
value. Tests must prove it on the SAVED and reloaded layout (the bug that lost the layout after Done hid this).

### Box style override per product / per combo
- `products.accessory_box_preset_id` and `product_combos.accessory_box_preset_id` (FK
  `dealer_kit.accessory_box_preset` ON DELETE SET NULL, NULL = the tag template's own box). Additive migration.
- UI: on the product's and each combo's "Accessories included" section, a "Box style" SearchableSelect (clearable):
  empty = "Tag template's own box", else a saved accessories template. Saved through the same list endpoints:
  `GET|PUT /products/{id}/accessories` and `/product-combos/{id}/accessories` gain `box_style_id` (read and write;
  omitted on PUT = unchanged, null = cleared; another company's or unknown id = 404).
- Resolution, ONE function each side (a category default may be added later: product -> category -> template):
  - BE `accessory_service.box_style_for(db, *, product_id=None, combo_id=None)` returns `{id, name, design} | None`.
  - Every place the tag payload carries an `accessories` list also carries `accessory_box_style` for the same owner
    (product data, combo object, request line row = its combo's else its product's, parts / slots = that product's).
    Pinned rows freeze it with the list; a row pinned before reads null.
  - FE `accessoryBoxStyleOf(data, layer)` in `accessory-card.ts`, branching exactly like `accessoriesOf`; the
    renderers draw `applyAccessoryDesign(layer.props, style.design, layer.props.presetId)` when a style resolves,
    keeping the box's position, size and "Reads from". The editor canvas shows the override too when previewing that
    product / combo, with an inspector note "Box style from <product or combo>: <name>".
- Deleting a saved accessories template clears the overrides (SET NULL); those tags fall back to the template's box.
