# PLAN: configurable project party roles + proposal To picker (lane PROJECT-PARTY-ROLES)

Status: Review round 1 fixed (owner approved mock v4 + Q1-Q7, 10 Nov). Track: full
(migration + permission surface + external-facing proposal header).

Card (behaviour, owner answers): `CARD-project-party-roles-10nov.md`. UAC:
`project-party-roles-10nov-acceptance-criteria.md`. Mock: `mockups/project-party-roles-10nov.html` (v4).

## Slices

### PR 1: configurable roles, one-line Parties section, contacts popup

Backend
1. Migration `ppr_0001_party_roles` (id <= 32 chars, down_revision = main's head at build time, re-parented by
   `scripts/alembic-reparent.sh`):
   - `lookup_options.allows_many BOOLEAN NOT NULL DEFAULT false` (additive);
   - seed lookup set `project_party_role` ("Project - Party role") with the eight keys, labels and order of
     today, `allows_many` true for subcontractor, trading_house, tender_party (same `_seed_lookup` shape as
     `psr3_0001_party_contacts.py:83-108`, `ON CONFLICT DO NOTHING`);
   - backfill `projects.party_links` from `sales_profile.architect_party_id` / `main_contractor_party_id`
     (`INSERT ... SELECT ... ON CONFLICT DO NOTHING`); old columns untouched (drop held for the owner).
   - downgrade: drop the column, delete the seeded set; the backfilled links stay (harmless, additive).
2. `app/services/project_party_roles.py` (one small module): `active_roles(db)`, `all_roles(db)`,
   `role_allows_many(db, key)`; reads the lookup set. `PARTY_TYPES`, `PARTY_LINK_ROLES`,
   `PARTY_LINK_SINGLE_ROLES` and the `PARTY_*` role constants go (developer stays a named constant: it is a
   fixed column, owner ruling).
3. `set_party_links` (`project_party_contact_service.py:172-210`): role must be a key of the set; a NEW link
   needs an active role, an existing link in an inactive role is kept; the party-type match check goes
   (Q4 b); "one" roles refuse a second party only for new links (rule 2).
4. Architect / main contractor: create/update stop writing the two columns and write `party_links`; every
   read (`_single_role_parties`, project serializers, registration, MCP `server.py`, AI extract) reads
   `party_links`. API keeps accepting `architect_party_id` / `main_contractor_party_id` on create/update for
   one release, mapped to links (the FE stops sending them).
5. Party create (`project_reference_service.py:231-275`): `party_type` validated against the set (any key,
   active for a new party); duplicate check by name across all types (Q4 b).
6. Party search for pickers: `party_type` filter becomes optional; results carry `party_type` for the caption.
7. Lookup option guard (`lookup_option_service.py:72-100`) for set `project_party_role` only: `developer`
   cannot be deactivated or deleted; any option referenced by `parties.party_type` or `party_links.role`
   cannot be deleted (409 "in use, deactivate it instead"); option responses carry `allows_many`.
8. `contact_ids` accepted on UPDATE too (today create only, `schemas/projects.py:231-232`); adds stakeholders,
   never removes (Q6 b).

Frontend
9. `ProjectForm.tsx` Parties section only (lane PROJECT-NAME owns page 1 / 2 layout): roles from
   `useLookupSetOptions('project_party_role')`, one `SearchableSelect` / `SearchableMultiSelect` per role,
   one shared party fetcher, label-row link "N contacts", `PartyContactsDialog` (new, wraps
   `components/ui/dialog` + `checkbox` + `tabs`, reuses `PartyContactDialog` fields). The
   `PartyContactsPicker` block at `:1057-1072` goes.
10. `ProjectDetailClient.tsx:890-896`, `partyTypes.ts`, `project.types.ts`: role list from the set; labels
    from the set, hint text dropped (no feature explanations in UI).
11. `OptionsSection.tsx`: "Many parties" switch column for set `project_party_role` only.

### PR 2: proposal / quotation TO (same lane, after PR 1)

12. `GET /projects/{id}/parties`: developer + links (role, party, its contacts on the project).
13. Create/update accept `recipient_party_id` + optional `recipient_role` (backfill link when the party is
    not on the project) + `attn_contact_ids` (stakeholder backfill); refused once revision A is issued (Q5 a).
    `_recipient_from_project` takes the picked party; address = party address else project site address
    (Q7 a); phone/email from the first Attn contact else the party.
14. `QuotationDocumentHeader.tsx` TO block only: Party picker (on-project group first), "Add as <role>"
    when not on the project, "Choose contacts" opening the PR 1 popup, Attn joined with " & ".

## Tests (red first, tester before coder)

Backend: seed + backfill migration test; `set_party_links` (inactive role kept / refused for new, any type
allowed, one-role second party refused, unknown role 422); party create name-dedupe across types; option
guard (developer, in-use delete); `contact_ids` on update adds only; PR 2 recipient pick, backfill, lock on
issue, address fallback. Frontend vitest: Parties section renders from a mocked role list (order, inactive
pill, multi vs single), contacts link + popup ticks / adds, no "Contacts at" block. Kill tests by the
reviewer.

## Out of scope / held

Dropping `sales_profile.architect_party_id` / `main_contractor_party_id` (destructive, owner). PO
`po_source`, lead informant sources, stakeholder template roles. WhatsApp send party pick (its own lane; the
PR 2 endpoint serves it).
