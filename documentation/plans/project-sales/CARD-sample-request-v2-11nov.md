# CARD: sample request v2 (lane SAMPLE-REQUEST-V2)

Status: behaviour card v1 APPROVED (owner answers 11 Nov ~18:40 MYT: Q1 a, Q2 a, Q3 a, Q4 a; mock approved). Slice 1 building. Mock: `documentation/mockups/SAMPLE-REQUEST-V2/index.html`.

## What is true today (main 12153bdf, read in this lane)

- One staff form, `project-sales/sample-requests/components/SampleRequestForm.tsx:154-510`, drawn as a paper
  "Consignment Requisition Form" card. Fields in order: Sales Person, Date, Customer Name * (AutoCount debtor
  `AsyncCombobox`, OR a typed name when no debtor matches, `:314-333`), Project Title (`:336-343`), Registered
  project (`:344-371`), **For** (`scope_note`, `:373-379`), Request Delivery Date * (**native** `type="date"`,
  `:385-390`), Ship To * (free text, `:393-399`), Shipping Address (`:401-408`), Contact Person (`:410-416`),
  Contact Phone / Note (`:418-434`), Consignment No / PO No read-only (`:436-441`), lines (`:444-477`),
  footer fields Delivery / Loan period / Goods from / Purpose / Board (`components/common/SampleRequestFooterFields.tsx`),
  then Cancel / Save as draft / Submit (`:489-505`).
- A salesperson limited to their own requests gets the PORTAL form instead
  (`SampleRequestForm.tsx:107-119` -> `app/(auth)/portal/components/SampleRequestForm.tsx`, same fields, `:376-456`).
- Storage is all snapshot text: `ship_to_name`, `ship_to_address`, `site_contact_name/phone/note`, `scope_note`
  (`app/models/sample_request.py:97-103`). No party or contact id. `customer_id` or a typed `customer_name`
  (`:83-87`); submit accepts either (`app/services/sample_request_service.py:348-349`).
- **Many per project already works.** Nothing limits one per project. The project page has a "Samples Request"
  tab listing them (`[projectId]/components/ProjectDetailClient.tsx:106, :603-604`,
  `SampleRequestsPanel.tsx`) with a Create that opens `/project-sales/sample-requests/new?project_id=<id>`
  (`SampleRequestsPanel.tsx:117-127`), and the sample_submission stage action opens the same URL (`:124`).
- After Submit / Save draft the form goes to the request's detail page (`SampleRequestForm.tsx:249, :263`).
- Prepared/requested by = the creator already: `salesperson_id` is the actor on create
  (`sample_request_service.py:479-487`); shown read-only as "Sales Person".

### What the rest of the app already has (reused, not rebuilt)

| Need | Existing piece |
| --- | --- |
| Pick a party of THIS project with its role, other parties below, add a new party | `QuotationRecipientPicker` (`[projectId]/quotation-documents/components/QuotationRecipientPicker.tsx:43`), the proposal "To"; `GET /projects/{id}/parties` (`app/api/v1/projects/projects.py:727`, schema `ProjectPartyOnProject` `app/schemas/projects.py:2785`) |
| Link a party not yet on the project in a role, contacts join stakeholders | `apply_recipient_pick` (`app/services/project_quotation_document_service.py:262-345`): `add_party_link`, `add_registered_contacts`; party without address falls back to the project's site address |
| Contacts lightbox: tick the party's people, add a contact, add a missing number | `PartyContactsDialog` (`_shared/components/PartyContactsDialog.tsx:34`), the one dialog behind project registration (`ProjectPartiesSection.tsx:176-186`) and proposal Attn (`QuotationAttnChooser`, `QuotationRecipientPicker.tsx:258`). PR #2335 (open) turns its list into `SearchableMultiSelect` with Select all and makes Add contact the only CTA while adding: this lane builds on that PR's version |
| Guided sections, choose-first, Preview -> confirm popup | price tag request PR #2318 (open): `FormSection` (`components/common/FormSection.tsx:26`), one question shows one path, Preview is the page's only main button and the popup's main button commits |
| dd/mm/yyyy date | `DatePicker` (`components/ui/date-picker.tsx:68`) |
| Return to where you came from | `?from=` + `useReviewOriginHref` (`_shared/hooks/useReviewOrigin.ts:13`), `isSafeReviewOrigin` / `withReviewOrigin` (`_shared/lib/reviewOrigin.ts:23, :33`) |

