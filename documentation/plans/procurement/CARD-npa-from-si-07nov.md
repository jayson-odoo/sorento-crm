# Behaviour card: NPA from Stock Inquiry, with product code lineage (NPA-FROM-SI)

Status: card filed 7 Nov 2026; mock v2 after the owner's v1 notes ("multi select at product code field just like
current form"), which also settle Q1 (a). Q2-Q5 wait for the owner. Size L, full track (additive migration,
portal surface). Issue #2200. Builds on NEW-PRODUCT-APP (#1769, merged 22 Oct).
Paths: BE = `sorento_crm_backend/app/`, FE = `sorento_crm_frontend/`. Mock: `mockups/npa-from-si-v2.html` (v1 kept for the record).

**Waits for the product manager's artifact** (not readable from the lane sandbox): the exact field list of the
"third example" layout, any status the PM wants beyond the shipped ones, and whether "the same change" (not only
the same codes) is part of the reuse match. Everything marked (ART) below is a default until the artifact is relayed.

## What exists today (measured, main 3200ee1a)

- **NPA record ships** (`models/new_product_application.py:50`): header + lines, one line = one code wanted;
  `stock_inquiry_id` FK (ONE inquiry per NPA, `:69`); per line `proposed_code` (text), `description` (PRODUCT TYPE),
  dimension / material / thickness / packing, brand, qty, purchasing's cost and the explicit link
  `opened_product_id` (`:156`) = the NEW code once AutoCount has sent it. Statuses draft -> submitted -> approved ->
  completed, plus rejected / cancelled (`:47`). The CRM never creates the code; purchasing links the synced product.
- **Prefill from the SI ships** (`services/new_product_application_service.py:673`): customer text, project,
  target date, line 1 = SI code text as `proposed_code`, description, qty. Text only, nothing matched.
- **Staff SI page**: gear item "Create new product application" on a Responded SI
  (`stock-inquiries/components/StockInquiryDetail.tsx:598`) and a "New product applications" row listing linked NPAs
  (`:1213`). Not a tab. The SI page has no tabs at all.
- **Portal SI view** (`app/(auth)/portal/components/SubmissionForm.tsx`, kind `stock_inquiry`): no NPA button, no
  linked NPA list. Tabs exist (Details / Comments / Revisions, `:2486`) with an `extraTabs` slot (`:1822`) that only
  the staff embed fills today.
- **Portal NPA form** (`app/(auth)/portal/components/NewProductApplicationForm.tsx:146`): picks one of the contact's
  own Responded SIs and prefills (`/new-product-application/prefill`, own only). Start-from-SI prop exists
  (`startFromInquiryId`, `:153`) but nothing in the portal passes it.
- **Purchasing reply** = "Edit purchasing response" dialog (`StockInquiryDetail.tsx:970`) -> Update & Reply
  (`services/procurement_service.py:6900`), free text + attachments. There is no "NPA needed" signal anywhere.
- **No "current codes"** anywhere: nothing records which existing products an NPA line is based on, so lineage and
  reuse cannot be answered today.
- **Product page** tabs: basic / pricing / specifications / suppliers / attachments
  (`master-data-management/products/components/ProductForm.tsx:322`). No lineage.
- **AI assistant registry** (`services/assistant_registry/`, AI tools standard): no stock inquiry or NPA entity yet.

## What ships

1. **Purchasing asks for an NPA on its reply.** The "Edit purchasing response" dialog gains one checkbox
   **Salesperson must create a New Product Application**. Stored on the SI (`stock_inquiries.npa_requested`,
   boolean, + who / when). Update & Reply adds one sentence to the outgoing message: "Next step: please create a
   New Product Application for this inquiry." (Q2). It never blocks the SI (Responded stays the SI's final status).
2. **The salesperson sees the next step** on the portal SI view (and the staff SI page): a blue banner
   "Purchasing asks you to create a New Product Application." with the page's one primary button
   **Create new product application** while the SI has no live NPA (live = not cancelled / rejected). Once an NPA
   exists the banner reads "NPA-000123 Submitted" with a link; once its code is linked: green
   "New code SRTWB893 created on 3 Nov 2026 (NPA-000123)". This is the "code created" indicator: read from the
   NPA line's `opened_product_id` + `resolved_at`, no second flag for purchasing to forget.
