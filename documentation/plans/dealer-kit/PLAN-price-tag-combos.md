# PLAN - Price tag combos: catalogue packages on the request, one line, many tags

Status: Grilled 14 Sep 2026 (lavish, four rounds, owner GO "ok good to go"); lane cut off db9528463 (c15766169); issues S1 #896, S2 #897, S3 #898, S4 #899; Phase 1 S1 next
UAC: `documentation/plans/dealer-kit/price-tag-combos-acceptance-criteria.md`
Predecessors: `PLAN-price-tag-r7-request-ux.md` (D3 hid alternatives), r9 `PLAN-price-tag-r9-review-loop.md` (in flight, pins keyed by line)
Grill artifact: `.lavish/combo/product-combo-alignment.html` (session ended by owner)
Lane: one lane, one PR. Branch `feat/price-tag-combos`, worktree `.claude/worktrees/price-tag-combos`, FE :3083 / BE :8083.

Marketing's ask (three voice notes, 1 Sep, transcribed): a cabinet is sold as a catalogue
package (cabinet + table top + mirror + tap + pop-up waste, and a basin picked from four
colours); salespeople ask for "11834" and omit the basin code; the designer would print four
tags and let them choose; kitchen sinks package the same way (sink + free drainers + a tap
picked from a list, with upgrade taps at a top-up).

All line refs are `origin/main` at ae0831776 unless a worktree is named.

## What exists (measured, one Opus explorer 14 Sep)

- **A request line is one tag.** The tag sheet doc keys every placed tag by
  `request_line_id` (`lib/dealer-kit/tag-template-types.ts:440`); `tagsFromDoc`
  (`lib/dealer-kit/request-tags.ts:798-816`) returns `Map<line_id, PlacedTag>`; copies per
  `quantity` are minted at design time by `copiesOf` (`:676-690`, key `${lineId}#${copyIndex}`)
  and laid out by `autoArrange` into `doc.sheets[].tags[]`. The designer's state is
  `Record<lineId, PlacedTag>` (`RequestTagDesigner.tsx:157-161`), `resolvedRows` joined by
  `row.line_id` (`:304-307`), `?line=` honoured on first pick (`:329-345`), `LinesRail`
  (`:1236-1340`). Print page reads `resolvedData[tag.request_line_id]`
  (`TagSheetRenderer.tsx:1069`); the backend never expands quantity
  (`tag_sheet_export_service.py:330-383`).
- **One resolver, four consumers.** `resolve_request_line_data`
  (`app/services/dealer_kit/tag_data_service.py:450-523`) returns one row per line
  (`line_id, code, name, dimensions, spec_lines, specs, set_members, images, list_price,
  sell_price, show_promo_price, included_accessories, quantity, barcode`), override applied at
  `:493-495`. Consumers: designer resolve route (`price_tag_requests.py:470`), portal design
  payload (`portal_price_tag.py:218`), CRM + portal detail body
  (`price_tag_request_service.py:789`), print payload (`tag_sheet_export_service.py:342`).
  `product_tag_data` (`:315-344`) gets `offer_price` from `pricing.resolve_prices`;
  `_set_member_text` (`:437-447`) prints `- CODE (NAME) DIMS` per line into the `set_members`
  slot, which every current template already carries.
- **Set guard.** `_BATHROOM_FURNITURE_CLASS` (`price_tag_request_service.py:80`), enforced in
  `submit_request` (`:342-362`), `validate_set_guard` (`:619-636`, called from the portal
  submit route `portal_price_tag.py:377`), `_ala_carte_offender` (`:638-657`, reads
  `ProductCategory.class_label`), `_set_guard_refusal` (`:659-681`, `detail=line:<index>`),
  and reused by `portal_revision_service.py:427,433`. There is NO CRM route that creates a
  request or its lines; `create_request` is called only from `portal_price_tag.py:112`, lines
  are written by `replace_lines` (`:305-339`) and `_add_lines` (`:208`). Zero Bathroom
  Furniture product sets exist, so every SRT-FC product (200: cabinets, mirrors, table tops)
  is blocked today.
- **Portal form.** `PriceTagRequestForm.tsx`: `DraftLine` (`:107-122`, carries dead
  `alternatives` and `guard_error`), `LineRow` (`:2021-2119`, Item is a `SearchableSelect`
  `:2057-2068`, Quantity, Remarks, trash; `guard_error` sub-row `:2110-2118`),
  `payloadLines()` (`:825-835`), `applyFieldErrors` puts `line:<index>` on the row
  (`:861-889`). Lookup `lookupTagItems` (`portal/lib/price-tag-request-service.ts:219-229`)
  -> `portal_price_tag.py:527-550` -> `lookup_tag_items`.