## Rules after this lane

1. **Customer** is mandatory and is an AutoCount debtor. The typed-name fallback goes for new requests (owner:
   "customer stay mandatory and source from debtor"). Submit refuses without `customer_id`. Old rows keep their
   typed `customer_name` and still display it.
2. **Ship to is a party.** The Ship to section is the proposal's party picker: this project's parties first with
   their role ("Trading house - Bintang Trading Sdn Bhd"), every other party below, "Add <typed> as a new
   party". A party not yet on the project asks for its role and is linked to the project on save (the proposal's
   rule, same code). Its address fills Shipping address (editable, it is where the van goes); no address on the
   party -> the project's site address; neither -> empty, required on submit. No free-text company.
3. **"For" is removed** from the form (owner crossed it out). The column stays; an old request that had it shows
   it on its detail page only ("For (scope)", today `SampleRequestDetail.tsx:782`), never on the form.
4. **Contact person = the registration contact popup.** "Choose contact" opens `PartyContactsDialog` on the
   ship-to party: search, tick, "+ Add contact" (name, job title, phone), "Add number" for one without a phone.
   The picked people print as "A & B", the phone from the first (exactly the proposal Attn rule). Picked contacts
   join the project's stakeholders as the proposal's Attn does. The separate "Contact Phone / Note" pair goes
   (registration has no note); the phone comes from the contact. Without the parties edit grant: tick only.
