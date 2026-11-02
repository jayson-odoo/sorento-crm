# CARD: PS-REGISTRATION-V3 v1.1 (2 Nov 2026)

**Owner ruling 2 Nov ~21:20 (Q1, Q2 answered):** phone is NOT mandatory. When a proposal or quotation is sent by
WhatsApp, the user chooses which of the project's parties to send to; a chosen party with no number gets it typed on
the spot and it is saved to that party (master data). Added to this lane's scope (rules 10-13). Today the To field is
free text (`FE/[projectId]/quotation-documents/[documentId]/components/QuotationWhatsAppDialog.tsx:134-140`), seeded
from the developer's phone snapshot (`:99-102`); the dialog is shared with PS-PROPOSAL-QUOTATION (#2097).

Status: Plan - card posted to the owner (crew-ask), no code yet. Track: normal (carries a migration: one new
table, five new columns). Size M.

Paths: BE = `sorento_crm_backend/app`, FE = `sorento_crm_frontend/app/(protected)/project-sales`. Code read on
origin/main 46de2f6d. Owner rulings used: 2 Nov ~21:05 ("most fields are selections; party master data holds each
party's contacts; lead source recorded; customer optional"), 30 Oct ("never re-add a lead picker").

## How Register a project works today (facts)

- Wizard, create mode only (`FE/_shared/components/ProjectForm.tsx:184-187`): step 1 Check (title *, developer), step 2
  Details + "Customer and salesperson".
- Fields and what they are today:

| Field | Today | Source |
|---|---|---|
| Title * | free text | `ProjectForm.tsx:561` |
| Developer | selection, parties of type developer (create row) | `:578-579` |
| Type, Template | selection, `projects.types` / `templates` | `:466-520` |
| Registered company / SPV | free text | `:702-710`; model says "an identity, not a buyer" (`BE/models/projects.py:363-365`) |
| Location | free text ("e.g. Setia Alam, Selangor") | `:713-719` |
| State | selection, lookup set `my_state` | `:725-745` |
| Area (mukim) | free text | `:748-755` |
| Address | free text | `:759-766` |
| Reference (admin ref) | free text, admin filing no. | `:771-778` |
| Estimated value, launch date, delivery window | number / dates | `:781-823` |
| Architect, Main contractor | selection, parties of that type (create row) | `:828-876` |
| Customer | selection, server search; REQUIRED on register | `:888-903` |
| Salesperson | selection, users | `:907-920` |

- Customer is required in three places: staff register `BE/api/v1/projects/projects.py:412-413`, salesperson
  `crm_register` `BE/services/project_registration_service.py:770`, submit of a draft `:839`
  (`require_customer` `:725-732`, 422 `project_customer_required`).
- Party types: developer, architect, main_contractor, trading_house, consultant (`BE/models/projects.py:98-102`,
  validated against `PARTY_TYPES` `BE/services/project_reference_service.py:26-32,142-150`). No subcontractor, no
  interior designer. A party has ONE phone and ONE email of its own (`BE/models/projects.py:127-128`); there is no
  per-party list of people.
- People on a project are `projects.stakeholders` (name, job title, phone, email, influence, optional `party_id`),
  typed per project with "no global person master" (`BE/models/projects.py:440-480`), shown on the project page
  (`FE/[projectId]/components/StakeholdersPanel.tsx`). Nothing on the register form writes them.
- Lead source exists only on LEADS: `leads.source` from `LEAD_SOURCES` = site_visit, architect, contractor, dealer,
  inbound, other (`BE/models/projects.py:686-701`), plus `leads.informant_source` free text (bci | referral |
  walk_in | ..., `:782`). A project shows its lead's source only when it has a lead (`BE/services/project_service.py:848`).
  The register form has no lead picker (owner 30 Oct) so a project registered today records no source at all.
- Quotation recipient is derived from the DEVELOPER party (name, address, phone), `attn_name` and recipient email are
  typed (`BE/services/project_quotation_document_service.py:156-199`). Registered contacts do not feed it.

## Rules (recommended)

Selections
1. Become selections: **Subcontractor, Trading house, Consultant, Interior designer** (new, each a party select of its
   type with the existing "Create <type>" row, same as Architect), **Lead source** (new), **Area** (see Q3).
2. Stay as they are: Title (it is the name), Registered company / SPV (an identity, typed), Address, Reference (admin's
   filing string), value and dates (typed numbers). **Location is dropped from the register form** (State + Area say it;
   the column stays and still shows and edits on the project page so old rows keep their text).
3. Party types gain `subcontractor` and `interior_designer` (the "ID" from the ruling). Parties page filter and form list
   them. One party per role on the form, the same shape as Architect / Main contractor today (new columns
   `sales_profile.subcontractor_party_id`, `trading_house_party_id`, `consultant_party_id`, `interior_designer_party_id`);
   see Q5.

Party contacts
4. New master `projects.party_contacts`: party, name *, job title, phone, email, active. Managed on the party's dialog
   (Parties page) as a small table with Add / edit / remove (remove = the deferred delete, no confirm).
5. On the register form, under each picked party, a **Contacts** multi-select lists that party's active contacts, with a
   "Add contact '<text>'" row that creates one on the party (needs `projects.parties.edit`, same as the party create row).
6. Register writes each picked contact as a `stakeholders` row on the project (party_id, name, job title, phone, email
   copied, new `stakeholders.party_contact_id` FK, SET NULL). Copy, not a live link: a contact who changes firm later does
   not rewrite who was on this project. They show in the existing Stakeholders panel.
7. Changing or clearing a party on the form drops that party's contact picks.

Lead source
8. **Lead source** selection in Details, required on Register (and on Submit for approval); drafts stay free. Stored on
   `sales_profile.lead_source`; values from one list shared with leads (`LEAD_SOURCES`), so lead and project report on
   the same buckets. A project made by Qualify copies its lead's source. Old projects stay NULL ("Not recorded").
   Proposed list: see Q4.

Customer optional
9. Customer is optional on Register, Submit and draft submit: the three `require_customer` calls go, the asterisk goes.
   A project without a customer shows "No customer yet" on its page. Nothing downstream needs it before a quotation /
   PO (to verify in Phase 2: grep every `sales_profile.customer_id` reader for a None crash).

Not in scope
- No lead picker (owner 30 Oct). No change to the Check, approve / reject or notifications.
- Quotation recipient snapshot (`recipient_*_snapshot`) is not changed; only the WhatsApp dialog's To is (rules 10-13).

WhatsApp send: choose the parties (owner 2 Nov ~21:20)
10. The send dialog's free-text **To** becomes a list of the project's parties: developer, architect, main contractor,
    subcontractor, trading house, consultant, interior designer, plus each party's registered contacts (the project's
    stakeholders that carry a `party_contact_id`). One row per recipient: party, person, number, and its own "Open
    WhatsApp" button (wa.me opens ONE chat per click, so several parties = several clicks). Message and counter-sign
    link unchanged.
