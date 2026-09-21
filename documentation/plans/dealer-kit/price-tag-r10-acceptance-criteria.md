# UAC: price tag r10

Plan: `PLAN-price-tag-r10.md`. Each AC is testable; the tester writes the red test named beside it before the
coder starts. Rulings Q1 to Q8 in the plan may amend S6/S7 lines; the amended AC is edited in place, never
left stale.

## S1. Print option defaults to self

- AC-S1-1 The portal price tag form renders no "Who prints" control; the strings "Office prints" and
  "I print myself" do not appear in the form. (vitest PriceTagRequestForm)
- AC-S1-2 Save draft, Submit and Revise payloads carry `print_by: "self"`. (vitest PriceTagRequestForm)
- AC-S1-3 Submitting a form with no print choice never shows "Say who prints these tags." (vitest)
- AC-S1-4 Migration `ptag_0013_r10` upgrade sets `print_by='self'` on rows where it was NULL and leaves
  `office` rows alone. (pytest migration)
- AC-S1-5 A request created with `print_by: "self"` reaching `approved` is terminal (`is_terminal` true);
  `ready_for_collection` is still refused for it. (pytest, existing behaviour kept)
- AC-S1-6 CRM detail still shows `Printing: I print myself` and the office control (Q7 default). (vitest)

## S2. Quantity never from the document

- AC-S2-1 The resolved system prompt for `portal.price_tag_request` contains rule (9) and the words "Omit
  `quantity`". (pytest ai_prompt_registry)
- AC-S2-2 `_build_messages("portal.price_tag_request", ...)` line-items clause names the entry shape
  `{product_code, product_name, notes}` and does not contain `quantity`; every other line-item form keeps
  `quantity`. (pytest extract_service)
- AC-S2-3 An extract response whose entries carry `quantity: 12` yields lines with quantity 1 on the price tag
  form. (vitest PriceTagRequestForm)
- AC-S2-4 The same code appearing twice in an extract response yields one line with quantity 1, not 2.
  (vitest)
