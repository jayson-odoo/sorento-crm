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
- AC-S2-5 Migration inserts `ai_extract_portal_price_tag_request` version 2 when version 1 text equals the
  pre-r10 fallback, and inserts nothing when the stored text differs. (pytest migration)

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
- AC-S4-3 The product Overview edit form shows a "Price tag description" textarea below Description; saving
  sends the field; the detail view shows it with line breaks preserved. (vitest ProductForm / ProductDetail)
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

## S5. Combo image

- AC-S5-1 Migration adds `product_combos.image_attachment_id` FK attachments, SET NULL on delete, and seeds
  attachment type `Combo Image` (`code combo_image`, idempotent). (pytest)
- AC-S5-2 `POST /product-combos/{id}/image` (multipart image) creates an `attachments` row of type Combo
  Image, a `product_attachments` link to the HOST product, and sets `image_attachment_id`; a non-image file
  answers 422; a combo of another company answers 404. (pytest + security)
- AC-S5-3 A second `POST` replaces: the new row is linked and referenced, the old row is unlinked and
  deleted; `DELETE /product-combos/{id}/image` clears and deletes the same way. (pytest)
- AC-S5-4 `GET /products/{id}/combos` returns `image: {attachment_id, url}` (signed) or `null`. (pytest)
- AC-S5-5 The combo block on the product page shows Upload when empty, else the thumbnail with Replace and
  Clear; image files only. (vitest ProductCombosSection)
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
- AC-S6-12 The proof (arranged sheets) never contains an excluded tag. (pytest, same filter as S6-8)

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
  publish. (pytest)
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
- AC-S8-6 `POST tags/{id}/dismiss` clears the three columns; the count drops. (pytest)
- AC-S8-7 `POST versions/{data_update_version}/restore` after an auto-update puts the old list price back on
  the tag's pin and the versions list gains a new row for the state being left. (pytest, existing restore)
- AC-S8-8 Designer rail shows the red dot on an updated tag; the Review dialog lists old -> new per field
  and offers Dismiss and Roll back; Dismiss clears the dot without a page reload; Roll back calls restore and
  the canvas re-renders the old value. (vitest RequestTagDesigner)
- AC-S8-9 Detail header pill and list badge read `Product data updated · N`. (vitest)
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

## S10. Designer rail scroll position

- AC-S10-1 With 40 tags in the rail, scrolling the rail to the bottom and clicking the last tag leaves the
  rail's `scrollTop` unchanged and the clicked row selected. (vitest RequestTagDesigner rail, jsdom
  scrollTop set by hand)
- AC-S10-2 `TagCanvasEditor` still remounts per selected tag (`key`), the rail element identity does not
  change across selections. (vitest)
- AC-S10-3 The rail is visible beside the Arrange view and its selected row matches the sheet's selected
  tag. (vitest ArrangeSheetView + browser evidence)

## Browser evidence (end of lane, agent-browser, sidebar navigation)

- E1 Portal: submit a request with an open group left open (3 tags); no print control visible.
- E2 CRM designer: on tag 1a bind slots to all three taps, mark 1b and 1c Not printed, arrange shows one
  tag; the rail keeps its scroll position on select; combo image shows on a combo line;
  `{{product.price_tag_description}}` renders the product page text; `{{spec.material}}` reads
  `Stainless Steel`.
- E3 Arrange: mixed request lays out kitchen sink then small tags; Export PDF pages match the arrange view.
- E4 Portal: an approved request with a failed export downloads a PDF after one click; a product price edit
  on a designing request shows the red dot, Review lists old -> new, Roll back restores.
