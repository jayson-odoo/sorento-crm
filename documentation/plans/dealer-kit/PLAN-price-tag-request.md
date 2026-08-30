# PLAN - Price Tag Request: end-to-end flow from salesperson to print

> The design that fulfils `price-tag-request-acceptance-criteria.md`. That file is the
> contract; where this plan and the UAC disagree, the UAC wins.
> Governs: `PRINCIPLES.md` + `documentation/reference/ADR-PRODUCT-STANDARDS.md`.

**Slug:** `price-tag-request` | **Domain:** dealer-kit (sub-feature)
**Status:** S0-S5 + S3b BUILT (PR #289). S3c (section 9, D33-D41) BUILT 2026-08-29 from the
captain's test of the S3b bed; D42-D44 BUILT 2026-08-30 from the second round of that test;
D45-D47 (section 10) BUILT 2026-08-30 from the captain's test of the PORTAL form; D48-D49
(section 11) BUILT 2026-08-30 from the round that followed it; D50-D52 (section 12) BUILT
2026-08-30 from the captain's test of the CRM detail and design pages; D53 (section 9) BUILT
2026-08-30, preview per block on a multi-product template; D54-D59 (section 13) BUILT
2026-08-30, colour picker plus merge fields; D60 (section 9) BUILT 2026-08-30, arrange
works inside a group; D61 (section 14) BUILT 2026-08-30, the form deploys granted to
nobody and admins switch it on per access type. The seventeen review findings of 30 Aug
(section 15) are FIXED, each with the test that reproduced it written first.
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
| 11 | Send to Back on a badge INSIDE a product block leaves it above the block's photo | `reorderZ` built one unit per TOP-LEVEL layer and mapped every selected id through `topLevelOf`, so a selected child reordered its whole block among the top-level layers and kept its own place inside the block. Bring Forward, Send Backward and Bring to Front on a child failed the same way. |

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
| D53 | **Preview is per BLOCK, not per template.** D41 kept one `preview: GroupBinding \| null` and handed it to every layer, so a template with four product blocks showed the same product four times. Editor state becomes `previews: Record<groupId, GroupBinding>` and `bindingOf(layer)` reads: the layer's block has a preview, use it; else the block's own binding; a slot-bound layer in NO block follows the FIRST previewed block in document order; anything else nothing. A block nobody previewed keeps its placeholders. A block is **previewable** when it is a group whose `binding` is not explicitly `null` and at least one of its children carries a slot in `{product_image, code, name, dimensions, spec_lines, list_price, sell_price, set_members, included_accessories}`; its mode is `set` when it holds `set_members`, else `product`. The `binding: null` half is what keeps the accessories strip out of the list: the seed writes `binding: {}` on a block that is MEANT to be bound and `null` on one that is not, and the strip's title carries `included_accessories`, so the slot list alone would have offered a product picker for a block that can never hold one. **Toolbar "Preview with...":** one previewable block keeps D41's behaviour (the `ProductPickDialog`, the `CODE - name` chip); several open a `Dialog` titled "Preview with products" with one row per block - the block's label, a clearable server-searched `SearchableSelect` in the block's mode, its current choice shown - where Apply loads each choice through `bindings.loadProduct` / `loadSet` and Clear all empties the map. The chip reads `Previewing: CODE - name` for one block and `Previewing 2 of 4 blocks` for several; clicking it reopens the same surface and its X clears every block. **Inspector:** a selected block, or a child of one, offers "Preview this block with..." for that block alone and shows what it is previewing with a clear beside it. **Block labels** must be told apart and must never be an id: the Layers panel's `layerDisplayName` moves to `product-block.ts` and is reused, then the block's ordinal in document order and its `code` child's placeholder are appended, because three unbound alternatives all read `Group (5)` on their own. The request designer (D51) is untouched: it binds a line and never previews. Nothing here reaches `layers`, so Save is unaffected. |
| D60 | **Arrange works inside a group, the way Illustrator arranges within the current group.** `reorderZ(layers, ids, direction)` acts at the level of the selection's COMMON parent rather than always at the top. When every selected id has the same immediate parent group P, the units being reordered are P's DIRECT children, each carrying its own subtree, and `direction` moves them among themselves exactly as it moves top-level layers; the rest of the document keeps its order, the whole document is renumbered `z_index` 1..n, every block stays contiguous and a group layer stays directly above its subtree. A top-level selection behaves exactly as it did. "Same parent" means the IMMEDIATE parent, so arranging inside a nested group moves among that inner group's children only and leaves the outer order alone. A MIXED selection (a child of P together with a top-level layer, or children of two different groups) has no common parent to arrange within, so it falls back to today's top-level semantics: each id is taken as its top-level block. Illustrator is the reference here because that is the tool the request was written against: Send to Back on a badge means the back of ITS block, not the back of the tag. |

### The pure part (`lib/dealer-kit/canvas-geometry.ts`, tested first)

Everything above that is arithmetic on layers lives in one module with no React and no Konva in
it, so the rules can be tested without a canvas: `descendantsOf`, `ancestorsOf`, `topLevelOf`,
`moveLayers`, `transformGroup`, `refitAncestors`, `removeLayers`, `ungroupLayers`, `marqueeHits`,
`topmostChildAt`, `hitLayerAt`, `reorderZ`, `cloneLayers`, `zoomAt`, `fitView`, `stageToMm`,
`bandBetween`. `boundsOf` is reused from `product-block.ts` rather than copied.

D53's rules are arithmetic on layers too, but they are about BINDING rather than geometry, so they
sit in their own module, `lib/dealer-kit/preview.ts`: `previewableBlocks`, `previewBlockOf` and
`previewBindingFor`. `previewBindingFor` answers only "which preview applies to this layer", and
the editor falls back to the document's own binding, so the one function that is worth a golden
test does not need the whole editor to state it.

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
the cursor, fit centring the artboard. For D60: a child sent to the back lands below its siblings
and above nothing outside the block, a child brought forward swaps with the next sibling only, the
group layer stays directly above its subtree after every direction, a reorder inside a nested group
leaves the outer order untouched, a mixed selection still behaves like a top-level one, and the
renumbering is 1..n every time. Browser: the seven items above, each shown to work.

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

### Found while proving it, on the lane

- **Mark proof ready had never worked.** `POST /{id}/transition` takes the STATUS to move to, and
  the frontend has been sending the action name `mark_proof_ready` since the feature was written,
  from the detail page and from the designer alike. The backend answered
  `409 Cannot transition from 'designing' to 'mark_proof_ready'` every time, and the toast said
  only that it failed. Both call sites now send `proof_ready`. Fixed here, proven on `:3030`.
- **A tag's edits did not survive switching lines**, in the first cut of this round. The editor was
  handed the layers the tag was CREATED with rather than the layers it currently has, so coming
  back to a line remounted the canvas on the original. Caught by measuring the inspector X before
  and after the switch, not by reading the code. The document the canvas opens on is now rebuilt
  when the TAG changes and not before.
- **`assigned_to_name` is null even on a claimed request**, so the header reads "Assigned to:
  Unclaimed" straight after a successful claim, and the CRM listing's Assigned To column shows the
  same dash. The claim writes the id; nothing resolves the name onto the response. Not caused by
  this round and not fixed in it.

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

---

## 13. Round 7, 30 Aug: a real colour picker, and merge fields inside a text layer

**Status:** BUILT 2026-08-30. Two items from the captain's test of round 6. First, the colour
control offers twelve swatches and a hex box, so any colour outside those twelve has to be typed
as a hex code. Second, and the larger one: a tag's text can draw on ONE whole product field
through `slot_binding`, but marketing writes lines that mix several ("1 product has so many
specs"), the way an email template writes `{{recipient.firstName}}` inside a sentence.

### What was wrong

| # | Symptom | Cause found in the code |
|---|---------|--------------------------|
| 1 | The colour control cannot reach a colour that is not one of twelve | `ColorPicker.tsx` is a swatch button, a hex `Input` and a popover of twelve fixed swatches. There is no spectrum control anywhere in it. |
| 2 | A text layer is either free text or ONE whole field | `layerText` returns `text_override`, else the resolved slot, else `props.text`. The three are alternatives, so a sentence that names a product's material AND its dimensions cannot be written at all: the designer types both by hand and the tag stops following the product. |
| 3 | A product's reviewed specs are unreachable from a tag | `ProductTagData` carries `spec_lines` - the rendered spec SENTENCE - and nothing key by key. `ProductSpecifications.values` holds `{"material": {"value": "ceramic"}}` per key, and no tag surface has ever read it. |

### Decisions

| ID | Decision |
|----|----------|
| D54 | **The colour control is a picker, not a palette.** The popover's PRIMARY control becomes a native `<input type="color">`, sized to a large swatch area rather than the browser's 20px default, so the full spectrum and Chrome's own eyedropper are both available with no library added. The twelve brand swatches stay under it as the quick path, and the hex `Input` stays editable beside the swatch button. The three sync both ways: picking on the spectrum calls `onChange` with the hex and rewrites the box, typing a valid hex moves the picker, and an invalid hex is ignored until it becomes valid rather than clearing the colour. `transparent` has no spectrum value, so the picker falls back to black while the swatch keeps drawing the chequerboard. One component; every colour field in the Inspector already uses it. |
| D55 | **A text layer's content may carry `{{path}}` merge fields.** The token set is fixed and small: `product.code`, `product.name`, `product.dimensions`, `product.spec_lines`, `product.list_price`, `product.sell_price`, `product.included_accessories`; `spec.<key>` for every key in the spec registry; `set.code`, `set.name`, `set.members`; `line.quantity`. `product.*` and `set.*` resolve through the SAME slot the tag already binds by, so `product.code` and `set.code` are one question asked twice - a set block's code IS its set code, and a token that read empty because the block turned out to be a set would be a trap rather than a rule. Prices render through `formatTagPrice`, the same `RM #,##0` the badge prints. Unknown path or missing data renders empty in print; in the EDITOR with no data at all the token is drawn as itself (`{{spec.material}}`), so the designer sees what will fill and not a blank tag. **No filters, no arithmetic, no conditionals.** The trigger for a formula layer is named here rather than built: the first real request for arithmetic or a condition (a price minus a deposit, "show X only when Y") is when one gets designed. |
| D56 | **One resolver, called by the canvas and by the print page.** `lib/dealer-kit/merge-fields.ts` holds `renderMergeFields(text, data, mode)` and `mergeFieldCatalog(specKeys)`; `product-block.ts`'s `layerText` runs every text layer's content through it, and `TagSheetRenderer`'s text layer stops switching on `slot_binding` for itself and calls `layerText` too. The print page's `ResolvedLineData` is the same shape as `LineTagData`, so the adaptation is one function and the two surfaces cannot resolve a token differently. A vitest renders one text layer through both and compares. |
| D57 | **A layer holding a token is dynamic, not unlinked.** `isUnlinked` today means "bound to a slot and showing typed text", and it is what puts the amber broken-link icon in the Layers panel. A `text_override` that CONTAINS a token is still following the product, so `isUnlinked` answers false for it and a new `isDynamic` answers true; the panel shows a small `{}` marker in the same place. Relink-all (D28) skips dynamic layers for the same reason: clearing an override that is doing its job would delete the designer's sentence. |
| D58 | **The data grows a `specs` list, key by key.** `ProductTagData` and `LineTagData` (and their Pydantic twins, `tag_data_service`, and the print payload in `tag_sheet_export_service`) gain `specs: [{key, label, value, unit}]`, built by joining the active spec registry against the product's reviewed `ProductSpecifications.values`. A value may be stored bare or as `{"value": ...}` - `dimensions_text` already reads both - and the unit comes from the registry, not from the row. Only keys the product actually carries are listed, so `spec.<key>` for anything else resolves empty. A set has no spec row of its own, so a set line's `specs` is empty. The catalogue's key list comes from `GET /api/v1/dealer-kit/spec-keys`, a read of `active_registry` gated on `dealer_kit.tag_templates.view` beside the editor's other data routes rather than the master-data registry route, which is gated on `master_data.products.view` - a permission the marketing role designing a tag has no reason to hold. A new spec key therefore appears in the dialog with no code change. |
| D59 | **Insert field is a dialog, and it writes ONE history entry.** The Inspector's Text section gains an "Insert field" button beside Content. The dialog holds the content in an editable textarea at the top (with the cursor position kept), a search box, the catalogue grouped Product / Specs / Set / Line with the label on the left and `{{token}}` on the right in mono, and a "Preview:" line under the list rendered by `renderMergeFields` against the layer's CURRENT data - its block's preview (D41/D53), its real binding, or the request designer's line - reading "(preview a product to see values)" when there is none. Clicking a field inserts at the cursor. Done writes the content back the way the Text section already does (to `text_override` when the layer has a slot binding, else `props.text`) and pushes one history entry, so one undo takes the whole edit back. |

### What is deliberately NOT built

- No expression language. See D55: filters, arithmetic and conditionals are named as the trigger
  for a formula layer, not shipped as an unused surface today.
- No merge fields outside text layers. A price badge is a composition (D26) and a product slot is
  one whole field by definition; neither has a sentence to put a token in.
- No colour library. `<input type="color">` is the browser's own spectrum control and already
  carries the eyedropper on Chrome, which is what the request was for.
- No stored spec ordering for the catalogue. The registry's own key order is used, and the search
  box is what finds a key in a long list.

### Tests

vitest `lib/dealer-kit/merge-fields.test.ts`: every path group against product, set and line data;
an unknown token; a spec key the product does not carry; price formatting; editor mode drawing the
token with no data and the value with data; the catalogue built from registry keys and grouped;
and the parity render, one text layer through `layerText` and through `TagSheetRenderer`'s DOM.
`ColorPicker.test.tsx`: picking a colour calls `onChange` with the hex, and typing a hex moves the
picker's value. `InsertFieldDialog.test.tsx`: a click inserts at the cursor, and the preview line
shows the resolved value against a stubbed binding. pytest: `product_tag_data` carries `specs`
built from the registry, the print payload's resolved line carries them too, and both are asserted
ON THE WIRE where a route answers, because `response_model` drops what it does not declare.

---

## 14. Round 9, 30 Aug: it deploys with nobody seeing it, and admins switch it on

**Status:** BUILT 2026-08-30. The captain's call before production: on the live database every
contact already holds one of the four legacy portal forms, and Price Tag Request must reach NOBODY
on the day it deploys. Turning it on later has to be an admin action in the CRM, not a migration
somebody writes and a DBA runs.

### What was wrong

| # | Symptom | Cause found in the code |
|---|---------|--------------------------|
| 1 | Deploying grants the form to a whole class of contacts nobody reviewed | `ptag_0001`'s first UPDATE writes `["price_tag_request", "stock_inquiry"]` onto every `contact_access_types` row whose code contains "dealer". On production that is every dealer at once, decided by a `LIKE` pattern in a migration rather than by a person. |
| 2 | There is no way to grant it, or take it back, without SQL | `portal_form_types` has no admin surface at all. The Contact Access Types screen edits code, name, description, keywords, sort order and active; `ContactAccessTypeBase` / `ContactAccessTypeUpdate` carry `keywords` and not `portal_form_types`, so even a hand-written PUT would be dropped by the schema before it reached the row. |
| 3 | A grant already written by an earlier run of the migration stays written | The branch has been applied to development databases already, so editing `ptag_0001` alone leaves those rows granted. Nothing walks them back. |

### Decisions

| ID | Decision |
|----|----------|
| D61a | **The migration grants nothing.** `ptag_0001`'s first UPDATE writes `["stock_inquiry"]` onto dealer-type rows, so the column arrives with the portal behaving exactly as it did before the branch. The second UPDATE is untouched: it seeds the four legacy kinds onto every other type that still had `[]`, which is what preserves today's behaviour for everyone else. `ptag_0003_strip_price_tag_grant` then removes `"price_tag_request"` from every `contact_access_types.portal_form_types` array with the jsonb `-` operator, so a database that already ran the old `ptag_0001` lands in the same state as a fresh one. It is idempotent by construction: after it runs, its own WHERE matches nothing. Its downgrade is a deliberate no-op, because a grant is an admin decision and a downgrade must not invent one. |
| D61b | **Granting is an admin action on the access type.** The Contact Access Types screen gains a "Portal forms" field: a `SearchableMultiSelect` over the five known kinds - the four legacy ones plus Price Tag Request - labelled exactly as the portal labels them, editable in the dialog that already edits the rest of the row and shown in the list as chips. No new page and no new screen: an access type is already the unit the portal resolves visibility by, so the switch belongs on the row it belongs to. `portal_form_types` joins the read, create and update schemas and is validated against the known kinds, an unknown kind answering 422. The label map moves to `lib/portal-form-kinds.ts` and `portal-client.ts` re-exports it, so the admin screen and the portal cannot label the same kind differently. |
| D61c | **Fail-closed is unchanged and that is the point.** `resolve_visible_form_types` still unions `portal_form_types` across the contact's access types and then applies per-contact overrides; the landing (D45) and every portal price-tag route already read it. With no access type carrying the kind, the union is empty for everybody, and the deploy is silent without a single line of gating code being added. |
| D61d | **Named, not built: gating the four legacy kinds on the landing.** The landing lists the legacy kinds unconditionally today and only the gated kinds (D45) are filtered by `visible_form_types`. The 0001 second UPDATE seeded the legacy four onto every non-dealer type precisely so that switch is safe to throw later. Trigger: the captain asks for one of the legacy forms to be hidden from a class of contacts. Until then, adding the filter would change nothing except the number of ways the landing can be wrong. |

### What is deliberately NOT built

- No per-contact grant UI. `contact_portal_form_overrides` exists and the resolver honours it, but
  nobody has asked to grant one person a form their access type does not carry. The access type is
  the unit the request was made in.
- No data migration that re-grants. D61a says a grant is an admin decision; a downgrade or a later
  migration that guesses one is the failure mode being removed, not a convenience.
- No new permission. Editing an access type is already gated where the rest of that row is edited.
- No landing-side gate for the legacy four. D61d names the trigger.

### Tests

pytest: the access type route accepts `portal_form_types` and answers with it ON THE WIRE, because
`response_model` drops what it does not declare; an unknown kind is refused 422; the strip SQL run
twice against the same row leaves the same array, and leaves the other kinds alone;
`resolve_visible_form_types` for a contact whose only access type carries no `price_tag_request`
answers without it. vitest: the edit dialog opens with the row's kinds selected, the multi-select
offers all five with the portal's labels, and Save submits the chosen codes; the list column draws
one chip per kind and a dash for none.


## 15. Review findings, 30 Aug

**Status:** FIXED 2026-08-30. `/code-review` on the branch raised ten findings above the
severity cap and a tail of smaller ones; every one was reproduced with a failing test before it
was fixed. One line each, in the order they were raised.

| # | What was wrong | The fix |
|---|----------------|---------|
| 1 | `generate_doc_number` counted the surviving rows of one company while `doc_number` is globally unique and a draft hard-deletes, so the create after any delete died on `price_tag_requests_doc_number_key` and two companies in one month collided | The sequence is MAX over the month's suffix, read with the company scope off because the numbering space is the table, plus a SAVEPOINT retry so a lost insert race takes the next number instead of a 500 |
| 2 | The tag sheet print payload resolved entirely inside `company_scope(db, None)`, so another company's products, prices, photos, assets and fonts were in reach of a token issued for this one | The widening stops at the page lookup and everything after is read inside `frozenset({page.company_id})`, which is what the sibling catalogue route already did |
| 3 | `GET /lookups/debtors-for-agent` was the one portal route with no `_assert_visible`, so a revoked contact could still enumerate their agent's whole debtor book | It calls `_assert_visible` like the other nine |
| 4 | A portal draft carries status `new`, so it sat in marketing's queue and could be claimed; the salesperson's later Submit then reset it to `new`, wiping the claim and firing the SLA twice | The CRM listing asks for `include_drafts=False`, the portal list keeps its drafts, and Claim refuses a draft outright through `validate_claimable` |
| 5 | Claiming wrote `created_by`, which nothing reads back, and the list and response schemas declared none of `line_count`, `contact_name`, `assigned_to_id`, `assigned_to_name`, `promotion_name`, so `response_model` dropped them and both screens drew blanks | `price_tag_requests.assigned_to_id` (migration `ptag_0004`, FK to `users`, backfilled from the overloaded `created_by`), the claim writes it, and the five fields are resolved for a whole page in two set-based queries |
| 6 | A set offer counted a member the pricing engine could not price as RM 0, printing a set offer far below the sum of its parts | An unpriceable contributing member abandons the offer and the tag prints the set's list price |
| 7 | `pinnedFromDoc` read every placed tag as a manual pin, so one save and reopen froze the sheet: a preset switch re-imposed nothing and a quantity bump stacked the new copy on copy 0 | A dragged copy carries `pinned: true` and only that is read back. **A document saved before the flag opens unpinned and auto-arrange re-imposes it**, which leaves the sheet correct rather than frozen |
| 8 | `Decimal(part)` on a measurement that came from JSONB is a float, so 407.3 printed as 28 digits on a physical tag | `Decimal(str(part))`, and the catalogue tile that delegates to the same formatter is fixed with it |
| 9 | The `price_field` kind drew a hardcoded "RM 1,550" on the canvas while print resolved the real price, and its `format` prop was read by nothing | **Deleted end to end.** The read-only probe first: 0 of 9 stored `tag_template` docs and 0 of 6 `tag_sheet` `page_version` docs carry `"kind": "price_field"`, so nothing on this database loses a layer. `price_badge` stays and is how a tag prints a price |
| 10 | `SUPPORTED_TYPES` answered two questions, so the generic listing returned `200 []` for `price_tag_request`, a dead revision-config row appeared, and the router include order was load-bearing | `GRANTABLE_PORTAL_FORM_TYPES` for what an admin may grant; `SUPPORTED_TYPES` back to the four generic kinds. `test_portal_revision_config_routes` is green again as a result |
| 11 | The landing awaited its five lists in one `Promise.all`, so one kind's 403 or 500 blanked the whole page | `allSettled` per leg; a failed leg is that kind empty, and an expired token is still rethrown |
| 12 | The sales agent contact picker read its label off the agent row, so choosing somebody else made the field say "Not linked" with a real person selected | The picked option is kept through `onOptionChange` and named until the row catches up |
| 13 | The CRM list fetched the whole table and paged it in the browser, hand-rolling its query string | The route takes page/limit/sort/dir/query/status and answers the `data` + `pagination` envelope with a real count; the service builds its string with `buildDataGridParams`; both new grids gained `columnResizeMode: 'onChange'` |
| 14 | The FE branched on a `draft` STATUS the backend never writes | Removed; draft-ness is `portal_draft_at` and nothing else |
| 15 | The portal's PO zone said "Drop PO files here" and had no drag handlers, so a dropped file opened in the browser tab | The shared `FileDropzone` |
| 16 | `data-dk-print-ready` flipped when the payload arrived, so the PDF could be taken while the photos were still loading | Every picture is counted and waited for, settling on `error` too |
| 17 | `sales_agents.contact_id` has no unique constraint and the debtor lookup took `.first()` off an unordered query | Ordered by agent code then id, and a second link is logged rather than hidden |

### Named, not built

- **`Customer.sales_agent_id` still has no writer.** The debtor lookup reads it and the column is
  populated by an import that has not landed; nothing in this feature writes it, and inventing a
  writer here would be guessing at a mapping the import owns. Trigger: the customer-to-agent import
  ships, or the captain asks for the link to be editable in the CRM.
- **`resolve_request_line_data` costs about six queries per line.** Every line resolves its product,
  its spec row, its images and its prices separately. It is correct and it is fast enough for the
  handful of lines a request carries; the trigger for batching it is a request with tens of lines,
  or the designer's panel becoming slow enough to notice.
- **The four legacy portal-forms toggles are still decorative.** That is D61d, unchanged.
