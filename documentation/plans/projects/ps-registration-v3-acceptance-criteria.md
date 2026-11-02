# UAC: PS-REGISTRATION-V3

Card: `CARD-ps-registration-v3-02nov.md`. Test file per group in brackets.

## A. Customer optional (rule 9) [BE test_ps_registration_v3 r9, FE ProjectForm*.test]

- A1 Staff Register without a customer saves (201).
- A2 A submit-only salesperson submits without a customer; it goes pending.
- A3 Submitting a draft without a customer goes pending.

## B. Lead source (rule 8, Q4) [r8]

- B1 Register / Submit without a lead source: 422 `project_lead_source_required`; the form keeps Register off.
- B2 A draft saves without one.
- B3 A value not in the list (or switched off in Settings): 422 `project_lead_source_invalid`.
- B4 Leads validate their source against the same list.
- B5 The project page shows the project's own source label, also when there is no lead.

## C. Party roles (rule 3, Q5) [r3, ProjectForm.registrationV3.test]

- C1 New party types Subcontractor, Interior designer, Tender party can be created and filtered.
- C2 Several subcontractors, trading houses, tender parties; one consultant, one interior designer (422
  `project_party_role_single`).
- C3 A party of the wrong type for the role, or of another company, is refused.
- C4 Edit replaces the links when sent and keeps them when left out; the page lists them by role.

## D. Party contacts (rules 4-7) [r4, r6, r7, PartyContactsPanel.test, ProjectForm.registrationV3.test]

- D1 A party page has a Contacts section; add needs a name only; delete is the 10 s countdown with Cancel.
- D2 On Register, each picked party shows a Contacts picker; picks become the project's stakeholders (copied).
- D3 Clearing a party drops its picks; a contact of a party not on the project is refused (422).
- D4 Deleting a contact keeps the stakeholder copy on old projects.

## E. Area and Location (rules 1-2, Q3) [ProjectForm.registrationV3.test]

- E1 Area is off until a State is picked, then lists that state's districts; a new State clears it.
- E2 An area typed before the list existed still shows as itself on edit.
- E3 Location is not on the register form; edit still shows and saves it.

## F. WhatsApp send to a party (rules 10-13) [r10-r13, QuotationWhatsAppDialog.parties.test]

- F1 "Send to" lists every party of the project and each person registered at it, with their number.
- F2 Picking one with a number fills To.
- F3 Picking one with no number says so; the number typed is saved to that person (and their party contact) or the
  party on Open WhatsApp.
- F4 A number already on file is never overwritten from the send (409 on the server).
- F5 Free-typed To still works and saves nothing.

## G. Parties grid (owner rule) [PartiesClient.test, parties_list tests]

- G1 Sort and paging are server side for every sortable column; a Contacts column shows the count.
