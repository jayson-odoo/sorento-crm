# Price Tag Request - Acceptance Criteria

**Slug:** `price-tag-request`
**Domain:** dealer-kit (sub-feature)
**Depends on:** `product-sets` (feat/product-sets branch must merge first)

---

## Journey

A Sorento salesperson (a contact without a CRM user account) visits a dealer showroom. The
dealer wants price tags for products on display. The salesperson opens the portal on their
phone, picks the products (or bathroom furniture sets), chooses which ones get promotional
pricing, attaches the customer's purchase order, and submits to marketing. Marketing opens
the request in the CRM, designs the tags in a canvas editor using pre-built templates, and
marks the proof ready. The salesperson reviews the proof on their portal, approves (or
requests changes), and both parties can print the final PDF. The customer PO is cross-checked
against the selling prices to catch discrepancies before print.

---

## Decisions

| ID | Decision |
|----|----------|
| D1 | **Entity type = hand-coded `price_tag_request`** registered in `FORM_SLA_TYPES`, not a workflow_forms definition. Workflow_forms lacks product picker, set guard, promotion binding. |
| D2 | **Submitter = portal contact** (Sorento staff serving dealers), authenticated via existing OTP portal. NOT a CRM user. |
| D3 | **Dealer dropdown = customer list** scoped to the salesperson. Primary: `customers.sales_agent_id` links customers to their assigned agent. Dropdown = customers assigned to the contact's linked agent. Fallback enrichment from orders in last 24 months + prior price-tag requests by this contact. |
| D4 | **SalesAgent.contact_id** FK added (links portal contact to their agent). **customers.sales_agent_id** FK added (links dealer/customer to their assigned salesperson). |
| D5 | **Product sets from `feat/product-sets`** branch. Members carry quantity + contributes_to_price tick, no roles. |
| D6 | **Set guard = hard block.** A Bathroom-Furniture-class product (cabinet) cannot be submitted ala carte; must come as a Product Set line. Guard names the sets containing that cabinet. Zero sets = block + in-app notification to marketing to define the set. |
| D7 | **Combo lines.** A line = product OR set, + optional `alternatives[]` (tap choices, the OR groups on the PDF), + `included_accessories` text. Not a Product Set. Marketing decides layout. |
| D8 | **Price mode = per-line toggle.** Request carries optional `promotion_id`. Each line has `show_promo_price` (default true when promotion present). Promo = LP struck + SP NETT. No promo = LP only. |
| D9 | **Marketing picks the promotion** (page-level, existing mechanism). Salesperson uploads PO. Marketing may override SP per line with a logged reason. Salesperson cannot override prices. |
| D10 | **Lifecycle: `new -> designing -> proof_ready -> approved -> ready`**, plus `changes_requested` (back to designing with note), `rejected`, `void`. |
| D11 | **Form SLA = single `marketing` stage**, configurable via `form_sla_configs`. Notifications via form_sla_config (not hardcoded). Deadline = salesperson's "needed by" date, shown but not the SLA clock. |
| D12 | **Proof step kept.** Salesperson reviews on portal, approves or requests changes (single loop). PO cross-check result shown at proof. |
| D13 | **Revisions enabled** for this type via `PortalRevisionConfig`. Restart at `marketing` stage. |
| D14 | **Portal form type visibility** via `contact_access_types.portal_form_types` JSONB (access-type-level defaults) + `contact_portal_form_overrides` table (per-contact). Fail-closed: no matching type = hidden. Migration seeds existing 4 types onto current access type codes. |
| D15 | **Under dealer_kit module**, not a new module. Permissions: `dealer_kit.price_tag_requests.{view,create,process}`, `dealer_kit.tag_templates.{view,manage}`. |
| D16 | **Page.kind = `'catalogue' \| 'tag_sheet'`**. A `tag_sheet` doc = `sheets[] -> tags[] -> layers[]` with absolute positioning (mm units). Same `PageVersion`/labels/assets/pricing/PDF pipeline. |
| D17 | **Tag templates per family** (sink combo, ala carte, WC, shower, mirror, furniture set). Named slots: `product_image`, `code`, `name`, `dimensions`, `spec_lines`, `list_price`, `sell_price`, `badges[]`, `alternatives[]`, `accessories[]`, `set_members[]`. |
| D18 | **Slot data resolved at render** from product + `resolve_prices` (prices never stored - ADR 0008). Text edits stored as overrides in doc, with a "relink" action. Spec lines fall back to product description when flyer-spec data absent. |
| D19 | **Canvas v1 = items 1-12.** Drag/resize/rotate + snap + alignment guides, z-order + layers panel, multi-select/group/duplicate/copy-paste/nudge, text (font/size/weight/colour/align/line-height/letter-spacing), shapes (rect/rounded/ellipse/line, fill/stroke), image crop+fit+mask, badge/icon library from dealer-kit assets, auto-formatted price fields (LP struck, SP nett), colour palette + brand swatches, undo/redo, imposition presets (A4 3-up, 2x2, custom mm) + bleed/crop marks, rulers + mm coordinates in inspector. |
| D20 | **Canvas v2** (future): text on path / warp / gradients / blend modes, pen tool / vector paths, import SVG/AI. |
| D21 | **Locked layers** from day one. `locked: true` per layer; marketing can toggle. Dealer self-design rollout enforces locked = immovable. |
| D22 | **PO cross-check Phase 1 = manual** (PO attached, viewer side-by-side). Phase 2 = AI extract product codes + unit prices, per-line discrepancy table, mismatch blocks `proof_ready` until each mismatch resolved (fix SP or accept with reason). |
| D23 | **One PDF per request** via `ExportRequest` on `catalogue_render` queue. Single-sheet export with `sheet_ids` filter. Downloadable in CRM (My Downloads) + portal request page. Re-export re-resolves prices; expired promotion = export refused with reason. |
| D24 | **Doc number prefix `PT-YYYYMM-NNNN`.** |
| D25 | **Only contacts with a SalesAgent link** see price_tag_request on the portal (enforced by portal_form_types + the SalesAgent.contact_id existence check). |

