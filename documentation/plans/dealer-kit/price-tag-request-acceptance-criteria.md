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

### L. S3b - canvas enriched with the catalogue builder's data layer

- **AC-L.1** `[FE][T]` `price_badge` layer renders `list_only` as `RM 1,599` and `promo` as struck `LP: RM 1,599` above `SP RM 599 NETT`; colours/size/radius editable, composition fixed. Print renderer output matches the editor.
- **AC-L.2** `[BE][T]` `GET /dealer-kit/products/search?q=` returns id, code, name for a staff user; `GET /dealer-kit/products/{id}/tag-data` returns code, name, dimensions, spec lines (flyer-spec first, description fallback), gated image attachments, and `list_price` / `offer_price` from `resolve_prices()`.
- **AC-L.3** `[FE]` "Add product" opens a product search select and drops a bound group (image, code, name, dimensions, spec lines, price badge) at the canvas centre. Editing a bound text unlinks it; "Relink" restores the resolved value. The group's binding can be switched to another product and every still-linked layer updates.
- **AC-L.4** `[BE][FE][T]` "Add set" drops a set-members list bound to a Product Set: one line per member `- CODE (NAME) LxWxH`.
- **AC-L.5** `[FE]` "Add alternatives row" places N chosen products with `OR` connectors and a leading `+`; "Add accessories strip" places N products/assets as small image + caption. Resulting layers are ordinary layers.
- **AC-L.6** `[FE]` Badge and image layers pick from `dealer_kit.asset` (tags badge/icon/diagram/logo) with upload-in-place; image layers can also pick any of the bound product's attachments (primary first).
- **AC-L.7** `[BE][FE][T]` A woff2/ttf uploaded as `Asset.kind='font'` appears in the inspector font list and renders in both editor and print page via `@font-face`.
- **AC-L.8** `[BE][T]` `resolve_prices_for_lines` and `/tag-templates/resolve-preview` return prices from `resolve_prices()`; the Phase 1 mock is gone.
- **AC-L.9** `[BE][T]` `scripts/seed_tag_templates.py` inserts eight templates (sink combo, sink ala carte, art basin, mirror + mirror cabinet, shower set, WC, urinal, bathroom furniture set) and their badge assets; rerunning changes nothing.
- **AC-L.10** `[Browser]` Each seeded template opens in the editor with live product data and is screenshotted next to its page of `Sorento Pricetag Template.pdf`; the reviewer can name no element on the PDF page that the template cannot express.

### M. S3c - the tag canvas behaves like a drawing tool