- AC-S2-5 (amended by the tester, captain's ruling, phase 3 review, 21 Sep) Migration moves the `production`
  label of `ai_extract_portal_price_tag_request` onto a version containing rule (9) when the CURRENT
  production text equals the pre-r10 fallback (inserting a new version, not just row 2); an owner-edited
  production text is left alone (no new version, label untouched); a pre-existing version 2 an owner
  published for something unrelated does not collide - the migration never hardcodes `version = 2` - and
  production still ends on the rule-9 text. (pytest test_migration_ptag_0013_r10.py)

## S3. Readable spec values

- AC-S3-1 `product_specs` emits `Stainless Steel` for stored `stainless_steel` when `value_labels` is empty.
  (pytest tag_data_service)
- AC-S3-2 Emits `PVC` for `pvc`, `Rose Gold` for `rose_gold`, `Single Lever` for `single_lever`. (pytest)
- AC-S3-3 `value_labels {"pp": "Polypropylene"}` wins over the automatic form. (pytest)
- AC-S3-4 `407` (float 407.0) still emits `407`; `true` emits `Yes`; a free-text value with spaces
  (`Made in Malaysia`) is returned unchanged. (pytest)
- AC-S3-5 The `{{spec.material}}` merge field on the canvas renders `Stainless Steel` from a payload row whose
  value is `Stainless Steel` (FE pass-through unchanged). (vitest merge-fields)

## S4. Price tag description

- AC-S4-1 Migration adds `products.price_tag_description` nullable text. (pytest migration)
- AC-S4-2 `PATCH /products/{id}` with `price_tag_description` stores it; `GET /products/{id}` returns it, and
  the list serializer and `get_product` dict builder both include the key. (pytest)
- AC-S4-3 (amended by the tester, owner amendment 21 Sep after seeing S4 on the lane build, see S11) The
  product Overview edit form and Overview detail row are REMOVED - a "Price tag description" textarea does
  NOT appear on the Overview edit form, and no "Price tag description" row appears in the Overview detail
  view; the field has exactly one home, the Specifications tab (AC-S4-10 to AC-S4-14). (vitest ProductForm /
  ProductDetail)
- AC-S4-4 `resolve_tags_live` carries `price_tag_description` on the line's product row and on every part
  row. (pytest tag_data)
- AC-S4-5 `{{product.price_tag_description}}` renders the line's text; with `subjectPart: n` renders that
  part's text; with subject Parent renders the parent's. (vitest merge-fields)
- AC-S4-6 An empty description renders an empty string, never `spec_lines` or `description`. (vitest)
- AC-S4-7 The Insert field list shows `Price tag description` in group Product after Spec lines. (vitest)
- AC-S4-8 Editing the description on a product with an open request changes the tag's data hash, so
  `GET data-changes` flags the tag. (pytest data change)
- AC-S4-9 The AutoCount masters push does not write `price_tag_description`. (pytest, existing push test
  extended)
- AC-S4-10 (added by the tester, owner amendment 21 Sep, S11) The Specifications tab shows a "Price tag
  description" block directly under "Product description": the stored template in a read-only mono box, or
  `(none)` when empty; an "Edit price tag description" action (visible only with `master_data.products.edit`)
  swaps it for a prefilled textarea with Save and Cancel; Save calls the product update through
  `useUpdateProduct` with `{ price_tag_description }` and shows the new text; Cancel and Escape both discard
  the edit without saving. (vitest ProductSpecificationsTab.priceTagDescription.test.tsx)
- AC-S4-11 (added by the tester, owner amendment 21 Sep, S11) While editing, an "Insert field" button opens
  `InsertFieldDialog`; picking `Material` (from `spec.material`) inserts `{{spec.material}}` at the textarea's
  caret; the dialog offers only the Product and Specs groups - no Line, Set or part group, a product's own
  description cannot address a line. (vitest ProductSpecificationsTab.priceTagDescription.test.tsx)
- AC-S4-12 (added by the tester, owner amendment 21 Sep, S11) Under the box, "Prints as:" renders the stored
  template against THIS product's own data, built on the client from the tab's own spec rows in READABLE
  form (not the raw stored slug) - no backend call. A product whose `material` spec reads `Stainless Steel`
  and whose template is `{{spec.material}} tap` shows "Prints as: Stainless Steel tap". (vitest
  ProductSpecificationsTab.priceTagDescription.test.tsx)
- AC-S4-13 (added by the tester, owner amendment 21 Sep, S11, amends AC-S4-5) `resolvePath('product.
  price_tag_description', data, layer)` renders the STORED TEXT AS A TEMPLATE against the same subject's own
  data, one pass, not the raw text: `{{product.name}} in {{spec.material}}` stored on a product named
  `Basin Tap` with `spec.material = Stainless Steel` resolves to `Basin Tap in Stainless Steel`; with
  `subjectPart: n` the PART's own stored template renders against the PART's own data; a spec VALUE that
  itself contains the literal text `{{product.name}}` is never re-expanded (single left-to-right scan, no
  recursion); a template naming a token the data cannot answer renders that token empty; an empty or absent
  template renders empty (Q5, unchanged). (vitest merge-fields.test.tsx)
- AC-S4-14 (added by the tester, owner amendment 21 Sep, S11; corrected by the tester, S11 re-check, 21 Sep)
  `GET`/`PATCH /products/{id}` already carried `price_tag_description` (AC-S4-2) - no route or schema change
  there. This AC's original text ("no backend change... no new pytest") undersold the amendment: the
  RESOLVED-TAG-DATA schemas the canvas and the template designer actually read
  (`ResolvedLineData`/`TagPartData`/`ProductTagData`) never declared the field at all, so it never reached
  the designer even though `tag_data_service` always computed it - fixed in 5ce3bd5d8, pytest
  `test_dealer_kit_tag_data_routes.py::test_resolve_prices_carries_price_tag_description_on_the_line_and_its_parts`
  and `::test_product_tag_data_keeps_every_field`. See AC-S4-15 for the follow-on gap this same investigation
  found (a part-level edit not reaching the pin at all).
- AC-S4-15 (added by the tester, S11 re-check, phase 3, 21 Sep) A `price_tag_description` edit on ANY
  product of a combo line - the line's own host product (AC-S4-8, unchanged), a fixed part, or any
  open-group candidate, chosen or not - reaches the tag: the next `GET data-changes` flags it (or
  auto-applies it on a `designing`/`changes_requested` request, same as any other product data change,
  S8), and the tag's re-pinned row then carries the new template on that part in `parts` (every combo
  product) and, for a fixed part or the chosen candidate, in `own_parts` too. (pytest
  `test_price_tag_data_pin.py::TestAcS415APartProductsTemplateEditReachesThePin`,
  `test_dealer_kit_tag_data.py::test_ac_s4_15_resolve_tags_live_carries_price_tag_description_on_every_part_row`,
  `test_dealer_kit_tag_data_routes.py::test_resolve_prices_carries_price_tag_description_on_an_open_groups_candidates`)