---

## Acceptance Criteria

### A. Portal form type visibility

- **AC-A.1** `[BE][M]` `contact_access_types` gains `portal_form_types` JSONB column (default `[]`). Migration seeds: dealer-type codes get `["price_tag_request", "stock_inquiry"]`; project-type codes get `["stock_inquiry", "purchase_request", "sponsorship_form", "complaint"]`. Admin can edit via existing access-type CRUD.
- **AC-A.2** `[BE][M]` New table `contact_portal_form_overrides(contact_id FK, form_type VARCHAR, is_enabled BOOLEAN, UNIQUE(contact_id, form_type))`. Per-contact toggle that wins over access-type defaults. Admin edits on contact detail page.
- **AC-A.3** `[BE][T]` Portal `/submissions` list and create endpoints filter by resolved visibility: union of access-type `portal_form_types` for the contact's assigned codes, then per-contact overrides applied. A type not visible = 403 on create, absent from list.
- **AC-A.4** `[FE]` Portal form picker hides invisible types. No empty state for hidden types.

### B. SalesAgent link + dealer dropdown

- **AC-B.1** `[BE][M]` `sales_agents.contact_id` nullable FK to `respond_contacts.id` (SET NULL). Editable on Sales Agent detail form.
- **AC-B.1a** `[BE][M]` `customers.sales_agent_id` nullable FK to `sales_agents.id` (SET NULL). Editable on Customer detail form. Links dealer/customer to their assigned salesperson.
- **AC-B.2** `[BE][T]` Portal `/lookups/debtors` for price_tag_request: returns customers where `sales_agent_id` matches the contact's linked agent, PLUS distinct debtors from orders for that agent within last 24 months, PLUS debtors from the contact's earlier price-tag requests. Searchable. Empty agent = empty list.
- **AC-B.3** `[FE]` Portal request form: `SearchableSelect` debtor dropdown. Required field.

### C. Request entity + lines

