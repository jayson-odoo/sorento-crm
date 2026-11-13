# UAC: PRICETAG-ALA-CARTE

Owner answers 13 Nov (relayed by crew): Q1 (b) empty Package = ala carte, placeholder "Ala carte"; Q2 every newly
added line starts ala carte and the same product may be added any number of times; Q3 (b) bare code from Upload a
file = ala carte; Q4 (a) no new label on read-only screens; Q5 (a) package in the revision snapshot.
Crew: drop the request+product unique (no replacement); key everything that matched lines by product by line id.

Terms: "package" of a product line = its combo_id; null = ala carte. Set lines unchanged throughout.

## Editor (shared PriceTagLinesTable + usePriceTagLineEditor, portal and CRM create/edit)
- AC-1 A product line whose product has 1+ combos shows the Package select (today 2+ only). A product with no combo
  and a set line show none.
- AC-2 Options = each combo by name. Clearable; empty shows the placeholder "Ala carte". No extra option.
- AC-3 Every newly added product line starts ala carte (combo_id null, no parts), also when the product has exactly
  one combo: the single-combo auto-pick is removed for single pick, multi-add and Upload a file.
- AC-4 Choosing a combo sets it and its parts; clearing sets combo_id null and parts [] (choosePackage).
- AC-5 Lines that arrive saved (draft reopen, duplicate, revise) keep their saved package exactly; the combos lookup
  never changes combo_id.
- AC-6 The same product may be added any number of times, whatever the packages (ala carte twice included): no
  "is already on this request." guard for products, in single pick and multi-add. Sets keep today's guard.
- AC-7 Multi-add: a product already on the request is not skipped or greyed; each tick adds a line through the same
  single-pick function.
- AC-8 A combo with zero parts is still a package (combo_id set), not ala carte.

## Upload a file (AI read, portal handleAIExtractApply)
- AC-9 A bare product row starts ala carte; a "+" row matching a stored combo starts on that combo (unchanged).
- AC-10 Rows are never merged into an existing line by product: each product row becomes its own line. (Sets keep
  today's behaviour.)

## Backend
- AC-11 No DUPLICATE_LINE 422 for products on create, update (replace_lines) or portal revise: the same product
  any number of times, any packages, is accepted. Sets: unchanged (same set twice still 422).
- AC-12 Saved lines carry their id in the form payload (draftLinesPayload `id` for lines loaded from the server).
  replace_lines and portal revise carry marketing's tags (ids, splits, overrides, print_excluded) and the template
  pick by that line id. A payload line without a known id gets fresh tags, except the compatibility fallback: it
  claims the first not-yet-claimed old line with the same (product_id, product_set_id, combo_id), each old line
  claimed at most once. Repeated products never crash a re-save and never swap tags between lines.
- AC-13 An ala carte line of a product that has combos renders the product's own list price, template and
  accessories, never the combo's (regression).
- AC-14 DB: constraint uq_ptag_line_request_product dropped (IF EXISTS); no replacement unique; the model's
  __table_args__ match; uq_ptag_line_request_set unchanged. Migration ptag_0023_line_package up / down / up; down
  re-adds the constraint and fails clearly if a request holds a product twice.
- AC-15 Deleting a combo leaves its lines ala carte (ON DELETE SET NULL, unchanged) and never fails, also when
  the same request already has an ala carte line of that product.
- AC-16 (Q5) Price tag revision snapshot carries item_code (product or set code) and package (combo name or
  "Ala carte"); a package change shows in History as "Product line N package: <old> -> <new>".

## Package warning (crew answer 13 Nov, from the owner's "empty Package = ala carte")
- AC-17 "No package chosen" is dropped on both sides (FE packageWarningFor, BE package_warning): a guarded product
  line with combos and an empty Package (ala carte) has no warning. "No package defined" (guarded product with no
  combo) and "Missing: ..." (chosen combo with parts removed) stay.
