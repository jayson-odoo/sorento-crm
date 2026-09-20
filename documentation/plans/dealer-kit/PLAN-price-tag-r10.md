# PLAN: price tag r10 - self print by default, no quantity from the image, all variations on one tag, automatic arrange, combo image, price tag description, readable spec values

Status: building (owner "ok go" on the lavish page, 20 Sep 2026, round 5; the six lost round-1 comments were never re-sent and are treated as covered by rounds 2 to 5)
Source: owner's price tag testing notes, 17 Sep 2026 (WhatsApp): "always i print myself, qty ignore",
"promo only follow dealer use A3 flyer", "sometimes dealer want all variation in 1 price tag", "gap easier to
cut", "1. combo image 2. description 3. templates".
UAC: `price-tag-r10-acceptance-criteria.md` (alongside).
Measured against: `origin/main 0fb5ec7d1`, prod copy `sorento_ai_automation_0918_1900`.
Lane: `feat/price-tag-r10` off `origin/main 86547d074`, worktree `.claude/worktrees/price-tag-r10`, one migration
`ptag_0013_r10` chained on the single alembic head at the pre-PR gate (`522_oi_cancelled_used_confirm` on 20 Sep; `./scripts/alembic-reparent.sh` re-parents it). Private pytest DB `sorento_ptr10_ci` (clone of sorento_buc_ci, migrated to head).

## The seven findings and what exists today

| # | Owner note | Today (measured) | Change |
|---|---|---|---|
| 1 | Always "I print myself"; keep the field, default it, hide it | `price_tag_requests.print_by` is `office`/`self`/NULL, required at submit (`PRINT_BY_REQUIRED` 422), portal radio at `PriceTagRequestForm.tsx:2743`. Prod: office 10, self 4, NULL 3 | Portal control removed, payload sends `self`; NULL rows backfilled to `self`; CRM office control stays (Q7) |
| 2 | Quantity is the number of tags, never read from the image; default 1 | Extract prompt asks for `{product_code, product_name, quantity, ...}` (`extract_service.py:748`); FE applies `Math.max(1, round(quantity))` else 1 (`PriceTagRequestForm.tsx:1026`). Prod has stored prompt version 1 per key (19 Sep) | Price tag prompt gets rule (9): never emit quantity; its line-items clause drops `quantity`; FE ignores any extracted quantity on this form |
| 3 | Sometimes the dealer wants ALL variations on ONE tag; designer must offer parent + every child | Open choice group auto-splits at submit into one tag per candidate (`_add_line_tags`, cartesian). A tag's parts = resolved parts + the chosen candidate; the subject picker lists those parts | Split stays. Every tag exposes every product of the line's combo to the subject picker; a tag can be marked Not printed so arrange and the PDF skip it (ruled round 4) |
| 4 | Arrange must be automatic: small tag 9 x 3, kitchen sink 2 x 2, DIY 7 x 2, overflow to next page, zero gap | Arrange = one grid sized off the LARGEST tag, 3 mm bleed, 2 mm gap, centred, drag-to-pin, page/bleed/gap inputs (`ArrangeSheetView.tsx`, `request-tags.ts:726`) | Arrange groups tags by size, packs each size on its own sheets at 0 gap inside a 5 mm printable margin, turns the group 90 degrees when that fits more (sheet stays portrait), overflows to the next sheet; inputs and drag removed |
| 5 | A combo has ONE picture of all its products; it must come out when the combo is picked | `product_combos` has no image; a line's image = the parent product's gallery (`product_images.py:128`) | `product_combos.image_attachment_id`, uploaded on the combo block as a product attachment of the new type Combo Image; a line with that combo puts the combo image first |
| 6 | Once a product is picked the image AND description should come out; a per-product "price tag description" field feeds a template variable | No description merge field; `product.spec_lines` falls back to `products.description` (AutoCount text) | `products.price_tag_description` (multi-line, product page); merge field `product.price_tag_description` |
| 7 | Variable values render `stainless_steel`; must read `Stainless Steel` | `_spec_display_value` in `tag_data_service.py:243` emits `str(raw)`; `ProductSpecRegistry.value_labels` exists but is `{}` on every prod key and is never read on the tag path. FE already has `readableValue` in `lib/spec-readable.ts` for product pages | Backend `product_specs` maps through `value_labels`, then title-cases the slug with an acronym set (`pvc`, `abs`, `pp`, `led`) |