- **AC-M.1** `[FE][T]` The wheel over the canvas zooms about the cursor: the mm point under the pointer stays under the pointer, the `%` readout updates, and the page behind does not scroll. `Cmd/Ctrl+0` fits the artboard to the viewport, `Cmd/Ctrl+1` returns to 100%.
- **AC-M.2** `[FE]` `V` and `H` toggle the Select and Hand tools and holding Space is Hand for as long as it is held. A hand drag pans the view. A select drag on empty space draws a marquee and selects every top-level layer the band touches; Shift adds to the selection instead of replacing it.
- **AC-M.3** `[FE]` A click on a group selects the group. A double-click selects the child under the pointer, and from then on the group box no longer intercepts pointer events. Escape climbs one level and deselects at the top. Clicking a child in the Layers panel puts the canvas in the same state.
- **AC-M.4** `[FE][T]` Dragging a group moves every descendant, both live and on drop. Resizing or rotating a group applies the same change to its descendants. Moving a child refits the boxes of every ancestor group. One undo reverts the whole move.
- **AC-M.5** `[FE]` A multi-selection drags as one object and is served by a single Transformer.
- **AC-M.6** `[FE]` Right-click anywhere on the canvas opens our context menu and never the browser's. Every listed item works, and each item that changes the document is undoable.
- **AC-M.7** `[FE][T]` Copy, cut, duplicate and delete of a group carry its descendants; pasted groups have fresh ids and a `children` array pointing at the pasted copies.
- **AC-M.8** `[FE]` A canvas drag persists: the inspector X/Y change as the layer moves, Save writes the moved position, and re-opening the template shows it.
- **AC-M.9** `[FE]` Previewing with a product resolves every bound layer against it, names it in a chip on the toolbar, can be cleared, and changes nothing that Save writes: re-opening the template shows the group still unbound.
- **AC-M.10** `[FE][T]` Nothing already shipping regresses: `TagSheetDesigner` still renders placed tags, `vitest lib/dealer-kit` is green, and `tsc --noEmit` is clean.
- **AC-M.11** `[FE][BE][T]` A product-photo slot draws the bound product's photo without anything being written into the document: previewing a template whose hero layer has `slot_binding: 'product_image'` and `source: null` shows that product's primary photo, a pinned attachment still wins while it belongs to the bound product, a pinned attachment that does not belong to it falls back to the primary, and an image layer with no slot binding and no source stays empty. A `product_slot` layer resolves the same way for `product_image` and through `resolveSlotText` for its other field keys, keeping the dashed placeholder only when there is no data. The print page resolves both by the same helper. Clearing the preview goes back to "No image", and Save leaves `source` null.
- **AC-M.12** `[FE][T]` The Layers panel reorders by drag: a row dropped between two rows takes their place and their parent, a row dropped onto a group row becomes that group's last child, a group drags with its whole subtree, and nothing can be dropped into its own subtree. After any drop the panel order is the z order, a group's descendants are a contiguous block below it, the ancestor boxes are refitted, and one undo reverts the whole move. Click to select, the eye and the lock still work, and a collapsed group stays collapsed.
- **AC-M.13** `[FE]` Holding the middle mouse button and dragging pans the view whatever tool is active, with the `grabbing` cursor while held: no marquee is drawn, no layer moves, the selection does not change and the browser's autoscroll cursor never appears.
- **AC-M.14** `[FE][T]` The portal landing's type dropdown offers Price Tag Request, with a count badge, a star and the same card list, search and status filter as the four legacy kinds, to a contact whose `visible_form_types` include it and to nobody else. A row opens the existing detail page and New opens the existing form. The separate "Price Tag Requests" link button is gone. A `?type=price_tag_request` deep link, or a starred default of it, falls back to Stock Inquiry for a contact without the grant instead of showing an option the server would refuse. A request saved and never submitted reads as Draft, not New.
- **AC-M.15** `[FE][BE][T]` When the debtor lookup answers with no options the portal form shows, in place of the select, that the account is not linked to a sales agent and who to ask; a lookup that FAILS keeps the existing error toast instead. Submit stays blocked in both cases. The Sales Agents master screen's edit modal carries a "Linked portal contact" field: a server-searched, clearable select over contacts showing name and a masked phone and never an id, writing `sales_agents.contact_id` through the existing annotation route. The response declares `contact_id` and a resolved `contact_name`, so re-opening the modal on a linked agent shows the person rather than a blank.
- **AC-M.16** `[FE][BE][T]` The request's lines are one table with one Add line button. The Item column is a single server-searched dropdown listing sets and products together, each labelled with which it is; picking one fills the row's type and id, and the submitted payload still carries `line_type` of `product` or `product_set` with the matching `product_id` / `product_set_id` and nothing else new. Qty is a number with a floor of 1, Alternatives is disabled on a set row and says why, Accessories stays free text, a row can be removed without a confirm and reordered. The Bathroom Furniture set guard still refuses an ala carte submit with its message. The table is usable at 375px and 1280px.
- **AC-M.17** `[FE][BE][T]` Save Draft checks nothing but that there is something to save. The needed-by field starts empty rather than pre-filled with a date nobody chose. A form with one line and no debtor, or a debtor and nothing else, saves; the request stores a null debtor and a null needed-by date without complaint, lists as Draft, and reopens with those fields empty and its lines present, ready to be finished. Saving an already-saved draft updates it rather than creating a second one, and a draft can be deleted from its own form behind a confirmation. Every place a request is read renders a dash for a missing debtor or date instead of failing: the portal list and detail, the CRM list and detail, and the landing card.
- **AC-M.18** `[FE][BE][T]` Submit says what is missing. The button is enabled whenever the form is not busy; the click reports each problem where it is - under Debtor, under Needed by, on the row that has no item - with one summary line above the actions and the first problem scrolled into view, and it posts nothing. The server refuses an incomplete submit too, naming every missing field, and refuses an ala carte Bathroom Furniture line naming the line; both land on the same inline surfaces rather than in an unreadable toast. A complete form still submits in one go.
- **AC-M.19** `[FE][T]` The CRM request detail page wears the same chrome as the other form detail pages. The breadcrumb is the way back and there is no ad-hoc "Back to list" button. The header carries the document number as the page heading, a `Created: ... - <status pill>` subline, and the debtor, salesperson, promotion, needed-by and assignee as read-only metadata. Its right side carries exactly ONE primary CTA, a gear menu holding every other action legal at that status, and working prev/next record navigation with a position counter. Lines, PO attachments and the proof are cards below, each with its own empty state. Void still asks for confirmation in an `AlertDialog`. Usable at 375px and 1280px.
- **AC-M.20** `[FE][T]` The primary CTA is the next lifecycle action and nothing else: `new` offers Claim and does not offer Design; `designing` and `changes_requested` offer Design tags; `proof_ready` offers View design; `approved` and `ready` offer Export PDF; `rejected` and `void` offer none. Whatever is not primary but is still legal appears in the gear menu.
- **AC-M.21** `[FE][T]` Designing a request opens the template editor, not a second layout: the same `CanvasToolbar`, Layers panel and Inspector, with the request's lines as a rail above the Layers panel and the selected line's tag on the artboard. A line with no tag yet is cloned from its family's default template and drawn against the LINE, so its real code, photo and price show; edits are saved into that line's tag and re-opening the template shows the template unchanged. "Use template..." re-clones from any template, asking for confirmation first when the tag already carries edits. The Arrange half shows the sheet canvas with every line's tag laid out in line order, quantity times, on the request's preset, with a manual drag kept across a re-arrange; the sheet count is visible. Save writes one `TagSheetDoc` through the existing route and Mark proof ready still transitions the request, so the portal proof and the print page render the designed layers.
- **AC-M.22** `[FE][T]` A template with several product blocks previews each block against its own product. "Preview with..." on a multi-block template opens a dialog listing every previewable block once - the main block and the three alternatives on the sink combo, and not the accessories strip, which is not about a product - each labelled so the three unbound alternatives can be told apart and never by an id, each with a clearable server-searched select in its own mode. Choosing a product for two blocks and applying draws each of those blocks against its own product, in the code, the name, the photo and the price alike, while the blocks nobody chose for keep their placeholders; the chip reads how many of how many blocks are previewing, reopens the dialog when clicked and clears every block on its X. A block, or any layer inside it, offers the same picker for itself alone in the Inspector and shows what it is previewing there with a clear. A single-block template keeps the D41 behaviour exactly: one picker, one `CODE - name` chip. Nothing previewed reaches the document: Save while previewing and re-open, and every group is still unbound with its placeholders back.
- **AC-M.23** `[FE][T]` The colour control is a picker, not a palette. Opening it shows a full-spectrum control as its primary element, sized to be usable rather than the browser's default swatch, with the twelve brand swatches under it and the hex box beside the trigger. Picking a colour on the spectrum changes the layer at once and rewrites the hex box; typing a valid hex moves the picker to it; an invalid hex changes nothing until it becomes valid. `transparent` still draws its chequerboard and is still reachable from the swatches. Every colour field in the Inspector behaves the same way, and no colour library is added.
- **AC-M.24** `[FE][BE][T]` A text layer's content may carry `{{path}}` merge fields and they resolve in the canvas and in the PDF from ONE function. The tokens are the product's code, name, dimensions, spec lines, list price, sell price and accessories; `spec.<key>` for every key in the spec registry, rendered with its unit where the registry has one; the set's code, name and members; and the line's quantity. Prices carry the same `RM #,##0` the badge prints. An unknown token or a spec the product does not carry renders empty in print, and in the editor with nothing previewed the token is drawn as itself so the designer sees what will fill. The Inspector's Text section has an Insert field button: the dialog shows the content with the cursor kept, a search box, the catalogue grouped Product / Specs / Set / Line with the label left and the token right, and a Preview line rendered against whatever the layer is currently previewing with, reading "(preview a product to see values)" when there is nothing; a click inserts at the cursor and Done writes the content back as one undoable edit. A layer whose content holds a token reads as dynamic, with a `{}` marker in the Layers panel rather than the amber unlinked icon, and Relink-all leaves it alone. `ProductTagData` and the print payload's resolved line both carry `specs` of `{key, label, value, unit}` built from the registry and the product's reviewed spec values, asserted on the wire; the dialog's spec keys come from a dealer-kit registry read behind `dealer_kit.tag_templates.view`, so a new spec key appears without a code change. No filters, no arithmetic and no conditionals are offered.
- **AC-M.25** `[FE][T]` Arrange works inside a group. With a badge selected inside a product block, Send to Back puts it below its siblings in that block and above nothing outside it, so it draws under the block's photo; Bring to Front puts it above its siblings and still under nothing outside the block; Bring Forward and Send Backward each step it past exactly one sibling. The rest of the tag keeps its order, the block stays contiguous with its group layer directly above its own subtree, and every layer in the document carries a `z_index` from 1..n with no gaps and no ties. A reorder inside a nested group moves among that inner group's children only and leaves the outer order untouched. A selection with no common parent, a child of one block together with a top-level layer, still arranges as whole top-level blocks the way it does today, and a top-level selection is unchanged. Each direction is one undoable edit.