3. **Create from the SI, prefilled.** The button opens the NPA New form with the SI preset (portal: own Responded
   SI only, as today's prefill). Prefill adds to today's: the SI's remark into REMARK and **Current product codes** per Q3.
   **Follow-up, not in this lane:** offering the SI's attachments on the NPA. A portal delete of a shared link would
   remove the SI's file too (the generic portal attachment delete), so it needs its own link-only path; today the
   applicant attaches files as before. Dimension / material / brand are NOT on the SI today (`models/procurement.py:1061-1069`), so they stay
   empty (ART: if the PM wants them asked on the SI, that is an SI change, follow-up).
4. **Current codes -> one new code** (Q1 (a), owner v1 notes). The form stays today's form: the existing
   **Product code** cell of the line table (`components/common/NewProductApplicationLines.tsx:93,115`, an `Input`
   today) becomes a `SearchableMultiSelect` (`components/common/SearchableMultiSelect.tsx`) of catalogue codes,
   one or many = the CURRENT codes; empty = a brand-new item. Same product search as Link product (ignores dashes,
   spaces, case; only lists; a person picks). No extra column. The line's NEW code stays what purchasing links
   (`opened_product_id`): exactly one per line, shown as `CBM111-BL -> CBM111-BL-69` once linked. The old free-text
   `proposed_code` stays in the table (no drop) but leaves the form; when the SI's code text did not equal one
   catalogue code, it shows read-only under the cell as "Inquiry asked: <text>" so nothing the salesperson typed on
   the SI is lost (never parsed).
5. **Lineage is remembered.** Stored as rows `new_product_application_line_sources (line_id, product_id, position)`.
   Lineage = a resolved line: its sources -> its opened product, why = the line's PRODUCT TYPE text + the NPA
   (number, applicant, customer, project, qty, date). No separate lineage table: the NPA is the record of why.
   A product page shows it (Q5): **Lineage** tab with "Created from: SRTWB888 (NPA-000123, 3 Nov 2026, 'use the
   existing model but no tap hole & overflow')" and "New codes made from this product: ...". Empty state:
   heading "No lineage" + hint "Codes created through a New Product Application show here."
6. **Reuse before create** (owner rule: EXACT set, explicit codes, suggestion only). When a line's picked current
   codes form exactly the same SET (order ignored, same company) as an earlier line that has a linked new code, the
   line shows: "A code was already created from SRTWB888: **SRTWB893** (NPA-000123, 3 Nov 2026,
   'use the existing model but no tap hole & overflow')". Several earlier matches: newest first, up to 3.
   - Applicant (staff or portal): information only; they decide whether to still submit.
   - Purchasing on Link product: the same line carries a **Use SRTWB893** button that fills the Link product picker
     with that product; purchasing still presses Link. Nothing is applied by itself.
   - No match on a subset, superset, similar code, or text (ART: "same change" may join the rule later).
   - Portal sees code + date + product type text only (Q4).
