# UAC: QUOTE-NO-FREE-TEXT

Status: answered 30 Oct ~22:05 (owner via crew): prod is not live, so no legacy free-text lines exist that matter.
Q1 no legacy handling, Q3 yes, Q5 (a) API + UI now; 22:40: Q2 (a) refuse a quoted product / set delete,
Q4 (a) bespoke items via New Product Application (no code).
Card: `CARD-quote-no-free-text-30oct.md`. Plan: `PLAN-quote-no-free-text-30oct.md`.

## The rule

A project quotation line saves only when it names a catalogue product OR a catalogue product set. A line with
neither is refused with HTTP 422, code `quotation_line_product_required`, message
"Every line needs a catalogue product or product set.", whatever its description says. Nothing is written.

## Server (every write path)

- AC-1 Add one line (POST `.../quotation-versions/{version_id}/lines`, `quotations.py:501`) with no product and no set, description filled:
  422 `quotation_line_product_required`; the version has no new line.
- AC-2 Edit a catalogue line (PUT `.../quotation-versions/{version_id}/lines/{line_id}`, `quotations.py:578`) sending `product_id: null` and no set: 422; the stored line
  still has its product and description.
- AC-3 Save all lines (PUT `.../quotation-versions/{version_id}/lines`, `quotations.py:532`) where one of several lines has no product and no
  set: 422; the whole save rolls back (no line added, changed or removed, totals unchanged).
- AC-4 New quotation form (POST `.../projects/{project_id}/quotation-documents`, `quotation_documents.py:124`) with a product-less line in any scope:
  422; no document, quotation or version is left behind.
- AC-5 Edit quotation form (PATCH `.../quotation-documents/{document_id}`, `quotation_documents.py:193`) with a product-less line: 422; the stored lines are unchanged.
- AC-6 No regression: a line with a product, or with a set, saves exactly as today on every path above, including
  a catalogue line whose description was edited, and a product line moved to a set and back.
- AC-7 A line with a product that is outside the project's series is still stored `is_non_standard = true`
  (the "Non-standard" meaning that remains); a product-less line is never stored (so never flagged).
- AC-8 The API schema no longer documents an off-catalog line: `product_id` / `description_snapshot` descriptions
  say a product or a set is required (`schemas/projects.py:1278-1290`).

## Editor (CRM quotation lines grid, quotation form)

- AC-9 A new line (from "Add a line" or insert-below) with a description but no product or set shows the row error
  "Pick a catalogue product or set" and the editor does not send the save.
- AC-10 Clearing the product on an existing line leaves the same row error; picking a product or set clears it.
- AC-11 No row ever shows "Not a catalogue product"; "Non-standard" still shows for an out-of-series product.
- AC-12 Usable and not clipped at 375px and 1280px.

## Product / set delete (Q2, owner 30 Oct ~22:40: refuse)

- AC-13 Deleting a product that is on any quotation line (any version, issued or draft) is refused 409 with the
  message "This product is on quotation <document_no>, so it cannot be deleted." (first quotation number in
  document_no order); the product and the line are unchanged. Same through the deferred delete
  (`record_actions.py` `product.delete` -> `ProductService.delete_product`): the action ends `failed` with that text,
  which the page toasts (`lib/pending-entity-store.ts:275-276`).
- AC-14 Same for a product set on any quotation line: 409 "This product set is on quotation <document_no>, so it
  cannot be deleted."; set and line unchanged; deferred `product_set.delete` ends `failed` with that text.
- AC-15 A product (or set) on no quotation still deletes exactly as today.
- The check lives in the service delete methods, like the new-product-application guard
  (`product_service.py:1301`), so the direct route and the deferred action share it. No migration (FKs stay SET NULL).

## Bespoke items (Q4, owner 30 Oct ~22:40: existing flow)

- AC-Q4 No code: an item not in the catalogue goes through a New Product Application
  (`procurement.new_product_applications.create`), purchasing opens the code, then it is quoted like any product.
  No inline create in the editor. User guide note on request (guide-writer).

## Review round 1 (reviewer + security-reviewer + browser pass, 30 Oct)

- AC-16 A line naming a product id the caller's company cannot see (another company's product, or an id that does
  not exist) is refused 404 `product_not_found` "That product was not found." before anything is written (today: a
  foreign id is stored with no snapshot; a random id is a 500 at flush). Mirrors the set check
  (`project_quotation_service.py:882-890`).
- AC-17 Bulk product delete (`DELETE .../master-data/products/bulk`, `product_service.py:1464`) refuses the whole
  batch with the AC-13 409 when any product in it is on a quotation; nothing is deleted.
- AC-18 The AC-13 / AC-14 409 names the FIRST quotation in document_no order when several use the product / set,
  and a product used only on an issued (frozen) version is refused too.
- AC-19 Quotation form: Save with a description-only line shows "One line still needs a catalogue product or set."
  and sends nothing (`QuotationFormClient.tsx:349-352`).
- AC-20 A row with neither product nor set never shows the "Non-standard" pill and asks the server for no series
  verdict; the row error "Pick a catalogue product or set" wraps instead of clipping at 375px.

## Out of scope

- Legacy free-text lines: none exist (prod not live), so no read-only or migration logic.
- DB CHECK constraint (Q5a).
- Seed demo script `scripts/seed_project_cs_demo.py:267-282`: dev-only, but it skips a code that is not in the
  catalogue instead of inserting a product-less line (no test; reviewer checks).
- Sample request from quotation (#1985, lane SAMPLE-FROM-QUOTE).