11. A row with no number shows an empty phone input. Typing a number and pressing Open WhatsApp saves it: to the
    party contact when the row is a contact, else to the party's own phone. It fills an EMPTY number only; a number
    already on file is used as is and can be edited for this send without being saved (no silent overwrite of master
    data).
12. The save needs the send right the user already has (`projects.projects.edit` on this project), not
    `projects.parties.edit`: one narrow endpoint `POST /projects/{id}/parties/{party_id}/phone` that refuses unless the
    party is on that project and its number is blank. Audited. (Security review: it is a master-data write by a
    lesser grant.)
13. A party with no number and nothing typed: its button stays off. No other change to sending.

## Examples (dev data)

The sandbox cannot reach the dev copy. Examples come from `ps-registration-v3-dev-examples.sql` (read-only), asked
through a `crew-data-request:` comment; crew masks names. Wanted: (1) a project with architect + main contractor set,
(2) one with no customer, (3) how leads.source and informant_source are spread, (4) distinct mukim values per state,
(5) stakeholders that carry a party_id.

## Edge cases

- A party picked twice in different roles (main con also subcon): allowed; contacts are picked once per role row, a
  person picked under both becomes ONE stakeholder (dedup on party_contact_id).
- A deactivated contact still shows on old projects (stakeholder is a copy) but is not offered.
- Contact create row with no phone: allowed (Q1 answered: phone optional); the number can be added at send time.
- AI extract fills names it read; party contacts are never invented from it (no match = hint only, as today).
- Edit mode: the new party selects show and save; contact picks are register-only (after that the Stakeholders panel
  is the place), so edit never deletes a stakeholder.

## Overlap with parallel lanes

- PS-PROPOSAL-QUOTATION (#2097): this lane changes `QuotationWhatsAppDialog.tsx` (shared by proposals and quotations)
  into the party list; they should reuse it, not fork it. "proposals can go to tender party, trading house, main con, subcon" will want these party
  contacts as recipients. This lane only creates the master + stakeholder copies; it does not touch quotation code.
- PS-QUOTE-RULES / PS-SAMPLE-TRACKING / PS-SPEC-SHEET: no shared files expected. Shared: `BE/models/projects.py` (all
  lanes add to it), alembic head (migration order: merge one at a time).

## Questions (max 5, each with a recommendation)

- **Q1** answered 2 Nov ~21:20: phone not mandatory.
- **Q2** answered 2 Nov ~21:20: the WhatsApp send picks the project's parties, a missing number is filled and saved to
  the party (rules 10-13).
- **Q3 Area (mukim): selection from where?** (a) a new lookup set of districts per state, seeded once from the distinct
  values already typed (crew data request) and editable in Settings; (b) stays free text. Recommend (a) only if the dev
  data shows few distinct values per state; otherwise (b).
- **Q4 Lead source list.** Recommend extending the lead list to one shared list: site visit, architect, contractor,
  dealer, inbound (call / walk-in / web), BCI / data provider, referral, tender notice, existing customer, other. Final
  list after the dev counts of `leads.source` and `leads.informant_source`.
- **Q5 One party per role, or many?** (a) one per role (like today's architect / main con); (b) several subcontractors.
  Recommend (a) on the form for now; more subcons go on the Stakeholders panel, a many-subcon picker is built when a
  real project needs two at registration.
