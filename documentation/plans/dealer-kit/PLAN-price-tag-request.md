# PLAN - Price Tag Request: end-to-end flow from salesperson to print

> The design that fulfils `price-tag-request-acceptance-criteria.md`. That file is the
> contract; where this plan and the UAC disagree, the UAC wins.
> Governs: `PRINCIPLES.md` + `documentation/reference/ADR-PRODUCT-STANDARDS.md`.

**Slug:** `price-tag-request` | **Domain:** dealer-kit (sub-feature)
**Status:** S0-S5 + S3b BUILT (PR #289). S3c (section 9, D33-D41) BUILT 2026-08-29 from the
captain's test of the S3b bed; D42-D44 BUILT 2026-08-30 from the second round of that test;
D45-D47 (section 10) BUILT 2026-08-30 from the captain's test of the PORTAL form; D48-D49
(section 11) BUILT 2026-08-30 from the round that followed it; D50-D52 (section 12) BUILT
2026-08-30 from the captain's test of the CRM detail and design pages.
**UAC:** `documentation/plans/dealer-kit/price-tag-request-acceptance-criteria.md`
**Depends on:** `feat/product-sets` branch merged to main.
**Branch:** TBD

---

## 1. What is being built, in one paragraph

A portal contact (Sorento salesperson) submits a price tag request naming the products, sets,
combos, price mode, dealer, deadline, and customer PO. Marketing claims the request in the CRM,
designs the tags in a free-form canvas editor using per-family templates with product-bound
slots, and marks the proof ready. The salesperson reviews and approves on the portal. Both
parties download the final PDF. Prices resolve at render time from the existing pricing engine,
never stored in the document (ADR 0008). The customer PO is cross-checked against selling prices
(manual in Phase 1, AI-automated in Phase 2).

---

## 2. Dependencies and their state

| Dependency | Branch | State | What we need from it |
|---|---|---|---|
| Product Sets | `feat/product-sets` | Approved, unmerged | `product_sets` + `product_set_members` tables, set membership queries |
| Dealer Kit builder | `main` | Merged, live | `Page`/`PageVersion`/`PageLabel`, `Asset`, `CatalogueRenderer`, PDF export pipeline |
| Promotions + pricing | `main` | Merged, live | `resolve_prices()`, `Promotion`/`PromotionProduct`, promotion window |
| Form SLA | `main` | Merged, live | `FormSLAConfig`, `emit_form_event()`, stage chain, notifications |
| Portal | `main` | Merged, live | OTP auth, `SUPPORTED_TYPES`, attachments, revisions, lookups |
| Flyer spec ingestion | PR pending | Nice-to-have | Product spec lines for slot data; falls back to product description |

---

## 3. Data model

### Portal form type visibility (shared infrastructure, not price-tag-specific)

```
contact_access_types (existing)
  + portal_form_types    JSONB NOT NULL DEFAULT '[]'    -- e.g. ["price_tag_request","stock_inquiry"]

contact_portal_form_overrides (new)
  id                     UUID pk
  contact_id             TEXT FK respond_contacts ON DELETE CASCADE NOT NULL
  form_type              VARCHAR(50) NOT NULL
  is_enabled             BOOLEAN NOT NULL
  created_at / updated_at
  UNIQUE (contact_id, form_type)
```

Resolution: union of `portal_form_types` from all the contact's assigned access types, then
per-contact overrides applied (`is_enabled` wins). Empty resolved set = contact sees nothing.

### SalesAgent + Customer links

```
sales_agents (existing)
  + contact_id           UUID FK respond_contacts ON DELETE SET NULL NULL

customers (existing)
  + sales_agent_id       UUID FK sales_agents ON DELETE SET NULL NULL
```

`customers.sales_agent_id` is the primary source for the debtor dropdown: customers assigned
to the contact's linked agent. Enriched by debtors from orders in last 24 months + prior
price-tag requests.

### Request

```
price_tag_requests                              CompanyScopedMixin
  id                     UUID pk
  contact_id             TEXT FK respond_contacts NOT NULL
  debtor_code            VARCHAR(100) NULL
  debtor_name            VARCHAR(255) NOT NULL
  promotion_id           UUID FK promotions ON DELETE SET NULL NULL
  needed_by_date         DATE NOT NULL
  notes                  TEXT NULL
  status                 VARCHAR(30) NOT NULL DEFAULT 'new'
  doc_number             VARCHAR(30) NOT NULL UNIQUE   -- PT-YYYYMM-NNNN
  page_id                UUID FK dealer_kit.page ON DELETE SET NULL NULL
  portal_draft_at        TIMESTAMP NULL
  po_extraction_result   JSONB NULL                    -- Phase 2: AI extraction output
  created_at / updated_at / created_by

  INDEX (status)
  INDEX (contact_id)
  INDEX (promotion_id)
```

Statuses: `new`, `designing`, `proof_ready`, `changes_requested`, `approved`, `ready`,
`rejected`, `void`.

```
price_tag_request_lines
  id                     UUID pk
  request_id             UUID FK price_tag_requests ON DELETE CASCADE NOT NULL
  line_type              VARCHAR(20) NOT NULL           -- 'product' | 'product_set'
  product_id             UUID FK products ON DELETE RESTRICT NULL
  product_set_id         UUID FK product_sets ON DELETE RESTRICT NULL
  show_promo_price       BOOLEAN NOT NULL DEFAULT true
  quantity               INTEGER NOT NULL DEFAULT 1     -- number of tags to print
  alternatives           JSONB NOT NULL DEFAULT '[]'    -- [{product_id}] for OR taps
  included_accessories   TEXT NULL
  sort_order             INTEGER NOT NULL DEFAULT 0
  marketing_price_override  NUMERIC(15,2) NULL
  marketing_override_reason TEXT NULL
  created_at / updated_at

  CHECK (  (line_type = 'product'     AND product_id IS NOT NULL AND product_set_id IS NULL)
        OR (line_type = 'product_set' AND product_set_id IS NOT NULL AND product_id IS NULL) )
  UNIQUE (request_id, product_id)    -- no duplicate product lines
  UNIQUE (request_id, product_set_id) -- no duplicate set lines
```

### Tag templates

```
dealer_kit.tag_templates
  id                     UUID pk
  name                   VARCHAR(255) NOT NULL
  family                 VARCHAR(50) NOT NULL
      -- 'sink_combo','ala_carte','wc','shower','mirror','mirror_cabinet','furniture_set'
  doc                    JSONB NOT NULL                  -- layer definitions with named slots
  print_size             JSONB NOT NULL DEFAULT '{}'     -- {width_mm, height_mm}
  company_id             UUID FK companies NOT NULL
  created_at / updated_at / created_by

  INDEX (family)
```

### Page extension

```
dealer_kit.page (existing)
  + kind                 VARCHAR(20) NOT NULL DEFAULT 'catalogue'
                         -- 'catalogue' | 'tag_sheet'
  + request_id           UUID FK price_tag_requests ON DELETE SET NULL NULL
```

All existing pages get `kind = 'catalogue'`, `request_id = NULL`.

### Tag sheet document model

Stored in `page_version.doc` when `page.kind = 'tag_sheet'`:

```jsonc
{
  "kind": "tag_sheet",
  "imposition": {
    "preset": "a4_3up",           // "a4_3up" | "a4_2x2" | "custom"
    "page_width_mm": 210,
    "page_height_mm": 297,
    "bleed_mm": 3,
    "gap_mm": 2
  },
  "sheets": [{
    "id": "s1",
    "tags": [{
      "id": "t1",
      "template_id": "uuid-of-tag-template",
      "request_line_id": "uuid-of-request-line",
      "x_mm": 5, "y_mm": 5,
      "width_mm": 95, "height_mm": 130,
      "layers": [{
        "id": "l1",
        "type": "image",           // image | text | shape | product_slot | price_field | badge | group
        "x_mm": 10, "y_mm": 20,
        "width_mm": 50, "height_mm": 30,
        "rotation_deg": 0,
        "z_index": 1,
        "locked": false,
        "visible": true,
        "props": { /* type-specific: src/assetId, text/font/size/color/align, shape/fill/stroke, field binding */ },
        "slot_binding": "product_image",  // named slot or null for free layers
        "text_override": null             // non-null = unlinked from product data
      }]
    }]
  }]
}
```

**Layer types and props:**

| type | props | slot_binding values |
|---|---|---|
| `image` | `assetId`, `fit: 'cover'\|'contain'`, `cropRect` | `product_image` |
| `text` | `text`, `fontFamily`, `fontSize`, `fontWeight`, `color`, `align`, `lineHeight`, `letterSpacing` | `code`, `name`, `dimensions`, `spec_lines`, `included_accessories` |
| `shape` | `shape: 'rect'\|'rounded_rect'\|'ellipse'\|'line'`, `fill`, `stroke`, `strokeWidth`, `cornerRadius` | null (decorative) |
| `product_slot` | `fieldKey` | `product_image`, `code`, `name`, `dimensions`, `spec_lines` |
| `price_field` | `priceType: 'list'\|'sell'\|'both'`, `format` | `list_price`, `sell_price` |
| `badge` | `assetId` (from dealer-kit badge/icon library) | `badges` |
| `group` | `children: layer_id[]` | null |

**Slot resolution at render:**

1. `request_line_id` on a tag identifies the line.
2. Line's `product_id` or `product_set_id` resolves product data (name, code, dimensions,
   description/specs) from the product master.
