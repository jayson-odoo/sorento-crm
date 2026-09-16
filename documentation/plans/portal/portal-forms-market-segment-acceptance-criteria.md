# UAC - Portal forms: grant by market segment, every kind gated, per-contact override for all five

Plan: `documentation/plans/portal/PLAN-portal-forms-market-segment.md`
Status: r4, 16 Sep 2026: PR #963 draft, review fix round (r2 base default = four legacy kinds; r4 expand-only migration)

## Journey

Actor A: a CRM admin on a desktop browser, arriving from the sidebar. Actor B: a dealer or
customer on a phone, arriving from the WhatsApp portal link.

1. **Admin grants extra forms per market segment.** User Management -> Market Segments. Each
   row shows an "Additional portal forms" chip list. Edit opens the existing modal; an
   "Additional portal forms" multi-select (kinds beyond the four every contact already has;
   today Price Tag Request) sits under the existing fields. Save. Decision: which extra kinds
   this segment gets. Nothing else asked.
2. **Admin adjusts one contact.** User Management -> Contacts -> contact -> Profile. The
   "Portal forms" block now lists all five kinds, each with its Visible / Hidden badge and
   the same Inherit / Always show / Always hide select. Inherit = the four legacy kinds every
   contact has, plus whatever the contact's market segments add. Decision per row: one. The Market segment block sits beside it, so what
   a contact inherits and why is on one screen.
3. **Contact Access Types no longer carry portal forms.** The "Portal forms" column and modal
   field are gone. Decision: none.
4. **Dealer opens the portal.** Landing offers only the kinds resolved for that contact. Every
   list, card, count, "New <kind>" button and deep link follows the same set. A contact whose
   overrides hide every kind sees an empty state with a WhatsApp CTA, not a blank page.
   Decision: which form (already there).
5. **Deploy changes nothing for today's users.** The four legacy kinds are the base every
   contact gets; the migration writes no data. Price tag stays opt-in; the one existing
   per-contact override survives.

Stakeholders told automatically: nobody. A hidden kind returns 403 with
`FORM_TYPE_NOT_VISIBLE` on every portal route, list and detail included (owner ruling: mirror
price tag exactly).

## Phase 1 (FE against mocks)

### Market Segments admin

- **AC-M1 [FE]** Given the Market Segments list, when it renders, then an "Additional portal
  forms" column shows one chip per granted kind using `portalFormKindLabel`, and "-" when none.
- **AC-M2 [FE]** Given the add/edit segment modal, when it opens, then an "Additional portal
  forms" `SearchableMultiSelect` lists only the kinds beyond `SUBMISSION_KINDS` (today: Price
  Tag Request), prefilled from the row on edit, empty on add; saving sends `portal_form_types`
  as a string array in the same payload as the other fields.
- **AC-M3 [FE]** Given the Contact Access Types list and modal, when they render, then no
  "Portal forms" column and no "Portal forms" field exist, and the create/update payload
  carries no `portal_form_types` key.

### Contact detail

- **AC-C1 [FE]** Given a contact whose portal-forms response carries five rows, when the Portal
  forms block renders, then five rows appear in `LANDING_KINDS` order (Complaint, Stock
  Inquiry, Purchase Request, Sponsorship Form, Price Tag Request), each with a Visible or
  Hidden badge from `effective` and the Inherit / Always show / Always hide select from
  `override`.
- **AC-C2 [FE]** Given any row, when the select changes, then one PUT is issued with that row's
  `form_type` and `is_enabled` true / false / null, unchanged from today.
- **AC-C3 [FE]** Given the block, when it renders, then the option label reads "Inherit"
  (neither "access types" nor "market segments": the inherited value is base plus segments).

### Portal landing

- **AC-L1 [FE]** Given `visible_form_types` on the portal contact, when the landing renders, then
  the kind picker, per-kind fetches, submissions map, totals and the "New <kind>" button all
  derive from `LANDING_KINDS.filter(k => visible_form_types.includes(k))`; no kind is offered
  or fetched unconditionally.
- **AC-L2 [FE]** Given a visible set that excludes `stock_inquiry`, when the landing opens with
  no tab in the URL or a tab not in the set, then the active tab is the first visible kind.
- **AC-L3 [FE]** Given an empty visible set (every kind hidden by override), when the landing renders, then no picker, toolbar
  or list renders; one empty state card, same shape as the per-kind empty card (icon, `py-8`),
  reads "No forms are available for your account" with a "Chat with us on WhatsApp" button
  using the existing `whatsapp_number`, or the Log out button when no number is set; the search
  box is hidden.
- **AC-L4 [FE]** Given a deep link (`/portal/c/<slug>/<kind>/new` or `/<id>`) to a kind the
  contact cannot see, when the page loads and the API answers 403 `FORM_TYPE_NOT_VISIBLE`, then
  the page shows the server message inline and a link back to the landing; no crash, no empty
  form.