- **CRM detail.** `PriceTagRequestDetail.tsx` tabs request / lines / attachments
  (`:404-415`); Lines table inline (`:465-581`): Type, Code, Name, Qty, List, Sell (+ amber
  override sub-line `:534-539`), Remarks, Tag (Designed / No tag from `tagsFromDoc` `:140`),
  Design button -> `?line=<id>` (`:219-226`). `marketing_price_override` has a wire
  (`PUT /lines/{lineId}`, `price_tag_requests.py:218-250`, blind setattr) and no CRM UI.
- **Companion pattern to copy (#779).** Suppliers tab mounts `ProductSuppliedWithSection` +
  `ProductShipsWithSection` (`ProductSuppliersTab.tsx:108-109`); hook
  `products/hooks/useProductCompanions.ts`; service `productCompanionService.ts` (contract
  comment at `:3-54`); route `app/api/v1/master_data/product_companions.py` (list/create/
  delete, permissions `master_data.products.view|edit` at `:32-33`, no dedicated slug by
  design); service `product_companion_service.py`; schema `schemas/product_companion.py`;
  models `product_companion.py` (rule + host child rows). Product detail tabs
  (`ProductDetail.tsx:291-326`): overview, stock, purchases, attachments, suppliers,
  promotions, variants, specifications, audit.
- **Product sets are searched by the chatbot** (`chatbot/lanes/business/gate.py`,
  `miss_suggest.py`), which is why the owner rejected a set as the package object.
- **System settings.** One wide row `SystemSetting` (`models/user.py:274-606`); JSONB list
  precedent `chatbot_completed_lanes` (`:582-586`, `server_default="[]"`); API
  `user_management/settings.py` update model `:20`, manual GET dict from `:238` (must carry
  every new column, `:243`), write impl `:482`; FE `settings/page.tsx:330-357` payload map,
  list-valued read precedent `settings/layout.tsx:106-107`.
- **Alembic.** Main head `515_chatbot_offer_decline`, single. Price tag chain is
  `ptag_000N_<slug>`; r9 adds `ptag_0007_print_collection` (off `510`) and
  `ptag_0008_pins_versions` and will re-parent at its pre-PR gate.
- **r9 (worktree `.claude/worktrees/price-tag-r9`) keys by line:**
  `price_tag_review_comments.line_id` (nullable FK, index `ix_ptag_review_comments_line_id`),
  `price_tag_request_lines.pinned_tag_data` (JSONB, embeds `"line_id"`), `pinned_at`,
  `data_change_ack_hash`, `dealer_kit.page_version.pinned_line_data` (dict keyed by line
  id); FE `DesignPinLayer.tsx`, `lib/dealer-kit/review-comments.ts`, `design-payload.ts:102`.
- **Tests.** Backend price tag tests are flat `tests/test_price_tag*.py` (5) +
  `test_portal_price_tag*.py` (5) + `test_dealer_kit_tag_data.py` (resolver) +
  `test_tag_sheet_print_company_scope.py`; fixture `tests/_pg_fixture.py` (`blank_session`,
  `unique_code`, usage `test_price_tag_request.py:16,56-60`). Vitest: designer
  `RequestTagDesigner*.test.tsx` (4), portal `PriceTagRequestForm.*.test.tsx` (9),
  `PriceTagRequestDetail.test.tsx`.

## Rulings (owner, 14 Sep, lavish rounds 1 to 4)

1. **Not a product set.** A set is a synthetic code the system never sold, and the chatbot
   searches sets. WC two-piece sets untouched.
2. **Combos live on the real host product**, one or many per host, named as the catalogue
   names them ("2 in 1", "4 in 1"). Marketing edits them on the product page. No code, no
   price. Part's page shows read-only "Sold with".
3. **The requested product is the line.** Parts fill in as rows under it when picked
   (Package select on the line when the host has several combos). Salesperson removes,
   adds by hand, or leaves a choice group open.
4. **Submit warns and allows.** Guarded classes Bathroom Furniture + Kitchen Sink,
   editable in System Settings. Warning stored on the line for marketing.
5. **One line, N tags under it.** One tag at submit; marketing splits an open part into N
   tags in the designer, or picks one. Cloning lines was rejected: the request must keep
   showing what the salesperson asked for.
6. **Price per tag**: sum of list prices of the products on the tag, promotion engine per
   product, marketing override on the tag. No price on the combo.
7. **Data cost accepted**: 60 to 100 combos authored by hand; catalogue-page reader deferred.

## Design

### D1 Combos on the product (S1)

Two tables, copying the #779 shape (rule + child rows), company scoped through the host.

```
product_combos            id, host_product_id FK products RESTRICT, name varchar(100),
                          sort_order int, created_by, created_at, updated_at
                          UNIQUE (host_product_id, name)
product_combo_parts       id, combo_id FK product_combos CASCADE, part_product_id FK products
                          RESTRICT, choice_group varchar(100) NULL, sort_order int
                          UNIQUE (combo_id, part_product_id)
                          CHECK (part_product_id <> host via service, not DB)
```

Routes (`app/api/v1/master_data/product_combos.py`, registered beside product_companions):

| Method | Path | Perm | Notes |
| --- | --- | --- | --- |
| GET | `/master-data/products/{id}/combos` | products.view | combos with parts, each part `{product_id, code, name, dimensions, choice_group, sort_order}` |
| POST | `/master-data/products/{id}/combos` | products.edit | `{name}`; 409 `COMBO_NAME_TAKEN` |
| PATCH | `/master-data/product-combos/{combo_id}` | products.edit | `{name?, sort_order?}` |
| DELETE | `/master-data/product-combos/{combo_id}` | products.edit | 204, cascades parts |
| POST | `/master-data/product-combos/{combo_id}/parts` | products.edit | `{part_product_id, choice_group?}`; 422 host-as-part `COMBO_PART_IS_HOST`, duplicate `COMBO_PART_DUPLICATE` |
| PATCH | `/master-data/product-combo-parts/{part_id}` | products.edit | `{choice_group?, sort_order?}` |
| DELETE | `/master-data/product-combo-parts/{part_id}` | products.edit | 204 |
| GET | `/master-data/products/{id}/sold-with` | products.view | `[{host_product_id, host_code, host_name, combo_id, combo_name}]` |

Service `app/services/product_combo_service.py`; schema `app/schemas/product_combo.py`;
model `app/models/product_combo.py`. Cross-company: host resolved under the caller's
company scope, 404 otherwise (AC-S1-7). Audit: `product_combos` `__audit_track__ = True`
with entity type `product_combo` (product page audit tab shows it).

FE: `products/[id]/components/ProductCombosSection.tsx` + `ProductSoldWithSection.tsx`
mounted on the **overview tab** below the existing cards (the combo is what the product is
sold as, not a supplier fact; the Suppliers tab keeps #779's purchasing bundling). Hook
`products/hooks/useProductCombos.ts`, service `products/services/productComboService.ts`
(contract comment at the top per the layering rule), types
`products/types/productCombo.types.ts`. Add combo = small modal with one name field. Parts
table: Part (code, name, dimensions), Choice group (clearable `SearchableSelect` with
`allowCreate`, options = labels already used in this combo), delete (deferred countdown via
the existing `useDeferredAction`). Empty state "No combos" + Add combo. Rows sharing a label
are grouped visually under the label with "pick one". Product picker = the shared product
search (`components/common/ProductSearchSelect` or whatever the portal lookup already uses;
never a capped dropdown).

### D2 Portal request: parts under the line, warn and allow (S2)

Line and parts:

```
price_tag_request_lines   + combo_id uuid NULL FK product_combos SET NULL
                          + package_warning text NULL
                          - alternatives (dropped)
price_tag_request_line_parts
                          id, line_id FK lines CASCADE, product_id FK products RESTRICT NULL,
                          role varchar(100) NULL, candidates jsonb NOT NULL default '[]',
                          sort_order int
                          CHECK ((product_id IS NOT NULL AND candidates = '[]') OR
                                 (product_id IS NULL AND jsonb_array_length(candidates) > 0))
```

Payload (`PriceTagRequestLineCreate`): add `combo_id: Optional[str]`, `parts:
list[LinePartIn]` with `LinePartIn {product_id?: str, role?: str, candidates?: list[str]}`;
drop `alternatives`. `_add_lines` / `replace_lines` write parts in order.

Portal lookup gains combos: `GET /portal/lookups/price-tag-items?q=` unchanged; a new
`GET /portal/lookups/product-combos/{product_id}` returns `[{combo_id, name, parts:[{product_id,
code, name, choice_group}]}]` under the same `_assert_visible` gate. The form calls it on
product pick: one combo -> parts fill in; several -> Package select (clearable
`SearchableSelect`), parts follow the choice. An open row = one row per choice group with a
clearable candidate select ("Not sure, any of N" placeholder) and the single copy line
"Marketing will prepare one tag per option". Part rows removed by staged removal (no
countdown, per the staged-removals rule), added by hand via the shared product search. Draft
save round-trips parts and `combo_id`.

Guard (replaces the 422):

```
guarded = settings.price_tag_guarded_classes  (JSONB list, default
          ["Bathroom Furniture", "Kitchen Sink"])
for each product line:
  if class_label in guarded:
    if line.combo_id is None and host has no combos:   warning = "No package defined"
    elif line.combo_id is None and host has combos:    warning = "No package chosen"
    else: missing = combo fixed parts not present as a part row (by product_id)
          plus choice groups with neither a resolved nor an open row
          warning = "Missing: " + ", ".join(codes or group labels) if any
  line.package_warning = warning or None
```

Runs in `submit_request` and `portal_revision_service` where the old guard ran;
`_BATHROOM_FURNITURE_CLASS`, `validate_set_guard`, `_ala_carte_offender`,
`_set_guard_refusal` and the `SET_GUARD_VIOLATION` code are deleted; product-set lines keep
their existing path. The form computes the same warning client-side for the pre-submit row
warning (same rule, evaluated over the rows it holds) and shows a pill "Package warning" on
the portal read view. `DUPLICATE_LINE` stays.

Settings: `system_settings.price_tag_guarded_classes JSONB NOT NULL default
'["Bathroom Furniture","Kitchen Sink"]'`; update model + manual GET dict + write impl in
`settings.py`; FE settings page: `SearchableMultiSelect` over
`GET /master-data/product-categories/class-labels` (distinct non-null `class_label`,
new tiny read route beside the categories router). Both manual dict builders (`get_user` /
`get_me` do not carry settings, so only `settings.py` `:238+`).

### D3 One line, many tags (S3)

```
price_tag_request_tags    id, line_id FK lines CASCADE, sort_order int, quantity int NOT NULL,
                          choices jsonb NOT NULL default '{}'   -- {role: product_id}
                          marketing_price_override numeric(15,2) NULL,
                          marketing_override_reason text NULL, created_at, updated_at
price_tag_request_lines   - marketing_price_override, marketing_override_reason (moved)
```

Creation: `submit_request` (and `replace_lines` on revision, which rebuilds tags 1:1 for
new lines and keeps existing tags where the line survives) creates one tag per line with
`quantity = line.quantity`, `choices = {}`. Tag ordinal shown as `1a, 1b` (line index +
letter), never an id.

Routes (`price_tag_requests.py`, `_PROCESS`):

| Method | Path | Notes |
| --- | --- | --- |
| PATCH | `/price-tag-requests/{id}/tags/{tag_id}` | `{quantity?, marketing_price_override?, marketing_override_reason?, choices?}` |
| POST | `/price-tag-requests/{id}/tags/{tag_id}/split` | `{role}`: resolves the tag to candidate 1, inserts N-1 siblings after it with `choices[role]` = each remaining candidate, copies the placed tag geometry in the draft doc; returns the line's tags |
| DELETE | `/price-tag-requests/{id}/tags/{tag_id}` | 422 `LAST_TAG` when it is the line's only tag; removes its placed tag from the draft doc |
| PUT | `/price-tag-requests/{id}/lines/{line_id}` | removed |

Resolver: `resolve_request_line_data` returns one row per TAG: existing keys plus `tag_id`,
`line_id`, `tag_label` ("1a"), `open_groups` (list of `{role, candidates:[codes]}` still
unresolved on this tag), `parts` (resolved part rows `{code, name, dimensions}`). `quantity`
= tag.quantity. `set_members` text for a product line with parts = `+ CODE NAME DIMS` per
part in order, then `ROLE: CODE / CODE / CODE` per open group (D4). Price per D4.

Doc: `PlacedTag.request_line_id` -> `request_tag_id` (type rename in
`tag-template-types.ts`, `request-tags.ts` helpers `tagForLine` -> `tagForTag`,
`placementKey(tagId, copy)`, `tagsFromDoc` keyed by tag id, `applyDesignToSiblings` over the
request's tags). Designer state `Record<tagId, PlacedTag>`, `selectedTagId`, `?tag=` deep
param (`?line=` resolves to the line's first tag for old links), `LinesRail` renders lines
with nested tag rows (label, resolved choice or "Open: Basin" pill, Split / Pick one actions
on an open tag). `ArrangeSheetView`, `TagSheetRenderer` (`resolvedData[tag.request_tag_id]`),
print page, portal `PriceTagProofViewer` follow. CRM Lines tab: line row (Type, Code, Name,
Qty, warning pill, Remarks) + indented part rows + indented tag rows (label, choices, List,
Sell with override sub-line, Designed / No tag, Design -> `?tag=`).

Migration `ptag_0009_combos_tags` (revision id 21 chars):
1. create `product_combos`, `product_combo_parts`, `price_tag_request_line_parts`,
   `price_tag_request_tags`; add `lines.combo_id`, `lines.package_warning`;
   `system_settings.price_tag_guarded_classes`.
2. data: one tag per existing line (`quantity`, override, reason copied); rewrite every
   `dealer_kit.page.doc` and `dealer_kit.page_version.doc` whose `kind = 'tag_sheet'`:
   each `tags[].request_line_id` -> `request_tag_id` of that line's tag (copies keep their
   `-cN` suffix). Rows whose line no longer exists are dropped from the doc.
3. r9 remap (guarded by `inspector.has_table / has_column`): `price_tag_review_comments`
   gains `tag_id` FK tags CASCADE NULL + index, filled from the line's tag, `line_id`
   dropped; `lines.pinned_tag_data` moves to `tags.pinned_tag_data` (+ `pinned_at`,
   `data_change_ack_hash`) with the inner `line_id` key rewritten to `tag_id`;
   `page_version.pinned_line_data` re-keyed by tag id. If r9 is not on main when this
   merges, this step is a no-op and r9's pre-PR gate adds the equivalent remap to its own
   migration (recorded in r9's plan Status line at that time).
4. drop `lines.alternatives`, `lines.marketing_price_override`,
   `lines.marketing_override_reason`.
Down-revision: main head at cut time; `scripts/alembic-reparent.sh` at the pre-PR gate.
Expected merge order: r9 first (it is in Phase 3), so `down_revision` will land on
`ptag_0008_pins_versions`.

### D4 What prints (S4)

- `set_members` slot text for a product tag with parts (D3). Templates unchanged.
- Prices: `list_price` = host list + sum(part list) over resolved parts (open groups
  contribute nothing); `sell_price` = `resolve_prices` over host + resolved parts summed
  (offer where the engine has one, list otherwise), quantized 0.01; override on the tag wins.
  A tag with no parts is exactly today's product tag.
- Portal read view lines show parts and the warning pill; preview and PDF render through the
  existing payload with `resolvedData` keyed by `request_tag_id`.

### Not building (triggers named)

- Catalogue-page reader proposing combos (trigger: next season's catalogue + a complaint
  about the by-hand pass; reuse `flyer_reading_service`).
- Price stored on the combo (owner: two places for a price to be wrong).
- Chatbot answer "11834 comes with..." (trigger: a customer asks it; the tables are ready).
- Auto-split at submit (owner chose marketing in the designer).
- Combo import sheet (trigger: > 100 combos to enter at once).

### Design brief

- Product page Combos section: low frequency (marketing, a few times a season), dense table.
- Portal form parts rows: daily for salespeople; must not slow the existing line entry.
  Part rows appear in place with the existing list transition preset only.
- Designer rail nesting: marketing, per request. No new motion; Split re-renders the rail.
- Must NOT animate: price figures, warning pills, the parts table, sheet re-layout after
  Split.

## Slices and phases

| Slice | Scope | Phase 1 (FE mock) | Phase 2 (tester red, then coder) |
| --- | --- | --- | --- |
| S1 | Combos on the product (D1) | Combos + Sold with sections, modal, parts table against a mocked service | model + migration part 1 + routes + service; swap mock |
| S2 | Portal parts + warn-and-allow + settings (D2) | parts rows, package select, open rows, client warning, settings multi-select against mocks | line parts model, payload, lookup route, guard rewrite, settings column; swap |
| S3 | Tags under the line (D3) | designer rail nesting, Split / Pick one, CRM Lines tab, `?tag=` against a mocked resolver | tags model, migration parts 2 to 4, routes, resolver per tag, doc re-key, r9 remap |
| S4 | Render + price (D4) | none (print path is server-fed) | resolver text + price, portal payload, evidence run of the PDF |

Order S1 -> S2 -> S3 -> S4. Phase 1 for S1 to S3 lands before any Phase 2. ONE coder for the
lane (Opus while the Sonnet limit holds, reason recorded in the brief), tester writes red
tests per slice before the coder's Phase 2. Phase 3 once: reviewer + security-reviewer
(touches permission-gated routes, portal ingest, company scoping, a migration over prod
JSON) + agent-browser verification, then guide-writer.

## Captain's test list (one line per AC)

pytest unless stated.

- AC-S1-2 `test_product_combos_create_duplicate_name_409`: second POST same name -> 409 `COMBO_NAME_TAKEN`.
- AC-S1-3 `test_combo_part_refuses_host_and_duplicate`: host as part -> 422; same part twice -> 422.
- AC-S1-5 `test_combo_delete_cascades_parts`: delete combo -> 0 parts; part referenced by a submitted line's part row still deletable.
- AC-S1-6 `test_sold_with_lists_hosts_across_combos`: part in two combos of two hosts -> two rows.
- AC-S1-7 `test_combos_cross_company_404`: caller scoped to Mocha, Sorento host -> 404.
- AC-S1-8 `test_business_gate_ignores_combos`: resolver for the host code returns the host product; no combo table read (assert query count or result shape).
- AC-S1-1/4/9 vitest `ProductCombosSection.test.tsx`: empty state; grouped choice rows; 375px container scroll.
- AC-S2-5 `test_submit_package_warning_texts`: guarded + no combos -> "No package defined"; combo chosen, mirror row removed -> "Missing: SRTMR502-BL"; clean -> NULL.
- AC-S2-6 `test_settings_guarded_classes_round_trip`: PUT list, GET dict carries it; default equals the two classes.
- AC-S2-7 `test_set_guard_violation_retired`: the two former 422 fixtures in `test_price_tag_request.py` now 201 with `package_warning`; set line path unchanged.
- AC-S2-8 `test_line_parts_persist_in_order`: three parts with roles/candidates -> stored order and shapes.
- AC-S2-10 `test_duplicate_line_still_refused`.
- AC-S2-1/2/3/4/11 vitest `PriceTagRequestForm.parts.test.tsx`: fill on pick; package select when 2 combos; open row select + clear; staged removal; 375px.
- AC-S2-9 agent-browser evidence: draft -> reload.
- AC-S3-1 `test_migration_ptag_0009_one_tag_per_line_and_doc_rekey`: seeded request with a saved doc -> tags created, doc `request_tag_id` set, override moved.
- AC-S3-1 `test_submit_creates_one_tag_per_line`.
- AC-S3-4 `test_split_tag_resolves_first_and_adds_siblings`: 4 candidates -> 4 tags, original id kept, sort 1..4, `choices[role]` distinct.
- AC-S3-5 `test_tag_patch_override_round_trip` + `test_line_override_route_gone` (404).
- AC-S3-6 `test_delete_last_tag_422`.
- AC-S3-7 `test_migration_remaps_r9_pins` (skipped when r9 tables absent).
- AC-S3-8 `test_print_payload_one_row_per_tag`: resolved rows = tags, quantity per tag.
- AC-S3-2/3 vitest `PriceTagRequestDetail.test.tsx` (nested rows), `RequestTagDesigner.tags.test.tsx` (`tagsFromDoc` by tag id, `?tag=`, `?line=` fallback, Split action calls the service).
- AC-S4-1 `test_set_members_text_parts_and_open_group`.
- AC-S4-2 `test_tag_price_sum_promotion_override`: three cases.
- AC-S4-3/4 agent-browser evidence: portal read view + PDF of a split line.

## Risks

- **Doc rewrite over prod JSON.** Migration step 2 walks every tag sheet doc; a doc with a
  `request_line_id` that no longer exists is dropped from the doc, logged. Test on the prod
  copy before the PR is ready.
- **r9 ordering.** Two migrations touching the same columns from two lanes. Rule: whoever
  merges second owns the remap, recorded in both plans' Status lines at that moment.
- **Guard softening.** A guarded product can now reach marketing bare. That is the owner's
  call (round 1, Q1); the warning text is the mitigation.
- **Parts on WC set lines.** Not supported; set lines keep their own path. A cabinet request
  therefore never mixes set and combo on one line.