5. **Project.** Started from a project, it is prefilled and fixed (the project title shows as text). Started from
   the list, the Registered project picker comes first; with the "require project" switch off an unregistered
   request still types a title (today's rule) and Ship to then lists all parties (none is "on this project").
6. **Return to where you started** (owner 16:30): from a project's Samples Request tab or stage action -> back to
   `/project-sales/<id>?tab=sample-requests` with the toast; from the Sample Requests list -> the list. Submit,
   Save draft, Cancel and Back alike. Mechanism: the existing `?from=` origin (above). Same for the limited
   salesperson's form.
7. **Guided layout, one main CTA.** Four sections: Customer & project / Ship to / Items / Delivery. Each section
   folds to a one-line summary once complete (price tag request pattern). The page's only primary button is
   **Preview**; it runs the submit checks and opens the popup that shows the request as the sample team will read
   it, with **Submit** as the popup's main button beside "Back to edit". "Save draft" stays a quiet link-style
   button. Request delivery date is the shared `DatePicker` (dd/mm/yyyy, after today).
8. Items keep today's lines (`components/common/SampleRequestLines.tsx`, quotation prefill included), one product
   per row. Consignment No / PO No stay read-only on the detail page; on a new form they say nothing, so they
   are not shown there (no headings that say nothing).
9. **Many per project**: already true (above). The project tab keeps listing all of them; nothing new to build
   beyond rule 6 and showing Ship to party + delivery date as columns there.

## Data (one additive migration)

`projects.sample_requests`: `ship_to_party_id` uuid NULL FK `projects.parties` ON DELETE SET NULL. The printed
name / address / contact / phone stay the existing snapshot columns (a party that moves address later does not
rewrite an old delivery, the proposal's AC-A3 reasoning). Write schema gains `ship_to_party_id`,
`ship_to_role` (link role when not on the project) and `ship_to_contact_ids` (not stored; they fill the snapshot
and join stakeholders, as `attn_contact_ids` do). No backfill.

## Real examples (dev DB)

`sample-request-v2-dev-examples.sql` (this folder) was run read-only by crew on the dev copy
(sorento_prod_1104, as of 4 Nov), aggregates only. **The table holds just 2 sample requests** (01/11 and 02/11/2026),
so every request-level number below is anecdotal, not a pattern:

- Per project: 2 projects with 1 request each. "Many per project" has not happened yet in data; the UI already allows it.
- Both registered (project_id set) and both debtor customers (customer_id set): 0 unregistered, 0 typed customer.
- Ship To typed on 2/2. Exact match to a project party 0/2, to the customer 0/2. Loose substring match: party
  0/2, customer 1/2. So today's free text does not line up with the parties list: the reason for the change, and
  weak evidence for Q2 (one of two loosely names the customer).
- Fill rates (of 2): For 0, Shipping address 0, Contact name 0, Contact phone 0, Contact note 0. Nobody fills
  "For" or the phone/note pair today, so removing them loses nothing.
- Projects behind them: project A = 1 party, 0 with an address, 0 active contacts (the "party without address"
  and "no contacts yet" edge cases are real, not hypothetical); project B = 3 parties, 2 with an address,
  1 active contact (the shape example A below uses).

The mock therefore uses project B's shape with fake names:

- **A. Registered project, ship to a trading house.** PPF2611007 "Residensi Taman Seri Murni", customer
  NUSANTARA BUILDERS SDN BHD [A/C I] (300-N021). Parties: Developer Seri Murni Development Sdn Bhd, Trading house
  Bintang Trading Sdn Bhd (address set, 2 contacts), Consultant Arkitek Lima & Rakan. Ship to = Bintang Trading,
  contact Mei Ling Tan (+60 12-345 6789). Customer and ship to differ: that is the point.
- **B. Ship to the consultant, no address on the party.** Same project, Ship to = Arkitek Lima & Rakan: address
  falls back to the project site address, editable.
- **C. Party not on the project yet.** Ship to typed "Delta Interior Works": not found -> "Add as a new party",
  role Subcontractor -> linked to PPF2611007 on save; no contacts yet -> "+ Add contact" in the popup.
- **D. Second request on the same project.** PPF2611007 already has SR-000214 (Submitted); a new one from the
  tab lands back on the tab with both rows.
- **E. Old request with free text.** SR-000118: Ship To "site office, Lot 22" (typed), For "show unit", contact
  phone + note typed. Detail page shows them unchanged; opening the draft keeps the typed Ship to as a hint
  ("Typed before: site office, Lot 22") until a party is picked; submit then needs a party.

## Edge cases

- Registered vs unregistered: rule 5. Unregistered + party picked: no link is written (no project).
- Party without address: rule 2 fallback, then required.
- Debtor vs party mismatch: allowed and expected (customer = who buys, ship to = who receives). No warning.
- Debtor that is also a party (`parties.customer_id`, `app/models/projects.py:123`): it shows in the picker like
  any party; no special case.
- Existing drafts with free text: example E. Submitted/old rows display as stored; nothing is rewritten.
- Portal (external dealer contact) form: see Q1.
- A ship-to party later removed from the project: the request keeps its snapshot; the FK only nulls on party delete.

## Owner answers (11 Nov ~18:40 MYT, supersede anything above)

- Q1 (a): staff form AND the limited salesperson's form; the salesperson form is slice 2 on a NEW branch/PR.
- Q2 (a): ship to the customer = pick it like any party, "Add as a new party" if missing.
- Q3 (a): several contacts, printed "A & B", phone from the first.
- Q4 (a): keep Save draft as a secondary button; Preview is the only main button.

## Questions (4, with recommendations)

- **Q1 Who gets the new form?** (a) staff form AND the limited salesperson's form (both are our salespeople, so
  one experience from registration on), external portal contacts keep today's form; (b) staff form only, the
  limited salesperson's form in a later slice. **Rec (a)**: the owner asked for one experience, and a limited
  salesperson is exactly who files most sample requests. Not yet verified: whether their form can read
  `GET /projects/{id}/parties` with their own-scope grants (checked in slice 2 before building).
- **Q2 Ship to the customer itself?** Today's free text often names the customer. (a) the customer is picked like
  any party (it must exist as a party; "Add as a new party" otherwise); (b) offer "Same as customer" using the
  debtor's address. **Rec (a)**: one rule ("ship to is a party"), and it puts the customer on the project's
  parties list where the owner wants it. Revisit with the dev numbers (query 3).
- **Q3 Contact person: one person or several?** (a) several, printed "A & B", phone from the first (the
  proposal Attn rule, same popup); (b) exactly one. **Rec (a)**: the same component behaves the same everywhere.
- **Q4 Draft button.** (a) Preview is the only primary button, "Save draft" a quiet secondary; (b) drop Save
  draft (autosave). **Rec (a)**: drafts exist today and autosave is its own lane.

## Slices

1. This PR: migration + backend write/validate + staff form restructure + return-to-origin + detail page Ship to
   party. Hand test, then frozen.
2. Next PR (new branch): the limited salesperson's portal form (if Q1 a).