- **AC-L5 [UX]** Given the empty state, when it renders at 375px and 1280px, then it is centred in
  the 768px content column, nothing clips, and nothing animates (no motion added in this lane).

## Phase 2 (backend, tester first)

### Data

- **AC-D1 [BE]** Given a schema without `market_segments.portal_form_types` (the test rewinds
  it first), when the migration runs, then that column exists as JSONB NOT NULL default `'[]'`
  and `contact_access_types.portal_form_types` STILL exists (expand only, D4 r4). Running it
  twice converges.
- **AC-D2 [BE]** Given the migration, when it runs, then it writes no data: every segment's
  `portal_form_types` stays `[]`, the `contact_portal_form_overrides` row count is unchanged and
  an existing row is byte-identical.
- **AC-D3 [BE]** Given a contact with no market segment, no access type and no override, when
  `resolve_visible_form_types` runs, then it returns exactly the four legacy kinds
  (`SUPPORTED_TYPES`), not `price_tag_request`.
- **AC-D4 [BE]** Given the migration, when downgraded, then the segment column is dropped and
  nothing else changes.

### Resolver and admin

- **AC-R1 [BE]** Given a contact in two segments granting `{price_tag_request}` and `{}`, when
  `resolve_visible_form_types` runs, then it returns the four legacy kinds plus
  `price_tag_request`; access types play no part (an access type row linked to the contact
  changes nothing).
- **AC-R2 [BE]** Given an `is_enabled=false` override for `complaint`, when resolved, then
  `complaint` is absent although it is a base kind; given no segment grant plus an
  `is_enabled=true` override for `price_tag_request`, then it is present.
- **AC-R3 [BE]** Given the market segment create and update routes, when `portal_form_types`
  carries an unknown kind, then 422; when valid, then the response echoes the list with blanks
  and duplicates stripped; an update that omits the field leaves it alone; the list endpoint
  carries the field; a user without `user_management.reference_data.manage` gets 403 on both
  (r4).
- **AC-R6 [BE]** Given a segment with `is_active=false` granting `price_tag_request`, when the
  resolver runs for a contact in it, then the kind is absent (r4).
- **AC-R7 [BE]** Given `POST /public/portal/ai-extract` and its `/schema` with a `portal.*`
  form key whose kind the contact cannot see, then 403 `FORM_TYPE_NOT_VISIBLE` (r4;
  `master.*` keys are issue #964).
- **AC-R4 [BE]** Given the contact access type create/update schemas, when a payload carries
  `portal_form_types`, then it is ignored (no 422, not persisted) and the response carries no
  such key.
- **AC-R5 [BE]** Given `GET /user-management/contacts/{id}/portal-forms`, when called, then it
  returns five rows in `GRANTABLE_PORTAL_FORM_TYPES` order with `inherited` true for the four
  legacy kinds and, for `price_tag_request`, true only when a segment grants it; `PUT` accepts any of the five and still 422s an unknown kind.

### Portal gate (public routes)

- **AC-G1 [BE]** Given a contact whose visible set excludes `complaint`, when it calls any of
  list (`?type=complaint`), create draft, update draft, delete draft, submit, detail, list
  revisions, revise, save/discard revision draft, neighbours, list attachments
  (`?kind=complaint`), upload attachment (`kind=complaint`), then each returns 403 with
  `code=FORM_TYPE_NOT_VISIBLE`. Parametrised over the four legacy kinds.
- **AC-G2 [BE]** Given the same contact, when it downloads or deletes an attachment whose link
  resolves to a submission of a hidden kind, then 403 `FORM_TYPE_NOT_VISIBLE`; covered for the
  live-link arm, the revision-history arm, and a `sponsorship_form` row living in the
  `purchase_requests` table (r4).
- **AC-G3 [BE]** Given a contact whose visible set includes the kind, when it calls the same
  routes, then behaviour is unchanged (existing suites stay green after fixtures grant
  visibility).
- **AC-G4 [BE]** Given `GET /public/portal/me`, when called, then `visible_form_types` reflects
  segment grants plus overrides for all five kinds.
- **AC-G5 [BE]** Given the price tag portal routes, when the contact's visible set excludes
  `price_tag_request`, then 403 as today (regression guard, one route).

### End to end (agent-browser, recorded evidence)

- **AC-E1 [E2E]** Sidebar -> Market Segments: edit Retail, add Price Tag Request, save; the
  chip list updates. Sidebar -> Contacts -> a Retail contact: Portal forms shows Price Tag
  Request Visible (Inherit) and the four legacy kinds Visible (Inherit). Portal (that
  contact's link) -> landing offers all five.
- **AC-E2 [E2E]** Same contact: set Complaint to Always show; portal landing now offers
  Complaint. Set to Always hide; landing hides it and a deep link to `/complaint/new` shows the
  403 message.
- **AC-E3 [E2E]** A contact with every kind Always hide: landing shows the empty state with the
  WhatsApp button, at 375px and 1280px.
- **AC-E4 [E2E]** Contact Access Types list: no Portal forms column; edit modal: no field.