## S5. Combo image

- AC-S5-1 Migration adds `product_combos.image_attachment_id` FK attachments, SET NULL on delete, and seeds
  attachment type `Combo Image` (`code combo_image`, idempotent). (pytest)
- AC-S5-2 `POST /product-combos/{id}/image` (multipart image) creates an `attachments` row of type Combo
  Image, a `product_attachments` link to the HOST product, and sets `image_attachment_id`; a non-image file
  answers 422; a combo of another company answers 404. (pytest + security)
- AC-S5-3 A second `POST` replaces: the new row is linked and referenced, the old row is unlinked and
  deleted; `DELETE /product-combos/{id}/image` clears and deletes the same way. (pytest)
- AC-S5-4 `GET /products/{id}/combos` returns `image: {attachment_id, url}` (signed) or `null`. (pytest)
- AC-S5-5 (amended by the tester, captain's ruling, phase 3 review, 21 Sep) The combo block on the product
  page shows Upload when empty, else the thumbnail with Replace and Clear; image files only; the controls
  route through a `useProductComboImage` hook (the same shape every other combo mutation on the page uses,
  not a bare service call); the image row wraps at phone width (`flex-wrap`). (vitest ProductCombosSection)
- AC-S5-11 `gallery_images` ranks a Combo Image attachment after Technical Specifications, so the host's own
  `product_image` never resolves to it; `primary_image_urls` excludes the type. (pytest product_images)
- AC-S5-6 A line whose `combo_id` names a combo with an image resolves `images[0]` to the combo image with
  `is_primary: true`, followed by the parent's gallery; a line on the same product without a combo keeps the
  gallery order. (pytest tag_data)
- AC-S5-7 A `product_image` slot with no subject on that line renders the combo image; the same slot with
  subject Parent renders the parent's own primary photo. (vitest product-block)
- AC-S5-8 The PDF payload's `images` map contains the combo attachment id. (pytest tag_sheet_export)
- AC-S5-9 Deleting the attachment nulls the combo's image and the line falls back to the gallery. (pytest)
- AC-S5-10 Changing the combo image changes the tag's data hash (red dot). (pytest)
- AC-S5-12 (added by the tester, captain's ruling, phase 3 review, 21 Sep) `POST /product-combos/{id}/image`
  refuses `x.svg` sent as `image/svg+xml` and `x.exe` sent as `image/png` with 422; `x.PNG` sent as
  `application/octet-stream` is accepted, and the stored mime is derived from the FILENAME extension
  (`image/png`), never trusted from the client's content type; the stored attachment's `company_id` is the
  HOST product's company; replacing an image whose attachment is still linked from another product's own
  link does not hard-delete that attachment or break the other product's link. (pytest test_product_combos.py)
- AC-S5-13 (added by the tester, captain's ruling, phase 3 review, 21 Sep) `attachments_entity_type_check`
  includes `product_combo_image` after the r10 migration upgrade (an attachments row with that entity_type
  inserts); downgrade restores the pre-r10 (402) value list, so `product_combo_image` is refused again; the
  combo image upload route stores `entity_type='product_combo_image'` (the value under test in the migration
  must be the value the route actually writes). (pytest test_migration_ptag_0013_r10.py + test_product_combos.py)

## S6. Any product of the parent on any tag; Not printed

- AC-S6-1 Migration adds `price_tag_request_tags.print_excluded` boolean default false. (pytest migration)
- AC-S6-2 Submit with one open group (3 candidates) still mints three tags; the portal form offers no
  "All N on one tag" option. (pytest + vitest, existing behaviour asserted)
- AC-S6-3 `resolve_tags_live` for tag 1a of a line with fixed part X and open group Kitchen Tap (A, B, C),
  chosen A: `parts` = [X, A(chosen), B, C] with `role` and `chosen`; `own_parts` = [X, A]; `set_members`
  prints X and A only. (pytest)
- AC-S6-4 The subject picker on tag 1a lists Parent, X, and the three taps grouped under "Kitchen Tap" with
  A marked "(this tag)". (vitest InspectorPanel)
- AC-S6-5 An image slot with `subjectPart` on B renders B's photo on the canvas and in the print payload of
  tag 1a; a price text bound to C shows C's price under the line's promotion. (vitest product-block +
  pytest tag_sheet_export)
- AC-S6-6 Tag total on 1a = parent + X + A (unchanged). (vitest product-block)
- AC-S6-7 `PATCH /{id}/tags/{tag}` with `print_excluded: true` stores it and the response carries it; on a
  `proof_ready` request answers 409; another company's request 404. (pytest route + security)
- AC-S6-8 `autoArrange` skips a tag with `print_excluded` (no slot, no copies); the print payload
  (`ordered_tags` / `design_media`) omits it; the export sheet list counts only printed tags. (vitest
  request-tags + pytest print payload)
- AC-S6-9 The rail row shows a `Not printed` toggle (icon button with label, `aria-pressed`); pressing it
  calls the PATCH, greys the row and shows the pill; pressing again clears it. (vitest RequestTagDesigner
  rail) Amended by the tester, 20 Sep: the toggle's ACCESSIBLE NAME is `Not printed <tag label>` with
  `aria-pressed` reflecting the state; the visible text `Not printed` lives on the separate pill
  (`data-testid="not-printed-pill"`), not on the button itself.
- AC-S6-10 Revise carries `print_excluded` on a tag whose choice set is unchanged. (pytest revise)
- AC-S6-11 A pinned row written before r10 (no `own_parts`) still renders `set_members` and Tag total from
  `parts`. (pytest `_row_from_pin`)
- AC-S6-12 (amended by the tester, captain's ruling, phase 3 review, 21 Sep) The proof (arranged sheets)
  never contains an excluded tag - including a SAVED doc whose placements were arranged before a tag was
  marked Not printed: `resolve_tag_sheet_print_payload` filters the doc's OWN sheets too, not only a
  freshly-arranged doc, and drops a sheet a filter empties out entirely; the export sheet list counts printed
  tags only. (pytest, same filter as S6-8)
- AC-S6-13 (added by the tester, captain's ruling, phase 3 review, 21 Sep) For a line [X fixed sort 0, open
  group G=A,B,C sort 1, Y fixed sort 2], tag 1b (chose B): `parts` = [X, B(chosen), Y, A, C] - the NARROW
  own-order list first (this tag's own fixed parts and its chosen candidate, in sort order), the group's
  non-chosen candidates APPENDED at the end in combo order, never interleaved at the group's own sort
  position; `own_parts` = [X, B, Y]; the index of Y is 2 on every tag of that line, whichever candidate it
  chose. (pytest test_dealer_kit_tag_data.py)

## S7. Automatic arrange

- AC-S7-1 `autoArrange` with 30 copies of a 66.7 x 31.9 tag on A4 yields two sheets: 27 on sheet 1 (3 cols
  x 9 rows, gap 0, inside a 5 mm margin), 3 on sheet 2. (vitest request-tags)
- AC-S7-2 4 copies of 143.5 x 100 yield one sheet of 2 x 2 with `rotation: 90`; 4 copies of 98 x 140 yield
  2 x 2 with `rotation: 0`; the sheet is portrait in both. (vitest)
- AC-S7-3 Adjacent slots in a group touch: `x_mm` of column 2 equals `x_mm` of column 1 plus the placed width;
  same for rows. (vitest)
- AC-S7-4 A saved doc with `pinned: true` placements re-flows on arrange; no output placement carries
  `pinned`. (vitest)
- AC-S7-5 2 copies of 143.5 x 100 plus 30 copies of 66.7 x 31.9 yield three sheets in that order: kitchen sink
  (2 of 4 slots used, rotated), small 27, small 3. (vitest)
- AC-S7-6 The arrange view shows no page, bleed or gap inputs and no drag handle; it shows a per-sheet line
  `<template name> - C x R, used of N`. (vitest ArrangeSheetView)
- AC-S7-7 Arrange writes `imposition.gap_mm = 0` and `bleed_mm = 5` into the doc; `tagSizeBounds` ceiling is
  the page minus 10 mm per axis. (vitest)
- AC-S7-8 `TagSheetRenderer` renders a `rotation: 90` tag with a transform so its printed box is height x
  width at the placed origin; the print payload passes `rotation` through unchanged. (vitest renderer + pytest
  print payload)
- AC-S7-9 The Konva arrange preview draws a rotated tag the same way (visual, browser evidence).
- AC-S7-11 Migration adds `sheet_cols`, `sheet_rows`, `sheet_turn` to `dealer_kit.tag_size_preset`; the
  preset routes read and write them; a template `print_size` with `sheet` keys round-trips through save and
  publish. (pytest) Amended by the tester, captain's ruling, phase 3 review, 21 Sep: both Publish (which
  snapshots the draft via `updateTemplate`) and Undo-after-Restore (which PUTs the pre-restore draft straight
  back) must send a `print_size` that still carries the configured `sheet` grid - neither drops a configured
  grid to a bare `doc`-only payload with no `print_size` key. (vitest tag-templates/[id]/page.test.tsx)
- AC-S7-12 A size group whose template `print_size` carries `sheet: {cols: 2, rows: 7, turn: false}` lays out
  2 x 7 at cell 100 x 41 with the tag at each cell's top-left, ignoring the derived fit. (vitest request-tags)
- AC-S7-13 A configured grid whose cell is smaller than the tag is ignored (derived fit used) and the Tag
  Size panel shows one line naming the cell size. (vitest request-tags + TagSizeControl)
- AC-S7-14 The Tag Size panel shows `Per A4 C x R turn` with derived values greyed; typing values and blur
  writes them to the template print size (template editor) or the preset on Save as size; `Auto` clears
  them. (vitest TagSizeControl)
- AC-S7-15 Lookup order: template `print_size` match, then preset with the same size, then derive; a group
  of tags resized to a preset carrying a grid uses that grid. (vitest)
- AC-S7-10 A group whose tag exceeds A4 in both rotations still produces one overflowing centred slot and the
  existing "0 per sheet" message. (vitest, existing AC-S6-3 of r6 kept)
- AC-S7-16 (added by the tester, captain's ruling, phase 3 review, 21 Sep) Two DIFFERENT request tags off ONE
  line (an open group resolved into its own tag per candidate at submit, D6), same size, quantity 1 each,
  none excluded: both reach the Arrange doc as distinct placements with distinct `request_tag_id`s.
  `autoArrange` itself places whatever `ArrangeItem[]` it is handed correctly (lib layer); a request tag
  nobody has opened on the canvas yet must still reach `arrangeItems` one layer up in `RequestTagDesigner` -
  it must not silently drop out because that component's own `tags` state record has no entry for it yet.
  (vitest lib/dealer-kit/request-tags.test.ts + RequestTagDesigner.test.tsx designer-level shape)

## S8. Auto-apply product data changes, rollback, indicator

- AC-S8-1 Migration adds `data_updated_at`, `data_update_changes`, `data_update_version` on
  `price_tag_request_tags`. (pytest migration)
- AC-S8-2 A `designing` (and a `changes_requested`) request with a pinned tag whose product list price then
  changes: the next `GET data-changes` re-pins the tag to the live data, writes ONE "Before product update"
  PageVersion carrying the old pins and an after-version, sets the three columns (changes list holds
  `list_price` old/new; version = the before-version number). (pytest, Q9 ruled)
- AC-S8-3 Three tags change between two polls: one before-version, three re-pinned tags. (pytest)
- AC-S8-4 The same edit on a `proof_ready` (and `approved`) request does NOT re-pin; the response lists the
  change as today and Keep / Update still work. (pytest, Q9 ruled)
- AC-S8-5 The list sweep (`GET price-tag-requests` with a touched row) applies the update the same way and
  `data_changed_tag_count` counts tags with `data_updated_at` set. (pytest)
- AC-S8-6 `POST tags/{id}/dismiss` clears the three columns; the count drops. (pytest) Amended by the
  tester, captain's ruling, phase 3 review, 21 Sep: Dismiss's own count-refresh must pass
  `apply_updates=False` the same way the pin route's own refresh does - a second, uncoordinated before/after
  pair for some OTHER tag's own live diff must never ride in on a dismiss call. (pytest test_price_tag_data_pin.py)
- AC-S8-7 `POST versions/{data_update_version}/restore` after an auto-update puts the old list price back on
  the tag's pin and the versions list gains a new row for the state being left. (pytest, existing restore)
- AC-S8-8 Designer rail shows the red dot on an updated tag; the Review dialog lists old -> new per field
  and offers Dismiss and Roll back; Dismiss clears the dot without a page reload; Roll back calls restore and
  the canvas re-renders the old value. (vitest RequestTagDesigner)
- AC-S8-9 (amended by the tester, captain's ruling, phase 3 review, 21 Sep) Detail header pill and list badge
  follow the request's own status: `designing`/`changes_requested` (which auto-apply, S8-2) read `Product
  data updated · N`; `proof_ready`/`approved` (flag-only, S8-4 - nothing has actually moved yet) read
  `Product data changed · N`. (vitest PriceTagRequestDetail + PriceTagRequestsList)
- AC-S8-10 A terminal request is never re-pinned. (pytest)
- AC-S8-11 The PDF payload after an auto-update renders the new value (pins are the print source). (pytest
  tag_sheet_export)
- AC-S8-12 (added by the tester, captain's test list, 20 Sep) After `POST versions/{n}/restore` on a `designing`
  request whose tag was auto-updated, the next `GET data-changes` does NOT re-apply the same live data: the tag
  keeps the restored pin, no new before-version is written, and the response lists no change for it (the
  restore acks the live hash on the restored tags, the same ack Keep writes today; a LATER product edit applies
  again). (pytest `test_price_tag_request_versions.py::TestRestoreAcksTheLiveHashOnAutoApplyStatuses`)
- AC-S8-13 (added by the tester, captain's ruling, 20 Sep, extends AC-S8-5) On a `designing` request with a
  pinned tag whose product price changed, the FIRST poll (list sweep or `GET data-changes`) auto-applies and
  stores `data_changed_tag_count = 1`; a SECOND poll with no further edit still reports
  `data_changed_tag_count = 1` - the tag still carries `data_updated_at`, so the badge holds until a person
  dismisses it, not until the next live diff happens to be empty. After `POST tags/{tag_id}/dismiss` the next
  poll reports 0. (pytest `test_price_tag_data_pin.py::TestS8AutoApplyOnDesigning::
  test_ac_s8_13_the_badge_holds_its_count_across_a_second_sweep_until_dismiss`)
- AC-S8-14 (added by the tester, captain's ruling, phase 3 review, 21 Sep) `POST versions/{n}/restore`
  clears the rolled-back tag's `data_updated_at`, `data_update_changes` and `data_update_version`, and
  `data_changed_tag_count` drops to 0 on the next poll - a restore that leaves the indicator set would keep
  showing "Product data updated" for a change that was just undone. (pytest test_price_tag_request_versions.py)
- AC-S8-15 (added by the tester, captain's ruling, phase 3 review, 21 Sep) Auto-apply requires the ACTING
  principal to hold `.process` on a real staff session: a `.view`-only caller (and an X-API-Key principal,
  whatever the acted-as user's own grants are) may still poll and see the diff, but the tag is never re-pinned
  and `data_updated_at` stays null; a `.process` holder's own read still applies exactly as today, and the
  PageVersions it writes carry `created_by` naming that user, not an anonymous system write. (pytest
  test_price_tag_data_pin.py)
- AC-S8-16 (added by the tester, captain's ruling, phase 3 review, 21 Sep) `apply_auto_data_updates` called
  twice with the same (already-applied) triples writes ONE before/after pair, not two - a version-number race
  guard against a duplicate write off the same live edit. (pytest test_price_tag_data_pin.py, single-session
  double-call; see the test's own docstring for why a true two-connection lock test is not attempted in this
  slice)

## S9. Portal Download PDF

- AC-S9-1 Detail response carries `latest_export_status` in `ready | pending | failed | null`. (pytest
  portal route, `response_model` asserted)
- AC-S9-2 `POST /public/portal/submissions/price_tag_request/{id}/export` on an `approved` request with a
  saved version queues one export as the assignee and answers 202; on `proof_ready` answers 409; on a
  request of another contact answers 404. (pytest portal route + security)
- AC-S9-3 Portal menu item at `approved` with no export: enabled, reads "Download PDF"; click calls the
  export route and the item reads "Preparing your PDF" with a spinner; when the refetched detail says
  `ready` the file streams. (vitest PriceTagRequestForm, fake timers for the 5 s poll)
- AC-S9-4 With `latest_export_status: failed` the item reads "PDF failed, try again" and click re-queues.
  (vitest)
- AC-S9-5 At `proof_ready` the item is disabled and reads "Available after approval". (vitest)
- AC-S9-6 With a READY export the click streams without queueing (today's path). (vitest)
- AC-S9-7 (added by the tester, captain's ruling, phase 3 review, 21 Sep) A second `POST .../export` while
  the first is still pending answers 202 with the SAME `download_id` and does not enqueue a second render
  (`enqueue_job` called once, one `user_downloads` row for the request); revoked visibility refuses the
  export route the same way the download route does (403 `FORM_TYPE_NOT_VISIBLE`). (pytest
  test_portal_price_tag_routes.py)
- AC-S9-8 (added by the tester, captain's ruling, phase 3 review, 21 Sep) The read-only gear's poll starts on
  MOUNT when the request already carries `latest_export_status: 'pending'` (a reload mid-export, or a second
  tab that queued it) - not only after this component's own click sets local `exportPending` state. (vitest
  PriceTagRequestForm.readOnlyGear.test.tsx)

## S10. Designer rail scroll position

- AC-S10-1 With 40 tags in the rail, scrolling the rail to the bottom and clicking the last tag leaves the
  rail's `scrollTop` unchanged and the clicked row selected. (vitest RequestTagDesigner rail, jsdom scrollTop
  set by hand) Confirmed by the tester, captain's ruling, phase 3 review, 21 Sep, with a REAL assertion (the
  numeric `scrollTop` value AND the scroll container's element identity, not merely "the rail is still in the
  document"): already green - no rail remount or scroll manipulation exists on tag select today.
- AC-S10-2 `TagCanvasEditor` still remounts per selected tag (`key`), the rail element identity does not
  change across selections. (vitest)
- AC-S10-3 (amended by the tester, captain's ruling, phase 3 review, 21 Sep) The rail is visible beside the
  Arrange view and its selected row matches the sheet's selected tag; on the Arrange canvas, selection is
  keyed by REQUEST tag id, not the placed copy's own `-c0`/`-c1` id - the placed copy whose `request_tag_id`
  matches `selectedTagId` is the one marked selected, and clicking a placed copy reports the REQUEST tag id,
  not the copy id. (vitest ArrangeSheetView + browser evidence)
- AC-S10-4 (added by the tester, captain's ruling, phase 3 review, 21 Sep) The rail wrapper is hidden at
  phone width and shown only from `md` up (`hidden md:flex`). (vitest RequestTagDesigner.rail.test.tsx)

## Browser evidence (end of lane, agent-browser, sidebar navigation)

- E1 Portal: submit a request with an open group left open (3 tags); no print control visible.
- E2 CRM designer: on tag 1a bind slots to all three taps, mark 1b and 1c Not printed, arrange shows one
  tag; the rail keeps its scroll position on select; combo image shows on a combo line;
  `{{product.price_tag_description}}` renders the product page text; `{{spec.material}}` reads
  `Stainless Steel`.
- E3 Arrange: mixed request lays out kitchen sink then small tags; Export PDF pages match the arrange view.
- E4 Portal: an approved request with a failed export downloads a PDF after one click; a product price edit
  on a designing request shows the red dot, Review lists old -> new, Roll back restores.
