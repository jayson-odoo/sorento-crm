# CARD: configurable project party roles + proposal "To" picker (lane PROJECT-PARTY-ROLES)

Status: behaviour card v4. Owner answered Q1-Q7 on 10 Nov ~15:10 MYT (section "Owner answers" below supersedes any rule above it); mock v4 waiting on approval. No code yet.

## What is true today (origin/main a4af6565, read in this lane)

- The roles are typed into code six times:
  - backend `PARTY_TYPES` `sorento_crm_backend/app/services/project_reference_service.py:29-39`, checked by
    `_assert_party_type` `:218-228` on party create/edit;
  - backend `PARTY_LINK_ROLES` / `PARTY_LINK_SINGLE_ROLES` `app/models/projects.py:175-185`, enforced in
    `set_party_links` `app/services/project_party_contact_service.py:172-210` (role must be a link role, the
    party's `party_type` must equal the role, consultant / interior designer max one);
  - frontend `LINK_ROLES` + one fetcher per role `_shared/components/ProjectForm.tsx:66-73, :205-219`, the
    Architect and Main contractor pickers hand-written at `:941-990`;
  - frontend `PartyType` union `_shared/types/project.types.ts:18-35`, the detail page list
    `[projectId]/components/ProjectDetailClient.tsx:890-896`, the party master `parties/components/partyTypes.ts:10-27`.
- The DB does not restrict: `parties.party_type` and `party_links.role` are varchar(32), no CHECK.
- Three roles are columns, not links: `projects.developer_party_id`, `sales_profile.architect_party_id`,
  `sales_profile.main_contractor_party_id`. Developer stays a column (page 1, lane PROJECT-NAME).
- Lead source is the precedent: lookup set `project_lead_source` (`app/models/projects.py:768-784`, seeded by
  `alembic/versions/psr3_0001_party_contacts.py:83-108, :159`), edited on Master data > Lookup sets
  (`master-data-management/lookup-sets/components/OptionsSection.tsx`) under `master_data.lookup_sets.edit`
  (`app/api/v1/master_data/lookup_sets.py:180-225`). A lookup option has value, label, sort order, active,
  description (`app/models/lookup.py:34-53`); no per-option flag exists.
- A proposal's "To" is the developer, snapshotted at create (`project_quotation_document_service.py:214-237`);
  `recipient_party_id` is not accepted on create/update (`schemas/projects.py:1959-1974`); the header is free
  text (`QuotationDocumentHeader.tsx:206-251`). The recipient lives on the document row (one row per
  proposal), not per revision.

## Rules after this lane

1. **One list, admin-edited.** Party roles are a lookup set `project_party_role` ("Project - Party role") on the
   existing Lookup sets screen. Seeded with today's eight, same keys, same labels: Developer, Architect, Main
   contractor, Trading house, Consultant, Subcontractor, Interior designer, Tender party. No Dealer. An admin
   adds, renames (label), reorders, deactivates. The stored key never changes, so a rename touches no project.
2. **Many or one, per role.** Each role carries "many parties allowed". Seeded: many for Subcontractor, Trading
   house, Tender party (owner 2 Nov); one for the rest. A role set to one that already has two parties on a
   project keeps both and refuses a third (the project is not rewritten behind the user).
3. **Registration Parties section is drawn from the list.** One picker per active role in the set's order
   (Developer excluded: it is on page 1). Single pickers for "one" roles, multi pickers for "many". A new role
   appears on every project's form the moment it is saved; no deploy.
4. **Architect and main contractor become ordinary roles.** They move into `party_links` (additive migration +
   backfill from the two columns). Reads and writes go to `party_links` only. The two old columns stay in the
   DB, no longer written, until the owner OKs the drop (destructive, held).
5. **Deactivated role.** Not offered on new picks or in the party master's type picker. Projects that already
   have a party in it keep showing it (detail page + form, label as saved) and keep it on save. Its parties
   stay in the party master. Delete of a role that any party or project uses is refused ("in use, deactivate
   it instead"); an unused one deletes normally.
6. **Developer is locked in the list.** It cannot be deactivated or deleted (the registration lock and page 1
   depend on it); its label can still be renamed.
7. **Party master type.** A party still has one type, now picked from the role list. A role picker searches
   parties of that type, as today (see Q4).
8. **"To" picker on the proposal / quotation header** (PR 2). Lists the developer and every party on this
   project, each with its role ("Veritas Architects, Architect"). Picking one fills name, address, phone from
   the party and Attn + email from the party's first contact on this project; every field stays editable
   after. Default on create is the developer, as today. Saved on the document as `recipient_party_id` (see
   Q5 for when it locks).
9. **Who edits roles:** holders of `master_data.lookup_sets.edit`, same as lead source. No new permission.

## Not in this lane (named so they are not mistaken for roles)

- PO `po_source = trading_house` (`PurchaseOrderDialog.tsx:37`): where a PO came from, not a party role.
- Lead informant sources (`project_lead_service.py:16-24`, `leads/components/acceptance.ts:20-29`): a
  separate list.
- AI extract keeps filling Developer / Architect / Main contractor by name (`project_ai_extract_service.py:24-25`);
  it skips a role the admin has deactivated.
- Stakeholder roles (Decision Maker etc.) are already per template.
- WhatsApp send's party pick + fill-a-missing-number (owner 2 Nov) uses the same project-parties list; I build
  the list endpoint once in PR 2 and the WhatsApp wiring stays its own lane unless you say otherwise.

## Real examples (dev DB, 10 Nov; aggregates only, rows not committed)

- Dev data is thin: `party_links` holds 1 row in the whole DB (PPF2611003, a trading house); 12 projects,
  9 with a developer.
- Parties by type: architect 1561, developer 211, main contractor 26, trading house 1, every one active. No
  subcontractor, tender party, consultant or interior designer party exists yet.
- Backfill size: 4 projects with an architect column, 5 with a main contractor column; 0 whose party type
  differs from the column role. 0 type / role values outside the eight keys, so the seed covers all data.
- Proposals: 12 proposals + 4 quotations; every one with a recipient is addressed to the developer (2
  proposals have none). Nothing to migrate for PR 2.
- Mock uses the owner's 10 Nov screenshot as the busy example (developer PARAGON VIEW SDN BHD, A. BAKHTIAR
  ARCHITECT, AHMAD ZAKI RESOURCES BERHAD, SUBCONA, TRADING HOUSE A, TPA, CONSULTANTA, IDA) and PPF2611004
  for the proposal (developer PARAGON VIEW SDN BHD; owner screenshot: name prefilled, address / phone / email
  / attn empty).

## Edge cases

- Role key collides with an existing option value on create (case-insensitive): refused, as lookup options are
  today.
- Admin renames "Main contractor" to "Main con": every screen and the PDF "To" role caption say "Main con";
  saved projects untouched.
- Admin deactivates Consultant while a user has the registration form open: save still keeps the consultant
  already picked; a new consultant pick is refused with "Consultant is no longer a party role".
- A party whose type is a deactivated role is still pickable as the proposal "To" when it is on the project.
- Lookup sets are tenant-wide, parties are per company: every company in the tenant shares one role list
  (same as lead source today).
- dd/mm/yyyy everywhere a date shows (no new dates in this lane).

## Owner addition, 10 Nov ~13:40: pick a party's contacts in the same step (PR 1)

Today: the Parties section picks one party per role, then a SEPARATE "Contacts at <party>" box per picked
party is rendered below the whole grid (`ProjectForm.tsx:1057-1072`), and only on create (`mode === 'create'`,
`:417`; `contact_ids` is accepted on create only, `schemas/projects.py:231-232`,
`project_party_contact_service.py:266-321`). The contact create-inline exists (`PartyContactsPicker.tsx`
createOption -> `PartyContactDialog.tsx`, name the only required field) but sits far from the party.

10. **Party and contacts, one field.** Picking a party opens its contacts picker directly under it, inside
    the same role field. Many-party roles get one contacts row per picked party, captioned with the party
    name. The separate "Contacts at X" boxes are removed.
11. **Create on the spot.** A contact not found is added from the picker ("+ Add contact \"Mr Wong\""): typed
    name prefilled, phone optional (2 Nov B4), created on the party and picked in one go. A party not found
    is created on the spot as today (28 Oct), and its contacts row opens straight after.
12. **Missing number on the spot.** A picked contact without a phone shows one inline number input; saving
    writes it to the contact on the party.
13. **Edit too, not only create.** The same picker works on edit. Picks become the project's stakeholders as
    today. On edit the picker shows the stakeholders already linked from that party (Q6).
14. Permission unchanged: creating a party or contact needs `projects.parties.edit`; without it the picker
    only picks.

Q6. On edit, un-picking a contact under a party. (a) removes that person's stakeholder row from the project
    (the contact stays on the party); (b) only adds, removal stays on the Stakeholders tab.
    **Recommend (a)**: the picker then shows the truth both ways; a picker that ignores un-picks reads as a bug.

## Owner addition 2, 10 Nov ~14:00: guided proposal / quotation TO (PR 2)

Owner: "we want to make the filling in very guided and smooth and flexible at the registration and quotation
stage". This refines rule 8. Lane PROPOSAL-FORM-COLLAPSE owns the rest of the Header section; this lane
touches only the TO block.

15. **Choose the party, the header autoloads.** The TO block starts with a Party picker: the project's parties
    first ("On this project", each with its role), then every other party of the company as you type.
    Default on a new proposal is the developer, as today. Picking fills name, address, phone, email, Attn.
16. **Not on the project yet: pick or create it here, backfilled.** A party from "Other parties" or one created
    on the spot shows "Not on this project yet. Add as <role>": role defaults to the party's type, picked from
    the active roles (a "one party" role already filled on the project is not offered). On Save the party is
    linked to the project in that role and appears in its Parties section.
17. **Attn = one or more contacts of that party.** Contacts already on the project first, then the party's
    other contacts; not found: created on the spot (name only required). A contact picked here that is not a
    project stakeholder yet is added as one; a new one is also added to the party. A missing number is filled
    on the spot and saved to the contact.
18. **Two or more Attn** print joined with " & " ("ATTN: MS. ANNE CHEW & MS IIYANA", real PGB GROUP sample),
    stored in the existing `attn_name` text. Phone and email come from the first Attn, else the party's own.
19. **Address** prefills per Q7.
20. **Every field stays editable** after autoload; a typed value is never overwritten by a later re-pick
    unless the user picks a different party (then the whole block reloads from the new party).
21. Who may create a party or contact from the proposal: `projects.parties.edit`, same as registration;
    without it the pickers only pick. Backfilling a party link needs edit rights on the project.

Q7. Proposal address (owner: "the address we can get from project"). (a) the chosen party's address, falling
    back to the project's site address when the party has none; (b) always the project's site address.
    **Recommend (a)**: a letter's TO address is the addressee's own, the site already prints in the project
    title, and the fallback still gives "from the project" when the party has no address on file. Mock 4b
    shows both.

## Owner answers, 10 Nov ~15:10 MYT (supersede the rules above where they differ)

Q1 (a) lookup set + `allows_many`. Q2 (a). Q3 (a). Q4 **(b)**. Q5 (a). Q6 **(b)**. Q7 (a).

A. **One parties table for every role (Q2, owner: "we do have Parties right so should be able to reuse the
   parties table").** Confirmed: every company on a project, whatever its role (developer, architect, main
   contractor, trading house, a role an admin adds later), is ONE row in `projects.parties`. A project says
   which party plays which role through `projects.party_links (project_id, role, party_id)`; developer stays the
   `projects.developer_party_id` column. No new party table; the architect / main contractor columns are
   backfilled into `party_links` and no longer written (drop held for the owner).
B. **Any party can fill any role (Q4 b), in this lane.** A firm that is main con on one project and subcon on
   another is one party. Replaces rule 7:
   - every role picker (registration and the proposal TO) searches ALL active parties of the company, not
     only one type; `set_party_links` stops refusing a party whose type differs from the role (today
     `project_party_contact_service.py:192-197`, code `project_party_role_mismatch`);
   - **`parties.party_type` stays, as the party's usual role**: set to the role it was first created for,
     shown as the caption next to the name in every picker and as the Type column / filter on the party
     master, used as the default role when a proposal backfills the party onto a project. It never restricts
     a pick. Its values are the role lookup's keys (checked against the set, active or not, instead of
     `PARTY_TYPES`), and it can be edited on the party master;
   - "Add as a new party" on create-on-the-spot first returns an existing active party with the same name of
     ANY type (today: same name AND same type, `project_reference_service.py:244-257`), so one firm stays one
     row.