3. Prices resolve via `resolve_prices()` using the request's `promotion_id` + viewer context.
4. `marketing_price_override` on the line wins over resolved price when set.
5. `text_override` on a layer wins over slot-resolved value. "Relink" clears the override.
6. Set lines: `set_members[]` slot iterates `product_set_members` and resolves each.

---

## 4. Slices

### S0 - Foundation (migration + data)

- `contact_access_types.portal_form_types` column + migration seed
- `contact_portal_form_overrides` table
- `sales_agents.contact_id` FK + Sales Agent form edit
- `customers.sales_agent_id` FK + Customer form edit
- `price_tag_requests` + `price_tag_request_lines` tables
- `dealer_kit.tag_templates` table
- `dealer_kit.page.kind` + `request_id` columns
- Register `price_tag_request` in `FORM_SLA_TYPES`
- Seed `form_sla_configs` (marketing stage)
- Seed permissions
- Doc number generator
- Portal `SUPPORTED_TYPES` expansion
- Portal form visibility resolver (access-type union + per-contact overrides)

### S1 - Portal request form (FE mock + set guard)

- Portal request form: product/set picker, alternatives, debtor dropdown (scoped), promotion
  picker, PO upload, deadline, notes, quantity per line
- Set guard validation (hard block on Bathroom Furniture ala carte)
- Portal request list + detail page
- Draft save + submit flow
- CRM: Dealer Kit -> Price Tag Requests DataGrid listing + claim + detail page

### S2 - Request lifecycle (BE wiring + tests)