7. **Linked tabs on both sides** (Q5). SI (staff page and portal view): tab **New product applications (n)**
   listing number, status pill (`Badge`), new codes, date; empty state "No new product applications" + hint
   "Applications created from this inquiry show here." NPA (staff detail and portal view): tab **Stock inquiry**
   with the SI's number (link), status, code text, purchasing response; empty state "No stock inquiry" + hint.
   One SI per NPA stays (today's FK); the SI side lists many.
8. **AI assistant**: register `stock_inquiry`, `new_product_application` and `new_product_application_line`
   (with its current codes and new code) in `services/assistant_registry/procurement.py`, view slugs as the screens,
   so "why does SRTWB893 exist" and "was a code made from SRTWB888 before" answer from the same rows.
9. **Permissions**: none new. Lineage tab on a product = `master_data.products.view`; NPA links inside it only for
   NPA viewers (others see the number as text). Portal: own SIs and own NPAs only (today's rules); the reuse
   suggestion is the only cross-applicant read and carries no NPA number, customer or project (Q4).

## Data

Crew data request on the dev copy (7 Nov, PR #2233, aggregates + masked rows):
- Responded SIs whose purchasing response asks for a new code / NPA: 7 of 89.
- NPAs on the copy: 0 (feature merged 22 Oct, not used yet), so no reuse history exists today.
- Responded SIs whose code text equals exactly one catalogue code (trim, case-fold): **61 of 89**: Q3 (a) prefills
  the current code for about two in three.
- Mock v2 case: SI26-0193, CBM111-BL, "client want the mirror size with 600 mm x 900 mm", qty 270 (the new code in
  the mock is invented).

## Examples

| # | Input | Result |
|---|---|---|
| A | SI-26-0412 Responded; purchasing ticks "must create an NPA", reply "Supplier can do no tap hole & overflow" | WhatsApp reply carries the next-step sentence; portal SI shows the blue banner + Create button |
| B | Salesperson presses Create on the portal | NPA form: SI preset, project/customer/qty/target/remark copied, SI image attached, current codes = SRTWB888 (Q3 (a): SI code text equals one product code exactly) |
| C | Submit, approve; AutoCount sends SRTWB893; purchasing links it | Line shows SRTWB888 -> SRTWB893; SI banner turns green "New code SRTWB893 created on <date>"; SRTWB893's Lineage tab: created from SRTWB888 via NPA-000123 |
| D | Next month another salesperson picks current code SRTWB888 | Line shows "A code was already created from SRTWB888: SRTWB893 (...)"; purchasing gets "Use SRTWB893" |
| E | Current codes SRTWB1163 + SRTBF11840 (basin + cabinet set) | Matches only an earlier line with exactly {SRTWB1163, SRTBF11840}; {SRTWB1163} alone does not match |
| F | SI code text "SRTWB1163 & SRTBF11840" | Q3 (a): no exact single-code match, so current codes start empty; the text stays in Product code; salesperson picks both |

## Edge cases

- A source product deactivated later: lineage kept, "Inactive" badge (as Opened as today).
- A linked new code undone by purchasing: it leaves the lineage and stops being suggested at once (read live).
- The same product picked twice on one line: refused, "SRTWB888 is already a current code on this product".
- A current code from another company: 422 (company scoped like `link_line`).
- Revise / Rejected: current codes are editable like the other line fields; locked while Submitted / Approved.
- NPA without SI (raised from the list): Stock inquiry tab shows its empty state.

## Questions (max 5, each with a recommendation)

- **Q1 Shape. Answered (a)** by the owner's v1 notes ("follow current forms"). Was: (a) Keep the multi-product NPA; EACH line = current codes -> one new code (the paper form is one
  line; a set-order of 3 colours stays one NPA). (b) One NPA = exactly one new code (one line, a second product
  needs a second NPA). **Recommend (a)**: no rework of the shipped form, the Excel and the open-code flow; (b)
  forces three NPAs for the colour case of #1769.
- **Q2 Purchasing's flag.** (a) Checkbox on the reply, non-blocking, adds one sentence to the outgoing reply.
  (b) Same, and the SI cannot be closed/voided until an NPA exists. **Recommend (a)**: Responded is already the SI's
  end; a block would strand SIs whose customer walked away.
- **Q3 Prefill current codes.** (a) Prefill only when the SI's code text, trimmed and case-folded, equals ONE
  product code exactly; shown picked, removable. (b) Never prefill; the salesperson always picks. **Recommend (a)**:
  exact equality is not fuzzy matching, and the common case (one existing code) is then zero typing; anything else
  ("A & B", "flange only") starts empty.
- **Q4 Reuse suggestion on the portal.** (a) Code + date + the earlier PRODUCT TYPE text only (no NPA number,
  customer, project, qty). (b) Everything incl. the earlier NPA number. **Recommend (a)**: the earlier NPA belongs to
  another salesperson whose customer must not leak; staff see the NPA link.
- **Q5 Where linkage shows.** (a) Tabs: SI "New product applications (n)", NPA "Stock inquiry", product "Lineage"
  (staff + portal for SI/NPA; product staff only). (b) Keep today's rows on the SI page, add rows elsewhere.
  **Recommend (a)**: the owner asked for tabs; the portal already has the tab strip, the staff SI page gains one.