C. **Contacts in a popup (mock v4, owner feedback on v3: "too complicated", "very bloated").** Replaces rules
   10-12 and 17's picker: each role is ONE line (the party picker). Once a party is picked, a small link next
   to the role's label reads "N contacts" (or "Add contacts") and opens a contacts popup for that party
   (many-party roles: line tabs, one per picked party). In the popup the user ticks contacts, adds a contact
   (name only required, phone optional) and fills a missing number ("Add number" turns into one input, saved
   to the contact). Creating a party on the spot opens its popup straight away. The proposal's Attn uses the
   same popup: "Choose contacts" next to Attn, the ticked names fill Attn joined with " & ".
D. **The popup only adds (Q6 b).** On edit, contacts that are already the project's stakeholders show ticked
   and fixed, with "On this project". Removing a stakeholder stays on the Stakeholders tab. Same in the
   proposal popup.
E. **Proposal address (Q7 a):** the chosen party's address; when the party has none, the project's site
   address. Editable.
F. **TO locks on issue (Q5 a):** the party is changeable while the proposal is a draft and fixed once
   revision A is issued; a different party gets its own proposal.

## Questions (at most 5, each with a recommendation)

Q1. Where roles are managed. (a) lookup set `project_party_role` on the existing Lookup sets screen + one
    boolean column `allows_many` on `lookup_options` (default false, shown as a "Many parties" toggle only
    for this set); (b) a new `projects.party_roles` table with its own admin screen.
    **Recommend (a)**: it is the lead-source pattern, one column, no new screen or permission.

Q2. Architect / main contractor columns. (a) move to `party_links` + backfill, stop writing the columns, hold
    the drop for you; (b) keep them as columns and only make the other roles configurable.
    **Recommend (a)**: (b) leaves two hard-coded roles in every code path, which ruling 1 rules out.

Q3. Deactivated role on projects that use it. (a) keep showing, keep on save, not pickable for new;
    (b) hide it everywhere. **Recommend (a)**: (b) silently hides who is on a live project.

Q4. Party master type. (a) one type per party as today, pickers search that type; (b) any party can fill any
    role (a firm that is main con here and subcon there is one party). **Recommend (a)** for this lane: it
    keeps the change to "where the list comes from"; (b) changes the party master and its counts and is
    better as its own decision.

Q5. When the proposal "To" can change. (a) per proposal: changeable while the proposal is a draft, fixed once
    revision A is issued; a different party gets its own proposal (2 Nov card rule 2, one proposal per party
    so prices can differ); (b) changeable on every revision. **Recommend (a)**: it matches the 2 Nov rule and
    the existing recipient column on the document row; (b) would let revision B silently go to someone else.