- **AC-C.1** `[BE][M]` `price_tag_requests` table: `id`, `contact_id` FK, `company_id`, `debtor_code`, `debtor_name`, `promotion_id` FK NULL (SET NULL), `needed_by_date` DATE NOT NULL, `notes` TEXT NULL, `status` VARCHAR default `'new'`, `doc_number` (generated `PT-YYYYMM-NNNN`), `portal_draft_at`, standard audit columns. CompanyScopedMixin.
- **AC-C.2** `[BE][M]` `price_tag_request_lines` table: `id`, `request_id` FK CASCADE, `line_type` (`'product'` | `'product_set'`), `product_id` FK NULL, `product_set_id` FK NULL, `show_promo_price` BOOLEAN default true, `quantity` INTEGER default 1 (number of tags), `alternatives` JSONB default `[]` (list of product_ids), `included_accessories` TEXT NULL, `sort_order` INTEGER, `marketing_price_override` NUMERIC NULL, `marketing_override_reason` TEXT NULL. CHECK: exactly one of product_id/product_set_id is NOT NULL.
- **AC-C.3** `[BE][T]` Register `price_tag_request` in `FORM_SLA_TYPES`. Stage chain seeded in `form_sla_configs`: single `marketing` stage.
- **AC-C.4** `[BE][T]` Doc number generation: `PT-{YYYYMM}-{sequence}`, zero-padded 4-digit sequence per month, company-scoped.
- **AC-C.5** `[BE][T]` Status transitions: `new -> designing` (on claim), `designing -> proof_ready`, `proof_ready -> approved`, `proof_ready -> changes_requested -> designing`, `approved -> ready` (on PDF export), `* -> void`. Invalid transitions = 409.
- **AC-C.6** `[FE]` CRM: `Dealer Kit -> Price Tag Requests` DataGrid listing. Claim assigns to the claiming user. Detail page shows all request data + lines + PO attachments + lifecycle log.

### D. Set guard

- **AC-D.1** `[BE][T]` On submit (not on draft save): for each line with `line_type='product'`, if the product's derived class = `'Bathroom Furniture'` AND the product belongs to at least one product_set, reject with 422 naming the sets. If the product belongs to zero sets, reject with a different message ("no set defined") AND fire an in-app notification to users with `dealer_kit.tag_templates.manage` permission.
- **AC-D.2** `[BE][T]` Products with class != `'Bathroom Furniture'` are always allowed ala carte. Taps, mirrors, basins submitted alone = fine.
- **AC-D.3** `[FE]` Portal form: inline validation on blur shows the guard message before submit.

### E. Portal request form

- **AC-E.1** `[FE]` New portal page `price_tag_request/new` and `price_tag_request/[id]`. Line builder: add product (SearchableSelect from `/lookups/products`), add set (SearchableSelect from `/lookups/sets`), per-line: alternatives picker (multi-select products), accessories text, quantity (number input, min 1), show_promo_price toggle (visible only when request has promotion).
- **AC-E.2** `[FE]` Promotion picker: SearchableSelect from portal lookups, shows only live promotions. Selecting populates `show_promo_price` default on all lines.
- **AC-E.3** `[FE]` PO upload: `AttachmentDropzone` on the request, linked as `price_tag_request` attachment type. Multiple files allowed.
- **AC-E.4** `[FE]` Deadline: date picker, required, min = today + 1 business day.
- **AC-E.5** `[FE]` Portal request list: shows status badge, doc number, dealer name, deadline, line count.
- **AC-E.6** `[FE]` Proof review: when status = `proof_ready`, salesperson sees the rendered proof (same renderer as CRM), PO cross-check results (Phase 2), and `Approve` / `Request Changes` (with note) buttons.

### F. Tag templates

- **AC-F.1** `[BE][M]` `tag_templates` table in `dealer_kit` schema: `id`, `name`, `family` VARCHAR (`sink_combo`, `ala_carte`, `wc`, `shower`, `mirror`, `mirror_cabinet`, `furniture_set`), `doc` JSONB (layer definitions with named slots), `print_size` JSONB (`{width_mm, height_mm}`), `company_id`, timestamps. CompanyScopedMixin.
- **AC-F.2** `[BE]` CRUD API under `/api/v1/dealer-kit/tag-templates`. Permission: `dealer_kit.tag_templates.{view,manage}`.
- **AC-F.3** `[FE]` CRM: `Dealer Kit -> Tag Templates` page. Template editor = the canvas (same as tag sheet editor, operating on a single-tag doc).

### G. Tag sheet designer

- **AC-G.1** `[BE][M]` `Page.kind` column: `'catalogue'` (default, existing) or `'tag_sheet'`. All existing pages default to `'catalogue'`. `tag_sheet` pages carry a `request_id` FK to `price_tag_requests` (nullable, SET NULL).
- **AC-G.2** `[BE]` Tag sheet document schema stored in `page_version.doc`:
  ```jsonc
  {
    "kind": "tag_sheet",
    "imposition": { "preset": "a4_3up" | "a4_2x2" | "custom", "page_width_mm": 210, "page_height_mm": 297, "bleed_mm": 3, "gap_mm": 2 },
    "sheets": [
      { "id": "s1", "tags": [
        { "id": "t1", "template_id": "...", "request_line_id": "...",
          "layers": [
            { "id": "l1", "type": "image" | "text" | "shape" | "product_slot" | "price_field" | "badge" | "group",
              "x_mm": 10, "y_mm": 20, "width_mm": 50, "height_mm": 30,
              "rotation_deg": 0, "z_index": 1, "locked": false, "visible": true,
              "props": { /* type-specific */ },
              "slot_binding": "product_image" | "code" | "name" | ... | null,
              "text_override": null }
          ] }
      ] }
    ]
  }
  ```
