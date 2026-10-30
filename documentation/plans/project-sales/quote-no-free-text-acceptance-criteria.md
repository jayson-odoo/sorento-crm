# UAC: QUOTE-NO-FREE-TEXT

Status: DRAFT, written against the card's recommendations; rewritten once the owner answers Q1-Q5
(`CARD-quote-no-free-text-30oct.md`). Plan: `PLAN-quote-no-free-text-30oct.md`.

## Server (every write path)

- AC-1 Add one line (POST version lines) with no product and no set, description filled: 422, code
  `quotation_line_product_required`, nothing written.
- AC-2 Edit a catalogue line sending `product_id: null` and no set: 422, the line keeps its product.
- AC-3 Save all lines (PUT version lines) where one of several lines has no product and no set: 422, the whole save
  rolls back (no line added, changed or removed).
- AC-4 New quotation form (POST quotation-documents) with a product-less line in any scope: 422, no document,
  quotation or version is left behind.
- AC-5 Edit quotation form (PATCH document) with a product-less line: 422, the stored lines are unchanged.
- AC-6 A line with a product, or with a set, still saves exactly as today on every path above (no regression),
  including an edited description on a catalogue line.
- AC-7 (Q1a) A draft version holding a legacy product-less line (row inserted directly, as old data is): re-saving
  it unchanged via save-all is refused 422; replacing that line with a product, or removing it, saves.
- AC-8 (Q1a) `revise` of an issued version holding a legacy product-less line succeeds and copies the line; the
  issued version and its PDF are untouched.
- AC-9 (Q1a) Customer amendment Apply that touches a legacy product-less line is refused with a message naming the
  line; an Apply touching only catalogue lines on the same quote works.
- AC-10 (Q2a) Deleting a product that sits on any quotation line: 409 naming the quotation number; the product and
  the line are unchanged. Same for a product set. A product on no quotation still deletes.
- AC-11 Schema text no longer says "off-catalog"; the OpenAPI description of `product_id` says a product or a set
  is required.

## Editor (CRM quotation lines grid and quotation form)

- AC-12 "Add a line" gives a row whose product picker must be filled; Save stays refused with the row in red
  "Pick a catalogue product" until a product or set is picked, or the row is removed.
- AC-13 Typing a description alone never makes a savable line.
- AC-14 (Q3a) No row ever shows "Not a catalogue product"; "Non-standard" still shows for a product outside the
  project's series.
- AC-15 A legacy product-less line opened in a draft shows the red "Pick a catalogue product" row; an issued
  version shows its lines read-only as today.
- AC-16 Usable and not clipped at 375px and 1280px.

## Out of scope

- DB CHECK constraint (Q5a: later, once the owner's prod SQL shows 0 legacy lines).
- Sample request from quotation (#1985, lane SAMPLE-FROM-QUOTE).