- Request CRUD endpoints (portal + CRM sides)
- Status transition engine with validation
- Form SLA stage chain integration
- Notifications via form_sla_config
- Debtor lookup scoping (agent's orders + prior requests)
- Portal form visibility enforcement on all portal endpoints
- Tests: transitions, guard, doc number, visibility, debtor scoping

### S3 - Tag template editor + canvas foundation

- Tag template CRUD API
- Canvas editor component: absolute positioning (mm units), single layer operations
  (move, resize, rotate), snap grid + alignment guides, undo/redo
- Layer model: z-order, layers panel, multi-select, group, duplicate, copy-paste, nudge
- Content types: text (font/size/weight/color/align/line-height/letter-spacing), shapes
  (rect/rounded/ellipse/line, fill/stroke), image (crop/fit/mask to shape)
- Badge/icon library picker from dealer-kit assets
- Rulers + mm coordinate inspector
- Colour palette + brand swatches
- Locked layer enforcement
- Template save/load, family catalog
- CRM: Dealer Kit -> Tag Templates management page

### S4 - Tag sheet designer + product binding

- Tag sheet page creation from request (`Page.kind = 'tag_sheet'`, `request_id`)
- Tag sheet document schema (sheets -> tags -> layers)
- Designer UI: left panel = request lines, drop onto sheet creates tag from family template
- Product slot binding: auto-fill from product data
- Price field rendering: LP / LP struck + SP NETT based on `show_promo_price`
- Imposition presets (A4 3-up, 2x2, custom) + bleed/crop marks
- Marketing price override per line with reason
- Proof marking: `designing -> proof_ready` transition from designer

### S5 - Export + proof review

- PDF export for `tag_sheet` pages through existing `catalogue_render` pipeline
- `TagSheetRenderer` (print page, same headless-Chromium flow)
- Single-sheet export with `sheet_ids` filter
- Expired-promotion guard on export
- Portal proof review: rendered proof view, approve/request changes actions
- Download on portal request detail + CRM My Downloads
- PO cross-check Phase 1: side-by-side viewer (PO attachment + request lines with prices)

### S6 - PO cross-check automation (Phase 2)

- AI extraction from PO PDF (existing AIExtractDialog/extraction pattern)
- `po_extraction_result` JSONB stored on request
- Per-line discrepancy table (code, price, qty match/mismatch/missing)
- Mismatch resolution workflow (accept with reason / fix)
- Block `proof_ready` until all mismatches resolved
- Discrepancy display on CRM detail + portal proof review

---

## 5. What will bite, addressed up front

### The canvas editor is the biggest piece

S3 is a design tool. It is not a form, not a listing, not a CRUD page. The risk is scope
creep toward Illustrator. The v1 boundary is explicit (items 1-12 in D19) and v2 is named
(D20). The template + slot model keeps marketing productive without full free-form design:
most tags start from a template and get nudged, not drawn from scratch.

**Library choice matters.** Options: (a) Konva (canvas-based, good perf, React bindings via
react-konva, MIT); (b) Fabric.js (canvas-based, rich feature set, FOSS but heavier);
(c) pure SVG/DOM (simpler mental model, mm units natural, but perf at many layers).
Recommendation: **Konva** - React-friendly, handles the v1 feature set, rotation/snapping/
grouping built in, mm-to-pixel scaling is a viewport transform. SVG is the fallback if
canvas-to-print fidelity is a problem (the print renderer is DOM/CSS, not canvas).

### Price resolution at print time, not design time

The designer shows resolved prices for feedback, but the doc stores only bindings. The print
renderer re-resolves. If a promotion expires between design and print, the export is refused
(AC-H.2). Marketing must either remove the promotion or extend it. This is the ADR 0008
contract applied to a new surface.

### Portal visibility is shared infrastructure

AC-A.1-A.4 changes the portal for ALL form types, not just price tags. The migration seeds
must preserve existing behavior (every contact sees what they see today). Test coverage must
verify that a dealer-type contact still sees stock_inquiry after the migration.

### Set guard depends on product class derivation

`product_class_signal.py` derives "Bathroom Furniture" from product attributes. If a cabinet
product has not been classified, the guard cannot fire. The notification to marketing (AC-D.1)
when a cabinet belongs to zero sets is the safety net.

---

## 6. Test strategy

| Slice | Test type | What |
|---|---|---|
| S0 | pytest | Migration up/down, portal visibility resolver (union + override logic), doc number generation |
| S1 | vitest | Portal form component rendering, set guard inline validation |
| S2 | pytest | Status transitions (valid + invalid), set guard (block + pass), debtor scoping, visibility enforcement |
| S3 | vitest | Canvas layer operations (add/move/resize/rotate/delete), undo/redo stack, snap calculations, locked-layer enforcement |
| S4 | vitest + pytest | Tag placement from template, slot resolution, price field formatting, imposition layout math |
| S5 | pytest | Export with sheet filter, expired-promo guard, status transition on export |
| S6 | pytest | AI extraction mock, discrepancy detection, mismatch resolution |

Browser verification (agent-browser) required for S1, S3, S4, S5.

---

## 7. Order of work

```
feat/product-sets merges to main
         |
         v
   S0 (foundation)
         |
    +----+----+
    |         |
    v         v
   S1        S3
  (portal    (canvas +
   form)     templates)
    |         |
    v         |
   S2         |
  (lifecycle) |
    |         v
    +----+----+
         |
         v
        S4
   (tag sheet
    designer)
         |
         v
        S5
   (export +
    proof)
         |
         v
        S6
   (PO auto-
    check)
```

S1 and S3 can run in parallel after S0. S4 needs both S2 (request lines to bind) and S3
(canvas to compose on). S5 needs S4. S6 is Phase 2, independent sprint.

---

## 8. S3b - Enrich the tag canvas with the catalogue builder's data layer

**Status:** Slices 1-5 BUILT 2026-08-25 (types + `price_badge`, tag-data endpoints and bound
blocks, assets/product images/fonts, presets, and the eight seeded starter templates).
AC-L.9 and AC-L.10 are met: `scripts/seed_tag_templates.py` uploads the 28 manifest assets and
inserts the eight templates idempotently, and each family is screenshotted beside its PDF page in
`seed-assets/verification/` with the gap list in that folder's README. Builds on S3/S4/S5 as
merged in PR #289.

**Deviation recorded during slice 5.** The eight families use the EXISTING
`TagTemplateFamily` keys where one fits (`sink_combo`, `ala_carte`, `mirror_cabinet`, `shower`,
`wc`, `furniture_set`) and add the two the list genuinely lacked, `art_basin` and `urinal`. The
alternative - seeding keys outside the list - would have shown the raw key in the listing and made
neither pickable in the template dialog. `lineFamily` in `TagSheetDesigner` still never selects the
two new families; that is named in the verification README as outstanding.

### Why

The canvas is the right editing model for a print tag (free-form, mm, layers); the grid builder
is the right model for a responsive web catalogue. What the canvas lacks is not editing but the
data plumbing the catalogue builder already has: product binding, product images, the asset
library, viewer-resolved prices. S3b reuses that plumbing so every tag in
`Sorento Pricetag Template.pdf` can be designed in the system. No second copy of the data logic;
the grid builder is untouched.

### Decisions

| ID | Decision |
|----|----------|
| D26 | **`price_badge` is a dedicated layer type**, not free text. Variants `list_only` (plain `RM 1,599`) and `promo` (struck `LP: RM 1,599` + `SP RM 599 NETT`). Colours, size, radius editable; composition fixed. Bound to the tag's product/set; marketing override wins. |
| D27 | **"Add product" drops a product block**: a group of layers (image, code, name, dimensions, spec lines, price badge) bound to one product picked from a product search select. Spec lines: `product_specifications.rendered_text` / `product_flyer_text.lines` when present, else product description. Every text layer is override-able (unlink / relink). **"Add set"** drops a set-members list bound to a Product Set (`- CODE (NAME) LxWxH` per member). |
| D28 | **Presets**: "Add alternatives row" (N products, `OR` connectors, leading `+`) and "Add accessories strip" (N products or assets, small image + caption). Layers stay free after drop. |
| D29 | **Assets**: `badge` / `image` layers pick from `dealer_kit.asset` (tags `badge`, `icon`, `diagram`, `logo`) with upload-in-place. **Fonts**: `Asset.kind = 'font'` (woff2/ttf) loaded via `@font-face` in the editor and on the print page; the inspector font list = Google fallbacks + uploaded brand fonts. |
| D30 | **Product images**: image layer picker shows the product's own attachments first (primary + secondary: accessories, callouts, inside views), asset library second. Same `access_levels` gate as `primary_image_urls`. |
| D31 | **Editor price preview calls the real resolver.** `POST /price-tag-requests/{id}/resolve-prices` and a new `POST /tag-templates/resolve-preview` wrap `resolve_prices()`; the S4 mock is removed. |
| D32 | **Eight starter templates seeded from the PDF** (sink combo, sink ala carte, art basin, mirror + mirror cabinet, shower set, WC, urinal, bathroom furniture set) plus the badge assets, as a seed script, not hardcoded. Each is verified side by side with its PDF page. This is the acceptance test. |

### Layer model additions (`lib/dealer-kit/tag-template-types.ts`)

```ts
type TagLayerType = ... | 'price_badge';
{ kind: 'price_badge'; variant: 'list_only' | 'promo'; fill: string; textColor: string;
  cornerRadius: number; showNett: boolean }
// image props gain a source discriminator
{ kind: 'image'; source: { type: 'asset'; assetId } | { type: 'product_attachment'; attachmentId } | null; fit; cropRect; maskShape?: 'none'|'circle' }
// a group carries its binding so a whole product block can be re-bound or relinked at once
{ kind: 'group'; children: string[]; binding?: { product_id?: string; product_set_id?: string } }
```

### Backend

- `GET /api/v1/dealer-kit/products/search?q=` - lightweight product search (id, code, name) for the
  editor select. Reuse the master-data product query; do not build a new index.
- `GET /api/v1/dealer-kit/products/{id}/tag-data` - code, name, dimensions, spec lines, image
  attachments (gated), list price, offer price via `resolve_prices()` for the staff viewer.
- `GET /api/v1/dealer-kit/product-sets/{id}/tag-data` - members with code, name, dimensions,
  quantity, PLUS `list_price` / `offer_price` / `promotion_id`. **Amended during build:** a set
  block drops a price badge like a product block does, and with no figures on the set payload that
  badge could only ever print "Price TBC". The list price is the set's own rule
  (`resolve_set_price`, so a tag and the set's detail page agree); the offer is the same sum with
  each ticked member at its promotional price, and absent entirely when no member is on offer.
- `GET /api/v1/dealer-kit/product-sets/search?q=` - sets for the editor's picker (the master-data
  set list is a DataGrid listing, not a select).
- Assets: **there was no HTTP surface at all** - `dealer_kit.asset` rows were only ever written by
  the flyer reader - so `GET|POST /api/v1/dealer-kit/assets` was added over the existing
  `asset_service` (same file store, same storage router, same strict signing), with `kind='font'`
  added to the allowed kinds and extension validation per kind. Gated on the existing
  `dealer_kit.library.manage`, so no new permission and no grant sweep.
- **Amended during build:** the editor gets `fonts[]` and asset URLs from `GET /dealer-kit/assets`
  (which it already calls for the badge picker) rather than from the tag-template GET - one
  delivery path instead of two, and the template GET is untouched. The PRINT payload carries
  `fonts[]`, `assets{assetId: url}` and `images{attachmentId: url}` as planned.
- `POST /tag-templates/resolve-preview` - resolve a template's bindings for preview.
- Remove the Phase 1 mock in `resolve_prices_for_lines`; wire `resolve_prices()`. The body is now
  nullable (`null` = every line) and the response is the full display row - code, name,
  dimensions, spec lines, set members, gated images, both prices - which is also what the print
  payload's `resolvedData` is built from, so the designer and the PDF cannot drift.
- Seed script `scripts/seed_tag_templates.py`: uploads badge assets from
  `documentation/plans/dealer-kit/seed-assets/` and inserts the eight templates (idempotent by name).

### Frontend

- Toolbar gains: Add product, Add set, Add alternatives row, Add accessories strip, Add badge
  (asset picker), Upload asset, Upload font.
- `KonvaTagLayer` renders `price_badge`, real product images, real asset images (signed URLs).
- Inspector: binding panel on a group (which product / set, relink all), font list from assets.
- `TagSheetRenderer` (print) renders `price_badge` and `@font-face` fonts identically.

### Slice order

1. Types + `price_badge` (editor + print renderer)
2. Product search + tag-data endpoints; Add product / Add set with live data
3. Asset + product-image pickers, font assets
4. Presets (alternatives row, accessories strip)
5. Seed the eight templates; side-by-side verification against the PDF

### Tests

pytest: tag-data endpoints (gating, price via `resolve_prices`, set members), font kind accepted,
seed idempotency. vitest: `price_badge` render both variants, product block drop creates bound
group, relink restores slot text. Browser: each seeded family opened and screenshotted next to its
PDF page.

---

## 9. S3c - The tag canvas behaves like a drawing tool

**Status:** BUILT 2026-08-29. Captain's test of the S3b bed on `:3030` produced seven items:
five behaviour gaps against how Illustrator works, and two bugs. This section holds the rulings
(D33-D41) and the shape of the fix. Frontend only: no schema, no endpoint, no migration. The
document model is untouched, so every seeded template and every saved tag opens unchanged.

### What was wrong

| # | Symptom | Cause found in the code |
|---|---------|--------------------------|
| 1 | The wheel scrolls the workspace instead of zooming | The workspace was an `overflow-auto` div wrapping a Stage sized to the artboard. There was no viewport model at all. |
| 2 | A child inside a group cannot be reached from the canvas | The group's outline is a `Rect` with `fill="transparent"`, which Konva still hit-tests, and the group's `z_index` puts it on top. Every click in the block landed on the group. |
| 3 | Right-click shows the browser menu | Nothing handled `contextmenu` anywhere on the canvas. |
| 4 | No marquee, no panning choice | Selection was click-only; the container scrolled. |
| 5 | Moving a group leaves its children behind | Children are flat layers with ABSOLUTE positions and the group is a bounding box carrying `children: string[]`. Nothing propagated the delta. |
| 6 | No way to see a template against a real product without binding it | Binding is the only path to data, and binding writes into `layers`. |
| 7 | A canvas drag is silently lost on Save | `KonvaTagLayer` never set `id={layer.id}` on its Konva `Group`, so `stageRef.findOne('#id')` in `handleDragMove` / `handleDragEnd` returned `undefined`. Snap never applied and the new position was never written back to `layers`. Undo/redo then restored a document the nodes disagreed with. |
| 8 | Preview with a real product shows "No image" where the photo goes | The seeded hero layer is `{"type":"image","slot_binding":"product_image","source":null}`, because a template ships unbound. `layerDisplay` returned `{ imageUrl: null }` the moment `source` was null without ever looking at the bound product's photos, and only Rebind (which writes an attachment id into the document) filled it in. |
| 9 | The Layers panel cannot reorder or regroup anything | It was a read-only tree: click to select, eye, lock. Z order could only be changed from the canvas, and there was no way at all to move a layer into or out of a group. |
| 10 | Holding the scroll wheel and dragging draws a marquee | `handleStageMouseDown` never looked at `e.evt.button`, so every button started a band, and Konva's `dragButtons` default of `[0, 1]` let the same press drag a layer. |

### Decisions

| ID | Decision |
|----|----------|
| D33 | **Viewport model.** The Konva Stage fills the workspace container (sized by a `ResizeObserver`) and the artboard is drawn at a pan offset inside it. This replaces `overflow-auto` scrolling. View state is `{ zoom, panX, panY }`, pan in px = the artboard origin in stage coordinates. On mount the view is fit to the container with a 32px margin, centred. Rulers become viewport-wide strips whose ticks sit at `origin + mm * scale`; `CanvasRulers` takes `originX` / `originY` and loses `scrollX` / `scrollY`. |
| D34 | **Wheel = zoom at the cursor.** Multiplicative, factor 1.1 per 100 `deltaY`, clamped 0.1 to 8, and the mm point under the pointer stays under the pointer. The listener is a NATIVE one registered with `{ passive: false }`, because React's `onWheel` is passive and cannot `preventDefault`. `Cmd/Ctrl+0` fits, `Cmd/Ctrl+1` is 100%. The toolbar keeps `-` / `%` / `+` and gains Fit; the `%` readout is the 100% button. |
| D35 | **Two tools.** `select` (V) and `hand` (H) as a toolbar toggle, plus Space held = hand for as long as it is held. Hand drags the view (cursor `grab` / `grabbing`). Select drags on empty space draw a marquee. Layers are not draggable while the hand is active. |
| D36 | **Marquee.** Mousedown on the Stage or on the artboard background starts it; a translucent blue band with a 1px stroke follows the pointer; on mouseup every layer whose box INTERSECTS the band is selected (touch selects, as Illustrator does, not enclose). Scope is top-level layers, a child being represented by its outermost ancestor group, UNLESS the user is inside a group (D37), when the scope is that group's direct children. Shift is additive. A click with no movement deselects and leaves the group. |
| D37 | **Group isolation is DERIVED, not stored.** The set of entered groups = every ancestor of the currently selected layers. A group whose id is in that set renders with `listening={false}`, so its children receive pointer events; the outline stays visible, because removing the fill is not what makes a node pass through. Double-click on a group selects its top-most visible, unlocked direct child under the pointer; a nested group counts as a child, so double-clicking again goes deeper. Double-click on empty canvas clears the selection. Escape selects the parent group of the current selection, and deselects at top level. Selecting a child in the Layers panel enters the group by the same derivation, with no code of its own. |
| D38 | **Moving and transforming propagate.** Dragging a group moves every descendant, live during the drag (descendant nodes are positioned on each `dragmove`) and committed on `dragend` in ONE `setLayers` and ONE history push, so one undo reverts the whole move. Dragging any member of a multi-selection moves the whole selection plus descendants. Resizing or rotating a group applies the same affine change to descendants: positions relative to the group origin scale by `(newW/oldW, newH/oldH)` and rotate by the rotation delta about that origin, child sizes scale, child rotation gains the delta. When a CHILD is moved or transformed, every ancestor group's box is recomputed from its children with `boundsOf`, so the box stays honest. There is ONE `Transformer`, rendered after every layer and attached to the selected unlocked nodes; the per-layer `Transformer` inside `KonvaTagLayer` is removed. |
| D39 | **Group semantics for the clipboard follow Illustrator.** Copy, cut, duplicate and delete apply to the group AND its descendants. Duplicate and paste clone descendants with fresh ids and remap `children`, which also repairs a latent bug: duplicate used to copy the group layer alone, leaving its `children` pointing at the ORIGINAL children. Deleting a child prunes it from its parent's `children` and refits the ancestors. Cut is copy plus delete. |
| D40 | **Our context menu, never the browser's.** A Radix `ContextMenu` with the workspace div as `asChild` trigger. The Stage's Konva `onContextMenu` runs first, being the deeper DOM node: if the layer under the pointer is not in the selection it becomes the selection, resolved through isolation to the top-most non-entered ancestor. With a selection the items are Cut, Copy, Paste, Duplicate / Bring to Front, Bring Forward, Send Backward, Send to Back / Group (2+) or Ungroup (a group) / Enter Group (one group) or Select Parent Group (a selection inside a group) / Lock or Unlock, Hide / Delete. On empty space: Paste (disabled with an empty clipboard), Select All, Fit to View, Zoom 100%. Z reorder treats a group and its descendants as one contiguous block and renumbers `z_index` 1..n afterwards. Delete carries no confirm dialog: it is undoable and it matches the toolbar button and the Del key that already ship. |
| D41 | **Preview with a product, binding nothing.** A toolbar action opens the existing `ProductPickDialog` (mode `set` when any layer carries the `set_members` slot, else `product`), loads through `bindings.loadProduct` / `loadSet`, and holds the result in editor state as `preview: GroupBinding \| null`. While it is set, `bindingOf(layer)` returns the preview for EVERY layer, because templates ship unbound on purpose, so slot text, product image and price badge all resolve. A chip on the toolbar's right reads `Previewing: CODE - name`, changes the product when clicked and clears on its X. The preview is never written into `layers` and Save is unaffected. |
| D42 | **A product-photo slot follows the bound product's primary photo.** A layer that is ABOUT the product photo resolves in this order: the `product_attachment` source the designer pinned, when that attachment is one of the bound product's photos; otherwise the bound product's primary photo (`is_primary`, else the first); otherwise nothing. This applies to an `image` layer carrying `slot_binding: 'product_image'` and to a `product_slot` layer whose `fieldKey` is `product_image`, and it is what makes Preview (D41) show a photo at all: templates ship unbound, so their hero layer holds `source: null` and only Rebind ever wrote an attachment id into the document. An `asset` source is untouched, and an image layer with NO slot binding and a null source stays empty, because that is a decorative picture nobody chose yet. A `product_slot` layer with any other `fieldKey` resolves its text through `resolveSlotText` and draws it, keeping the dashed placeholder only when there is no data. One helper, `slotImageAttachmentId` in `product-block.ts`, answers this for the canvas and for the print page, so the proof on screen and the PDF cannot disagree; the print payload therefore carries each line's `images` list beside its resolved text. Preview still writes nothing: `source` stays null in the saved document. |
| D43 | **The Layers panel reorders by drag, and a drop into a group is a membership change.** The panel is ONE flat sortable tree (`@dnd-kit/core` + `@dnd-kit/sortable`, as `SpecRuleEditor` already does), rows in panel order, children indented under their group. Dropping a row BETWEEN two rows places it there: it takes the parent of the rows it lands among, so a drop between two children of group G joins G and a drop between two top-level rows leaves any group. Dropping ONTO a group row appends the layer as that group's last child. A group row drags with its whole subtree, and a layer cannot be dropped into its own subtree. The pure rule is `reparentLayer(layers, id, { parentId, beforeId })` in `canvas-geometry.ts`: it detaches the layer from its old parent, inserts it at the requested slot, renumbers `z_index` 1..n so the panel order IS the z order with every group's descendants a contiguous block directly below it, refits both the old and the new ancestors, and lands as ONE history entry. Locked layers still reorder, because a lock protects the canvas and not the stack. The pointer sensor activates after 6px, so click to select, the eye and the lock still behave; collapse state survives a drop; keyboard reordering is not built. |
| D44 | **The middle mouse button pans.** Holding the scroll wheel down and dragging pans the view exactly as the hand tool does, whatever tool is active, with the `grabbing` cursor for as long as it is held; it never starts a marquee, a layer drag or a selection change, and the mousedown is `preventDefault`ed so the browser's autoscroll cursor stays away. `button === 2` starts nothing, the context menu owns it. Only `button === 0` marquees, drags or selects, which also means `Konva.dragButtons` is narrowed to `[0]`: Konva's default is `[0, 1]`, so the middle button was dragging whatever layer was under it while the workspace drew a band. |

### The pure part (`lib/dealer-kit/canvas-geometry.ts`, tested first)

Everything above that is arithmetic on layers lives in one module with no React and no Konva in
it, so the rules can be tested without a canvas: `descendantsOf`, `ancestorsOf`, `topLevelOf`,
`moveLayers`, `transformGroup`, `refitAncestors`, `removeLayers`, `ungroupLayers`, `marqueeHits`,
`topmostChildAt`, `hitLayerAt`, `reorderZ`, `cloneLayers`, `zoomAt`, `fitView`, `stageToMm`,
`bandBetween`. `boundsOf` is reused from `product-block.ts` rather than copied.

`zoomAt` needs no px-per-mm constant: the base scale cancels out of
`pan' = p - (p - pan) * newZoom / zoom`, which is the whole of keeping a point under the cursor.

### What is deliberately NOT built

- No stored isolation mode. The entered set is derived from the selection every render (D37), so
  there is no second source of truth to keep in step with undo, redo or a Layers panel click.
- No nested Konva groups. Children stay flat layers with absolute positions, which is what the
  document model has always said and what the print renderer already reads. Propagation is a
  function over the layer array, not a change of representation.
- No preview field on the document. Preview is editor state and dies with the component (ADR
  0008 already forbids baking resolved values into a template).

### Tests

vitest on `lib/dealer-kit/canvas-geometry.test.ts`: descendants through a nested group, a move
that touches each layer exactly once, the affine propagation of a resize plus a rotation, ancestor
refit after a child move, marquee touch-selection in both scopes, hit resolution with and without
isolation, z reorder keeping a block contiguous, clone id remapping, zoom keeping the point under
the cursor, fit centring the artboard. Browser: the seven items above, each shown to work.

---

## 10. Portal form feedback, 30 Aug

**Status:** BUILT 2026-08-30. The captain opened the portal form after S3c and produced three
items, all on the salesperson's side of the feature: the request type was reachable only through
a link button of its own, the debtor dropdown was empty with nothing said about why, and the
lines section asked a dealer to decide "product or set" before it would let them pick anything.

### What was wrong

| # | Symptom | Cause found in the code |
|---|---------|--------------------------|
| 1 | Price Tag Request is a separate page behind a link button, not one of the things the landing dropdown offers | `PortalLanding` builds its dropdown from `SUBMISSION_KINDS`, and `price_tag_request` is deliberately not in that list because the generic `[type]` route guards key off it. Commit 0f0b07590 added a link button beside the dropdown rather than extending the dropdown. |
| 2 | The debtor dropdown is empty and says nothing | The options come from `/portal/lookups/debtors-for-agent`, which returns `[]` when no `sales_agents.contact_id` points at the contact. Nothing in the database links a contact to an agent, because no admin surface was ever built to set it: the column shipped with the feature and has never been writable. |
| 3 | Two Add buttons and a card per line, and a dealer must know product from set before picking | The lines section was built as one card per line with the line type chosen by which Add button was pressed, so the picker could only be shown after the type was known. |
| 4 | A saved draft with a product line would be refused by Postgres | Not reported, found while reading item 3. `price_tag_request_lines.product_id` is a UUID FK to `products.id`, but the portal's `/lookups/products` returns no id at all, so `price-tag-request-service.ts` used `product_code` as the id and the form posted a code into a uuid column. The set picker was worse: `lookupProductSets` was a stub returning `[]`, so a set line could never be filled in. |

### Decisions

| ID | Decision |
|----|----------|
| D45 | **Price Tag Request is one of the landing dropdown's options, and the link button goes.** The option list is a derived `LANDING_KINDS`: the four legacy `SUBMISSION_KINDS` (ungated, unchanged) plus `price_tag_request` when `contact.visible_form_types` includes it. It carries the same label, count badge, star, search box, status filter and card pattern as the others, its rows open the existing `/portal/price_tag_request/{id}` detail page and its New button the existing new page. `price_tag_request` stays OUT of `SUBMISSION_KINDS`, because the generic `[type]` route guards use that list to decide what the shared submission pages may render; `LANDING_KINDS` is the extension point and the next gated form joins there. The list endpoint answers a different shape from the legacy kinds (`{items: [...]}` of price tag rows, not `PortalSubmissionSummary`), so the adaptation happens once in `price-tag-request-service.ts` and no legacy endpoint changes. `?type=price_tag_request` and the starred default tab accept the kind, and fall back to `stock_inquiry` for a contact whose grant does not include it rather than showing an option the server would refuse. `PriceTagRequestListItem` gains `portal_draft_at` so the Draft filter tells the truth about a request that was saved and never submitted; without it every draft would read as New (`response_model` and a response schema both drop what they do not declare). |
| D46 | **An empty debtor dropdown says why, and an admin can fix it.** Two halves. (a) The portal form distinguishes "the lookup answered nothing" from "the lookup failed": on an empty answer it replaces the select with an inline notice naming the cause and the next step, on a failure it keeps the existing error toast, and Submit stays blocked either way because a request without a dealer is not a request. (b) `sales_agents.contact_id` becomes writable from the Sales Agents master screen: the edit modal gains a "Linked portal contact" field, a server-searched clearable `SearchableSelect` over `respond_contacts` showing name plus a masked phone and never an id. It rides the existing `PATCH /master-data/sales-agents/{id}/annotation` body, which is `extra="forbid"`, so the key is declared on `MirrorAnnotationUpdate`; `SalesAgentResponse` declares `contact_id` and a resolved `contact_name` beside it, because a response schema drops an undeclared field and the modal would open blank on a row that IS linked. No DDL: the column has no unique constraint and none is added, so two agents can point at one contact and the screen simply shows what is there. |
| D47 | **One lines table, one Add button, one Item dropdown that offers sets and products together.** The lines section is rebuilt as a row-per-line table on the Purchase Request pattern in `SubmissionForm.tsx` (a `<table>` inside `overflow-x-auto`, an `AsyncCombobox` per picker cell, a trash button per row, one Add button under it). Columns: `#`, Item, Qty (tags), Alternatives, Accessories, and the row actions. The Item cell is ONE server-searched combobox whose results are sets and products in the same list, each option prefixed with the word `Set` or `Product`; picking one sets the row's `line_type` to `product_set` or `product` and the matching id. Alternatives is the existing multi-select and is disabled on a set row, with a title saying why, which is the capability the old Set card simply did not have. The submit payload shape is unchanged: `{line_type, product_id, product_set_id, show_promo_price, quantity, alternatives, included_accessories}` with `line_type` in `('product','product_set')`, exactly as `PriceTagRequestCreate` and the table's `ck_price_tag_request_lines_one_ref` already require. **Deviation from the brief, recorded here because the brief said this item changes no backend:** the picker needs real ids and no portal endpoint returns one, so `GET /portal/lookups/price-tag-items?q=` is added, gated by the same `_assert_visible` as the rest of the price tag routes and answering `[{kind, id, code, name}]` merged from `tag_data_service.search_products` and `search_product_sets`. Without it the Item column could only post a product CODE into a uuid FK (which is what the form does today and why no draft with a product line can have ever saved) and could never offer a set at all, since `lookupProductSets` was a stub returning `[]`. One endpoint for one dropdown, not two calls per keystroke. The server-enforced Bathroom Furniture set guard is untouched and its 422 still surfaces on submit. |

### What is deliberately NOT built

- No gating of the four legacy kinds. They are ungated today and D45 does not change that; the
  landing simply stops pretending `price_tag_request` is not a submission type.
- No unique constraint on `sales_agents.contact_id`. One contact backing one agent is the
  intent, not a rule the data can carry yet, and a migration to enforce it would fail on any
  existing duplicate the captain has not seen. The trigger for adding it: the first time two
  agents pointing at one contact produces a wrong debtor list.
- No admin surface for `contact_portal_form_overrides`. Item 2 is about the agent link; the
  override table already has a service and nobody has asked to edit it by hand.
- The standalone `/portal/price_tag_request` index page stays where it is. Nothing links to it
  any more, but it is a URL a salesperson may have bookmarked, and it costs one file.

### Tests

pytest: the annotation route writes and clears `contact_id`, the response declares `contact_id`
and `contact_name` (the exact-key-set assertion in `test_sales_agents_master_api.py` is what
catches the drop), an omitted key still leaves the link alone, and the merged item lookup returns
products and sets with their real ids and honours `q`. vitest: the landing lists Price Tag Request
with a count for a contact whose `visible_form_types` include it and does not for one whose do not,
a `?type=price_tag_request` deep link for that second contact falls back instead of crashing, the
debtor notice appears on an empty lookup and not on a failed one, and the lines table posts
`line_type: 'product_set'` for a picked set and `'product'` for a picked product with alternatives
disabled on the set row.

---

## 11. Round 4, 30 Aug: a draft that saves, and a Submit that says what is missing

**Status:** BUILT 2026-08-30. The captain filled the form (debtor ARDENCY CONSTRUCTION, needed by
31/08/2026, notes, a CABANA set on line 1 and product SRTWC286-SH on line 2), pressed Submit, and
could not tell what was still required. Second item, verbatim: "save as draft shouldn't need to
check for required fields."

### Step 0: what the reproduction found

Rebuilt exactly that form state on the lane and pressed Submit. The toast reads **"Field required"**
and nothing else. The backend log has the matching line:

```
POST /api/v1/public/portal/submissions/price_tag_request - Status: 422
{"detail":[{"type":"missing","loc":["body","fields"],"msg":"Field required", ...}]}
```

`body.fields` is not a field of a price tag request. **The request never reached the price tag
route.** `app/api/v1/public/__init__.py` includes `portal.router` BEFORE `portal_price_tag.router`,
both under `/portal`, and Starlette serves the first route whose path matches. `portal.py` declares
`POST /submissions/{kind}`, `PUT /submissions/{kind}/{id}`, `GET /submissions/{kind}/{id}` and
`POST /submissions/{kind}/{id}/submit`; every price tag path of that shape matches them first.
`price_tag_request` is in `SUPPORTED_TYPES`, so `_check_kind` waves it through instead of rejecting
it, and the generic handler's `SubmissionPayload` requires a `fields` dict the price tag payload has
never had. The 422 the salesperson sees is a pydantic error about a schema for a different form.

The same shadowing had already broken the rest of the flow, unnoticed because only the list was ever
exercised in a browser:

| Path | Went to | Result before this round |
|------|---------|--------------------------|
| `GET /submissions/price_tag_request` | the price tag route (one segment, matches no generic route) | worked, which is why the landing looked healthy |
| `POST /submissions/price_tag_request` | `portal.py` `POST /submissions/{kind}` | 422 "Field required" - no request could be created at all |
| `GET /submissions/price_tag_request/{id}` | `portal.py` `GET /submissions/{kind}/{id}` | 400 "Unsupported submission type" from `PortalService.get_submission`, which has no branch for the kind. The FE reads that as "not found" and bounces back |
| `PUT /submissions/price_tag_request/{id}` | `portal.py` `PUT /submissions/{kind}/{id}` | 422 "Field required" |
| `POST /submissions/price_tag_request/{id}/submit` | `portal.py` submit | 400 "Unsupported submission type" |

So the honest summary of the captain's report: Submit did not fail validation, it never ran. This is
the SLA route-shadowing lesson again, one router apart instead of one file.

Two further findings from reading the same path:

- There is no `GET` detail route for a price tag request on the portal at all. Even unshadowed,
  reopening a saved draft had nothing to call.
- `Save Draft` refused to run without a debtor, and `price_tag_requests.debtor_name` and
  `needed_by_date` are `NOT NULL`, so a sloppy draft could not be stored even if the route worked.

### Decisions

| ID | Decision |
|----|----------|
| D48a | **Save as draft validates nothing.** The only client-side requirement is that there is something to save: a debtor, a date the salesperson changed, a note, or a line. The backend accepts a draft create or update with no debtor and no needed-by date, which takes DDL: both columns become nullable. `PriceTagRequestCreate` declares them `Optional`, and so do `PriceTagRequestResponse` and `PriceTagRequestListItem`, because a schema drops nothing but it does refuse to serialise a `None` into a non-optional field. Every reader renders a dash rather than crashing: the portal list card, the portal detail, the CRM list and detail, and the landing summary adapter (whose card title falls back to the doc number). **Completeness is enforced on SUBMIT, not on save** - a draft can be sloppy, a submitted request cannot. The needed-by input starts EMPTY rather than pre-filled with the next business day: a deadline nobody chose is not an answer, the column now accepts none, and Submit asks for it by name. The next business day stays as the input's `min`. |
| D48b | **Submit explains itself.** The button stays ENABLED whenever the form is not busy. The click runs the checks and renders them where the problem is: red text under Debtor and under Needed by, a message on each incomplete row and on any row the server's set guard named, and one summary line above the actions ("2 things need attention"). The first error is scrolled into view. A server refusal lands on the same surfaces: `AppException.detail` carries a comma-separated list of field keys (`debtor_name`, `needed_by_date`, `lines`, `line:<sort_order>`) beside the human sentence in `message`, the form routes each key it recognises to its inline surface, and anything it does not recognise falls back to the toast it shows today. `detail` is a plain string because that is what `AppException` declares; a key the form cannot place is a message, not a crash. |
| D48c | **A draft is a real record: it saves, it lists, it reopens, and it can be deleted.** After a draft save the form routes to the portal landing filtered to the kind, where the row reads Draft (`portal_draft_at`). Reopening it loads the partial state - a null debtor is an empty select, a null date an empty date input - and the form is editable because it is a draft, which is `portal_draft_at`, not `status === 'draft'` (a draft's status is `new`; the old check was against a status that never exists and would have shown a read-only page). Save on an already-saved draft UPDATES it instead of creating a second one, lines included. Delete draft is offered on the draft's own form behind an `AlertDialog`, exactly as `SubmissionForm` offers it for the legacy kinds, and hard-deletes the request with its lines. |
| D49 | **The price tag router is mounted before the generic portal router, and the two routes it was missing are added.** Mount order is the whole fix for the shadowing: `portal_price_tag.router` declares only literal `price_tag_request` and `price-tag-*` paths, so putting it first captures exactly the requests meant for it and leaves every legacy path with the generic handler. `price_tag_request` stays in `SUPPORTED_TYPES` (the attachment helpers and the visibility service read that list) - the ordering, not the list, is what decides who serves the request. Added beside it: `GET /submissions/price_tag_request/{id}`, answering the same body the CRM detail route does (lines resolved to code, name and both prices through `tag_data_service`, so the portal and the print payload cannot disagree), and `DELETE /submissions/price_tag_request/{id}` for a draft only. The line resolution helper moves from the CRM route module into `PriceTagRequestService` so both routes call the one implementation. |

### Found while proving it, on the lane

- **Every line came back with `sort_order` 0.** `PriceTagRequestLineCreate.sort_order` defaulted to
  `0` and the portal sends no sort order at all, so `line_data.get("sort_order", idx)` never reached
  its fallback and the relationship's `order_by(sort_order)` returned the lines in whatever order
  Postgres liked. The row a refusal names has to be the row on screen, so the field is now
  `Optional[int] = None` and the position fills it. Fixed here, tested.
- **The set guard cannot see a product outside the caller's company scope, and passes in silence.**
  On the lane, `CBF66406` is a Bathroom Furniture product belonging to company MOCHA while the portal
  contact's scope is Sorento, so `db.query(Product)` returns nothing and the line submits ala carte;
  the same request refuses correctly for `SRTBF11721`, which is Sorento's. Not caused by this round
  and not fixed in it: the guard has never actually run in production (the route it lives on was
  shadowed), and the fix is a decision about which company a portal price tag request and its
  catalogue belong to, which is the captain's to make. The same scope explains the blank `code` and
  `name` on a Mocha line in the detail body.

### What is deliberately NOT built

- No structured (JSON) error body. `AppException.detail` is a string in this codebase and one
  comma-separated list of field keys answers the whole journey. The trigger for a richer shape:
  the first error that needs to carry a value as well as a field name.
- No client-side mirror of the Bathroom Furniture set guard. It stays server-enforced and its 422
  now lands on the offending row instead of a toast, which is what was missing.
- No draft autosave, and no unsaved-changes prompt. Save Draft is one button away.
- No `NOT NULL` replacement for the two columns at submit time (a partial index or a check
  constraint). Submit validates in the service, where the message that names the missing field is
  written; a constraint would only produce a violation nobody can read.

### Tests

pytest: a draft created with nothing but one line, a draft created with nothing but a debtor, a
draft update that clears the debtor, submit refused with every missing field named in `detail`,
submit refused for a line with no item, the set guard naming the line index, the happy submit
unchanged, and the mounted route order actually serving the price tag create (a create through the
app, not through the service, is the only thing that would have caught the shadowing). vitest: Save
Draft posts with a null debtor and a null date, Save Draft is disabled only while the form is
completely empty, a Submit click with an empty debtor renders the inline error and posts nothing,
and a server 422 naming `line:0` lands on the first row.

---

## 12. Round 5, 30 Aug: the CRM page wears the house chrome, and designing a request IS the editor

**Status:** BUILT 2026-08-30. Two items from the captain's test of the CRM side. First, verbatim:
"why is this one not having the same form design as other forms like complaint, stock inquiry...
not necessarily same fields, the design taste: the CTA button, secondary buttons in gear dropdown,
next/prev, back button." Second: "the design page is different from my template design... they
should be the same layout, and how can I pull out the template from the template I have designed."

### What was wrong

`PriceTagRequestDetail` was written before the house pattern was read. It carried its own chrome:
an "Back to list" ghost button in a row of its own, a `RecordNavigation` hard-wired to
`prevId={null} nextId={null}` (so the chevrons were permanently dead), the document number inside
a card body rather than in a page heading, and a **row of five peer buttons** in a second card,
each of them equally loud, so nothing on the page said what to do next. Every other form detail
page in this codebase - `stock-inquiries/[id]`, `complaints/[id]` - has the same shape and none of
it was used.

The design page had drifted the other way. `/design` was `TagSheetDesigner`: a lines rail on the
left that PLACED a line on an A4 sheet, an imposition sidebar on the right, and tags that were
**read-only objects on the sheet**. Nothing about a tag could be edited there, which is the one
thing the page exists for. The editor that CAN edit a tag, `TagCanvasEditor` with the whole D33-D44
interaction model, was reachable only from Tag Templates, where edits change the template for every
future request instead of this one's tag.

### Decisions

| ID | Decision |
|----|----------|
| D50 | **The CRM request detail page is the same page as the other form details.** `Container` + breadcrumb (the page's own way back - the ad-hoc "Back to list" button is deleted, exactly as stock inquiries and complaints have none), then a header row: the document number as the `h1`, a `Created: ... - <status pill>` subline, and the read-only metadata (debtor, salesperson, promotion, needed by, assigned to) in the header, never in a tab body. On the right of that row, in this order: **ONE primary CTA**, the gear `DetailActionsMenu` holding every secondary action, and `RecordNavigation`. Sections below are cards in the house rhythm: Lines, PO attachments, Proof. Where the two references disagree the newer one wins: stock inquiries puts export in the gear and complaints leaves it out as a peer button, so **every** secondary action here is a gear item (Design tags when it is not the primary, Mark proof ready, Export PDF, Open proof, Void). Void keeps its `AlertDialog`. Prev/next stops being dead: there is no neighbours endpoint for this resource and one is not worth building, so `RecordNavigation` is used in its LIST mode over the request list the page already has a service for. |
| D51 | **`/dealer-kit/price-tag-requests/{id}/design` IS the template editor, with a request rail.** Top: a slim request bar (document number, `Design | Arrange` segmented control, Save, Mark proof ready) above the unchanged `CanvasToolbar`. Left column: a "Lines" rail ABOVE the Layers panel - code, name, qty, family, and a check once that line's tag has been designed. Centre: `TagCanvasEditor` on the SELECTED line's tag. Right: the Inspector as it stands. A line's tag is a `PlacedTag`: on first selection of a line with no tag, its layers are cloned from its DEFAULT template (the family-prefix rule, `lineFamily`) through `bindTemplateLayers`, and the editor draws every layer against the LINE (`TagBindingData` kind `'line'`, which the resolver already answers), so the real code, photo and price show. Edits land in that `PlacedTag.layers`; **the template is never written from here**. "Use template..." on the rail row and in the Inspector opens a template picker (any family, the line's own family first) and re-clones; when the tag already has edits an `AlertDialog` confirms the replace. "Reset to template" is the same picker preselected on the current template. The artboard is the template's `print_size`. Sheet arrangement is DEMOTED to the `Arrange` half of the segmented control: the old sheet canvas and imposition controls, kept; on save every line's tag is laid out in line order, `quantity` times, on the request's preset, so nobody has to drag - and a manual drag in Arrange is kept, pinned by line and copy index. `TagSheetDoc`, the print page and the worker are untouched; only where the layers come from changed. |
| D52 | **The primary CTA is the next lifecycle action.** `new` = Claim (Design is not offered before the claim); `designing` and `changes_requested` = Design tags; `proof_ready` = View design (the designer, showing the proof that was sent - there is no separate CRM proof surface and inventing one is not this round's job); `approved` and `ready` = Export PDF; `rejected` and `void` = none. Everything else that is legal at that status lives in the gear. |

### What was deleted

`TagSheetDesigner.tsx` in whole. Its read-only `SelectedTagInspector` and its drag-to-place lines
rail are what D51 replaces, so leaving them would have shipped two designers for one job. The sheet
canvas, the sheet tabs and `ImpositionControls` moved into `ArrangeSheetView.tsx` and are what the
Arrange half renders; `computeImpositionSlots` moved into `lib/dealer-kit/request-tags.ts` where it
is tested.

### What is deliberately NOT built

- No neighbours endpoint for price tag requests. The list is one call and already client-paginated,
  so `RecordNavigation`'s list mode answers prev/next with no backend at all. The trigger for the
  endpoint: a request list long enough that fetching it to navigate is felt.
- No second editor and no shared "editor host" abstraction. `TagCanvasEditor` gained four optional
  props (a left rail slot, the bound data to draw against, a layers-changed callback, and a
  "Use template" hook for the Inspector) rather than being wrapped: one component, two callers.
- No per-line undo history that survives switching lines. Switching remounts the editor on the new
  tag, which is how a drawing tool behaves when the document changes.
- No new backend route. The design document saves through the page/version route it already used.

### Tests

vitest: `lib/dealer-kit/request-tags.ts` golden tests - `defaultTemplateFor` over the family
prefixes with the ala carte fallback, `tagForLine` cloning and binding without touching the
template, `impositionSlots` per preset, and `autoArrange` laying out quantity copies in line order
across sheets with pinned drags kept and everything else flowing around them. Component tests for
the detail page: one primary CTA per status (table-driven over every status) and the secondary
actions living in the gear. No pytest: no route changed.
