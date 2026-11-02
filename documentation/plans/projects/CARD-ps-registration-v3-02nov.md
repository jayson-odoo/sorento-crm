# CARD: PS-REGISTRATION-V3 v1.2 (2 Nov 2026)

**v1.2, as built (PR #2099).** All five questions answered (crew 2 Nov, owner ~21:20 and ~21:40): Q1 (b) phone
optional; Q2 the WhatsApp send picks a party of the project and a typed number for a pick with none is saved to it;
Q3 (a) Area is a selection from an editable district list per state, old free text left as typed; Q4 one
lead-source list editable in Settings, shared with leads, seeded with the list in Q4 plus "Interior designer (ID)" and
"Referral"; Q5 (b) several trading houses, subcontractors and tender parties, one of each other role. This lane owns
every new party type, `tender_party` included (#2097 reuses them). What changed from v1.1 while building:

- The roles beyond developer / architect / main contractor live in one table `projects.party_links` (project, role,
  party), not four columns, because Q5 needs several per role. The role IS the party's type.
- Lead source sits in the always-open bottom section, renamed "Lead source, customer and salesperson": Details starts
  folded in create mode, and a required field there would leave Register disabled with no visible reason.
- Contacts live in a Contacts section on the party's own page, not inside the party dialog (a new party has no id to
  hang contacts on, and the view page renders every section).
- The WhatsApp dialog keeps its free To field and adds one "Send to" picker above it (rules 10-11 as built).
- The Parties grid sorts and pages on the server (owner rule), with a Contacts column.

**Owner ruling 2 Nov ~21:20 (Q1, Q2 answered):** phone is NOT mandatory. When a proposal or quotation is sent by
WhatsApp, the user chooses which of the project's parties to send to; a chosen party with no number gets it typed on
the spot and it is saved to that party (master data). Added to this lane's scope (rules 10-13). Today the To field is
free text (`FE/[projectId]/quotation-documents/[documentId]/components/QuotationWhatsAppDialog.tsx:134-140`), seeded
from the developer's phone snapshot (`:99-102`); the dialog is shared with PS-PROPOSAL-QUOTATION (#2097).

Status: Build done, in review (PR #2099). Track: normal (migration `psr3_0001_party_contacts`: two tables, two
columns, lookup seeds). Size M. Plan: `PLAN-ps-registration-v3-02nov.md`.

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
1. Become selections: **Subcontractors, Trading houses, Tender parties** (several each), **Consultant, Interior
   designer** (one each), **Lead source** (new, lookup set `project_lead_source`), **Area** (lookup set
   `my_district_<state>`, filtered by the picked State; a new State clears the Area).
2. Stay as they are: Title (it is the name), Registered company / SPV (an identity, typed), Address, Reference (admin's
   filing string), value and dates (typed numbers). **Location is dropped from the register form** (State + Area say it;
   the column stays and still shows and edits on the project page so old rows keep their text).
3. Party types gain `subcontractor`, `interior_designer` and `tender_party`. Parties page filter and form list them.
   The new roles are rows of `projects.party_links`; the server refuses a party of the wrong type for the role
   (422 `project_party_role_mismatch`) and a second consultant or interior designer (422 `project_party_role_single`).

Party contacts
4. New master `projects.party_contacts`: party, name *, job title, phone, email, active. Managed in a Contacts
   section on the party's page with Add / Edit / Delete (Delete = the deferred `project_party_contact.delete`, 10 s,
   no confirm). A salesperson with only the submit grant can READ contacts to pick them.
5. On the register form, under each picked party, a **Contacts** multi-select lists that party's active contacts, with a
   "Add contact '<text>'" row that creates one on the party (needs `projects.parties.edit`, same as the party create row).
6. Register writes each picked contact as a `stakeholders` row on the project (party_id, name, job title, phone, email
   copied, new `stakeholders.party_contact_id` FK, SET NULL). Copy, not a live link: a contact who changes firm later does
   not rewrite who was on this project. They show in the existing Stakeholders panel.
7. Changing or clearing a party on the form drops that party's contact picks.

Lead source
8. **Lead source** selection, required on Register (and on Submit for approval); drafts stay free. Stored on
   `sales_profile.lead_source`; values from the lookup set `project_lead_source`, which leads validate against too
   (where the set was never seeded, e.g. a create_all test DB, the seed tuple `LEAD_SOURCES` answers). A project made
   by Qualify copies its lead's source. Old projects stay NULL. The project page shows the project's own source,
   else its lead's.

Customer optional
9. Customer is optional on Register, Submit and draft submit: the three `require_customer` calls go, the asterisk goes.
   A project without a customer shows "No customer yet" on its page. Nothing downstream needs it before a quotation /
   PO (to verify in Phase 2: grep every `sales_profile.customer_id` reader for a None crash).

Not in scope
- No lead picker (owner 30 Oct). No change to the Check, approve / reject or notifications.
- Quotation recipient snapshot (`recipient_*_snapshot`) is not changed; only the WhatsApp dialog's To is (rules 10-13).

WhatsApp send: choose the parties (owner 2 Nov ~21:20)
10. (as built) The send dialog gets a **Send to** picker above its free-text To: one option per party of the project
    (every role) and per person registered at it (the project's stakeholders at that party), each with its number.
    Picking one fills To. wa.me opens ONE chat per click, so several parties = pick, open, pick the next. Message and
    counter-sign link unchanged; a typed To with no pick still works and saves nothing.
11. A pick with no number on file leaves To empty with a line saying so. Typing a number and pressing Open WhatsApp
    saves it (normalised to +digits): to the person and their party contact when a person was picked, else to the
    party's own phone. It fills an EMPTY number only; a number
    already on file is used as is and can be edited for this send without being saved (no silent overwrite of master
    data).
12. The save needs the send right the user already has (`projects.projects.edit` on this project), not
    `projects.parties.edit`: one narrow endpoint `POST /projects/{id}/parties/{party_id}/phone` that refuses unless the
    party is on that project and its number is blank. Audited. (Security review: it is a master-data write by a
    lesser grant.)
13. A party with no number and nothing typed: its button stays off. No other change to sending.

## Examples (dev data)

Still owed by crew (data request on #2099). The sandbox cannot reach the dev copy. Examples come from `ps-registration-v3-dev-examples.sql` (read-only), asked
through a `crew-data-request:` comment; crew masks names. Wanted: (1) a project with architect + main contractor set,
(2) one with no customer, (3) how leads.source and informant_source are spread, (4) distinct mukim values per state,
(5) stakeholders that carry a party_id.

## Edge cases

- A party in two roles cannot happen: a role takes only a party of that type (the role IS the type). A contact picked
  twice becomes ONE stakeholder (dedup on party_contact_id).
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
- **Q3** answered (a), **Q4** answered (seed list plus ID and Referral), **Q5** answered (b). Original wording kept below.
- **Q3 Area (mukim): selection from where?** (a) a new lookup set of districts per state, seeded once from the distinct
  values already typed (crew data request) and editable in Settings; (b) stays free text. Recommend (a) only if the dev
  data shows few distinct values per state; otherwise (b).
- **Q4 Lead source list.** Recommend extending the lead list to one shared list: site visit, architect, contractor,
  dealer, inbound (call / walk-in / web), BCI / data provider, referral, tender notice, existing customer, other. Final
  list after the dev counts of `leads.source` and `leads.informant_source`.
- **Q5 One party per role, or many?** (a) one per role (like today's architect / main con); (b) several subcontractors.
  Recommend (a) on the form for now; more subcons go on the Stakeholders panel, a many-subcon picker is built when a
  real project needs two at registration.