Not in scope, named: "promo only follow dealer use A3 flyer" is a statement of how promotions are chosen (the
per-line promotion from #948 already follows the active promotion covering the line's products); no change.
"3. templates" = the owner re-authors the live templates once 6 and 7 land (variables swap, sizes per Q1);
no code.

## Measured facts

Templates on prod (`dealer_kit.tag_template.print_size`, mm) and what a zero-gap A4 grid gives:

| Template | Size | Portrait fit | Rotated 90 fit | Owner says |
|---|---|---|---|---|
| Small Price Tag LP / SP, DIY Tag, Free Item | 95 x 44.5 | 2 x 6 = 12 | 3 x 4 = 12 | small 9 rows x 3 cols = 27, DIY 7 x 2 = 14 |
| Kitchen Sink, Kitchen Sink SP | 140 x 98 | 1 x 3 = 3 | 2 x 2 = 4 | 2 x 2 |
| Bathroom Furniture, Bathroom Furniture SP | 98 x 140 | 2 x 2 = 4 | 3 x 1 = 3 | (not stated) |
| preset Free Item | 60 x 34 | 3 x 8 = 24 | 4 x 6 = 24 | - |

9 x 3 on A4 portrait is a 70 x 33 mm cell; 7 x 2 is 105 x 42.4 mm. The stored small and DIY sizes (95 x 44.5)
give 12 per sheet either way, so either the templates are the wrong size or the grid the owner quotes is from a
different sheet. This is Q1.

- Tag sheet doc lives in `dealer_kit.page.draft_doc` (`TagSheetDoc`: `imposition`, `sheets[].tags[]` in mm,
  `pinned`). The PDF print page renders that doc as-is (`TagSheetRenderer.tsx`), one `.sheet` per page, always
  portrait A4 (`dealer_kit_export_tasks.py:185`). Prod: 4 requests with a doc, all `preset: auto`, 1 sheet each.
- Combos on prod: 7 rows. Lines with an open part: 6.
- Extract prompt: `ai_prompt_versions` holds version 1 of `ai_extract_portal_price_tag_request` (seeded 19 Sep,
  text = fallback). `get_prompt` reads the DB version, so a fallback-only change would not reach prod.
- Spec registry: 0 of ~60 keys have `value_labels`; enum keys (`finish`, `control_type`, `flush_type`,
  `furniture_type`, `material`, ...) store slugs such as `stainless_steel`, `rose_gold`, `single_lever`.

## Design (simplest thing that works)

### S1. Print option: default `self`, portal control hidden

- `PriceTagRequestForm.tsx`: delete the radio block and `MISSING_PRINT_BY` check; `printBy` state is a constant
  `'self'`; the three payloads (draft, submit, revise) keep sending `print_by: 'self'`. Nothing else in the
  portal reads it.
- Backend untouched: `validate_submittable` still requires a value (always satisfied), `is_terminal`,
  `notify`, `run_auto_collect` keep branching on it.
- Migration data step: `UPDATE price_tag_requests SET print_by='self' WHERE print_by IS NULL` (3 rows on prod),
  so every old row reaches the terminal state the same way a new one does.
- CRM detail keeps the `Printing:` line and the office PATCH control (Q7). Office print remains reachable from
  the CRM for the odd request; nothing on the portal can pick it.

### S2. Quantity never comes from the document

- `ai_prompt_registry._ai_extract_price_tag_fallback` adds rule (9): "`quantity` is how many tags the
  salesperson wants, which the document never says. Omit `quantity` from every entry; never copy a quantity,
  pack size or order quantity from the document."
- `extract_service._build_messages` line-items clause: for `portal.price_tag_request` the entry shape is
  `{product_code, product_name, notes}` (no quantity, no prices).
- Migration data step: if the stored `ai_extract_portal_price_tag_request` text equals the OLD fallback
  (untouched since seed), insert version 2 with the new text; if the owner edited it, leave it and the plan
  notes tell the owner to paste rule (9) in System Management > AI Assistant.
- `PriceTagRequestForm.tsx:1026`: `const qty = 1` for extracted lines on this form; merging into an existing
  line no longer adds to its quantity (a second sighting of the same code is not a second tag).

### S3. Readable spec values

- `tag_data_service.product_specs`: `value = _spec_display_value(raw, key.value_labels)`; the helper returns
  `labels[str(raw)]` when present, else for a string slug returns the title-cased words with `_` as space, each
  word uppercased when in `SPEC_ACRONYMS = {"pvc", "abs", "pp", "led", "uv", "ss", "sus"}`, else unchanged
  (bool and float rules as today). `stainless_steel` -> `Stainless Steel`, `rose_gold` -> `Rose Gold`,
  `pvc` -> `PVC`, `407` -> `407`, `true` -> `Yes`.
- Numeric strings and free text with spaces are returned untouched (a slug is `^[a-z0-9]+(_[a-z0-9]+)*$`).
- FE unchanged: `specText` keeps passing `spec.value` through. The pinned-data hash changes for tags carrying
  an affected spec, so the data-change red dot fires once per open request; expected.

### S4. `products.price_tag_description`

- Column `products.price_tag_description TEXT NULL`. Schema: `ProductCreate`/`ProductUpdate`/`ProductResponse`
  and BOTH manual dict builders (lesson: a new column must reach every builder).
- Product page: textarea "Price tag description" on the Overview edit form below Description; detail view shows
  it verbatim with line breaks. Excluded from the AutoCount masters push (it is staff-authored, like `remark`
  is AutoCount-authored; the two never overwrite each other).
- Tag data: `product_tag_data` and `_part_row` carry `price_tag_description`; `TagProductData`/`TagPartData`
  types gain it. `merge-fields.ts` `PATH_SLOTS` gains `product.price_tag_description`, label "Price tag
  description", group Product, after Spec lines. Subject-aware like every `product.*` token.
- Empty field renders nothing (Q5). No fallback to `spec_lines` or `description`.
- Included in the pinned data hash, so an edit on the product page shows the red dot on open requests.

### S5. Combo image (ruled Q6: separate upload on the combo block, stored as a product attachment of a NEW type)

- Migration seeds attachment type `Combo Image` (`code = combo_image`, images only, 10 MB). Column
  `product_combos.image_attachment_id UUID NULL` FK `attachments.id ON DELETE SET NULL`.
- One route `POST /product-combos/{combo_id}/image` (multipart): stores the file through the storage router,
  creates the `attachments` row with type Combo Image, links it to the HOST product (`product_attachments`,
  so it shows on the product's Attachments tab like any photo), sets `image_attachment_id`. A second upload
  replaces: new row linked, old row unlinked and deleted when nothing else links it. `DELETE
  /product-combos/{combo_id}/image` clears and deletes the same way. Deferred-action delete rules do not
  apply (it is a field on the combo, not a record; same as clearing `choice_group`).
- The combo block (`ProductCombosSection.tsx ComboBlock`) shows the thumbnail with Replace and Clear, or an
  Upload control; image files only (`isImageAttachment`).
- `gallery_images` ranks type Combo Image LAST (after Technical Specifications), so a combo picture never
  becomes the product's own tag photo; `primary_image_urls` (catalogue tiles) excludes the type.
- `ProductComboOut` carries `image: {attachment_id, url} | null` (signed on read).
- Tag data: in `resolve_tags_live` (and the pinned path) when `line.combo_id` names a combo with an image, the
  line's `images` list is `[combo image as is_primary] + gallery`. `primaryImageOf` then resolves the line
  subject's `product_image` to the combo picture; a layer with subject Parent (`-1`) or a part still shows that
  product's own photo. `design_media` already walks `row["images"]`, so the PDF map needs no change.
- The image attachment id enters the pinned data, so swapping the combo picture is a product data change (S8).

### S6. Any product of the parent on any tag; a tag can be marked "not printed"

Ruled round 4 (owner): "it will always split, but the designer has the choice to use any products from the
same parent in any of the 3 tags, and designer can mark the combination to be invalid also so it doesn't go
into the arrangement during printing". So: NO portal option, NO mode switch, NO new part flag. Submit
keeps splitting an open group into one tag per candidate exactly as today. The change is in the designer.

1. Portal, salesperson. Unchanged: pick one candidate, or leave "Not sure, any of N" and get N tags.
2. Submit. Unchanged: `_add_line_tags` mints one tag per candidate combination.
3. Designer, subject picker. Today a tag's `parts` = the line's resolved parts + the candidate THIS tag
   chose, so a slot can only bind to those. New: every tag of a line exposes ALL products of the line's
   combo: fixed parts plus every candidate of every open group, in combo order, each a full product row
   (`_part_row`), with `chosen: true` on the candidates this tag's `choices` name. The subject picker
   lists them grouped by role (`Kitchen Tap · SRTKT1643SS (this tag)`, `Kitchen Tap · SRTKT1650BK`, ...).
   So on tag 1a marketing can lay out the cabinet with all three taps, each slot bound to one candidate.
   `set_members`, Tag total and `line.parts` merge fields keep today's meaning (resolved parts + this tag's
   own candidate), so an unchanged template prints exactly what it printed before.
4. Designer, not printed. Each tag row in the rail gets a toggle `Not printed` (an eye-off icon button
   with label, `aria-pressed`). A tag marked not printed: greyed row with the pill `Not printed`, still
   openable and editable, skipped by arrange (no slot, no copies), absent from the PDF, excluded from the
   per-sheet counts and the export sheet list. Reversible at any time before proof; the flag survives
   Revise (carried with the tag like quantity and overrides). So after designing 1a with every tap,
   marketing marks 1b and 1c not printed and one tag prints.
5. Print. Arrange and the print payload filter `print_excluded`; the proof the dealer sees is the arranged
   sheets, so it never shows an excluded tag either.
6. Data change (S8): a candidate added to the combo later appears in every tag's part list on the next
   auto-update; a removed one disappears; the pinned data holds the full list.

Mechanics:

- Column `price_tag_request_tags.print_excluded BOOLEAN NOT NULL DEFAULT false`. `PATCH
  /{request_id}/tags/{tag_id}` (exists, takes `quantity`) accepts `print_excluded`; refused from
  `proof_ready` on (409) like the other design edits. `PriceTagRequestTagResponse` carries it.
- `tag_data_service`: `_combo_products(db, line)` = fixed parts + every candidate of every open part, in
  order; `_part_row` for each with `role` and `chosen`. `resolve_tags_live` puts that list in `parts`
  (superset of today's), and a second key `own_parts` (today's list) feeds `set_members`, Tag total and
  `line.parts`; `pin_payload` / `data_hash` include both. Pinned rows written before r10 lack `own_parts`;
  `_row_from_pin` falls back to `parts` for them.
- FE: `TagPartData` gains `role?`, `chosen?`; `SubjectInspector` groups by role and marks the tag's own
  candidate; `productFromLineParent` and Tag total read `own_parts`. `autoArrange`, `ordered_tags` for the
  print payload, `design_media` and the sheet selector skip `print_excluded`.
- Rail: `TagRailRow` toggle + pill; `useUpdateTag` mutation already exists for quantity.
- Migration: column only. Existing tags print as before (default false).

### S7. Automatic arrange

- Ruled 20 Sep: sheets are always portrait (Q2, tags turn 90 degrees when that fits more); a 5 mm printable
  margin on every edge (Q3), so the usable block is 200 x 287 mm; the owner resizes the live templates to the
  cell (Q1): Small 66.7 x 31.9 (3 x 9), DIY 100 x 41 (2 x 7), Kitchen Sink 143.5 x 100 turned (2 x 2).
- Ruled round 2: the grid is CONFIGURABLE per tag size. A tag size (a template's `print_size`, or a saved
  size preset) may carry `sheet: {cols, rows, turn}`; when it does, arrange uses it; when it does not, arrange
  derives the best fit. Measured 20 Sep: `TagTemplate.print_size` is a bare dict on the backend, so `sheet`
  already round-trips; only the preset columns need the migration. Storage: `print_size` JSONB gains the
  optional `sheet` keys (no migration; the
  template save routes already store `print_size` whole), `dealer_kit.tag_size_preset` gains
  `sheet_cols INT NULL, sheet_rows INT NULL, sheet_turn BOOL NOT NULL DEFAULT false` (migration).
  Editing: the Tag Size panel (`TagSizeControl`, shared by the template editor and the request designer)
  gets one line under the size, `Per A4  [3] x [9]  [turn]`, showing the derived numbers greyed until the
  person types their own, with `Auto` to clear. Saved with the template's print size (template editor) or
  the preset (Save as size). Lookup at arrange time, per size group: the template of the group's tags when
  its `print_size` equals the group's size, else a preset with that exact size, else derive. A configured
  grid whose cell (usable page / cols x rows) is smaller than the tag is refused with a one-line message in
  the panel and arrange falls back to derive.
- `request-tags.ts`: `autoArrange` becomes size-grouped. Copies (tag x quantity) are grouped by
  `(width_mm, height_mm)`, groups ordered by area desc then first line order. For each group, `impositionFit`
  at gap 0 / bleed 5 (the printable margin, a constant `PRINT_MARGIN_MM`) is computed for rotation 0 and
  rotation 90; the rotation with more per sheet wins (tie:
  0). `impositionFit` allows `FIT_TOLERANCE_MM = 0.5` so a size typed to one decimal (66.7 for 200/3) still
  fits its cell. Slots are packed row-major from the top-left of a centred block (symmetrical margins, as today). With a
  configured grid the cell is usable page / cols x rows and the tag sits at the cell's top-left, so tags
  touch when the tag equals the cell and leave a strip when it is smaller; the group overflows to as many
  sheets as it needs; the next group starts a new sheet. `PlacedTag` gains
  `rotation?: 0 | 90`.
- `pinned` placements are no longer read or written; `pinnedFromDoc` and drag handling in `ArrangeSheetView`
  go. The page / bleed / gap inputs go; the view shows, per sheet, `Small Price Tag SP - 3 x 9, 27 of 30` and
  the sheet preview. `imposition` stays in the doc with `gap_mm: 0, bleed_mm: 5` written on every arrange so
  the print page and `tagSizeBounds` (ceiling = page minus 2 x 5 mm) need no new field.
- Renderers: `KonvaTagLayer`/arrange preview and `TagSheetRenderer` apply `rotation` as a transform about the
  tag's placed box (90 = the tag's width runs down the page). Page stays portrait A4; the export task is
  untouched (Q2).
