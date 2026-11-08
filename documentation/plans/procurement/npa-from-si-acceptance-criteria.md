# UAC - NPA from Stock Inquiry with product code lineage (NPA-FROM-SI)

Lane NPA-FROM-SI, issue #2200. Card: `CARD-npa-from-si-07nov.md` (rules 1-9). Plan: `PLAN-npa-from-si-07nov.md`.
Built on the card's recommended answers (Q1 (a) confirmed by the owner's v1 notes; Q2-Q5 pending the owner).

## Purchasing's ask (rules 1-2)

- AC-SI-01 The "Edit purchasing response" dialog has a checkbox "Salesperson must create a New Product Application",
  initialised from the inquiry; Save and Update & Reply both send it.
- AC-SI-02 Ticking stamps who and when on the server; unticking clears both; the payload cannot set who/when.
- AC-SI-03 Changing the ask outside the response stage (pending_purchasing / responded) is 422; sending the
  current value back is not a write and succeeds.
- AC-SI-04 Update & Reply adds "Next step: please create a New Product Application for this inquiry." while the
  inquiry is asked and has no live application (draft, submitted, resubmitted, approved, completed). A rejected or
  cancelled application does not count.
- AC-SI-05 The ask never blocks the inquiry (no status changes because of it).
- AC-SI-06 Staff SI page and portal SI view show a blue banner while asked and no live application; a green
  "New code <code> created on <date> (<NPA no.>)" once a line of a linked application has its new code.
- AC-SI-07 Portal SI view: the header's one primary button "Create new product application" shows only when the
  inquiry is Responded, asked, and has no live application of this contact; it opens the portal NPA form with the
  inquiry preset.

## Current codes -> one new code (rule 4)

- AC-CC-01 The NPA line table's existing Product code cell is a multi-select of catalogue codes (one or many, or
  none); no extra column. Read-only shows the codes as text.
- AC-CC-02 The write sends `current_product_ids` in picked order; the detail returns `current_products` in that order.
- AC-CC-03 The same code twice on one line is 422 "Product N: <code> is already a current code on this product."
- AC-CC-04 A product of another company (staff or portal) is 422.
- AC-CC-05 Leaving `current_product_ids` out keeps the saved codes; `[]` clears them.
- AC-CC-06 Current codes are locked with the rest of the line while Submitted / Approved (422 `new_product_application_locked`).
- AC-CC-07 The applicant (create) can search products; purchasing (open_code) still can; the portal has its own
  company-scoped search. Searches list only; nothing is preselected.

## Prefill (rule 3)

- AC-PF-01 From an inquiry whose code text, trimmed and case-folded, equals exactly ONE catalogue code, line 1's
  current codes = that product (removable). Anything else ("A & B", a near code) starts empty and the text shows as
  "Inquiry asked: <text>" under the cell, never parsed.
- AC-PF-02 The inquiry's remark is copied into REMARK.
- AC-PF-03 The portal prefill reads products of the contact's company only.

## Reuse before create (rule 6)

- AC-RU-01 A line whose current codes form exactly the same set (order ignored) as an earlier line that has a linked
  new code shows "A code was already created from <codes>: <new code> (<NPA no.>, <date>, "<product type>")".
- AC-RU-02 A subset, a superset, no codes, an unresolved line, a closed ("Not opening") line, and an undone link
  suggest nothing. A line is never suggested to itself.
- AC-RU-03 Newest first, at most 3, one entry per new code.
- AC-RU-04 Information only: nothing is linked or changed by a suggestion. Purchasing's "Use <code>" fills the Link
  product picker; Link is still pressed by the person.
- AC-RU-05 Portal: the suggestion names the code, date and product type, never the earlier application's number,
  id, customer, project or quantity.

## Lineage (rule 5)

- AC-LI-01 `GET .../lineage?product_id=` answers `created_from` (lines whose new code is this product, with their
  current codes and why) and `made_from_this` (new codes built from this product).
- AC-LI-02 Application id, customer and project only for NPA view-all holders; a product viewer sees the number as
  text; neither slug = 403.
- AC-LI-03 The product page has a read-only Lineage tab with both sections and the empty state "No lineage" +
  "Codes created through a New Product Application show here."

## Linked tabs (rule 7)

- AC-TB-01 SI (staff + portal): tab "New product applications (n)": number, status pill, `current -> new` codes,
  date; empty state "No new product applications" + "Applications created from this inquiry show here."
- AC-TB-02 Portal SI lists only the contact's own applications from that inquiry.
- AC-TB-03 NPA (staff + portal): tab "Stock inquiry" with number (staff: link), status, code text, description,
  purchasing response, qty; empty state "No stock inquiry" + hint.

## AI assistant (rule 8)

- AC-AI-01 Registered: stock_inquiry, new_product_application, new_product_application_line (with application and
  opened_product), new_product_application_line_source (line, product).
- AC-AI-02 "Why does <code> exist" and "what was made from <code>" answer from those entities.
- AC-AI-03 Company isolation holds for the line and source entities (no company column of their own); view_own
  holders see only their own applications' rows.

## Migration

- AC-MG-01 `npasi_0001_lineage` is additive and idempotent, id <= 32 chars, one alembic head.
