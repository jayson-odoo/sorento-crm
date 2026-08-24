# PLAN - Price Tag Request: end-to-end flow from salesperson to print

> The design that fulfils `price-tag-request-acceptance-criteria.md`. That file is the
> contract; where this plan and the UAC disagree, the UAC wins.
> Governs: `PRINCIPLES.md` + `documentation/reference/ADR-PRODUCT-STANDARDS.md`.

**Slug:** `price-tag-request` | **Domain:** dealer-kit (sub-feature)
**Status:** DRAFT - grilled (30 decisions, 4 rounds), awaiting captain sign-off.
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
