# UAC: QUOTE-NO-FREE-TEXT

Status: answered 30 Oct ~22:05 (owner via crew): prod is not live, so no legacy free-text lines exist that matter.
Q1 no legacy handling, Q3 yes, Q5 (a) API + UI now. Q2 (product delete guard) and Q4 (bespoke flow) are being
explained to the owner; each lands as its own small commit after his answer (AC-Q2 / AC-Q4 below, not built yet).
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

## Pending the owner's answer (separate commits)

- AC-Q2 (if Q2 = refuse): deleting a product or a product set that sits on any quotation line returns 409 naming
  the quotation number; product and line unchanged. A product on no quotation still deletes.
- AC-Q4 (if Q4 = existing flow): no code; the user guide points bespoke items to a New Product Application.

## Out of scope

- Legacy free-text lines: none exist (prod not live), so no read-only or migration logic.
- DB CHECK constraint (Q5a).
- Seed demo script `scripts/seed_project_cs_demo.py:267-282`: dev-only, but it skips a code that is not in the
  catalogue instead of inserting a product-less line (no test; reviewer checks).
- Sample request from quotation (#1985, lane SAMPLE-FROM-QUOTE).