- A request mixing sizes (2 kitchen sink + 30 small): sheet 1 kitchen sink 2 x 2 turned (2 used), sheets 2
  and 3 small 3 x 9 (27 + 3). Worked example is AC-S7-5.
- Per-sheet count feeds the existing sheet selector on export unchanged.

### S8. Product data change: auto-apply, keep the old data for rollback, indicator (owner addition, 20 Sep)

Today (r9 D16, #907 / #966): a tag's data is frozen (`pinned_tag_data`) when the request enters `designing`;
the designer and detail poll `GET data-changes` every 30 s, which diffs the pin against a live resolve and
shows a red dot; the person opens Review and clicks Update (re-pin, with a "Before product update" PageVersion
snapshot carrying every tag's pins, then an "after" snapshot) or Keep (ack hash). `POST versions/{n}/restore`
copies a version's pins back onto the tags and its doc onto the draft. The list shows `Product data changed
· N` from `data_changed_tag_count`. "Update all" was retired in #966.

Change: the Update click happens by itself; the version snapshot that already precedes an Update is the
rollback; the red dot becomes an "updated" indicator that the person dismisses.

- One seam: `resolve_request_line_data` already runs the live diff for every non-terminal pinned tag. When
  the diff is non-empty and the request's status is in `AUTO_UPDATE_STATUSES` (Q9), it applies the same
  steps `resolve_tag_pin(action="update")` does today: one "Before product update" PageVersion per batch (the
  existing fold rule, so N tags changing in one sweep make ONE before-version), re-pin every changed tag
  (`pinned_tag_data = pin_payload(live)`, `pinned_at = now`), then the "after" snapshot. The `pin` route's
  `update` branch calls the same helper; `keep` stays for the flag-only statuses.
- New columns on `price_tag_request_tags`: `data_updated_at TIMESTAMP NULL`, `data_update_changes JSONB
  NULL` (the `LineDataChange[]` that was applied: field, label, old, new, image urls), `data_update_version
  INT NULL` (the before-version number to roll back to). Set on auto-apply; cleared on Dismiss.
- Indicator: the rail red dot stays, now meaning "updated, not yet seen"; the Review dialog lists what changed
  (from `data_update_changes`, old -> new, image thumbnails) with two actions: **Dismiss** (clears the three
  columns) and **Roll back** (calls the existing restore route with `data_update_version`; restore already
  snapshots the state being left, so a rollback can itself be undone from the versions list). The detail
  header pill and the list badge read `Product data updated · N`; `data_changed_tag_count` keeps its column
  and now counts tags with `data_updated_at` set.
- Statuses outside `AUTO_UPDATE_STATUSES` keep today's behaviour exactly (red dot, Keep / Update).
- Terminal requests: untouched (no diff runs today either).
- `GET data-changes` remains the poll endpoint; because the read seam applies the update, the FIRST poll after
  a product edit both applies and reports it. The list sweep (`touched_request_ids`, capped per page) applies
  it too, so a request nobody has open still updates within a page load of the list.
- Restore is whole-request (every tag's pins + the doc), as today. A single-tag rollback is not built; the
  trigger for one is an owner request after a multi-tag batch where only one tag should revert.
- Roll back must ack the live hash on the restored tags of a request in `AUTO_UPDATE_STATUSES`, else the next
  poll re-applies the update it just undid (tester's test list, 20 Sep, AC-S8-12): restore already writes a
  "Before restore to vN" snapshot of the state it left, and it must stamp the SAME `data_change_ack_hash` Keep
  writes today onto every tag it restores, computed against that tag's now-current (restored) pin. A later,
  genuinely new product edit still trips the gate, because it produces a different hash.

### S9. Portal Download PDF (owner addition, 20 Sep: "the button is not clickable")

Measured on the 0918 copy: the portal button is `disabled={!request.has_completed_export}` with the
sub-label "No completed export yet" (`PriceTagRequestForm.tsx:2331`); it only streams the latest READY
`user_downloads` row and never queues one. Approve auto-queues an export (`transition_status`, D12). On prod
the auto-exports of PT-202609-0002 / 0003 / 0004 (approved 9 and 15 Sep) all FAILED with
`net::ERR_CONNECTION_REFUSED at http://localhost:3000/c/print/tag-sheet/...` (DEALER_KIT_PRINT_BASE_URL unset
in the server compose; the `FRONTEND_BASE_URL` fallback from #929 S11 merged 15 Sep, and PT-0014 / 0016
approved on 17 Sep rendered fine). Nothing retries a failed auto-export and the portal cannot ask for one,
so those three requests show a dead button for ever. That is the demo.

- Portal button enabled whenever the design block shows (`proof_ready` and later; download itself needs
  `approved` or later, so at `proof_ready` / `changes_requested` the item reads "Available after approval"
  and is disabled, as a proof is not for printing).
- Click at `approved`+: if a READY export exists, stream it (today's route). Otherwise call new
  `POST /public/portal/submissions/price_tag_request/{id}/export` (contact-authenticated like the download
  route; queues `request_tag_sheet_export` as the request's assignee, the same actor the portal approve
  uses; 409s from the service surface as the toast text). The menu item then reads "Preparing your PDF"
  with a spinner and the form polls the submission every 5 s until `has_completed_export` flips, then
  streams. A FAILED latest export reads "PDF failed, try again" and re-queues on click.
- Detail response gains `latest_export_status: ready | pending | failed | null` beside
  `has_completed_export` so the portal can tell "never asked" from "in progress" from "failed".
- CRM: no change (designer bar Export PDF at approved; detail actions at approved / ready_for_collection /
  collected).
- Owner action on prod: none. The three stuck requests get their PDF on the first click.

### S10. Designer rail keeps its scroll position on select (owner, round 4)

Cause: `RequestTagDesigner.tsx:1541-1551` renders `<TagCanvasEditor key={selectedTag.id} leftRail={rail}>`;
the rail is a prop INSIDE the keyed editor, so selecting a tag remounts the editor and with it the rail's
`overflow-y-auto` container (line 1756), whose `scrollTop` goes back to 0. A tag picked at the bottom of a
long list jumps out of view.

- Hoist the rail out of the keyed subtree: the designer lays out `[LinesRail | TagCanvasEditor]` itself and
  passes no `leftRail`; the editor keeps its `key` (the canvas must remount per tag). The rail's scroll
  container is then never remounted. `ArrangeSheetView` gets the same rail beside it (today it is inside
  the editor only when a tag is selected, so the arrange view has none; keeping the rail visible there is a
  side benefit, and the selected row highlights the tag on the sheet as `selectedTagId` already does).
- No scrollIntoView on select; the row the person clicked is under their pointer already.

## Migration `ptag_0013_r10`

1. `products.price_tag_description TEXT NULL`
2. `product_combos.image_attachment_id UUID NULL` FK `attachments(id) ON DELETE SET NULL`
3. `price_tag_request_tags.print_excluded BOOLEAN NOT NULL DEFAULT false` (S6)
3b. `price_tag_request_tags.data_updated_at`, `data_update_changes`, `data_update_version` (S8)
3c. `dealer_kit.tag_size_preset.sheet_cols`, `sheet_rows`, `sheet_turn` (S7)
4. attachment type `Combo Image` seed row (idempotent by `code`)
5. data: `print_by NULL -> 'self'`; prompt version 2 when version 1 text is untouched (ruled Q8)

Downgrade drops 1 to 3 (the type row stays if any attachment uses it); the data steps are not reversed.

## Tickets (after go)

S1 print default, S2 extract quantity, S3 spec labels, S4 description field, S5 combo image, S6 any product
on any tag + Not printed, S7 auto arrange, S8 auto-update + rollback, S9 portal PDF, S10 rail scroll. One
lane, one PR. Phase 1 FE mock: S1, S2 (FE half), S6 designer, S7, S8 dialog, S9 button states, S10.
Phase 2 tester-first: everything.

## Rulings (owner, 20 Sep 2026, on the lavish page)

- Q1 Small tag grid: owner resizes the templates to the cell; the grid follows from size.
- Q2 Sheets are always portrait; the kitchen sink tag turns 90 degrees on the sheet.
- Q3 Keep a 5 mm printable margin; the grid fits inside it (Small 66.7 x 31.9 for 3 x 9).
- Q4 (superseded by round 4: no all-variations tag) A slot bound to a candidate shows that candidate's own
  price; Tag total keeps today's meaning (parent + this tag's own parts).
- Q5 Empty price tag description prints nothing.
- Q6 Combo image: a separate upload on the combo block that ALSO stores it as a product attachment, under a
  new attachment type.
- Q7 CRM detail keeps the office print control; the portal hides it.
- Q8 Migration inserts prompt version 2 when version 1 is untouched.

## Owner additions from the same review (folded in as S8 and S9 above)

- Product data change: auto-apply instead of flag-and-click, keep the old data for rollback, indicator on
  the tag and in the designer. -> S8.
- Portal Download PDF button was not clickable at the demo. -> S9 (cause measured: failed auto-export, no
  retry).

## Round 2 rulings (20 Sep)

- Q9 Auto-apply while `designing` and `changes_requested`; from `proof_ready` on, flag only with Keep /
  Update as today. `AUTO_UPDATE_STATUSES = {designing, changes_requested}`.
- The per-A4 grid is configurable per tag size (S7 amended); S6 journey written out in full.

## Round 4 rulings (20 Sep)

- S6 replaced: always split; any product of the parent bindable on any tag of the line; a tag can be
  marked Not printed so it leaves the arrangement and the PDF. The portal option, the mode switch and the
  `all_candidates` column are gone.
- S10 added: the designer rail loses its scroll position when a tag is selected.

## Open

- Six comments from the first lavish round (before the auto-update note) were lost in transit; the owner
  re-sends them.

## Risks

- S7 drops manual pins: any request arranged by hand today (0 on the 0918 copy have `pinned`) is re-flowed.
- S3 changes pinned hashes: every open request with an enum spec shows the red dot once.
- S6 widens `parts` on every tag to the whole combo; `set_members` and Tag total read `own_parts`, so no
  existing template changes its print. Pinned payloads grow (N candidates x product row); measured on the
  0918 copy the largest combo has 4 parts, so the growth is small.
- Rotation (S7) touches both renderers; the PDF parity test (`test_dealer_kit_pdf_render`) must cover a
  rotated sheet.