- **AC-G.3** `[FE]` Tag sheet editor: left panel shows request lines to drag onto sheets. Each drop creates a tag from the matching family template. Canvas displays the sheet at actual mm scale with rulers.
- **AC-G.4** `[FE]` Canvas capabilities (v1): drag/resize/rotate with snap + alignment guides, z-order + layers panel, multi-select + group + duplicate + copy-paste + nudge, text styling (font family from brand assets, size, weight, colour, align, line-height, letter-spacing), shapes (rect/rounded/ellipse/line, fill/stroke), image crop + fit + mask to shape, badge/icon library from dealer-kit assets, auto-formatted price fields (LP / LP struck + SP nett based on line's `show_promo_price`), colour palette + brand swatches, undo/redo (Ctrl+Z/Y), imposition presets + bleed/crop marks, rulers + mm coordinates typed in inspector panel.
- **AC-G.5** Prices resolve via `resolve_prices` at render time (never stored in doc - ADR 0008). Product data (name, code, dimensions, specs) resolved from product master. Slot text overrides break the binding; "Relink" action re-resolves from product data.
- **AC-G.6** `[BE][T]` Locked layers: `locked: true` prevents move/resize/delete/edit in the editor. Marketing can toggle lock via inspector. Lock state stored per layer in the doc.

### H. PDF export

- **AC-H.1** `[BE]` `POST /api/v1/dealer-kit/pages/{id}/exports` works for `tag_sheet` pages. Accepts optional `sheet_ids[]` filter for single-sheet export. Enqueues on `catalogue_render` queue.
- **AC-H.2** `[BE][T]` Export re-resolves all prices and product data at render time. If the request's promotion has expired, return 409 with reason; do not generate a stale-price PDF.
- **AC-H.3** `[BE][T]` Status transitions to `ready` on successful export (first export after `approved`). Subsequent exports are reprints, no status change.
- **AC-H.4** `[FE]` Download available in CRM (My Downloads) and portal request detail page.
- **AC-H.5** `[FE]` "Print Sheet N" button on the designer exports a single sheet.

### I. PO cross-check

- **AC-I.1** (Phase 1) `[FE]` Side-by-side view: PO attachment viewer + request lines with resolved prices. Manual comparison by marketing.
- **AC-I.2** (Phase 2) `[BE]` AI extraction from PO PDF: product codes, quantities, unit prices. Stored on the request as `po_extraction_result` JSONB. Runs async on PO upload via existing AI-extract pattern.
- **AC-I.3** (Phase 2) `[BE][T]` Per-line discrepancy table: `{line_id, po_code, po_price, system_price, status: 'match' | 'mismatch' | 'missing', resolution: null | 'accepted' | 'fixed', resolution_reason}`. Mismatches block transition to `proof_ready` until each is `accepted` or `fixed`.
- **AC-I.4** (Phase 2) `[FE]` Discrepancy table shown to marketing on request detail and to salesperson on proof review.

### J. Notifications

- **AC-J.1** `[BE]` All notifications configurable via `form_sla_configs`, not hardcoded. Seeded defaults: submit -> marketing team, proof_ready -> salesperson (WhatsApp + portal link), changes_requested -> marketing, approved -> both, deadline T-1 -> marketing.
- **AC-J.2** `[BE][T]` Deadline nudge: scheduler checks `needed_by_date - 1 business day` for requests still in `designing`. Uses existing form-SLA notify, no new cron.

### K. Permissions + module

- **AC-K.1** `[BE][M]` Permissions seeded: `dealer_kit.price_tag_requests.view`, `dealer_kit.price_tag_requests.create` (portal only, implicit for linked contacts), `dealer_kit.price_tag_requests.process` (CRM marketing), `dealer_kit.tag_templates.view`, `dealer_kit.tag_templates.manage`.
- **AC-K.2** `[BE]` Routes guarded by `require_module_enabled_with_api_key("dealer_kit")`.
