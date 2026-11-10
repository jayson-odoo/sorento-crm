# CARD: configurable project party roles + proposal "To" picker (lane PROJECT-PARTY-ROLES)

Status: behaviour card v2 (owner addition 10 Nov ~13:40: contacts in the same step), waiting on the owner. No code yet.

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

## Real examples (dev data, requested from crew, filled in when the rows come back)

`crew-data-request:` SQL in `documentation/plans/project-sales/project-party-roles-dev-examples.sql`:
1. PPF2611003: its developer, architect, main contractor and every `party_links` row (role, party), what the
   Parties section would show after the move.
2. Count of parties per `party_type`, active / inactive.
3. Projects with an architect or main contractor column set (the backfill size), and any project where the
   column party's `party_type` differs from the column's role (backfill must keep those, not drop them).
4. Proposals per project with `recipient_party_id`, and how many differ from the project's developer today.
5. Any `party_type` / `party_links.role` value outside the eight keys (would need seeding as an option).

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
