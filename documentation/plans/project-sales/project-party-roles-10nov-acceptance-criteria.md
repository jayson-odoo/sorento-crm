# UAC: project party roles + proposal To (lane PROJECT-PARTY-ROLES)

Plan: `PLAN-project-party-roles-10nov.md`. Card: `CARD-project-party-roles-10nov.md`.

## PR 1

- AC-1 Master data > Lookup sets lists "Project - Party role" with Developer, Architect, Main contractor,
  Trading house, Consultant, Subcontractor, Interior designer, Tender party; Many parties on for Trading
  house, Subcontractor, Tender party. No Dealer.
- AC-2 An admin with `master_data.lookup_sets.edit` adds "Quantity surveyor"; without reload of code it
  appears as a picker in every project's Parties section, after Tender party in the set's order.
- AC-3 Renaming "Main contractor" to "Main con" changes the label on the form, the project page and the party
  master; no project changes.
- AC-4 Deactivating Interior designer: a project that has one still shows it with an Inactive pill and keeps
  it on save; a project without one shows no Interior designer picker; saving a new interior designer link
  is refused.
- AC-5 Developer cannot be deactivated or deleted; deleting a role used by any party or project is refused
  with "in use, deactivate it instead"; an unused role deletes.
- AC-6 The 4 + 5 dev projects with an architect / main contractor column show the same party in the
  Architect / Main contractor picker after the migration; the old columns are unchanged.
- AC-7 A party whose usual role is Main contractor can be picked as a Subcontractor on another project; the
  picker caption reads "Main contractor".
- AC-8 "Add as a new party" with the name of an existing active party (any type) reuses that party.
- AC-9 Each role is one line; after a party is picked a "N contacts" / "Add contacts" link opens the
  contacts popup; ticking, adding a contact (name only) and adding a missing number work on create AND
  edit; the separate "Contacts at X" boxes are gone.
- AC-10 Contacts already on the project show ticked and fixed; un-ticking is not possible in the popup;
  removal stays on the Stakeholders tab.
- AC-11 Usable and not clipped at 375 and 1280.

## PR 2

- AC-12 A new proposal on PPF2611004 opens with To = PARAGON VIEW SDN BHD (developer) and its address,
  phone, email filled where the party has them.
- AC-13 The Party picker lists the project's parties first with their roles, then other parties; picking one
  autoloads name, address (party, else project site), phone, email (first Attn, else party).
- AC-14 Picking a party not on the project shows "Add as <role>" defaulting to its usual role; on Save it
  appears in the project's Parties section in that role.
- AC-15 "Choose contacts" ticks two contacts; Attn reads "MS. ANNE CHEW & MS IIYANA"; a contact newly
  created there is a stakeholder of the project and a contact of the party.
- AC-16 Every TO field stays editable; once revision A is issued the party can no longer change.
